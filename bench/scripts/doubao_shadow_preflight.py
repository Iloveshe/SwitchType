from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from command_safety import (
        command_is_executable,
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )
except ModuleNotFoundError:
    from bench.scripts.command_safety import (
        command_is_executable,
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )

try:
    from doubao_shadow_daemon import status_payload
except ModuleNotFoundError:
    from bench.scripts.doubao_shadow_daemon import status_payload

try:
    from run_hotkey_probe import binary_supports_timeout
except ModuleNotFoundError:
    from bench.scripts.run_hotkey_probe import binary_supports_timeout

try:
    from doubao_shadow_permissions import (
        expected_input_device_detail,
        expected_input_device_payload,
        mac_permission_payload,
        permission_guidance_for_binary,
        permission_targets_for_binary,
    )
except ModuleNotFoundError:
    from bench.scripts.doubao_shadow_permissions import (
        expected_input_device_detail,
        expected_input_device_payload,
        mac_permission_payload,
        permission_guidance_for_binary,
        permission_targets_for_binary,
    )


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PreflightResult:
    checks: list[PreflightCheck]
    shadow_summary: str
    next_command: str
    shadow_hearing_status: dict[str, object] | None = None
    preview_command: str | None = None
    permission_guidance: str = ""
    permission_targets: list[str] | None = None
    warnings: list[str] | None = None
    mac_permissions: dict[str, object] | None = None
    input_device: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def permission_prompt_command(binary: Path) -> str:
    if "dist/SwitchType.app" in binary.as_posix():
        return "make app-request-permissions-packaged"
    return "make app-request-permissions"


def is_packaged_binary(binary: Path) -> bool:
    return "dist/SwitchType.app" in binary.as_posix()


def build_preflight(
    *,
    binary: Path,
    binary_executable: bool,
    doctor: dict[str, object],
    shadow: dict[str, object],
    packaged_hotkey_probe_timeout_supported: bool | None = None,
) -> PreflightResult:
    permissions = doctor.get("permissions", {})
    if not isinstance(permissions, dict):
        permissions = {}

    microphone = str(permissions.get("microphone") or "unknown")
    accessibility = str(permissions.get("accessibility") or "unknown")
    expected_input_status = str(permissions.get("expected_input_device_status") or "unknown")
    mac_permissions = mac_permission_payload(permissions)
    input_device = expected_input_device_payload(permissions)

    checks = [
        PreflightCheck(
            name="Shadow recorder binary",
            ok=binary_executable,
            detail=f"Shadow recorder binary: {binary}",
        ),
        PreflightCheck(
            name="Microphone permission",
            ok=microphone == "granted",
            detail=f"Microphone permission: {microphone}",
        ),
        PreflightCheck(
            name="Accessibility permission",
            ok=accessibility == "granted",
            detail=f"Accessibility permission: {accessibility}",
        ),
        PreflightCheck(
            name="Expected input device",
            ok=expected_input_status in {"matched", "not_enforced"},
            detail=expected_input_device_detail(permissions),
        ),
    ]

    warnings: list[str] = []
    packaged_probe_stale = False
    if is_packaged_binary(binary):
        if packaged_hotkey_probe_timeout_supported is None:
            packaged_hotkey_probe_timeout_supported = binary_supports_timeout(binary.with_name("SwitchTypeHotkeyProbe"))
        if not packaged_hotkey_probe_timeout_supported:
            packaged_probe_stale = True
            warnings.append(
                "Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis."
            )

    segments = shadow.get("segments", {})
    benchmark = shadow.get("benchmark", {})
    if not isinstance(segments, dict):
        segments = {}
    if not isinstance(benchmark, dict):
        benchmark = {}
    focused = segments.get("focused_text", {})
    if not isinstance(focused, dict):
        focused = {}
    shadow_hearing_status = shadow.get("hearing_status")
    if not isinstance(shadow_hearing_status, dict):
        shadow_hearing_status = None

    shadow_summary = (
        f"captured={segments.get('captured', 0)}, "
        f"references={segments.get('references', 0)}, "
        f"needs_reconciliation={segments.get('needs_reconciliation', 0)}, "
        f"focused_text_captured={focused.get('captured', 0)}, "
        f"valid_audio={benchmark.get('valid_audio', 0)}/{benchmark.get('audio_total', 0)}"
    )

    failing_names = {check.name for check in checks if not check.ok}
    if "Shadow recorder binary" in failing_names:
        next_command = "make swift-build"
    elif packaged_probe_stale and (
        "Microphone permission" in failing_names or "Accessibility permission" in failing_names
    ):
        next_command = "make doubao-shadow-refresh-packaged"
    elif "Microphone permission" in failing_names or "Accessibility permission" in failing_names:
        next_command = permission_prompt_command(binary)
    elif "Expected input device" in failing_names:
        next_command = "check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"
    else:
        next_command = str(shadow.get("next") or "make doubao-shadow-start-auto")
    preview_command = (
        "make doubao-shadow-refresh-packaged-plan"
        if next_command == "make doubao-shadow-refresh-packaged"
        else None
    )

    permission_guidance = ""
    permission_targets: list[str] = []
    if "Microphone permission" in failing_names or "Accessibility permission" in failing_names:
        permission_targets = permission_targets_for_binary(binary)
        permission_guidance = permission_guidance_for_binary(
            binary,
            include_refresh_recovery=packaged_probe_stale,
        )

    return PreflightResult(
        checks=checks,
        shadow_summary=shadow_summary,
        next_command=next_command,
        shadow_hearing_status=shadow_hearing_status,
        preview_command=preview_command,
        permission_guidance=permission_guidance,
        permission_targets=permission_targets,
        warnings=warnings,
        mac_permissions=mac_permissions,
        input_device=input_device,
    )


