from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from bench.scripts.create_tts_smoke_sample import (
    FALLBACK_TERMS,
    FALLBACK_TEXT,
    create_manifest_samples,
    use_fallback,
    wav_duration_seconds,
)


def write_silent_wav(path: Path, seconds: float = 0.25, rate: int = 16000) -> None:
    frames = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


class CreateTTSSmokeSampleTests(unittest.TestCase):
    def test_wav_duration_detects_non_empty_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_silent_wav(audio, seconds=0.5)

            self.assertAlmostEqual(wav_duration_seconds(audio), 0.5)

    def test_fallback_audio_is_copied_with_reference_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = root / "fallback.wav"
            output = root / "output.wav"
            write_silent_wav(fallback)

            result = use_fallback(output, fallback)

            self.assertEqual(result, (FALLBACK_TEXT, FALLBACK_TERMS))
            self.assertGreater(wav_duration_seconds(output), 0)

    def test_create_manifest_samples_generates_audio_and_preserves_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "manifest.jsonl"
            output_manifest = root / "tts/manifest.jsonl"
            audio_dir = root / "tts/audio"
            source.write_text(
                '{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"帮我看一下 Codex 的 PR","terms":["Codex","PR"]}\n'
                '{"id":"sample-002","audio":"bench/samples/audio/sample-002.wav","reference":"这个 MCP server","terms":["MCP","server"]}\n',
                encoding="utf-8",
            )
            generated: list[tuple[Path, str]] = []

            def fake_create_audio(audio_path: Path, text: str, fallback_audio: Path | None):
                generated.append((audio_path, text))
                write_silent_wav(audio_path, seconds=0.25)
                return text, []

            count = create_manifest_samples(
                source_manifest=source,
                output_manifest=output_manifest,
                audio_dir=audio_dir,
                fallback_audio=None,
                create_audio=fake_create_audio,
            )

            rows = [json.loads(line) for line in output_manifest.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(count, 2)
        self.assertEqual([text for _, text in generated], ["帮我看一下 Codex 的 PR", "这个 MCP server"])
        self.assertEqual(rows[0]["audio"], str(audio_dir / "sample-001.wav"))
        self.assertEqual(rows[0]["reference"], "帮我看一下 Codex 的 PR")
        self.assertEqual(rows[0]["terms"], ["Codex", "PR"])
        self.assertEqual(rows[1]["audio"], str(audio_dir / "sample-002.wav"))
        self.assertEqual(rows[1]["reference"], "这个 MCP server")
        self.assertEqual(rows[1]["terms"], ["MCP", "server"])

    def test_makefile_exposes_tts_benchmark_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("tts-manifest:", makefile)
        self.assertIn("tts-benchmark:", makefile)
        self.assertIn("bench/scripts/create_tts_smoke_sample.py", makefile)
        self.assertIn("./scripts/run_tts_manifest_benchmark.sh", makefile)


if __name__ == "__main__":
    unittest.main()
