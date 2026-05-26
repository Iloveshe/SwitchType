from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.asr_config import resolve_whisper_settings


def with_whisper_options(command: list[str], whisper_bin: str, no_gpu: bool) -> list[str]:
    updated = list(command)
    if updated:
        updated[0] = whisper_bin
    if no_gpu and "-ng" not in updated and "--no-gpu" not in updated:
        updated.insert(1, "-ng")
    if "-l" not in updated and "--language" not in updated:
        insert_at = updated.index("-otxt") if "-otxt" in updated else len(updated)
        updated[insert_at:insert_at] = ["-l", "auto"]
    return updated


def with_command_executable(command: list[str], executable: str) -> list[str]:
    updated = list(command)
    if updated:
        updated[0] = executable
    return updated


def with_option(command: list[str], option: str, value: str | None) -> list[str]:
    updated = list(command)
    if value is None:
        return updated
    if option in updated:
        option_index = updated.index(option)
        if option_index + 1 < len(updated):
            updated[option_index + 1] = value
        else:
            updated.append(value)
    else:
        updated.extend([option, value])
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a local SwitchType benchmark config.")
    parser.add_argument("--template", default=Path("bench/config/benchmark.example.json"), type=Path)
    parser.add_argument("--output", default=Path("bench/config/benchmark.local.json"), type=Path)
    parser.add_argument("--asr-config", default="", help="Path to a SwitchType ASR config JSON file.")
    parser.add_argument("--whisper-bin", default=None)
    parser.add_argument("--whisper-model", default=None)
    parser.add_argument(
        "--whisper-no-gpu",
        action="store_true",
        default=None,
        help="Add whisper.cpp -ng/--no-gpu to the command.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Override command engine timeout in seconds.")
    parser.add_argument("--enable-sensevoice", action="store_true")
    parser.add_argument("--sensevoice-python", default="python3", help="Python executable that can import funasr.")
    parser.add_argument("--sensevoice-model", default=None, help="Override the SenseVoice model id or local path.")
    parser.add_argument("--sensevoice-hub", default=None, choices=["ms", "modelscope", "hf", "huggingface"])
    parser.add_argument("--sensevoice-vad-model", default=None, help="Set to none/off/disabled to skip FunASR VAD.")
    args = parser.parse_args()

    whisper_settings = resolve_whisper_settings(
        ROOT,
        os.environ,
        asr_config_path=args.asr_config or None,
        whisper_bin=args.whisper_bin,
        whisper_model=args.whisper_model,
        whisper_no_gpu=args.whisper_no_gpu,
    )
    whisper_bin = args.whisper_bin or whisper_settings.whisper_bin
    whisper_model = args.whisper_model or whisper_settings.whisper_model
    config = json.loads(args.template.read_text(encoding="utf-8"))
    if args.timeout_seconds is not None:
        config["timeout_seconds"] = args.timeout_seconds
    for engine in config.get("engines", []):
        if engine.get("name") == "whisper_cpp":
            engine["enabled"] = True
            engine["model"] = whisper_model
            engine["command"] = with_whisper_options(
                engine.get("command", []),
                whisper_bin,
                whisper_settings.whisper_no_gpu,
            )
        elif engine.get("name") == "sensevoice_funasr":
            engine["enabled"] = bool(args.enable_sensevoice)
            if args.sensevoice_model is not None:
                engine["model"] = args.sensevoice_model
            command = with_command_executable(engine.get("command", []), args.sensevoice_python)
            command = with_option(command, "--hub", args.sensevoice_hub)
            command = with_option(command, "--vad-model", args.sensevoice_vad_model)
            engine["command"] = command
        elif engine.get("type") == "fake":
            engine["enabled"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
