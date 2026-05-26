import sys
import tempfile
import unittest
from pathlib import Path

from switchtype_bench.asr import CommandEngine


class CommandEngineTests(unittest.TestCase):
    def test_empty_command_transcript_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            audio.write_bytes(b"placeholder")
            command_script = root / "empty_transcript.py"
            command_script.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[1]).write_text('', encoding='utf-8')\n"
                "print('audio decode failed', file=sys.stderr)\n",
                encoding="utf-8",
            )
            engine = CommandEngine([sys.executable, str(command_script), "{output}"], model=None, timeout_seconds=5)

            with self.assertRaisesRegex(RuntimeError, "audio decode failed"):
                engine.transcribe(audio)

    def test_failed_command_error_includes_audio_and_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            audio.write_bytes(b"placeholder")
            command_script = root / "fail.py"
            command_script.write_text(
                "import sys\n"
                "print('model exploded', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            engine = CommandEngine([sys.executable, str(command_script), "{audio}"], model=None, timeout_seconds=5)

            with self.assertRaises(RuntimeError) as raised:
                engine.transcribe(audio)

            message = str(raised.exception)
            self.assertIn("model exploded", message)
            self.assertIn(str(audio), message)
            self.assertIn(str(command_script), message)
            self.assertIn("exit code 7", message)

    def test_whisper_metal_failure_retries_with_cpu_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            audio.write_bytes(b"placeholder")
            command_script = root / "whisper-cli"
            command_script.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "output = pathlib.Path(sys.argv[sys.argv.index('-of') + 1]).with_suffix('.txt')\n"
                "if '-ng' not in sys.argv:\n"
                "    output.write_text('partial gpu transcript', encoding='utf-8')\n"
                "    print('ggml_metal_buffer_init: error: failed to allocate buffer', file=sys.stderr)\n"
                "    raise SystemExit(2)\n"
                "output.write_text('CPU fallback transcript', encoding='utf-8')\n",
                encoding="utf-8",
            )
            command_script.chmod(0o755)
            engine = CommandEngine(
                [
                    str(command_script),
                    "-m",
                    "{model}",
                    "-f",
                    "{audio}",
                    "-otxt",
                    "-of",
                    "{output_without_suffix}",
                ],
                model="model.bin",
                timeout_seconds=5,
            )

            transcript = engine.transcribe(audio)

            self.assertEqual(transcript.text, "CPU fallback transcript")

    def test_timeout_error_includes_audio_command_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            audio.write_bytes(b"placeholder")
            command_script = root / "slow.py"
            command_script.write_text(
                "import time\n"
                "time.sleep(1)\n",
                encoding="utf-8",
            )
            engine = CommandEngine([sys.executable, str(command_script), "{audio}"], model=None, timeout_seconds=0.01)

            with self.assertRaises(RuntimeError) as raised:
                engine.transcribe(audio)

            message = str(raised.exception)
            self.assertIn("timed out after 0.01s", message)
            self.assertIn(str(audio), message)
            self.assertIn(str(command_script), message)


if __name__ == "__main__":
    unittest.main()
