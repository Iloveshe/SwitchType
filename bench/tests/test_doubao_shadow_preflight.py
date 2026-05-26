import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from bench.scripts.doubao_shadow_preflight import (
    build_preflight,
    print_preflight_json,
    print_preflight,
    run_doctor_json,
    run_preflight,
)


def doctor_report(
    *,
    microphone: str = "granted",
    accessibility: str = "granted",
    input_device_name: Optional[str] = "DJI MIC MINI",
    expected_input_device_name: Optional[str] = None,
    expected_input_status: str = "not_enforced",
) -> dict:
    return {
        "permissions": {
            "microphone": microphone,
            "accessibility": accessibility,
            "input_device_name": input_device_name,
            "expected_input_device_name": expected_input_device_name,
            "expected_input_device_status": expected_input_status,
            "all_required_granted": microphone == "granted" and accessibility == "granted",
            "summary": (
                f"Microphone: {microphone}, Accessibility: {accessibility}, "
                f"Input: {input_device_name or 'unavailable'}"
            ),
        },
        "asr": {
            "whisper_bin_status": "ok",
            "whisper_model_status": "ok",
        },
        "hotwords": {"status": "developer_default"},
    }


def shadow_status(
    next_command: str = "make doubao-shadow-start-auto",
    hearing_status=None,
) -> dict:
    return {
        "running": False,
        "pid": None,
        "segments": {
            "captured": 0,
            "references": 0,
            "needs_reconciliation": 0,
            "focused_text": {"captured": 0, "unmatched": 0},
        },
        "benchmark": {
            "manifest": "bench/samples/doubao-shadow/manifest.jsonl",
            "manifest_samples": 0,
            "valid_audio": 0,
            "audio_total": 0,
            "missing_audio": 0,
            "too_short": 0,
            "unreadable": 0,
            "wrong_format": 0,
            "silent": 0,
        },
        "next": next_command,
        "hearing_status": hearing_status,
    }


