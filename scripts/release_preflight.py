from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.asr_config import resolve_whisper_settings

try:
    from scripts.check_release_ready import (
        benchmark_report_check,
        gif_check,
        readme_benchmark_summary_check,
        strict_audio_check,
        verification_log_check,
    )
except ModuleNotFoundError:
    from check_release_ready import (
        benchmark_report_check,
        gif_check,
        readme_benchmark_summary_check,
        strict_audio_check,
        verification_log_check,
    )

@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


REAL_BENCHMARK_ACTION = " ".join(
    [
        "SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall",
        "SWITCHTYPE_SENSEVOICE_HUB=hf",
        "SWITCHTYPE_SENSEVOICE_VAD_MODEL=none",
        "scripts/run_real_benchmark.sh",
    ]
)
VERIFICATION_LOG_ACTION = "make release-evidence-template, fill actual manual evidence, then run make release-evidence ARGS='...'"
NEXT_ACTION_BY_CHECK = {
    "whisper.cpp binary": "./scripts/bootstrap_whisper_cpp.sh large-v3-turbo",
    "whisper.cpp model": "./scripts/bootstrap_whisper_cpp.sh large-v3-turbo",
    "FunASR dependency": "make bootstrap-funasr",
    "real audio samples": 'make record-session EXPECT_DEVICE_NAME="<device name>", then follow the printed commands',
    "app doctor": (
        'make app-doctor, then grant Microphone and Accessibility permissions; '
        'set SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME="<device name>" if you want microphone matching enforced'
    ),
    "real benchmark report": REAL_BENCHMARK_ACTION,
    "README benchmark summary": REAL_BENCHMARK_ACTION,
    "demo GIF": "./scripts/record_demo.sh",
    "verification log": VERIFICATION_LOG_ACTION,
}


def collect_checks(root: Path = ROOT, environment: dict[str, str] | None = None) -> list[Check]:
    env = environment or os.environ
    return [
        *collect_input_checks(root, environment=env),
        app_doctor_check(root, environment=env),
        benchmark_report(root),
        readme_benchmark_summary(root),
        verification_log(root),
    ]


def collect_input_checks(root: Path = ROOT, environment: dict[str, str] | None = None) -> list[Check]:
    env = environment or os.environ
    return [
        whisper_binary_check(root, environment=env),
        whisper_model_check(root, environment=env),
        funasr_dependency_check(env, root=root),
        real_audio_check(root),
        demo_gif(root),
    ]


def whisper_binary_check(root: Path, environment: dict[str, str] | None = None) -> Check:
    env = os.environ if environment is None else environment
    settings = resolve_whisper_settings(root, env)
    path = Path(settings.whisper_bin)
    return Check("whisper.cpp binary", path.is_file() and _is_executable(path), _detail_for_path(path))


def whisper_model_check(root: Path, environment: dict[str, str] | None = None) -> Check:
    env = os.environ if environment is None else environment
    settings = resolve_whisper_settings(root, env)
    path = Path(settings.whisper_model)
    return Check("whisper.cpp model", path.is_file(), _detail_for_path(path))


