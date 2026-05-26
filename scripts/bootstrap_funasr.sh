#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_PYTHON="${SWITCHTYPE_FUNASR_BASE_PYTHON:-python3}"
VENV_DIR="${SWITCHTYPE_FUNASR_VENV:-$ROOT_DIR/.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

if [ ! -x "$PYTHON_BIN" ]; then
  "$BASE_PYTHON" -m venv "$VENV_DIR"
fi

"$PIP_BIN" install --upgrade pip setuptools wheel
"$PIP_BIN" install -r "$ROOT_DIR/requirements-sensevoice.txt"

"$PYTHON_BIN" -c "from funasr import AutoModel; import torch; print('FunASR ready with torch ' + torch.__version__)"

echo "Use this Python for SenseVoice:"
echo "  SWITCHTYPE_FUNASR_PYTHON=$PYTHON_BIN"
