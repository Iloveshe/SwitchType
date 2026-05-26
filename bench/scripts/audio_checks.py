from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path


EXPECTED_SAMPLE_RATE = 16000
EXPECTED_CHANNELS = 1


@dataclass(frozen=True)
class WavInfo:
    duration_seconds: float
    sample_rate: int
    channels: int
    has_signal: bool


def read_wav_info(path: Path) -> WavInfo | None:
    if path.suffix.lower() != ".wav" or not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            if rate <= 0:
                return None
            frame_count = handle.getnframes()
            frame_bytes = handle.readframes(frame_count)
            return WavInfo(
                duration_seconds=frame_count / float(rate),
                sample_rate=rate,
                channels=handle.getnchannels(),
                has_signal=any(byte != 0 for byte in frame_bytes),
            )
    except (OSError, EOFError, wave.Error):
        return None


def is_expected_wav_format(info: WavInfo) -> bool:
    return info.sample_rate == EXPECTED_SAMPLE_RATE and info.channels == EXPECTED_CHANNELS


def expected_wav_format_label() -> str:
    return f"{EXPECTED_SAMPLE_RATE} Hz mono"
