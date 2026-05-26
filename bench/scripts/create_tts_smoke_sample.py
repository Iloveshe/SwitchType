from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import wave
from pathlib import Path


DEFAULT_TEXT = "SwitchType Codex PR issue CI"
DEFAULT_TERMS = ["SwitchType", "Codex", "PR", "issue", "CI"]
FALLBACK_TEXT = "And so, my fellow Americans, ask not what your country can do for you, ask what you can do for your country."
FALLBACK_TERMS = ["Americans", "country"]


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"Missing required macOS tool: {name}")
    return path


def wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            if rate <= 0:
                return 0
            return handle.getnframes() / float(rate)
    except (OSError, EOFError, wave.Error):
        return 0


def use_fallback(output_audio: Path, fallback_audio: Path | None) -> tuple[str, list[str]] | None:
    if fallback_audio is None or not fallback_audio.exists():
        return None
    shutil.copyfile(fallback_audio, output_audio)
    return FALLBACK_TEXT, FALLBACK_TERMS


def create_sample(output_audio: Path, text: str, fallback_audio: Path | None) -> tuple[str, list[str]]:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    aiff_path = output_audio.with_suffix(".aiff")
    try:
        say = require_tool("say")
        afconvert = require_tool("afconvert")
        subprocess.run([say, "-o", str(aiff_path), text], check=True)
        subprocess.run([afconvert, str(aiff_path), str(output_audio), "-f", "WAVE", "-d", "LEI16@16000"], check=True)
        if wav_duration_seconds(output_audio) > 0:
            return text, DEFAULT_TERMS
    except (SystemExit, subprocess.CalledProcessError):
        pass
    finally:
        aiff_path.unlink(missing_ok=True)

    fallback = use_fallback(output_audio, fallback_audio)
    if fallback is not None:
        return fallback
    raise SystemExit("Synthetic TTS audio was empty. Run outside the sandbox or provide --fallback-audio.")


def load_manifest(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
        if "id" not in row or "reference" not in row:
            raise SystemExit(f"Manifest row {line_number} must include id and reference.")
        rows.append(row)
    return rows


def create_manifest_samples(
    source_manifest: Path,
    output_manifest: Path,
    audio_dir: Path,
    fallback_audio: Path | None,
    limit: int | None = None,
    create_audio=create_sample,
) -> int:
    rows = load_manifest(source_manifest)
    selected_rows = rows[:limit] if limit is not None else rows
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_rows: list[str] = []
    for row in selected_rows:
        sample_id = str(row["id"])
        reference = str(row["reference"])
        audio_path = audio_dir / f"{sample_id}.wav"
        create_audio(audio_path, reference, fallback_audio)
        output_row = dict(row)
        output_row["audio"] = str(audio_path)
        output_rows.append(json.dumps(output_row, ensure_ascii=False))
    output_manifest.write_text("\n".join(output_rows) + ("\n" if output_rows else ""), encoding="utf-8")
    return len(output_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic ASR smoke-test sample.")
    parser.add_argument("--audio", default=Path("bench/samples/smoke/smoke-001.wav"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/smoke/manifest.jsonl"), type=Path)
    parser.add_argument("--source-manifest", type=Path, help="Generate one synthetic WAV for each row in this manifest.")
    parser.add_argument("--audio-dir", default=Path("bench/samples/tts/audio"), type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--fallback-audio", type=Path)
    args = parser.parse_args()

    if args.source_manifest:
        count = create_manifest_samples(
            source_manifest=args.source_manifest,
            output_manifest=args.manifest,
            audio_dir=args.audio_dir,
            fallback_audio=args.fallback_audio,
            limit=args.limit,
        )
        print(f"Wrote {count} synthetic sample(s)")
        print(f"Wrote {args.manifest}")
        return 0

    reference, terms = create_sample(args.audio, args.text, args.fallback_audio)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "id": "smoke-001",
                "audio": str(args.audio),
                "reference": reference,
                "terms": terms,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.audio}")
    print(f"Wrote {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
