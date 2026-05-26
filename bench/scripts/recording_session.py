from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

try:
    from bench.scripts.sample_status import SampleStatus, collect_status
except ModuleNotFoundError:
    from sample_status import SampleStatus, collect_status


FINAL_BENCHMARK_COMMAND = (
    "SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall "
    "SWITCHTYPE_SENSEVOICE_HUB=hf "
    "SWITCHTYPE_SENSEVOICE_VAD_MODEL=none "
    "scripts/run_real_benchmark.sh"
)


@dataclass(frozen=True)
class RecordingPlan:
    valid_count: int
    expected_count: int
    remaining_count: int
    invalid_counts: dict[str, int]
    commands: list[str]


def build_recording_plan(
    statuses: list[SampleStatus],
    expected_count: int = 30,
    device_name: str | None = None,
    ffmpeg_input: str | None = None,
) -> RecordingPlan:
    valid_count = sum(1 for status in statuses if status.state == "valid")
    remaining_count = max(expected_count - valid_count, 0)
    invalid_counts = Counter(status.state for status in statuses if status.state != "valid")
    commands: list[str] = []

    device_value = _shell_double_quoted(device_name or "<device name>")
    input_prefix = _recording_input_prefix(device_name=device_name, ffmpeg_input=ffmpeg_input)
    device_check_command = None if ffmpeg_input else f"EXPECT_DEVICE_NAME={device_value} make record-devices"

    if valid_count >= expected_count and not invalid_counts:
        commands.extend(
            [
                FINAL_BENCHMARK_COMMAND,
                "python3 scripts/release_preflight.py",
            ]
        )
    elif valid_count == 0:
        commands.extend(
            [
                "make app-permissions",
                "make record-devices",
                f"{input_prefix} SWITCHTYPE_WHISPER_NO_GPU=1 make record-preview",
                "make sample-status",
            ]
        )
        if device_check_command:
            commands.insert(2, device_check_command)
    else:
        commands.extend(
            [
                "make app-permissions",
                "make record-devices",
                "make real-benchmark-preview",
                f"{input_prefix} LIMIT=5 make record-next",
                "make sample-status",
            ]
        )
        if device_check_command:
            commands.insert(2, device_check_command)

    return RecordingPlan(
        valid_count=valid_count,
        expected_count=expected_count,
        remaining_count=remaining_count,
        invalid_counts=dict(invalid_counts),
        commands=commands,
    )


def _shell_double_quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _recording_input_prefix(device_name: str | None, ffmpeg_input: str | None) -> str:
    if ffmpeg_input:
        return f"SWITCHTYPE_FFMPEG_INPUT={_shell_env_value(ffmpeg_input)}"
    device_value = _shell_double_quoted(device_name or "<device name>")
    return f"SWITCHTYPE_FFMPEG_INPUT_NAME={device_value}"


def _shell_env_value(value: str) -> str:
    if re.fullmatch(r"[-A-Za-z0-9_./:=]+", value):
        return value
    return _shell_double_quoted(value)


def format_plan(plan: RecordingPlan) -> str:
    lines = [
        "Recording session status",
        f"Valid recordings: {plan.valid_count}/{plan.expected_count}",
        f"Remaining recordings: {plan.remaining_count}",
    ]
    if plan.invalid_counts:
        lines.append("Invalid or missing samples:")
        for state, count in sorted(plan.invalid_counts.items()):
            lines.append(f"- {state}: {count}")
    else:
        lines.append("Invalid or missing samples: 0")
    lines.append("")
    lines.append("Next commands:")
    for index, command in enumerate(plan.commands, start=1):
        lines.append(f"{index}. {command}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the next recording-session commands for SwitchType.")
    parser.add_argument("--manifest", default=Path("bench/samples/manifest.30-template.jsonl"), type=Path)
    parser.add_argument("--expected-count", default=30, type=int)
    parser.add_argument(
        "--device-name",
        default=os.environ.get("EXPECT_DEVICE_NAME"),
        help="Physical microphone name to use in suggested commands.",
    )
    parser.add_argument(
        "--ffmpeg-input",
        default=os.environ.get("SWITCHTYPE_FFMPEG_INPUT"),
        help='Raw ffmpeg avfoundation microphone input to use in suggested commands, for example ":2".',
    )
    args = parser.parse_args()

    statuses = collect_status(args.manifest)
    print(
        format_plan(
            build_recording_plan(
                statuses,
                expected_count=args.expected_count,
                device_name=args.device_name,
                ffmpeg_input=args.ffmpeg_input,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
