from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.scripts.audio_checks import is_expected_wav_format, read_wav_info


MIN_DEMO_GIF_BYTES = 10_000
MIN_DEMO_GIF_WIDTH = 640
MIN_DEMO_GIF_HEIGHT = 360


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def exists(path: str) -> Check:
    target = ROOT / path
    return Check(path, target.exists(), "present" if target.exists() else "missing")


def command_ok(name: str, command: list[str], env: dict[str, str] | None = None) -> Check:
    command_env = os.environ.copy()
    command_env.setdefault("PYTHONPATH", "bench")
    command_env.setdefault("CLANG_MODULE_CACHE_PATH", str(ROOT / "app/SwitchType/.build/clang-module-cache"))
    if env:
        command_env.update(env)
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, env=command_env)
    output = (completed.stdout + completed.stderr).strip().splitlines()
    detail = output[-1] if output else f"exit {completed.returncode}"
    return Check(name, completed.returncode == 0, detail)


def count_manifest_samples(path: str, expected: int) -> Check:
    target = ROOT / path
    if not target.exists():
        return Check(path, False, "manifest missing")
    count = sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())
    return Check(path, count == expected, f"{count}/{expected} samples")


def strict_audio_check(path: str, expected: int) -> Check:
    target = ROOT / path
    if not target.exists():
        return Check("real audio samples", False, "manifest missing")
    sample_count = 0
    missing: list[str] = []
    invalid: list[str] = []
    wrong_format: list[str] = []
    silent: list[str] = []
    too_short: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sample_count += 1
        audio = ROOT / json.loads(line)["audio"]
        if not audio.exists():
            missing.append(str(audio.relative_to(ROOT)))
            continue
        if audio.stat().st_size <= 0:
            invalid.append(str(audio.relative_to(ROOT)))
            continue
        if audio.suffix.lower() == ".wav":
            info = read_wav_info(audio)
            if info is None:
                invalid.append(str(audio.relative_to(ROOT)))
            elif not is_expected_wav_format(info):
                wrong_format.append(str(audio.relative_to(ROOT)))
            elif not info.has_signal:
                silent.append(str(audio.relative_to(ROOT)))
            elif info.duration_seconds < 0.25:
                too_short.append(str(audio.relative_to(ROOT)))

    details: list[str] = []
    if sample_count != expected:
        details.append(f"sample count {sample_count}/{expected}")
    if missing:
        details.append(f"{len(missing)} missing")
    if invalid:
        details.append(f"{len(invalid)} invalid")
    if wrong_format:
        details.append(f"{len(wrong_format)} wrong format")
    if silent:
        details.append(f"{len(silent)} silent")
    if too_short:
        details.append(f"{len(too_short)} too short")
    ok = sample_count == expected and not missing and not invalid and not wrong_format and not silent and not too_short and expected > 0
    return Check("real audio samples", ok, "all valid" if ok else "; ".join(details))