class DoubaoShadowPreflightTests(unittest.TestCase):
    def test_preflight_fails_when_permissions_are_not_granted(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.next_command, "make app-request-permissions")
        details = "\n".join(check.detail for check in result.checks)
        self.assertIn("Microphone permission: denied", details)
        self.assertIn("Accessibility permission: denied", details)
        self.assertIn("not DoubaoIme", result.permission_guidance)
        self.assertIn("Codex", result.permission_guidance)
        self.assertIn("SwitchTypeDoubaoShadow", result.permission_guidance)
        self.assertIn("make app-permissions", result.permission_guidance)
        self.assertEqual(
            result.permission_targets,
            [
                "Codex",
                "Terminal",
                "iTerm",
                "Cursor",
                "SwitchTypeDoctor",
                "SwitchTypeDoubaoShadow",
            ],
        )

    def test_preflight_recommends_packaged_permission_prompt_for_packaged_binary(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied"),
            shadow=shadow_status(),
            packaged_hotkey_probe_timeout_supported=True,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.next_command, "make app-request-permissions-packaged")
        self.assertEqual(
            result.permission_targets,
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

    def test_preflight_recommends_refresh_when_packaged_probe_is_stale_and_permissions_fail(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(),
            packaged_hotkey_probe_timeout_supported=False,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.next_command, "make doubao-shadow-refresh-packaged")
        self.assertEqual(result.preview_command, "make doubao-shadow-refresh-packaged-plan")
        self.assertIn("make doubao-shadow-refresh-packaged-plan", result.permission_guidance)
        self.assertIn("make doubao-shadow-refresh-packaged", result.permission_guidance)
        self.assertIn("make app-request-permissions-packaged", result.permission_guidance)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight(result)

        self.assertEqual(code, 1)
        self.assertIn("Primary permission target: SwitchType.app", stdout.getvalue())
        self.assertIn("Preview: make doubao-shadow-refresh-packaged-plan", stdout.getvalue())
        self.assertIn("Preview approval: no approval needed.", stdout.getvalue())
        self.assertIn(
            "Preview safety: mutates_state=no, requests_mac_permissions=no, records_audio=no",
            stdout.getvalue(),
        )
        self.assertIn("Next command approval: user approval required before running.", stdout.getvalue())
        self.assertIn(
            "Next command safety: mutates_state=yes, requests_mac_permissions=yes, records_audio=no",
            stdout.getvalue(),
        )
        self.assertIn(
            "Next command approval summary: approval_steps=3, "
            "mutating_steps=1,2,3, permission_prompt_steps=3, recording_steps=none",
            stdout.getvalue(),
        )
        self.assertIn("Next command plan: make doubao-shadow-refresh-packaged-plan-json", stdout.getvalue())
        self.assertIn(
            "Next command plan step 3: make app-request-permissions-packaged; "
            "approval_reason=requests macOS Microphone/Accessibility permission prompts",
            stdout.getvalue(),
        )
        self.assertIn("Next: make doubao-shadow-refresh-packaged", stdout.getvalue())

    def test_preflight_warns_when_packaged_hotkey_probe_is_stale(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(),
            shadow=shadow_status(),
            packaged_hotkey_probe_timeout_supported=False,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.next_command, "make doubao-shadow-start-auto")
        self.assertEqual(
            result.warnings,
            [
                "Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis."
            ],
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight(result)

        self.assertEqual(code, 0)
        self.assertIn(
            "[WARN] Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis.",
            stdout.getvalue(),
        )
        self.assertIn(
            "Next command safety: mutates_state=yes, requests_mac_permissions=no, records_audio=yes",
            stdout.getvalue(),
        )

    def test_preflight_passes_and_recommends_shadow_start_auto(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(),
            shadow=shadow_status(),
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.next_command, "make doubao-shadow-start-auto")
        self.assertIn("captured=0", result.shadow_summary)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight_json(result)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["next_mutates_state"])
        self.assertFalse(payload["next_requests_mac_permissions"])
        self.assertTrue(payload["next_records_audio"])
        self.assertFalse(payload["preview_mutates_state"])
        self.assertFalse(payload["preview_requests_mac_permissions"])
        self.assertFalse(payload["preview_records_audio"])
        self.assertTrue(payload["readiness_summary"]["recommended_command_records_audio"])
        self.assertTrue(payload["readiness_summary"]["recommended_command_mutates_state"])
        self.assertFalse(payload["readiness_summary"]["recommended_command_requests_mac_permissions"])
        self.assertTrue(payload["readiness_summary"]["recommended_command_requires_user_approval"])
        self.assertIsNone(payload["readiness_summary"]["primary_blocker"])
        self.assertEqual(payload["readiness_summary"]["primary_blocker_detail"], "")
        self.assertIsNone(payload["readiness_summary"]["primary_recovery_command"])
        self.assertIsNone(payload["readiness_summary"]["primary_permission_target"])
        self.assertEqual(payload["readiness_summary"]["permission_targets"], [])
        self.assertEqual(payload["readiness_summary"]["permission_guidance"], "")
        self.assertFalse(payload["readiness_summary"]["primary_recovery_command_is_executable"])
        self.assertFalse(payload["readiness_summary"]["primary_recovery_requires_user_approval"])
        self.assertFalse(payload["readiness_summary"]["primary_recovery_mutates_state"])
        self.assertFalse(payload["readiness_summary"]["primary_recovery_requests_mac_permissions"])
        self.assertFalse(payload["readiness_summary"]["primary_recovery_records_audio"])
        self.assertIsNone(payload["readiness_summary"]["next_safe_command"])
        self.assertEqual(payload["readiness_summary"]["next_user_approval_command"], "make doubao-shadow-start-auto")
        self.assertEqual(payload["recommended_command_approval_reasons"], [])

    def test_preflight_json_exposes_flat_approval_reasons_for_packaged_refresh(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(),
            packaged_hotkey_probe_timeout_supported=False,
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight_json(result)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
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
            payload["recommended_command_approval_reasons"],
        )

    def test_preflight_fails_when_expected_input_device_is_not_matched(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(
                input_device_name="MacBook Pro Microphone",
                expected_input_device_name="DJI MIC MINI",
                expected_input_status="mismatch",
            ),
            shadow=shadow_status(),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.next_command, "check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME")
        details = "\n".join(check.detail for check in result.checks)
        self.assertIn(
            "Expected input device: mismatch; current=MacBook Pro Microphone; expected=DJI MIC MINI",
            details,
        )

    def test_preflight_prints_current_input_device_when_not_enforced(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(
                input_device_name="DJI MIC MINI",
                expected_input_device_name=None,
                expected_input_status="not_enforced",
            ),
            shadow=shadow_status(),
        )

        details = "\n".join(check.detail for check in result.checks)
        self.assertIn(
            "Expected input device: not_enforced; current=DJI MIC MINI; expected=not enforced",
            details,
        )

    def test_print_preflight_includes_checks_status_and_next_command(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(),
            shadow=shadow_status(
                "make doubao-shadow-reconcile",
                hearing_status={
                    "can_capture_next": False,
                    "status": "blocked",
                    "reason": "recorder is not running",
                    "message": "Hearing status: stopped; not capturing new speech now (recorder is not running).",
                },
            ),
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight(result)

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[PASS] Shadow recorder binary", output)
        self.assertIn("Shadow samples: captured=0", output)
        self.assertIn(
            "Shadow hearing: Hearing status: stopped; not capturing new speech now (recorder is not running).",
            output,
        )
        self.assertIn("Next command approval: user approval required before running.", output)
        self.assertIn("Next: make doubao-shadow-reconcile", output)
        self.assertNotIn("Permission target:", output)

    def test_print_preflight_includes_permission_target_when_permissions_fail(self):
        result = build_preflight(
            binary=Path("shadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(),
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight(result)

        output = stdout.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("Primary permission target: Codex", output)
        self.assertIn("Permission target:", output)
        self.assertIn("not DoubaoIme", output)
        self.assertIn("Next command approval: user approval required before running.", output)

    def test_print_preflight_json_includes_preview_next_and_checks(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(
                hearing_status={
                    "can_capture_next": False,
                    "status": "blocked",
                    "reason": "packaged preflight required before live capture",
                    "message": (
                        "Hearing status: blocked; not capturing new speech now "
                        "(packaged preflight required before live capture)."
                    ),
                },
            ),
            packaged_hotkey_probe_timeout_supported=False,
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight_json(result)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["next"], "make doubao-shadow-refresh-packaged")
        self.assertTrue(payload["next_is_executable_command"])
        self.assertTrue(payload["next_requires_user_approval"])
        self.assertTrue(payload["next_mutates_state"])
        self.assertTrue(payload["next_requests_mac_permissions"])
        self.assertFalse(payload["next_records_audio"])
        self.assertEqual(payload["recommended_command_plan"]["command"], "make doubao-shadow-refresh-packaged")
        self.assertTrue(payload["recommended_command_plan"]["does_not_execute"])
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
        self.assertEqual(payload["preview"], "make doubao-shadow-refresh-packaged-plan")
        self.assertTrue(payload["preview_is_executable_command"])
        self.assertFalse(payload["preview_requires_user_approval"])
        self.assertFalse(payload["preview_mutates_state"])
        self.assertFalse(payload["preview_requests_mac_permissions"])
        self.assertFalse(payload["preview_records_audio"])
        self.assertEqual(
            payload["input_device_detail"],
            "Expected input device: not_enforced; current=DJI MIC MINI; expected=not enforced",
        )
        self.assertEqual(
            payload["input_device"],
            {
                "status": "not_enforced",
                "current": "DJI MIC MINI",
                "expected": "not enforced",
            },
        )
        self.assertEqual(
            payload["mac_permissions"],
            {
                "microphone": "denied",
                "accessibility": "denied",
                "all_required_granted": False,
            },
        )
        self.assertEqual(
            payload["shadow_hearing_status"],
            {
                "can_capture_next": False,
                "status": "blocked",
                "reason": "packaged preflight required before live capture",
                "message": (
                    "Hearing status: blocked; not capturing new speech now "
                    "(packaged preflight required before live capture)."
                ),
            },
        )
        self.assertIn("Packaged hotkey probe is stale", payload["warnings"][0])
        self.assertIn("not DoubaoIme", payload["permission_guidance"])
        self.assertEqual(
            payload["permission_targets"],
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
        self.assertIn("captured=0", payload["shadow_summary"])
        self.assertEqual(payload["checks"][0]["name"], "Shadow recorder binary")
        self.assertTrue(payload["checks"][0]["ok"])
        self.assertIn(
            {"name": "Microphone permission", "ok": False, "detail": "Microphone permission: denied"},
            payload["checks"],
        )
        self.assertEqual(
            payload["readiness_summary"],
            {
                "status": "blocked",
                "can_capture_next": False,
                "underlying_shadow_status": "blocked",
                "underlying_shadow_reason": "packaged preflight required before live capture",
                "underlying_shadow_message": (
                    "Hearing status: blocked; not capturing new speech now "
                    "(packaged preflight required before live capture)."
                ),
                "primary_blocker": "packaged_permissions_denied",
                "primary_blocker_detail": "Microphone permission: denied; Accessibility permission: denied",
                "primary_recovery_command": "make doubao-shadow-refresh-packaged",
                "primary_recovery_command_is_executable": True,
                "primary_recovery_requires_user_approval": True,
                "primary_recovery_mutates_state": True,
                "primary_recovery_requests_mac_permissions": True,
                "primary_recovery_records_audio": False,
                "primary_permission_target": "SwitchType.app",
                "permission_targets": [
                    "SwitchType.app",
                    "SwitchTypeDoctor",
                    "SwitchTypeDoubaoShadow",
                    "Codex",
                    "Terminal",
                    "iTerm",
                    "Cursor",
                ],
                "permission_guidance": result.permission_guidance,
                "blocked_by": [
                    "microphone_permission_denied",
                    "accessibility_permission_denied",
                    "stale_packaged_hotkey_probe",
                ],
                "user_action_required": True,
                "recommended_command": "make doubao-shadow-refresh-packaged",
                "recommended_command_requires_user_approval": True,
                "recommended_command_records_audio": False,
                "recommended_command_mutates_state": True,
                "recommended_command_requests_mac_permissions": True,
                "recommended_command_approval_reasons": [
                    "stops the background recorder daemon",
                    "rebuilds the packaged app bundle",
                    "requests macOS Microphone/Accessibility permission prompts",
                ],
                "preview_command": "make doubao-shadow-refresh-packaged-plan",
                "preview_command_is_executable": True,
                "preview_command_requires_user_approval": False,
                "preview_command_mutates_state": False,
                "preview_command_requests_mac_permissions": False,
                "preview_command_records_audio": False,
                "preview_safe_to_run_now": True,
                "next_safe_command": "make doubao-shadow-refresh-packaged-plan",
                "next_user_approval_command": "make doubao-shadow-refresh-packaged",
                "safe_to_run_now": False,
                "safe_to_run_reason": "recommended command requires user approval",
                "message": "Preflight blocked; resolve checks before starting recorder.",
            },
        )

    def test_preflight_summary_status_stays_blocked_when_shadow_status_is_fallback(self):
        result = build_preflight(
            binary=Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow"),
            binary_executable=True,
            doctor=doctor_report(microphone="denied", accessibility="denied"),
            shadow=shadow_status(
                hearing_status={
                    "can_capture_next": False,
                    "status": "fallback",
                    "reason": "hotkey mismatch; use fixed-duration capture",
                    "message": "Hearing status: fallback; not capturing new speech now.",
                },
            ),
            packaged_hotkey_probe_timeout_supported=False,
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = print_preflight_json(result)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        summary = payload["readiness_summary"]
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["message"], "Preflight blocked; resolve checks before starting recorder.")
        self.assertEqual(summary["primary_blocker"], "packaged_permissions_denied")
        self.assertEqual(summary["primary_permission_target"], "SwitchType.app")
        self.assertIn("SwitchTypeDoubaoShadow", summary["permission_targets"])
        self.assertIn("not DoubaoIme", summary["permission_guidance"])
        self.assertEqual(summary["underlying_shadow_status"], "fallback")
        self.assertEqual(summary["underlying_shadow_reason"], "hotkey mismatch; use fixed-duration capture")
        self.assertEqual(summary["underlying_shadow_message"], "Hearing status: fallback; not capturing new speech now.")

    def test_run_preflight_reads_doctor_json_and_shadow_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "SwitchTypeDoubaoShadow"
            doctor = root / "SwitchTypeDoctor"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            doctor.write_text("#!/bin/sh\n", encoding="utf-8")
            doctor.chmod(0o755)

            completed = type(
                "Completed",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(doctor_report()),
                    "stderr": "",
                },
            )()

            with patch("bench.scripts.doubao_shadow_preflight.subprocess.run", return_value=completed) as subprocess_run:
                with patch("bench.scripts.doubao_shadow_preflight.status_payload", return_value=shadow_status()):
                    with contextlib.redirect_stdout(io.StringIO()) as stdout:
                        code = run_preflight(
                            binary=binary,
                            doctor=doctor,
                            pid_file=root / "shadow.pid",
                            segments=root / "segments.jsonl",
                            manifest=root / "manifest.jsonl",
                            min_duration=0.25,
                        )

        self.assertEqual(code, 0)
        subprocess_run.assert_called_once_with([str(doctor), "--json"], capture_output=True, text=True, check=False)
        self.assertIn("Next: make doubao-shadow-start-auto", stdout.getvalue())

    def test_run_doctor_json_wraps_missing_doctor_as_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-doctor"

            with self.assertRaisesRegex(RuntimeError, "failed to run"):
                run_doctor_json(missing)

    def test_run_preflight_json_reports_runtime_error_as_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = run_preflight(
                    binary=root / "missing-shadow",
                    doctor=root / "missing-doctor",
                    pid_file=root / "shadow.pid",
                    segments=root / "segments.jsonl",
                    manifest=root / "manifest.jsonl",
                    min_duration=0.25,
                    json_output=True,
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("failed to run", payload["error"])
        self.assertEqual(payload["next"], "make swift-build")
        self.assertTrue(payload["next_is_executable_command"])
        self.assertFalse(payload["next_requires_user_approval"])
        self.assertTrue(payload["next_mutates_state"])
        self.assertFalse(payload["next_requests_mac_permissions"])
        self.assertFalse(payload["next_records_audio"])
        self.assertEqual(payload["preview"], None)
        self.assertFalse(payload["preview_is_executable_command"])
        self.assertFalse(payload["preview_requires_user_approval"])
        self.assertFalse(payload["preview_mutates_state"])
        self.assertFalse(payload["preview_requests_mac_permissions"])
        self.assertFalse(payload["preview_records_audio"])
        self.assertIsNone(payload["recommended_command_plan"])
        self.assertEqual(payload["recommended_command_approval_reasons"], [])
        self.assertEqual(payload["recommended_command_approval_summary"], {})
        self.assertIsNone(payload["shadow_hearing_status"])
        self.assertEqual(payload["mac_permissions"], {})
        self.assertEqual(payload["input_device_detail"], "")
        self.assertEqual(payload["input_device"], {})
        self.assertEqual(payload["permission_guidance"], "")
        self.assertEqual(payload["permission_targets"], [])
        self.assertEqual(payload["checks"], [])
        self.assertEqual(
            payload["readiness_summary"],
            {
                "status": "error",
                "can_capture_next": False,
                "primary_blocker": "preflight_runtime_error",
                "primary_blocker_detail": payload["error"],
                "primary_recovery_command": "make swift-build",
                "primary_recovery_command_is_executable": True,
                "primary_recovery_requires_user_approval": False,
                "primary_recovery_mutates_state": True,
                "primary_recovery_requests_mac_permissions": False,
                "primary_recovery_records_audio": False,
                "primary_permission_target": None,
                "permission_targets": [],
                "permission_guidance": "",
                "blocked_by": ["preflight_runtime_error"],
                "user_action_required": True,
                "recommended_command": "make swift-build",
                "recommended_command_requires_user_approval": False,
                "recommended_command_records_audio": False,
                "recommended_command_mutates_state": True,
                "recommended_command_requests_mac_permissions": False,
                "recommended_command_approval_reasons": [],
                "preview_command": None,
                "preview_command_is_executable": False,
                "preview_command_requires_user_approval": False,
                "preview_command_mutates_state": False,
                "preview_command_requests_mac_permissions": False,
                "preview_command_records_audio": False,
                "preview_safe_to_run_now": False,
                "next_safe_command": "make swift-build",
                "next_user_approval_command": None,
                "safe_to_run_now": True,
                "safe_to_run_reason": "recommended command can run without user approval",
                "message": payload["error"],
            },
        )

    def test_makefile_and_docs_expose_shadow_preflight(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")
        bench_readme = Path("bench/README.md").read_text(encoding="utf-8")

        self.assertIn("ensure-packaged-app:", makefile)
        self.assertIn("doubao-shadow-preflight:", makefile)
        self.assertIn("doubao-shadow-preflight-json:", makefile)
        self.assertIn("doubao-shadow-preflight-packaged: ensure-packaged-app", makefile)
        self.assertIn("doubao-shadow-preflight-packaged-json: ensure-packaged-app", makefile)
        self.assertIn("--json", makefile)
        self.assertIn("doubao-shadow-refresh-packaged-plan:", makefile)
        self.assertIn("bench/scripts/doubao_shadow_refresh_plan.py --human", makefile)
        self.assertIn("doubao-shadow-refresh-packaged:", makefile)
        self.assertIn("$(MAKE) doubao-shadow-stop\n\t$(MAKE) package\n\t$(MAKE) app-request-permissions-packaged\n\t$(MAKE) doubao-shadow-preflight-packaged", makefile)
        self.assertIn("doubao-shadow-start-auto: doubao-shadow-preflight", makefile)
        self.assertIn("doubao-shadow-start-auto-packaged: doubao-shadow-preflight-packaged", makefile)
        self.assertIn("bench/scripts/doubao_shadow_preflight.py", makefile)
        self.assertIn("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor", makefile)
        self.assertNotIn("doubao-shadow-preflight-packaged: package", makefile)
        self.assertIn("make doubao-shadow-preflight", readme)
        self.assertIn("make doubao-shadow-preflight-packaged-json", readme)
        self.assertIn("shadow_hearing_status", readme)
        self.assertIn("mac_permissions", readme)
        self.assertIn("permission_guidance", readme)
        self.assertIn("permission_targets", readme)
        self.assertIn("input_device", readme)
        self.assertIn("input_device_detail", readme)
        self.assertIn("readiness_summary", readme)
        self.assertIn("primary_blocker", readme)
        self.assertIn("primary_blocker_detail", readme)
        self.assertIn("primary_recovery_command", readme)
        self.assertIn("primary_permission_target", readme)
        self.assertIn("underlying_shadow_status", readme)
        self.assertIn("underlying_shadow_reason", readme)
        self.assertIn("preview_command", readme)
        self.assertIn("preview_safe_to_run_now", readme)
        self.assertIn("next_safe_command", readme)
        self.assertIn("next_user_approval_command", readme)
        self.assertIn("preview_is_executable_command", readme)
        self.assertIn("preview_mutates_state", readme)
        self.assertIn("preview_requests_mac_permissions", readme)
        self.assertIn("preview_records_audio", readme)
        self.assertIn("next_is_executable_command", readme)
        self.assertIn("next_requires_user_approval", readme)
        self.assertIn("next_mutates_state", readme)
        self.assertIn("next_requests_mac_permissions", readme)
        self.assertIn("next_records_audio", readme)
        self.assertIn("recommended_command_plan", readme)
        self.assertIn("recommended_command_approval_reasons", readme)
        self.assertIn("recommended_command_approval_summary", readme)
        self.assertIn("make doubao-shadow-refresh-packaged-plan", readme)
        self.assertIn("make doubao-shadow-refresh-packaged", readme)
        self.assertIn("make doubao-shadow-start-auto-packaged", readme)
        self.assertIn("make doubao-shadow-preflight", bench_readme)
        self.assertIn("make doubao-shadow-preflight-packaged-json", bench_readme)
        self.assertIn("shadow_hearing_status", bench_readme)
        self.assertIn("mac_permissions", bench_readme)
        self.assertIn("permission_guidance", bench_readme)
        self.assertIn("permission_targets", bench_readme)
        self.assertIn("input_device", bench_readme)
        self.assertIn("input_device_detail", bench_readme)
        self.assertIn("readiness_summary", bench_readme)
        self.assertIn("primary_blocker", bench_readme)
        self.assertIn("primary_blocker_detail", bench_readme)
        self.assertIn("primary_recovery_command", bench_readme)
        self.assertIn("primary_permission_target", bench_readme)
        self.assertIn("underlying_shadow_status", bench_readme)
        self.assertIn("underlying_shadow_reason", bench_readme)
        self.assertIn("preview_command", bench_readme)
        self.assertIn("preview_safe_to_run_now", bench_readme)
        self.assertIn("next_safe_command", bench_readme)
        self.assertIn("next_user_approval_command", bench_readme)
        self.assertIn("preview_is_executable_command", bench_readme)
        self.assertIn("preview_mutates_state", bench_readme)
        self.assertIn("preview_requests_mac_permissions", bench_readme)
        self.assertIn("preview_records_audio", bench_readme)
        self.assertIn("next_is_executable_command", bench_readme)
        self.assertIn("next_requires_user_approval", bench_readme)
        self.assertIn("next_mutates_state", bench_readme)
        self.assertIn("next_requests_mac_permissions", bench_readme)
        self.assertIn("next_records_audio", bench_readme)
        self.assertIn("recommended_command_plan", bench_readme)
        self.assertIn("recommended_command_approval_reasons", bench_readme)
        self.assertIn("recommended_command_approval_summary", bench_readme)
        self.assertIn("make doubao-shadow-refresh-packaged-plan", bench_readme)
        self.assertIn("make doubao-shadow-refresh-packaged", bench_readme)
        self.assertIn("Packaged hotkey probe is stale", readme)
        self.assertIn("Packaged hotkey probe is stale", bench_readme)

    def test_permission_script_names_the_processes_to_grant_not_doubao(self):
        script = Path("scripts/open_app_permissions.sh").read_text(encoding="utf-8")

        self.assertIn("not DoubaoIme", script)
        self.assertIn("Codex", script)
        self.assertIn("SwitchTypeDoubaoShadow", script)


if __name__ == "__main__":
    unittest.main()
