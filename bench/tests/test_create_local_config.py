import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CreateLocalConfigTests(unittest.TestCase):
    def test_create_local_config_enables_whisper_and_disables_fake(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--whisper-bin",
                    "bin/whisper-cli",
                    "--whisper-model",
                    "models/ggml-base.bin",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertFalse(engines["fake"]["enabled"])
            self.assertTrue(engines["whisper_cpp"]["enabled"])
            self.assertEqual(engines["whisper_cpp"]["command"][0], "bin/whisper-cli")
            self.assertEqual(engines["whisper_cpp"]["model"], "models/ggml-base.bin")
            self.assertEqual(
                engines["whisper_cpp"]["command"][
                    engines["whisper_cpp"]["command"].index("-l") + 1
                ],
                "auto",
            )

    def test_create_local_config_can_disable_whisper_gpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--whisper-bin",
                    "bin/whisper-cli",
                    "--whisper-model",
                    "models/ggml-base.bin",
                    "--whisper-no-gpu",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertEqual(engines["whisper_cpp"]["command"][:2], ["bin/whisper-cli", "-ng"])

    def test_create_local_config_can_set_timeout_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--timeout-seconds",
                    "900",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(config["timeout_seconds"], 900)

    def test_create_local_config_adds_auto_language_when_template_omits_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template.json"
            output = root / "benchmark.local.json"
            template.write_text(
                json.dumps(
                    {
                        "engines": [
                            {
                                "name": "whisper_cpp",
                                "type": "command",
                                "enabled": False,
                                "model": "model.bin",
                                "command": [
                                    "whisper-cli",
                                    "-m",
                                    "{model}",
                                    "-f",
                                    "{audio}",
                                    "-otxt",
                                    "-of",
                                    "{output_without_suffix}",
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--template",
                    str(template),
                    "--output",
                    str(output),
                    "--whisper-bin",
                    "bin/whisper-cli",
                    "--whisper-model",
                    "models/ggml-base.bin",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            command = config["engines"][0]["command"]
            self.assertEqual(command[command.index("-l") + 1], "auto")
            self.assertLess(command.index("-l"), command.index("-otxt"))

    def test_create_local_config_can_enable_sensevoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--enable-sensevoice",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertTrue(engines["sensevoice_funasr"]["enabled"])
            self.assertIn("bench/scripts/run_sensevoice.py", engines["sensevoice_funasr"]["command"])

    def test_create_local_config_can_set_sensevoice_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--enable-sensevoice",
                    "--sensevoice-python",
                    ".venv/bin/python",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertEqual(engines["sensevoice_funasr"]["command"][0], ".venv/bin/python")

    def test_create_local_config_can_set_sensevoice_huggingface_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.local.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--enable-sensevoice",
                    "--sensevoice-model",
                    "FunAudioLLM/SenseVoiceSmall",
                    "--sensevoice-hub",
                    "hf",
                    "--sensevoice-vad-model",
                    "none",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            command = engines["sensevoice_funasr"]["command"]
            self.assertEqual(engines["sensevoice_funasr"]["model"], "FunAudioLLM/SenseVoiceSmall")
            self.assertEqual(command[command.index("--hub") + 1], "hf")
            self.assertEqual(command[command.index("--vad-model") + 1], "none")

    def test_create_local_config_can_use_asr_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "benchmark.local.json"
            asr_config = root / "asr.json"
            asr_config.write_text(
                "{\n"
                '  "whisper_bin": "/configured/whisper-cli",\n'
                '  "whisper_model": "/configured/model.bin",\n'
                '  "whisper_no_gpu": true\n'
                "}\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--asr-config",
                    str(asr_config),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertEqual(engines["whisper_cpp"]["command"][:2], ["/configured/whisper-cli", "-ng"])
            self.assertEqual(engines["whisper_cpp"]["model"], "/configured/model.bin")

    def test_create_local_config_cli_paths_override_asr_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "benchmark.local.json"
            asr_config = root / "asr.json"
            asr_config.write_text(
                "{\n"
                '  "whisper_bin": "/configured/whisper-cli",\n'
                '  "whisper_model": "/configured/model.bin"\n'
                "}\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/create_local_config.py",
                    "--output",
                    str(output),
                    "--asr-config",
                    str(asr_config),
                    "--whisper-bin",
                    "/cli/whisper-cli",
                    "--whisper-model",
                    "/cli/model.bin",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            engines = {engine["name"]: engine for engine in config["engines"]}
            self.assertEqual(engines["whisper_cpp"]["command"][0], "/cli/whisper-cli")
            self.assertEqual(engines["whisper_cpp"]["model"], "/cli/model.bin")


if __name__ == "__main__":
    unittest.main()
