#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_SMOKE_BIN="$ROOT_DIR/app/SwitchType/.build/debug/SwitchTypeASRSmoke"
SMOKE_AUDIO="${SWITCHTYPE_APP_HOTWORDS_AUDIO:-$ROOT_DIR/third_party/whisper.cpp/samples/jfk.wav}"
TRANSCRIPT_OVERRIDE="${SWITCHTYPE_APP_HOTWORDS_TRANSCRIPT:-扣德克斯 的 皮阿尔 issue}"
EXPECTED_TEXT="${SWITCHTYPE_APP_HOTWORDS_EXPECT:-Codex 的 PR issue}"

if [ ! -x "$APP_SMOKE_BIN" ]; then
  echo "Missing app ASR smoke binary: $APP_SMOKE_BIN" >&2
  echo "Run: make swift-build" >&2
  exit 1
fi

if [ ! -f "$SMOKE_AUDIO" ]; then
  echo "Missing smoke audio: $SMOKE_AUDIO" >&2
  echo "Run: make asr-smoke" >&2
  exit 1
fi

SWITCHTYPE_TRANSCRIPT_OVERRIDE="$TRANSCRIPT_OVERRIDE" \
SWITCHTYPE_HOTWORDS_CONFIG="${SWITCHTYPE_HOTWORDS_CONFIG:-$ROOT_DIR/bench/config/hotwords.example.json}" \
"$APP_SMOKE_BIN" --audio "$SMOKE_AUDIO" --postprocess --expect "$EXPECTED_TEXT"
