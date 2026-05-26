from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.asr_config import DEFAULT_WHISPER_BIN, DEFAULT_WHISPER_MODEL, resolve_path


def asr_config(
    whisper_bin: str,
    whisper_model: str,
    whisper_no_gpu: bool,
    whisper_language: str,
    timeout_seconds: int,
    expected_input_device_name: str | None = None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "asr_backend": "local_whisper",
        "local_whisper_profile": "custom",
        "whisper_bin": whisper_bin,
        "whisper_model": whisper_model,
        "whisper_no_gpu": whisper_no_gpu,
        "whisper_language": whisper_language,
        "timeout_seconds": timeout_seconds,
    }
    if expected_input_device_name:
        config["expected_input_device_name"] = expected_input_device_name
    return config


def write_config(output: Path, config: dict[str, object], force: bool) -> None:
    if output.exists() and not force:
        raise SystemExit(f"{output} already exists; pass --force to overwrite it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a SwitchType ASR config JSON file.")
    parser.add_argument("--output", default=Path.home() / ".switchtype/asr.json", type=Path)
    parser.add_argument("--whisper-bin", default=str(resolve_path(ROOT, DEFAULT_WHISPER_BIN)))
    parser.add_argument("--whisper-model", default=str(resolve_path(ROOT, DEFAULT_WHISPER_MODEL)))
    parser.add_argument("--no-gpu", action="store_true", help="Set whisper_no_gpu to true for CPU-only whisper.cpp.")
    parser.add_argument("--whisper-language", default="zh", help='whisper.cpp language code. Use "zh" for Simplified Chinese with English code-switching.')
    parser.add_argument("--timeout-seconds", default=120, type=int)
    parser.add_argument("--expected-input-device-name", help='Expected macOS input device name, for example "DJI MIC MINI".')
    parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    args = parser.parse_args()

    config = asr_config(
        whisper_bin=args.whisper_bin,
        whisper_model=args.whisper_model,
        whisper_no_gpu=args.no_gpu,
        whisper_language=args.whisper_language,
        timeout_seconds=args.timeout_seconds,
        expected_input_device_name=args.expected_input_device_name,
    )
    write_config(args.output.expanduser(), config, force=args.force)
    print(f"Wrote {args.output.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