def benchmark_report_check(
    path: str,
    expected_samples: int,
    manifest_path: str = "bench/samples/manifest.30-template.jsonl",
    minimum_non_fake_engines: int = 2,
) -> Check:
    target = ROOT / path
    if not target.exists():
        return Check("real benchmark report", False, "missing")

    text = target.read_text(encoding="utf-8")
    engines = _engine_summary_rows(text)
    if not engines:
        return Check("real benchmark report", False, "no engine summary rows")

    non_fake = [row for row in engines if row["engine"].lower() != "fake"]
    if not non_fake:
        return Check("real benchmark report", False, "only fake engine rows")
    if len(non_fake) < minimum_non_fake_engines:
        return Check(
            "real benchmark report",
            False,
            f"at least {minimum_non_fake_engines} non-fake engines required",
        )

    try:
        sample_counts_by_engine = {row["engine"]: int(row["samples"]) for row in non_fake}
    except ValueError:
        return Check("real benchmark report", False, "malformed non-fake engine sample count")
    short_engines = [engine for engine, count in sample_counts_by_engine.items() if count < expected_samples]
    if short_engines:
        return Check(
            "real benchmark report",
            False,
            f"non-fake engine sample count below {expected_samples}: {', '.join(short_engines)}",
        )

    sample_rows = _sample_result_rows(text)
    for row in sample_rows:
        if row["engine"].lower() == "fake":
            continue
        if not row["processed_transcript"].strip():
            return Check("real benchmark report", False, f"empty transcript for {row['engine']} {row['sample']}")
        if not _valid_sample_metrics(row):
            return Check("real benchmark report", False, f"malformed sample metrics for {row['engine']} {row['sample']}")

    duplicate = _duplicate_sample_row(sample_rows)
    if duplicate:
        engine, sample = duplicate
        return Check("real benchmark report", False, f"duplicate sample row for {engine} {sample}")

    non_fake_sample_ids = {row["sample"] for row in sample_rows if row["engine"].lower() != "fake"}
    if len(non_fake_sample_ids) < expected_samples:
        return Check("real benchmark report", False, f"non-fake sample rows {len(non_fake_sample_ids)}/{expected_samples}")

    manifest_ids = _manifest_sample_ids(ROOT / manifest_path)
    if manifest_ids:
        expected_ids = set(manifest_ids)
        non_fake_engines = {row["engine"] for row in non_fake}
        rows_by_engine: dict[str, set[str]] = {engine: set() for engine in non_fake_engines}
        for row in sample_rows:
            if row["engine"] in rows_by_engine:
                rows_by_engine[row["engine"]].add(row["sample"])

        for engine, sample_ids in sorted(rows_by_engine.items()):
            missing = expected_ids - sample_ids
            if missing:
                return Check("real benchmark report", False, f"missing manifest sample ids for {engine}: {len(missing)}")
            unknown = sample_ids - expected_ids
            if unknown:
                return Check("real benchmark report", False, f"unknown sample ids for {engine}: {len(unknown)}")

    summary_consistency = _summary_consistency_error(non_fake, sample_rows)
    if summary_consistency:
        return Check("real benchmark report", False, summary_consistency)

    metadata_error = _run_metadata_error(text, manifest_path=manifest_path, report_path=path)
    if metadata_error:
        return Check("real benchmark report", False, metadata_error)

    return Check("real benchmark report", True, f"{len(non_fake)} non-fake engine(s), {len(non_fake_sample_ids)} sample(s)")


def readme_benchmark_summary_check(readme_path: str, report_path: str) -> Check:
    readme = ROOT / readme_path
    report = ROOT / report_path
    if not readme.exists():
        return Check("README benchmark summary", False, "README missing")
    if not report.exists():
        return Check("README benchmark summary", False, "real benchmark report missing")

    try:
        expected_summary = _benchmark_summary_section(report.read_text(encoding="utf-8"))
        actual_summary = _readme_benchmark_summary(readme.read_text(encoding="utf-8"))
    except ValueError as error:
        return Check("README benchmark summary", False, str(error))

    if actual_summary != expected_summary:
        return Check("README benchmark summary", False, "not updated from real benchmark report")
    return Check("README benchmark summary", True, "matches real benchmark report")


def _benchmark_summary_section(report: str) -> str:
    start_marker = "## Engine Summary"
    end_marker = "## Sample Results"
    start = report.find(start_marker)
    if start == -1:
        raise ValueError("report does not contain Engine Summary")
    end = report.find(end_marker, start + len(start_marker))
    if end == -1:
        raise ValueError("report does not contain Sample Results")
    return report[start:end].strip()


def _readme_benchmark_summary(readme: str) -> str:
    start_marker = "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->"
    end_marker = "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->"
    start = readme.find(start_marker)
    end = readme.find(end_marker)
    if start == -1 or end == -1 or end < start:
        raise ValueError("README benchmark summary markers missing")
    return readme[start + len(start_marker) : end].strip()


