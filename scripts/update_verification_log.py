from __future__ import annotations

import argparse
import platform
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.check_release_ready import _engine_summary_rows
except ModuleNotFoundError:
    from check_release_ready import _engine_summary_rows

from bench.scripts.audio_checks import is_expected_wav_format, read_wav_info


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def audio_sample_status(manifest: Path, root: Path) -> str:
    if not manifest.exists():
        return ""
    total = 0
    valid = 0
    missing = 0
    invalid = 0
    wrong_format = 0
    silent = 0
    too_short = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        audio = root / json.loads(line)["audio"]
        if not audio.exists():
            missing += 1
            continue
        if audio.stat().st_size <= 0:
            invalid += 1
            continue
        if audio.suffix.lower() == ".wav":
            info = read_wav_info(audio)
            if info is None:
                invalid += 1
                continue
            if not is_expected_wav_format(info):
                wrong_format += 1
                continue
            if not info.has_signal:
                silent += 1
                continue
            if info.duration_seconds < 0.25:
                too_short += 1
                continue
        valid += 1
    details = []
    if missing:
        details.append(f"{missing} missing")
    if invalid:
        details.append(f"{invalid} invalid")
    if wrong_format:
        details.append(f"{wrong_format} wrong format")
    if silent:
        details.append(f"{silent} silent")
    if too_short:
        details.append(f"{too_short} too short")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{valid}/{total} valid{suffix}"


def benchmark_fields(report: Path, root: Path) -> tuple[str, str, str]:
    if not report.exists():
        return "", "", ""
    rows = _engine_summary_rows(report.read_text(encoding="utf-8"))
    if not rows:
        return "", relative(report, root), ""
    engines = ", ".join(row["engine"] for row in rows)
    summary = "; ".join(
        (
            f"{row['engine']}: {row['samples']} samples, "
            f"avg CER {row['avg_cer']}, avg WER {row['avg_wer']}, "
            f"term accuracy {row['term_accuracy']}"
        )
        for row in rows
    )
    return engines, relative(report, root), summary


def existing_path(path: Path, root: Path) -> str:
    return relative(path, root) if path.exists() else ""


def field(manual_fields: dict[str, str], key: str) -> str:
    return manual_fields.get(key, "")


def build_log(
    root: Path,
    date: str,
    manifest: Path,
    benchmark_report: Path,
    app_build: Path,
    gif_path: Path,
    benchmark_command: str,
    manual_fields: dict[str, str],
) -> str:
    engines, report_path, summary = benchmark_fields(benchmark_report, root)
    return f"""# SwitchType Verification Log

Fill this in with real local evidence before marking the v0.1 goal complete.

## Benchmark Run

- Date: {date}
- Machine: {platform.platform()}
- Manifest: {existing_path(manifest, root)}
- Audio sample count: {audio_sample_status(manifest, root)}
- ASR engines: {engines}
- Report path: {report_path}
- Command:

```bash
{benchmark_command}
```

- Result summary: {summary}

## App Manual Verification

- Date: {field(manual_fields, "app_date")}
- App build: {existing_path(app_build, root)}
- Launch method: {field(manual_fields, "launch_method")}
- Microphone permission: {field(manual_fields, "microphone_permission")}
- Accessibility permission: {field(manual_fields, "accessibility_permission")}
- Hotword config path: {field(manual_fields, "hotword_config_path")}
- Input app: {field(manual_fields, "input_app")}
- Spoken sentence: {field(manual_fields, "spoken_sentence")}
- Pasted output: {field(manual_fields, "pasted_output")}
- Hotwords preserved: {field(manual_fields, "hotwords_preserved")}
- Short recording rejected: {field(manual_fields, "short_recording_rejected")}
- Hotkey consumed: {field(manual_fields, "hotkey_consumed")}

## Demo Asset

- GIF path: {existing_path(gif_path, root)}
- Recording command/tool: {field(manual_fields, "recording_tool")}
- Duration: {field(manual_fields, "gif_duration")}
- Shows real ASR rather than debug transcript mode: {field(manual_fields, "real_asr_demo")}

## Final Readiness

```bash
python3 scripts/check_release_ready.py --strict
```

- Result: {field(manual_fields, "final_result")}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Update docs/verification-log.md from current SwitchType evidence.")
    parser.add_argument("--output", default=Path("docs/verification-log.md"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/manifest.30-template.jsonl"), type=Path)
    parser.add_argument("--benchmark-report", default=Path("bench/reports/real-asr.md"), type=Path)
    parser.add_argument("--benchmark-command", default="scripts/run_real_benchmark.sh")
    parser.add_argument("--app-build", default=Path("dist/SwitchType-0.1.0.zip"), type=Path)
    parser.add_argument("--gif-path", default=Path("docs/assets/switchtype-demo.gif"), type=Path)
    parser.add_argument("--date", default=date.today().isoformat())
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
    parser.add_argument("--final-result", default="")
    args = parser.parse_args()

    root = Path.cwd()
    manual_fields = {
        "app_date": args.app_date,
        "launch_method": args.launch_method,
        "microphone_permission": args.microphone_permission,
        "accessibility_permission": args.accessibility_permission,
        "hotword_config_path": args.hotword_config_path,
        "input_app": args.input_app,
        "spoken_sentence": args.spoken_sentence,
        "pasted_output": args.pasted_output,
        "hotwords_preserved": args.hotwords_preserved,
        "short_recording_rejected": args.short_recording_rejected,
        "hotkey_consumed": args.hotkey_consumed,
        "recording_tool": args.recording_tool,
        "gif_duration": args.gif_duration,
        "real_asr_demo": args.real_asr_demo,
        "final_result": args.final_result,
    }
    log = build_log(
        root=root,
        date=args.date,
        manifest=root / args.manifest,
        benchmark_report=root / args.benchmark_report,
        app_build=root / args.app_build,
        gif_path=root / args.gif_path,
        benchmark_command=args.benchmark_command,
        manual_fields=manual_fields,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(log, encoding="utf-8")
    print(f"Updated {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