def run_doctor_json(doctor: Path) -> dict[str, object]:
    try:
        completed = subprocess.run([str(doctor), "--json"], capture_output=True, text=True, check=False)
    except OSError as error:
        raise RuntimeError(f"failed to run {doctor} --json: {error}") from error
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"{doctor} --json failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{doctor} --json returned invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{doctor} --json returned a non-object payload")
    return payload


def print_preflight(result: PreflightResult) -> int:
    print("Doubao shadow preflight")
    for check in result.checks:
        state = "PASS" if check.ok else "FAIL"
        print(f"[{state}] {check.detail}")
    for warning in result.warnings or []:
        print(f"[WARN] {warning}")
    if result.permission_targets:
        print(f"Primary permission target: {result.permission_targets[0]}")
    if result.permission_guidance:
        print(f"Permission target: {result.permission_guidance}")
    print(f"Shadow samples: {result.shadow_summary}")
    if result.shadow_hearing_status:
        message = str(result.shadow_hearing_status.get("message") or "").strip()
        if message:
            print(f"Shadow hearing: {message}")
    if result.preview_command:
        print(f"Preview: {result.preview_command}")
        print(format_command_approval("Preview", result.preview_command))
        print(
            format_command_safety(
                "Preview",
                mutates_state=command_mutates_state(result.preview_command),
                requests_mac_permissions=command_requests_mac_permissions(result.preview_command),
                records_audio=command_records_audio(result.preview_command),
            )
        )
    print(format_command_approval("Next command", result.next_command))
    print(
        format_command_safety(
            "Next command",
            mutates_state=command_mutates_state(result.next_command),
            requests_mac_permissions=command_requests_mac_permissions(result.next_command),
            records_audio=command_records_audio(result.next_command),
        )
    )
    approval_summary = recommended_command_approval_summary(result.next_command)
    if approval_summary:
        print(f"Next command approval summary: {format_approval_summary(approval_summary)}")
    plan = recommended_command_plan(result.next_command)
    if isinstance(plan, dict) and plan.get("plan_command"):
        print(f"Next command plan: {plan['plan_command']}")
        steps = plan.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                command = str(step.get("command") or "").strip()
                approval_reason = str(step.get("approval_reason") or "").strip()
                if not command or not approval_reason:
                    continue
                index = step.get("index", "?")
                print(f"Next command plan step {index}: {command}; approval_reason={approval_reason}")
    print(f"Next: {result.next_command}")
    return 0 if result.ok else 1


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def preflight_blockers(result: PreflightResult) -> list[str]:
    blockers: list[str] = []
    for check in result.checks:
        if check.ok:
            continue
        if check.name == "Microphone permission":
            blockers.append("microphone_permission_denied")
        elif check.name == "Accessibility permission":
            blockers.append("accessibility_permission_denied")
        elif check.name == "Expected input device":
            blockers.append("expected_input_device")
        elif check.name == "Shadow recorder binary":
            blockers.append("shadow_recorder_binary")

    for warning in result.warnings or []:
        if warning.startswith("Packaged hotkey probe is stale"):
            blockers.append("stale_packaged_hotkey_probe")
    return _dedupe(blockers)


