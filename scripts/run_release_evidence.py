from __future__ import annotations

import argparse
import subprocess
from typing import Any


MANUAL_FIELD_FLAGS = [
    ("app_date", "--app-date"),
    ("launch_method", "--launch-method"),
    ("microphone_permission", "--microphone-permission"),
    ("accessibility_permission", "--accessibility-permission"),
    ("hotword_config_path", "--hotword-config-path"),
    ("input_app", "--input-app"),
    ("spoken_sentence", "--spoken-sentence"),
    ("pasted_output", "--pasted-output"),
    ("hotwords_preserved", "--hotwords-preserved"),
    ("short_recording_rejected", "--short-recording-rejected"),
    ("hotkey_consumed", "--hotkey-consumed"),
    ("recording_tool", "--recording-tool"),
    ("gif_duration", "--gif-duration"),
    ("real_asr_demo", "--real-asr-demo"),
]
REQUIRED_MANUAL_FIELD_KEYS = [key for key, _ in MANUAL_FIELD_FLAGS]
FINAL_RESULT_ARGUMENTS = ["--final-result", "strict readiness passed"]
DEFAULT_RELEASE_SENTENCE = "帮我看一下 Codex 的 PR issue 有没有过 CI"

REAL_BENCHMARK_ENV_FLAGS = [
    ("asr_config", "SWITCHTYPE_ASR_CONFIG"),
    ("hotwords_config", "SWITCHTYPE_HOTWORDS_CONFIG"),
    ("whisper_bin", "SWITCHTYPE_WHISPER_BIN"),
    ("whisper_model", "SWITCHTYPE_WHISPER_MODEL"),
    ("funasr_python", "SWITCHTYPE_FUNASR_PYTHON"),
    ("sensevoice_model", "SWITCHTYPE_SENSEVOICE_MODEL"),
    ("sensevoice_hub", "SWITCHTYPE_SENSEVOICE_HUB"),
    ("sensevoice_vad_model", "SWITCHTYPE_SENSEVOICE_VAD_MODEL"),
]


def missing_manual_field_flags(values: dict[str, str]) -> list[str]:
    return [flag for key, flag in MANUAL_FIELD_FLAGS if key in REQUIRED_MANUAL_FIELD_KEYS and not values.get(key, "")]


def update_log_args(values: dict[str, str], require_complete: bool = True) -> list[str]:
    missing = missing_manual_field_flags(values)
    if require_complete and missing:
        raise ValueError("Missing required manual evidence field(s): " + ", ".join(missing))
    args: list[str] = []
    for key, flag in MANUAL_FIELD_FLAGS:
        value = values.get(key, "")
        if value:
            args.extend([flag, value])
    return args


def environment_command(environment: dict[str, str], command: list[str]) -> list[str]:
    env_args = [f"{key}={value}" for key, value in environment.items() if value]
    if not env_args:
        return command
    return ["env", *env_args, *command]


def real_benchmark_command(environment: dict[str, str]) -> list[str]:
    return environment_command(environment, ["make", "real-benchmark"])


def real_benchmark_environment(values: Any) -> dict[str, str]:
    environment: dict[str, str] = {}
    if getattr(values, "whisper_no_gpu", False):
        environment["SWITCHTYPE_WHISPER_NO_GPU"] = "1"
    if getattr(values, "enable_sensevoice", False):
        environment["SWITCHTYPE_ENABLE_SENSEVOICE"] = "1"
    for key, env_name in REAL_BENCHMARK_ENV_FLAGS:
        value = getattr(values, key, "")
        if value:
            environment[env_name] = value
    return environment


def command_plan(
    include_smoke: bool,
    update_log_arguments: list[str],
    real_benchmark_environment: dict[str, str] | None = None,
) -> list[list[str]]:
    asr_environment = real_benchmark_environment or {}
    benchmark_command = real_benchmark_command(asr_environment)
    plan = [
        environment_command(asr_environment, ["make", "release-inputs-preflight"]),
        ["make", "sample-status"],
        [
            "python3",
            "bench/scripts/validate_samples.py",
            "--manifest",
            "bench/samples/manifest.30-template.jsonl",
            "--expected-count",
            "30",
            "--require-audio",
        ],
    ]
    if include_smoke:
        plan.extend(
            [
                environment_command(asr_environment, ["make", "asr-smoke"]),
                environment_command(asr_environment, ["make", "app-asr-smoke"]),
            ]
        )
    plan.extend(
        [
            benchmark_command,
            ["make", "package"],
            [
                "python3",
                "scripts/update_verification_log.py",
                "--benchmark-command",
                shell_quote(benchmark_command),
                *update_log_arguments,
            ],
            ["python3", "scripts/check_release_ready.py", "--strict", "--ignore-final-result"],
            [
                "python3",
                "scripts/update_verification_log.py",
                "--benchmark-command",
                shell_quote(benchmark_command),
                *update_log_arguments,
                *FINAL_RESULT_ARGUMENTS,
            ],
            ["make", "release-preflight"],
            ["python3", "scripts/check_release_ready.py", "--strict"],
        ]
    )
    return plan