def _manifest_sample_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    sample_ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sample_ids.append(json.loads(line)["id"])
    return sample_ids


def verification_log_check(path: str, require_final_result: bool = True) -> Check:
    target = ROOT / path
    if not target.exists():
        return Check("verification log", False, "missing")

    fields = parse_verification_log(target.read_text(encoding="utf-8"))
    required = [
        "Benchmark Run/Date",
        "Benchmark Run/Machine",
        "Benchmark Run/Manifest",
        "Benchmark Run/Audio sample count",
        "Benchmark Run/ASR engines",
        "Benchmark Run/Report path",
        "Benchmark Run/Command",
        "Benchmark Run/Result summary",
        "App Manual Verification/Date",
        "App Manual Verification/App build",
        "App Manual Verification/Launch method",
        "App Manual Verification/Microphone permission",
        "App Manual Verification/Accessibility permission",
        "App Manual Verification/Hotword config path",
        "App Manual Verification/Input app",
        "App Manual Verification/Spoken sentence",
        "App Manual Verification/Pasted output",
        "App Manual Verification/Hotwords preserved",
        "App Manual Verification/Short recording rejected",
        "App Manual Verification/Hotkey consumed",
        "Demo Asset/GIF path",
        "Demo Asset/Duration",
        "Demo Asset/Shows real ASR rather than debug transcript mode",
    ]
    if require_final_result:
        required.append("Final Readiness/Result")
    missing = [field for field in required if not fields.get(field)]
    if missing:
        return Check("verification log", False, f"{len(missing)} required field(s) empty: {', '.join(missing)}")

    audio_sample_count = fields["Benchmark Run/Audio sample count"].lower()
    if "30/30" not in audio_sample_count or "valid" not in audio_sample_count:
        return Check("verification log", False, "Audio sample count is not 30/30 valid")

    asr_engines = [
        engine.strip()
        for engine in fields["Benchmark Run/ASR engines"].split(",")
        if engine.strip()
    ]
    non_fake_engines = [engine for engine in asr_engines if engine.lower() != "fake"]
    if len(non_fake_engines) < 2:
        return Check("verification log", False, "ASR engines must include at least two non-fake engines")

    if fields["Benchmark Run/Report path"] != "bench/reports/real-asr.md":
        return Check("verification log", False, "Report path must be bench/reports/real-asr.md")
    benchmark_command = fields["Benchmark Run/Command"]
    if "real-benchmark" not in benchmark_command and "run_real_benchmark.sh" not in benchmark_command:
        return Check("verification log", False, "Command is not a real benchmark command")

    if fields["App Manual Verification/App build"] != "dist/SwitchType-0.1.0.zip":
        return Check("verification log", False, "App build must be dist/SwitchType-0.1.0.zip")
    if not (ROOT / "dist/SwitchType-0.1.0.zip").exists():
        return Check("verification log", False, "App build file is missing")

    if fields["App Manual Verification/Launch method"] != "dist/SwitchType.app":
        return Check("verification log", False, "Launch method must be dist/SwitchType.app")

    hotword_config = _root_relative_path(fields["App Manual Verification/Hotword config path"])
    if not hotword_config.exists():
        return Check("verification log", False, "Hotword config path does not exist")
    protected_terms = _protected_terms_from_config(hotword_config)
    if protected_terms is None:
        return Check("verification log", False, "Hotword config is not readable")
    spoken_sentence = fields["App Manual Verification/Spoken sentence"]
    pasted_output = fields["App Manual Verification/Pasted output"]
    expected_terms = [term for term in protected_terms if term and term in spoken_sentence]
    missing_terms = [term for term in expected_terms if term not in pasted_output]
    if missing_terms:
        return Check("verification log", False, f"Pasted output missing protected term(s): {', '.join(missing_terms)}")

    real_asr = fields["Demo Asset/Shows real ASR rather than debug transcript mode"].lower()
    if real_asr not in {"yes", "true", "y"}:
        return Check("verification log", False, "demo is not marked as real ASR")

    if fields["App Manual Verification/Microphone permission"].lower() != "granted":
        return Check("verification log", False, "Microphone permission is not granted")
    if fields["App Manual Verification/Accessibility permission"].lower() != "granted":
        return Check("verification log", False, "Accessibility permission is not granted")

    hotwords_preserved = fields["App Manual Verification/Hotwords preserved"].lower()
    if hotwords_preserved not in {"yes", "true", "y"}:
        return Check("verification log", False, "Hotwords preserved is not yes")

    short_recording_rejected = fields["App Manual Verification/Short recording rejected"].lower()
    if short_recording_rejected not in {"yes", "true", "y"}:
        return Check("verification log", False, "Short recording rejected is not yes")

    hotkey_consumed = fields["App Manual Verification/Hotkey consumed"].lower()
    if hotkey_consumed not in {"yes", "true", "y"}:
        return Check("verification log", False, "Hotkey consumed is not yes")

    if require_final_result:
        final_result = fields["Final Readiness/Result"].lower()
        if final_result not in {"strict readiness passed", "passed"}:
            return Check("verification log", False, "Final readiness result is not passed")

    return Check("verification log", True, "required fields filled")


