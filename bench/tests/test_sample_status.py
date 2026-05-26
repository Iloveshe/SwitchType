import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from bench.scripts.sample_status import collect_status, wav_duration, write_valid_manifest


def write_test_wav(
    path: Path,
    seconds: float = 0.25,
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


class SampleStatusTests(unittest.TestCase):
    def test_wav_duration_reads_valid_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            write_test_wav(audio, seconds=0.5)

            self.assertAlmostEqual(wav_duration(audio), 0.5)

    def test_collect_status_reports_missing_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorded = root / "recorded.wav"
            too_short = root / "too-short.wav"
            unreadable = root / "unreadable.wav"
            wrong_rate = root / "wrong-rate.wav"
            stereo = root / "stereo.wav"
            silent = root / "silent.wav"
            missing = root / "missing.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(recorded, seconds=0.25)
            write_test_wav(too_short, seconds=0.05)
            write_test_wav(wrong_rate, seconds=0.25, rate=8000)
            write_test_wav(stereo, seconds=0.25, channels=2)
            write_test_wav(silent, seconds=0.25, signal=False)
            unreadable.write_text("not a wav", encoding="utf-8")
            rows = [
                {"id": "sample-001", "audio": str(recorded), "reference": "Codex PR", "terms": ["Codex"]},
                {"id": "sample-002", "audio": str(too_short), "reference": "MCP", "terms": ["MCP"]},
                {"id": "sample-003", "audio": str(unreadable), "reference": "Go test", "terms": ["Go"]},
                {"id": "sample-004", "audio": str(wrong_rate), "reference": "prelive", "terms": ["prelive"]},
                {"id": "sample-005", "audio": str(stereo), "reference": "Codex issue", "terms": ["Codex"]},
                {"id": "sample-006", "audio": str(silent), "reference": "CI", "terms": ["CI"]},
                {"id": "sample-007", "audio": str(missing), "reference": "SeaTalk", "terms": ["SeaTalk"]},
            ]
            manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            statuses = collect_status(manifest, min_duration=0.25)

            self.assertEqual(
                [status.state for status in statuses],
                ["valid", "too_short", "unreadable", "wrong_format", "wrong_format", "silent", "missing"],
            )
            self.assertEqual([status.exists for status in statuses], [True, True, True, True, True, True, False])
            self.assertGreater(statuses[0].bytes, 0)
            self.assertAlmostEqual(statuses[0].duration_seconds or 0, 0.25)
            self.assertAlmostEqual(statuses[1].duration_seconds or 0, 0.05)
            self.assertIsNone(statuses[2].duration_seconds)
            self.assertAlmostEqual(statuses[3].duration_seconds or 0, 0.25)
            self.assertAlmostEqual(statuses[4].duration_seconds or 0, 0.25)
            self.assertAlmostEqual(statuses[5].duration_seconds or 0, 0.25)
            self.assertIsNone(statuses[6].duration_seconds)

    def test_cli_json_reports_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorded = root / "recorded.wav"
            too_short = root / "too-short.wav"
            wrong_rate = root / "wrong-rate.wav"
            silent = root / "silent.wav"
            missing = root / "missing.wav"
            manifest = root / "manifest.jsonl"
            write_test_wav(recorded, seconds=0.25)
            write_test_wav(too_short, seconds=0.05)
            write_test_wav(wrong_rate, seconds=0.25, rate=8000)
            write_test_wav(silent, seconds=0.25, signal=False)
            rows = [
                {"id": "sample-001", "audio": str(recorded), "reference": "Codex PR", "terms": ["Codex"]},
                {"id": "sample-002", "audio": str(too_short), "reference": "MCP", "terms": ["MCP"]},
                {"id": "sample-003", "audio": str(wrong_rate), "reference": "Go", "terms": ["Go"]},
                {"id": "sample-004", "audio": str(silent), "reference": "CI", "terms": ["CI"]},
                {"id": "sample-005", "audio": str(missing), "reference": "SeaTalk", "terms": ["SeaTalk"]},
            ]
            manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/sample_status.py",
                    "--manifest",
                    str(manifest),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["total"], 5)
            self.assertEqual(payload["recorded"], 1)
            self.assertEqual(payload["valid"], 1)
            self.assertEqual(payload["missing"], 1)
            self.assertEqual(payload["too_short"], 1)
            self.assertEqual(payload["wrong_format"], 1)
            self.assertEqual(payload["silent"], 1)
            self.assertEqual(payload["unreadable"], 0)
            self.assertEqual(
                [sample["state"] for sample in payload["samples"]],
                ["valid", "too_short", "wrong_format", "silent", "missing"],
            )

    def test_write_valid_manifest_exports_only_valid_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_audio = root / "recorded.wav"
            too_short = root / "too-short.wav"
            missing = root / "missing.wav"
            manifest = root / "manifest.jsonl"
            output = root / "recorded-preview.jsonl"
            write_test_wav(valid_audio, seconds=0.25)
            write_test_wav(too_short, seconds=0.05)
            rows = [
                {"id": "sample-001", "audio": str(valid_audio), "reference": "Codex PR", "terms": ["Codex", "PR"]},
                {"id": "sample-002", "audio": str(too_short), "reference": "MCP", "terms": ["MCP"]},
                {"id": "sample-003", "audio": str(missing), "reference": "SeaTalk", "terms": ["SeaTalk"]},
            ]
            manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            count = write_valid_manifest(manifest, output, min_duration=0.25)

            self.assertEqual(count, 1)
            exported_rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                exported_rows,
                [
                    {
                        "id": "sample-001",
                        "audio": str(valid_audio),
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    }
                ],
            )

    def test_write_valid_manifest_rejects_empty_valid_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.wav"
            manifest = root / "manifest.jsonl"
            output = root / "recorded-preview.jsonl"
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": str(missing), "reference": "Codex", "terms": ["Codex"]})
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "No valid recordings"):
                write_valid_manifest(manifest, output, min_duration=0.25)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
