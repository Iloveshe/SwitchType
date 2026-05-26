from __future__ import annotations

import argparse
from pathlib import Path

from switchtype_bench.manifest import load_manifest

try:
    from audio_checks import expected_wav_format_label, is_expected_wav_format, read_wav_info
except ModuleNotFoundError:
    from bench.scripts.audio_checks import expected_wav_format_label, is_expected_wav_format, read_wav_info


def wav_duration(path: Path) -> float | None:
    info = read_wav_info(path)
    return None if info is None else info.duration_seconds


def unusable_audio(paths: list[Path], min_duration: float) -> tuple[list[Path], list[Path], list[Path], list[Path], list[Path]]:
    empty_or_unreadable: list[Path] = []
    unreadable: list[Path] = []
    wrong_format: list[Path] = []
    silent: list[Path] = []
    too_short: list[Path] = []
    for path in paths:
        if path.stat().st_size <= 0:
            empty_or_unreadable.append(path)
            continue
        if path.suffix.lower() != ".wav":
            continue
        info = read_wav_info(path)
        if info is None:
            unreadable.append(path)
        elif not is_expected_wav_format(info):
            wrong_format.append(path)
        elif not info.has_signal:
            silent.append(path)
        elif info.duration_seconds < min_duration:
            too_short.append(path)
    return empty_or_unreadable, unreadable, wrong_format, silent, too_short


def fail_with_audio_errors(
    missing: list[Path],
    empty_or_unreadable: list[Path],
    unreadable: list[Path],
    wrong_format: list[Path],
    silent: list[Path],
    too_short: list[Path],
) -> None:
    sections: list[str] = []
    if missing:
        sections.append("Missing audio files:\n" + "\n".join(str(path) for path in missing))
    if empty_or_unreadable:
        sections.append("Empty audio files:\n" + "\n".join(str(path) for path in empty_or_unreadable))
    if unreadable:
        sections.append("Unreadable audio files:\n" + "\n".join(str(path) for path in unreadable))
    if wrong_format:
        sections.append(
            f"Wrong-format WAV files (expected {expected_wav_format_label()}):\n"
            + "\n".join(str(path) for path in wrong_format)
        )
    if silent:
        sections.append("Silent audio files:\n" + "\n".join(str(path) for path in silent))
    if too_short:
        sections.append("Too-short audio files:\n" + "\n".join(str(path) for path in too_short))
    if sections:
        raise SystemExit("\n\n".join(sections))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SwitchType benchmark sample manifests.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--require-audio", action="store_true")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--min-duration", default=0.25, type=float, help="Minimum accepted WAV duration in seconds.")
    args = parser.parse_args()

    if not args.manifest.exists():
        raise SystemExit(f"Manifest missing: {args.manifest}")

    samples = load_manifest(args.manifest)
    if args.expected_count is not None and len(samples) != args.expected_count:
        raise SystemExit(f"Expected {args.expected_count} samples, found {len(samples)}")

    missing = [sample.audio for sample in samples if not sample.audio.exists()]
    present = [sample.audio for sample in samples if sample.audio.exists()]
    empty_or_unreadable, unreadable, wrong_format, silent, too_short = unusable_audio(present, args.min_duration)
    if args.require_audio:
        fail_with_audio_errors(missing, empty_or_unreadable, unreadable, wrong_format, silent, too_short)

    print(f"Validated {len(samples)} sample(s) from {args.manifest}")
    if missing:
        print(f"{len(missing)} audio file(s) are not present yet")
    if too_short:
        print(f"{len(too_short)} audio file(s) are shorter than {args.min_duration:.2f}s")
    invalid_count = len(empty_or_unreadable) + len(unreadable)
    if invalid_count:
        print(f"{invalid_count} audio file(s) are unreadable or empty")
    if wrong_format:
        print(f"{len(wrong_format)} WAV file(s) do not match {expected_wav_format_label()}")
    if silent:
        print(f"{len(silent)} audio file(s) are silent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
