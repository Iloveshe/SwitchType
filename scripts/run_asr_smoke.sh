#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WHISPER_BIN="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_bin)"
WHISPER_MODEL="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_model)"
WHISPER_NO_GPU="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_no_gpu)"
SMOKE_FALLBACK_AUDIO="$ROOT_DIR/third_party/whisper.cpp/samples/jfk.wav"
CONFIG="$ROOT_DIR/bench/config/benchmark.asr-smoke.local.json"
MANIFEST="$ROOT_DIR/bench/samples/smoke/manifest.jsonl"
REPORT="$ROOT_DIR/bench/reports/asr-smoke.md"

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

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/create_tts_smoke_sample.py" \
  --audio "$ROOT_DIR/bench/samples/smoke/smoke-001.wav" \
  --manifest "$MANIFEST" \
  --fallback-audio "$SMOKE_FALLBACK_AUDIO"

CREATE_CONFIG_ARGS=(
  --output "$CONFIG"
  --whisper-bin "$WHISPER_BIN"
  --whisper-model "$WHISPER_MODEL"
)
if [ "$WHISPER_NO_GPU" = "1" ]; then
  CREATE_CONFIG_ARGS+=(--whisper-no-gpu)
fi

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/create_local_config.py" "${CREATE_CONFIG_ARGS[@]}"

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/run_benchmark.py" \
  --config "$CONFIG" \
  --hotwords "$ROOT_DIR/bench/config/hotwords.example.json" \
  --manifest "$MANIFEST" \
  --report "$REPORT"

echo "ASR smoke report:"
echo "  $REPORT"