def shell_quote(command: list[str]) -> str:
    return " ".join(_quote_part(part) for part in command)


def _quote_part(part: str) -> str:
    if not part or any(character.isspace() for character in part):
        return "'" + part.replace("'", "'\"'\"'") + "'"
    return part


def run_plan(plan: list[list[str]], dry_run: bool) -> None:
    for command in plan:
        print(shell_quote(command))
        if not dry_run:
            subprocess.run(command, check=True)


def build_release_evidence_template(app_date: str = "") -> str:
    date_value = app_date or "YYYY-MM-DD"
    args = [
        "--dry-run",
        "--asr-config ~/.switchtype/asr.json",
        "--hotwords-config ~/.switchtype/hotwords.json",
        "--funasr-python .venv/bin/python",
        "--sensevoice-model FunAudioLLM/SenseVoiceSmall",
        "--sensevoice-hub hf",
        "--sensevoice-vad-model none",
        f"--app-date {date_value}",
        "--launch-method dist/SwitchType.app",
        "--microphone-permission granted",
        "--accessibility-permission granted",
        "--hotword-config-path ~/.switchtype/hotwords.json",
        "--input-app TextEdit",
        f'--spoken-sentence "{DEFAULT_RELEASE_SENTENCE}"',
        '--pasted-output "PASTE_REAL_OUTPUT_HERE"',
        "--hotwords-preserved yes",
        "--short-recording-rejected yes",
        "--hotkey-consumed yes",
        '--recording-tool "Kap or QuickTime"',
        '--gif-duration "8-15s"',
        "--real-asr-demo yes",
    ]
    command_lines = ["make release-evidence ARGS='" + args[0] + " \\"]
    for index, arg in enumerate(args[1:], start=1):
        suffix = "'" if index == len(args) - 1 else " \\"
        command_lines.append(f"  {arg}{suffix}")
    command_lines.extend(
        [
            "",
            "After the dry run looks right, remove `--dry-run` and replace `PASTE_REAL_OUTPUT_HERE` with the actual pasted output.",
        ]
    )
    return "\n".join(command_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SwitchType final release evidence workflow.")
    parser.add_argument("--template", action="store_true", help="Print an editable release-evidence command template and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip ASR smoke checks.")
    parser.add_argument("--asr-config", default="", help="Path to ASR config JSON for preflight, smoke checks, and benchmark.")
    parser.add_argument("--hotwords-config", default="", help="Path to hotwords JSON for the real benchmark.")
    parser.add_argument("--whisper-bin", default="", help="Path to whisper.cpp whisper-cli for preflight and benchmark.")
    parser.add_argument("--whisper-model", default="", help="Path to ggml whisper.cpp model for preflight and benchmark.")
    parser.add_argument("--whisper-no-gpu", action="store_true", help="Pass SWITCHTYPE_WHISPER_NO_GPU=1 to the benchmark.")
    parser.add_argument("--enable-sensevoice", action="store_true", help="Enable SenseVoice for the real benchmark step.")
    parser.add_argument("--funasr-python", default="", help="Python executable that can import FunASR.")
    parser.add_argument("--sensevoice-model", default="", help="SenseVoice model id or local path for the real benchmark.")
    parser.add_argument("--sensevoice-hub", default="", choices=["", "ms", "modelscope", "hf", "huggingface"])
    parser.add_argument("--sensevoice-vad-model", default="", help="Set to none/off/disabled to skip FunASR VAD.")
    parser.add_argument("--app-date", default="")
    parser.add_argument("--launch-method", default="")
    parser.add_argument("--microphone-permission", default="")
    parser.add_argument("--accessibility-permission", default="")
    parser.add_argument("--hotword-config-path", default="")
    parser.add_argument("--input-app", default="")
    parser.add_argument("--spoken-sentence", default="")
    parser.add_argument("--pasted-output", default="")
    parser.add_argument("--hotwords-preserved", default="")
    parser.add_argument("--short-recording-rejected", default="")
    parser.add_argument("--hotkey-consumed", default="")
    parser.add_argument("--recording-tool", default="")
    parser.add_argument("--gif-duration", default="")
    parser.add_argument("--real-asr-demo", default="")
    parser.add_argument("--final-result", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.template:
        print(build_release_evidence_template(app_date=args.app_date))
        return 0

    manual_values = {key: getattr(args, key) for key, _ in MANUAL_FIELD_FLAGS}
    try:
        update_log_arguments = update_log_args(manual_values, require_complete=not args.dry_run)
    except ValueError as error:
        print(error)
        print("Use --dry-run to print the command plan before collecting manual evidence.")
        return 2
    run_plan(
        command_plan(
            include_smoke=not args.skip_smoke,
            update_log_arguments=update_log_arguments,
            real_benchmark_environment=real_benchmark_environment(args),
        ),
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
