import unittest
from pathlib import Path


SCRIPT = Path("scripts/run_public_benchmark.sh")
MAKEFILE = Path("Makefile")


class RunPublicBenchmarkScriptTests(unittest.TestCase):
    def test_makefile_exposes_public_asr_target(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")

        self.assertIn("public-asr:", makefile)
        self.assertIn("./scripts/run_public_benchmark.sh", makefile)

    def test_script_prepares_ascend_and_validates_public_audio(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('LIMIT="${SWITCHTYPE_PUBLIC_LIMIT:-50}"', script)
        self.assertIn('SPLIT="${SWITCHTYPE_PUBLIC_SPLIT:-test}"', script)
        self.assertIn('PUBLIC_PYTHON="$ROOT_DIR/.venv/bin/python"', script)
        self.assertIn("bench/scripts/prepare_ascend_public_samples.py", script)
        self.assertIn('--split "$SPLIT"', script)
        self.assertIn('--limit "$LIMIT"', script)
        self.assertIn('--expected-count "$EXPECTED_COUNT"', script)
        self.assertIn("--require-audio", script)

    def test_script_creates_long_timeout_real_engine_config(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('TIMEOUT_SECONDS="${SWITCHTYPE_PUBLIC_TIMEOUT_SECONDS:-900}"', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_bin', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_model', script)
        self.assertIn('--timeout-seconds "$TIMEOUT_SECONDS"', script)
        self.assertIn('CREATE_CONFIG_ARGS+=(--enable-sensevoice)', script)
        self.assertIn('--sensevoice-python "$FUNASR_PYTHON"', script)

    def test_script_runs_public_benchmark_without_updating_release_summary(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('REPORT="${SWITCHTYPE_PUBLIC_REPORT:-$ROOT_DIR/bench/reports/public-asr.md}"', script)
        self.assertIn("bench/scripts/run_benchmark.py", script)
        self.assertIn('--manifest "$MANIFEST"', script)
        self.assertIn('--report "$REPORT"', script)
        self.assertNotIn("update_readme_benchmark.py", script)


if __name__ == "__main__":
    unittest.main()
