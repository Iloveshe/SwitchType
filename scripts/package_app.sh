#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/app/SwitchType"
BUILD_DIR="$PACKAGE_DIR/.build/debug"
APP_DIR="$ROOT_DIR/dist/SwitchType.app"
ARCHIVE_PATH="$ROOT_DIR/dist/SwitchType-0.1.0.zip"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
LOCAL_CODE_SIGN_IDENTITY="${SWITCHTYPE_LOCAL_CODESIGN_IDENTITY:-SwitchType Local Development}"
CODE_SIGN_IDENTITY="${SWITCHTYPE_CODESIGN_IDENTITY:-}"

if [[ -z "$CODE_SIGN_IDENTITY" ]]; then
  if security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$LOCAL_CODE_SIGN_IDENTITY\"" >/dev/null; then
    CODE_SIGN_IDENTITY="$LOCAL_CODE_SIGN_IDENTITY"
  else
    {
      echo "Unable to find required local codesigning identity: $LOCAL_CODE_SIGN_IDENTITY"
      echo "Run ./scripts/create_local_codesign_identity.sh outside the sandbox, then rerun make package outside the sandbox so macOS permissions stay attached to the signed app."
      echo "For throwaway builds only, explicitly set SWITCHTYPE_CODESIGN_IDENTITY=- to use ad-hoc signing."
    } >&2
    exit 2
  fi
fi

export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-$PACKAGE_DIR/.build/clang-module-cache}"

swift build --disable-sandbox --package-path "$PACKAGE_DIR"

rm -rf "$APP_DIR"
rm -f "$ARCHIVE_PATH"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$BUILD_DIR/SwitchType" "$MACOS_DIR/SwitchType"
cp "$BUILD_DIR/SwitchTypeDoctor" "$MACOS_DIR/SwitchTypeDoctor"
cp "$BUILD_DIR/SwitchTypeDoubaoShadow" "$MACOS_DIR/SwitchTypeDoubaoShadow"
cp "$BUILD_DIR/SwitchTypeHotkeyProbe" "$MACOS_DIR/SwitchTypeHotkeyProbe"
cp "$ROOT_DIR/bench/config/hotwords.example.json" "$RESOURCES_DIR/hotwords.example.json"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>SwitchType</string>
  <key>CFBundleIdentifier</key>
  <string>dev.switchtype.SwitchType</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>SwitchType</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>SwitchType records your speech locally while the global hotkey is held.</string>
</dict>
</plist>
PLIST

cat > "$RESOURCES_DIR/README.txt" <<'README'
SwitchType development app bundle.

Before running, set these environment variables if launching from a shell:

SWITCHTYPE_WHISPER_BIN=/path/to/whisper.cpp/build/bin/whisper-cli
SWITCHTYPE_WHISPER_MODEL=/path/to/model.bin
SWITCHTYPE_HOTWORDS_CONFIG=/path/to/hotwords.json

When launching the .app with open/Finder, create ~/.switchtype/asr.json instead:

{
  "whisper_bin": "/path/to/whisper.cpp/build/bin/whisper-cli",
  "whisper_model": "/path/to/model.bin",
  "whisper_no_gpu": false,
  "whisper_language": "zh",
  "timeout_seconds": 120
}

The app needs Microphone and Accessibility permission.
Bundled helper diagnostics:

dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor --focused-text-json
dist/SwitchType.app/Contents/MacOS/SwitchTypeHotkeyProbe
README

if [[ "$CODE_SIGN_IDENTITY" != "skip" ]]; then
  echo "Signing $APP_DIR with identity: $CODE_SIGN_IDENTITY"
  codesign --force --deep --sign "$CODE_SIGN_IDENTITY" --identifier dev.switchtype.SwitchType "$APP_DIR"
fi

(
  cd "$ROOT_DIR/dist"
  zip -qr "$(basename "$ARCHIVE_PATH")" "SwitchType.app"
)

echo "Packaged $APP_DIR"
echo "Archived $ARCHIVE_PATH"
