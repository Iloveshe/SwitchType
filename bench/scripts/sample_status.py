from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from switchtype_bench.manifest import load_manifest

try:
    from audio_checks import is_expected_wav_format, read_wav_info
except ModuleNotFoundError:
    from bench.scripts.audio_checks import is_expected_wav_format, read_wav_info


@dataclass(frozen=True)
class SampleStatus:
    id: str
    audio: str
    state: str
    exists: bool
    bytes: int
    duration_seconds: float | None
    reference: str


def wav_duration(path: Path) -> float | None:
    info = read_wav_info(path)
    return None if info is None else info.duration_seconds


def classify_audio(path: Path, min_duration: float) -> tuple[str, bool, int, float | None]:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    duration = wav_duration(path)
    if not exists:
        return "missing", exists, size, duration
    if size <= 0:
        return "unreadable", exists, size, duration
    if path.suffix.lower() == ".wav":
        info = read_wav_info(path)
        if info is None:
            return "unreadable", exists, size, duration
        if not is_expected_wav_format(info):
            return "wrong_format", exists, size, duration
        if not info.has_signal:
            return "silent", exists, size, duration
        if info.duration_seconds < min_duration:
            return "too_short", exists, size, duration
    return "valid", exists, size, duration


def collect_status(manifest: Path, min_duration: float = 0.25) -> list[SampleStatus]:
    statuses: list[SampleStatus] = []
    for sample in load_manifest(manifest):
        state, exists, size, duration = classify_audio(sample.audio, min_duration)
        statuses.append(
            SampleStatus(
                id=sample.id,
                audio=str(sample.audio),
                state=state,
                exists=exists,
                bytes=size,
                duration_seconds=duration,
                reference=sample.reference,
            )
        )
    return statuses


def valid_manifest_rows(manifest: Path, min_duration: float = 0.25) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample in load_manifest(manifest):
        state, _exists, _size, _duration = classify_audio(sample.audio, min_duration)
        if state == "valid":
            rows.append(
                {
                    "id": sample.id,
                    "audio": str(sample.audio),
                    "reference": sample.reference,
                    "terms": sample.terms,
                }
            )
    return rows


def write_valid_manifest(manifest: Path, output: Path, min_duration: float = 0.25) -> int:
    rows = valid_manifest_rows(manifest, min_duration=min_duration)
    if not rows:
        raise ValueError(f"No valid recordings found in {manifest}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return len(rows)


def print_table(statuses: list[SampleStatus], show_all: bool) -> None:
    visible = statuses if show_all else [status for status in statuses if status.state != "valid"]
    print("| Sample | Status | Bytes | Duration | Audio |")
    print("|---|---|---:|---:|---|")
    for status in visible:
        duration = "" if status.duration_seconds is None else f"{status.duration_seconds:.2f}s"
        print(f"| {status.id} | {status.state} | {status.bytes} | {duration} | {status.audio} |")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show recording status for a SwitchType sample manifest.")
    parser.add_argument("--manifest", default=Path("bench/samples/manifest.30-template.jsonl"), type=Path)
    parser.add_argument("--all", action="store_true", help="Show valid and invalid samples. Defaults to samples needing attention.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--min-duration", default=0.25, type=float, help="Minimum accepted WAV duration in seconds.")
    parser.add_argument(
        "--valid-manifest-output",
        type=Path,
        help="Write a JSONL manifest containing only currently valid recorded samples.",
    )
    args = parser.parse_args()

    if args.valid_manifest_output is not None:
        try:
            count = write_valid_manifest(args.manifest, args.valid_manifest_output, min_duration=args.min_duration)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Wrote {count} valid sample(s) to {args.valid_manifest_output}")
        return 0

    statuses = collect_status(args.manifest, min_duration=args.min_duration)
    valid = sum(1 for status in statuses if status.state == "valid")
    missing = sum(1 for status in statuses if status.state == "missing")
    too_short = sum(1 for status in statuses if status.state == "too_short")
    unreadable = sum(1 for status in statuses if status.state == "unreadable")
    wrong_format = sum(1 for status in statuses if status.state == "wrong_format")
    silent = sum(1 for status in statuses if status.state == "silent")

    if args.json:
        print(
            json.dumps(
                {
                    "manifest": str(args.manifest),
                    "total": len(statuses),
                    "recorded": valid,
                    "valid": valid,
                    "missing": missing,
                    "too_short": too_short,
                    "unreadable": unreadable,
                    "wrong_format": wrong_format,
                    "silent": silent,
                    "samples": [asdict(status) for status in statuses],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Manifest: {args.manifest}")
    print(f"Recorded: {valid}/{len(statuses)}")
    print(f"Missing: {missing}")
    print(f"Too short: {too_short}")
    print(f"Unreadable: {unreadable}")
    print(f"Wrong format: {wrong_format}")
    print(f"Silent: {silent}")
    print()
    print_table(statuses, show_all=args.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
