import unittest
from pathlib import Path


SCRIPT = Path("scripts/record_demo.sh")


class RecordDemoScriptTests(unittest.TestCase):
    def test_demo_script_uses_shared_asr_config_and_release_evidence_flow(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("~/.switchtype/asr.json", script)
        self.assertIn("make release-evidence ARGS=", script)
        self.assertIn("python3 scripts/check_release_ready.py --strict", script)

    def test_demo_script_rejects_debug_transcript_for_final_gif(self):
        script = SCRIPT.read_text(encoding="utf-8").lower()

        self.assertIn("do not use debug transcript", script)
        self.assertIn("real asr", script)

    def test_demo_script_documents_metal_fallback(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("SWITCHTYPE_WHISPER_NO_GPU=1 make asr-smoke", script)
        self.assertIn('"whisper_no_gpu": true', script)


if __name__ == "__main__":
    unittest.main()
