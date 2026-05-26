#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LIMIT="${SWITCHTYPE_PUBLIC_LIMIT:-50}"
SPLIT="${SWITCHTYPE_PUBLIC_SPLIT:-test}"
EXPECTED_COUNT="${SWITCHTYPE_PUBLIC_EXPECTED_COUNT:-$LIMIT}"
MANIFEST="${SWITCHTYPE_PUBLIC_MANIFEST:-$ROOT_DIR/bench/samples/public/manifest.jsonl}"
AUDIO_DIR="${SWITCHTYPE_PUBLIC_AUDIO_DIR:-$ROOT_DIR/bench/samples/public/audio}"
CONFIG="${SWITCHTYPE_PUBLIC_CONFIG:-$ROOT_DIR/bench/config/benchmark.local.json}"
HOTWORDS="${SWITCHTYPE_PUBLIC_HOTWORDS:-$ROOT_DIR/bench/config/hotwords.example.json}"
REPORT="${SWITCHTYPE_PUBLIC_REPORT:-$ROOT_DIR/bench/reports/public-asr.md}"
TIMEOUT_SECONDS="${SWITCHTYPE_PUBLIC_TIMEOUT_SECONDS:-900}"
WHISPER_BIN="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_bin)"
WHISPER_MODEL="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_model)"
WHISPER_NO_GPU="$(PYTHONPATH="$ROOT_DIR" python3 "$ROOT_DIR/scripts/resolve_asr_config.py" --key whisper_no_gpu)"
ENABLE_SENSEVOICE="${SWITCHTYPE_ENABLE_SENSEVOICE:-1}"
SENSEVOICE_MODEL="${SWITCHTYPE_SENSEVOICE_MODEL:-}"
SENSEVOICE_HUB="${SWITCHTYPE_SENSEVOICE_HUB:-}"
SENSEVOICE_VAD_MODEL="${SWITCHTYPE_SENSEVOICE_VAD_MODEL:-}"

if [ -n "${SWITCHTYPE_PUBLIC_PYTHON:-}" ]; then
  PUBLIC_PYTHON="$SWITCHTYPE_PUBLIC_PYTHON"
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PUBLIC_PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PUBLIC_PYTHON="python3"
fi

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

if ! "$PUBLIC_PYTHON" -c "import datasets" >/dev/null 2>&1; then
  echo "Missing public dataset dependency for $PUBLIC_PYTHON" >&2
  echo "Run: ./.venv/bin/pip install -r requirements-public.txt" >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/bench" "$PUBLIC_PYTHON" "$ROOT_DIR/bench/scripts/prepare_ascend_public_samples.py" \
  --split "$SPLIT" \
  --limit "$LIMIT" \
  --manifest "$MANIFEST" \
  --audio-dir "$AUDIO_DIR" \
  --hotwords "$HOTWORDS"

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/validate_samples.py" \
  --manifest "$MANIFEST" \
  --expected-count "$EXPECTED_COUNT" \
  --require-audio

CREATE_CONFIG_ARGS=(
  --output "$CONFIG"
  --whisper-bin "$WHISPER_BIN"
  --whisper-model "$WHISPER_MODEL"
  --sensevoice-python "$FUNASR_PYTHON"
  --timeout-seconds "$TIMEOUT_SECONDS"
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

echo "Public ASR benchmark complete:"
echo "  $REPORT"
