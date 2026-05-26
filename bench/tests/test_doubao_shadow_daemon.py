import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bench.scripts.doubao_shadow_daemon import (
    format_recorded_at_local,
    hearing_check_payload,
    print_hearing_check,
    print_status,
    start_daemon,
    status_payload,
    stop_daemon,
)


class FakeProcess:
    pid = 4242


def write_test_wav(
    path: Path,
    seconds: float = 0.25,
    rate: int = 16000,
    channels: int = 1,
    signal: bool = True,
) -> None:
    frames = int(seconds * rate)
    sample = b"\x01\x00" if signal else b"\x00\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(sample * frames * channels)


def write_packaged_shadow_helpers(
    root: Path,
    mtime: datetime = datetime(2026, 5, 24, 7, 0, 0, tzinfo=timezone.utc),
) -> tuple[Path, Path]:
    binary = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"
    doctor = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("packaged shadow helper", encoding="utf-8")
    doctor.write_text("packaged doctor helper", encoding="utf-8")
    timestamp = mtime.timestamp()
    os.utime(binary, (timestamp, timestamp))
    os.utime(doctor, (timestamp, timestamp))
    return binary, doctor


class DoubaoShadowDaemonTests(unittest.TestCase):
    def test_start_daemon_launches_shadow_binary_and_writes_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_popen(command, stdin, stdout, stderr, start_new_session):
                calls.append((command, stdin, stdout, stderr, start_new_session))
                return FakeProcess()

            with patch("bench.scripts.doubao_shadow_daemon.subprocess.Popen", side_effect=fake_popen):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = start_daemon(
                        binary=Path("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"),
                        output_dir=root / "audio",
                        segments=root / "segments.jsonl",
                        pid_file=root / "shadow.pid",
                        log_file=root / "shadow.log",
                        expected_input_device="DJI MIC MINI",
                        hotkey_key_code="36",
                        hotkey_modifiers="control,shift",
                        capture_focused_text=True,
                        text_capture_delay_seconds="2.0",
                        text_capture_timeout_seconds="5.0",
                    )

            self.assertEqual(code, 0)
            self.assertEqual((root / "shadow.pid").read_text(encoding="utf-8"), "4242")
            config = json.loads((root / "shadow.config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["binary"], "app/SwitchType/.build/debug/SwitchTypeDoubaoShadow")
            self.assertEqual(config["hotkey_key_code"], "36")
            self.assertEqual(config["hotkey_modifiers"], "control,shift")
            self.assertTrue(config["capture_focused_text"])
            self.assertEqual(config["expected_input_device"], "DJI MIC MINI")
            self.assertEqual(config["text_capture_timeout_seconds"], "5.0")
            command = calls[0][0]
            self.assertIn("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow", command)
            self.assertIn("--output-dir", command)
            self.assertIn(str(root / "audio"), command)
            self.assertIn("--segments", command)
            self.assertIn(str(root / "segments.jsonl"), command)
            self.assertIn("--expected-input-device", command)
            self.assertIn("DJI MIC MINI", command)
            self.assertIn("--hotkey-key-code", command)
            self.assertIn("36", command)
            self.assertIn("--hotkey-modifiers", command)
            self.assertIn("control,shift", command)
            self.assertIn("--capture-focused-text", command)
            self.assertIn("--text-capture-delay-seconds", command)
            self.assertIn("2.0", command)
            self.assertIn("--text-capture-timeout-seconds", command)
            self.assertIn("5.0", command)
            self.assertTrue(calls[0][4])
            self.assertIn("Started Doubao shadow recorder", stdout.getvalue())

    def test_start_daemon_does_not_launch_when_pid_is_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            pid_file.write_text("123", encoding="utf-8")

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.subprocess.Popen") as popen:
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = start_daemon(
                            binary=Path("shadow"),
                            output_dir=root / "audio",
                            segments=root / "segments.jsonl",
                            pid_file=pid_file,
                            log_file=root / "shadow.log",
                            expected_input_device=None,
                            hotkey_key_code=None,
                            hotkey_modifiers=None,
                            capture_focused_text=False,
                            text_capture_delay_seconds=None,
                        )

            self.assertEqual(code, 0)
            popen.assert_not_called()

    def test_print_status_reports_segment_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text('{"id":"one"}\n\n{"id":"two"}\n', encoding="utf-8")

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments)

            self.assertEqual(code, 0)
            self.assertIn("Doubao shadow recorder running: pid 123", stdout.getvalue())
            self.assertIn("Captured segments: 2", stdout.getvalue())

    def test_running_status_with_no_segments_prompts_user_to_use_doubao(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            pid_file.write_text("123", encoding="utf-8")

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(pid_file=pid_file, segments=segments, manifest=manifest)
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            self.assertEqual(code, 0)
            self.assertEqual(payload["next"], "use Doubao voice input now; if you already tried, run make hotkey-probe")
            self.assertFalse(payload["next_is_executable_command"])
            self.assertFalse(payload["next_requires_user_approval"])
            self.assertFalse(payload["capture_readiness"]["next_is_executable_command"])
            self.assertFalse(payload["capture_readiness"]["next_requires_user_approval"])
            output = stdout.getvalue()
            self.assertIn("Doubao shadow recorder running: pid 123", output)
            self.assertIn("Hearing status: armed; next Doubao utterance can be captured.", output)
            self.assertIn("Captured segments: 0", output)
            self.assertIn("Hotkey key code: 49", output)
            self.assertIn("Hotkey modifiers: option", output)
            self.assertIn("Recorder binary: app/SwitchType/.build/debug/SwitchTypeDoubaoShadow", output)
            self.assertIn("Focused text capture: disabled", output)
            self.assertIn("Live verify: TIMEOUT=30 make doubao-shadow-live-verify", output)
            self.assertIn("Live verify approval: user approval required before running.", output)
            self.assertIn(
                "Live verify safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Next action approval: guidance, not an executable command.", output)
            self.assertIn(
                "Next action safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Next: use Doubao voice input now; if you already tried, run make hotkey-probe", output)

    def test_status_payload_reports_live_verification_command_only_when_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            pid_file.write_text("123", encoding="utf-8")

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                running_payload = status_payload(pid_file=pid_file, segments=segments)
            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=False):
                stopped_payload = status_payload(pid_file=pid_file, segments=segments)

            self.assertEqual(
                running_payload["live_verification_command"],
                "TIMEOUT=30 make doubao-shadow-live-verify",
            )
            self.assertTrue(running_payload["live_verification_command_is_executable"])
            self.assertTrue(running_payload["live_verification_command_requires_user_approval"])
            self.assertFalse(running_payload["live_verification_command_mutates_state"])
            self.assertFalse(running_payload["live_verification_command_requests_mac_permissions"])
            self.assertFalse(running_payload["live_verification_command_records_audio"])
            self.assertIsNone(stopped_payload["live_verification_command"])
            self.assertFalse(stopped_payload["live_verification_command_is_executable"])
            self.assertFalse(stopped_payload["live_verification_command_requires_user_approval"])
            self.assertFalse(stopped_payload["live_verification_command_mutates_state"])
            self.assertFalse(stopped_payload["live_verification_command_requests_mac_permissions"])
            self.assertFalse(stopped_payload["live_verification_command_records_audio"])

    def test_print_hearing_check_answers_user_question_without_full_status_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_hearing_check(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Doubao shadow hearing check", output)
            self.assertIn("Can hear next Doubao utterance: no", output)
            self.assertIn(
                "Hearing status: stopped; not capturing new speech now (recorder is not running).",
                output,
            )
            self.assertIn(
                "Transcript visibility: inserted text is only visible after Doubao pastes it into the active field; this check is about local audio capture.",
                output,
            )
            self.assertIn("Next command approval: user approval required before running.", output)
            self.assertIn(
                "Next command safety: mutates_state=yes, requests_mac_permissions=no, records_audio=yes",
                output,
            )
            self.assertIn("Next: make doubao-shadow-start-auto", output)
            self.assertNotIn("Captured references:", output)
            self.assertNotIn("Benchmark manifest samples:", output)

    def test_hearing_check_labels_live_verify_as_alternative_when_fixed_duration_fallback_is_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option", "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=57, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_hearing_check(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Can hear next Doubao utterance: no", output)
            self.assertIn("Alternative live verify: TIMEOUT=30 make doubao-shadow-live-verify", output)
            self.assertNotIn("\nLive verify: TIMEOUT=30 make doubao-shadow-live-verify", output)
            self.assertIn("Recommended command: DURATION=5 make doubao-shadow-capture-once-packaged", output)
            self.assertIn("Next safe command: make doubao-shadow-capture-once-packaged-plan-json", output)
            self.assertIn(
                "Next user-approval command: DURATION=5 make doubao-shadow-capture-once-packaged",
                output,
            )

    def test_hearing_check_prints_recommended_hotkey_probe_before_lower_level_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"current","audio":"current.wav","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option", "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=56, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_hearing_check(
                        pid_file=pid_file,
                        segments=segments,
                        log_file=log_file,
                    )

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            recommended_index = output.index("Recommended command: TIMEOUT=30 make hotkey-probe-packaged")
            self.assertLess(recommended_index, output.index("Alternative live verify:"))
            self.assertLess(recommended_index, output.index("Pending clip action approval:"))
            self.assertLess(recommended_index, output.index("Capture diagnostic:"))
            self.assertLess(recommended_index, output.index("Hotkey repair hint:"))
            self.assertLess(
                output.index("Recommended command plan: make hotkey-probe-packaged-plan-json"),
                output.index("Capture diagnostic:"),
            )
            self.assertIn("Pending clip action: make doubao-shadow-reconcile-current", output)
            self.assertNotIn("Next: make doubao-shadow-reconcile-current", output)

    def test_cli_hearing_check_json_outputs_compact_machine_readable_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bench.scripts.doubao_shadow_daemon",
                    "--hearing-check",
                    "--json",
                    "--pid-file",
                    str(pid_file),
                    "--segments",
                    str(segments),
                    "--manifest",
                    str(manifest),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(set(payload.keys()), {
                "can_hear_next",
                "capture_readiness",
                "doubao_settings_shortcut_hints",
                "effective_hearing_status",
                "hearing_status",
                "hotkey_repair_hint",
                "hotkey_repair_deferred_until_permissions",
                "live_verification_command",
                "live_verification_command_is_executable",
                "live_verification_command_mutates_state",
                "live_verification_command_records_audio",
                "live_verification_command_requests_mac_permissions",
                "live_verification_command_requires_user_approval",
                "next",
                "next_is_executable_command",
                "next_mutates_state",
                "next_records_audio",
                "next_requests_mac_permissions",
                "next_requires_user_approval",
                "next_role",
                "pending_clip_action",
                "pending_clip_action_is_executable_command",
                "pending_clip_action_mutates_state",
                "pending_clip_action_preview",
                "pending_clip_action_preview_is_executable_command",
                "pending_clip_action_preview_mutates_state",
                "pending_clip_action_preview_records_audio",
                "pending_clip_action_preview_requests_mac_permissions",
                "pending_clip_action_preview_requires_user_approval",
                "pending_clip_action_records_audio",
                "pending_clip_action_requests_mac_permissions",
                "pending_clip_action_requires_user_approval",
                "pending_clip_cleanup_deferred_until_permissions",
                "primary_blocker",
                "primary_blocker_detail",
                "primary_permission_target",
                "primary_recovery_command",
                "primary_recovery_command_is_executable",
                "primary_recovery_mutates_state",
                "primary_recovery_records_audio",
                "primary_recovery_requests_mac_permissions",
                "primary_recovery_requires_user_approval",
                "permission_guidance",
                "permission_targets",
                "preflight_blockers",
                "preflight_blockers_available",
                "preflight_blockers_error",
                "preflight_blockers_ignored_reason",
                "preflight_ignored_blockers",
                "preflight_mac_permissions",
                "preflight_input_device",
                "preflight_input_device_detail",
                "preflight_next",
                "preflight_next_is_executable_command",
                "preflight_next_mutates_state",
                "preflight_next_records_audio",
                "preflight_next_requests_mac_permissions",
                "preflight_next_requires_user_approval",
                "preflight_permission_guidance",
                "preflight_permission_targets",
                "preflight_preview",
                "preflight_preview_is_executable_command",
                "preflight_preview_mutates_state",
                "preflight_preview_records_audio",
                "preflight_preview_requests_mac_permissions",
                "preflight_preview_requires_user_approval",
                "preflight_warnings",
                "recommended_command",
                "recommended_command_approval_reasons",
                "recommended_command_approval_summary",
                "recommended_command_is_executable",
                "recommended_command_mutates_state",
                "recommended_command_plan",
                "recommended_command_records_audio",
                "recommended_command_requests_mac_permissions",
                "recommended_command_requires_user_approval",
                "recommended_command_source",
                "readiness_summary",
                "recovery_command",
                "recovery_condition",
                "recovery_is_executable_command",
                "recovery_mutates_state",
                "recovery_records_audio",
                "recovery_requests_mac_permissions",
                "recovery_requires_user_approval",
                "shadow_hotkey_config_match",
                "secondary_diagnostics_deferred_until_permissions",
                "transcript_visibility",
            })
            self.assertFalse(payload["can_hear_next"])
            self.assertEqual(payload["capture_readiness"]["status"], "stopped")
            self.assertEqual(
                payload["transcript_visibility"],
                "inserted text is only visible after Doubao pastes it into the active field; this check is about local audio capture.",
            )
            self.assertEqual(payload["hearing_status"]["status"], "stopped")
            self.assertEqual(payload["effective_hearing_status"], payload["hearing_status"])
            self.assertFalse(payload["secondary_diagnostics_deferred_until_permissions"])
            self.assertFalse(payload["hotkey_repair_deferred_until_permissions"])
            self.assertIn("available", payload["doubao_settings_shortcut_hints"])
            self.assertEqual(payload["next"], "make doubao-shadow-start-auto")
            self.assertTrue(payload["next_is_executable_command"])
            self.assertTrue(payload["next_requires_user_approval"])
            self.assertTrue(payload["next_mutates_state"])
            self.assertFalse(payload["next_requests_mac_permissions"])
            self.assertTrue(payload["next_records_audio"])
            self.assertEqual(payload["next_role"], "primary_action")
            self.assertIsNone(payload["pending_clip_action"])
            self.assertFalse(payload["pending_clip_action_is_executable_command"])
            self.assertFalse(payload["pending_clip_action_requires_user_approval"])
            self.assertFalse(payload["pending_clip_action_mutates_state"])
            self.assertFalse(payload["pending_clip_action_requests_mac_permissions"])
            self.assertFalse(payload["pending_clip_action_records_audio"])
            self.assertIsNone(payload["pending_clip_action_preview"])
            self.assertFalse(payload["pending_clip_action_preview_is_executable_command"])
            self.assertFalse(payload["pending_clip_action_preview_requires_user_approval"])
            self.assertFalse(payload["pending_clip_action_preview_mutates_state"])
            self.assertFalse(payload["pending_clip_action_preview_requests_mac_permissions"])
            self.assertFalse(payload["pending_clip_action_preview_records_audio"])
            self.assertFalse(payload["pending_clip_cleanup_deferred_until_permissions"])
            self.assertEqual(payload["primary_blocker"], "recorder_stopped")
            self.assertEqual(payload["primary_blocker_detail"], "recorder is not running")
            self.assertEqual(payload["primary_recovery_command"], "make doubao-shadow-start-auto")
            self.assertTrue(payload["primary_recovery_command_is_executable"])
            self.assertTrue(payload["primary_recovery_requires_user_approval"])
            self.assertTrue(payload["primary_recovery_mutates_state"])
            self.assertFalse(payload["primary_recovery_requests_mac_permissions"])
            self.assertTrue(payload["primary_recovery_records_audio"])
            self.assertIsNone(payload["primary_permission_target"])
            self.assertEqual(payload["permission_targets"], [])
            self.assertEqual(payload["permission_guidance"], "")
            self.assertIsNone(payload["recovery_command"])
            self.assertFalse(payload["recovery_is_executable_command"])
            self.assertFalse(payload["recovery_requires_user_approval"])
            self.assertFalse(payload["recovery_mutates_state"])
            self.assertFalse(payload["recovery_requests_mac_permissions"])
            self.assertFalse(payload["recovery_records_audio"])
            self.assertEqual(payload["preflight_blockers"], [])
            self.assertFalse(payload["preflight_blockers_available"])
            self.assertIsNone(payload["preflight_blockers_error"])
            self.assertEqual(payload["preflight_ignored_blockers"], [])
            self.assertIsNone(payload["preflight_blockers_ignored_reason"])
            self.assertEqual(payload["preflight_mac_permissions"], {})
            self.assertEqual(payload["preflight_input_device"], {})
            self.assertEqual(payload["preflight_input_device_detail"], "")
            self.assertIsNone(payload["preflight_next"])
            self.assertFalse(payload["preflight_next_is_executable_command"])
            self.assertFalse(payload["preflight_next_requires_user_approval"])
            self.assertFalse(payload["preflight_next_mutates_state"])
            self.assertFalse(payload["preflight_next_requests_mac_permissions"])
            self.assertFalse(payload["preflight_next_records_audio"])
            self.assertEqual(payload["preflight_permission_guidance"], "")
            self.assertEqual(payload["preflight_permission_targets"], [])
            self.assertIsNone(payload["preflight_preview"])
            self.assertFalse(payload["preflight_preview_is_executable_command"])
            self.assertFalse(payload["preflight_preview_requires_user_approval"])
            self.assertFalse(payload["preflight_preview_mutates_state"])
            self.assertFalse(payload["preflight_preview_requests_mac_permissions"])
            self.assertFalse(payload["preflight_preview_records_audio"])
            self.assertEqual(payload["preflight_warnings"], [])
            self.assertEqual(payload["recommended_command"], "make doubao-shadow-start-auto")
            self.assertEqual(payload["recommended_command_source"], "next")
            self.assertTrue(payload["recommended_command_is_executable"])
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertTrue(payload["recommended_command_mutates_state"])
            self.assertFalse(payload["recommended_command_requests_mac_permissions"])
            self.assertTrue(payload["recommended_command_records_audio"])
            self.assertIsNone(payload["recommended_command_plan"])
            self.assertEqual(payload["recommended_command_approval_reasons"], [])
            self.assertEqual(payload["recommended_command_approval_summary"], {})
            self.assertEqual(
                payload["readiness_summary"],
                {
                    "status": "stopped",
                    "can_capture_next": False,
                    "primary_blocker": "recorder_stopped",
                    "primary_blocker_detail": "recorder is not running",
                    "primary_recovery_command": "make doubao-shadow-start-auto",
                    "primary_recovery_command_is_executable": True,
                    "primary_recovery_requires_user_approval": True,
                    "primary_recovery_mutates_state": True,
                    "primary_recovery_requests_mac_permissions": False,
                    "primary_recovery_records_audio": True,
                    "primary_permission_target": None,
                    "permission_targets": [],
                    "permission_guidance": "",
                    "blocked_by": ["recorder_stopped"],
                    "user_action_required": True,
                    "recommended_command": "make doubao-shadow-start-auto",
                    "recommended_command_requires_user_approval": True,
                    "recommended_command_records_audio": True,
                    "recommended_command_mutates_state": True,
                    "recommended_command_requests_mac_permissions": False,
                    "recommended_command_approval_reasons": [],
                    "secondary_diagnostics_deferred_until_permissions": False,
                    "next_role": "primary_action",
                    "pending_clip_action": None,
                    "pending_clip_action_is_executable_command": False,
                    "pending_clip_action_requires_user_approval": False,
                    "pending_clip_action_mutates_state": False,
                    "pending_clip_action_requests_mac_permissions": False,
                    "pending_clip_action_records_audio": False,
                    "pending_clip_cleanup_deferred_until_permissions": False,
                    "pending_clip_action_preview": None,
                    "pending_clip_action_preview_is_executable_command": False,
                    "pending_clip_action_preview_requires_user_approval": False,
                    "pending_clip_action_preview_mutates_state": False,
                    "pending_clip_action_preview_requests_mac_permissions": False,
                    "pending_clip_action_preview_records_audio": False,
                    "preview_command": None,
                    "preview_command_is_executable": False,
                    "preview_command_requires_user_approval": False,
                    "preview_command_mutates_state": False,
                    "preview_command_requests_mac_permissions": False,
                    "preview_command_records_audio": False,
                    "preview_safe_to_run_now": False,
                    "next_safe_command": None,
                    "next_user_approval_command": "make doubao-shadow-start-auto",
                    "safe_to_run_now": False,
                    "safe_to_run_reason": "recommended command requires user approval",
                    "message": "Hearing status: stopped; not capturing new speech now (recorder is not running).",
                },
            )

    def test_print_status_reports_reference_and_manifest_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            valid_audio = root / "valid.wav"
            too_short_audio = root / "too-short.wav"
            missing_audio = root / "missing.wav"
            write_test_wav(valid_audio, seconds=0.25)
            write_test_wav(too_short_audio, seconds=0.05)
            segments.write_text(
                '{"id":"one","audio":"one.wav","reference":"Codex PR","text_capture_status":"captured","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"two","audio":"two.wav","reference":"stale","text_capture_status":"captured","recording_stop_reason":"max_duration"}\n'
                '{"id":"three","audio":"three.wav","recorded_at":"2026-05-24T05:01:02Z","text_capture_status":"unmatched","text_capture_reason":"missing_before_snapshot","text_capture_attempts":3,"text_capture_elapsed_seconds":1.02,"text_capture_before_length":7,"text_capture_after_length":9,"text_capture_before_process_identifier":11,"text_capture_after_process_identifier":11,"text_capture_before_selection_location":7,"text_capture_before_selection_length":0,"text_capture_after_selection_location":9,"text_capture_after_selection_length":0}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                f'{{"id":"one","audio":"{valid_audio}","reference":"Codex PR"}}\n'
                f'{{"id":"two","audio":"{too_short_audio}","reference":"MCP"}}\n'
                f'{{"id":"three","audio":"{missing_audio}","reference":"SeaTalk"}}\n',
                encoding="utf-8",
            )

            with patch(
                "bench.scripts.doubao_shadow_daemon.format_recorded_at_local",
                return_value="2026-05-24 13:01:02 +0800",
            ):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Captured segments: 3", output)
            self.assertIn("Captured references: 2", output)
            self.assertIn("Safe captured references: 1", output)
            self.assertIn("Needs reconciliation: 0", output)
            self.assertIn("Focused text captured: 2", output)
            self.assertIn("Focused text unmatched: 1", output)
            self.assertIn("Focused text reasons: missing_before_snapshot=1", output)
            self.assertIn(
                "Latest segment: id=three, recorded_at=2026-05-24T05:01:02Z, stop=unknown, text=unmatched/missing_before_snapshot, reference=no, audio=three.wav",
                output,
            )
            self.assertIn("Latest segment local time: 2026-05-24 13:01:02 +0800", output)
            self.assertIn(
                "Latest focused text diagnostic: attempts=3, elapsed=1.02s, before_len=7, after_len=9, before_pid=11, after_pid=11, before_sel=7+0, after_sel=9+0",
                output,
            )
            self.assertIn("Benchmark manifest samples: 3", output)
            self.assertIn("Benchmark valid audio: 1/3", output)
            self.assertIn("Benchmark missing audio: 1", output)
            self.assertIn("Benchmark too short: 1", output)
            self.assertIn("Next: make doubao-shadow-benchmark", output)

    def test_status_marks_latest_segment_recorded_before_current_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            binary = root / "SwitchTypeDoubaoShadow"
            binary.write_text("packaged shadow helper", encoding="utf-8")
            binary_mtime = datetime(2026, 5, 24, 7, 0, tzinfo=timezone.utc).timestamp()
            os.utime(binary, (binary_mtime, binary_mtime))
            (root / "shadow.config.json").write_text(
                json.dumps({"binary": str(binary)}) + "\n",
                encoding="utf-8",
            )
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:13:04Z","text_capture_status":"unmatched","text_capture_reason":"invalid_selection_range","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments)
            hearing_payload = hearing_check_payload(pid_file=pid_file, segments=segments)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments)
            with contextlib.redirect_stdout(io.StringIO()) as hearing_stdout:
                hearing_code = print_hearing_check(pid_file=pid_file, segments=segments)

            latest = payload["segments"]["latest"]
            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertEqual(hearing_code, 0)
            self.assertTrue(latest["recorded_before_current_recorder_binary"])
            self.assertEqual(latest["recorder_binary"], str(binary))
            self.assertIn("recorder_binary_mtime", latest)
            self.assertTrue(
                hearing_payload["hearing_status"]["latest_segment_recorded_before_current_recorder_binary"]
            )
            self.assertIn(
                "latest_segment_before_current_recorder_binary",
                payload["readiness_summary"]["blocked_by"],
            )
            self.assertIn(
                "latest_segment_before_current_recorder_binary",
                hearing_payload["readiness_summary"]["blocked_by"],
            )
            self.assertIn(
                "Latest segment binary freshness: recorded before current recorder binary build; rerun capture before trusting this failure reason.",
                output,
            )
            self.assertIn(
                "Latest segment binary freshness: recorded before current recorder binary build; rerun capture before trusting this failure reason.",
                hearing_stdout.getvalue(),
            )

    def test_status_payload_reports_latest_segment_age_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(
                    pid_file=pid_file,
                    segments=segments,
                    now=datetime(2026, 5, 24, 5, 1, 30, tzinfo=timezone.utc),
                )

            latest = payload["segments"]["latest"]
            self.assertEqual(latest["age_seconds"], 90)
            self.assertFalse(latest["stale"])

    def test_status_payload_reports_latest_segment_local_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch(
                "bench.scripts.doubao_shadow_daemon.format_recorded_at_local",
                return_value="2026-05-24 13:00:00 +0800",
            ):
                payload = status_payload(pid_file=pid_file, segments=segments)

            latest = payload["segments"]["latest"]
            self.assertEqual(latest["recorded_at"], "2026-05-24T05:00:00Z")
            self.assertEqual(latest["recorded_at_local"], "2026-05-24 13:00:00 +0800")

    def test_format_recorded_at_local_converts_utc_to_given_timezone(self):
        self.assertEqual(
            format_recorded_at_local(
                "2026-05-24T05:01:02Z",
                local_timezone=timezone(timedelta(hours=8)),
            ),
            "2026-05-24 13:01:02 +0800",
        )

    def test_status_payload_reports_latest_audio_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            audio = root / "latest.wav"
            write_test_wav(audio, seconds=0.5)
            segments.write_text(
                f'{{"id":"latest","audio":"{audio}","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}}\n',
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments)

            latest_audio = payload["segments"]["latest"]["audio_status"]
            self.assertEqual(latest_audio["state"], "valid")
            self.assertTrue(latest_audio["exists"])
            self.assertGreater(latest_audio["bytes"], 0)
            self.assertAlmostEqual(latest_audio["duration_seconds"], 0.5, places=2)

    def test_status_payload_reports_hotkey_event_diagnostics_from_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Debug hotkey events: enabled\n"
                "Hotkey event: source=eventTap, type=keyUp, keyCode=51, modifiers=none, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=61, modifiers=option, action=startRecording\n"
                "Hotkey event: source=modifierPoll, type=flagsChanged, keyCode=61, modifiers=none, action=finishRecording\n",
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)

            hotkey_events = payload["hotkey_events"]
            self.assertTrue(hotkey_events["enabled"])
            self.assertEqual(hotkey_events["observed"], 3)
            self.assertEqual(hotkey_events["recognized"], 2)
            self.assertEqual(hotkey_events["actions"], {"finishRecording": 1, "ignore": 1, "startRecording": 1})
            self.assertEqual(
                hotkey_events["latest_recognized"],
                {
                    "source": "modifierPoll",
                    "type": "flagsChanged",
                    "key_code": 61,
                    "modifiers": "none",
                    "action": "finishRecording",
                },
            )

    def test_print_status_reports_latest_audio_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            audio = root / "latest.wav"
            write_test_wav(audio, seconds=0.05, signal=False)
            segments.write_text(
                f'{{"id":"latest","audio":"{audio}","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Latest audio: state=silent, duration=0.05s, bytes=", output)

    def test_print_status_reports_hotkey_event_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=58, modifiers=option, action=startRecording\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, log_file=log_file)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Hotkey events observed: 1", output)
            self.assertIn("Hotkey recording events: 1", output)
            self.assertIn("Hotkey event actions: startRecording=1", output)
            self.assertIn(
                "Latest hotkey event: source=eventTap, type=flagsChanged, keyCode=58, modifiers=option, action=startRecording",
                output,
            )

    def test_print_status_suggests_fixed_duration_fallback_when_hotkey_events_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option", "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=57, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments, log_file=log_file)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertEqual(
                payload["hotkey_events"]["diagnosis"],
                "events_visible_no_recording_match",
            )
            self.assertIn(
                "Hotkey diagnosis: key events are visible, but none matched the recorder hotkey.",
                output,
            )
            self.assertIn(
                "Fixed-duration fallback: DURATION=5 make doubao-shadow-capture-once-packaged",
                output,
            )

    def test_status_reports_low_confidence_hotkey_candidate_without_restart_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            settings_root = root / "settings"
            settings_file = settings_root / "DoubaoIme" / "MMKV" / "com.apple.xpc.activity"
            settings_file.parent.mkdir(parents=True)
            settings_file.write_text(
                '{"asrShortcutKeyCode":58,"asrShortcutModifierFlags":0,"asrShortcutKeyDisplay":"Option"}',
                encoding="utf-8",
            )
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option", "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=56, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)
                compact = hearing_check_payload(
                    pid_file=pid_file,
                    segments=segments,
                    log_file=log_file,
                    doubao_settings_roots=[settings_root],
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments, log_file=log_file)
                with contextlib.redirect_stdout(io.StringIO()) as hearing_stdout:
                    hearing_code = print_hearing_check(
                        pid_file=pid_file,
                        segments=segments,
                        log_file=log_file,
                        doubao_settings_roots=[settings_root],
                    )

            hint = payload["hotkey_repair_hint"]
            compact_hint = compact["hotkey_repair_hint"]
            output = stdout.getvalue()
            hearing_output = hearing_stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertEqual(hearing_code, 0)
            self.assertTrue(hint["available"])
            self.assertTrue(compact_hint["available"])
            self.assertEqual(hint["confidence"], "low")
            self.assertEqual(
                hint["confidence_reasons"],
                ["common_shift_modifier", "candidate_count_below_threshold"],
            )
            self.assertEqual(hint["suggested_hotkey_key_code"], "56")
            self.assertEqual(compact_hint["suggested_hotkey_key_code"], "56")
            self.assertEqual(compact["doubao_settings_shortcut_hints"]["display_values"], ["Option"])
            self.assertEqual(compact["doubao_settings_shortcut_hints"]["key_codes"], [58])
            self.assertEqual(compact["doubao_settings_shortcut_hints"]["modifier_flags"], [0])
            self.assertEqual(compact["doubao_settings_shortcut_hints"]["suggested_hotkey_key_code"], "58")
            self.assertEqual(compact["doubao_settings_shortcut_hints"]["suggested_hotkey_modifiers"], "option")
            self.assertTrue(compact["shadow_hotkey_config_match"]["available"])
            self.assertTrue(compact["shadow_hotkey_config_match"]["matches"])
            self.assertEqual(compact["shadow_hotkey_config_match"]["configured_key_code"], "58")
            self.assertEqual(compact["shadow_hotkey_config_match"]["configured_modifiers"], "option")
            self.assertEqual(compact["shadow_hotkey_config_match"]["settings_key_code"], "58")
            self.assertEqual(compact["shadow_hotkey_config_match"]["settings_modifiers"], "option")
            self.assertEqual(
                compact["doubao_settings_shortcut_hints"]["visible_setting_keys"],
                ["asrShortcutKeyCode", "asrShortcutModifierFlags", "asrShortcutKeyDisplay"],
            )
            self.assertIn(str(settings_file), compact["doubao_settings_shortcut_hints"]["candidate_files"])
            self.assertEqual(hint["suggested_hotkey_modifiers"], "shift")
            self.assertEqual(compact_hint["suggested_hotkey_modifiers"], "shift")
            self.assertTrue(compact_hint["settings_conflict"])
            self.assertEqual(compact_hint["settings_expected_modifiers"], ["option"])
            self.assertEqual(compact_hint["settings_display_values"], ["Option"])
            self.assertIn("conflicts_with_doubao_settings", compact_hint["confidence_reasons"])
            self.assertIsNone(hint["command"])
            self.assertFalse(hint["command_requires_user_approval"])
            self.assertFalse(hint["command_mutates_state"])
            self.assertFalse(hint["command_records_audio"])
            self.assertFalse(hint["command_requests_mac_permissions"])
            self.assertEqual(hint["diagnostic_command"], "TIMEOUT=30 make hotkey-probe-packaged")
            self.assertTrue(hint["diagnostic_command_requires_user_approval"])
            self.assertFalse(hint["diagnostic_command_mutates_state"])
            self.assertFalse(hint["diagnostic_command_records_audio"])
            self.assertFalse(hint["diagnostic_command_requests_mac_permissions"])
            self.assertEqual(hint["diagnostic_plan_command"], "make hotkey-probe-packaged-plan-json")
            self.assertFalse(hint["diagnostic_plan_requires_user_approval"])
            self.assertFalse(hint["diagnostic_plan_mutates_state"])
            self.assertFalse(hint["diagnostic_plan_records_audio"])
            self.assertTrue(hint["diagnostic_plan_safe_to_run_now"])
            self.assertEqual(payload["recommended_command"], "TIMEOUT=30 make hotkey-probe-packaged")
            self.assertEqual(payload["recommended_command_source"], "hotkey_repair_hint.diagnostic_command")
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertFalse(payload["recommended_command_mutates_state"])
            self.assertFalse(payload["recommended_command_records_audio"])
            self.assertFalse(payload["recommended_command_requests_mac_permissions"])
            self.assertEqual(
                payload["recommended_command_approval_reasons"],
                ["listens for global hotkey events without recording audio"],
            )
            self.assertEqual(
                payload["recommended_command_plan"]["plan_command"],
                "make hotkey-probe-packaged-plan-json",
            )
            self.assertFalse(payload["recommended_command_plan"]["records_audio"])
            self.assertEqual(compact["recommended_command"], "TIMEOUT=30 make hotkey-probe-packaged")
            self.assertEqual(
                compact["recommended_command_approval_reasons"],
                ["listens for global hotkey events without recording audio"],
            )
            self.assertIn(
                "hotkey_candidate_conflicts_with_doubao_settings",
                compact["readiness_summary"]["blocked_by"],
            )
            self.assertIn("hotkey_mismatch", payload["readiness_summary"]["blocked_by"])
            self.assertEqual(
                payload["readiness_summary"]["recommended_command_approval_reasons"],
                ["listens for global hotkey events without recording audio"],
            )
            self.assertEqual(
                payload["readiness_summary"]["preview_command"],
                "make hotkey-probe-packaged-plan-json",
            )
            self.assertEqual(
                payload["readiness_summary"]["next_safe_command"],
                "make hotkey-probe-packaged-plan-json",
            )
            self.assertEqual(
                payload["readiness_summary"]["next_user_approval_command"],
                "TIMEOUT=30 make hotkey-probe-packaged",
            )
            self.assertEqual(payload["next_role"], "primary_action")
            self.assertIsNone(payload["pending_clip_action"])
            self.assertIn("Doubao settings shortcut hint: display=Option; keyCode=58; modifiers=option", hearing_output)
            self.assertIn(
                "Shadow recorder hotkey matches Doubao settings: yes (keyCode=58, modifiers=option).",
                hearing_output,
            )
            self.assertIn(
                "Hotkey repair settings conflict: Doubao settings display=Option, keyCode=58, modifiers=option; observed inferred modifiers=shift.",
                hearing_output,
            )
            self.assertIn("Hotkey repair hint: observed keyCode=56, modifiers=none; inferred modifiers=shift", output)
            self.assertIn("Hotkey repair confidence: low", output)
            self.assertIn(
                "Hotkey repair confidence reasons: common_shift_modifier, candidate_count_below_threshold",
                output,
            )
            self.assertNotIn("Hotkey repair command:", output)
            self.assertIn("Hotkey repair diagnostic plan: make hotkey-probe-packaged-plan-json", output)
            self.assertIn("Hotkey repair diagnostic plan approval: no approval needed.", output)
            self.assertIn(
                "Hotkey repair diagnostic plan safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Hotkey repair diagnostic: TIMEOUT=30 make hotkey-probe-packaged", output)
            self.assertIn("Hotkey repair diagnostic approval: user approval required before running.", output)
            self.assertIn(
                "Hotkey repair diagnostic safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Recommended command: TIMEOUT=30 make hotkey-probe-packaged", output)
            self.assertIn(
                "Recommended command source: hotkey_repair_hint.diagnostic_command",
                output,
            )
            self.assertIn(
                "Recommended command approval reasons: listens for global hotkey events without recording audio",
                output,
            )
            self.assertLess(
                output.index("Recommended command: TIMEOUT=30 make hotkey-probe-packaged"),
                output.index("Live verify: TIMEOUT=30 make doubao-shadow-live-verify"),
            )
            self.assertIn(
                "Hotkey repair caution: run this only if the observed candidate is the Doubao voice shortcut you just held.",
                output,
            )

    def test_status_reports_high_confidence_hotkey_repair_command_for_repeated_non_shift_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "49", "hotkey_modifiers": "option", "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=59, modifiers=control, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=59, modifiers=control, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(pid_file=pid_file, segments=segments, log_file=log_file)

            hint = payload["hotkey_repair_hint"]
            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertTrue(hint["available"])
            self.assertEqual(hint["confidence"], "high")
            self.assertEqual(hint["confidence_reasons"], ["candidate_repeated"])
            self.assertEqual(hint["suggested_hotkey_key_code"], "59")
            self.assertEqual(hint["suggested_hotkey_modifiers"], "control")
            self.assertEqual(
                hint["command"],
                "SWITCHTYPE_HOTKEY_KEY_CODE=59 SWITCHTYPE_HOTKEY_MODIFIERS=control make doubao-shadow-restart-packaged",
            )
            self.assertTrue(hint["command_requires_user_approval"])
            self.assertTrue(hint["command_mutates_state"])
            self.assertTrue(hint["command_records_audio"])
            self.assertFalse(hint["command_requests_mac_permissions"])
            self.assertIsNone(hint["diagnostic_command"])
            self.assertEqual(
                payload["recommended_command"],
                "SWITCHTYPE_HOTKEY_KEY_CODE=59 SWITCHTYPE_HOTKEY_MODIFIERS=control make doubao-shadow-restart-packaged",
            )
            self.assertEqual(payload["recommended_command_source"], "hotkey_repair_hint.command")
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertTrue(payload["recommended_command_mutates_state"])
            self.assertTrue(payload["recommended_command_records_audio"])
            self.assertFalse(payload["recommended_command_requests_mac_permissions"])
            self.assertIsNone(payload["recommended_command_plan"])
            self.assertIn("Hotkey repair confidence: high", output)
            self.assertIn(
                "Hotkey repair command: SWITCHTYPE_HOTKEY_KEY_CODE=59 SWITCHTYPE_HOTKEY_MODIFIERS=control make doubao-shadow-restart-packaged",
                output,
            )

    def test_status_prefers_capture_once_when_hotkey_events_do_not_match_and_no_benchmark_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"current","audio":"current.wav","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=57, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(
                    pid_file=pid_file,
                    segments=segments,
                    manifest=manifest,
                    log_file=log_file,
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                    )

            self.assertEqual(code, 0)
            self.assertEqual(payload["next"], "make doubao-shadow-reconcile-current")
            self.assertTrue(payload["next_is_executable_command"])
            self.assertTrue(payload["next_requires_user_approval"])
            self.assertEqual(
                payload["capture_readiness"]["next"],
                "DURATION=5 make doubao-shadow-capture-once-packaged",
            )
            self.assertTrue(payload["capture_readiness"]["next_is_executable_command"])
            self.assertTrue(payload["capture_readiness"]["next_requires_user_approval"])
            self.assertEqual(payload["recommended_command"], "DURATION=5 make doubao-shadow-capture-once-packaged")
            self.assertEqual(payload["recommended_command_source"], "capture_readiness.next")
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertTrue(payload["recommended_command_mutates_state"])
            self.assertTrue(payload["recommended_command_records_audio"])
            self.assertFalse(payload["recommended_command_requests_mac_permissions"])
            self.assertEqual(
                payload["recommended_command_approval_reasons"],
                ["records local microphone audio for a fixed-duration capture"],
            )
            self.assertEqual(
                payload["recommended_command_plan"]["plan_command"],
                "make doubao-shadow-capture-once-packaged-plan-json",
            )
            self.assertTrue(payload["recommended_command_plan"]["does_not_execute"])
            self.assertFalse(payload["recommended_command_plan"]["records_audio"])
            self.assertEqual(
                payload["readiness_summary"]["preview_command"],
                "make doubao-shadow-capture-once-packaged-plan-json",
            )
            self.assertEqual(
                payload["readiness_summary"]["recommended_command_approval_reasons"],
                ["records local microphone audio for a fixed-duration capture"],
            )
            self.assertTrue(payload["readiness_summary"]["recommended_command_records_audio"])
            self.assertTrue(payload["readiness_summary"]["preview_safe_to_run_now"])
            self.assertEqual(
                payload["readiness_summary"]["next_safe_command"],
                "make doubao-shadow-capture-once-packaged-plan-json",
            )
            self.assertEqual(
                payload["readiness_summary"]["next_user_approval_command"],
                "DURATION=5 make doubao-shadow-capture-once-packaged",
            )
            self.assertEqual(payload["readiness_summary"]["next_role"], "pending_clip_action")
            self.assertEqual(
                payload["readiness_summary"]["pending_clip_action"],
                "make doubao-shadow-reconcile-current",
            )
            self.assertTrue(payload["readiness_summary"]["pending_clip_action_is_executable_command"])
            self.assertTrue(payload["readiness_summary"]["pending_clip_action_requires_user_approval"])
            self.assertTrue(payload["readiness_summary"]["pending_clip_action_mutates_state"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_requests_mac_permissions"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_records_audio"])
            self.assertEqual(
                payload["readiness_summary"]["pending_clip_action_preview"],
                "make doubao-shadow-reconcile-current-plan",
            )
            self.assertTrue(payload["readiness_summary"]["pending_clip_action_preview_is_executable_command"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_preview_requires_user_approval"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_preview_mutates_state"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_preview_requests_mac_permissions"])
            self.assertFalse(payload["readiness_summary"]["pending_clip_action_preview_records_audio"])
            self.assertEqual(payload["next_role"], "pending_clip_action")
            self.assertEqual(payload["pending_clip_action"], "make doubao-shadow-reconcile-current")
            self.assertTrue(payload["pending_clip_action_is_executable_command"])
            self.assertTrue(payload["pending_clip_action_requires_user_approval"])
            self.assertTrue(payload["pending_clip_action_mutates_state"])
            self.assertFalse(payload["pending_clip_action_requests_mac_permissions"])
            self.assertFalse(payload["pending_clip_action_records_audio"])
            self.assertEqual(payload["pending_clip_action_preview"], "make doubao-shadow-reconcile-current-plan")
            self.assertFalse(payload["pending_clip_action_preview_requires_user_approval"])
            self.assertFalse(payload["pending_clip_action_preview_mutates_state"])
            self.assertFalse(payload["pending_clip_action_preview_requests_mac_permissions"])
            self.assertFalse(payload["pending_clip_action_preview_records_audio"])
            self.assertIn("Fixed-duration fallback: DURATION=5 make doubao-shadow-capture-once-packaged", stdout.getvalue())
            self.assertIn("Recommended command plan: make doubao-shadow-capture-once-packaged-plan-json", stdout.getvalue())
            self.assertIn("Pending clip action: make doubao-shadow-reconcile-current", stdout.getvalue())
            self.assertNotIn("Next: make doubao-shadow-reconcile-current", stdout.getvalue())

    def test_stale_segment_guidance_uses_fixed_duration_fallback_when_hotkey_events_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=57, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn(
                "Latest segment age: 12m ago (stale; use fixed-duration fallback because hotkey events do not match)",
                output,
            )
            self.assertNotIn("Latest segment age: 12m ago (stale; run live verify", output)
            self.assertIn("Next safe command: make doubao-shadow-capture-once-packaged-plan-json", output)
            self.assertIn("Next user-approval command: DURATION=5 make doubao-shadow-capture-once-packaged", output)

    def test_status_reports_top_ignored_hotkey_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text(
                "Hotkey event: source=eventTap, type=keyDown, keyCode=18, modifiers=none, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=55, modifiers=command, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=55, modifiers=command, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=57, modifiers=none, action=ignore\n"
                "Hotkey event: source=eventTap, type=keyUp, keyCode=18, modifiers=none, action=ignore\n",
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, log_file=log_file)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertEqual(
                payload["hotkey_events"]["ignored_candidates"][0],
                {
                    "source": "eventTap",
                    "type": "flagsChanged",
                    "key_code": 55,
                    "modifiers": "command",
                    "count": 2,
                },
            )
            self.assertIn(
                "Top ignored hotkey candidates: source=eventTap, type=flagsChanged, keyCode=55, modifiers=command, count=2",
                output,
            )

    def test_status_payload_keeps_old_hotkey_event_logs_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            log_file = root / "shadow.log"
            log_file.write_text(
                "Hotkey event: type=flagsChanged, keyCode=58, modifiers=option, action=startRecording\n",
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments, log_file=log_file)

            self.assertEqual(payload["hotkey_events"]["latest"]["source"], "unknown")

    def test_print_status_warns_when_latest_running_segment_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            pid_file.write_text("123", encoding="utf-8")
            segments.write_text(
                '{"id":"latest","audio":"latest.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Latest segment age: 12m ago (stale; run live verify, then hold the Doubao hotkey)", output)

    def test_status_prefers_live_verify_when_running_session_has_no_hotkey_events_and_latest_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                '{"debug_hotkey_events": true, "hotkey_key_code": "58", "hotkey_modifiers": "option"}\n',
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(
                    pid_file=pid_file,
                    segments=segments,
                    manifest=manifest,
                    log_file=log_file,
                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            self.assertEqual(code, 0)
            self.assertEqual(payload["hotkey_events"]["observed"], 0)
            self.assertEqual(payload["segments"]["needs_reconciliation"], 1)
            self.assertEqual(payload["next"], "make doubao-shadow-reconcile-current")
            self.assertEqual(payload["next_preview"], "make doubao-shadow-reconcile-current-plan")
            self.assertFalse(payload["next_preview_requires_user_approval"])
            self.assertFalse(payload["next_preview_mutates_state"])
            self.assertFalse(payload["next_preview_requests_mac_permissions"])
            self.assertFalse(payload["next_preview_records_audio"])
            self.assertTrue(payload["next_requires_user_approval"])
            self.assertEqual(
                payload["capture_readiness"]["next"],
                "TIMEOUT=30 make doubao-shadow-live-verify",
            )
            self.assertTrue(payload["capture_readiness"]["next_requires_user_approval"])
            self.assertEqual(payload["recommended_command"], "TIMEOUT=30 make doubao-shadow-live-verify")
            self.assertEqual(payload["recommended_command_source"], "live_verification_command")
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertFalse(payload["recommended_command_mutates_state"])
            self.assertFalse(payload["recommended_command_requests_mac_permissions"])
            self.assertFalse(payload["recommended_command_records_audio"])
            self.assertEqual(payload["recommended_command_plan"]["command"], "TIMEOUT=30 make doubao-shadow-live-verify")
            self.assertEqual(payload["recommended_command_plan"]["plan_command"], "make doubao-shadow-live-verify-plan-json")
            self.assertTrue(payload["recommended_command_plan"]["does_not_execute"])
            self.assertTrue(payload["recommended_command_plan"]["waits_for_new_shadow_segment"])
            self.assertFalse(payload["recommended_command_plan"]["records_audio"])
            self.assertEqual(
                payload["recommended_command_approval_reasons"],
                ["waits for a new shadow segment during user-triggered Doubao input"],
            )
            self.assertEqual(
                payload["recommended_command_approval_summary"],
                {
                    "requires_user_approval": True,
                    "approval_step_count": 1,
                    "steps_requiring_user_approval": [
                        {
                            "index": 2,
                            "command": "TIMEOUT=30 make doubao-shadow-wait-next-preview",
                            "approval_reason": "waits for a new shadow segment during user-triggered Doubao input",
                        }
                    ],
                    "mutating_step_indices": [],
                    "permission_prompt_step_indices": [],
                    "recording_step_indices": [],
                },
            )
            self.assertEqual(payload["readiness_summary"]["preview_command"], "make doubao-shadow-live-verify-plan-json")
            self.assertEqual(
                payload["readiness_summary"]["recommended_command_approval_reasons"],
                ["waits for a new shadow segment during user-triggered Doubao input"],
            )
            self.assertTrue(payload["readiness_summary"]["preview_safe_to_run_now"])
            self.assertEqual(payload["readiness_summary"]["next_safe_command"], "make doubao-shadow-live-verify-plan-json")
            self.assertIn("Live verify: TIMEOUT=30 make doubao-shadow-live-verify", stdout.getvalue())
            self.assertIn("Recommended command plan: make doubao-shadow-live-verify-plan-json", stdout.getvalue())
            self.assertIn("Pending clip action preview: make doubao-shadow-reconcile-current-plan", stdout.getvalue())
            self.assertIn("Pending clip action: make doubao-shadow-reconcile-current", stdout.getvalue())

    def test_capture_readiness_prefers_packaged_preflight_before_live_verify_when_packaged_session_has_no_hotkey_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            binary, _ = write_packaged_shadow_helpers(root)
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "debug_hotkey_events": True,
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(
                    pid_file=pid_file,
                    segments=segments,
                    manifest=manifest,
                    log_file=log_file,
                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            self.assertEqual(code, 0)
            self.assertEqual(payload["next"], "make doubao-shadow-reconcile-current")
            self.assertTrue(payload["next_is_executable_command"])
            self.assertTrue(payload["next_requires_user_approval"])
            self.assertIsNone(payload["live_verification_command"])
            self.assertFalse(payload["live_verification_command_requires_user_approval"])
            self.assertEqual(payload["capture_readiness"]["next"], "make doubao-shadow-preflight-packaged")
            self.assertEqual(
                payload["capture_readiness"],
                {
                    "can_capture_next": False,
                    "status": "blocked",
                    "reason": "packaged preflight required before live capture",
                    "next": "make doubao-shadow-preflight-packaged",
                    "next_is_executable_command": True,
                    "next_requires_user_approval": False,
                    "next_mutates_state": False,
                    "next_requests_mac_permissions": False,
                    "next_records_audio": False,
                },
            )
            self.assertEqual(
                payload["hearing_status"],
                {
                    "can_capture_next": False,
                    "status": "blocked",
                    "reason": "packaged preflight required before live capture",
                    "message": (
                        "Hearing status: blocked; not capturing new speech now "
                        "(packaged preflight required before live capture). "
                        "Latest segment is stale: 12m ago."
                    ),
                    "latest_segment_age_seconds": 720,
                    "latest_segment_stale": True,
                    "latest_segment_recorded_before_current_recorder_binary": True,
                },
            )
            self.assertIn(
                "Can capture next Doubao utterance: no (packaged preflight required before live capture)",
                stdout.getvalue(),
            )
            self.assertIn(
                "Hearing status: blocked; not capturing new speech now (packaged preflight required before live capture). Latest segment is stale: 12m ago.",
                stdout.getvalue(),
            )
            self.assertIn(
                "Latest segment age: 12m ago (stale; run packaged preflight before live verify)",
                stdout.getvalue(),
            )
            self.assertNotIn("Live verify: TIMEOUT=30 make doubao-shadow-live-verify", stdout.getvalue())
            self.assertIn("Next command approval: user approval required before running.", stdout.getvalue())
            self.assertIn("Next: make doubao-shadow-reconcile-current", stdout.getvalue())

    def test_status_reconciles_existing_packaged_clips_before_permission_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            binary, doctor = write_packaged_shadow_helpers(root)
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "debug_hotkey_events": True,
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = status_payload(
                    pid_file=pid_file,
                    segments=segments,
                    manifest=manifest,
                    log_file=log_file,
                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_status(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            self.assertEqual(code, 0)
            self.assertEqual(payload["segments"]["needs_reconciliation"], 1)
            self.assertEqual(payload["next"], "make doubao-shadow-reconcile-current")
            self.assertEqual(payload["next_preview"], "make doubao-shadow-reconcile-current-plan")
            self.assertFalse(payload["next_preview_requires_user_approval"])
            self.assertFalse(payload["next_requests_mac_permissions"])
            self.assertFalse(payload["next_records_audio"])
            self.assertIn("Next preview: make doubao-shadow-reconcile-current-plan", stdout.getvalue())
            self.assertIn("Next: make doubao-shadow-reconcile-current", stdout.getvalue())

    def test_hearing_check_includes_recovery_hint_when_packaged_preflight_blocks_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            binary, doctor = write_packaged_shadow_helpers(root)
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "debug_hotkey_events": True,
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                payload = hearing_check_payload(
                    pid_file=pid_file,
                    segments=segments,
                    manifest=manifest,
                    log_file=log_file,
                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                )
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = print_hearing_check(
                        pid_file=pid_file,
                        segments=segments,
                        manifest=manifest,
                        log_file=log_file,
                        now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                    )

            self.assertEqual(code, 0)
            self.assertEqual(payload["next"], "make doubao-shadow-reconcile-current")
            self.assertEqual(payload["capture_readiness"]["next"], "make doubao-shadow-preflight-packaged")
            self.assertEqual(payload["recovery_command"], "make doubao-shadow-refresh-packaged")
            self.assertTrue(payload["recovery_is_executable_command"])
            self.assertTrue(payload["recovery_requires_user_approval"])
            self.assertIn("if packaged preflight fails", payload["recovery_condition"])
            output = stdout.getvalue()
            self.assertIn("Pending clip action: make doubao-shadow-reconcile-current", output)
            self.assertIn("Capture diagnostic: make doubao-shadow-preflight-packaged", output)
            self.assertIn(
                "Pending clip action safety: mutates_state=yes, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Likely recovery if packaged preflight fails: make doubao-shadow-refresh-packaged", output)
            self.assertIn("Recovery approval: user approval required before running.", output)
            self.assertIn(
                "Recovery safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
                output,
            )

    def test_hearing_check_reports_packaged_preflight_permission_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            binary, doctor = write_packaged_shadow_helpers(root)
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "debug_hotkey_events": True,
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            doctor_payload = {
                "permissions": {
                    "microphone": "denied",
                    "accessibility": "denied",
                    "input_device_name": None,
                    "expected_input_device_name": None,
                    "expected_input_device_status": "not_enforced",
                }
            }
            completed = subprocess.CompletedProcess(
                args=["SwitchTypeDoctor", "--json"],
                returncode=0,
                stdout=json.dumps(doctor_payload),
                stderr="",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.os.access", return_value=True):
                    with patch("bench.scripts.doubao_shadow_daemon.subprocess.run", return_value=completed) as run:
                        with patch(
                            "bench.scripts.doubao_shadow_daemon.binary_supports_hotkey_probe_timeout",
                            return_value=False,
                        ):
                            payload = hearing_check_payload(
                                pid_file=pid_file,
                                segments=segments,
                                manifest=manifest,
                                log_file=log_file,
                                now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                preflight_binary=binary,
                                preflight_doctor=doctor,
                            )
                            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                                code = print_hearing_check(
                                    pid_file=pid_file,
                                    segments=segments,
                                    manifest=manifest,
                                    log_file=log_file,
                                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                    preflight_binary=binary,
                                    preflight_doctor=doctor,
                                )

            self.assertEqual(code, 0)
            self.assertTrue(payload["preflight_blockers_available"])
            self.assertEqual(
                payload["preflight_blockers"],
                ["Microphone permission: denied", "Accessibility permission: denied"],
            )
            self.assertIsNone(payload["preflight_blockers_error"])
            self.assertEqual(
                payload["preflight_input_device_detail"],
                "Expected input device: not_enforced; current=unavailable; expected=not enforced",
            )
            self.assertEqual(
                payload["preflight_input_device"],
                {
                    "status": "not_enforced",
                    "current": "unavailable",
                    "expected": "not enforced",
                },
            )
            self.assertEqual(
                payload["preflight_mac_permissions"],
                {
                    "microphone": "denied",
                    "accessibility": "denied",
                    "all_required_granted": False,
                },
            )
            self.assertIn("not DoubaoIme", payload["preflight_permission_guidance"])
            self.assertIn("SwitchType.app", payload["preflight_permission_guidance"])
            self.assertIn("SwitchTypeDoubaoShadow", payload["preflight_permission_guidance"])
            self.assertEqual(
                payload["preflight_permission_targets"],
                [
                    "SwitchType.app",
                    "SwitchTypeDoctor",
                    "SwitchTypeDoubaoShadow",
                    "Codex",
                    "Terminal",
                    "iTerm",
                    "Cursor",
                ],
            )
            self.assertEqual(payload["preflight_next"], "make doubao-shadow-refresh-packaged")
            self.assertTrue(payload["preflight_next_is_executable_command"])
            self.assertTrue(payload["preflight_next_requires_user_approval"])
            self.assertTrue(payload["preflight_next_mutates_state"])
            self.assertTrue(payload["preflight_next_requests_mac_permissions"])
            self.assertFalse(payload["preflight_next_records_audio"])
            self.assertEqual(payload["preflight_preview"], "make doubao-shadow-refresh-packaged-plan")
            self.assertTrue(payload["preflight_preview_is_executable_command"])
            self.assertFalse(payload["preflight_preview_requires_user_approval"])
            self.assertFalse(payload["preflight_preview_mutates_state"])
            self.assertFalse(payload["preflight_preview_requests_mac_permissions"])
            self.assertFalse(payload["preflight_preview_records_audio"])
            self.assertEqual(
                payload["preflight_warnings"],
                ["Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis."],
            )
            self.assertEqual(payload["recommended_command"], "make doubao-shadow-refresh-packaged")
            self.assertEqual(payload["recommended_command_source"], "preflight_next")
            self.assertTrue(payload["recommended_command_is_executable"])
            self.assertTrue(payload["recommended_command_requires_user_approval"])
            self.assertTrue(payload["recommended_command_mutates_state"])
            self.assertTrue(payload["recommended_command_requests_mac_permissions"])
            self.assertFalse(payload["recommended_command_records_audio"])
            self.assertEqual(payload["primary_blocker"], "packaged_permissions_denied")
            self.assertEqual(
                payload["primary_blocker_detail"],
                "Microphone permission: denied; Accessibility permission: denied",
            )
            self.assertEqual(payload["primary_recovery_command"], "make doubao-shadow-refresh-packaged")
            self.assertTrue(payload["primary_recovery_command_is_executable"])
            self.assertTrue(payload["primary_recovery_requires_user_approval"])
            self.assertTrue(payload["primary_recovery_mutates_state"])
            self.assertTrue(payload["primary_recovery_requests_mac_permissions"])
            self.assertFalse(payload["primary_recovery_records_audio"])
            self.assertEqual(payload["readiness_summary"]["primary_blocker"], "packaged_permissions_denied")
            self.assertEqual(
                payload["readiness_summary"]["primary_blocker_detail"],
                "Microphone permission: denied; Accessibility permission: denied",
            )
            self.assertEqual(
                payload["readiness_summary"]["primary_recovery_command"],
                "make doubao-shadow-refresh-packaged",
            )
            self.assertTrue(payload["readiness_summary"]["primary_recovery_command_is_executable"])
            self.assertTrue(payload["readiness_summary"]["primary_recovery_requires_user_approval"])
            self.assertTrue(payload["readiness_summary"]["primary_recovery_mutates_state"])
            self.assertTrue(payload["readiness_summary"]["primary_recovery_requests_mac_permissions"])
            self.assertFalse(payload["readiness_summary"]["primary_recovery_records_audio"])
            self.assertEqual(payload["readiness_summary"]["primary_permission_target"], "SwitchType.app")
            self.assertEqual(
                payload["readiness_summary"]["permission_targets"],
                [
                    "SwitchType.app",
                    "SwitchTypeDoctor",
                    "SwitchTypeDoubaoShadow",
                    "Codex",
                    "Terminal",
                    "iTerm",
                    "Cursor",
                ],
            )
            self.assertIn("not DoubaoIme", payload["readiness_summary"]["permission_guidance"])
            self.assertEqual(
                payload["readiness_summary"]["blocked_by"],
                [
                    "microphone_permission_denied",
                    "accessibility_permission_denied",
                    "packaged_preflight_required",
                    "latest_segment_stale",
                    "latest_segment_before_current_recorder_binary",
                    "stale_packaged_hotkey_probe",
                ],
            )
            self.assertTrue(payload["readiness_summary"]["user_action_required"])
            self.assertFalse(payload["readiness_summary"]["safe_to_run_now"])
            self.assertEqual(
                payload["readiness_summary"]["safe_to_run_reason"],
                "recommended command requires user approval",
            )
            self.assertFalse(payload["readiness_summary"]["recommended_command_records_audio"])
            self.assertTrue(payload["readiness_summary"]["recommended_command_mutates_state"])
            self.assertTrue(payload["readiness_summary"]["recommended_command_requests_mac_permissions"])
            self.assertEqual(payload["readiness_summary"]["preview_command"], "make doubao-shadow-refresh-packaged-plan")
            self.assertTrue(payload["readiness_summary"]["preview_command_is_executable"])
            self.assertFalse(payload["readiness_summary"]["preview_command_requires_user_approval"])
            self.assertFalse(payload["readiness_summary"]["preview_command_mutates_state"])
            self.assertFalse(payload["readiness_summary"]["preview_command_requests_mac_permissions"])
            self.assertFalse(payload["readiness_summary"]["preview_command_records_audio"])
            self.assertTrue(payload["readiness_summary"]["preview_safe_to_run_now"])
            self.assertEqual(payload["readiness_summary"]["next_safe_command"], "make doubao-shadow-refresh-packaged-plan")
            self.assertEqual(payload["readiness_summary"]["next_user_approval_command"], "make doubao-shadow-refresh-packaged")
            self.assertEqual(payload["recommended_command_plan"]["command"], "make doubao-shadow-refresh-packaged")
            self.assertTrue(payload["recommended_command_plan"]["does_not_execute"])
            self.assertEqual(
                payload["recommended_command_approval_reasons"],
                [
                    "stops the background recorder daemon",
                    "rebuilds the packaged app bundle",
                    "requests macOS Microphone/Accessibility permission prompts",
                ],
            )
            self.assertEqual(
                payload["readiness_summary"]["recommended_command_approval_reasons"],
                [
                    "stops the background recorder daemon",
                    "rebuilds the packaged app bundle",
                    "requests macOS Microphone/Accessibility permission prompts",
                ],
            )
            self.assertEqual(
                payload["recommended_command_approval_summary"],
                {
                    "requires_user_approval": True,
                    "approval_step_count": 3,
                    "steps_requiring_user_approval": [
                        {
                            "index": 1,
                            "command": "make doubao-shadow-stop",
                            "approval_reason": "stops the background recorder daemon",
                        },
                        {
                            "index": 2,
                            "command": "make package",
                            "approval_reason": "rebuilds the packaged app bundle",
                        },
                        {
                            "index": 3,
                            "command": "make app-request-permissions-packaged",
                            "approval_reason": "requests macOS Microphone/Accessibility permission prompts",
                        },
                    ],
                    "mutating_step_indices": [1, 2, 3],
                    "permission_prompt_step_indices": [3],
                    "recording_step_indices": [],
                },
            )
            self.assertEqual(
                [step["command"] for step in payload["recommended_command_plan"]["steps"]],
                [
                    "make doubao-shadow-stop",
                    "make package",
                    "make app-request-permissions-packaged",
                    "make doubao-shadow-preflight-packaged",
                ],
            )
            output = stdout.getvalue()
            self.assertIn(
                "Current packaged preflight blockers: Microphone permission: denied; Accessibility permission: denied",
                output,
            )
            self.assertIn(
                "Current packaged macOS permissions: microphone=denied, accessibility=denied, all_required_granted=no",
                output,
            )
            self.assertIn(
                "Current packaged input device: not_enforced; current=unavailable; expected=not enforced",
                output,
            )
            self.assertIn("Primary permission target: SwitchType.app", output)
            self.assertIn("Current packaged permission target:", output)
            self.assertIn("not DoubaoIme", output)
            self.assertIn("SwitchType.app", output)
            self.assertIn(
                "Current packaged preflight warning: Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis.",
                output,
            )
            self.assertIn("Current packaged preflight preview: make doubao-shadow-refresh-packaged-plan", output)
            self.assertIn(
                "Current packaged preflight preview safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
                output,
            )
            self.assertIn("Current packaged preflight next: make doubao-shadow-refresh-packaged", output)
            self.assertIn(
                "Current packaged preflight next safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
                output,
            )
            self.assertIn("Recommended command: make doubao-shadow-refresh-packaged", output)
            self.assertIn("Recommended command source: preflight_next", output)
            self.assertIn(
                "Recommended command safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
                output,
            )
            self.assertIn(
                "Recommended command approval summary: approval_steps=3, "
                "mutating_steps=1,2,3, permission_prompt_steps=3, recording_steps=none",
                output,
            )
            self.assertIn(
                "Recommended command approval reasons: stops the background recorder daemon; "
                "rebuilds the packaged app bundle; requests macOS Microphone/Accessibility permission prompts",
                output,
            )
            self.assertIn("Recommended command plan: make doubao-shadow-refresh-packaged-plan-json", output)
            self.assertIn("Next safe command: make doubao-shadow-refresh-packaged-plan", output)
            self.assertIn("Next user-approval command: make doubao-shadow-refresh-packaged", output)
            self.assertIn(
                "Recommended command plan step 3: make app-request-permissions-packaged; "
                "approval_reason=requests macOS Microphone/Accessibility permission prompts",
                output,
            )
            run.assert_called()

    def test_hearing_check_ignores_permission_blockers_when_recent_packaged_capture_proves_runtime_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            audio = root / "latest.wav"
            binary = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"
            doctor = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor"
            write_test_wav(audio, seconds=0.5)
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            doctor.write_text("#!/bin/sh\n", encoding="utf-8")
            binary_mtime = datetime(2026, 5, 24, 5, 0, 0, tzinfo=timezone.utc).timestamp()
            os.utime(binary, (binary_mtime, binary_mtime))
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                f'{{"id":"latest","audio":"{audio}","recorded_at":"2026-05-24T05:11:30Z","recording_stop_reason":"hotkey_released"}}\n',
                encoding="utf-8",
            )
            doctor_payload = {
                "permissions": {
                    "microphone": "denied",
                    "accessibility": "denied",
                    "input_device_name": None,
                    "expected_input_device_name": None,
                    "expected_input_device_status": "not_enforced",
                }
            }
            completed = subprocess.CompletedProcess(
                args=["SwitchTypeDoctor", "--json"],
                returncode=0,
                stdout=json.dumps(doctor_payload),
                stderr="",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.os.access", return_value=True):
                    with patch("bench.scripts.doubao_shadow_daemon.subprocess.run", return_value=completed):
                        with patch(
                            "bench.scripts.doubao_shadow_daemon.binary_supports_hotkey_probe_timeout",
                            return_value=True,
                        ):
                            payload = hearing_check_payload(
                                pid_file=pid_file,
                                segments=segments,
                                manifest=manifest,
                                log_file=log_file,
                                now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                preflight_binary=binary,
                                preflight_doctor=doctor,
                            )
                            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                                code = print_hearing_check(
                                    pid_file=pid_file,
                                    segments=segments,
                                    manifest=manifest,
                                    log_file=log_file,
                                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                    preflight_binary=binary,
                                    preflight_doctor=doctor,
                                )

            self.assertEqual(code, 0)
            self.assertTrue(payload["can_hear_next"])
            self.assertEqual(payload["effective_hearing_status"]["status"], "armed")
            self.assertEqual(payload["preflight_blockers"], [])
            self.assertEqual(
                payload["preflight_ignored_blockers"],
                ["Microphone permission: denied", "Accessibility permission: denied"],
            )
            self.assertIn("recent valid packaged capture", payload["preflight_blockers_ignored_reason"])
            self.assertFalse(payload["secondary_diagnostics_deferred_until_permissions"])
            self.assertIsNone(payload["primary_blocker"])
            self.assertNotEqual(payload["recommended_command"], "make app-request-permissions-packaged")
            output = stdout.getvalue()
            self.assertIn("Can hear next Doubao utterance: yes", output)
            self.assertIn("Current packaged preflight ignored blockers: Microphone permission: denied; Accessibility permission: denied", output)
            self.assertNotIn("Primary blocker: packaged_permissions_denied", output)

    def test_hearing_check_ignores_permission_blockers_when_packaged_recorder_is_armed_even_if_latest_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            audio = root / "latest.wav"
            binary = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"
            doctor = root / "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor"
            write_test_wav(audio, seconds=0.5)
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            doctor.write_text("#!/bin/sh\n", encoding="utf-8")
            binary_mtime = datetime(2026, 5, 24, 5, 0, 0, tzinfo=timezone.utc).timestamp()
            os.utime(binary, (binary_mtime, binary_mtime))
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": str(binary),
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text("Doubao shadow recorder armed.\n", encoding="utf-8")
            segments.write_text(
                f'{{"id":"latest","audio":"{audio}","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {
                        "id": "latest",
                        "audio": str(audio),
                        "reference": "已经人工确认的参考文本",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            doctor_payload = {
                "permissions": {
                    "microphone": "denied",
                    "accessibility": "denied",
                    "input_device_name": None,
                    "expected_input_device_name": None,
                    "expected_input_device_status": "not_enforced",
                }
            }
            completed = subprocess.CompletedProcess(
                args=["SwitchTypeDoctor", "--json"],
                returncode=0,
                stdout=json.dumps(doctor_payload),
                stderr="",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.os.access", return_value=True):
                    with patch("bench.scripts.doubao_shadow_daemon.subprocess.run", return_value=completed):
                        with patch(
                            "bench.scripts.doubao_shadow_daemon.binary_supports_hotkey_probe_timeout",
                            return_value=True,
                        ):
                            payload = hearing_check_payload(
                                pid_file=pid_file,
                                segments=segments,
                                manifest=manifest,
                                log_file=log_file,
                                now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                preflight_binary=binary,
                                preflight_doctor=doctor,
                            )

            self.assertTrue(payload["hearing_status"]["latest_segment_stale"])
            self.assertTrue(payload["can_hear_next"])
            self.assertEqual(payload["effective_hearing_status"]["status"], "armed")
            self.assertEqual(payload["preflight_blockers"], [])
            self.assertEqual(
                payload["preflight_ignored_blockers"],
                ["Microphone permission: denied", "Accessibility permission: denied"],
            )
            self.assertIn("packaged recorder is armed", payload["preflight_blockers_ignored_reason"])
            self.assertIsNone(payload["primary_blocker"])

    def test_hearing_check_prefers_packaged_preflight_when_hotkey_mismatch_has_permission_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            log_file = root / "shadow.log"
            pid_file.write_text("123", encoding="utf-8")
            (root / "shadow.config.json").write_text(
                json.dumps(
                    {
                        "binary": "dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow",
                        "debug_hotkey_events": True,
                        "hotkey_key_code": "58",
                        "hotkey_modifiers": "option",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file.write_text(
                "Doubao shadow recorder armed.\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=56, modifiers=shift, action=ignore\n"
                "Hotkey event: source=eventTap, type=flagsChanged, keyCode=56, modifiers=shift, action=ignore\n",
                encoding="utf-8",
            )
            segments.write_text(
                '{"id":"old-current","audio":"old-current.wav","recorded_at":"2026-05-24T05:00:00Z","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            doctor_payload = {
                "permissions": {
                    "microphone": "denied",
                    "accessibility": "denied",
                    "input_device_name": None,
                    "expected_input_device_name": None,
                    "expected_input_device_status": "not_enforced",
                }
            }
            completed = subprocess.CompletedProcess(
                args=["SwitchTypeDoctor", "--json"],
                returncode=0,
                stdout=json.dumps(doctor_payload),
                stderr="",
            )

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.os.access", return_value=True):
                    with patch("bench.scripts.doubao_shadow_daemon.subprocess.run", return_value=completed):
                        with patch(
                            "bench.scripts.doubao_shadow_daemon.binary_supports_hotkey_probe_timeout",
                            return_value=False,
                        ):
                            payload = hearing_check_payload(
                                pid_file=pid_file,
                                segments=segments,
                                manifest=manifest,
                                log_file=log_file,
                                now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                preflight_binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
                                preflight_doctor=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor"),
                            )
                            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                                code = print_hearing_check(
                                    pid_file=pid_file,
                                    segments=segments,
                                    manifest=manifest,
                                    log_file=log_file,
                                    now=datetime(2026, 5, 24, 5, 12, 0, tzinfo=timezone.utc),
                                    preflight_binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
                                    preflight_doctor=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor"),
                                )

            self.assertEqual(code, 0)
            self.assertEqual(payload["capture_readiness"]["next"], "DURATION=5 make doubao-shadow-capture-once-packaged")
            self.assertEqual(
                payload["preflight_blockers"],
                ["Microphone permission: denied", "Accessibility permission: denied"],
            )
            self.assertEqual(payload["recommended_command"], "make doubao-shadow-refresh-packaged")
            self.assertEqual(payload["recommended_command_source"], "preflight_next")
            self.assertTrue(payload["secondary_diagnostics_deferred_until_permissions"])
            self.assertTrue(payload["hotkey_repair_deferred_until_permissions"])
            self.assertTrue(payload["hotkey_repair_hint"]["deferred_until_permissions"])
            self.assertEqual(payload["hotkey_repair_hint"]["role"], "secondary_after_permissions")
            self.assertTrue(payload["pending_clip_cleanup_deferred_until_permissions"])
            self.assertEqual(payload["effective_hearing_status"]["status"], "blocked")
            self.assertIn(
                "packaged preflight blockers: Microphone permission: denied; Accessibility permission: denied",
                payload["effective_hearing_status"]["message"],
            )
            self.assertNotIn("hotkey mismatch", payload["effective_hearing_status"]["message"])
            self.assertEqual(payload["primary_blocker"], "packaged_permissions_denied")
            self.assertEqual(
                payload["primary_blocker_detail"],
                "Microphone permission: denied; Accessibility permission: denied",
            )
            self.assertEqual(payload["primary_recovery_command"], "make doubao-shadow-refresh-packaged")
            self.assertTrue(payload["primary_recovery_command_is_executable"])
            self.assertTrue(payload["primary_recovery_requires_user_approval"])
            self.assertTrue(payload["primary_recovery_mutates_state"])
            self.assertTrue(payload["primary_recovery_requests_mac_permissions"])
            self.assertFalse(payload["primary_recovery_records_audio"])
            self.assertEqual(payload["primary_permission_target"], "SwitchType.app")
            self.assertIn("SwitchTypeDoubaoShadow", payload["permission_targets"])
            self.assertIn("not DoubaoIme", payload["permission_guidance"])
            self.assertEqual(payload["readiness_summary"]["status"], "blocked")
            self.assertEqual(payload["readiness_summary"]["message"], payload["effective_hearing_status"]["message"])
            self.assertEqual(payload["readiness_summary"]["primary_blocker"], "packaged_permissions_denied")
            self.assertEqual(
                payload["readiness_summary"]["primary_blocker_detail"],
                "Microphone permission: denied; Accessibility permission: denied",
            )
            self.assertEqual(
                payload["readiness_summary"]["primary_recovery_command"],
                "make doubao-shadow-refresh-packaged",
            )
            self.assertTrue(payload["readiness_summary"]["primary_recovery_requires_user_approval"])
            self.assertTrue(payload["readiness_summary"]["primary_recovery_requests_mac_permissions"])
            self.assertFalse(payload["readiness_summary"]["primary_recovery_records_audio"])
            self.assertTrue(payload["readiness_summary"]["secondary_diagnostics_deferred_until_permissions"])
            self.assertTrue(payload["readiness_summary"]["pending_clip_cleanup_deferred_until_permissions"])
            self.assertEqual(
                payload["readiness_summary"]["blocked_by"][:2],
                ["microphone_permission_denied", "accessibility_permission_denied"],
            )
            self.assertIn("microphone_permission_denied", payload["readiness_summary"]["blocked_by"])
            self.assertIn("accessibility_permission_denied", payload["readiness_summary"]["blocked_by"])
            self.assertIn("hotkey_mismatch", payload["readiness_summary"]["blocked_by"])
            output = stdout.getvalue()
            self.assertIn(
                "Hearing status: blocked; not capturing new speech now "
                "(packaged preflight blockers: Microphone permission: denied; Accessibility permission: denied).",
                output,
            )
            self.assertNotIn(
                "Hearing status: fallback; not capturing new speech now (hotkey mismatch; use fixed-duration capture).",
                output,
            )
            self.assertLess(
                output.index("Recommended command: make doubao-shadow-refresh-packaged"),
                output.index("Secondary hotkey diagnostics after permissions:"),
            )
            self.assertIn(
                "Secondary live verify after permissions: TIMEOUT=30 make doubao-shadow-live-verify",
                output,
            )
            self.assertNotIn("Alternative live verify: TIMEOUT=30 make doubao-shadow-live-verify", output)
            self.assertIn(
                "Secondary capture diagnostic after permissions: "
                "DURATION=5 make doubao-shadow-capture-once-packaged",
                output,
            )
            self.assertNotIn(
                "Capture diagnostic: DURATION=5 make doubao-shadow-capture-once-packaged",
                output,
            )
            self.assertIn(
                "Secondary pending clip cleanup after permissions: make doubao-shadow-reconcile-current",
                output,
            )
            self.assertIn(
                "Secondary pending clip cleanup preview after permissions: "
                "make doubao-shadow-reconcile-current-plan",
                output,
            )
            self.assertNotIn("Pending clip action: make doubao-shadow-reconcile-current", output)
            self.assertIn(
                "Secondary hotkey diagnostics after permissions: resolve packaged permissions before changing hotkey config.",
                output,
            )
            self.assertIn("Secondary hotkey repair hint: observed keyCode=56", output)
            self.assertIn("Secondary hotkey repair confidence: low", output)
            self.assertIn("Secondary hotkey repair diagnostic: TIMEOUT=30 make hotkey-probe-packaged", output)
            self.assertNotIn("\nHotkey repair hint:", output)
            self.assertNotIn("\nHotkey repair diagnostic:", output)
            self.assertIn(
                "Current packaged preflight blockers: Microphone permission: denied; Accessibility permission: denied",
                output,
            )

    def test_status_prefers_partial_benchmark_when_valid_manifest_exists_despite_pending_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            valid_audio = root / "valid.wav"
            write_test_wav(valid_audio, seconds=0.25)
            segments.write_text(
                '{"id":"old","audio":"old.wav","text_capture_status":"unmatched","text_capture_reason":"unchanged","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"ready","audio":"valid.wav","reference":"Codex PR","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                f'{{"id":"ready","audio":"{valid_audio}","reference":"Codex PR"}}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Needs reconciliation: 1", output)
            self.assertIn("Benchmark valid audio: 1/1", output)
            self.assertIn("Next: make doubao-shadow-benchmark", output)

    def test_status_splits_legacy_pending_segments_from_actionable_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            segments.write_text(
                '{"id":"legacy-one","audio":"legacy-one.wav","text_capture_status":"unmatched"}\n'
                '{"id":"legacy-two","audio":"legacy-two.wav","reference":"stale","text_capture_status":"captured"}\n'
                '{"id":"current-one","audio":"current-one.wav","text_capture_status":"unmatched","recording_stop_reason":"hotkey_released"}\n'
                '{"id":"current-ready","audio":"current-ready.wav","reference":"Codex PR","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            payload = status_payload(pid_file=pid_file, segments=segments, manifest=manifest)
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertEqual(payload["segments"]["needs_reconciliation"], 1)
            self.assertEqual(payload["segments"]["legacy_pending_reconciliation"], 2)
            self.assertIn("Needs reconciliation: 1", output)
            self.assertIn("Legacy pending reconciliation: 2", output)

    def test_print_status_reconciles_before_benchmark_when_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "missing-manifest.jsonl"
            segments.write_text(
                '{"id":"one","audio":"one.wav","reference":"Codex PR","recording_stop_reason":"hotkey_released"}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Captured segments: 1", output)
            self.assertIn("Captured references: 1", output)
            self.assertIn("Benchmark manifest samples: 0", output)
            self.assertIn("Next: make doubao-shadow-reconcile-current", output)

    def test_print_status_requests_more_recording_when_manifest_has_no_valid_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            too_short_audio = root / "too-short.wav"
            write_test_wav(too_short_audio, seconds=0.05)
            segments.write_text(
                '{"id":"one","audio":"too-short.wav","reference":"Codex PR"}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                f'{{"id":"one","audio":"{too_short_audio}","reference":"Codex PR"}}\n',
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = print_status(pid_file=pid_file, segments=segments, manifest=manifest)

            output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Benchmark manifest samples: 1", output)
            self.assertIn("Benchmark valid audio: 0/1", output)
            self.assertIn("Benchmark too short: 1", output)
            self.assertIn("Next: make doubao-shadow-start-auto", output)

    def test_cli_status_json_reports_next_action_and_audio_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            segments = root / "segments.jsonl"
            manifest = root / "manifest.jsonl"
            valid_audio = root / "valid.wav"
            write_test_wav(valid_audio, seconds=0.25)
            segments.write_text(
                f'{{"id":"one","audio":"{valid_audio}","recorded_at":"2026-05-24T05:04:00Z","reference":"Codex PR","text_capture_status":"captured","recording_stop_reason":"hotkey_released"}}\n',
                encoding="utf-8",
            )
            manifest.write_text(
                f'{{"id":"one","audio":"{valid_audio}","reference":"Codex PR"}}\n',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "bench/scripts/doubao_shadow_daemon.py",
                    "--status",
                    "--json",
                    "--pid-file",
                    str(pid_file),
                    "--segments",
                    str(segments),
                    "--manifest",
                    str(manifest),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "bench"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["running"])
            self.assertIsNone(payload["pid"])
            self.assertEqual(payload["segments"]["captured"], 1)
            self.assertEqual(payload["segments"]["references"], 1)
            self.assertEqual(payload["segments"]["needs_reconciliation"], 0)
            self.assertEqual(payload["segments"]["latest"]["id"], "one")
            self.assertEqual(payload["segments"]["latest"]["recorded_at"], "2026-05-24T05:04:00Z")
            self.assertEqual(payload["segments"]["latest"]["recording_stop_reason"], "hotkey_released")
            self.assertEqual(payload["segments"]["latest"]["text"], "captured")
            self.assertEqual(payload["segments"]["latest"]["audio"], str(valid_audio))
            self.assertTrue(payload["segments"]["latest"]["has_reference"])
            self.assertEqual(payload["segments"]["focused_text"]["captured"], 1)
            self.assertEqual(payload["benchmark"]["manifest_samples"], 1)
            self.assertEqual(payload["benchmark"]["valid_audio"], 1)
            self.assertEqual(payload["benchmark"]["audio_total"], 1)
            self.assertEqual(payload["next"], "make doubao-shadow-benchmark")
            self.assertTrue(payload["next_is_executable_command"])
            self.assertFalse(payload["next_requires_user_approval"])
            self.assertFalse(payload["live_verification_command_is_executable"])
            self.assertFalse(payload["live_verification_command_requires_user_approval"])
            self.assertTrue(payload["capture_readiness"]["next_is_executable_command"])
            self.assertTrue(payload["capture_readiness"]["next_requires_user_approval"])

    def test_stop_daemon_removes_pid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "shadow.pid"
            pid_file.write_text("123", encoding="utf-8")

            with patch("bench.scripts.doubao_shadow_daemon.process_is_running", return_value=True):
                with patch("bench.scripts.doubao_shadow_daemon.os.kill") as kill:
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = stop_daemon(pid_file=pid_file)

            self.assertEqual(code, 0)
            kill.assert_called_once()
            self.assertFalse(pid_file.exists())

    def test_makefile_exposes_shadow_daemon_targets(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")
        bench_readme = Path("bench/README.md").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-start:", makefile)
        self.assertIn("doubao-shadow-start-auto:", makefile)
        self.assertIn("doubao-shadow-start-auto-packaged:", makefile)
        self.assertIn("doubao-shadow-restart-packaged:", makefile)
        self.assertIn("--binary dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow", makefile)
        self.assertIn("doubao-shadow-can-hear-me:", makefile)
        self.assertIn("doubao-shadow-can-hear-me-json:", makefile)
        self.assertIn("--hearing-check", makefile)
        self.assertIn("\t@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --hearing-check", makefile)
        self.assertIn("\t@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --hearing-check --json", makefile)
        self.assertIn("doubao-shadow-status:", makefile)
        self.assertIn("doubao-shadow-status-json:", makefile)
        self.assertIn("--status --json", makefile)
        self.assertIn("\t@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --status --json", makefile)
        self.assertIn("doubao-shadow-stop:", makefile)
        self.assertIn("doubao-shadow-capture-once-packaged-plan:", makefile)
        self.assertIn("doubao-shadow-capture-once-packaged-plan-json:", makefile)
        self.assertIn("doubao-shadow-live-verify-plan:", makefile)
        self.assertIn("doubao-shadow-live-verify-plan-json:", makefile)
        self.assertIn("doubao-shadow-reconcile-current-plan:", makefile)
        self.assertIn("doubao-shadow-reconcile-current-plan-json:", makefile)
        self.assertIn("SWITCHTYPE_HOTKEY_KEY_CODE", makefile)
        self.assertIn("SWITCHTYPE_HOTKEY_MODIFIERS", makefile)
        self.assertIn("SWITCHTYPE_CAPTURE_FOCUSED_TEXT", makefile)
        self.assertIn("bench/scripts/doubao_shadow_daemon.py", makefile)
        self.assertIn("next_is_executable_command", readme)
        self.assertIn("next_requires_user_approval", readme)
        self.assertIn("next_mutates_state", readme)
        self.assertIn("next_requests_mac_permissions", readme)
        self.assertIn("next_records_audio", readme)
        self.assertIn("live_verification_command_is_executable", readme)
        self.assertIn("live_verification_command_requires_user_approval", readme)
        self.assertIn("live_verification_command_mutates_state", readme)
        self.assertIn("live_verification_command_requests_mac_permissions", readme)
        self.assertIn("live_verification_command_records_audio", readme)
        self.assertIn("doubao-shadow-capture-once-packaged-plan-json", readme)
        self.assertIn("doubao-shadow-live-verify-plan-json", readme)
        self.assertIn("make doubao-shadow-can-hear-me", readme)
        self.assertIn("make doubao-shadow-can-hear-me-json", readme)
        self.assertIn("recovery_command", readme)
        self.assertIn("preflight_blockers", readme)
        self.assertIn("preflight_mac_permissions", readme)
        self.assertIn("preflight_input_device", readme)
        self.assertIn("preflight_input_device_detail", readme)
        self.assertIn("current packaged input device", readme)
        self.assertIn("preflight_next", readme)
        self.assertIn("preflight_next_mutates_state", readme)
        self.assertIn("preflight_next_requests_mac_permissions", readme)
        self.assertIn("preflight_next_records_audio", readme)
        self.assertIn("preflight_permission_guidance", readme)
        self.assertIn("preflight_permission_targets", readme)
        self.assertIn("preflight_preview", readme)
        self.assertIn("preflight_preview_mutates_state", readme)
        self.assertIn("preflight_preview_requests_mac_permissions", readme)
        self.assertIn("preflight_preview_records_audio", readme)
        self.assertIn("preflight_warnings", readme)
        self.assertIn("recommended_command", readme)
        self.assertIn("effective_hearing_status", readme)
        self.assertIn("secondary_diagnostics_deferred_until_permissions", readme)
        self.assertIn("pending_clip_cleanup_deferred_until_permissions", readme)
        self.assertIn("microphone_permission_denied", readme)
        self.assertIn("accessibility_permission_denied", readme)
        self.assertIn("recommended_command_approval_reasons", readme)
        self.assertIn("recommended_command_mutates_state", readme)
        self.assertIn("recommended_command_requests_mac_permissions", readme)
        self.assertIn("recommended_command_records_audio", readme)
        self.assertIn("recommended_command_plan", readme)
        self.assertIn("primary_blocker", readme)
        self.assertIn("primary_blocker_detail", readme)
        self.assertIn("primary_recovery_command", readme)
        self.assertIn("primary_permission_target", readme)
        self.assertIn("Primary blocker", readme)
        self.assertIn("Primary recovery", readme)
        self.assertIn("next_role", readme)
        self.assertIn("pending_clip_action", readme)
        self.assertIn("pending_clip_action_preview", readme)
        self.assertIn("latest_segment_before_current_recorder_binary", readme)
        self.assertIn("latest_segment_recorded_before_current_recorder_binary", readme)
        self.assertIn("readiness_summary", readme)
        self.assertIn("preview_command", readme)
        self.assertIn("preview_safe_to_run_now", readme)
        self.assertIn("next_safe_command", readme)
        self.assertIn("next_user_approval_command", readme)
        self.assertIn("Next safe command", readme)
        self.assertIn("Next user-approval command", readme)
        self.assertIn("Capture diagnostic", readme)
        self.assertIn("doubao-shadow-reconcile-current-plan", readme)
        self.assertIn("doubao-shadow-reconcile-current-plan-json", readme)
        self.assertIn("hearing_status", readme)
        self.assertIn("doubao_settings_shortcut_hints", readme)
        self.assertIn("shadow_hotkey_config_match", readme)
        self.assertIn("suggested_hotkey_key_code", readme)
        self.assertIn("suggested_hotkey_modifiers", readme)
        self.assertIn("settings_conflict", readme)
        self.assertIn("hotkey_candidate_conflicts_with_doubao_settings", readme)
        self.assertIn("Doubao settings shortcut hint", readme)
        self.assertIn("Hotkey repair settings conflict", readme)
        self.assertIn("transcript_visibility", readme)
        self.assertIn("recorded_at_local", readme)
        self.assertIn("next_is_executable_command", bench_readme)
        self.assertIn("next_requires_user_approval", bench_readme)
        self.assertIn("next_mutates_state", bench_readme)
        self.assertIn("next_requests_mac_permissions", bench_readme)
        self.assertIn("next_records_audio", bench_readme)
        self.assertIn("live_verification_command_is_executable", bench_readme)
        self.assertIn("live_verification_command_requires_user_approval", bench_readme)
        self.assertIn("live_verification_command_mutates_state", bench_readme)
        self.assertIn("live_verification_command_requests_mac_permissions", bench_readme)
        self.assertIn("live_verification_command_records_audio", bench_readme)
        self.assertIn("doubao-shadow-capture-once-packaged-plan-json", bench_readme)
        self.assertIn("doubao-shadow-live-verify-plan-json", bench_readme)
        self.assertIn("make doubao-shadow-can-hear-me", bench_readme)
        self.assertIn("make doubao-shadow-can-hear-me-json", bench_readme)
        self.assertIn("recovery_command", bench_readme)
        self.assertIn("preflight_blockers", bench_readme)
        self.assertIn("preflight_mac_permissions", bench_readme)
        self.assertIn("preflight_input_device", bench_readme)
        self.assertIn("preflight_input_device_detail", bench_readme)
        self.assertIn("current packaged input device", bench_readme)
        self.assertIn("preflight_next", bench_readme)
        self.assertIn("preflight_next_mutates_state", bench_readme)
        self.assertIn("preflight_next_requests_mac_permissions", bench_readme)
        self.assertIn("preflight_next_records_audio", bench_readme)
        self.assertIn("preflight_permission_guidance", bench_readme)
        self.assertIn("preflight_permission_targets", bench_readme)
        self.assertIn("preflight_preview", bench_readme)
        self.assertIn("preflight_preview_mutates_state", bench_readme)
        self.assertIn("preflight_preview_requests_mac_permissions", bench_readme)
        self.assertIn("preflight_preview_records_audio", bench_readme)
        self.assertIn("preflight_warnings", bench_readme)
        self.assertIn("recommended_command", bench_readme)
        self.assertIn("effective_hearing_status", bench_readme)
        self.assertIn("secondary_diagnostics_deferred_until_permissions", bench_readme)
        self.assertIn("pending_clip_cleanup_deferred_until_permissions", bench_readme)
        self.assertIn("microphone_permission_denied", bench_readme)
        self.assertIn("accessibility_permission_denied", bench_readme)
        self.assertIn("recommended_command_approval_reasons", bench_readme)
        self.assertIn("recommended_command_mutates_state", bench_readme)
        self.assertIn("recommended_command_requests_mac_permissions", bench_readme)
        self.assertIn("recommended_command_records_audio", bench_readme)
        self.assertIn("recommended_command_plan", bench_readme)
        self.assertIn("primary_blocker", bench_readme)
        self.assertIn("primary_blocker_detail", bench_readme)
        self.assertIn("primary_recovery_command", bench_readme)
        self.assertIn("primary_permission_target", bench_readme)
        self.assertIn("Primary blocker", bench_readme)
        self.assertIn("Primary recovery", bench_readme)
        self.assertIn("next_role", bench_readme)
        self.assertIn("pending_clip_action", bench_readme)
        self.assertIn("pending_clip_action_preview", bench_readme)
        self.assertIn("latest_segment_before_current_recorder_binary", bench_readme)
        self.assertIn("latest_segment_recorded_before_current_recorder_binary", bench_readme)
        self.assertIn("readiness_summary", bench_readme)
        self.assertIn("preview_command", bench_readme)
        self.assertIn("preview_safe_to_run_now", bench_readme)
        self.assertIn("next_safe_command", bench_readme)
        self.assertIn("next_user_approval_command", bench_readme)
        self.assertIn("Next safe command", bench_readme)
        self.assertIn("Next user-approval command", bench_readme)
        self.assertIn("Capture diagnostic", bench_readme)
        self.assertIn("doubao-shadow-reconcile-current-plan", bench_readme)
        self.assertIn("doubao-shadow-reconcile-current-plan-json", bench_readme)
        self.assertIn("hearing_status", bench_readme)
        self.assertIn("doubao_settings_shortcut_hints", bench_readme)
        self.assertIn("shadow_hotkey_config_match", bench_readme)
        self.assertIn("suggested_hotkey_key_code", bench_readme)
        self.assertIn("suggested_hotkey_modifiers", bench_readme)
        self.assertIn("settings_conflict", bench_readme)
        self.assertIn("hotkey_candidate_conflicts_with_doubao_settings", bench_readme)
        self.assertIn("Doubao settings shortcut hint", bench_readme)
        self.assertIn("Hotkey repair settings conflict", bench_readme)
        self.assertIn("transcript_visibility", bench_readme)
        self.assertIn("recorded_at_local", bench_readme)


if __name__ == "__main__":
    unittest.main()
