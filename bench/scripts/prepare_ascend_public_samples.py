from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


EXPECTED_SAMPLE_RATE = 16000


def sanitize_id(value: object) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    safe = safe.strip("-._").lower()
    if not safe:
        raise ValueError("ASCEND row is missing a usable id")
    return f"ascend-{safe}"


def term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if term.isascii() and term.replace("_", "").replace("-", "").isalnum():
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def terms_from_reference(reference: str, protected_terms: Sequence[str]) -> list[str]:
    matched: list[str] = []
    for term in protected_terms:
        if term and term_pattern(term).search(reference):
            matched.append(term)
    return matched


@dataclass(frozen=True)
class AudioPayload:
    samples: Sequence[float] | None
    wav_bytes: bytes | None
    sample_rate: int


def audio_payload_from_row(row: dict) -> AudioPayload:
    audio = row.get("audio")
    if not isinstance(audio, dict):
        raise ValueError("ASCEND row is missing an audio object")
    wav_bytes = audio.get("bytes")
    if wav_bytes:
        return AudioPayload(samples=None, wav_bytes=bytes(wav_bytes), sample_rate=EXPECTED_SAMPLE_RATE)
    samples = audio.get("array")
    sample_rate = int(audio.get("sampling_rate") or 0)
    if hasattr(samples, "tolist"):
        samples = samples.tolist()
    if samples is None:
        raise ValueError("ASCEND row is missing audio samples")
    if sample_rate != EXPECTED_SAMPLE_RATE:
        row_id = row.get("id", "<unknown>")
        raise ValueError(f"Expected 16000 Hz audio for {row_id}, found {sample_rate} Hz")
    return AudioPayload(samples=samples, wav_bytes=None, sample_rate=sample_rate)


def pcm16_frame(value: object) -> bytes:
    sample = float(value)
    sample = max(-1.0, min(1.0, sample))
    return struct.pack("<h", int(round(sample * 32767.0)))


def write_wav(path: Path, samples: Sequence[float], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(pcm16_frame(sample) for sample in samples))


def write_audio(path: Path, audio: AudioPayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.wav_bytes is not None:
        path.write_bytes(audio.wav_bytes)
        return
    if audio.samples is None:
        raise ValueError("ASCEND row is missing audio samples")
    write_wav(path, audio.samples, audio.sample_rate)


@dataclass(frozen=True)
class PreparedSample:
    id: str
    audio: AudioPayload
    reference: str
    terms: list[str]

    @classmethod
    def from_row(cls, row: dict, protected_terms: Sequence[str] | None = None) -> "PreparedSample":
        audio = audio_payload_from_row(row)
        reference = str(row.get("transcription") or "").strip()
        if not reference:
            raise ValueError(f"ASCEND row {row.get('id', '<unknown>')} is missing transcription")
        return cls(
            id=sanitize_id(row.get("id")),
            audio=audio,
            reference=reference,
            terms=terms_from_reference(reference, protected_terms or []),
        )


def prepare_samples(
    rows: Iterable[dict],
    manifest: Path,
    audio_dir: Path,
    limit: int | None = None,
    mixed_only: bool = True,
    protected_terms: Sequence[str] | None = None,
) -> int:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with manifest.open("w", encoding="utf-8") as file:
        for row in rows:
            if limit is not None and count >= limit:
                break
            if mixed_only and str(row.get("language") or "").lower() != "mixed":
                continue
            sample = PreparedSample.from_row(row, protected_terms=protected_terms)
            audio_path = audio_dir / f"{sample.id}.wav"
            write_audio(audio_path, sample.audio)
            file.write(
                json.dumps(
                    {
                        "id": sample.id,
                        "audio": str(audio_path),
                        "reference": sample.reference,
                        "terms": sample.terms,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def load_protected_terms(path: Path | None) -> list[str]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(term) for term in data.get("protected_terms", [])]


def load_ascend_rows(split: str, load_dataset_fn=None, audio_feature_cls=None):
    if load_dataset_fn is None:
        try:
            from datasets import load_dataset as load_dataset_fn
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "Missing dependency: install the optional public dataset helper with `python3 -m pip install datasets`."
            ) from exc
    if audio_feature_cls is None:
        try:
            from datasets import Audio as audio_feature_cls
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "Missing dependency: install the optional public dataset helper with `python3 -m pip install datasets`."
            ) from exc
    dataset = load_dataset_fn("CAiRE/ASCEND", split=split, streaming=True)
    return dataset.cast_column("audio", audio_feature_cls(decode=False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download ASCEND from Hugging Face, export mixed Chinese-English utterances as "
            "16 kHz mono WAV files, and write a SwitchType public benchmark manifest."
        )
    )
    parser.add_argument("--split", default="test", help="ASCEND split to load from Hugging Face.")
    parser.add_argument("--limit", default=50, type=int, help="Maximum number of usable samples to export.")
    parser.add_argument("--manifest", default=Path("bench/samples/public/manifest.jsonl"), type=Path)
    parser.add_argument("--audio-dir", default=Path("bench/samples/public/audio"), type=Path)
    parser.add_argument("--hotwords", default=Path("bench/config/hotwords.example.json"), type=Path)
    parser.add_argument("--include-all-languages", action="store_true", help="Do not filter ASCEND rows to language=mixed.")
    args = parser.parse_args()

    rows = load_ascend_rows(args.split)
    protected_terms = load_protected_terms(args.hotwords)
    count = prepare_samples(
        rows=rows,
        manifest=args.manifest,
        audio_dir=args.audio_dir,
        limit=args.limit,
        mixed_only=not args.include_all_languages,
        protected_terms=protected_terms,
    )
    print(f"Wrote {count} ASCEND sample(s) to {args.manifest}")
    print(f"Audio directory: {args.audio_dir}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Hugging Face streaming can leave non-daemon worker threads alive after the requested rows are exported.
    os._exit(exit_code)