def _root_relative_path(path: str) -> Path:
    target = Path(path).expanduser()
    return target if target.is_absolute() else ROOT / target


def _protected_terms_from_config(path: Path) -> list[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    terms = data.get("protected_terms", [])
    if not isinstance(terms, list):
        return None
    return [str(term) for term in terms]


def gif_check(path: str) -> Check:
    target = ROOT / path
    if not target.exists():
        return Check("demo GIF", False, "missing")
    size = target.stat().st_size
    if size <= 0:
        return Check("demo GIF", False, "empty file")
    header = target.read_bytes()[:10]
    signature = header[:6]
    if signature not in {b"GIF87a", b"GIF89a"}:
        return Check("demo GIF", False, "not a GIF file")
    if size < MIN_DEMO_GIF_BYTES:
        return Check("demo GIF", False, f"too small ({size} bytes, expected >= {MIN_DEMO_GIF_BYTES})")
    dimensions = _gif_dimensions(header)
    if dimensions is None:
        return Check("demo GIF", False, "missing GIF dimensions")
    width, height = dimensions
    if width < MIN_DEMO_GIF_WIDTH or height < MIN_DEMO_GIF_HEIGHT:
        return Check(
            "demo GIF",
            False,
            f"dimensions {width}x{height} below {MIN_DEMO_GIF_WIDTH}x{MIN_DEMO_GIF_HEIGHT}",
        )
    return Check("demo GIF", True, f"{size} bytes, {width}x{height}")


def _gif_dimensions(header: bytes) -> tuple[int, int] | None:
    if len(header) < 10:
        return None
    return int.from_bytes(header[6:8], "little"), int.from_bytes(header[8:10], "little")


def _engine_summary_rows(report: str) -> list[dict[str, str]]:
    rows = _markdown_table_rows(report, "## Engine Summary", "## Sample Results")
    return [
        {
            "engine": row[0],
            "samples": row[1],
            "avg_latency_ms": row[2],
            "avg_cer": row[3],
            "avg_wer": row[4],
            "term_accuracy": row[5],
        }
        for row in rows
        if len(row) >= 6
    ]


def _sample_result_rows(report: str) -> list[dict[str, str]]:
    rows = _markdown_table_rows(report, "## Sample Results", None)
    return [
        {
            "sample": row[0],
            "engine": row[1],
            "latency_ms": row[2] if len(row) > 2 else "",
            "cer": row[3] if len(row) > 3 else "",
            "wer": row[4] if len(row) > 4 else "",
            "term_accuracy": row[5] if len(row) > 5 else "",
            "processed_transcript": row[6] if len(row) > 6 else "",
        }
        for row in rows
        if len(row) >= 2
    ]


def _run_metadata_error(report: str, manifest_path: str, report_path: str) -> str | None:
    fields = _run_metadata_fields(report)
    required = ["Generated at", "Config", "Hotwords", "Manifest", "Report"]
    missing = [field for field in required if not fields.get(field)]
    if missing:
        return f"run metadata missing: {', '.join(missing)}"
    if not _metadata_path_matches(fields["Manifest"], manifest_path):
        return "run metadata manifest path does not match checked manifest"
    if not _metadata_path_matches(fields["Report"], report_path):
        return "run metadata report path does not match checked report"
    return None


def _run_metadata_fields(report: str) -> dict[str, str]:
    start_marker = "## Run Metadata"
    end_marker = "## Engine Summary"
    start = report.find(start_marker)
    if start == -1:
        return {}
    end = report.find(end_marker, start + len(start_marker))
    if end == -1:
        end = len(report)
    fields: dict[str, str] = {}
    for line in report[start:end].splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped.removeprefix("- ").split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _metadata_path_matches(value: str, expected_path: str) -> bool:
    path = Path(value).expanduser()
    expected = ROOT / expected_path
    if path.is_absolute():
        return path == expected
    return path == Path(expected_path) or ROOT / path == expected


def _valid_sample_metrics(row: dict[str, str]) -> bool:
    latency = _parse_float(row["latency_ms"])
    cer = _parse_float(row["cer"])
    wer = _parse_float(row["wer"])
    term_accuracy = _parse_float(row["term_accuracy"])
    if latency is None or cer is None or wer is None or term_accuracy is None:
        return False
    return latency > 0 and cer >= 0 and wer >= 0 and 0 <= term_accuracy <= 1


def _duplicate_sample_row(sample_rows: list[dict[str, str]]) -> tuple[str, str] | None:
    seen: set[tuple[str, str]] = set()
    for row in sample_rows:
        if row["engine"].lower() == "fake":
            continue
        key = (row["engine"], row["sample"])
        if key in seen:
            return key
        seen.add(key)
    return None


def _summary_consistency_error(summary_rows: list[dict[str, str]], sample_rows: list[dict[str, str]]) -> str | None:
    rows_by_engine: dict[str, list[dict[str, str]]] = {}
    for row in sample_rows:
        if row["engine"].lower() != "fake":
            rows_by_engine.setdefault(row["engine"], []).append(row)

    for summary in summary_rows:
        engine = summary["engine"]
        engine_rows = rows_by_engine.get(engine, [])
        summary_count = _parse_int(summary["samples"])
        if summary_count is None:
            return f"malformed summary sample count for {engine}"
        if summary_count != len(engine_rows):
            return f"summary sample count mismatch for {engine}: {summary_count} != {len(engine_rows)}"
        for summary_key, row_key, precision in [
            ("avg_latency_ms", "latency_ms", 1),
            ("avg_cer", "cer", 3),
            ("avg_wer", "wer", 3),
        ]:
            summary_value = _parse_float(summary[summary_key])
            row_values = [_parse_float(row[row_key]) for row in engine_rows]
            if summary_value is None or any(value is None for value in row_values):
                return f"malformed summary average for {engine}"
            average = sum(value for value in row_values if value is not None) / len(row_values)
            if not _matches_reported_average(summary_value, average, precision):
                return f"summary average mismatch for {engine} {summary_key}"
        term_accuracy = _parse_float(summary["term_accuracy"])
        if term_accuracy is None or not 0 <= term_accuracy <= 1:
            return f"malformed summary term accuracy for {engine}"
    return None


def _matches_reported_average(summary_value: float, row_average: float, precision: int) -> bool:
    tolerance = 10 ** -precision
    return abs(round(summary_value, precision) - round(row_average, precision)) <= tolerance + 1e-12


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _markdown_table_rows(text: str, start_marker: str, end_marker: str | None) -> list[list[str]]:
    start = text.find(start_marker)
    if start == -1:
        return []
    end = text.find(end_marker, start + len(start_marker)) if end_marker else len(text)
    if end == -1:
        end = len(text)
    section = text[start:end]
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0].lower() not in {"engine", "sample"}:
            rows.append(cells)
    return rows


