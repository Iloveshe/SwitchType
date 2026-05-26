#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-large-v3-turbo}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
THIRD_PARTY_DIR="$ROOT_DIR/third_party"
WHISPER_DIR="$THIRD_PARTY_DIR/whisper.cpp"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required. Install it with Homebrew or Xcode tooling." >&2
  exit 1
fi

mkdir -p "$THIRD_PARTY_DIR"

if [ ! -d "$WHISPER_DIR/.git" ]; then
  git clone https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
else
  git -C "$WHISPER_DIR" pull --ff-only
fi

cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build"
cmake --build "$WHISPER_DIR/build" -j --config Release

sh "$WHISPER_DIR/models/download-ggml-model.sh" "$MODEL"

cat <<EOF
whisper.cpp is ready.

Binary:
  $WHISPER_DIR/build/bin/whisper-cli

Model:
  $WHISPER_DIR/models/ggml-$MODEL.bin

Suggested environment:
  export SWITCHTYPE_WHISPER_BIN="$WHISPER_DIR/build/bin/whisper-cli"
  export SWITCHTYPE_WHISPER_MODEL="$WHISPER_DIR/models/ggml-$MODEL.bin"
EOF

