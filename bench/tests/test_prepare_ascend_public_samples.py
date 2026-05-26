import json
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path

from bench.scripts.prepare_ascend_public_samples import (
    PreparedSample,
    load_ascend_rows,
    prepare_samples,
    terms_from_reference,
)


def wav_bytes(seconds: float) -> bytes:
    buffer = BytesIO()
    frames = int(seconds * 16000)
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x01\x00" * frames)
    return buffer.getvalue()


class PrepareAscendPublicSamplesTests(unittest.TestCase):
    def test_makefile_exposes_public_ascend_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("public-ascend:", makefile)
        self.assertIn("bench/scripts/prepare_ascend_public_samples.py", makefile)
        self.assertIn("$${SPLIT:-test}", makefile)
        self.assertIn("$${LIMIT:-50}", makefile)
        self.assertIn("$${PYTHON:-python3}", makefile)

    def test_load_ascend_rows_requests_streaming_dataset(self):
        calls = []

        class FakeDataset:
            def __init__(self):
                self.cast_args = None

            def cast_column(self, *args):
                self.cast_args = args
                return ["row"]

        class FakeAudio:
            def __init__(self, decode):
                self.decode = decode

        def fake_load_dataset(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeDataset()

        rows = load_ascend_rows("test", load_dataset_fn=fake_load_dataset, audio_feature_cls=FakeAudio)

        self.assertEqual(rows, ["row"])
        self.assertEqual(calls, [(("CAiRE/ASCEND",), {"split": "test", "streaming": True})])

    def test_prepare_samples_can_write_huggingface_decode_false_wav_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            audio_dir = root / "audio"

            count = prepare_samples(
                rows=[
                    {
                        "id": "bytes-row",
                        "audio": {"bytes": wav_bytes(seconds=0.3), "path": "bytes-row.wav"},
                        "transcription": "ASCEND mixed Codex",
                        "language": "mixed",
                    }
                ],
                manifest=manifest,
                audio_dir=audio_dir,
                protected_terms=["Codex"],
            )

            self.assertEqual(count, 1)
            with wave.open(str(audio_dir / "ascend-bytes-row.wav"), "rb") as handle:
                self.assertEqual(handle.getframerate(), 16000)
                self.assertEqual(handle.getnchannels(), 1)

    def test_terms_from_reference_matches_protected_terms_case_insensitively(self):
        terms = terms_from_reference("帮我 review codex PR 和 MCP server", ["Codex", "MCP", "PR", "CI"])

        self.assertEqual(terms, ["Codex", "MCP", "PR"])

    def test_prepare_samples_writes_mixed_rows_to_wav_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            audio_dir = root / "audio"

            count = prepare_samples(
                rows=[
                    {
                        "id": "00099",
                        "audio": {"array": [0.0, 0.25, -0.25, 0.0] * 5000, "sampling_rate": 16000},
                        "transcription": "because i was already 被这本书吸引, Codex PR",
                        "language": "mixed",
                    },
                    {
                        "id": "00100",
                        "audio": {"array": [0.0, 0.1] * 5000, "sampling_rate": 16000},
                        "transcription": "纯中文样本不用于 mixed sanity benchmark",
                        "language": "zh",
                    },
                ],
                manifest=manifest,
                audio_dir=audio_dir,
                limit=10,
                mixed_only=True,
                protected_terms=["Codex", "MCP", "PR"],
            )

            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual(
                rows,
                [
                    {
                        "id": "ascend-00099",
                        "audio": str(audio_dir / "ascend-00099.wav"),
                        "reference": "because i was already 被这本书吸引, Codex PR",
                        "terms": ["Codex", "PR"],
                    }
                ],
            )
            with wave.open(str(audio_dir / "ascend-00099.wav"), "rb") as handle:
                self.assertEqual(handle.getframerate(), 16000)
                self.assertEqual(handle.getnchannels(), 1)
                self.assertGreater(handle.getnframes(), 0)

    def test_prepare_samples_rejects_non_16khz_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError) as raised:
                prepare_samples(
                    rows=[
                        {
                            "id": "bad-rate",
                            "audio": {"array": [0.0, 0.1], "sampling_rate": 8000},
                            "transcription": "bad rate",
                            "language": "mixed",
                        }
                    ],
                    manifest=root / "manifest.jsonl",
                    audio_dir=root / "audio",
                )

            self.assertIn("Expected 16000 Hz audio", str(raised.exception))

    def test_prepared_sample_sanitizes_public_ids(self):
        sample = PreparedSample.from_row(
            {
                "id": "session 1/utt:099",
                "audio": {"array": [0.0, 0.1], "sampling_rate": 16000},
                "transcription": "Codex",
                "language": "mixed",
            },
            protected_terms=["Codex"],
        )

        self.assertEqual(sample.id, "ascend-session-1-utt-099")


if __name__ == "__main__":
    unittest.main()