def parse_verification_log(text: str) -> dict[str, str]:
    current_section = ""
    fields: dict[str, str] = {}
    in_code_block = False
    pending_code_field = ""
    code_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            if in_code_block and pending_code_field:
                fields[pending_code_field] = "\n".join(code_lines).strip()
                pending_code_field = ""
                code_lines = []
            in_code_block = not in_code_block
            continue
        if in_code_block:
            if pending_code_field:
                code_lines.append(raw_line.rstrip())
            continue
        if line.startswith("## "):
            pending_code_field = ""
            current_section = line.removeprefix("## ").strip()
            continue
        if not line:
            continue
        if not line.startswith("- ") or ":" not in line:
            pending_code_field = ""
            continue
        key, value = line.removeprefix("- ").split(":", 1)
        field_key = f"{current_section}/{key.strip()}"
        fields[field_key] = value.strip()
        pending_code_field = field_key if not value.strip() else ""
    return fields


def print_checks(checks: list[Check]) -> int:
    failed = 0
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
        if not check.ok:
            failed += 1
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SwitchType release readiness.")
    parser.add_argument("--strict", action="store_true", help="Require real audio samples, demo GIF, and real benchmark report evidence.")
    parser.add_argument(
        "--ignore-final-result",
        action="store_true",
        help="Strict mode only: allow docs/verification-log.md to omit Final Readiness/Result for pre-final validation.",
    )
    parser.add_argument("--run-build", action="store_true", help="Also run Swift build and app packaging from Python. This may fail in nested sandbox environments.")
    args = parser.parse_args()

    checks = [
        exists("README.md"),
        exists("LICENSE"),
        exists("CONTRIBUTING.md"),
        exists("SECURITY.md"),
        exists("CHANGELOG.md"),
        exists("bench/README.md"),
        exists("app/SwitchType/README.md"),
        exists("docs/public-datasets.md"),
        exists("docs/privacy.md"),
        exists("docs/demo.md"),
        exists("docs/release-checklist.md"),
        exists("docs/verification-log.md"),
        exists("docs/assets/demo-storyboard.svg"),
        exists("bench/config/benchmark.example.json"),
        exists("bench/config/hotwords.example.json"),
        count_manifest_samples("bench/samples/manifest.30-template.jsonl", 30),
        exists("scripts/bootstrap_whisper_cpp.sh"),
        exists("scripts/package_app.sh"),
        exists("scripts/record_demo.sh"),
        command_ok("python tests", ["python3", "-m", "unittest", "discover", "-s", "bench/tests", "-v"]),
        exists("app/SwitchType/.build/debug/SwitchType"),
        command_ok("swift core check", ["app/SwitchType/.build/debug/SwitchTypeCoreCheck"]),
        exists("dist/SwitchType.app/Contents/MacOS/SwitchType"),
        exists("dist/SwitchType.app/Contents/Resources/hotwords.example.json"),
        exists("dist/SwitchType-0.1.0.zip"),
    ]

    if args.run_build:
        checks.extend(
            [
                command_ok("swift build", ["swift", "build", "--package-path", "app/SwitchType"]),
                command_ok("package app", ["./scripts/package_app.sh"]),
            ]
        )

    if args.strict:
        checks.extend(
            [
                strict_audio_check("bench/samples/manifest.30-template.jsonl", 30),
                gif_check("docs/assets/switchtype-demo.gif"),
                benchmark_report_check("bench/reports/real-asr.md", 30),
                readme_benchmark_summary_check("README.md", "bench/reports/real-asr.md"),
                verification_log_check("docs/verification-log.md", require_final_result=not args.ignore_final_result),
            ]
        )

    failed = print_checks(checks)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