def funasr_dependency_check(environment: dict[str, str] | None = None, root: Path = ROOT) -> Check:
    env = os.environ if environment is None else environment
    python = env.get("SWITCHTYPE_FUNASR_PYTHON") or _project_venv_python(root) or sys.executable
    command = [
        python,
        "-c",
        "from funasr import AutoModel",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        return Check("FunASR dependency", False, f"{python}: {error}")
    ok = completed.returncode == 0
    detail = f"{python}: AutoModel importable" if ok else f"{python}: cannot import funasr.AutoModel"
    return Check("FunASR dependency", ok, detail)


def _project_venv_python(root: Path) -> str | None:
    python = root / ".venv/bin/python"
    if python.is_file() and os.access(python, os.X_OK):
        return str(python)
    return None


def real_audio_check(root: Path) -> Check:
    return _with_readiness_root(root, lambda: _copy_check(strict_audio_check("bench/samples/manifest.30-template.jsonl", 30)))


def benchmark_report(root: Path) -> Check:
    return _with_readiness_root(root, lambda: _copy_check(benchmark_report_check("bench/reports/real-asr.md", 30)))


def readme_benchmark_summary(root: Path) -> Check:
    return _with_readiness_root(root, lambda: _copy_check(readme_benchmark_summary_check("README.md", "bench/reports/real-asr.md")))


def demo_gif(root: Path) -> Check:
    return _with_readiness_root(root, lambda: _copy_check(gif_check("docs/assets/switchtype-demo.gif")))


def app_doctor_check(root: Path, environment: dict[str, str] | None = None) -> Check:
    env = os.environ if environment is None else environment
    doctor = root / "app/SwitchType/.build/debug/SwitchTypeDoctor"
    if not doctor.is_file() or not os.access(doctor, os.X_OK):
        return Check("app doctor", False, f"{doctor}: missing or not executable")

    command_env = os.environ.copy()
    command_env.update(env)
    command_env.setdefault("SWITCHTYPE_HOTWORDS_CONFIG", str(root / "bench/config/hotwords.example.json"))
    try:
        completed = subprocess.run(
            [str(doctor), "--json"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=command_env,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Check("app doctor", False, str(error))
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return Check("app doctor", False, detail[-1] if detail else f"exit {completed.returncode}")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return Check("app doctor", False, f"invalid JSON: {error}")

    permissions = report.get("permissions", {})
    asr = report.get("asr", {})
    hotwords = report.get("hotwords", {})
    failures: list[str] = []
    if permissions.get("microphone") != "granted":
        failures.append(f"microphone {permissions.get('microphone', 'unknown')}")
    if permissions.get("accessibility") != "granted":
        failures.append(f"accessibility {permissions.get('accessibility', 'unknown')}")
    expected_status = permissions.get("expected_input_device_status", "not_enforced")
    if expected_status not in ("not_enforced", "matched"):
        failures.append(f"expected input {expected_status}")
    if asr.get("whisper_bin_status") != "ok":
        failures.append(f"whisper bin {asr.get('whisper_bin_status', 'unknown')}")
    if asr.get("whisper_model_status") != "ok":
        failures.append(f"whisper model {asr.get('whisper_model_status', 'unknown')}")
    if hotwords.get("status") not in ("ok", "developer_default"):
        failures.append(f"hotwords {hotwords.get('status', 'unknown')}")

    if failures:
        return Check("app doctor", False, ", ".join(failures))
    return Check(
        "app doctor",
        True,
        f"permissions granted, expected input {expected_status}, hotwords {hotwords.get('status', 'unknown')}",
    )


def verification_log(root: Path) -> Check:
    return _with_readiness_root(root, lambda: _copy_check(verification_log_check("docs/verification-log.md")))


def _with_readiness_root(root: Path, callback):
    try:
        import scripts.check_release_ready as release_ready
    except ModuleNotFoundError:
        import check_release_ready as release_ready

    original_root = release_ready.ROOT
    release_ready.ROOT = root
    try:
        return callback()
    finally:
        release_ready.ROOT = original_root


def _copy_check(check) -> Check:
    return Check(check.name, check.ok, check.detail)


def _detail_for_path(path: Path) -> str:
    if path.exists():
        return str(path)
    return "missing"


def _is_executable(path: Path) -> bool:
    return shutil.which(str(path)) is not None


def print_checks(checks: list[Check]) -> int:
    failures = 0
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
        if not check.ok:
            failures += 1
    return failures


def next_actions(checks: list[Check]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for check in checks:
        if check.ok:
            continue
        action = NEXT_ACTION_BY_CHECK.get(check.name)
        if action is None or action in seen:
            continue
        actions.append(action)
        seen.add(action)
    return actions


def print_next_actions(actions: list[str]) -> None:
    if not actions:
        return
    print()
    print("Suggested next actions:")
    for action in actions:
        print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SwitchType release evidence readiness.")
    parser.add_argument(
        "--inputs-only",
        action="store_true",
        help="Check only prerequisites that must exist before generating benchmark/log evidence.",
    )
    args = parser.parse_args()

    checks = collect_input_checks(ROOT) if args.inputs_only else collect_checks(ROOT)
    failures = print_checks(checks)
    if failures:
        print()
        print("Release evidence is not ready. This preflight is diagnostic only; it does not create audio, benchmark, demo, or manual verification evidence.")
        print_next_actions(next_actions(checks))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
