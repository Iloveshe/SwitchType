from __future__ import annotations

from pathlib import Path


GENERIC_PERMISSION_TARGETS = [
    "Codex",
    "Terminal",
    "iTerm",
    "Cursor",
    "SwitchTypeDoctor",
    "SwitchTypeDoubaoShadow",
]
PACKAGED_PERMISSION_TARGETS = [
    "SwitchType.app",
    "SwitchTypeDoctor",
    "SwitchTypeDoubaoShadow",
    "Codex",
    "Terminal",
    "iTerm",
    "Cursor",
]


def is_packaged_binary(binary: Path | str | object) -> bool:
    return "dist/SwitchType.app" in str(binary or "")


def permission_targets_for_binary(binary: Path | str | object) -> list[str]:
    if is_packaged_binary(binary):
        return list(PACKAGED_PERMISSION_TARGETS)
    return list(GENERIC_PERMISSION_TARGETS)


def permission_guidance_for_binary(
    binary: Path | str | object,
    *,
    include_refresh_recovery: bool = False,
) -> str:
    if is_packaged_binary(binary):
        guidance = (
            "Grant Microphone and Accessibility to SwitchType.app / SwitchTypeDoctor / "
            "SwitchTypeDoubaoShadow, or to Codex, Terminal, iTerm, or Cursor if macOS lists "
            "the host process instead; not DoubaoIme. If macOS does not show a prompt, run "
            "make app-permissions and enable the same process there."
        )
    else:
        guidance = (
            "Grant Microphone and Accessibility to the app/process running SwitchType shadow "
            "recording, not DoubaoIme: Codex, Terminal, iTerm, Cursor, SwitchTypeDoctor, or "
            "SwitchTypeDoubaoShadow if they appear. If macOS does not show a prompt, run "
            "make app-permissions and enable the same process there."
        )
    if include_refresh_recovery:
        guidance += (
            " Run make doubao-shadow-refresh-packaged-plan to preview the recovery steps without"
            " changing anything. Run make doubao-shadow-refresh-packaged to rebuild the bundle,"
            " request packaged permissions via make app-request-permissions-packaged, and rerun"
            " packaged preflight in order."
        )
    return guidance


def permission_blockers_present(blockers: list[str]) -> bool:
    return any(
        blocker.startswith("Microphone permission:") or blocker.startswith("Accessibility permission:")
        for blocker in blockers
    )


def permission_hint_for_blockers(
    blockers: list[str],
    binary: Path | str | object,
    *,
    include_refresh_recovery: bool = False,
) -> dict[str, object]:
    if not permission_blockers_present(blockers):
        return {
            "permission_guidance": "",
            "permission_targets": [],
        }
    return {
        "permission_guidance": permission_guidance_for_binary(
            binary,
            include_refresh_recovery=include_refresh_recovery,
        ),
        "permission_targets": permission_targets_for_binary(binary),
    }


def _display_device_name(value: object, *, empty: str) -> str:
    text = str(value or "").strip()
    return text if text else empty


def mac_permission_payload(permissions: dict[str, object]) -> dict[str, object]:
    microphone = str(permissions.get("microphone") or "unknown")
    accessibility = str(permissions.get("accessibility") or "unknown")
    return {
        "microphone": microphone,
        "accessibility": accessibility,
        "all_required_granted": microphone == "granted" and accessibility == "granted",
    }


def mac_permission_detail(permissions: dict[str, object]) -> str:
    microphone = str(permissions.get("microphone") or "unknown")
    accessibility = str(permissions.get("accessibility") or "unknown")
    all_required_granted = bool(permissions.get("all_required_granted"))
    all_required_text = "yes" if all_required_granted else "no"
    return (
        f"microphone={microphone}, "
        f"accessibility={accessibility}, "
        f"all_required_granted={all_required_text}"
    )


def expected_input_device_payload(permissions: dict[str, object]) -> dict[str, str]:
    status = str(permissions.get("expected_input_device_status") or "unknown")
    current = _display_device_name(permissions.get("input_device_name"), empty="unavailable")
    expected = _display_device_name(
        permissions.get("expected_input_device_name"),
        empty="not enforced",
    )
    return {
        "status": status,
        "current": current,
        "expected": expected,
    }


def expected_input_device_detail(permissions: dict[str, object]) -> str:
    payload = expected_input_device_payload(permissions)
    return (
        f"Expected input device: {payload['status']}; "
        f"current={payload['current']}; expected={payload['expected']}"
    )
