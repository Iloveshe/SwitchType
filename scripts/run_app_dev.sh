#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_BIN="$ROOT_DIR/app/SwitchType/.build/debug/SwitchType"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_app_dev.sh [--debug-transcript]

Options:
  --debug-transcript   Bypass whisper.cpp and return a fixed transcript after recording.

Environment:
  SWITCHTYPE_WHISPER_BIN           Path to whisper-cli for real ASR mode.
  SWITCHTYPE_WHISPER_MODEL         Path to ggml model for real ASR mode.
  SWITCHTYPE_WHISPER_NO_GPU        Set to 1 to pass -ng to whisper-cli.
  SWITCHTYPE_HOTWORDS_CONFIG       Path to hotwords JSON.
  SWITCHTYPE_TRANSCRIPT_OVERRIDE   Transcript returned in debug-transcript mode.
  SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME
                                    Refuse recording unless the current default input device matches this name.
EOF
}

USE_DEBUG_TRANSCRIPT=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --debug-transcript)
      USE_DEBUG_TRANSCRIPT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-$ROOT_DIR/app/SwitchType/.build/clang-module-cache}"

swift build --disable-sandbox --package-path "$ROOT_DIR/app/SwitchType"

export SWITCHTYPE_HOTWORDS_CONFIG="${SWITCHTYPE_HOTWORDS_CONFIG:-$ROOT_DIR/bench/config/hotwords.example.json}"
echo "Expected input device: ${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:-not enforced}"

if [ "$USE_DEBUG_TRANSCRIPT" -eq 1 ]; then
  export SWITCHTYPE_TRANSCRIPT_OVERRIDE="${SWITCHTYPE_TRANSCRIPT_OVERRIDE:-帮我看一下扣德克斯的皮阿尔 issue 有没有过 CI}"
  echo "Running SwitchType with transcript override:"
  echo "  $SWITCHTYPE_TRANSCRIPT_OVERRIDE"
else
  export SWITCHTYPE_WHISPER_BIN="${SWITCHTYPE_WHISPER_BIN:-$ROOT_DIR/third_party/whisper.cpp/build/bin/whisper-cli}"
  export SWITCHTYPE_WHISPER_MODEL="${SWITCHTYPE_WHISPER_MODEL:-$ROOT_DIR/third_party/whisper.cpp/models/ggml-large-v3-turbo.bin}"
  echo "Running SwitchType with real ASR:"
  echo "  SWITCHTYPE_WHISPER_BIN=$SWITCHTYPE_WHISPER_BIN"
  echo "  SWITCHTYPE_WHISPER_MODEL=$SWITCHTYPE_WHISPER_MODEL"
  echo "  SWITCHTYPE_WHISPER_NO_GPU=${SWITCHTYPE_WHISPER_NO_GPU:-0}"
fi

exec "$APP_BIN"
