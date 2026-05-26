import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.create_qwen3_asr_http_config import write_config
from scripts.qwen3_asr_client import extract_transcript
from scripts.qwen3_asr_server import Qwen3ASRRuntime, parse_transcription_result


class ResultObject:
    def __init__(self, text: str, language: str = "Chinese"):
        self.text = text
        self.language = language


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, **kwargs):
        self.calls.append(kwargs)
        return [ResultObject("你好 Qwen3-ASR")]


class Qwen3ASROfficialTests(unittest.TestCase):
    def test_parse_transcription_result_accepts_qwen_result_object(self):
        payload = parse_transcription_result([ResultObject(" 你好 Codex ", "Chinese")])

        self.assertEqual(payload["text"], "你好 Codex")
        self.assertEqual(payload["language"], "Chinese")

    def test_runtime_loads_official_model_lazily_and_transcribes_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            audio.write_bytes(b"placeholder")
            fake_model = FakeModel()

            with patch("scripts.qwen3_asr_server.load_official_qwen3_asr_model", return_value=fake_model) as load:
                runtime = Qwen3ASRRuntime(
                    model_name="Qwen/Qwen3-ASR-0.6B",
                    language="Chinese",
                    device_map="cpu",
                    dtype="float32",
                    max_new_tokens=256,
                )

                first = runtime.transcribe(audio)
                second = runtime.transcribe(audio)

            self.assertEqual(first["text"], "你好 Qwen3-ASR")
            self.assertEqual(second["text"], "你好 Qwen3-ASR")
            load.assert_called_once()
            self.assertEqual(fake_model.calls[0]["audio"], str(audio))
            self.assertEqual(fake_model.calls[0]["language"], "Chinese")

    def test_runtime_reports_load_and_inference_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            audio.write_bytes(b"placeholder")
            fake_model = FakeModel()

            with patch("scripts.qwen3_asr_server.load_official_qwen3_asr_model", return_value=fake_model):
                runtime = Qwen3ASRRuntime(
                    model_name="Qwen/Qwen3-ASR-0.6B",
                    language="Chinese",
                    device_map="cpu",
                    dtype="float32",
                    max_new_tokens=256,
                )

                first_payload, first_metrics = runtime.transcribe_with_metrics(audio)
                _, second_metrics = runtime.transcribe_with_metrics(audio)

            self.assertEqual(first_payload["text"], "你好 Qwen3-ASR")
            self.assertFalse(first_metrics["model_loaded_before"])
            self.assertTrue(second_metrics["model_loaded_before"])
            self.assertIn("load_ms", first_metrics)
            self.assertIn("infer_ms", first_metrics)
            self.assertGreaterEqual(first_metrics["load_ms"], 0)
            self.assertGreaterEqual(first_metrics["infer_ms"], 0)

    def test_runtime_can_warm_up_model_before_first_transcription(self):
        fake_model = FakeModel()

        with patch("scripts.qwen3_asr_server.load_official_qwen3_asr_model", return_value=fake_model) as load:
            runtime = Qwen3ASRRuntime(
                model_name="Qwen/Qwen3-ASR-0.6B",
                language="Chinese",
                device_map="cpu",
                dtype="float32",
                max_new_tokens=256,
            )

            runtime.warm_up()
            runtime.warm_up()

        load.assert_called_once()

    def test_client_extracts_text_from_http_json_response(self):
        self.assertEqual(extract_transcript(json.dumps({"text": " 你好 Qwen3 "})), "你好 Qwen3")

    def test_config_writer_points_switchtype_at_local_http_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "asr.json"

            write_config(config, url="http://127.0.0.1:8765/transcribe", timeout_seconds=180)

            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(payload["asr_backend"], "http_json")
            self.assertEqual(payload["asr_http_profile"], "qwen3_official_local")
            self.assertEqual(payload["asr_http_url"], "http://127.0.0.1:8765/transcribe")
            self.assertEqual(payload["asr_http_field_name"], "audio")
            self.assertEqual(payload["asr_http_transcript_key"], "text")
            self.assertEqual(payload["timeout_seconds"], 180)

    def test_makefile_exposes_qwen3_asr_validation_targets(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("qwen3-asr-server:", makefile)
        self.assertIn("qwen3-asr-config:", makefile)
        self.assertIn("qwen3-asr-client:", makefile)
        self.assertIn("QWEN_PYTHON", makefile)
        self.assertIn("scripts/qwen3_asr_server.py", makefile)
        self.assertIn("scripts/create_qwen3_asr_http_config.py", makefile)
        self.assertIn("scripts/qwen3_asr_client.py", makefile)

    def test_qwen3_benchmark_config_uses_command_client(self):
        config_path = Path("bench/config/benchmark.qwen3-official.example.json")
        payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["timeout_seconds"], 180)
        engine = payload["engines"][0]
        self.assertEqual(engine["name"], "qwen3_asr_official_http")
        self.assertEqual(engine["type"], "command")
        self.assertIn("scripts/qwen3_asr_client.py", engine["command"])
        self.assertIn("{audio}", engine["command"])


if __name__ == "__main__":
    unittest.main()
