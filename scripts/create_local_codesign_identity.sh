#!/usr/bin/env bash
set -euo pipefail

IDENTITY="${SWITCHTYPE_LOCAL_CODESIGN_IDENTITY:-SwitchType Local Development}"
KEYCHAIN="${SWITCHTYPE_CODESIGN_KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"

if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -F "\"$IDENTITY\"" >/dev/null; then
  echo "Codesigning identity already exists: $IDENTITY"
  exit 0
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/switchtype-codesign.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

OPENSSL_CONFIG="$WORK_DIR/openssl.cnf"
KEY_PATH="$WORK_DIR/key.pem"
CERT_PATH="$WORK_DIR/cert.pem"
P12_PATH="$WORK_DIR/identity.p12"
P12_PASSWORD="$(uuidgen)"

cat > "$OPENSSL_CONFIG" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = code_signing
prompt = no

[req_distinguished_name]
CN = $IDENTITY

[code_signing]
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature
extendedKeyUsage = codeSigning
subjectKeyIdentifier = hash
EOF

openssl req \
  -new \
  -newkey rsa:2048 \
  -x509 \
  -sha256 \
  -days 3650 \
  -nodes \
  -config "$OPENSSL_CONFIG" \
  -keyout "$KEY_PATH" \
  -out "$CERT_PATH" >/dev/null 2>&1

openssl pkcs12 \
  -export \
  -out "$P12_PATH" \
  -inkey "$KEY_PATH" \
  -in "$CERT_PATH" \
  -passout "pass:$P12_PASSWORD" >/dev/null 2>&1

security import "$P12_PATH" \
  -k "$KEYCHAIN" \
  -P "$P12_PASSWORD" \
  -T /usr/bin/codesign >/dev/null

security add-trusted-cert \
  -d \
  -r trustRoot \
  -k "$KEYCHAIN" \
  "$CERT_PATH" >/dev/null 2>&1 || true

if ! security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -F "\"$IDENTITY\"" >/dev/null; then
  echo "Imported certificate, but it is not listed as a valid codesigning identity: $IDENTITY" >&2
  exit 1
fi

echo "Created codesigning identity: $IDENTITY"
echo "Run: SWITCHTYPE_CODESIGN_IDENTITY=\"$IDENTITY\" make package"
