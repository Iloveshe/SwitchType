#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_SMOKE_BIN="$ROOT_DIR/app/SwitchType/.build/debug/SwitchTypeASRSmoke"
WHISPER_BIN="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_bin)"
WHISPER_MODEL="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_model)"
WHISPER_NO_GPU="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_no_gpu)"
SMOKE_AUDIO="${SWITCHTYPE_APP_ASR_SMOKE_AUDIO:-$ROOT_DIR/third_party/whisper.cpp/samples/jfk.wav}"
EXPECTED_TEXT="${SWITCHTYPE_APP_ASR_SMOKE_EXPECT:-country}"
SMOKE_LANGUAGE="${SWITCHTYPE_APP_ASR_SMOKE_LANGUAGE:-en}"

if [ ! -x "$APP_SMOKE_BIN" ]; then
  echo "Missing app ASR smoke binary: $APP_SMOKE_BIN" >&2
  echo "Run: make swift-build" >&2
  exit 1
fi

if [ ! -x "$WHISPER_BIN" ]; then
  echo "Missing executable whisper CLI: $WHISPER_BIN" >&2
  echo "Run: ./scripts/bootstrap_whisper_cpp.sh large-v3-turbo" >&2
  exit 1
fi

if [ ! -f "$WHISPER_MODEL" ]; then
  echo "Missing whisper model: $WHISPER_MODEL" >&2
  echo "Run: ./scripts/bootstrap_whisper_cpp.sh large-v3-turbo" >&2
  exit 1
fi

if [ ! -f "$SMOKE_AUDIO" ]; then
  echo "Missing smoke audio: $SMOKE_AUDIO" >&2
  exit 1
fi

if ! OUTPUT="$(SWITCHTYPE_WHISPER_BIN="$WHISPER_BIN" \
  SWITCHTYPE_WHISPER_MODEL="$WHISPER_MODEL" \
  SWITCHTYPE_WHISPER_NO_GPU="$WHISPER_NO_GPU" \
  SWITCHTYPE_WHISPER_LANGUAGE="$SMOKE_LANGUAGE" \
  "$APP_SMOKE_BIN" --audio "$SMOKE_AUDIO" --expect "$EXPECTED_TEXT" 2>&1)"; then
  printf '%s\n' "$OUTPUT" >&2
  if [[ "$WHISPER_NO_GPU" != "1" ]] && [[ "$OUTPUT" == *"ggml_metal_buffer_init"* || "$OUTPUT" == *"failed to allocate buffer"* ]]; then
    echo "Metal/GPU allocation failed. Retry with: SWITCHTYPE_WHISPER_NO_GPU=1 make app-asr-smoke" >&2
  fi
  exit 1
fi

printf '%s\n' "$OUTPUT"
