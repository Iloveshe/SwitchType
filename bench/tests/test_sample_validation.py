import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


def write_test_wav(
    path: Path,
    seconds: float,
    rate: int = 16000,
    channels: int = 1,
    signal: bool = True,
) -> None:
    frames = int(seconds * rate)
    sample = b"\x01\x00" if signal else b"\x00\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(sample * frames * channels)


class SampleValidationTests(unittest.TestCase):
    def test_validate_manifest_reports_missing_manifest_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "missing.jsonl"

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(f"Manifest missing: {manifest}", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_validate_manifest_count_without_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(Path(tmp) / "missing.wav"),
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertEqual(completed.returncode, 0)
            self.assertIn("Validated 1 sample(s)", completed.stdout)

    def test_require_audio_rejects_too_short_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "too-short.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(audio, seconds=0.05)
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(audio),
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Too-short audio files", completed.stderr)

    def test_require_audio_rejects_unreadable_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "unreadable.wav"
            manifest = root / "manifest.jsonl"
            audio.write_text("not a wav", encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(audio),
                        "reference": "MCP",
                        "terms": ["MCP"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Unreadable audio files", completed.stderr)

    def test_require_audio_rejects_silent_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(audio, seconds=0.25, signal=False)
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(audio),
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Silent audio files", completed.stderr)

    def test_require_audio_rejects_wrong_sample_rate_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "wrong-rate.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(audio, seconds=0.25, rate=8000)
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(audio),
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Wrong-format WAV files", completed.stderr)
            self.assertIn("16000 Hz mono", completed.stderr)

    def test_require_audio_rejects_stereo_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "stereo.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(audio, seconds=0.25, channels=2)
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": str(audio),
                        "reference": "MCP issue",
                        "terms": ["MCP", "issue"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/validate_samples.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--require-audio",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Wrong-format WAV files", completed.stderr)


if __name__ == "__main__":
    unittest.main()
