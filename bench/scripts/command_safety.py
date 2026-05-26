from __future__ import annotations

import re
import shlex


USER_APPROVAL_COMMAND_MARKERS = (
    "app-permissions",
    "app-request-permissions",
    "doubao-shadow-capture",
    "doubao-shadow-live-verify",
    "doubao-shadow-record",
    "doubao-shadow-reconcile",
    "doubao-shadow-import-review",
    "doubao-shadow-review-sheet",
    "doubao-shadow-refresh-packaged",
    "doubao-shadow-restart",
    "doubao-shadow-start",
    "doubao-shadow-stop",
    "doubao-shadow-wait-next",
    "hotkey-probe",
    "make package",
)

AUDIO_RECORDING_COMMAND_MARKERS = (
    "doubao-shadow-capture",
    "doubao-shadow-record",
    "doubao-shadow-restart",
    "doubao-shadow-start",
)

STATE_MUTATING_COMMAND_MARKERS = (
    "app-permissions",
    "app-request-permissions",
    "doubao-shadow-capture",
    "doubao-shadow-record",
    "doubao-shadow-reconcile",
    "doubao-shadow-import-review",
    "doubao-shadow-review-sheet",
    "doubao-shadow-refresh-packaged",
    "doubao-shadow-restart",
    "doubao-shadow-start",
    "doubao-shadow-stop",
    "make package",
    "make swift-build",
)

MAC_PERMISSION_COMMAND_MARKERS = (
    "app-permissions",
    "app-request-permissions",
    "doubao-shadow-refresh-packaged",
)

NON_MUTATING_PLAN_COMMAND_PREFIXES = (
    "make doubao-shadow-capture-once-packaged-plan",
    "make doubao-shadow-refresh-packaged-plan",
    "make doubao-shadow-live-verify-plan",
    "make doubao-shadow-reconcile-current-plan",
    "make doubao-shadow-reconcile-plan",
    "make hotkey-probe-packaged-plan",
)

ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
SHELL_CONTROL_PATTERN = re.compile(r"[;&|<>`]|[$][(]")


def _tokenize_command(command: str | None) -> list[str]:
    if not command:
        return []
    if SHELL_CONTROL_PATTERN.search(command):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _make_tokens(command: str | None) -> list[str]:
    tokens = _tokenize_command(command)
    index = 0
    while index < len(tokens) and ENV_ASSIGNMENT_PATTERN.match(tokens[index]):
        index += 1
    if index < len(tokens) and tokens[index] == "make":
        return tokens[index:]
    return []


def _normalized_make_command(command: str | None) -> str:
    return " ".join(_make_tokens(command))


def command_is_executable(command: str | None) -> bool:
    if not command:
        return False
    return bool(_make_tokens(command))


def command_requires_user_approval(command: str | None) -> bool:
    if not command:
        return False
    normalized = _normalized_make_command(command)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in NON_MUTATING_PLAN_COMMAND_PREFIXES):
        return False
    return any(marker in normalized for marker in USER_APPROVAL_COMMAND_MARKERS)


def command_records_audio(command: str | None) -> bool:
    normalized = _normalized_make_command(command)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in NON_MUTATING_PLAN_COMMAND_PREFIXES):
        return False
    return any(marker in normalized for marker in AUDIO_RECORDING_COMMAND_MARKERS)


def command_mutates_state(command: str | None) -> bool:
    normalized = _normalized_make_command(command)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in NON_MUTATING_PLAN_COMMAND_PREFIXES):
        return False
    return any(marker in normalized for marker in STATE_MUTATING_COMMAND_MARKERS)


def command_requests_mac_permissions(command: str | None) -> bool:
    normalized = _normalized_make_command(command)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in NON_MUTATING_PLAN_COMMAND_PREFIXES):
        return False
    return any(marker in normalized for marker in MAC_PERMISSION_COMMAND_MARKERS)


def format_command_approval(prefix: str, command: str | None) -> str:
    if not command_is_executable(command):
        return f"{prefix} approval: guidance, not an executable command."
    if command_requires_user_approval(command):
        return f"{prefix} approval: user approval required before running."
    return f"{prefix} approval: no approval needed."


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def format_command_safety(
    prefix: str,
    *,
    mutates_state: object,
    requests_mac_permissions: object,
    records_audio: object,
) -> str:
    return (
        f"{prefix} safety: "
        f"mutates_state={_yes_no(mutates_state)}, "
        f"requests_mac_permissions={_yes_no(requests_mac_permissions)}, "
        f"records_audio={_yes_no(records_audio)}"
    )
