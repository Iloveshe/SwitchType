import os
import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path

from scripts.asr_config import resolve_whisper_settings


class ASRConfigTests(unittest.TestCase):
    def test_empty_environment_does_not_fall_back_to_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = os.environ.get("SWITCHTYPE_WHISPER_BIN")
            os.environ["SWITCHTYPE_WHISPER_BIN"] = "/process/env/whisper-cli"
            try:
                settings = resolve_whisper_settings(root, {})
            finally:
                if previous is None:
                    os.environ.pop("SWITCHTYPE_WHISPER_BIN", None)
                else:
                    os.environ["SWITCHTYPE_WHISPER_BIN"] = previous

        self.assertEqual(
            settings.whisper_bin,
            str(root / "third_party/whisper.cpp/build/bin/whisper-cli"),
        )

    def test_create_asr_config_writes_expected_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "asr.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/create_asr_config.py",
                    "--output",
                    str(output),
                    "--whisper-bin",
                    "/opt/whisper-cli",
                    "--whisper-model",
                    "/models/ggml-large-v3-turbo.bin",
                    "--no-gpu",
                    "--timeout-seconds",
                    "300",
                    "--expected-input-device-name",
                    "DJI MIC MINI",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(config["whisper_bin"], "/opt/whisper-cli")
        self.assertEqual(config["asr_backend"], "local_whisper")
        self.assertEqual(config["local_whisper_profile"], "custom")
        self.assertEqual(config["whisper_model"], "/models/ggml-large-v3-turbo.bin")
        self.assertEqual(config["whisper_no_gpu"], True)
        self.assertEqual(config["whisper_language"], "zh")
        self.assertEqual(config["timeout_seconds"], 300)
        self.assertEqual(config["expected_input_device_name"], "DJI MIC MINI")

    def test_create_asr_config_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "asr.json"
            output.write_text("existing", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/create_asr_config.py",
                    "--output",
                    str(output),
                    "--whisper-bin",
                    "/opt/whisper-cli",
                    "--whisper-model",
                    "/models/model.bin",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("--force", completed.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_makefile_exposes_asr_config_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("asr-config:", makefile)
        self.assertIn("scripts/create_asr_config.py", makefile)


if __name__ == "__main__":
    unittest.main()
