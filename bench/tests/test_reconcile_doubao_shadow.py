import csv
import json
import contextlib
import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from bench.scripts.reconcile_doubao_shadow import (
    import_review_tsv,
    main as reconcile_main,
    print_reconcile_plan,
    reconcile_segments,
    print_latest_asr_preview,
    print_wait_timeout_status,
    wait_for_next_asr_preview,
    validate_asr_preview_text,
    write_asr_preview_report,
    write_review_tsv,
)


def write_test_wav(path: Path, seconds: float = 0.25, rate: int = 16000) -> None:
    frames = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * frames)


class ReconcileDoubaoShadowTests(unittest.TestCase):
    def test_print_reconcile_plan_current_only_summarizes_without_writing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"legacy","audio":"legacy.wav"}\n'
                '{"id":"needs-text","audio":"needs-text.wav","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"captured","audio":"captured.wav","reference":"Codex prompt","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_reconcile_plan(
                    segments_path=segments,
                    manifest_path=manifest,
                    current_only=True,
                    target_command="make doubao-shadow-reconcile-current",
                    plan_command="make doubao-shadow-reconcile-current-plan",
                )

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertFalse(manifest.exists())
            self.assertIn("Plan: make doubao-shadow-reconcile-current", output)
            self.assertIn("Plan command safety: mutates_state=no, requests_mac_permissions=no, records_audio=no", output)
            self.assertIn("Target command safety: mutates_state=yes, requests_mac_permissions=no, records_audio=no", output)
            self.assertIn("Current segments: 2", output)
            self.assertIn("Legacy segments skipped: 1", output)
            self.assertIn("Trusted captured references: 1", output)
            self.assertIn("Will prompt for missing references: 1", output)
            self.assertIn("This preview does not write the manifest, prompt for references, record audio, or request macOS permissions.", output)

    def test_print_reconcile_plan_json_current_only_summarizes_without_writing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"legacy","audio":"legacy.wav"}\n'
                '{"id":"needs-text","audio":"needs-text.wav","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"captured","audio":"captured.wav","reference":"Codex prompt","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_reconcile_plan(
                    segments_path=segments,
                    manifest_path=manifest,
                    current_only=True,
                    target_command="make doubao-shadow-reconcile-current",
                    json_output=True,
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertFalse(manifest.exists())
            self.assertEqual(payload["plan_command"], "make doubao-shadow-reconcile-current-plan-json")
            self.assertFalse(payload["plan_mutates_state"])
            self.assertFalse(payload["plan_records_audio"])
            self.assertEqual(payload["target_command"], "make doubao-shadow-reconcile-current")
            self.assertTrue(payload["target_mutates_state"])
            self.assertEqual(payload["current_segments"], 2)
            self.assertEqual(payload["legacy_segments_skipped"], 1)
            self.assertEqual(payload["trusted_captured_references"], 1)
            self.assertEqual(payload["will_prompt_for_missing_references"], 1)
            self.assertTrue(payload["does_not_write_manifest"])

    def test_reconcile_segments_writes_benchmark_manifest_with_detected_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                json.dumps(
                    {
                        "id": "doubao-shadow-001",
                        "audio": "bench/samples/doubao-shadow/audio/doubao-shadow-001.wav",
                        "recorded_at": "2026-05-22T08:00:00Z",
                        "source": "doubao-shadow",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            answers = iter(["帮我生成一个 Codex prompt 让它修 flaky test"])

            with contextlib.redirect_stdout(io.StringIO()):
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex", "prompt", "flaky test"],
                    input_func=lambda prompt: next(answers),
                )

            self.assertEqual(count, 1)
            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["id"], "doubao-shadow-001")
            self.assertEqual(rows[0]["audio"], "bench/samples/doubao-shadow/audio/doubao-shadow-001.wav")
            self.assertEqual(rows[0]["reference"], "帮我生成一个 Codex prompt 让它修 flaky test")
            self.assertEqual(rows[0]["terms"], ["Codex", "prompt", "flaky test"])

    def test_reconcile_segments_prints_asr_preview_before_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex"],
                    input_func=lambda prompt: "最终确认的 Codex reference",
                    preview_func=lambda audio: "ASR 预览 Codex reference",
                )

            output = stdout.getvalue()
            self.assertEqual(count, 1)
            self.assertIn("ASR preview: ASR 预览 Codex reference", output)

    def test_reconcile_segments_continues_when_asr_preview_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav"}\n',
                encoding="utf-8",
            )

            def fail_preview(audio: str) -> str:
                raise RuntimeError("missing model")

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex"],
                    input_func=lambda prompt: "Codex reference",
                    preview_func=fail_preview,
                )

            output = stdout.getvalue()
            self.assertEqual(count, 1)
            self.assertIn("ASR preview failed: missing model", output)

    def test_write_asr_preview_report_lists_all_shadow_segments_without_prompting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            report = root / "preview.md"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","recorded_at":"2026-05-22T09:00:00Z"}\n'
                '{"id":"doubao-shadow-002","audio":"bench/samples/doubao-shadow/audio/two.wav","reference":"已确认的 Codex 文本"}\n',
                encoding="utf-8",
            )

            count = write_asr_preview_report(
                segments_path=segments,
                output_path=report,
                preview_func=lambda audio: f"preview for {Path(audio).name}",
            )

            text = report.read_text(encoding="utf-8")
            self.assertEqual(count, 2)
            self.assertIn("# Doubao Shadow ASR Preview", text)
            self.assertIn("doubao-shadow-001", text)
            self.assertIn("preview for one.wav", text)
            self.assertIn("已确认的 Codex 文本", text)

    def test_write_asr_preview_report_records_preview_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            report = root / "preview.md"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav"}\n',
                encoding="utf-8",
            )

            count = write_asr_preview_report(
                segments_path=segments,
                output_path=report,
                preview_func=lambda audio: (_ for _ in ()).throw(RuntimeError("missing model")),
            )

            text = report.read_text(encoding="utf-8")
            self.assertEqual(count, 1)
            self.assertIn("preview failed: missing model", text)

    def test_print_latest_asr_preview_only_transcribes_newest_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            segments.write_text(
                '{"id":"old","audio":"old.wav","recorded_at":"2026-05-24T04:00:00Z"}\n'
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","reference":"要求后续变更","text_capture_status":"captured","text_capture_attempts":2,"text_capture_elapsed_seconds":1.5,"text_capture_before_length":3,"text_capture_after_length":11}\n',
                encoding="utf-8",
            )
            calls = []

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = print_latest_asr_preview(
                    segments_path=segments,
                    preview_func=lambda audio: calls.append(audio) or "你好 Codex",
                )

            output = stdout.getvalue()
            self.assertEqual(count, 1)
            self.assertEqual(calls, ["latest.wav"])
            self.assertIn("Latest segment: latest", output)
            self.assertIn("Recorded at: 2026-05-24T05:00:00Z", output)
            self.assertIn("Audio: latest.wav", output)
            self.assertIn("Captured reference: 要求后续变更", output)
            self.assertIn("Text capture: captured", output)
            self.assertIn("Text capture diagnostic: attempts=2, elapsed=1.5s, before_len=3, after_len=11", output)
            self.assertIn("ASR preview: 你好 Codex", output)

    def test_print_latest_asr_preview_rejects_unsupported_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = print_latest_asr_preview(
                    segments_path=segments,
                    preview_func=lambda audio: "염산소를 의심하죠?",
                )

            output = stdout.getvalue()
            self.assertEqual(count, 1)
            self.assertIn("ASR preview rejected: unsupported script", output)
            self.assertNotIn("ASR preview: 염산소를 의심하죠?", output)

    def test_validate_asr_preview_text_accepts_chinese_english_and_digits(self):
        self.assertEqual(validate_asr_preview_text("你好 Codex 123456789"), "你好 Codex 123456789")

    def test_wait_for_next_asr_preview_only_transcribes_segment_created_after_start(self):
        old_segment = {
            "id": "old",
            "audio": "old.wav",
            "recorded_at": "2026-05-24T04:00:00Z",
        }
        new_segment = {
            "id": "new",
            "audio": "new.wav",
            "recorded_at": "2026-05-24T05:00:00Z",
            "reference": "你好 Codex",
            "text_capture_status": "unmatched",
            "text_capture_reason": "selection_range_mismatch",
        }
        snapshots = iter([[old_segment], [old_segment], [old_segment, new_segment]])
        preview_calls = []
        sleep_calls = []

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: preview_calls.append(audio) or "ASR 看到新录音",
                timeout_seconds=5.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: next(snapshots),
                sleep_func=lambda seconds: sleep_calls.append(seconds),
                monotonic_func=lambda: 0.0,
            )

        output = stdout.getvalue()
        self.assertEqual(count, 1)
        self.assertEqual(preview_calls, ["new.wav"])
        self.assertEqual(sleep_calls, [0.25])
        self.assertIn("Waiting up to 5.0s for the next Doubao shadow segment.", output)
        self.assertIn("New segment captured.", output)
        self.assertIn("Latest segment: new", output)
        self.assertIn("Text capture: unmatched/selection_range_mismatch", output)
        self.assertIn("ASR preview: ASR 看到新录音", output)

    def test_wait_for_next_asr_preview_reports_new_segment_even_when_preview_fails(self):
        old_segment = {
            "id": "old",
            "audio": "old.wav",
        }
        new_segment = {
            "id": "new",
            "audio": "new.wav",
        }
        snapshots = iter([[old_segment], [old_segment, new_segment]])

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: (_ for _ in ()).throw(RuntimeError("missing ASR helper")),
                timeout_seconds=5.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: next(snapshots),
                sleep_func=lambda seconds: None,
                monotonic_func=lambda: 0.0,
            )

        output = stdout.getvalue()
        self.assertEqual(count, 1)
        self.assertIn("New segment captured.", output)
        self.assertIn("Latest segment: new", output)
        self.assertIn("ASR preview failed: missing ASR helper", output)

    def test_wait_for_next_asr_preview_reports_timeout_without_reusing_old_segment(self):
        old_segment = {
            "id": "old",
            "audio": "old.wav",
            "recorded_at": "2026-05-24T04:00:00Z",
        }
        times = iter([0.0, 0.0, 2.0])
        preview_calls = []

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: preview_calls.append(audio) or "should not run",
                timeout_seconds=1.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: [old_segment],
                sleep_func=lambda seconds: None,
                monotonic_func=lambda: next(times),
            )

        output = stdout.getvalue()
        self.assertEqual(count, 0)
        self.assertEqual(preview_calls, [])
        self.assertIn("No new shadow segment captured within 1.0s.", output)
        self.assertIn("Latest existing segment: old", output)

    def test_wait_next_preview_cli_timeout_is_diagnostic_success(self):
        with patch("sys.argv", ["reconcile_doubao_shadow.py", "--wait-next-preview"]):
            with patch("bench.scripts.reconcile_doubao_shadow.wait_for_next_asr_preview", return_value=0):
                code = reconcile_main()

        self.assertEqual(code, 0)

    def test_wait_for_next_asr_preview_prints_status_diagnostics_on_timeout(self):
        old_segment = {
            "id": "old",
            "audio": "old.wav",
            "recorded_at": "2026-05-24T04:00:00Z",
        }
        status_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
                "capture_focused_text": True,
                "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow",
            },
            "segments": {
                "latest": {
                    "id": "old",
                    "age_seconds": 720,
                    "audio_status": {
                        "state": "valid",
                        "duration_seconds": 0.55,
                        "bytes": 21834,
                    },
                }
            },
            "hotkey_events": {
                "enabled": True,
                "observed": 0,
                "recognized": 0,
                "actions": {},
                "latest": None,
                "latest_recognized": None,
            },
        }
        times = iter([0.0, 0.0, 2.0])

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: "should not run",
                timeout_seconds=1.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: [old_segment],
                sleep_func=lambda seconds: None,
                monotonic_func=lambda: next(times),
                status_func=lambda: status_payload,
            )

        output = stdout.getvalue()
        self.assertEqual(count, 0)
        self.assertIn("Recorder status: running pid 123", output)
        self.assertIn("Configured hotkey: option key_code=58", output)
        self.assertIn("Hotkey events observed: 0", output)
        self.assertIn("Hotkey recording events: 0", output)
        self.assertIn("Latest status segment: old, age=12m, audio=valid, duration=0.55s, bytes=21834", output)
        self.assertIn("No hotkey events were observed during this wait.", output)
        self.assertIn("Verify packaged hotkey visibility with: make hotkey-probe-packaged", output)
        self.assertIn("If you need a sample now: DURATION=5 make doubao-shadow-capture-once-packaged", output)

    def test_wait_timeout_reports_hotkey_event_delta_for_this_wait_window(self):
        old_segment = {
            "id": "old",
            "audio": "old.wav",
            "recorded_at": "2026-05-24T04:00:00Z",
        }
        baseline_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow",
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
            },
            "segments": {"latest": {}},
            "hotkey_events": {
                "enabled": True,
                "observed": 5,
                "recognized": 1,
                "actions": {"ignore": 4, "startRecording": 1},
                "diagnosis": "events_visible_no_recording_match",
            },
        }
        timeout_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow",
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
            },
            "segments": {"latest": {}},
            "hotkey_events": {
                "enabled": True,
                "observed": 5,
                "recognized": 1,
                "actions": {"ignore": 4, "startRecording": 1},
                "diagnosis": "events_visible_no_recording_match",
            },
        }
        status_payloads = iter([baseline_payload, timeout_payload])
        times = iter([0.0, 0.0, 2.0])

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: "should not run",
                timeout_seconds=1.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: [old_segment],
                sleep_func=lambda seconds: None,
                monotonic_func=lambda: next(times),
                status_func=lambda: next(status_payloads),
            )

        output = stdout.getvalue()
        self.assertEqual(count, 0)
        self.assertIn("Hotkey events observed during this wait: 0 (total since recorder start: 5)", output)
        self.assertIn("Hotkey recording events during this wait: 0 (total since recorder start: 1)", output)
        self.assertIn("No new hotkey events were observed during this wait.", output)
        self.assertNotIn("Hotkey diagnosis: key events are visible, but none matched the recorder hotkey.", output)

    def test_wait_timeout_suggests_fixed_duration_fallback_when_hotkey_events_do_not_match(self):
        status_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
            },
            "segments": {"latest": {}},
            "hotkey_events": {
                "enabled": True,
                "observed": 3,
                "recognized": 0,
                "actions": {"ignore": 3},
                "latest": {
                    "source": "eventTap",
                    "type": "flagsChanged",
                    "key_code": 57,
                    "modifiers": "none",
                    "action": "ignore",
                },
                "diagnosis": "events_visible_no_recording_match",
            },
        }

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            print_wait_timeout_status(status_payload)

        output = stdout.getvalue()
        self.assertIn("Hotkey events observed: 3", output)
        self.assertIn("Hotkey recording events: 0", output)
        self.assertIn("Fixed-duration fallback: DURATION=5 make doubao-shadow-capture-once-packaged", output)

    def test_wait_timeout_suggests_enabling_packaged_hotkey_diagnostics_when_disabled(self):
        status_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow",
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
            },
            "segments": {"latest": {}},
            "hotkey_events": {
                "enabled": False,
                "observed": 0,
                "recognized": 0,
            },
        }

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            print_wait_timeout_status(status_payload)

        output = stdout.getvalue()
        self.assertIn("Hotkey event diagnostics are disabled.", output)
        self.assertIn(
            "Enable diagnostics with: SWITCHTYPE_DEBUG_HOTKEY_EVENTS=1 make doubao-shadow-restart-packaged",
            output,
        )
        self.assertNotIn("No hotkey events were observed during this wait.", output)

    def test_wait_timeout_prints_top_ignored_hotkey_candidates(self):
        status_payload = {
            "running": True,
            "pid": 123,
            "config": {
                "hotkey_key_code": "58",
                "hotkey_modifiers": "option",
            },
            "segments": {"latest": {}},
            "hotkey_events": {
                "enabled": True,
                "observed": 4,
                "recognized": 0,
                "actions": {"ignore": 4},
                "latest": None,
                "ignored_candidates": [
                    {
                        "source": "eventTap",
                        "type": "flagsChanged",
                        "key_code": 55,
                        "modifiers": "command",
                        "count": 2,
                    }
                ],
            },
        }

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            print_wait_timeout_status(status_payload)

        output = stdout.getvalue()
        self.assertIn(
            "Top ignored hotkey candidates: source=eventTap, type=flagsChanged, keyCode=55, modifiers=command, count=2",
            output,
        )

    def test_wait_for_next_asr_preview_fails_fast_when_recorder_is_not_running(self):
        preview_calls = []
        load_calls = []

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            count = wait_for_next_asr_preview(
                segments_path=Path("segments.jsonl"),
                preview_func=lambda audio: preview_calls.append(audio) or "should not run",
                timeout_seconds=30.0,
                poll_interval_seconds=0.25,
                load_func=lambda path: load_calls.append(path) or [],
                sleep_func=lambda seconds: None,
                monotonic_func=lambda: 0.0,
                recorder_running_func=lambda: False,
            )

        output = stdout.getvalue()
        self.assertEqual(count, 0)
        self.assertEqual(preview_calls, [])
        self.assertEqual(load_calls, [])
        self.assertIn("Doubao shadow recorder is not running.", output)
        self.assertIn("Start it with: make doubao-shadow-start-auto-packaged", output)

    def test_write_review_tsv_exports_preview_but_leaves_reference_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            review = root / "review.tsv"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","recorded_at":"2026-05-22T09:00:00Z"}\n',
                encoding="utf-8",
            )

            count = write_review_tsv(
                segments_path=segments,
                output_path=review,
                preview_func=lambda audio: "ASR preview only",
            )

            rows = review.read_text(encoding="utf-8").splitlines()
            self.assertEqual(count, 1)
            self.assertEqual(
                rows[0],
                "id\trecorded_at\taudio\taudio_state\taudio_duration_seconds\trecording_stop_reason\ttext_capture_status\ttext_capture_reason\tasr_preview\treference\treference_source\treference_trusted",
            )
            self.assertIn("ASR preview only\t\t\t", rows[1])
            self.assertTrue(rows[1].endswith("\t\t\t"))

    def test_write_review_tsv_exports_audio_and_text_capture_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            review = root / "review.tsv"
            safe_audio = root / "safe.wav"
            write_test_wav(safe_audio, seconds=0.5)
            segments.write_text(
                json.dumps(
                    {
                        "id": "safe",
                        "audio": str(safe_audio),
                        "recorded_at": "2026-05-24T04:37:48Z",
                        "recording_stop_reason": "hotkey_released",
                        "text_capture_status": "captured",
                        "text_capture_reason": "captured",
                        "reference": "要求后续变更",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                '{"id":"miss","audio":"miss.wav","recorded_at":"2026-05-24T05:13:04Z","recording_stop_reason":"hotkey_released","text_capture_status":"unmatched","text_capture_reason":"invalid_selection_range"}\n',
                encoding="utf-8",
            )

            count = write_review_tsv(
                segments_path=segments,
                output_path=review,
                preview_func=lambda audio: f"preview for {audio}",
            )

            with review.open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(count, 2)
            self.assertEqual(rows[0]["audio_state"], "valid")
            self.assertEqual(rows[0]["audio_duration_seconds"], "0.500")
            self.assertEqual(rows[0]["recording_stop_reason"], "hotkey_released")
            self.assertEqual(rows[0]["text_capture_status"], "captured")
            self.assertEqual(rows[0]["text_capture_reason"], "captured")
            self.assertEqual(rows[0]["reference"], "要求后续变更")
            self.assertEqual(rows[0]["reference_source"], "segment_log_safe")
            self.assertEqual(rows[0]["reference_trusted"], "yes")
            self.assertEqual(rows[1]["audio_state"], "missing")
            self.assertEqual(rows[1]["audio_duration_seconds"], "")
            self.assertEqual(rows[1]["text_capture_status"], "unmatched")
            self.assertEqual(rows[1]["text_capture_reason"], "invalid_selection_range")
            self.assertEqual(rows[1]["reference"], "")
            self.assertEqual(rows[1]["reference_source"], "")
            self.assertEqual(rows[1]["reference_trusted"], "")

    def test_write_review_tsv_does_not_prefill_unsafe_segment_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            review = root / "review.tsv"
            segments.write_text(
                '{"id":"unsafe","audio":"unsafe.wav","reference":"误配文本","recording_stop_reason":"max_duration"}\n',
                encoding="utf-8",
            )

            count = write_review_tsv(
                segments_path=segments,
                output_path=review,
                preview_func=lambda audio: "local preview",
            )

            with review.open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(count, 1)
            self.assertEqual(rows[0]["reference"], "")
            self.assertEqual(rows[0]["reference_source"], "")
            self.assertEqual(rows[0]["reference_trusted"], "")

    def test_import_review_tsv_writes_manifest_from_reviewed_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.tsv"
            manifest = root / "manifest.jsonl"
            review.write_text(
                "id\trecorded_at\taudio\tasr_preview\treference\n"
                "doubao-shadow-001\t2026-05-22T09:00:00Z\tbench/samples/doubao-shadow/audio/one.wav\t错误预览\t帮我生成一个 Codex prompt\n"
                "doubao-shadow-002\t2026-05-22T09:01:00Z\tbench/samples/doubao-shadow/audio/two.wav\t只有预览\t   \n",
                encoding="utf-8",
            )

            count = import_review_tsv(
                review_path=review,
                manifest_path=manifest,
                protected_terms=["Codex", "prompt"],
            )

            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual(rows[0]["id"], "doubao-shadow-001")
            self.assertEqual(rows[0]["reference"], "帮我生成一个 Codex prompt")
            self.assertEqual(rows[0]["terms"], ["Codex", "prompt"])
            self.assertNotIn("错误预览", json.dumps(rows[0], ensure_ascii=False))

    def test_import_review_tsv_preserves_existing_manifest_and_skips_untrusted_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.tsv"
            manifest = root / "manifest.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "id": "existing",
                        "audio": "existing.wav",
                        "reference": "保留 Codex 旧样本",
                        "terms": ["Codex"],
                        "source": "manual",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            review.write_text(
                "id\trecorded_at\taudio\tasr_preview\treference\treference_source\treference_trusted\n"
                "existing\t2026-05-22T09:00:00Z\texisting.wav\tpreview\t   \t\t\n"
                "trusted\t2026-05-22T09:01:00Z\ttrusted.wav\tpreview\t新的 Qwen3-ASR reference\tmanual\tyes\n"
                "rejected\t2026-05-22T09:02:00Z\trejected.wav\tpreview\t不要导入的 reference\tmanual\tno\n",
                encoding="utf-8",
            )

            count = import_review_tsv(
                review_path=review,
                manifest_path=manifest,
                protected_terms=["Codex", "Qwen3-ASR"],
            )

            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual([row["id"] for row in rows], ["existing", "trusted"])
            self.assertEqual(rows[0]["reference"], "保留 Codex 旧样本")
            self.assertEqual(rows[0]["source"], "manual")
            self.assertEqual(rows[1]["reference"], "新的 Qwen3-ASR reference")
            self.assertEqual(rows[1]["terms"], ["Qwen3-ASR"])

    def test_reconcile_segments_skips_blank_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav"}\n'
                '{"id":"doubao-shadow-002","audio":"bench/samples/doubao-shadow/audio/two.wav"}\n',
                encoding="utf-8",
            )
            answers = iter(["   ", "Codex PR"])

            with contextlib.redirect_stdout(io.StringIO()):
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex", "PR"],
                    input_func=lambda prompt: next(answers),
                )

            self.assertEqual(count, 1)
            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["doubao-shadow-002"])

    def test_reconcile_segments_current_only_skips_legacy_segments_without_prompting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"legacy","audio":"legacy.wav","text_capture_status":"unmatched"}\n'
                '{"id":"current","audio":"current.wav","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            prompts = []

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex"],
                    input_func=lambda prompt: prompts.append(prompt) or "当前 Codex 文本",
                    current_only=True,
                )

            output = stdout.getvalue()
            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual(len(prompts), 1)
            self.assertIn("Current-only mode: skipped legacy segment without recording_stop_reason.", output)
            self.assertEqual([row["id"] for row in rows], ["current"])
            self.assertEqual(rows[0]["reference"], "当前 Codex 文本")

    def test_reconcile_segments_uses_reference_captured_in_segment_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                json.dumps(
                    {
                        "id": "doubao-shadow-001",
                        "audio": "bench/samples/doubao-shadow/audio/one.wav",
                        "recording_stop_reason": "hotkey_released",
                        "reference": "帮我 review Codex PR",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError(f"unexpected prompt: {prompt}")

            with contextlib.redirect_stdout(io.StringIO()):
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex", "PR"],
                    input_func=fail_if_prompted,
                )

            self.assertEqual(count, 1)
            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["reference"], "帮我 review Codex PR")
            self.assertEqual(rows[0]["terms"], ["Codex", "PR"])

    def test_reconcile_segments_auto_only_rejects_captured_reference_when_asr_preview_does_not_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                json.dumps(
                    {
                        "id": "doubao-shadow-001",
                        "audio": "bench/samples/doubao-shadow/audio/one.wav",
                        "recording_stop_reason": "hotkey_released",
                        "reference": "要求后续变更",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError(f"unexpected prompt: {prompt}")

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=[],
                    input_func=fail_if_prompted,
                    preview_func=lambda audio: "你给自己设置一个48小时之内可以持续优化的目标",
                    prompt_for_missing=False,
                )

            output = stdout.getvalue()
            self.assertEqual(count, 0)
            self.assertIn("Ignored captured reference because ASR preview did not overlap.", output)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "")

    def test_reconcile_segments_auto_only_skips_unresolved_without_prompting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","reference":"要求后续变更","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"doubao-shadow-002","audio":"bench/samples/doubao-shadow/audio/two.wav","text_capture_status":"unmatched"}\n',
                encoding="utf-8",
            )

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError(f"unexpected prompt: {prompt}")

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex"],
                    input_func=fail_if_prompted,
                    prompt_for_missing=False,
                )

            output = stdout.getvalue()
            self.assertEqual(count, 1)
            self.assertIn("Auto-only mode: skipped unresolved segment.", output)
            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["doubao-shadow-001"])
            self.assertEqual(rows[0]["reference"], "要求后续变更")

    def test_reconcile_segments_does_not_trust_captured_reference_without_safe_stop_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","reference":"误配文本"}\n'
                '{"id":"doubao-shadow-002","audio":"bench/samples/doubao-shadow/audio/two.wav","reference":"超时误配","recording_stop_reason":"max_duration"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=[],
                    input_func=lambda prompt: "",
                    prompt_for_missing=False,
                )

            output = stdout.getvalue()
            self.assertEqual(count, 0)
            self.assertIn("Ignored captured reference with unsafe stop reason", output)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "")

    def test_reconcile_segments_does_not_reuse_manifest_reference_copied_from_unsafe_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","reference":"误配文本"}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav","reference":"误配文本"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=[],
                    input_func=lambda prompt: "",
                    prompt_for_missing=False,
                )

            output = stdout.getvalue()
            self.assertEqual(count, 0)
            self.assertIn("Ignored existing manifest reference copied from unsafe segment capture.", output)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "")

    def test_reconcile_segments_reuses_existing_manifest_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"doubao-shadow-001","audio":"bench/samples/doubao-shadow/audio/one.wav"}\n'
                '{"id":"doubao-shadow-002","audio":"bench/samples/doubao-shadow/audio/two.wav","reference":"新的 MCP server","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {
                        "id": "doubao-shadow-001",
                        "audio": "bench/samples/doubao-shadow/audio/one.wav",
                        "reference": "手工修正过的 Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError(f"unexpected prompt: {prompt}")

            with contextlib.redirect_stdout(io.StringIO()):
                count = reconcile_segments(
                    segments_path=segments,
                    manifest_path=manifest,
                    protected_terms=["Codex", "PR", "MCP", "server"],
                    input_func=fail_if_prompted,
                )

            rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 2)
            self.assertEqual([row["id"] for row in rows], ["doubao-shadow-001", "doubao-shadow-002"])
            self.assertEqual(rows[0]["reference"], "手工修正过的 Codex PR")
            self.assertEqual(rows[0]["terms"], ["Codex", "PR"])
            self.assertEqual(rows[1]["reference"], "新的 MCP server")
            self.assertEqual(rows[1]["terms"], ["MCP", "server"])

    def test_makefile_exposes_doubao_shadow_reconcile_and_benchmark(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-reconcile:", makefile)
        self.assertIn("doubao-shadow-reconcile-current:", makefile)
        self.assertIn("doubao-shadow-reconcile-auto:", makefile)
        self.assertIn("doubao-shadow-reconcile-auto: swift-build", makefile)
        self.assertIn("doubao-shadow-reconcile-preview:", makefile)
        self.assertIn("doubao-shadow-latest-preview:", makefile)
        self.assertIn("doubao-shadow-live-verify:", makefile)
        self.assertIn("$(MAKE) doubao-shadow-wait-next-preview", makefile)
        self.assertIn("doubao-shadow-wait-next-preview:", makefile)
        self.assertNotIn("doubao-shadow-wait-next-preview: swift-build", makefile)
        self.assertIn("doubao-shadow-preview-transcripts:", makefile)
        self.assertIn("doubao-shadow-review-sheet:", makefile)
        self.assertIn("doubao-shadow-import-review:", makefile)
        self.assertIn("--asr-preview", makefile)
        self.assertIn("--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke", makefile)
        self.assertIn("--latest-preview", makefile)
        self.assertIn("--wait-next-preview", makefile)
        self.assertIn("--wait-timeout-seconds", makefile)
        self.assertIn("--pid-file $${PID_FILE:-bench/samples/doubao-shadow/shadow.pid}", makefile)
        self.assertIn("--preview-only", makefile)
        self.assertIn("--review-output", makefile)
        self.assertIn("--import-review", makefile)
        self.assertIn("--auto-only", makefile)
        self.assertIn("--current-only", makefile)
        self.assertIn("bench/scripts/reconcile_doubao_shadow.py", makefile)
        self.assertIn("doubao-shadow-benchmark:", makefile)
        self.assertIn("bench/reports/doubao-shadow-preview.md", makefile)


if __name__ == "__main__":
    unittest.main()
