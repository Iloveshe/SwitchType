#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_MANIFEST="${SWITCHTYPE_REAL_SOURCE_MANIFEST:-$ROOT_DIR/bench/samples/manifest.30-template.jsonl}"
PREVIEW_MANIFEST="${SWITCHTYPE_REAL_PREVIEW_MANIFEST:-$ROOT_DIR/bench/samples/manifest.recorded-preview.jsonl}"
REPORT="${SWITCHTYPE_REAL_PREVIEW_REPORT:-$ROOT_DIR/bench/reports/real-asr-preview.md}"
MIN_DURATION="${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25}"

PYTHONPATH="$ROOT_DIR/bench" python3 "$ROOT_DIR/bench/scripts/sample_status.py" \
  --manifest "$SOURCE_MANIFEST" \
  --min-duration "$MIN_DURATION" \
  --valid-manifest-output "$PREVIEW_MANIFEST"

SWITCHTYPE_REAL_MANIFEST="$PREVIEW_MANIFEST" \
SWITCHTYPE_REAL_REPORT="$REPORT" \
SWITCHTYPE_REAL_ALLOW_PARTIAL=1 \
SWITCHTYPE_REAL_UPDATE_README=0 \
  "$ROOT_DIR/scripts/run_real_benchmark.sh"
