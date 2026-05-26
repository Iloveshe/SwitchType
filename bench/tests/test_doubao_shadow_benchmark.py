import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from bench.scripts.run_doubao_shadow_benchmark import (
    benchmark_environment,
    readiness_error,
    run_shadow_benchmark,
)


def payload(
    *,
    captured: int = 1,
    references: int = 1,
    needs_reconciliation: int = 0,
    manifest_samples: int = 1,
    valid_audio: int = 1,
    audio_total: int = 1,
    next_command: str = "make doubao-shadow-benchmark",
):
    return {
        "running": False,
        "pid": None,
        "segments": {
            "captured": captured,
            "references": references,
            "needs_reconciliation": needs_reconciliation,
            "focused_text": {"captured": references, "unmatched": needs_reconciliation},
        },
        "benchmark": {
            "manifest": "bench/samples/doubao-shadow/manifest.jsonl",
            "manifest_samples": manifest_samples,
            "valid_audio": valid_audio,
            "audio_total": audio_total,
            "missing_audio": 0,
            "too_short": 0,
            "unreadable": 0,
            "wrong_format": 0,
            "silent": 0,
        },
        "next": next_command,
    }


class DoubaoShadowBenchmarkTests(unittest.TestCase):
    def test_readiness_error_requires_shadow_start_when_no_segments_exist(self):
        error = readiness_error(
            payload(captured=0, references=0, manifest_samples=0, valid_audio=0, audio_total=0, next_command="make doubao-shadow-start")
        )

        self.assertIn("No Doubao shadow audio has been captured", error)
        self.assertIn("make doubao-shadow-start-auto", error)

    def test_readiness_error_requires_reconcile_when_manifest_is_not_ready(self):
        error = readiness_error(
            payload(
                captured=2,
                references=1,
                needs_reconciliation=1,
                manifest_samples=0,
                valid_audio=0,
                audio_total=0,
                next_command="make doubao-shadow-reconcile",
            )
        )

        self.assertIn("not benchmark-ready", error)
        self.assertIn("make doubao-shadow-reconcile", error)

    def test_readiness_error_requires_more_valid_shadow_audio(self):
        error = readiness_error(
            payload(
                captured=1,
                references=1,
                needs_reconciliation=0,
                manifest_samples=1,
                valid_audio=0,
                audio_total=1,
                next_command="make doubao-shadow-start",
            )
        )

        self.assertIn("No valid Doubao shadow audio", error)
        self.assertIn("make doubao-shadow-start-auto", error)

    def test_readiness_error_accepts_ready_status(self):
        self.assertIsNone(readiness_error(payload()))

    def test_readiness_error_accepts_partial_manifest_with_valid_audio(self):
        self.assertIsNone(
            readiness_error(
                payload(
                    captured=34,
                    references=1,
                    needs_reconciliation=33,
                    manifest_samples=1,
                    valid_audio=1,
                    audio_total=1,
                    next_command="make doubao-shadow-reconcile",
                )
            )
        )

    def test_benchmark_environment_points_preview_runner_at_shadow_files(self):
        env = benchmark_environment(
            base_env={"KEEP": "1"},
            manifest=Path("bench/samples/doubao-shadow/manifest.jsonl"),
            preview_manifest=Path("bench/samples/doubao-shadow/manifest.valid.jsonl"),
            report=Path("bench/reports/doubao-shadow-preview.md"),
        )

        self.assertEqual(env["KEEP"], "1")
        self.assertEqual(env["SWITCHTYPE_REAL_SOURCE_MANIFEST"], "bench/samples/doubao-shadow/manifest.jsonl")
        self.assertEqual(env["SWITCHTYPE_REAL_PREVIEW_MANIFEST"], "bench/samples/doubao-shadow/manifest.valid.jsonl")
        self.assertEqual(env["SWITCHTYPE_REAL_PREVIEW_REPORT"], "bench/reports/doubao-shadow-preview.md")
        self.assertEqual(env["SWITCHTYPE_ENABLE_SENSEVOICE"], "0")

    def test_benchmark_environment_preserves_explicit_sensevoice_choice(self):
        env = benchmark_environment(
            base_env={"SWITCHTYPE_ENABLE_SENSEVOICE": "1"},
            manifest=Path("manifest.jsonl"),
            preview_manifest=Path("manifest.valid.jsonl"),
            report=Path("report.md"),
        )

        self.assertEqual(env["SWITCHTYPE_ENABLE_SENSEVOICE"], "1")

    def test_run_shadow_benchmark_refuses_when_status_is_not_ready(self):
        with patch("bench.scripts.run_doubao_shadow_benchmark.status_payload") as status:
            with patch("bench.scripts.run_doubao_shadow_benchmark.subprocess.run") as subprocess_run:
                status.return_value = payload(
                    captured=0,
                    references=0,
                    manifest_samples=0,
                    valid_audio=0,
                    audio_total=0,
                    next_command="make doubao-shadow-start-auto",
                )

                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    code = run_shadow_benchmark(
                        pid_file=Path("shadow.pid"),
                        segments=Path("segments.jsonl"),
                        manifest=Path("manifest.jsonl"),
                        preview_manifest=Path("manifest.valid.jsonl"),
                        report=Path("report.md"),
                        min_duration=0.25,
                    )

        self.assertEqual(code, 1)
        self.assertIn("make doubao-shadow-start-auto", stderr.getvalue())
        subprocess_run.assert_not_called()

    def test_run_shadow_benchmark_delegates_to_recorded_preview_when_ready(self):
        class Completed:
            returncode = 7

        calls = []

        def fake_run(command, cwd, env, check):
            calls.append((command, cwd, env, check))
            return Completed()

        with patch("bench.scripts.run_doubao_shadow_benchmark.status_payload", return_value=payload()):
            with patch("bench.scripts.run_doubao_shadow_benchmark.subprocess.run", side_effect=fake_run):
                code = run_shadow_benchmark(
                    pid_file=Path("shadow.pid"),
                    segments=Path("segments.jsonl"),
                    manifest=Path("manifest.jsonl"),
                    preview_manifest=Path("manifest.valid.jsonl"),
                    report=Path("report.md"),
                    min_duration=0.25,
                )

        self.assertEqual(code, 7)
        command, cwd, env, check = calls[0]
        self.assertTrue(str(command[0]).endswith("scripts/run_recorded_benchmark_preview.sh"))
        self.assertEqual(env["SWITCHTYPE_REAL_SOURCE_MANIFEST"], "manifest.jsonl")
        self.assertEqual(env["SWITCHTYPE_REAL_PREVIEW_MANIFEST"], "manifest.valid.jsonl")
        self.assertEqual(env["SWITCHTYPE_REAL_PREVIEW_REPORT"], "report.md")
        self.assertFalse(check)

    def test_makefile_exposes_auto_shadow_start_and_benchmark_wrapper(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-start-auto:", makefile)
        self.assertIn("SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1", makefile)
        self.assertIn("bench/scripts/run_doubao_shadow_benchmark.py", makefile)


if __name__ == "__main__":
    unittest.main()