def recommended_command_records_audio(command: str | None) -> bool | None:
    if not command_is_executable(command):
        return None
    if command != "make doubao-shadow-refresh-packaged":
        return command_records_audio(command)
    plan = recommended_command_plan(command)
    if not isinstance(plan, dict):
        return None
    records_audio = plan.get("records_audio")
    if records_audio is None:
        return None
    return bool(records_audio)


def recommended_command_plan(command: str | None) -> dict[str, object] | None:
    if command != "make doubao-shadow-refresh-packaged":
        return None
    try:
        from doubao_shadow_refresh_plan import build_refresh_plan
    except ModuleNotFoundError:
        from bench.scripts.doubao_shadow_refresh_plan import build_refresh_plan
    return build_refresh_plan()


def recommended_command_approval_summary(command: str | None) -> dict[str, object]:
    plan = recommended_command_plan(command)
    summary = plan.get("approval_summary") if isinstance(plan, dict) else {}
    if not isinstance(summary, dict):
        return {}
    return summary


def approval_reasons_from_summary(summary: object) -> list[str]:
    if not isinstance(summary, dict):
        return []
    steps = summary.get("steps_requiring_user_approval")
    if not isinstance(steps, list):
        return []
    reasons: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        reason = str(step.get("approval_reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def _format_step_indices(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ",".join(str(item) for item in value)


def format_approval_summary(summary: dict[str, object]) -> str:
    return (
        f"approval_steps={summary.get('approval_step_count', 0)}, "
        f"mutating_steps={_format_step_indices(summary.get('mutating_step_indices'))}, "
        f"permission_prompt_steps={_format_step_indices(summary.get('permission_prompt_step_indices'))}, "
        f"recording_steps={_format_step_indices(summary.get('recording_step_indices'))}"
    )


def _safe_to_run_reason(*, is_executable: bool, requires_approval: bool) -> str:
    if requires_approval:
        return "recommended command requires user approval"
    if is_executable:
        return "recommended command can run without user approval"
    return "recommended action is guidance, not an executable command"


def _primary_recovery_fields(command: str | None) -> dict[str, object]:
    command_text = str(command or "").strip()
    if not command_text:
        return {
            "primary_recovery_command": None,
            "primary_recovery_command_is_executable": False,
            "primary_recovery_requires_user_approval": False,
            "primary_recovery_mutates_state": False,
            "primary_recovery_requests_mac_permissions": False,
            "primary_recovery_records_audio": False,
        }
    records_audio = recommended_command_records_audio(command_text)
    return {
        "primary_recovery_command": command_text,
        "primary_recovery_command_is_executable": command_is_executable(command_text),
        "primary_recovery_requires_user_approval": command_requires_user_approval(command_text),
        "primary_recovery_mutates_state": command_mutates_state(command_text),
        "primary_recovery_requests_mac_permissions": command_requests_mac_permissions(command_text),
        "primary_recovery_records_audio": bool(records_audio),
    }


def _empty_primary_blocker_fields() -> dict[str, object]:
    fields: dict[str, object] = {
        "primary_blocker": None,
        "primary_blocker_detail": "",
    }
    fields.update(_primary_recovery_fields(None))
    return fields


def _permission_target_summary_fields(
    targets: list[str] | None,
    guidance: str,
) -> dict[str, object]:
    target_list = list(targets or [])
    return {
        "primary_permission_target": target_list[0] if target_list else None,
        "permission_targets": target_list,
        "permission_guidance": guidance if target_list else "",
    }


def preflight_primary_blocker_fields(
    result: PreflightResult,
    blocked_by: list[str],
    command: str,
) -> dict[str, object]:
    if result.ok:
        return _empty_primary_blocker_fields()

    failed_details = {check.name: check.detail for check in result.checks if not check.ok}
    fields: dict[str, object] = {
        "primary_blocker": None,
        "primary_blocker_detail": "",
    }
    fields.update(_primary_recovery_fields(command))
    permission_blockers = [
        failed_details[name]
        for name in ["Microphone permission", "Accessibility permission"]
        if name in failed_details
    ]
    if permission_blockers:
        fields["primary_blocker"] = (
            "packaged_permissions_denied"
            if command in {"make app-request-permissions-packaged", "make doubao-shadow-refresh-packaged"}
            else "mac_permissions_denied"
        )
        fields["primary_blocker_detail"] = "; ".join(permission_blockers)
        return fields
    if "shadow_recorder_binary" in blocked_by:
        fields["primary_blocker"] = "shadow_recorder_binary"
        fields["primary_blocker_detail"] = failed_details.get("Shadow recorder binary", "")
        return fields
    if "expected_input_device" in blocked_by:
        fields["primary_blocker"] = "expected_input_device"
        fields["primary_blocker_detail"] = failed_details.get("Expected input device", "")
        return fields
    if "stale_packaged_hotkey_probe" in blocked_by:
        fields["primary_blocker"] = "stale_packaged_hotkey_probe"
        fields["primary_blocker_detail"] = next(iter(result.warnings or []), "")
        return fields
    return fields


def preflight_readiness_summary(result: PreflightResult) -> dict[str, object]:
    hearing = result.shadow_hearing_status if isinstance(result.shadow_hearing_status, dict) else {}
    command = result.next_command
    is_executable = command_is_executable(command)
    requires_approval = command_requires_user_approval(command)
    approval_summary = recommended_command_approval_summary(command)
    blocked_by = preflight_blockers(result)
    can_capture_next = hearing.get("can_capture_next")
    if not isinstance(can_capture_next, bool):
        can_capture_next = False
    shadow_status = str(hearing.get("status") or "").strip()
    shadow_reason = str(hearing.get("reason") or "").strip()
    shadow_message = str(hearing.get("message") or "").strip()
    status = (shadow_status or "ready") if result.ok else "blocked"
    message = (
        shadow_message
        if result.ok and shadow_message
        else (
            "Preflight passed; recorder is ready to start."
            if result.ok
            else "Preflight blocked; resolve checks before starting recorder."
        )
    )
    underlying_shadow_fields: dict[str, object] = {}
    if not result.ok:
        if shadow_status:
            underlying_shadow_fields["underlying_shadow_status"] = shadow_status
        if shadow_reason:
            underlying_shadow_fields["underlying_shadow_reason"] = shadow_reason
        if shadow_message:
            underlying_shadow_fields["underlying_shadow_message"] = shadow_message
    preview_command = result.preview_command
    preview_is_executable = command_is_executable(preview_command)
    preview_requires_approval = command_requires_user_approval(preview_command)
    preview_mutates_state = command_mutates_state(preview_command)
    preview_requests_permissions = command_requests_mac_permissions(preview_command)
    preview_records_audio = command_records_audio(preview_command)
    preview_safe_to_run_now = bool(
        preview_is_executable
        and not preview_requires_approval
        and not preview_mutates_state
        and not preview_requests_permissions
        and not preview_records_audio
    )
    safe_to_run_now = bool(is_executable and not requires_approval)
    next_safe_command = None
    if preview_safe_to_run_now:
        next_safe_command = preview_command
    elif safe_to_run_now:
        next_safe_command = command
    next_user_approval_command = command if requires_approval else None
    primary_fields = preflight_primary_blocker_fields(result, blocked_by, command)
    permission_target_fields = _permission_target_summary_fields(
        result.permission_targets,
        result.permission_guidance,
    )
    return {
        "status": status,
        "can_capture_next": can_capture_next,
        **underlying_shadow_fields,
        **primary_fields,
        **permission_target_fields,
        "blocked_by": blocked_by,
        "user_action_required": bool(blocked_by or requires_approval),
        "recommended_command": command,
        "recommended_command_requires_user_approval": requires_approval,
        "recommended_command_records_audio": recommended_command_records_audio(command),
        "recommended_command_mutates_state": command_mutates_state(command),
        "recommended_command_requests_mac_permissions": command_requests_mac_permissions(command),
        "recommended_command_approval_reasons": approval_reasons_from_summary(approval_summary),
        "preview_command": preview_command,
        "preview_command_is_executable": preview_is_executable,
        "preview_command_requires_user_approval": preview_requires_approval,
        "preview_command_mutates_state": preview_mutates_state,
        "preview_command_requests_mac_permissions": preview_requests_permissions,
        "preview_command_records_audio": preview_records_audio,
        "preview_safe_to_run_now": preview_safe_to_run_now,
        "next_safe_command": next_safe_command,
        "next_user_approval_command": next_user_approval_command,
        "safe_to_run_now": safe_to_run_now,
        "safe_to_run_reason": _safe_to_run_reason(
            is_executable=is_executable,
            requires_approval=requires_approval,
        ),
        "message": message,
    }


def preflight_error_readiness_summary(error: str, next_command: str) -> dict[str, object]:
    is_executable = command_is_executable(next_command)
    requires_approval = command_requires_user_approval(next_command)
    safe_to_run_now = bool(is_executable and not requires_approval)
    approval_summary = recommended_command_approval_summary(next_command)
    return {
        "status": "error",
        "can_capture_next": False,
        "primary_blocker": "preflight_runtime_error",
        "primary_blocker_detail": error,
        **_primary_recovery_fields(next_command),
        **_permission_target_summary_fields(None, ""),
        "blocked_by": ["preflight_runtime_error"],
        "user_action_required": True,
        "recommended_command": next_command,
        "recommended_command_requires_user_approval": requires_approval,
        "recommended_command_records_audio": recommended_command_records_audio(next_command),
        "recommended_command_mutates_state": command_mutates_state(next_command),
        "recommended_command_requests_mac_permissions": command_requests_mac_permissions(next_command),
        "recommended_command_approval_reasons": approval_reasons_from_summary(approval_summary),
        "preview_command": None,
        "preview_command_is_executable": False,
        "preview_command_requires_user_approval": False,
        "preview_command_mutates_state": False,
        "preview_command_requests_mac_permissions": False,
        "preview_command_records_audio": False,
        "preview_safe_to_run_now": False,
        "next_safe_command": next_command if safe_to_run_now else None,
        "next_user_approval_command": next_command if requires_approval else None,
        "safe_to_run_now": safe_to_run_now,
        "safe_to_run_reason": _safe_to_run_reason(
            is_executable=is_executable,
            requires_approval=requires_approval,
        ),
        "message": error,
    }


def preflight_input_device_detail(result: PreflightResult) -> str:
    for check in result.checks:
        if check.name == "Expected input device":
            return check.detail
    return ""


def preflight_payload(result: PreflightResult) -> dict[str, object]:
    plan = recommended_command_plan(result.next_command)
    approval_summary = (
        plan.get("approval_summary")
        if isinstance(plan, dict) and isinstance(plan.get("approval_summary"), dict)
        else {}
    )
    return {
        "ok": result.ok,
        "checks": [
            {"name": check.name, "ok": check.ok, "detail": check.detail}
            for check in result.checks
        ],
        "warnings": list(result.warnings or []),
        "permission_guidance": result.permission_guidance,
        "permission_targets": list(result.permission_targets or []),
        "shadow_summary": result.shadow_summary,
        "shadow_hearing_status": result.shadow_hearing_status,
        "mac_permissions": dict(result.mac_permissions or {}),
        "input_device": dict(result.input_device or {}),
        "input_device_detail": preflight_input_device_detail(result),
        "preview": result.preview_command,
        "preview_is_executable_command": command_is_executable(result.preview_command),
        "preview_requires_user_approval": command_requires_user_approval(result.preview_command),
        "preview_mutates_state": command_mutates_state(result.preview_command),
        "preview_requests_mac_permissions": command_requests_mac_permissions(result.preview_command),
        "preview_records_audio": command_records_audio(result.preview_command),
        "next": result.next_command,
        "next_is_executable_command": command_is_executable(result.next_command),
        "next_requires_user_approval": command_requires_user_approval(result.next_command),
        "next_mutates_state": command_mutates_state(result.next_command),
        "next_requests_mac_permissions": command_requests_mac_permissions(result.next_command),
        "next_records_audio": command_records_audio(result.next_command),
        "recommended_command_plan": plan,
        "recommended_command_approval_reasons": approval_reasons_from_summary(approval_summary),
        "recommended_command_approval_summary": approval_summary,
        "readiness_summary": preflight_readiness_summary(result),
    }


def print_preflight_json(result: PreflightResult) -> int:
    print(json.dumps(preflight_payload(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 1


def preflight_error_payload(error: str, next_command: str = "make swift-build") -> dict[str, object]:
    plan = recommended_command_plan(next_command)
    approval_summary = (
        plan.get("approval_summary")
        if isinstance(plan, dict) and isinstance(plan.get("approval_summary"), dict)
        else {}
    )
    return {
        "ok": False,
        "error": error,
        "checks": [],
        "warnings": [],
        "permission_guidance": "",
        "permission_targets": [],
        "shadow_summary": "",
        "shadow_hearing_status": None,
        "mac_permissions": {},
        "input_device": {},
        "input_device_detail": "",
        "preview": None,
        "preview_is_executable_command": False,
        "preview_requires_user_approval": False,
        "preview_mutates_state": False,
        "preview_requests_mac_permissions": False,
        "preview_records_audio": False,
        "next": next_command,
        "next_is_executable_command": command_is_executable(next_command),
        "next_requires_user_approval": command_requires_user_approval(next_command),
        "next_mutates_state": command_mutates_state(next_command),
        "next_requests_mac_permissions": command_requests_mac_permissions(next_command),
        "next_records_audio": command_records_audio(next_command),
        "recommended_command_plan": plan,
        "recommended_command_approval_reasons": approval_reasons_from_summary(approval_summary),
        "recommended_command_approval_summary": approval_summary,
        "readiness_summary": preflight_error_readiness_summary(error, next_command),
    }


def print_preflight_error_json(error: str, next_command: str = "make swift-build") -> int:
    print(json.dumps(preflight_error_payload(error, next_command), ensure_ascii=False, indent=2, sort_keys=True))
    return 1


def run_preflight(
    *,
    binary: Path,
    doctor: Path,
    pid_file: Path,
    segments: Path,
    manifest: Path,
    min_duration: float,
    json_output: bool = False,
) -> int:
    try:
        doctor_payload = run_doctor_json(doctor)
        shadow_payload = status_payload(
            pid_file=pid_file,
            segments=segments,
            manifest=manifest,
            min_duration=min_duration,
        )
        result = build_preflight(
            binary=binary,
            binary_executable=os.access(binary, os.X_OK),
            doctor=doctor_payload,
            shadow=shadow_payload,
        )
    except RuntimeError as error:
        if json_output:
            return print_preflight_error_json(str(error))
        print(f"Doubao shadow preflight failed: {error}", file=sys.stderr)
        print("Next: make swift-build", file=sys.stderr)
        return 1
    if json_output:
        return print_preflight_json(result)
    return print_preflight(result)


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether the Doubao shadow recorder is ready to start.")
    parser.add_argument("--binary", default=Path("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"), type=Path)
    parser.add_argument("--doctor", default=Path("app/SwitchType/.build/debug/SwitchTypeDoctor"), type=Path)
    parser.add_argument("--pid-file", default=Path("bench/samples/doubao-shadow/shadow.pid"), type=Path)
    parser.add_argument("--segments", default=Path("bench/samples/doubao-shadow/segments.jsonl"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/doubao-shadow/manifest.jsonl"), type=Path)
    parser.add_argument("--min-duration", default=0.25, type=float)
    parser.add_argument("--json", action="store_true", help="Print machine-readable preflight JSON.")
    return parser


def main() -> int:
    args = parser().parse_args()
    return run_preflight(
        binary=args.binary,
        doctor=args.doctor,
        pid_file=args.pid_file,
        segments=args.segments,
        manifest=args.manifest,
        min_duration=args.min_duration,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
