import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bench.scripts.run_doubao_shadow_capture_once import run_capture_once


class Completed:
    def __init__(self, returncode: int):
        self.returncode = returncode


class DoubaoShadowCaptureOnceTests(unittest.TestCase):
    def test_capture_once_runs_status_after_recording_failure_and_skips_preview(self):
        calls = []

        def fake_run(command):
            calls.append(command)
            if command[-1] == "doubao-shadow-record-seconds-auto-packaged":
                return Completed(2)
            return Completed(0)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = run_capture_once(run_func=fake_run, make_command="make")

        self.assertEqual(code, 2)
        self.assertEqual(
            calls,
            [
                ["make", "doubao-shadow-record-seconds-auto-packaged"],
                ["make", "doubao-shadow-status"],
            ],
        )
        self.assertIn("Skipping latest preview because fixed-duration recording failed.", stdout.getvalue())

    def test_capture_once_ignores_preview_failure_but_still_returns_status_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            segments = Path(tmp) / "segments.jsonl"
            segments.write_text('{"id":"old","audio":"old.wav"}\n', encoding="utf-8")
            calls = []

            def fake_run(command):
                calls.append(command)
                if command[-1] == "doubao-shadow-record-seconds-auto-packaged":
                    segments.write_text(
                        '{"id":"old","audio":"old.wav"}\n{"id":"new","audio":"new.wav"}\n',
                        encoding="utf-8",
                    )
                if command[-1] == "doubao-shadow-latest-preview":
                    return Completed(7)
                return Completed(0)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = run_capture_once(
                    run_func=fake_run,
                    make_command="make",
                    segments_path=segments,
                )

        self.assertEqual(code, 0)
        self.assertEqual(
            calls,
            [
                ["make", "doubao-shadow-record-seconds-auto-packaged"],
                ["make", "doubao-shadow-latest-preview"],
                ["make", "doubao-shadow-status"],
            ],
        )
        self.assertIn("Latest preview failed; continuing to status.", stdout.getvalue())

    def test_capture_once_skips_preview_when_recording_writes_no_new_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            segments = Path(tmp) / "segments.jsonl"
            segments.write_text('{"id":"old","audio":"old.wav"}\n', encoding="utf-8")
            calls = []

            def fake_run(command):
                calls.append(command)
                return Completed(0)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = run_capture_once(
                    run_func=fake_run,
                    make_command="make",
                    segments_path=segments,
                )

        self.assertEqual(code, 1)
        self.assertEqual(
            calls,
            [
                ["make", "doubao-shadow-record-seconds-auto-packaged"],
                ["make", "doubao-shadow-status"],
            ],
        )
        self.assertIn("Skipping latest preview because no new shadow segment was written.", stdout.getvalue())

    def test_capture_once_previews_only_after_new_segment_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            segments = Path(tmp) / "segments.jsonl"
            segments.write_text('{"id":"old","audio":"old.wav"}\n', encoding="utf-8")
            calls = []

            def fake_run(command):
                calls.append(command)
                if command[-1] == "doubao-shadow-record-seconds-auto-packaged":
                    segments.write_text(
                        '{"id":"old","audio":"old.wav"}\n{"id":"new","audio":"new.wav"}\n',
                        encoding="utf-8",
                    )
                return Completed(0)

            with contextlib.redirect_stdout(io.StringIO()):
                code = run_capture_once(
                    run_func=fake_run,
                    make_command="make",
                    segments_path=segments,
                )

        self.assertEqual(code, 0)
        self.assertEqual(
            calls,
            [
                ["make", "doubao-shadow-record-seconds-auto-packaged"],
                ["make", "doubao-shadow-latest-preview"],
                ["make", "doubao-shadow-status"],
            ],
        )

    def test_makefile_routes_capture_once_through_wrapper(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-capture-once-packaged:", makefile)
        self.assertIn("bench/scripts/run_doubao_shadow_capture_once.py", makefile)


if __name__ == "__main__":
    unittest.main()
