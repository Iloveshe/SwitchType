from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from doubao_shadow_daemon import status_payload
except ModuleNotFoundError:
    from bench.scripts.doubao_shadow_daemon import status_payload


ROOT_DIR = Path(__file__).resolve().parents[2]


def readiness_error(payload: dict[str, object]) -> str | None:
    segments = payload["segments"]
    benchmark = payload["benchmark"]
    next_command = str(payload["next"])

    captured = int(segments["captured"])
    needs_reconciliation = int(segments["needs_reconciliation"])
    manifest_samples = int(benchmark["manifest_samples"])
    valid_audio = int(benchmark["valid_audio"])

    if captured == 0:
        return (
            "No Doubao shadow audio has been captured yet. "
            "Start the opt-in background recorder with: make doubao-shadow-start-auto"
        )
    if manifest_samples == 0:
        return (
            "Doubao shadow samples are not benchmark-ready yet. "
            "Pair audio with Doubao's inserted text using: make doubao-shadow-reconcile"
        )
    if valid_audio == 0:
        return (
            "No valid Doubao shadow audio is ready for benchmark. "
            "Record more usable clips with: make doubao-shadow-start-auto"
        )
    return None


def benchmark_environment(
    *,
    base_env: dict[str, str],
    manifest: Path,
    preview_manifest: Path,
    report: Path,
) -> dict[str, str]:
    env = dict(base_env)
    env["SWITCHTYPE_REAL_SOURCE_MANIFEST"] = str(manifest)
    env["SWITCHTYPE_REAL_PREVIEW_MANIFEST"] = str(preview_manifest)
    env["SWITCHTYPE_REAL_PREVIEW_REPORT"] = str(report)
    env.setdefault("SWITCHTYPE_ENABLE_SENSEVOICE", "0")
    return env


def run_shadow_benchmark(
    *,
    pid_file: Path,
    segments: Path,
    manifest: Path,
    preview_manifest: Path,
    report: Path,
    min_duration: float,
) -> int:
    payload = status_payload(
        pid_file=pid_file,
        segments=segments,
        manifest=manifest,
        min_duration=min_duration,
    )
    error = readiness_error(payload)
    if error:
        print(error, file=sys.stderr)
        print("Run make doubao-shadow-status for detailed counts.", file=sys.stderr)
        return 1

    env = benchmark_environment(
        base_env=os.environ,
        manifest=manifest,
        preview_manifest=preview_manifest,
        report=report,
    )
    completed = subprocess.run(
        [str(ROOT_DIR / "scripts/run_recorded_benchmark_preview.sh")],
        cwd=ROOT_DIR,
        env=env,
        check=False,
    )
    return completed.returncode


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Doubao shadow benchmark only when captured samples are ready.")
    parser.add_argument("--pid-file", default=Path("bench/samples/doubao-shadow/shadow.pid"), type=Path)
    parser.add_argument("--segments", default=Path("bench/samples/doubao-shadow/segments.jsonl"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/doubao-shadow/manifest.jsonl"), type=Path)
    parser.add_argument("--preview-manifest", default=Path("bench/samples/doubao-shadow/manifest.valid.jsonl"), type=Path)
    parser.add_argument("--report", default=Path("bench/reports/doubao-shadow-preview.md"), type=Path)
    parser.add_argument("--min-duration", default=0.25, type=float)
    return parser


def main() -> int:
    args = parser().parse_args()
    return run_shadow_benchmark(
        pid_file=args.pid_file,
        segments=args.segments,
        manifest=args.manifest,
        preview_manifest=args.preview_manifest,
        report=args.report,
        min_duration=args.min_duration,
    )


if __name__ == "__main__":
    raise SystemExit(main())
