import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.run_release_evidence import (
    build_release_evidence_template,
    command_plan,
    real_benchmark_command,
    real_benchmark_environment,
    update_log_args,
)


class RunReleaseEvidenceTests(unittest.TestCase):
    def test_make_release_evidence_target_forwards_args(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("python3 scripts/run_release_evidence.py $(ARGS)", makefile)

    def test_make_release_evidence_template_target_prints_template(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("release-evidence-template:", makefile)
        self.assertIn("python3 scripts/run_release_evidence.py --template", makefile)
        self.assertIn('$${APP_DATE:+--app-date "$$APP_DATE"}', makefile)

    def test_build_release_evidence_template_uses_safe_defaults_and_placeholders(self):
        template = build_release_evidence_template(app_date="2026-05-22")

        self.assertIn("make release-evidence ARGS='--dry-run \\", template)
        self.assertIn("--asr-config ~/.switchtype/asr.json", template)
        self.assertIn("--hotwords-config ~/.switchtype/hotwords.json", template)
        self.assertIn("--funasr-python .venv/bin/python", template)
        self.assertIn("--sensevoice-model FunAudioLLM/SenseVoiceSmall", template)
        self.assertIn("--app-date 2026-05-22", template)
        self.assertIn("--launch-method dist/SwitchType.app", template)
        self.assertIn("--microphone-permission granted", template)
        self.assertIn("--accessibility-permission granted", template)
        self.assertIn('--spoken-sentence "帮我看一下 Codex 的 PR issue 有没有过 CI"', template)
        self.assertIn('--pasted-output "PASTE_REAL_OUTPUT_HERE"', template)
        self.assertIn('--recording-tool "Kap or QuickTime"', template)
        self.assertIn("--real-asr-demo yes", template)
        self.assertIn("After the dry run looks right, remove `--dry-run`", template)

    def test_command_plan_runs_release_evidence_in_order(self):
        plan = command_plan(include_smoke=True, update_log_arguments=["--app-date", "2026-05-21"])

        self.assertEqual(plan[0], ["make", "release-inputs-preflight"])
        self.assertEqual(plan[1], ["make", "sample-status"])
        self.assertEqual(
            plan[2],
            [
                "python3",
                "bench/scripts/validate_samples.py",
                "--manifest",
                "bench/samples/manifest.30-template.jsonl",
                "--expected-count",
                "30",
                "--require-audio",
            ],
        )
        self.assertIn(["make", "asr-smoke"], plan)
        self.assertIn(["make", "app-asr-smoke"], plan)
        self.assertIn(["make", "real-benchmark"], plan)
        self.assertIn(["make", "package"], plan)
        self.assertEqual(
            plan[-5],
            [
                "python3",
                "scripts/update_verification_log.py",
                "--benchmark-command",
                "make real-benchmark",
                "--app-date",
                "2026-05-21",
            ],
        )
        self.assertEqual(plan[-4], ["python3", "scripts/check_release_ready.py", "--strict", "--ignore-final-result"])
        self.assertEqual(
            plan[-3],
            [
                "python3",
                "scripts/update_verification_log.py",
                "--benchmark-command",
                "make real-benchmark",
                "--app-date",
                "2026-05-21",
                "--final-result",
                "strict readiness passed",
            ],
        )
        self.assertEqual(plan[-2], ["make", "release-preflight"])
        self.assertEqual(plan[-1], ["python3", "scripts/check_release_ready.py", "--strict"])

    def test_command_plan_can_skip_smoke_steps(self):
        plan = command_plan(include_smoke=False, update_log_arguments=[])

        self.assertNotIn(["make", "asr-smoke"], plan)
        self.assertNotIn(["make", "app-asr-smoke"], plan)

    def test_real_benchmark_command_can_include_sensevoice_environment(self):
        command = real_benchmark_command(
            {
                "SWITCHTYPE_ENABLE_SENSEVOICE": "1",
                "SWITCHTYPE_FUNASR_PYTHON": ".venv/bin/python",
                "SWITCHTYPE_SENSEVOICE_MODEL": "FunAudioLLM/SenseVoiceSmall",
                "SWITCHTYPE_SENSEVOICE_HUB": "hf",
                "SWITCHTYPE_SENSEVOICE_VAD_MODEL": "none",
            }
        )

        self.assertEqual(
            command,
            [
                "env",
                "SWITCHTYPE_ENABLE_SENSEVOICE=1",
                "SWITCHTYPE_FUNASR_PYTHON=.venv/bin/python",
                "SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall",
                "SWITCHTYPE_SENSEVOICE_HUB=hf",
                "SWITCHTYPE_SENSEVOICE_VAD_MODEL=none",
                "make",
                "real-benchmark",
            ],
        )

    def test_command_plan_passes_asr_environment_to_release_input_preflight(self):
        environment = {
            "SWITCHTYPE_ENABLE_SENSEVOICE": "1",
            "SWITCHTYPE_FUNASR_PYTHON": ".venv/bin/python",
        }

        plan = command_plan(
            include_smoke=False,
            update_log_arguments=[],
            real_benchmark_environment=environment,
        )

        self.assertEqual(
            plan[0],
            [
                "env",
                "SWITCHTYPE_ENABLE_SENSEVOICE=1",
                "SWITCHTYPE_FUNASR_PYTHON=.venv/bin/python",
                "make",
                "release-inputs-preflight",
            ],
        )

    def test_command_plan_records_exact_benchmark_command_in_log_update(self):
        environment = {
            "SWITCHTYPE_WHISPER_BIN": "/opt/whisper/whisper-cli",
            "SWITCHTYPE_WHISPER_MODEL": "/models/ggml.bin",
        }

        plan = command_plan(
            include_smoke=False,
            update_log_arguments=[],
            real_benchmark_environment=environment,
        )

        self.assertEqual(
            plan[-5],
            [
                "python3",
                "scripts/update_verification_log.py",
                "--benchmark-command",
                "env SWITCHTYPE_WHISPER_BIN=/opt/whisper/whisper-cli SWITCHTYPE_WHISPER_MODEL=/models/ggml.bin make real-benchmark",
            ],
        )

    def test_command_plan_passes_asr_environment_to_smoke_steps(self):
        environment = {
            "SWITCHTYPE_WHISPER_BIN": "/opt/whisper/whisper-cli",
            "SWITCHTYPE_WHISPER_MODEL": "/models/ggml.bin",
            "SWITCHTYPE_WHISPER_NO_GPU": "1",
        }

        plan = command_plan(
            include_smoke=True,
            update_log_arguments=[],
            real_benchmark_environment=environment,
        )

        self.assertIn(
            [
                "env",
                "SWITCHTYPE_WHISPER_BIN=/opt/whisper/whisper-cli",
                "SWITCHTYPE_WHISPER_MODEL=/models/ggml.bin",
                "SWITCHTYPE_WHISPER_NO_GPU=1",
                "make",
                "asr-smoke",
            ],
            plan,
        )
        self.assertIn(
            [
                "env",
                "SWITCHTYPE_WHISPER_BIN=/opt/whisper/whisper-cli",
                "SWITCHTYPE_WHISPER_MODEL=/models/ggml.bin",
                "SWITCHTYPE_WHISPER_NO_GPU=1",
                "make",
                "app-asr-smoke",
            ],
            plan,
        )

    def test_real_benchmark_environment_includes_only_provided_values(self):
        environment = real_benchmark_environment(
            SimpleNamespace(
                enable_sensevoice=True,
                whisper_bin="",
                whisper_model="",
                whisper_no_gpu=False,
                funasr_python=".venv/bin/python",
                sensevoice_model="FunAudioLLM/SenseVoiceSmall",
                sensevoice_hub="hf",
                sensevoice_vad_model="none",
            )
        )

        self.assertEqual(
            environment,
            {
                "SWITCHTYPE_ENABLE_SENSEVOICE": "1",
                "SWITCHTYPE_FUNASR_PYTHON": ".venv/bin/python",
                "SWITCHTYPE_SENSEVOICE_MODEL": "FunAudioLLM/SenseVoiceSmall",
                "SWITCHTYPE_SENSEVOICE_HUB": "hf",
                "SWITCHTYPE_SENSEVOICE_VAD_MODEL": "none",
            },
        )

    def test_real_benchmark_environment_includes_whisper_overrides(self):
        environment = real_benchmark_environment(
            SimpleNamespace(
                asr_config="",
                enable_sensevoice=False,
                whisper_bin="/opt/whisper/whisper-cli",
                whisper_model="/models/ggml.bin",
                whisper_no_gpu=True,
                funasr_python="",
                sensevoice_model="",
                sensevoice_hub="",
                sensevoice_vad_model="",
            )
        )

        self.assertEqual(
            environment,
            {
                "SWITCHTYPE_WHISPER_BIN": "/opt/whisper/whisper-cli",
                "SWITCHTYPE_WHISPER_MODEL": "/models/ggml.bin",
                "SWITCHTYPE_WHISPER_NO_GPU": "1",
            },
        )

    def test_real_benchmark_environment_includes_asr_config(self):
        environment = real_benchmark_environment(
            SimpleNamespace(
                asr_config="/Users/me/.switchtype/asr.json",
                hotwords_config="",
                enable_sensevoice=False,
                whisper_bin="",
                whisper_model="",
                whisper_no_gpu=False,
                funasr_python="",
                sensevoice_model="",
                sensevoice_hub="",
                sensevoice_vad_model="",
            )
        )

        self.assertEqual(environment, {"SWITCHTYPE_ASR_CONFIG": "/Users/me/.switchtype/asr.json"})

    def test_real_benchmark_environment_includes_hotwords_override(self):
        environment = real_benchmark_environment(
            SimpleNamespace(
                asr_config="",
                hotwords_config="/Users/me/.switchtype/hotwords.json",
                enable_sensevoice=False,
                whisper_bin="",
                whisper_model="",
                whisper_no_gpu=False,
                funasr_python="",
                sensevoice_model="",
                sensevoice_hub="",
                sensevoice_vad_model="",
            )
        )

        self.assertEqual(environment, {"SWITCHTYPE_HOTWORDS_CONFIG": "/Users/me/.switchtype/hotwords.json"})

    def test_update_log_args_include_only_provided_manual_fields(self):
        args = update_log_args(
            {
                "app_date": "2026-05-21",
                "launch_method": "",
                "real_asr_demo": "yes",
            },
            require_complete=False,
        )

        self.assertEqual(args, ["--app-date", "2026-05-21", "--real-asr-demo", "yes"])

    def test_update_log_args_rejects_missing_required_manual_fields(self):
        with self.assertRaises(ValueError) as context:
            update_log_args({"app_date": "2026-05-21"})

        self.assertIn("--launch-method", str(context.exception))
        self.assertNotIn("--final-result", str(context.exception))

    def test_update_log_args_does_not_require_final_result(self):
        args = update_log_args(
            {
                "app_date": "2026-05-21",
                "launch_method": "dist/SwitchType.app",
                "microphone_permission": "granted",
                "accessibility_permission": "granted",
                "hotword_config_path": "~/.switchtype/hotwords.json",
                "input_app": "TextEdit",
                "spoken_sentence": "Codex PR",
                "pasted_output": "Codex PR",
                "hotwords_preserved": "yes",
                "short_recording_rejected": "yes",
                "hotkey_consumed": "yes",
                "recording_tool": "Kap",
                "gif_duration": "8s",
                "real_asr_demo": "yes",
            }
        )

        self.assertNotIn("--final-result", args)

    def test_update_log_args_requires_short_recording_rejected(self):
        with self.assertRaises(ValueError) as context:
            update_log_args(
                {
                    "app_date": "2026-05-21",
                    "launch_method": "dist/SwitchType.app",
                    "microphone_permission": "granted",
                    "accessibility_permission": "granted",
                    "hotword_config_path": "~/.switchtype/hotwords.json",
                    "input_app": "TextEdit",
                    "spoken_sentence": "Codex PR",
                    "pasted_output": "Codex PR",
                    "hotwords_preserved": "yes",
                    "recording_tool": "Kap",
                    "gif_duration": "8s",
                    "real_asr_demo": "yes",
                }
            )

        self.assertIn("--short-recording-rejected", str(context.exception))

    def test_update_log_args_requires_hotkey_consumed(self):
        with self.assertRaises(ValueError) as context:
            update_log_args(
                {
                    "app_date": "2026-05-21",
                    "launch_method": "dist/SwitchType.app",
                    "microphone_permission": "granted",
                    "accessibility_permission": "granted",
                    "hotword_config_path": "~/.switchtype/hotwords.json",
                    "input_app": "TextEdit",
                    "spoken_sentence": "Codex PR",
                    "pasted_output": "Codex PR",
                    "hotwords_preserved": "yes",
                    "short_recording_rejected": "yes",
                    "recording_tool": "Kap",
                    "gif_duration": "8s",
                    "real_asr_demo": "yes",
                }
            )

        self.assertIn("--hotkey-consumed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
