#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${SWITCHTYPE_REAL_MANIFEST:-$ROOT_DIR/bench/samples/manifest.30-template.jsonl}"
CONFIG="${SWITCHTYPE_BENCHMARK_CONFIG:-$ROOT_DIR/bench/config/benchmark.local.json}"
HOTWORDS="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_hotwords_config.py")"
REPORT="${SWITCHTYPE_REAL_REPORT:-$ROOT_DIR/bench/reports/real-asr.md}"
EXPECTED_COUNT="${SWITCHTYPE_REAL_EXPECTED_COUNT:-30}"
ALLOW_PARTIAL="${SWITCHTYPE_REAL_ALLOW_PARTIAL:-0}"
UPDATE_README="${SWITCHTYPE_REAL_UPDATE_README:-1}"
WHISPER_BIN="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_bin)"
WHISPER_MODEL="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_model)"
WHISPER_NO_GPU="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_no_gpu)"
ENABLE_SENSEVOICE="${SWITCHTYPE_ENABLE_SENSEVOICE:-1}"
SENSEVOICE_MODEL="${SWITCHTYPE_SENSEVOICE_MODEL:-}"
SENSEVOICE_HUB="${SWITCHTYPE_SENSEVOICE_HUB:-}"
SENSEVOICE_VAD_MODEL="${SWITCHTYPE_SENSEVOICE_VAD_MODEL:-}"

if [ -n "${SWITCHTYPE_FUNASR_PYTHON:-}" ]; then
  FUNASR_PYTHON="$SWITCHTYPE_FUNASR_PYTHON"
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  FUNASR_PYTHON="$ROOT_DIR/.venv/bin/python"
else
  FUNASR_PYTHON="python3"
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

if [ "$ALLOW_PARTIAL" = "1" ]; then
  PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/validate_samples.py" \
    --manifest "$MANIFEST" \
    --require-audio
else
  PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/validate_samples.py" \
    --manifest "$MANIFEST" \
    --expected-count "$EXPECTED_COUNT" \
    --require-audio
fi

CREATE_CONFIG_ARGS=(
  --output "$CONFIG"
  --whisper-bin "$WHISPER_BIN"
  --whisper-model "$WHISPER_MODEL"
  --sensevoice-python "$FUNASR_PYTHON"
)
if [ "$WHISPER_NO_GPU" = "1" ]; then
  CREATE_CONFIG_ARGS+=(--whisper-no-gpu)
fi
if [ "$ENABLE_SENSEVOICE" = "1" ]; then
  CREATE_CONFIG_ARGS+=(--enable-sensevoice)
fi
if [ -n "$SENSEVOICE_MODEL" ]; then
  CREATE_CONFIG_ARGS+=(--sensevoice-model "$SENSEVOICE_MODEL")
fi
if [ -n "$SENSEVOICE_HUB" ]; then
  CREATE_CONFIG_ARGS+=(--sensevoice-hub "$SENSEVOICE_HUB")
fi
if [ -n "$SENSEVOICE_VAD_MODEL" ]; then
  CREATE_CONFIG_ARGS+=(--sensevoice-vad-model "$SENSEVOICE_VAD_MODEL")
fi

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/create_local_config.py" "${CREATE_CONFIG_ARGS[@]}"

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/run_benchmark.py" \
  --config "$CONFIG" \
  --hotwords "$HOTWORDS" \
  --manifest "$MANIFEST" \
  --report "$REPORT"

if [ "$UPDATE_README" = "1" ]; then
  PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/update_readme_benchmark.py" \
    --readme "$ROOT_DIR/README.md" \
    --report "$REPORT"
fi

echo "Real ASR benchmark complete:"
echo "  $REPORT"
if [ "$UPDATE_README" = "1" ]; then
  echo "README benchmark summary updated."
else
  echo "README benchmark summary not updated."
fi
