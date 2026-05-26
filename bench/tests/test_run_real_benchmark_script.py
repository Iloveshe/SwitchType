import unittest
from pathlib import Path


SCRIPT = Path("scripts/run_real_benchmark.sh")
PREVIEW_SCRIPT = Path("scripts/run_recorded_benchmark_preview.sh")
MAKEFILE = Path("Makefile")


class RunRealBenchmarkScriptTests(unittest.TestCase):
    def test_enables_sensevoice_by_default_for_real_ab_benchmark(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('ENABLE_SENSEVOICE="${SWITCHTYPE_ENABLE_SENSEVOICE:-1}"', script)
        self.assertIn('if [ "$ENABLE_SENSEVOICE" = "1" ]; then', script)
        self.assertIn('CREATE_CONFIG_ARGS+=(--enable-sensevoice)', script)

    def test_prefers_project_funasr_venv_by_default(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('if [ -n "${SWITCHTYPE_FUNASR_PYTHON:-}" ]; then', script)
        self.assertIn('FUNASR_PYTHON="$SWITCHTYPE_FUNASR_PYTHON"', script)
        self.assertIn('elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then', script)
        self.assertIn('FUNASR_PYTHON="$ROOT_DIR/.venv/bin/python"', script)
        self.assertIn('FUNASR_PYTHON="python3"', script)

    def test_forwards_sensevoice_fallback_environment_to_config_generator(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('SENSEVOICE_MODEL="${SWITCHTYPE_SENSEVOICE_MODEL:-}"', script)
        self.assertIn('SENSEVOICE_HUB="${SWITCHTYPE_SENSEVOICE_HUB:-}"', script)
        self.assertIn('SENSEVOICE_VAD_MODEL="${SWITCHTYPE_SENSEVOICE_VAD_MODEL:-}"', script)
        self.assertIn('CREATE_CONFIG_ARGS+=(--sensevoice-model "$SENSEVOICE_MODEL")', script)
        self.assertIn('CREATE_CONFIG_ARGS+=(--sensevoice-hub "$SENSEVOICE_HUB")', script)
        self.assertIn('CREATE_CONFIG_ARGS+=(--sensevoice-vad-model "$SENSEVOICE_VAD_MODEL")', script)

    def test_resolves_whisper_paths_from_shared_asr_config(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('scripts/resolve_asr_config.py" --key whisper_bin', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_model', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_no_gpu', script)
        self.assertIn('--whisper-bin "$WHISPER_BIN"', script)
        self.assertIn('--whisper-model "$WHISPER_MODEL"', script)

    def test_resolves_hotwords_from_personal_config_by_default(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('scripts/resolve_hotwords_config.py"', script)
        self.assertIn('--hotwords "$HOTWORDS"', script)

    def test_can_run_partial_preview_without_updating_readme(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('EXPECTED_COUNT="${SWITCHTYPE_REAL_EXPECTED_COUNT:-30}"', script)
        self.assertIn('ALLOW_PARTIAL="${SWITCHTYPE_REAL_ALLOW_PARTIAL:-0}"', script)
        self.assertIn('UPDATE_README="${SWITCHTYPE_REAL_UPDATE_README:-1}"', script)
        self.assertIn('if [ "$ALLOW_PARTIAL" = "1" ]; then', script)
        self.assertIn('--expected-count "$EXPECTED_COUNT"', script)
        self.assertIn('if [ "$UPDATE_README" = "1" ]; then', script)

    def test_makefile_exposes_recorded_benchmark_preview(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        preview_script = PREVIEW_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("real-benchmark-preview", makefile)
        self.assertIn("./scripts/run_recorded_benchmark_preview.sh", makefile)
        self.assertIn("--valid-manifest-output", preview_script)
        self.assertIn("manifest.recorded-preview.jsonl", preview_script)
        self.assertIn("real-asr-preview.md", preview_script)
        self.assertIn("SWITCHTYPE_REAL_ALLOW_PARTIAL=1", preview_script)
        self.assertIn("SWITCHTYPE_REAL_UPDATE_README=0", preview_script)


if __name__ == "__main__":
    unittest.main()
