import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bench.scripts.sample_status import SampleStatus


class RecordingSessionTests(unittest.TestCase):
    def status(self, sample_id: str, state: str) -> SampleStatus:
        return SampleStatus(
            id=sample_id,
            audio=f"bench/samples/audio/{sample_id}.wav",
            state=state,
            exists=state != "missing",
            bytes=32000 if state == "valid" else 0,
            duration_seconds=1.0 if state == "valid" else None,
            reference="Codex PR",
        )

    def test_zero_valid_samples_guides_first_preview_recording(self):
        from bench.scripts.recording_session import build_recording_plan

        plan = build_recording_plan(
            statuses=[self.status("sample-001", "missing"), self.status("sample-002", "missing")],
            expected_count=2,
            device_name="DJI MIC MINI",
        )

        self.assertEqual(plan.valid_count, 0)
        self.assertEqual(plan.remaining_count, 2)
        self.assertIn('EXPECT_DEVICE_NAME="DJI MIC MINI" make record-devices', plan.commands)
        self.assertIn(
            'SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" SWITCHTYPE_WHISPER_NO_GPU=1 make record-preview',
            plan.commands,
        )
        self.assertNotIn("make real-benchmark-preview", plan.commands)

    def test_partial_recordings_guides_preview_benchmark_and_next_batch(self):
        from bench.scripts.recording_session import build_recording_plan

        plan = build_recording_plan(
            statuses=[
                self.status("sample-001", "valid"),
                self.status("sample-002", "too_short"),
                self.status("sample-003", "missing"),
            ],
            expected_count=3,
            device_name=None,
        )

        self.assertEqual(plan.valid_count, 1)
        self.assertEqual(plan.remaining_count, 2)
        self.assertEqual(plan.invalid_counts["too_short"], 1)
        self.assertIn("make real-benchmark-preview", plan.commands)
        self.assertIn('SWITCHTYPE_FFMPEG_INPUT_NAME="<device name>" LIMIT=5 make record-next', plan.commands)

    def test_raw_ffmpeg_input_takes_precedence_over_device_name(self):
        from bench.scripts.recording_session import build_recording_plan

        plan = build_recording_plan(
            statuses=[self.status("sample-001", "valid"), self.status("sample-002", "missing")],
            expected_count=2,
            device_name="DJI MIC MINI",
            ffmpeg_input=":2",
        )

        self.assertIn("SWITCHTYPE_FFMPEG_INPUT=:2 LIMIT=5 make record-next", plan.commands)
        self.assertNotIn('SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" LIMIT=5 make record-next', plan.commands)

    def test_complete_recordings_guides_final_benchmark(self):
        from bench.scripts.recording_session import build_recording_plan

        plan = build_recording_plan(
            statuses=[self.status(f"sample-{index:03d}", "valid") for index in range(1, 31)],
            expected_count=30,
            device_name="DJI MIC MINI",
        )

        self.assertEqual(plan.valid_count, 30)
        self.assertEqual(plan.remaining_count, 0)
        self.assertIn(
            "SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall "
            "SWITCHTYPE_SENSEVOICE_HUB=hf "
            "SWITCHTYPE_SENSEVOICE_VAD_MODEL=none "
            "scripts/run_real_benchmark.sh",
            plan.commands,
        )
        self.assertIn("python3 scripts/release_preflight.py", plan.commands)

    def test_cli_prints_plan_for_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            manifest.write_text(
                '{"id":"sample-001","audio":"missing.wav","reference":"Codex PR","terms":["Codex","PR"]}\n',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/recording_session.py",
                    "--manifest",
                    str(manifest),
                    "--expected-count",
                    "1",
                    "--device-name",
                    "DJI MIC MINI",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Valid recordings: 0/1", completed.stdout)
            self.assertIn('SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI"', completed.stdout)

    def test_makefile_exposes_record_session_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("record-session", makefile)
        self.assertIn("bench/scripts/recording_session.py", makefile)
        self.assertIn('$${EXPECT_DEVICE_NAME:+--device-name "$$EXPECT_DEVICE_NAME"}', makefile)
        self.assertIn('$${SWITCHTYPE_FFMPEG_INPUT:+--ffmpeg-input "$$SWITCHTYPE_FFMPEG_INPUT"}', makefile)


if __name__ == "__main__":
    unittest.main()
