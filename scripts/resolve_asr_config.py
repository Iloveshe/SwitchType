from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.asr_config import resolve_whisper_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve SwitchType local ASR settings.")
    parser.add_argument("--key", choices=["whisper_bin", "whisper_model", "whisper_no_gpu"], default="")
    args = parser.parse_args()

    settings = resolve_whisper_settings(ROOT)
    values = {
        "whisper_bin": settings.whisper_bin,
        "whisper_model": settings.whisper_model,
        "whisper_no_gpu": "1" if settings.whisper_no_gpu else "0",
    }
    if args.key:
        print(values[args.key])
    else:
        print(json.dumps(values, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
