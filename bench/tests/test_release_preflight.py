import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.release_preflight import (
    Check,
    app_doctor_check,
    collect_checks,
    collect_input_checks,
    funasr_dependency_check,
    next_actions,
    print_checks,
    whisper_binary_check,
    whisper_model_check,
)


class ReleasePreflightTests(unittest.TestCase):
    def write_fake_doctor(self, root: Path, output: str) -> Path:
        doctor = root / "app/SwitchType/.build/debug/SwitchTypeDoctor"
        doctor.parent.mkdir(parents=True)
        doctor.write_text(
            "#!/bin/sh\n"
            "cat <<'JSON'\n"
            f"{output}\n"
            "JSON\n",
            encoding="utf-8",
        )
        doctor.chmod(0o755)
        return doctor

    def test_collect_checks_reports_missing_release_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"Codex"}\n',
                encoding="utf-8",
            )

            checks = collect_checks(root, environment={"SWITCHTYPE_FUNASR_PYTHON": "/missing/python"})
            by_name = {check.name: check for check in checks}

            self.assertFalse(by_name["real audio samples"].ok)
            self.assertIn("1 missing", by_name["real audio samples"].detail)
            self.assertFalse(by_name["FunASR dependency"].ok)
            self.assertFalse(by_name["app doctor"].ok)
            self.assertFalse(by_name["demo GIF"].ok)
            self.assertFalse(by_name["real benchmark report"].ok)

    def test_app_doctor_check_accepts_granted_permissions_and_matched_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_fake_doctor(
                root,
                '{"permissions":{"microphone":"granted","accessibility":"granted",'
                '"input_device_name":"DJI MIC MINI","expected_input_device_name":"DJI MIC MINI",'
                '"expected_input_device_status":"matched","summary":"ok"},'
                '"asr":{"whisper_bin_status":"ok","whisper_model_status":"ok"},'
                '"hotwords":{"status":"ok"}}',
            )

            check = app_doctor_check(root, environment={})

        self.assertTrue(check.ok)
        self.assertIn("permissions granted", check.detail)

    def test_app_doctor_check_rejects_denied_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_fake_doctor(
                root,
                '{"permissions":{"microphone":"denied","accessibility":"denied",'
                '"input_device_name":null,"expected_input_device_name":"DJI MIC MINI",'
                '"expected_input_device_status":"unavailable","summary":"permissions denied"},'
                '"asr":{"whisper_bin_status":"ok","whisper_model_status":"ok"},'
                '"hotwords":{"status":"ok"}}',
            )

            check = app_doctor_check(root, environment={})

        self.assertFalse(check.ok)
        self.assertIn("microphone denied", check.detail)
        self.assertIn("accessibility denied", check.detail)
        self.assertIn("expected input unavailable", check.detail)

    def test_collect_input_checks_excludes_generated_release_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"Codex"}\n',
                encoding="utf-8",
            )

            checks = collect_input_checks(root, environment={"SWITCHTYPE_FUNASR_PYTHON": "/missing/python"})
            names = [check.name for check in checks]

            self.assertIn("real audio samples", names)
            self.assertIn("demo GIF", names)
            self.assertNotIn("real benchmark report", names)
            self.assertNotIn("verification log", names)

    def test_collect_checks_reports_stale_readme_benchmark_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"Codex"}\n',
                encoding="utf-8",
            )
            readme = root / "README.md"
            readme.write_text(
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->\n"
                "Real ASR benchmark results have not been recorded yet.\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True)
            report.write_text(
                "## Engine Summary\n\n"
                "| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |\n"
                "|---|---:|---:|---:|---:|---:|\n"
                "| whisper_cpp | 1 | 400.0 | 0.100 | 0.200 | 0.950 |\n\n"
                "## Sample Results\n",
                encoding="utf-8",
            )

            checks = collect_checks(root, environment={"SWITCHTYPE_FUNASR_PYTHON": "/missing/python"})
            by_name = {check.name: check for check in checks}

            self.assertFalse(by_name["README benchmark summary"].ok)
            self.assertIn("not updated", by_name["README benchmark summary"].detail)

    def test_print_checks_returns_failure_count(self):
        with redirect_stdout(StringIO()):
            failures = print_checks(
                [
                    Check("ready", True, "ok"),
                    Check("missing", False, "not found"),
                ]
            )

        self.assertEqual(failures, 1)

    def test_next_actions_suggest_failed_release_steps_without_duplicates(self):
        actions = next_actions(
            [
                Check("whisper.cpp binary", False, "missing"),
                Check("whisper.cpp model", False, "missing"),
                Check("real audio samples", False, "30 missing"),
                Check("demo GIF", False, "missing"),
                Check("verification log", False, "missing manual fields"),
                Check("ready", True, "ok"),
            ]
        )

        self.assertEqual(
            actions,
            [
                "./scripts/bootstrap_whisper_cpp.sh large-v3-turbo",
                'make record-session EXPECT_DEVICE_NAME="<device name>", then follow the printed commands',
                "./scripts/record_demo.sh",
                "make release-evidence-template, fill actual manual evidence, then run make release-evidence ARGS='...'",
            ],
        )

    def test_funasr_dependency_check_uses_configured_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python"
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            python.chmod(0o755)

            check = funasr_dependency_check({"SWITCHTYPE_FUNASR_PYTHON": str(python)})

        self.assertTrue(check.ok)
        self.assertIn(str(python), check.detail)

    def test_funasr_dependency_check_uses_project_venv_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python = root / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            python.chmod(0o755)

            check = funasr_dependency_check({}, root=root)

        self.assertTrue(check.ok)
        self.assertIn(str(python), check.detail)

    def test_funasr_dependency_check_empty_environment_ignores_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python = root / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            python.chmod(0o755)
            previous = os.environ.get("SWITCHTYPE_FUNASR_PYTHON")
            os.environ["SWITCHTYPE_FUNASR_PYTHON"] = "/process/env/python"
            try:
                check = funasr_dependency_check({}, root=root)
            finally:
                if previous is None:
                    os.environ.pop("SWITCHTYPE_FUNASR_PYTHON", None)
                else:
                    os.environ["SWITCHTYPE_FUNASR_PYTHON"] = previous

        self.assertTrue(check.ok)
        self.assertIn(str(python), check.detail)

    def test_whisper_checks_use_configured_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            whisper_bin = root / "tools/whisper-cli"
            whisper_bin.parent.mkdir(parents=True)
            whisper_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            whisper_bin.chmod(0o755)
            model = root / "models/custom-whisper.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model")
            environment = {
                "SWITCHTYPE_WHISPER_BIN": str(whisper_bin),
                "SWITCHTYPE_WHISPER_MODEL": str(model),
            }

            binary_check = whisper_binary_check(root, environment=environment)
            model_check = whisper_model_check(root, environment=environment)

        self.assertTrue(binary_check.ok)
        self.assertIn(str(whisper_bin), binary_check.detail)
        self.assertTrue(model_check.ok)
        self.assertIn(str(model), model_check.detail)

    def test_whisper_checks_use_asr_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            whisper_bin = root / "tools/whisper-cli"
            whisper_bin.parent.mkdir(parents=True)
            whisper_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            whisper_bin.chmod(0o755)
            model = root / "models/configured-whisper.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model")
            asr_config = root / "asr.json"
            asr_config.write_text(
                "{\n"
                f'  "whisper_bin": "{whisper_bin}",\n'
                f'  "whisper_model": "{model}",\n'
                '  "whisper_no_gpu": true\n'
                "}\n",
                encoding="utf-8",
            )
            environment = {"SWITCHTYPE_ASR_CONFIG": str(asr_config)}

            binary_check = whisper_binary_check(root, environment=environment)
            model_check = whisper_model_check(root, environment=environment)

        self.assertTrue(binary_check.ok)
        self.assertIn(str(whisper_bin), binary_check.detail)
        self.assertTrue(model_check.ok)
        self.assertIn(str(model), model_check.detail)

    def test_whisper_environment_overrides_asr_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configured_bin = root / "tools/configured-whisper-cli"
            configured_bin.parent.mkdir(parents=True)
            configured_bin.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            configured_bin.chmod(0o755)
            configured_model = root / "models/configured.bin"
            configured_model.parent.mkdir(parents=True)
            configured_model.write_bytes(b"configured")
            override_bin = root / "tools/override-whisper-cli"
            override_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            override_bin.chmod(0o755)
            override_model = root / "models/override.bin"
            override_model.write_bytes(b"override")
            asr_config = root / "asr.json"
            asr_config.write_text(
                "{\n"
                f'  "whisper_bin": "{configured_bin}",\n'
                f'  "whisper_model": "{configured_model}"\n'
                "}\n",
                encoding="utf-8",
            )
            environment = {
                "SWITCHTYPE_ASR_CONFIG": str(asr_config),
                "SWITCHTYPE_WHISPER_BIN": str(override_bin),
                "SWITCHTYPE_WHISPER_MODEL": str(override_model),
            }

            binary_check = whisper_binary_check(root, environment=environment)
            model_check = whisper_model_check(root, environment=environment)

        self.assertTrue(binary_check.ok)
        self.assertIn(str(override_bin), binary_check.detail)
        self.assertTrue(model_check.ok)
        self.assertIn(str(override_model), model_check.detail)


if __name__ == "__main__":
    unittest.main()
