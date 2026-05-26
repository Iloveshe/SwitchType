from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, tzinfo
import errno
import json
import os
import re
import signal
import subprocess
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
    from sample_status import classify_audio, collect_status
except ModuleNotFoundError:
    from bench.scripts.sample_status import classify_audio, collect_status

try:
    from doubao_shadow_permissions import (
        expected_input_device_detail,
        expected_input_device_payload,
        mac_permission_detail,
        mac_permission_payload,
        permission_hint_for_blockers,
    )
except ModuleNotFoundError:
    from bench.scripts.doubao_shadow_permissions import (
        expected_input_device_detail,
        expected_input_device_payload,
        mac_permission_detail,
        mac_permission_payload,
        permission_hint_for_blockers,
    )

try:
    from watch_doubao_audio import build_settings_probe_report, default_settings_roots
except ModuleNotFoundError:
    from bench.scripts.watch_doubao_audio import build_settings_probe_report, default_settings_roots


DEFAULT_PACKAGED_SHADOW_BINARY = Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow")
DEFAULT_PACKAGED_DOCTOR_BINARY = Path("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor")
TRANSCRIPT_VISIBILITY = (
    "inserted text is only visible after Doubao pastes it into the active field; "
    "this check is about local audio capture."
)
LATEST_SEGMENT_BINARY_FRESHNESS_MESSAGE = (
    "Latest segment binary freshness: recorded before current recorder binary build; "
    "rerun capture before trusting this failure reason."
)


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError as error:
        if isinstance(error, PermissionError) or error.errno == errno.EPERM:
            return True
        return False


def read_pid(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def start_daemon(
    binary: Path,
    output_dir: Path,
    segments: Path,
    pid_file: Path,
    log_file: Path,
    expected_input_device: str | None,
    hotkey_key_code: str | None,
    hotkey_modifiers: str | None,
    capture_focused_text: bool,
    text_capture_delay_seconds: str | None,
    text_capture_timeout_seconds: str | None = None,
    debug_hotkey_events: bool = False,
) -> int:
    pid = read_pid(pid_file)
    if pid and process_is_running(pid):
        print(f"Doubao shadow recorder already running: pid {pid}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    segments.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        str(binary),
        "--output-dir",
        str(output_dir),
        "--segments",
        str(segments),
    ]
    if expected_input_device:
        command.extend(["--expected-input-device", expected_input_device])
    if hotkey_key_code:
        command.extend(["--hotkey-key-code", hotkey_key_code])
    if hotkey_modifiers:
        command.extend(["--hotkey-modifiers", hotkey_modifiers])
    if capture_focused_text:
        command.append("--capture-focused-text")
    if debug_hotkey_events:
        command.append("--debug-hotkey-events")
    if text_capture_delay_seconds:
        command.extend(["--text-capture-delay-seconds", text_capture_delay_seconds])
    if text_capture_timeout_seconds:
        command.extend(["--text-capture-timeout-seconds", text_capture_timeout_seconds])

    config_file = pid_file.with_name("shadow.config.json")
    config_file.write_text(
        json.dumps(
            {
                "binary": str(binary),
                "hotkey_key_code": hotkey_key_code or "49",
                "hotkey_modifiers": hotkey_modifiers or "option",
                "capture_focused_text": capture_focused_text,
                "debug_hotkey_events": debug_hotkey_events,
                "expected_input_device": expected_input_device,
                "text_capture_delay_seconds": text_capture_delay_seconds,
                "text_capture_timeout_seconds": text_capture_timeout_seconds,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with log_file.open("ab") as log, open(os.devnull, "rb") as stdin:
        process = subprocess.Popen(
            command,
            stdin=stdin,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(process.pid), encoding="utf-8")
    print(f"Started Doubao shadow recorder: pid {process.pid}")
    print(f"Log: {log_file}")
    print(f"Segments: {segments}")
    return 0


def stop_daemon(pid_file: Path) -> int:
    pid = read_pid(pid_file)
    if not pid:
        print("Doubao shadow recorder is not running.")
        return 0
    if process_is_running(pid):
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Doubao shadow recorder: pid {pid}")
    else:
        print(f"Doubao shadow recorder pid file was stale: pid {pid}")
    pid_file.unlink(missing_ok=True)
    return 0


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def read_config(pid_file: Path) -> dict[str, object]:
    path = pid_file.with_name("shadow.config.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "binary": str(data.get("binary") or "app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"),
        "hotkey_key_code": str(data.get("hotkey_key_code") or "49"),
        "hotkey_modifiers": str(data.get("hotkey_modifiers") or "option"),
        "capture_focused_text": bool(data.get("capture_focused_text")),
        "debug_hotkey_events": bool(data.get("debug_hotkey_events")),
        "expected_input_device": data.get("expected_input_device"),
        "text_capture_delay_seconds": data.get("text_capture_delay_seconds"),
        "text_capture_timeout_seconds": data.get("text_capture_timeout_seconds"),
    }


def is_packaged_binary_path(value: object) -> bool:
    return "dist/SwitchType.app" in str(value or "")


SAFE_CAPTURE_STOP_REASONS = {"hotkey_released", "record_seconds"}


def has_safe_capture_stop_reason(row: dict[str, object]) -> bool:
    return str(row.get("recording_stop_reason") or "").strip() in SAFE_CAPTURE_STOP_REASONS


def has_recording_stop_reason(row: dict[str, object]) -> bool:
    return bool(str(row.get("recording_stop_reason") or "").strip())


def needs_reference(row: dict[str, object], manifest_sample_ids: set[str]) -> bool:
    if str(row.get("id") or "").strip() in manifest_sample_ids:
        return False
    return not (
        str(row.get("reference") or "").strip()
        and has_safe_capture_stop_reason(row)
    )


def latest_focused_text_diagnostic(segment_rows: list[dict[str, object]]) -> dict[str, object]:
    for row in reversed(segment_rows):
        if not str(row.get("text_capture_status") or "").strip():
            continue
        keys = [
            "text_capture_attempts",
            "text_capture_elapsed_seconds",
            "text_capture_before_length",
            "text_capture_after_length",
            "text_capture_before_process_identifier",
            "text_capture_after_process_identifier",
            "text_capture_before_selection_location",
            "text_capture_before_selection_length",
            "text_capture_after_selection_location",
            "text_capture_after_selection_length",
        ]
        diagnostic = {key: row.get(key) for key in keys if row.get(key) is not None}
        if diagnostic:
            return diagnostic
    return {}


HOTKEY_EVENT_PATTERN = re.compile(
    r"Hotkey event: (?:source=(?P<source>\w+), )?type=(?P<type>.*?), keyCode=(?P<key_code>\d+), modifiers=(?P<modifiers>.*?), action=(?P<action>\w+)"
)


def parse_hotkey_event(line: str) -> dict[str, object] | None:
    match = HOTKEY_EVENT_PATTERN.search(line)
    if not match:
        return None
    return {
        "source": match.group("source") or "unknown",
        "type": match.group("type"),
        "key_code": int(match.group("key_code")),
        "modifiers": match.group("modifiers"),
        "action": match.group("action"),
    }


def summarize_ignored_hotkey_candidates(
    events: list[dict[str, object]],
    limit: int = 5,
) -> list[dict[str, object]]:
    ignored_events = [
        event
        for event in events
        if str(event.get("action") or "") == "ignore"
    ]
    interesting_events = [
        event
        for event in ignored_events
        if str(event.get("type") or "") == "flagsChanged"
        or str(event.get("modifiers") or "") != "none"
        or str(event.get("source") or "") == "modifierPoll"
    ]
    candidates = interesting_events or ignored_events
    counts = Counter(
        (
            str(event.get("source") or "unknown"),
            str(event.get("type") or "unknown"),
            int(event.get("key_code") or 0),
            str(event.get("modifiers") or "unknown"),
        )
        for event in candidates
    )
    return [
        {
            "source": source,
            "type": event_type,
            "key_code": key_code,
            "modifiers": modifiers,
            "count": count,
        }
        for (source, event_type, key_code, modifiers), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1], item[0][2], item[0][3]),
        )[:limit]
    ]


def format_ignored_hotkey_candidates(candidates: object) -> str | None:
    if not isinstance(candidates, list) or not candidates:
        return None
    parts = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        parts.append(
            ", ".join(
                [
                    f"source={candidate.get('source', 'unknown')}",
                    f"type={candidate.get('type', 'unknown')}",
                    f"keyCode={candidate.get('key_code', 'unknown')}",
                    f"modifiers={candidate.get('modifiers', 'unknown')}",
                    f"count={candidate.get('count', 0)}",
                ]
            )
        )
    if not parts:
        return None
    return "Top ignored hotkey candidates: " + "; ".join(parts)


MODIFIER_KEY_CODE_NAMES = {
    56: "shift",
    60: "shift",
    58: "option",
    61: "option",
    59: "control",
    62: "control",
    54: "command",
    55: "command",
}
SHORTCUT_DISPLAY_MODIFIERS = {
    "option": "option",
    "shift": "shift",
    "control": "control",
    "command": "command",
}


def inferred_hotkey_modifiers(candidate: dict[str, object]) -> str:
    modifiers = str(candidate.get("modifiers") or "").strip()
    if modifiers and modifiers != "none":
        return modifiers
    try:
        key_code = int(candidate.get("key_code") or 0)
    except (TypeError, ValueError):
        key_code = 0
    return MODIFIER_KEY_CODE_NAMES.get(key_code, modifiers or "none")


def select_hotkey_repair_candidate(candidates: object) -> dict[str, object] | None:
    if not isinstance(candidates, list):
        return None
    dict_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    for candidate in dict_candidates:
        if str(candidate.get("type") or "") == "flagsChanged" and str(candidate.get("modifiers") or "") != "none":
            return candidate
    for candidate in dict_candidates:
        if str(candidate.get("type") or "") == "flagsChanged" and inferred_hotkey_modifiers(candidate) != "none":
            return candidate
    for candidate in dict_candidates:
        if str(candidate.get("modifiers") or "") != "none":
            return candidate
    for candidate in dict_candidates:
        if inferred_hotkey_modifiers(candidate) != "none":
            return candidate
    return None


def hotkey_repair_confidence_payload(candidate: dict[str, object], modifiers: str) -> tuple[str, list[str]]:
    try:
        count = int(candidate.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    reasons: list[str] = []
    if modifiers == "shift":
        reasons.append("common_shift_modifier")
    if count >= 2:
        reasons.append("candidate_repeated")
    else:
        reasons.append("candidate_count_below_threshold")
    if "common_shift_modifier" in reasons:
        return "low", reasons
    if count >= 2:
        return "high", reasons
    return "low", reasons


def hotkey_repair_hint_payload(
    hotkey_events: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    empty = {
        "available": False,
        "reason": None,
        "candidate": None,
        "suggested_hotkey_key_code": None,
        "suggested_hotkey_modifiers": None,
        "command": None,
        "command_is_executable": False,
        "command_requires_user_approval": False,
        "command_mutates_state": False,
        "command_requests_mac_permissions": False,
        "command_records_audio": False,
        "confidence": None,
        "confidence_reasons": [],
        "diagnostic_command": None,
        "diagnostic_command_is_executable": False,
        "diagnostic_command_requires_user_approval": False,
        "diagnostic_command_mutates_state": False,
        "diagnostic_command_requests_mac_permissions": False,
        "diagnostic_command_records_audio": False,
        "diagnostic_plan_command": None,
        "diagnostic_plan_is_executable": False,
        "diagnostic_plan_requires_user_approval": False,
        "diagnostic_plan_mutates_state": False,
        "diagnostic_plan_requests_mac_permissions": False,
        "diagnostic_plan_records_audio": False,
        "diagnostic_plan_safe_to_run_now": False,
        "caution": None,
    }
    if hotkey_events.get("diagnosis") != "events_visible_no_recording_match":
        return empty
    candidate = select_hotkey_repair_candidate(hotkey_events.get("ignored_candidates"))
    if not candidate:
        return {**empty, "reason": "no ignored hotkey candidate"}
    modifiers = inferred_hotkey_modifiers(candidate)
    if modifiers == "none":
        return {**empty, "reason": "ignored candidate has no modifier information", "candidate": candidate}
    key_code = str(candidate.get("key_code") or "").strip()
    if not key_code:
        return {**empty, "reason": "ignored candidate has no key code", "candidate": candidate}
    confidence, confidence_reasons = hotkey_repair_confidence_payload(candidate, modifiers)
    if not is_packaged_binary_path(config.get("binary")):
        return {
            **empty,
            "reason": "hotkey repair restart command is packaged-app only",
            "candidate": candidate,
            "suggested_hotkey_key_code": key_code,
            "suggested_hotkey_modifiers": modifiers,
            "confidence": confidence,
            "confidence_reasons": confidence_reasons,
        }
    command = None
    if confidence == "high":
        command = (
            f"SWITCHTYPE_HOTKEY_KEY_CODE={key_code} "
            f"SWITCHTYPE_HOTKEY_MODIFIERS={modifiers} "
            "make doubao-shadow-restart-packaged"
        )
    diagnostic_command = "TIMEOUT=30 make hotkey-probe-packaged" if confidence != "high" else None
    diagnostic_plan_command = "make hotkey-probe-packaged-plan-json" if diagnostic_command else None
    diagnostic_plan_is_executable = command_is_executable(diagnostic_plan_command)
    diagnostic_plan_requires_user_approval = command_requires_user_approval(diagnostic_plan_command)
    diagnostic_plan_mutates_state = command_mutates_state(diagnostic_plan_command)
    diagnostic_plan_requests_mac_permissions = command_requests_mac_permissions(diagnostic_plan_command)
    diagnostic_plan_records_audio = command_records_audio(diagnostic_plan_command)
    return {
        "available": True,
        "reason": "observed ignored hotkey candidate",
        "candidate": candidate,
        "suggested_hotkey_key_code": key_code,
        "suggested_hotkey_modifiers": modifiers,
        "command": command,
        "command_is_executable": command_is_executable(command),
        "command_requires_user_approval": command_requires_user_approval(command),
        "command_mutates_state": command_mutates_state(command),
        "command_requests_mac_permissions": command_requests_mac_permissions(command),
        "command_records_audio": command_records_audio(command),
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "diagnostic_command": diagnostic_command,
        "diagnostic_command_is_executable": command_is_executable(diagnostic_command),
        "diagnostic_command_requires_user_approval": command_requires_user_approval(diagnostic_command),
        "diagnostic_command_mutates_state": command_mutates_state(diagnostic_command),
        "diagnostic_command_requests_mac_permissions": command_requests_mac_permissions(diagnostic_command),
        "diagnostic_command_records_audio": command_records_audio(diagnostic_command),
        "diagnostic_plan_command": diagnostic_plan_command,
        "diagnostic_plan_is_executable": diagnostic_plan_is_executable,
        "diagnostic_plan_requires_user_approval": diagnostic_plan_requires_user_approval,
        "diagnostic_plan_mutates_state": diagnostic_plan_mutates_state,
        "diagnostic_plan_requests_mac_permissions": diagnostic_plan_requests_mac_permissions,
        "diagnostic_plan_records_audio": diagnostic_plan_records_audio,
        "diagnostic_plan_safe_to_run_now": (
            diagnostic_plan_is_executable
            and not diagnostic_plan_requires_user_approval
            and not diagnostic_plan_mutates_state
            and not diagnostic_plan_requests_mac_permissions
            and not diagnostic_plan_records_audio
        ),
        "caution": "run this only if the observed candidate is the Doubao voice shortcut you just held",
    }


def settings_expected_modifiers(settings_hint: object) -> list[str]:
    if not isinstance(settings_hint, dict) or not settings_hint.get("available"):
        return []
    expected: list[str] = []
    suggested_modifiers = str(settings_hint.get("suggested_hotkey_modifiers") or "").strip()
    for value in suggested_modifiers.split(","):
        modifier = value.strip()
        if modifier and modifier not in expected:
            expected.append(modifier)
    for value in normalized_string_list(settings_hint.get("display_values")):
        modifier = SHORTCUT_DISPLAY_MODIFIERS.get(value.casefold())
        if modifier and modifier not in expected:
            expected.append(modifier)
    return expected


def hotkey_repair_hint_with_settings(
    hint: object,
    settings_hint: object,
) -> dict[str, object] | object:
    if not isinstance(hint, dict) or not hint.get("available"):
        return hint
    expected_modifiers = settings_expected_modifiers(settings_hint)
    if not expected_modifiers:
        return {
            **hint,
            "settings_conflict": False,
            "settings_expected_modifiers": [],
            "settings_display_values": [],
            "settings_suggested_hotkey_key_code": None,
            "settings_suggested_hotkey_modifiers": None,
            "settings_conflict_message": None,
        }
    suggested = str(hint.get("suggested_hotkey_modifiers") or "").strip()
    display_values = normalized_string_list(
        settings_hint.get("display_values") if isinstance(settings_hint, dict) else None
    )
    settings_suggested_key_code = (
        str(settings_hint.get("suggested_hotkey_key_code") or "").strip()
        if isinstance(settings_hint, dict)
        else ""
    )
    settings_suggested_modifiers = (
        str(settings_hint.get("suggested_hotkey_modifiers") or "").strip()
        if isinstance(settings_hint, dict)
        else ""
    )
    conflict = bool(suggested and suggested not in expected_modifiers)
    if not conflict:
        return {
            **hint,
            "settings_conflict": False,
            "settings_expected_modifiers": expected_modifiers,
            "settings_display_values": display_values,
            "settings_suggested_hotkey_key_code": settings_suggested_key_code or None,
            "settings_suggested_hotkey_modifiers": settings_suggested_modifiers or None,
            "settings_conflict_message": None,
        }

    confidence_reasons = normalized_string_list(hint.get("confidence_reasons"))
    if "conflicts_with_doubao_settings" not in confidence_reasons:
        confidence_reasons.append("conflicts_with_doubao_settings")
    diagnostic_command = str(hint.get("diagnostic_command") or "").strip() or "TIMEOUT=30 make hotkey-probe-packaged"
    diagnostic_plan_command = (
        str(hint.get("diagnostic_plan_command") or "").strip()
        or "make hotkey-probe-packaged-plan-json"
    )
    diagnostic_plan_is_executable = command_is_executable(diagnostic_plan_command)
    diagnostic_plan_requires_user_approval = command_requires_user_approval(diagnostic_plan_command)
    diagnostic_plan_mutates_state = command_mutates_state(diagnostic_plan_command)
    diagnostic_plan_requests_mac_permissions = command_requests_mac_permissions(diagnostic_plan_command)
    diagnostic_plan_records_audio = command_records_audio(diagnostic_plan_command)
    return {
        **hint,
        "command": None,
        "command_is_executable": False,
        "command_requires_user_approval": False,
        "command_mutates_state": False,
        "command_requests_mac_permissions": False,
        "command_records_audio": False,
        "confidence": "low",
        "confidence_reasons": confidence_reasons,
        "diagnostic_command": diagnostic_command,
        "diagnostic_command_is_executable": command_is_executable(diagnostic_command),
        "diagnostic_command_requires_user_approval": command_requires_user_approval(diagnostic_command),
        "diagnostic_command_mutates_state": command_mutates_state(diagnostic_command),
        "diagnostic_command_requests_mac_permissions": command_requests_mac_permissions(diagnostic_command),
        "diagnostic_command_records_audio": command_records_audio(diagnostic_command),
        "diagnostic_plan_command": diagnostic_plan_command,
        "diagnostic_plan_is_executable": diagnostic_plan_is_executable,
        "diagnostic_plan_requires_user_approval": diagnostic_plan_requires_user_approval,
        "diagnostic_plan_mutates_state": diagnostic_plan_mutates_state,
        "diagnostic_plan_requests_mac_permissions": diagnostic_plan_requests_mac_permissions,
        "diagnostic_plan_records_audio": diagnostic_plan_records_audio,
        "diagnostic_plan_safe_to_run_now": (
            diagnostic_plan_is_executable
            and not diagnostic_plan_requires_user_approval
            and not diagnostic_plan_mutates_state
            and not diagnostic_plan_requests_mac_permissions
            and not diagnostic_plan_records_audio
        ),
        "settings_conflict": True,
        "settings_expected_modifiers": expected_modifiers,
        "settings_display_values": display_values,
        "settings_suggested_hotkey_key_code": settings_suggested_key_code or None,
        "settings_suggested_hotkey_modifiers": settings_suggested_modifiers or None,
        "settings_conflict_message": (
            "observed hotkey candidate conflicts with readable Doubao shortcut settings; "
            "run the packaged hotkey probe before changing recorder config"
        ),
    }


def hotkey_event_diagnostics(log_file: Path, enabled: bool) -> dict[str, object]:
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []

    session_start = 0
    for index, line in enumerate(lines):
        if "Doubao shadow recorder armed." in line:
            session_start = index + 1

    events = [
        event
        for line in lines[session_start:]
        if (event := parse_hotkey_event(line)) is not None
    ]
    recognized_events = [
        event
        for event in events
        if str(event.get("action") or "") in {"consumeOnly", "finishRecording", "startRecording"}
    ]
    actions = Counter(str(event.get("action") or "unknown") for event in events)
    diagnosis = None
    if enabled and events and not recognized_events:
        diagnosis = "events_visible_no_recording_match"
    return {
        "enabled": enabled,
        "observed": len(events),
        "recognized": len(recognized_events),
        "actions": dict(sorted(actions.items())),
        "latest": events[-1] if events else None,
        "latest_recognized": recognized_events[-1] if recognized_events else None,
        "ignored_candidates": summarize_ignored_hotkey_candidates(events),
        "diagnosis": diagnosis,
    }


def parse_recorded_at(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "unknown":
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        recorded_at = datetime.fromisoformat(text)
    except ValueError:
        return None
    if recorded_at.tzinfo is None:
        return recorded_at.replace(tzinfo=timezone.utc)
    return recorded_at.astimezone(timezone.utc)


def format_recorded_at_local(value: object, local_timezone: tzinfo | None = None) -> str:
    recorded_at = parse_recorded_at(value)
    if recorded_at is None:
        return "unknown"
    target_timezone = local_timezone or datetime.now().astimezone().tzinfo
    if target_timezone is None:
        return recorded_at.isoformat()
    return recorded_at.astimezone(target_timezone).strftime("%Y-%m-%d %H:%M:%S %z")


def latest_segment_summary(
    segment_rows: list[dict[str, object]],
    now: datetime | None = None,
    stale_after_seconds: int = 300,
    min_duration: float = 0.25,
) -> dict[str, object]:
    if not segment_rows:
        return {}
    row = segment_rows[-1]
    text_status = str(row.get("text_capture_status") or "unknown").strip() or "unknown"
    text_reason = str(row.get("text_capture_reason") or "").strip()
    text = f"{text_status}/{text_reason}" if text_reason else text_status
    summary = {
        "id": str(row.get("id") or "unknown"),
        "recorded_at": str(row.get("recorded_at") or "unknown"),
        "audio": str(row.get("audio") or "unknown"),
        "recording_stop_reason": str(row.get("recording_stop_reason") or "unknown"),
        "text": text,
        "has_reference": bool(str(row.get("reference") or "").strip()),
    }
    recorded_at_local = format_recorded_at_local(summary["recorded_at"])
    if recorded_at_local != "unknown":
        summary["recorded_at_local"] = recorded_at_local
    audio_path = Path(summary["audio"])
    if summary["audio"] != "unknown":
        state, exists, size, duration = classify_audio(audio_path, min_duration=min_duration)
        summary["audio_status"] = {
            "state": state,
            "exists": exists,
            "bytes": size,
            "duration_seconds": duration,
        }
    recorded_at = parse_recorded_at(row.get("recorded_at"))
    if recorded_at is not None:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        current_time = current_time.astimezone(timezone.utc)
        age_seconds = max(0, int((current_time - recorded_at).total_seconds()))
        summary["age_seconds"] = age_seconds
        summary["stale"] = age_seconds > stale_after_seconds
    return summary


def recorder_binary_freshness_payload(
    latest_segment: dict[str, object],
    binary: object,
) -> dict[str, object]:
    if not latest_segment:
        return {}
    recorded_at = parse_recorded_at(latest_segment.get("recorded_at"))
    binary_text = str(binary or "").strip()
    if recorded_at is None or not binary_text:
        return {}
    binary_path = Path(binary_text)
    try:
        binary_mtime = datetime.fromtimestamp(binary_path.stat().st_mtime, timezone.utc)
    except OSError:
        return {
            "recorder_binary": binary_text,
            "recorder_binary_exists": False,
        }
    binary_mtime_text = binary_mtime.isoformat().replace("+00:00", "Z")
    return {
        "recorder_binary": binary_text,
        "recorder_binary_exists": True,
        "recorder_binary_mtime": binary_mtime_text,
        "recorded_before_current_recorder_binary": recorded_at < binary_mtime,
    }


def format_age(seconds: object) -> str:
    if not isinstance(seconds, int):
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if remaining_minutes:
        return f"{hours}h {remaining_minutes}m"
    return f"{hours}h"


def capture_readiness(next_command: str, running: bool) -> dict[str, object]:
    next_is_executable = command_is_executable(next_command)
    next_requires_user_approval = command_requires_user_approval(next_command)
    next_mutates_state = command_mutates_state(next_command)
    next_requests_mac_permissions = command_requests_mac_permissions(next_command)
    next_records_audio = command_records_audio(next_command)
    if not running:
        return {
            "can_capture_next": False,
            "status": "stopped",
            "reason": "recorder is not running",
            "next": next_command,
            "next_is_executable_command": next_is_executable,
            "next_requires_user_approval": next_requires_user_approval,
            "next_mutates_state": next_mutates_state,
            "next_requests_mac_permissions": next_requests_mac_permissions,
            "next_records_audio": next_records_audio,
        }
    if next_command == "make doubao-shadow-preflight-packaged":
        return {
            "can_capture_next": False,
            "status": "blocked",
            "reason": "packaged preflight required before live capture",
            "next": next_command,
            "next_is_executable_command": next_is_executable,
            "next_requires_user_approval": next_requires_user_approval,
            "next_mutates_state": next_mutates_state,
            "next_requests_mac_permissions": next_requests_mac_permissions,
            "next_records_audio": next_records_audio,
        }
    if next_command == "TIMEOUT=30 make doubao-shadow-live-verify":
        return {
            "can_capture_next": None,
            "status": "verify",
            "reason": "live verification required",
            "next": next_command,
            "next_is_executable_command": next_is_executable,
            "next_requires_user_approval": next_requires_user_approval,
            "next_mutates_state": next_mutates_state,
            "next_requests_mac_permissions": next_requests_mac_permissions,
            "next_records_audio": next_records_audio,
        }
    if next_command.startswith("DURATION=5 make doubao-shadow-capture-once-packaged"):
        return {
            "can_capture_next": False,
            "status": "fallback",
            "reason": "hotkey mismatch; use fixed-duration capture",
            "next": next_command,
            "next_is_executable_command": next_is_executable,
            "next_requires_user_approval": next_requires_user_approval,
            "next_mutates_state": next_mutates_state,
            "next_requests_mac_permissions": next_requests_mac_permissions,
            "next_records_audio": next_records_audio,
        }
    if next_command.startswith("use Doubao voice input now"):
        return {
            "can_capture_next": True,
            "status": "armed",
            "reason": "recorder is armed; use Doubao voice input now",
            "next": next_command,
            "next_is_executable_command": next_is_executable,
            "next_requires_user_approval": next_requires_user_approval,
            "next_mutates_state": next_mutates_state,
            "next_requests_mac_permissions": next_requests_mac_permissions,
            "next_records_audio": next_records_audio,
        }
    return {
        "can_capture_next": True,
        "status": "running",
        "reason": "recorder is running",
        "next": next_command,
        "next_is_executable_command": next_is_executable,
        "next_requires_user_approval": next_requires_user_approval,
        "next_mutates_state": next_mutates_state,
        "next_requests_mac_permissions": next_requests_mac_permissions,
        "next_records_audio": next_records_audio,
    }


def next_preview_payload(next_command: str) -> dict[str, object]:
    if next_command == "make doubao-shadow-reconcile-current":
        preview = "make doubao-shadow-reconcile-current-plan"
    elif next_command == "make doubao-shadow-reconcile":
        preview = "make doubao-shadow-reconcile-plan"
    else:
        preview = None
    return {
        "next_preview": preview,
        "next_preview_is_executable_command": command_is_executable(preview),
        "next_preview_requires_user_approval": command_requires_user_approval(preview),
        "next_preview_mutates_state": command_mutates_state(preview),
        "next_preview_requests_mac_permissions": command_requests_mac_permissions(preview),
        "next_preview_records_audio": command_records_audio(preview),
    }


def pending_clip_action_payload(payload: dict[str, object]) -> dict[str, object]:
    next_command = str(payload.get("next") or "").strip()
    recommended_command = str(payload.get("recommended_command") or "").strip()
    is_pending_clip_action = bool(
        next_command == "make doubao-shadow-reconcile-current"
        and recommended_command
        and recommended_command != next_command
    )
    pending_action = next_command if is_pending_clip_action else None
    pending_preview = payload.get("next_preview") if is_pending_clip_action else None
    return {
        "next_role": "pending_clip_action" if is_pending_clip_action else "primary_action",
        "pending_clip_action": pending_action,
        "pending_clip_action_is_executable_command": (
            bool(payload.get("next_is_executable_command"))
            if pending_action
            else False
        ),
        "pending_clip_action_requires_user_approval": (
            bool(payload.get("next_requires_user_approval"))
            if pending_action
            else False
        ),
        "pending_clip_action_mutates_state": (
            bool(payload.get("next_mutates_state"))
            if pending_action
            else False
        ),
        "pending_clip_action_requests_mac_permissions": (
            bool(payload.get("next_requests_mac_permissions"))
            if pending_action
            else False
        ),
        "pending_clip_action_records_audio": (
            bool(payload.get("next_records_audio"))
            if pending_action
            else False
        ),
        "pending_clip_action_preview": pending_preview,
        "pending_clip_action_preview_is_executable_command": (
            bool(payload.get("next_preview_is_executable_command"))
            if pending_preview
            else False
        ),
        "pending_clip_action_preview_requires_user_approval": (
            bool(payload.get("next_preview_requires_user_approval"))
            if pending_preview
            else False
        ),
        "pending_clip_action_preview_mutates_state": (
            bool(payload.get("next_preview_mutates_state"))
            if pending_preview
            else False
        ),
        "pending_clip_action_preview_requests_mac_permissions": (
            bool(payload.get("next_preview_requests_mac_permissions"))
            if pending_preview
            else False
        ),
        "pending_clip_action_preview_records_audio": (
            bool(payload.get("next_preview_records_audio"))
            if pending_preview
            else False
        ),
    }


def format_capture_readiness(readiness: dict[str, object]) -> str:
    can_capture = readiness.get("can_capture_next")
    if can_capture is True:
        can_text = "yes"
    elif can_capture is False:
        can_text = "no"
    else:
        can_text = "unknown"
    return f"Can capture next Doubao utterance: {can_text} ({readiness.get('reason', 'unknown')})"


def format_hearing_status(
    readiness: dict[str, object],
    latest_segment: dict[str, object] | None = None,
) -> str:
    status = str(readiness.get("status") or "unknown")
    reason = str(readiness.get("reason") or "unknown")
    can_capture = readiness.get("can_capture_next")
    if can_capture is True:
        message = f"Hearing status: {status}; next Doubao utterance can be captured."
    elif can_capture is False:
        message = f"Hearing status: {status}; not capturing new speech now ({reason})."
    else:
        message = f"Hearing status: {status}; capture readiness is unknown ({reason})."

    if isinstance(latest_segment, dict) and latest_segment.get("stale"):
        age_seconds = latest_segment.get("age_seconds")
        if isinstance(age_seconds, int):
            message += f" Latest segment is stale: {format_age(age_seconds)} ago."
    return message


def hearing_status_payload(
    readiness: dict[str, object],
    latest_segment: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "can_capture_next": readiness.get("can_capture_next"),
        "status": readiness.get("status", "unknown"),
        "reason": readiness.get("reason", "unknown"),
        "message": format_hearing_status(readiness, latest_segment),
    }
    if isinstance(latest_segment, dict):
        age_seconds = latest_segment.get("age_seconds")
        if isinstance(age_seconds, int):
            payload["latest_segment_age_seconds"] = age_seconds
        if "stale" in latest_segment:
            payload["latest_segment_stale"] = bool(latest_segment.get("stale"))
        if "recorded_before_current_recorder_binary" in latest_segment:
            payload["latest_segment_recorded_before_current_recorder_binary"] = bool(
                latest_segment.get("recorded_before_current_recorder_binary")
            )
    return payload


def doubao_settings_shortcut_hints(settings_roots: list[Path] | None = None) -> dict[str, object]:
    roots = settings_roots if settings_roots is not None else default_settings_roots()
    try:
        report = build_settings_probe_report(list(roots))
    except OSError as error:
        return {
            "available": False,
            "error": str(error),
            "candidate_file_count": 0,
            "visible_setting_keys": [],
            "display_values": [],
            "key_codes": [],
            "modifier_flags": [],
            "suggested_hotkey_key_code": None,
            "suggested_hotkey_modifiers": None,
            "candidate_files": [],
            "probe_command": "make watch-doubao-settings-probe",
            "probe_records_audio": False,
            "probe_listens_for_hotkeys": False,
        }
    shortcut_hints = report.get("shortcut_hints")
    if not isinstance(shortcut_hints, dict):
        shortcut_hints = {}
    visible_setting_keys = normalized_string_list(shortcut_hints.get("visible_setting_keys"))
    display_values = normalized_string_list(shortcut_hints.get("display_values"))
    key_codes = normalized_int_list(shortcut_hints.get("key_codes"))
    modifier_flags = normalized_int_list(shortcut_hints.get("modifier_flags"))
    suggested_hotkey_key_code = str(shortcut_hints.get("suggested_hotkey_key_code") or "").strip() or None
    suggested_hotkey_modifiers = str(shortcut_hints.get("suggested_hotkey_modifiers") or "").strip() or None
    candidate_files = normalized_string_list(shortcut_hints.get("candidate_files"))
    return {
        "available": bool(visible_setting_keys or display_values or key_codes or suggested_hotkey_key_code),
        "error": None,
        "candidate_file_count": int(report.get("candidate_file_count") or 0),
        "visible_setting_keys": visible_setting_keys,
        "display_values": display_values,
        "key_codes": key_codes,
        "modifier_flags": modifier_flags,
        "suggested_hotkey_key_code": suggested_hotkey_key_code,
        "suggested_hotkey_modifiers": suggested_hotkey_modifiers,
        "candidate_files": candidate_files,
        "probe_command": "make watch-doubao-settings-probe",
        "probe_records_audio": False,
        "probe_listens_for_hotkeys": False,
    }


def shadow_hotkey_config_match_payload(
    config: dict[str, object],
    settings_hint: dict[str, object],
) -> dict[str, object]:
    configured_key_code = str(config.get("hotkey_key_code") or "").strip()
    configured_modifiers = str(config.get("hotkey_modifiers") or "").strip()
    settings_key_code = str(settings_hint.get("suggested_hotkey_key_code") or "").strip()
    settings_modifiers = str(settings_hint.get("suggested_hotkey_modifiers") or "").strip()
    available = bool(settings_key_code or settings_modifiers)
    matches = None
    if available:
        key_code_matches = not settings_key_code or configured_key_code == settings_key_code
        modifiers_match = not settings_modifiers or configured_modifiers == settings_modifiers
        matches = key_code_matches and modifiers_match
    return {
        "available": available,
        "matches": matches,
        "configured_key_code": configured_key_code or None,
        "configured_modifiers": configured_modifiers or None,
        "settings_key_code": settings_key_code or None,
        "settings_modifiers": settings_modifiers or None,
    }


def status_payload(
    pid_file: Path,
    segments: Path,
    manifest: Path | None = None,
    log_file: Path | None = None,
    min_duration: float = 0.25,
    now: datetime | None = None,
) -> dict[str, object]:
    pid = read_pid(pid_file)
    running = bool(pid and process_is_running(pid))
    config = read_config(pid_file)
    hotkey_events = hotkey_event_diagnostics(
        log_file or pid_file.with_name("shadow.log"),
        enabled=bool(config.get("debug_hotkey_events")),
    )

    segment_rows = read_jsonl(segments)
    captured_segments = len(segment_rows)
    captured_references = sum(1 for row in segment_rows if str(row.get("reference") or "").strip())
    safe_captured_references = sum(
        1
        for row in segment_rows
        if str(row.get("reference") or "").strip() and has_safe_capture_stop_reason(row)
    )
    focused_captured = sum(1 for row in segment_rows if row.get("text_capture_status") == "captured")
    focused_unmatched = sum(
        1
        for row in segment_rows
        if str(row.get("text_capture_status") or "").strip()
        and row.get("text_capture_status") != "captured"
    )
    focused_reasons = Counter(
        str(row.get("text_capture_reason") or "unspecified")
        for row in segment_rows
        if str(row.get("text_capture_status") or "").strip()
        and row.get("text_capture_status") != "captured"
    )
    manifest_samples = 0
    valid_audio = 0
    audio_status_count = 0
    missing = 0
    too_short = 0
    unreadable = 0
    wrong_format = 0
    silent = 0
    manifest_rows: list[dict[str, object]] = []
    manifest_sample_ids: set[str] = set()
    if manifest is not None:
        manifest_rows = read_jsonl(manifest)
        manifest_sample_ids = {
            str(row.get("id") or "").strip()
            for row in manifest_rows
            if str(row.get("id") or "").strip()
            and str(row.get("audio") or "").strip()
            and str(row.get("reference") or "").strip()
        }
        manifest_samples = len(manifest_sample_ids)
        statuses = collect_status(manifest, min_duration=min_duration) if manifest.exists() else []
        valid_audio = sum(1 for status in statuses if status.state == "valid")
        audio_status_count = len(statuses)
        missing = sum(1 for status in statuses if status.state == "missing")
        too_short = sum(1 for status in statuses if status.state == "too_short")
        unreadable = sum(1 for status in statuses if status.state == "unreadable")
        wrong_format = sum(1 for status in statuses if status.state == "wrong_format")
        silent = sum(1 for status in statuses if status.state == "silent")

    needs_reconciliation = sum(
        1
        for row in segment_rows
        if has_recording_stop_reason(row) and needs_reference(row, manifest_sample_ids)
    )
    legacy_pending_reconciliation = sum(
        1
        for row in segment_rows
        if not has_recording_stop_reason(row) and needs_reference(row, manifest_sample_ids)
    )
    current_manifest_candidates = sum(
        1
        for row in segment_rows
        if has_recording_stop_reason(row)
        and str(row.get("id") or "").strip()
        and str(row.get("audio") or "").strip()
        and str(row.get("id") or "").strip() not in manifest_sample_ids
    )

    if manifest is not None:
        manifest_samples = sum(
            1
            for row in manifest_rows
            if str(row.get("id") or "").strip()
            and str(row.get("audio") or "").strip()
            and str(row.get("reference") or "").strip()
        )

    latest_segment = latest_segment_summary(segment_rows, now=now, min_duration=min_duration)
    latest_segment.update(recorder_binary_freshness_payload(latest_segment, config.get("binary")))
    live_verification_needed = (
        running
        and valid_audio == 0
        and int(hotkey_events.get("observed") or 0) == 0
        and isinstance(latest_segment, dict)
        and bool(latest_segment.get("stale"))
    )
    hotkey_capture_fallback_needed = (
        running
        and hotkey_events.get("diagnosis") == "events_visible_no_recording_match"
        and valid_audio == 0
    )

    if hotkey_capture_fallback_needed:
        capture_next_command = "DURATION=5 make doubao-shadow-capture-once-packaged"
    elif live_verification_needed and is_packaged_binary_path(config.get("binary")):
        capture_next_command = "make doubao-shadow-preflight-packaged"
    elif live_verification_needed:
        capture_next_command = "TIMEOUT=30 make doubao-shadow-live-verify"
    elif not running:
        capture_next_command = "make doubao-shadow-start-auto"
    elif captured_segments == 0:
        capture_next_command = "use Doubao voice input now; if you already tried, run make hotkey-probe"
    else:
        capture_next_command = "use Doubao voice input now; if you already tried, run make hotkey-probe"

    if manifest is not None and valid_audio > 0:
        next_command = "make doubao-shadow-benchmark"
    elif needs_reconciliation > 0 or (manifest is not None and manifest_samples == 0 and current_manifest_candidates > 0):
        next_command = "make doubao-shadow-reconcile-current"
    elif legacy_pending_reconciliation > 0:
        next_command = "make doubao-shadow-reconcile"
    elif manifest is not None and audio_status_count > 0 and valid_audio < audio_status_count:
        next_command = "make doubao-shadow-start-auto"
    else:
        next_command = capture_next_command
    live_verification_command = (
        "TIMEOUT=30 make doubao-shadow-live-verify"
        if running and capture_next_command != "make doubao-shadow-preflight-packaged"
        else None
    )
    readiness = capture_readiness(capture_next_command, running)
    payload = {
        "running": running,
        "pid": pid if running else None,
        "live_verification_command": live_verification_command,
        "live_verification_command_is_executable": command_is_executable(live_verification_command),
        "live_verification_command_requires_user_approval": command_requires_user_approval(live_verification_command),
        "live_verification_command_mutates_state": command_mutates_state(live_verification_command),
        "live_verification_command_requests_mac_permissions": command_requests_mac_permissions(live_verification_command),
        "live_verification_command_records_audio": command_records_audio(live_verification_command),
        "capture_readiness": readiness,
        "hearing_status": hearing_status_payload(readiness, latest_segment),
        "segments": {
            "captured": captured_segments,
            "references": captured_references,
            "safe_references": safe_captured_references,
            "needs_reconciliation": needs_reconciliation,
            "legacy_pending_reconciliation": legacy_pending_reconciliation,
            "latest": latest_segment,
            "focused_text": {
                "captured": focused_captured,
                "unmatched": focused_unmatched,
                "reasons": dict(sorted(focused_reasons.items())),
                "latest_diagnostic": latest_focused_text_diagnostic(segment_rows),
            },
        },
        "benchmark": {
            "manifest": str(manifest) if manifest is not None else None,
            "manifest_samples": manifest_samples,
            "valid_audio": valid_audio,
            "audio_total": audio_status_count,
            "missing_audio": missing,
            "too_short": too_short,
            "unreadable": unreadable,
            "wrong_format": wrong_format,
            "silent": silent,
        },
        "config": config,
        "hotkey_events": hotkey_events,
        "hotkey_repair_hint": hotkey_repair_hint_payload(hotkey_events, config),
        "next": next_command,
        "next_is_executable_command": command_is_executable(next_command),
        "next_requires_user_approval": command_requires_user_approval(next_command),
        "next_mutates_state": command_mutates_state(next_command),
        "next_requests_mac_permissions": command_requests_mac_permissions(next_command),
        "next_records_audio": command_records_audio(next_command),
    }
    payload.update(next_preview_payload(next_command))
    payload.update(recommended_command_payload(payload))
    payload.update(pending_clip_action_payload(payload))
    payload.update(primary_blocker_payload(payload))
    payload["readiness_summary"] = readiness_summary_payload(payload)
    return payload


def print_status(
    pid_file: Path,
    segments: Path,
    manifest: Path | None = None,
    log_file: Path | None = None,
    min_duration: float = 0.25,
    now: datetime | None = None,
) -> int:
    payload = status_payload(
        pid_file=pid_file,
        segments=segments,
        manifest=manifest,
        log_file=log_file,
        min_duration=min_duration,
        now=now,
    )
    pid = payload["pid"]
    if payload["running"]:
        print(f"Doubao shadow recorder running: pid {pid}")
    else:
        print("Doubao shadow recorder not running.")
    segment_summary = payload["segments"]
    capture_status = payload.get("capture_readiness")
    if isinstance(capture_status, dict):
        print(format_capture_readiness(capture_status))
        latest_for_hearing = segment_summary.get("latest")
        latest_hearing_segment = latest_for_hearing if isinstance(latest_for_hearing, dict) else None
        print(format_hearing_status(capture_status, latest_hearing_segment))

    benchmark_summary = payload["benchmark"]
    config = payload["config"]
    hotkey_events = payload["hotkey_events"]
    focused_text = segment_summary["focused_text"]
    print(f"Captured segments: {segment_summary['captured']}")
    print(f"Captured references: {segment_summary['references']}")
    print(f"Safe captured references: {segment_summary['safe_references']}")
    print(f"Needs reconciliation: {segment_summary['needs_reconciliation']}")
    print(f"Legacy pending reconciliation: {segment_summary['legacy_pending_reconciliation']}")
    print(f"Focused text captured: {focused_text['captured']}")
    print(f"Focused text unmatched: {focused_text['unmatched']}")
    reasons = focused_text.get("reasons")
    if isinstance(reasons, dict) and reasons:
        print(
            "Focused text reasons: "
            + ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
        )
    latest_segment = segment_summary.get("latest")
    if isinstance(latest_segment, dict) and latest_segment:
        print(
            "Latest segment: "
            + ", ".join(
                [
                    f"id={latest_segment.get('id', 'unknown')}",
                    f"recorded_at={latest_segment.get('recorded_at', 'unknown')}",
                    f"stop={latest_segment.get('recording_stop_reason', 'unknown')}",
                    f"text={latest_segment.get('text', 'unknown')}",
                    f"reference={'yes' if latest_segment.get('has_reference') else 'no'}",
                    f"audio={latest_segment.get('audio', 'unknown')}",
                ]
            )
        )
        recorded_at_local = str(latest_segment.get("recorded_at_local") or "unknown")
        if recorded_at_local != "unknown":
            print(f"Latest segment local time: {recorded_at_local}")
        if latest_segment.get("recorded_before_current_recorder_binary"):
            print(LATEST_SEGMENT_BINARY_FRESHNESS_MESSAGE)
        age_seconds = latest_segment.get("age_seconds")
        if isinstance(age_seconds, int):
            age_text = f"Latest segment age: {format_age(age_seconds)} ago"
            if payload["running"] and latest_segment.get("stale"):
                capture_readiness_payload = payload.get("capture_readiness")
                capture_next = (
                    capture_readiness_payload.get("next")
                    if isinstance(capture_readiness_payload, dict)
                    else None
                )
                if capture_next == "make doubao-shadow-preflight-packaged":
                    age_text += " (stale; run packaged preflight before live verify)"
                elif str(capture_next or "").startswith("DURATION=5 make doubao-shadow-capture-once-packaged"):
                    age_text += " (stale; use fixed-duration fallback because hotkey events do not match)"
                else:
                    age_text += " (stale; run live verify, then hold the Doubao hotkey)"
            print(age_text)
        audio_status = latest_segment.get("audio_status")
        if isinstance(audio_status, dict):
            duration = audio_status.get("duration_seconds")
            duration_text = "unknown" if duration is None else f"{float(duration):.2f}s"
            print(
                "Latest audio: "
                + ", ".join(
                    [
                        f"state={audio_status.get('state', 'unknown')}",
                        f"duration={duration_text}",
                        f"bytes={audio_status.get('bytes', 0)}",
                    ]
                )
            )
    latest_diagnostic = focused_text.get("latest_diagnostic")
    if isinstance(latest_diagnostic, dict) and latest_diagnostic:
        print(
            "Latest focused text diagnostic: "
            + ", ".join(
                [
                    f"attempts={latest_diagnostic.get('text_capture_attempts', 'unknown')}",
                    f"elapsed={latest_diagnostic.get('text_capture_elapsed_seconds', 'unknown')}s",
                    f"before_len={latest_diagnostic.get('text_capture_before_length', 'unknown')}",
                    f"after_len={latest_diagnostic.get('text_capture_after_length', 'unknown')}",
                    f"before_pid={latest_diagnostic.get('text_capture_before_process_identifier', 'unknown')}",
                    f"after_pid={latest_diagnostic.get('text_capture_after_process_identifier', 'unknown')}",
                    (
                        "before_sel="
                        f"{latest_diagnostic.get('text_capture_before_selection_location', 'unknown')}"
                        f"+{latest_diagnostic.get('text_capture_before_selection_length', 'unknown')}"
                    ),
                    (
                        "after_sel="
                        f"{latest_diagnostic.get('text_capture_after_selection_location', 'unknown')}"
                        f"+{latest_diagnostic.get('text_capture_after_selection_length', 'unknown')}"
                    ),
                ]
            )
        )
    print(f"Hotkey key code: {config['hotkey_key_code']}")
    print(f"Hotkey modifiers: {config['hotkey_modifiers']}")
    print(f"Recorder binary: {config['binary']}")
    print(f"Focused text capture: {'enabled' if config['capture_focused_text'] else 'disabled'}")
    print(f"Debug hotkey events: {'enabled' if config['debug_hotkey_events'] else 'disabled'}")
    print(f"Hotkey events observed: {hotkey_events['observed']}")
    print(f"Hotkey recording events: {hotkey_events.get('recognized', 0)}")
    actions = hotkey_events.get("actions")
    if isinstance(actions, dict) and actions:
        print(
            "Hotkey event actions: "
            + ", ".join(f"{action}={count}" for action, count in sorted(actions.items()))
        )
    latest_hotkey_event = hotkey_events.get("latest")
    if isinstance(latest_hotkey_event, dict):
        print(
            "Latest hotkey event: "
            + ", ".join(
                [
                    f"source={latest_hotkey_event.get('source', 'unknown')}",
                    f"type={latest_hotkey_event.get('type', 'unknown')}",
                    f"keyCode={latest_hotkey_event.get('key_code', 'unknown')}",
                    f"modifiers={latest_hotkey_event.get('modifiers', 'unknown')}",
                    f"action={latest_hotkey_event.get('action', 'unknown')}",
                ]
            )
        )
    ignored_candidates_text = format_ignored_hotkey_candidates(hotkey_events.get("ignored_candidates"))
    if ignored_candidates_text:
        print(ignored_candidates_text)
    if hotkey_events.get("diagnosis") == "events_visible_no_recording_match":
        print("Hotkey diagnosis: key events are visible, but none matched the recorder hotkey.")
        print("Fixed-duration fallback: DURATION=5 make doubao-shadow-capture-once-packaged")
        print_hotkey_repair_hint(payload.get("hotkey_repair_hint"))
    print_recommended_command(payload)
    live_verification_command = payload.get("live_verification_command")
    if live_verification_command:
        print(f"Live verify: {live_verification_command}")
        print(format_command_approval("Live verify", str(live_verification_command)))
        print(
            format_command_safety(
                "Live verify",
                mutates_state=payload.get("live_verification_command_mutates_state"),
                requests_mac_permissions=payload.get("live_verification_command_requests_mac_permissions"),
                records_audio=payload.get("live_verification_command_records_audio"),
            )
        )
    if manifest is not None:
        print(f"Benchmark manifest samples: {benchmark_summary['manifest_samples']}")
        print(f"Benchmark valid audio: {benchmark_summary['valid_audio']}/{benchmark_summary['audio_total']}")
        print(f"Benchmark missing audio: {benchmark_summary['missing_audio']}")
        print(f"Benchmark too short: {benchmark_summary['too_short']}")
        print(f"Benchmark unreadable: {benchmark_summary['unreadable']}")
        print(f"Benchmark wrong format: {benchmark_summary['wrong_format']}")
        print(f"Benchmark silent: {benchmark_summary['silent']}")
    print_next_action(payload)
    readiness_summary = payload.get("readiness_summary")
    if isinstance(readiness_summary, dict):
        next_safe_command = readiness_summary.get("next_safe_command")
        if next_safe_command:
            print(f"Next safe command: {next_safe_command}")
        next_user_approval_command = readiness_summary.get("next_user_approval_command")
        if next_user_approval_command:
            print(f"Next user-approval command: {next_user_approval_command}")
    return 0


def print_hearing_check(
    pid_file: Path,
    segments: Path,
    manifest: Path | None = None,
    log_file: Path | None = None,
    min_duration: float = 0.25,
    now: datetime | None = None,
    preflight_binary: Path | None = None,
    preflight_doctor: Path | None = None,
    doubao_settings_roots: list[Path] | None = None,
) -> int:
    payload = status_payload(
        pid_file=pid_file,
        segments=segments,
        manifest=manifest,
        log_file=log_file,
        min_duration=min_duration,
        now=now,
    )
    hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict):
        hearing = {}
    settings_hint = doubao_settings_shortcut_hints(doubao_settings_roots)
    hotkey_config_match = shadow_hotkey_config_match_payload(payload.get("config", {}), settings_hint)
    hotkey_repair_hint = hotkey_repair_hint_with_settings(payload.get("hotkey_repair_hint"), settings_hint)
    recovery = hearing_recovery_hint(payload)
    preflight_hint = packaged_preflight_blocker_hint(
        payload,
        preflight_binary=preflight_binary,
        preflight_doctor=preflight_doctor,
    )
    effective_hearing = effective_hearing_status_payload(hearing, preflight_hint)
    can_capture = effective_hearing.get("can_capture_next")
    if can_capture is True:
        answer = "yes"
    elif can_capture is False:
        answer = "no"
    else:
        answer = "unknown"

    print("Doubao shadow hearing check")
    print(f"Can hear next Doubao utterance: {answer}")
    message = str(effective_hearing.get("message") or "").strip()
    if message:
        print(message)
    if hearing.get("latest_segment_recorded_before_current_recorder_binary"):
        print(LATEST_SEGMENT_BINARY_FRESHNESS_MESSAGE)
    print(f"Transcript visibility: {TRANSCRIPT_VISIBILITY}")
    if settings_hint.get("available"):
        display = ", ".join(normalized_string_list(settings_hint.get("display_values"))) or "unknown"
        suggested_key_code = str(settings_hint.get("suggested_hotkey_key_code") or "").strip()
        suggested_modifiers = str(settings_hint.get("suggested_hotkey_modifiers") or "").strip()
        keys = ", ".join(normalized_string_list(settings_hint.get("visible_setting_keys"))) or "none"
        parts = [f"display={display}"]
        if suggested_key_code:
            parts.append(f"keyCode={suggested_key_code}")
        if suggested_modifiers:
            parts.append(f"modifiers={suggested_modifiers}")
        parts.append(f"keys={keys}")
        print("Doubao settings shortcut hint: " + "; ".join(parts))
    if hotkey_config_match.get("available"):
        verdict = "yes" if hotkey_config_match.get("matches") else "no"
        settings_key_code = hotkey_config_match.get("settings_key_code") or "unknown"
        settings_modifiers = hotkey_config_match.get("settings_modifiers") or "unknown"
        print(
            "Shadow recorder hotkey matches Doubao settings: "
            f"{verdict} (keyCode={settings_key_code}, modifiers={settings_modifiers})."
        )
    combined_payload = dict(payload)
    combined_payload["effective_hearing_status"] = effective_hearing
    combined_payload["hotkey_repair_hint"] = hotkey_repair_hint
    combined_payload.update(recovery)
    combined_payload.update(preflight_hint)
    secondary_after_permissions = packaged_preflight_has_blockers(preflight_hint)
    recommendation = recommended_command_payload(combined_payload)
    action_payload = dict(combined_payload)
    action_payload.update(recommendation)
    action_payload["pending_clip_cleanup_deferred_until_permissions"] = bool(
        secondary_after_permissions
        and action_payload.get("pending_clip_action")
        and action_payload.get("recommended_command") != action_payload.get("pending_clip_action")
    )
    action_payload.update(primary_blocker_payload(action_payload))
    action_summary = readiness_summary_payload(action_payload)

    if action_summary.get("primary_blocker"):
        detail = str(action_summary.get("primary_blocker_detail") or "").strip()
        suffix = f" ({detail})" if detail else ""
        print(f"Primary blocker: {action_summary['primary_blocker']}{suffix}")
    if action_summary.get("primary_recovery_command"):
        print(f"Primary recovery: {action_summary['primary_recovery_command']}")
    primary_permission_target = str(action_summary.get("primary_permission_target") or "").strip()
    if primary_permission_target:
        print(f"Primary permission target: {primary_permission_target}")
    print_recommended_command(recommendation)

    live_verification_command = payload.get("live_verification_command")
    if live_verification_command:
        live_verify_label = "Live verify"
        if str(recommendation.get("recommended_command") or "").strip() != str(live_verification_command).strip():
            live_verify_label = "Alternative live verify"
        if secondary_after_permissions:
            live_verify_label = "Secondary live verify after permissions"
        print(f"{live_verify_label}: {live_verification_command}")
        print(format_command_approval(live_verify_label, str(live_verification_command)))
        print(
            format_command_safety(
                live_verify_label,
                mutates_state=payload.get("live_verification_command_mutates_state"),
                requests_mac_permissions=payload.get("live_verification_command_requests_mac_permissions"),
                records_audio=payload.get("live_verification_command_records_audio"),
            )
        )

    next_command = str(payload["next"])
    print_next_action(action_payload)
    capture_readiness_payload = payload.get("capture_readiness")
    capture_next = (
        str(capture_readiness_payload.get("next") or "").strip()
        if isinstance(capture_readiness_payload, dict)
        else ""
    )
    if capture_next and capture_next != next_command:
        capture_label = "Capture diagnostic"
        if secondary_after_permissions:
            capture_label = "Secondary capture diagnostic after permissions"
        print(format_command_approval(capture_label, capture_next))
        print(
            format_command_safety(
                capture_label,
                mutates_state=capture_readiness_payload.get("next_mutates_state"),
                requests_mac_permissions=capture_readiness_payload.get("next_requests_mac_permissions"),
                records_audio=capture_readiness_payload.get("next_records_audio"),
            )
        )
        print(f"{capture_label}: {capture_next}")
    if secondary_after_permissions and isinstance(hotkey_repair_hint, dict) and hotkey_repair_hint.get("available"):
        print(
            "Secondary hotkey diagnostics after permissions: "
            "resolve packaged permissions before changing hotkey config."
        )
    hotkey_repair_label = "Secondary hotkey repair" if secondary_after_permissions else "Hotkey repair"
    print_hotkey_repair_hint(hotkey_repair_hint, label=hotkey_repair_label)
    recovery_command = recovery.get("recovery_command")
    if recovery_command:
        print(f"Likely recovery if packaged preflight fails: {recovery_command}")
        print(format_command_approval("Recovery", str(recovery_command)))
        print(
            format_command_safety(
                "Recovery",
                mutates_state=recovery.get("recovery_mutates_state"),
                requests_mac_permissions=recovery.get("recovery_requests_mac_permissions"),
                records_audio=recovery.get("recovery_records_audio"),
            )
        )
    blockers = preflight_hint.get("preflight_blockers")
    if isinstance(blockers, list) and blockers:
        print(f"Current packaged preflight blockers: {'; '.join(str(blocker) for blocker in blockers)}")
    elif preflight_hint.get("preflight_blockers_error"):
        print(f"Current packaged preflight blockers unavailable: {preflight_hint['preflight_blockers_error']}")
    ignored_blockers = preflight_hint.get("preflight_ignored_blockers")
    if isinstance(ignored_blockers, list) and ignored_blockers:
        print(f"Current packaged preflight ignored blockers: {'; '.join(str(blocker) for blocker in ignored_blockers)}")
        ignored_reason = str(preflight_hint.get("preflight_blockers_ignored_reason") or "").strip()
        if ignored_reason:
            print(f"Current packaged preflight ignored reason: {ignored_reason}")
    mac_permissions = preflight_hint.get("preflight_mac_permissions")
    if isinstance(mac_permissions, dict) and mac_permissions:
        print(f"Current packaged macOS permissions: {mac_permission_detail(mac_permissions)}")
    input_device_detail = str(preflight_hint.get("preflight_input_device_detail") or "").strip()
    if input_device_detail:
        prefix = "Expected input device: "
        if input_device_detail.startswith(prefix):
            input_device_detail = input_device_detail[len(prefix):]
        print(f"Current packaged input device: {input_device_detail}")
    permission_guidance = str(preflight_hint.get("preflight_permission_guidance") or "").strip()
    if permission_guidance:
        print(f"Current packaged permission target: {permission_guidance}")
    warnings = preflight_hint.get("preflight_warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            print(f"Current packaged preflight warning: {warning}")
    preflight_preview = preflight_hint.get("preflight_preview")
    if preflight_preview:
        print(f"Current packaged preflight preview: {preflight_preview}")
        print(format_command_approval("Current packaged preflight preview", str(preflight_preview)))
        print(
            format_command_safety(
                "Current packaged preflight preview",
                mutates_state=preflight_hint.get("preflight_preview_mutates_state"),
                requests_mac_permissions=preflight_hint.get("preflight_preview_requests_mac_permissions"),
                records_audio=preflight_hint.get("preflight_preview_records_audio"),
            )
        )
    preflight_next = preflight_hint.get("preflight_next")
    if preflight_next:
        print(f"Current packaged preflight next: {preflight_next}")
        print(format_command_approval("Current packaged preflight next", str(preflight_next)))
        print(
            format_command_safety(
                "Current packaged preflight next",
                mutates_state=preflight_hint.get("preflight_next_mutates_state"),
                requests_mac_permissions=preflight_hint.get("preflight_next_requests_mac_permissions"),
                records_audio=preflight_hint.get("preflight_next_records_audio"),
            )
        )
    next_safe_command = action_summary.get("next_safe_command")
    if next_safe_command:
        print(f"Next safe command: {next_safe_command}")
    next_user_approval_command = action_summary.get("next_user_approval_command")
    if next_user_approval_command:
        print(f"Next user-approval command: {next_user_approval_command}")
    return 0


def print_recommended_command(recommendation: dict[str, object]) -> None:
    recommended_command = recommendation.get("recommended_command")
    if not recommended_command:
        return
    print(f"Recommended command: {recommended_command}")
    print(f"Recommended command source: {recommendation['recommended_command_source']}")
    print(format_command_approval("Recommended command", str(recommended_command)))
    print(
        format_command_safety(
            "Recommended command",
            mutates_state=recommendation.get("recommended_command_mutates_state"),
            requests_mac_permissions=recommendation.get("recommended_command_requests_mac_permissions"),
            records_audio=recommendation.get("recommended_command_records_audio"),
        )
    )
    approval_summary = recommendation.get("recommended_command_approval_summary")
    if isinstance(approval_summary, dict) and approval_summary:
        print(f"Recommended command approval summary: {format_approval_summary(approval_summary)}")
    approval_reasons = normalized_string_list(recommendation.get("recommended_command_approval_reasons"))
    if approval_reasons:
        print(f"Recommended command approval reasons: {'; '.join(approval_reasons)}")
    plan = recommendation.get("recommended_command_plan")
    if isinstance(plan, dict) and plan.get("plan_command"):
        print(f"Recommended command plan: {plan['plan_command']}")
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
                print(
                    f"Recommended command plan step {index}: "
                    f"{command}; approval_reason={approval_reason}"
                )


def next_action_label(payload: dict[str, object]) -> tuple[str, str, str]:
    next_command = str(payload["next"])
    recommended_command = str(payload.get("recommended_command") or "").strip()
    if (
        next_command == "make doubao-shadow-reconcile-current"
        and recommended_command
        and recommended_command != next_command
    ):
        if payload.get("pending_clip_cleanup_deferred_until_permissions"):
            return (
                "Secondary pending clip cleanup after permissions",
                "Secondary pending clip cleanup after permissions",
                "Secondary pending clip cleanup preview after permissions",
            )
        return "Pending clip action", "Pending clip action", "Pending clip action preview"
    command_label = "Next command" if payload.get("next_is_executable_command") else "Next action"
    return command_label, "Next", "Next preview"


def print_next_action(payload: dict[str, object]) -> None:
    next_command = str(payload["next"])
    approval_label, display_label, preview_label = next_action_label(payload)
    print(format_command_approval(approval_label, next_command))
    print(
        format_command_safety(
            approval_label,
            mutates_state=payload.get("next_mutates_state"),
            requests_mac_permissions=payload.get("next_requests_mac_permissions"),
            records_audio=payload.get("next_records_audio"),
        )
    )
    print(f"{display_label}: {next_command}")
    next_preview = payload.get("next_preview")
    if next_preview:
        preview_command = str(next_preview)
        print(format_command_approval(preview_label, preview_command))
        print(
            format_command_safety(
                preview_label,
                mutates_state=payload.get("next_preview_mutates_state"),
                requests_mac_permissions=payload.get("next_preview_requests_mac_permissions"),
                records_audio=payload.get("next_preview_records_audio"),
            )
        )
        print(f"{preview_label}: {preview_command}")


def empty_preflight_blocker_hint() -> dict[str, object]:
    return {
        "preflight_blockers": [],
        "preflight_blockers_available": False,
        "preflight_blockers_error": None,
        "preflight_ignored_blockers": [],
        "preflight_blockers_ignored_reason": None,
        "preflight_next": None,
        "preflight_next_is_executable_command": False,
        "preflight_next_requires_user_approval": False,
        "preflight_next_mutates_state": False,
        "preflight_next_requests_mac_permissions": False,
        "preflight_next_records_audio": False,
        "preflight_permission_guidance": "",
        "preflight_permission_targets": [],
        "preflight_preview": None,
        "preflight_preview_is_executable_command": False,
        "preflight_preview_requires_user_approval": False,
        "preflight_preview_mutates_state": False,
        "preflight_preview_requests_mac_permissions": False,
        "preflight_preview_records_audio": False,
        "preflight_warnings": [],
        "preflight_mac_permissions": {},
        "preflight_input_device": {},
        "preflight_input_device_detail": "",
    }


def binary_supports_hotkey_probe_timeout(binary: Path) -> bool:
    try:
        from run_hotkey_probe import binary_supports_timeout
    except ModuleNotFoundError:
        from bench.scripts.run_hotkey_probe import binary_supports_timeout
    return binary_supports_timeout(binary)


def packaged_preflight_warnings(preflight_binary: Path) -> list[str]:
    hotkey_probe = preflight_binary.with_name("SwitchTypeHotkeyProbe")
    if not binary_supports_hotkey_probe_timeout(hotkey_probe):
        return ["Packaged hotkey probe is stale; refresh the packaged app before probe-based hotkey diagnosis."]
    return []


def packaged_preflight_next_command(
    blockers: list[str],
    preflight_binary: Path,
) -> tuple[str | None, str | None]:
    if any(blocker.startswith("Shadow recorder binary:") for blocker in blockers):
        return "make package", None
    permission_blocked = any(
        blocker.startswith("Microphone permission:") or blocker.startswith("Accessibility permission:")
        for blocker in blockers
    )
    if permission_blocked:
        if packaged_preflight_warnings(preflight_binary):
            return "make doubao-shadow-refresh-packaged", "make doubao-shadow-refresh-packaged-plan"
        return "make app-request-permissions-packaged", None
    if any(blocker.startswith("Expected input device:") for blocker in blockers):
        return "check SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME", None
    return None, None


def is_permission_preflight_blocker(blocker: str) -> bool:
    return blocker.startswith("Microphone permission:") or blocker.startswith("Accessibility permission:")


def packaged_runtime_permission_blockers_ignored_reason(
    payload: dict[str, object],
    blockers: list[str],
) -> str | None:
    if not blockers or not all(is_permission_preflight_blocker(blocker) for blocker in blockers):
        return None
    if not payload.get("running"):
        return None
    config = payload.get("config")
    if not isinstance(config, dict) or not is_packaged_binary_path(config.get("binary")):
        return None
    hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict) or hearing.get("can_capture_next") is not True:
        return None
    if str(hearing.get("status") or "").strip() != "armed":
        return None
    segments = payload.get("segments")
    latest = segments.get("latest") if isinstance(segments, dict) else None
    if isinstance(latest, dict):
        audio_status = latest.get("audio_status")
        if (
            latest.get("stale") is False
            and latest.get("recorded_before_current_recorder_binary") is False
            and isinstance(audio_status, dict)
            and audio_status.get("state") == "valid"
        ):
            return "recent valid packaged capture contradicts packaged preflight permission blockers"
    return "packaged recorder is armed; packaged preflight permission blockers may be from a sandboxed caller"


def packaged_permission_hint_payload(
    blockers: list[str],
    preflight_binary: Path,
    *,
    include_refresh_recovery: bool = False,
) -> dict[str, object]:
    hint = permission_hint_for_blockers(
        blockers,
        preflight_binary,
        include_refresh_recovery=include_refresh_recovery,
    )
    return {
        "preflight_permission_guidance": hint["permission_guidance"],
        "preflight_permission_targets": hint["permission_targets"],
    }


def preflight_next_payload(next_command: str | None, preview_command: str | None) -> dict[str, object]:
    return {
        "preflight_next": next_command,
        "preflight_next_is_executable_command": command_is_executable(next_command),
        "preflight_next_requires_user_approval": command_requires_user_approval(next_command),
        "preflight_next_mutates_state": command_mutates_state(next_command),
        "preflight_next_requests_mac_permissions": command_requests_mac_permissions(next_command),
        "preflight_next_records_audio": command_records_audio(next_command),
        "preflight_preview": preview_command,
        "preflight_preview_is_executable_command": command_is_executable(preview_command),
        "preflight_preview_requires_user_approval": command_requires_user_approval(preview_command),
        "preflight_preview_mutates_state": command_mutates_state(preview_command),
        "preflight_preview_requests_mac_permissions": command_requests_mac_permissions(preview_command),
        "preflight_preview_records_audio": command_records_audio(preview_command),
    }


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


def normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def normalized_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            integer = int(item)
        except (TypeError, ValueError):
            continue
        if integer not in normalized:
            normalized.append(integer)
    return normalized


def effective_hearing_status_payload(
    hearing: object,
    preflight_hint: dict[str, object] | None = None,
) -> dict[str, object]:
    effective = dict(hearing) if isinstance(hearing, dict) else {}
    if not isinstance(preflight_hint, dict):
        return effective
    blockers = normalized_string_list(preflight_hint.get("preflight_blockers"))
    if not blockers:
        return effective
    previous_status = str(effective.get("status") or "").strip()
    previous_reason = str(effective.get("reason") or "").strip()
    effective["can_capture_next"] = False
    effective["status"] = "blocked"
    effective["reason"] = "packaged preflight blockers"
    if previous_status:
        effective["underlying_status"] = previous_status
    if previous_reason:
        effective["underlying_reason"] = previous_reason
    message = (
        "Hearing status: blocked; not capturing new speech now "
        f"(packaged preflight blockers: {'; '.join(blockers)})."
    )
    age_seconds = effective.get("latest_segment_age_seconds")
    if effective.get("latest_segment_stale") and isinstance(age_seconds, int):
        message += f" Latest segment is stale: {format_age(age_seconds)} ago."
    effective["message"] = message
    return effective


def packaged_preflight_has_blockers(preflight_hint: object) -> bool:
    if not isinstance(preflight_hint, dict):
        return False
    blockers = preflight_hint.get("preflight_blockers")
    return isinstance(blockers, list) and bool(blockers)


def recommended_command_payload(payload: dict[str, object]) -> dict[str, object]:
    capture_readiness_payload = payload.get("capture_readiness")
    capture_readiness_next = None
    if (
        isinstance(capture_readiness_payload, dict)
        and str(capture_readiness_payload.get("status") or "") == "fallback"
    ):
        capture_readiness_next = capture_readiness_payload.get("next")
    hotkey_repair_hint = payload.get("hotkey_repair_hint")
    hotkey_repair_command = None
    hotkey_repair_diagnostic = None
    if isinstance(hotkey_repair_hint, dict) and hotkey_repair_hint.get("available"):
        hotkey_repair_command = hotkey_repair_hint.get("command")
        hotkey_repair_diagnostic = hotkey_repair_hint.get("diagnostic_command")
    candidates = [
        ("preflight_next", payload.get("preflight_next")),
        ("recovery_command", payload.get("recovery_command")),
        ("hotkey_repair_hint.command", hotkey_repair_command),
        ("hotkey_repair_hint.diagnostic_command", hotkey_repair_diagnostic),
        ("capture_readiness.next", capture_readiness_next),
        ("live_verification_command", payload.get("live_verification_command")),
        ("next", payload.get("next")),
    ]
    source = None
    command = None
    for candidate_source, candidate_command in candidates:
        candidate_text = str(candidate_command or "").strip()
        if candidate_text:
            source = candidate_source
            command = candidate_text
            break
    plan = recommended_command_plan(command)
    approval_summary = plan.get("approval_summary") if isinstance(plan, dict) else {}
    if not isinstance(approval_summary, dict):
        approval_summary = {}
    return {
        "recommended_command": command,
        "recommended_command_source": source,
        "recommended_command_is_executable": command_is_executable(command),
        "recommended_command_requires_user_approval": command_requires_user_approval(command),
        "recommended_command_mutates_state": command_mutates_state(command),
        "recommended_command_requests_mac_permissions": command_requests_mac_permissions(command),
        "recommended_command_records_audio": command_records_audio(command),
        "recommended_command_approval_reasons": approval_reasons_from_summary(approval_summary),
        "recommended_command_approval_summary": approval_summary,
        "recommended_command_plan": plan,
    }


def recommended_command_plan(command: str | None) -> dict[str, object] | None:
    if command == "DURATION=5 make doubao-shadow-capture-once-packaged":
        try:
            from doubao_shadow_capture_once_plan import build_capture_once_plan
        except ModuleNotFoundError:
            from bench.scripts.doubao_shadow_capture_once_plan import build_capture_once_plan
        return build_capture_once_plan()
    if command == "TIMEOUT=30 make doubao-shadow-live-verify":
        try:
            from doubao_shadow_live_verify_plan import build_live_verify_plan
        except ModuleNotFoundError:
            from bench.scripts.doubao_shadow_live_verify_plan import build_live_verify_plan
        return build_live_verify_plan()
    if command == "TIMEOUT=30 make hotkey-probe-packaged":
        try:
            from hotkey_probe_plan import build_hotkey_probe_plan
        except ModuleNotFoundError:
            from bench.scripts.hotkey_probe_plan import build_hotkey_probe_plan
        return build_hotkey_probe_plan()
    if command != "make doubao-shadow-refresh-packaged":
        return None
    try:
        from doubao_shadow_refresh_plan import build_refresh_plan
    except ModuleNotFoundError:
        from bench.scripts.doubao_shadow_refresh_plan import build_refresh_plan
    return build_refresh_plan()


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


def readiness_blockers(payload: dict[str, object]) -> list[str]:
    blockers: list[str] = []
    hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict):
        hearing = {}
    status = str(hearing.get("status") or "").strip()
    reason = str(hearing.get("reason") or "").strip()
    if status == "stopped":
        blockers.append("recorder_stopped")
    if reason == "packaged preflight required before live capture":
        blockers.append("packaged_preflight_required")
    if reason == "hotkey mismatch; use fixed-duration capture":
        blockers.append("hotkey_mismatch")
    hotkey_repair_hint = payload.get("hotkey_repair_hint")
    if isinstance(hotkey_repair_hint, dict) and hotkey_repair_hint.get("settings_conflict"):
        blockers.append("hotkey_candidate_conflicts_with_doubao_settings")
    if hearing.get("latest_segment_stale"):
        blockers.append("latest_segment_stale")
    if hearing.get("latest_segment_recorded_before_current_recorder_binary"):
        blockers.append("latest_segment_before_current_recorder_binary")
    segments = payload.get("segments")
    latest_segment = segments.get("latest") if isinstance(segments, dict) else None
    if isinstance(latest_segment, dict) and latest_segment.get("recorded_before_current_recorder_binary"):
        blockers.append("latest_segment_before_current_recorder_binary")

    preflight_blockers = payload.get("preflight_blockers")
    if isinstance(preflight_blockers, list):
        for blocker in preflight_blockers:
            blocker_text = str(blocker)
            if blocker_text == "Microphone permission: denied":
                blockers.append("microphone_permission_denied")
            elif blocker_text == "Accessibility permission: denied":
                blockers.append("accessibility_permission_denied")
            elif blocker_text.startswith("Expected input device:"):
                blockers.append("expected_input_device")
            elif blocker_text.startswith("Shadow recorder binary:"):
                blockers.append("shadow_recorder_binary")

    preflight_warnings = payload.get("preflight_warnings")
    if isinstance(preflight_warnings, list):
        for warning in preflight_warnings:
            if str(warning).startswith("Packaged hotkey probe is stale"):
                blockers.append("stale_packaged_hotkey_probe")

    deduped: list[str] = []
    for blocker in blockers:
        if blocker not in deduped:
            deduped.append(blocker)
    permission_priority = ["microphone_permission_denied", "accessibility_permission_denied"]
    if any(blocker in deduped for blocker in permission_priority):
        return [blocker for blocker in permission_priority if blocker in deduped] + [
            blocker for blocker in deduped if blocker not in permission_priority
        ]
    return deduped


def primary_recovery_command_payload(payload: dict[str, object], command: str | None) -> dict[str, object]:
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
    if command_text == str(payload.get("recommended_command") or "").strip():
        return {
            "primary_recovery_command": command_text,
            "primary_recovery_command_is_executable": bool(payload.get("recommended_command_is_executable")),
            "primary_recovery_requires_user_approval": bool(
                payload.get("recommended_command_requires_user_approval")
            ),
            "primary_recovery_mutates_state": bool(payload.get("recommended_command_mutates_state")),
            "primary_recovery_requests_mac_permissions": bool(
                payload.get("recommended_command_requests_mac_permissions")
            ),
            "primary_recovery_records_audio": bool(payload.get("recommended_command_records_audio")),
        }
    return {
        "primary_recovery_command": command_text,
        "primary_recovery_command_is_executable": command_is_executable(command_text),
        "primary_recovery_requires_user_approval": command_requires_user_approval(command_text),
        "primary_recovery_mutates_state": command_mutates_state(command_text),
        "primary_recovery_requests_mac_permissions": command_requests_mac_permissions(command_text),
        "primary_recovery_records_audio": command_records_audio(command_text),
    }


def primary_blocker_payload(payload: dict[str, object]) -> dict[str, object]:
    hearing = payload.get("effective_hearing_status")
    if not isinstance(hearing, dict):
        hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict):
        hearing = {}
    command = str(payload.get("recommended_command") or payload.get("preflight_next") or payload.get("next") or "").strip()
    result: dict[str, object] = {
        "primary_blocker": None,
        "primary_blocker_detail": "",
    }
    result.update(primary_recovery_command_payload(payload, command))
    if hearing.get("can_capture_next") is True:
        result.update(primary_recovery_command_payload(payload, None))
        return result

    preflight_blockers = normalized_string_list(payload.get("preflight_blockers"))
    permission_blockers = [
        blocker
        for blocker in preflight_blockers
        if blocker in {"Microphone permission: denied", "Accessibility permission: denied"}
    ]
    if permission_blockers:
        result["primary_blocker"] = "packaged_permissions_denied"
        result["primary_blocker_detail"] = "; ".join(permission_blockers)
        return result

    for blocker in preflight_blockers:
        if blocker.startswith("Expected input device:"):
            result["primary_blocker"] = "expected_input_device"
            result["primary_blocker_detail"] = blocker
            return result
        if blocker.startswith("Shadow recorder binary:"):
            result["primary_blocker"] = "shadow_recorder_binary"
            result["primary_blocker_detail"] = blocker
            return result

    blockers = readiness_blockers(payload)
    reason = str(hearing.get("reason") or "").strip()
    detail_by_blocker = {
        "recorder_stopped": reason or "recorder is not running",
        "packaged_preflight_required": reason or "packaged preflight required before live capture",
        "hotkey_candidate_conflicts_with_doubao_settings": "observed hotkey candidate conflicts with Doubao settings",
        "hotkey_mismatch": reason or "hotkey mismatch",
        "latest_segment_before_current_recorder_binary": "latest segment was recorded before the current recorder binary",
        "latest_segment_stale": "latest segment is stale",
        "stale_packaged_hotkey_probe": "packaged hotkey probe is stale",
    }
    for blocker in [
        "recorder_stopped",
        "packaged_preflight_required",
        "hotkey_candidate_conflicts_with_doubao_settings",
        "hotkey_mismatch",
        "latest_segment_before_current_recorder_binary",
        "latest_segment_stale",
        "stale_packaged_hotkey_probe",
    ]:
        if blocker in blockers:
            result["primary_blocker"] = blocker
            result["primary_blocker_detail"] = detail_by_blocker[blocker]
            return result
    return result


def readiness_summary_payload(payload: dict[str, object]) -> dict[str, object]:
    hearing = payload.get("effective_hearing_status")
    if not isinstance(hearing, dict):
        hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict):
        hearing = {}
    plan = payload.get("recommended_command_plan")
    plan_records_audio = None
    if isinstance(plan, dict):
        plan_records_audio = bool(plan.get("command_records_audio"))
    elif payload.get("recommended_command_is_executable"):
        plan_records_audio = command_records_audio(str(payload.get("recommended_command") or ""))
    requires_approval = bool(payload.get("recommended_command_requires_user_approval"))
    is_executable = bool(payload.get("recommended_command_is_executable"))
    can_capture_next = hearing.get("can_capture_next")
    blocked_by = readiness_blockers(payload)
    safe_to_run_now = bool(is_executable and not requires_approval)
    preview_command = payload.get("preflight_preview")
    if not preview_command and isinstance(plan, dict):
        preview_command = plan.get("plan_command")
    preview_command_text = str(preview_command or "").strip()
    preview_is_executable = (
        bool(payload.get("preflight_preview_is_executable_command"))
        if payload.get("preflight_preview") == preview_command
        else command_is_executable(preview_command_text)
    )
    preview_requires_approval = (
        bool(payload.get("preflight_preview_requires_user_approval"))
        if payload.get("preflight_preview") == preview_command
        else command_requires_user_approval(preview_command_text)
    )
    preview_mutates_state = (
        bool(payload.get("preflight_preview_mutates_state"))
        if payload.get("preflight_preview") == preview_command
        else command_mutates_state(preview_command_text)
    )
    preview_requests_permissions = (
        bool(payload.get("preflight_preview_requests_mac_permissions"))
        if payload.get("preflight_preview") == preview_command
        else command_requests_mac_permissions(preview_command_text)
    )
    preview_records_audio = (
        bool(payload.get("preflight_preview_records_audio"))
        if payload.get("preflight_preview") == preview_command
        else command_records_audio(preview_command_text)
    )
    preview_safe_to_run_now = bool(
        preview_is_executable
        and not preview_requires_approval
        and not preview_mutates_state
        and not preview_requests_permissions
        and not preview_records_audio
    )
    next_safe_command = None
    if preview_safe_to_run_now:
        next_safe_command = preview_command_text
    elif safe_to_run_now:
        next_safe_command = payload.get("recommended_command")
    next_user_approval_command = payload.get("recommended_command") if requires_approval else None
    if can_capture_next is True:
        safe_to_run_reason = "recorder can capture next utterance"
        user_action_required = False
    elif requires_approval:
        safe_to_run_reason = "recommended command requires user approval"
        user_action_required = True
    elif is_executable:
        safe_to_run_reason = "recommended command can run without user approval"
        user_action_required = bool(blocked_by)
    else:
        safe_to_run_reason = "recommended action is guidance, not an executable command"
        user_action_required = bool(blocked_by)
    permission_targets = normalized_string_list(payload.get("preflight_permission_targets"))
    permission_guidance = str(payload.get("preflight_permission_guidance") or "").strip()
    return {
        "status": str(hearing.get("status") or "unknown"),
        "can_capture_next": can_capture_next,
        "primary_blocker": payload.get("primary_blocker"),
        "primary_blocker_detail": payload.get("primary_blocker_detail", ""),
        "primary_recovery_command": payload.get("primary_recovery_command"),
        "primary_recovery_command_is_executable": bool(payload.get("primary_recovery_command_is_executable")),
        "primary_recovery_requires_user_approval": bool(payload.get("primary_recovery_requires_user_approval")),
        "primary_recovery_mutates_state": bool(payload.get("primary_recovery_mutates_state")),
        "primary_recovery_requests_mac_permissions": bool(
            payload.get("primary_recovery_requests_mac_permissions")
        ),
        "primary_recovery_records_audio": bool(payload.get("primary_recovery_records_audio")),
        "primary_permission_target": permission_targets[0] if permission_targets else None,
        "permission_targets": permission_targets,
        "permission_guidance": permission_guidance if permission_targets else "",
        "blocked_by": blocked_by,
        "user_action_required": user_action_required,
        "secondary_diagnostics_deferred_until_permissions": bool(
            payload.get("secondary_diagnostics_deferred_until_permissions")
        ),
        "recommended_command": payload.get("recommended_command"),
        "recommended_command_requires_user_approval": requires_approval,
        "recommended_command_records_audio": plan_records_audio,
        "recommended_command_mutates_state": bool(payload.get("recommended_command_mutates_state")),
        "recommended_command_requests_mac_permissions": bool(
            payload.get("recommended_command_requests_mac_permissions")
        ),
        "recommended_command_approval_reasons": normalized_string_list(
            payload.get("recommended_command_approval_reasons")
        ),
        "next_role": str(payload.get("next_role") or "primary_action"),
        "pending_clip_action": payload.get("pending_clip_action"),
        "pending_clip_action_is_executable_command": bool(
            payload.get("pending_clip_action_is_executable_command")
        ),
        "pending_clip_action_requires_user_approval": bool(
            payload.get("pending_clip_action_requires_user_approval")
        ),
        "pending_clip_action_mutates_state": bool(payload.get("pending_clip_action_mutates_state")),
        "pending_clip_action_requests_mac_permissions": bool(
            payload.get("pending_clip_action_requests_mac_permissions")
        ),
        "pending_clip_action_records_audio": bool(payload.get("pending_clip_action_records_audio")),
        "pending_clip_cleanup_deferred_until_permissions": bool(
            payload.get("pending_clip_cleanup_deferred_until_permissions")
        ),
        "pending_clip_action_preview": payload.get("pending_clip_action_preview"),
        "pending_clip_action_preview_is_executable_command": bool(
            payload.get("pending_clip_action_preview_is_executable_command")
        ),
        "pending_clip_action_preview_requires_user_approval": bool(
            payload.get("pending_clip_action_preview_requires_user_approval")
        ),
        "pending_clip_action_preview_mutates_state": bool(
            payload.get("pending_clip_action_preview_mutates_state")
        ),
        "pending_clip_action_preview_requests_mac_permissions": bool(
            payload.get("pending_clip_action_preview_requests_mac_permissions")
        ),
        "pending_clip_action_preview_records_audio": bool(
            payload.get("pending_clip_action_preview_records_audio")
        ),
        "preview_command": preview_command_text or None,
        "preview_command_is_executable": preview_is_executable,
        "preview_command_requires_user_approval": preview_requires_approval,
        "preview_command_mutates_state": preview_mutates_state,
        "preview_command_requests_mac_permissions": preview_requests_permissions,
        "preview_command_records_audio": preview_records_audio,
        "preview_safe_to_run_now": preview_safe_to_run_now,
        "next_safe_command": next_safe_command,
        "next_user_approval_command": next_user_approval_command,
        "safe_to_run_now": safe_to_run_now,
        "safe_to_run_reason": safe_to_run_reason,
        "message": str(hearing.get("message") or ""),
    }


def print_hotkey_repair_hint(hint: object, *, label: str = "Hotkey repair") -> None:
    if not isinstance(hint, dict) or not hint.get("available"):
        return
    label = label.strip() or "Hotkey repair"
    candidate = hint.get("candidate")
    if isinstance(candidate, dict):
        print(
            (
                f"{label} hint: "
                f"observed keyCode={candidate.get('key_code', 'unknown')}, "
                f"modifiers={candidate.get('modifiers', 'unknown')}; "
                f"inferred modifiers={hint.get('suggested_hotkey_modifiers', 'unknown')}"
            )
    )
    confidence = str(hint.get("confidence") or "").strip()
    if confidence:
        print(f"{label} confidence: {confidence}")
    confidence_reasons = hint.get("confidence_reasons")
    if isinstance(confidence_reasons, list) and confidence_reasons:
        print(f"{label} confidence reasons: " + ", ".join(str(reason) for reason in confidence_reasons))
    if hint.get("settings_conflict"):
        display = ", ".join(normalized_string_list(hint.get("settings_display_values"))) or "unknown"
        settings_key_code = str(hint.get("settings_suggested_hotkey_key_code") or "").strip()
        settings_modifiers = str(hint.get("settings_suggested_hotkey_modifiers") or "").strip()
        suggested = str(hint.get("suggested_hotkey_modifiers") or "unknown")
        settings_parts = [f"display={display}"]
        if settings_key_code:
            settings_parts.append(f"keyCode={settings_key_code}")
        if settings_modifiers:
            settings_parts.append(f"modifiers={settings_modifiers}")
        print(
            f"{label} settings conflict: "
            f"Doubao settings {', '.join(settings_parts)}; observed inferred modifiers={suggested}."
        )
    command = str(hint.get("command") or "").strip()
    if command:
        print(f"{label} command: {command}")
        print(format_command_approval(f"{label} command", command))
        print(
            format_command_safety(
                f"{label} command",
                mutates_state=hint.get("command_mutates_state"),
                requests_mac_permissions=hint.get("command_requests_mac_permissions"),
                records_audio=hint.get("command_records_audio"),
            )
        )
    diagnostic_command = str(hint.get("diagnostic_command") or "").strip()
    if diagnostic_command:
        diagnostic_plan_command = str(hint.get("diagnostic_plan_command") or "").strip()
        if diagnostic_plan_command:
            print(f"{label} diagnostic plan: {diagnostic_plan_command}")
            print(format_command_approval(f"{label} diagnostic plan", diagnostic_plan_command))
            print(
                format_command_safety(
                    f"{label} diagnostic plan",
                    mutates_state=hint.get("diagnostic_plan_mutates_state"),
                    requests_mac_permissions=hint.get("diagnostic_plan_requests_mac_permissions"),
                    records_audio=hint.get("diagnostic_plan_records_audio"),
                )
            )
        print(f"{label} diagnostic: {diagnostic_command}")
        print(format_command_approval(f"{label} diagnostic", diagnostic_command))
        print(
            format_command_safety(
                f"{label} diagnostic",
                mutates_state=hint.get("diagnostic_command_mutates_state"),
                requests_mac_permissions=hint.get("diagnostic_command_requests_mac_permissions"),
                records_audio=hint.get("diagnostic_command_records_audio"),
            )
    )
    caution = str(hint.get("caution") or "").strip()
    if caution:
        print(f"{label} caution: {caution}.")


def packaged_preflight_blocker_hint(
    payload: dict[str, object],
    preflight_binary: Path | None = None,
    preflight_doctor: Path | None = None,
) -> dict[str, object]:
    capture_readiness_payload = payload.get("capture_readiness")
    capture_next = (
        capture_readiness_payload.get("next")
        if isinstance(capture_readiness_payload, dict)
        else None
    )
    config = payload.get("config")
    packaged_recorder_running = (
        bool(payload.get("running"))
        and isinstance(config, dict)
        and is_packaged_binary_path(config.get("binary"))
    )
    explicit_preflight_needed = (
        payload.get("next") == "make doubao-shadow-preflight-packaged"
        or capture_next == "make doubao-shadow-preflight-packaged"
    )
    if not explicit_preflight_needed and not packaged_recorder_running:
        return empty_preflight_blocker_hint()
    if preflight_binary is None or preflight_doctor is None:
        return empty_preflight_blocker_hint()

    blockers: list[str] = []
    if not os.access(preflight_binary, os.X_OK):
        blockers.append(f"Shadow recorder binary: not executable ({preflight_binary})")
    warnings = packaged_preflight_warnings(preflight_binary)

    try:
        completed = subprocess.run([str(preflight_doctor), "--json"], capture_output=True, text=True, check=False)
    except OSError as error:
        result = {
            "preflight_blockers": blockers,
            "preflight_blockers_available": bool(blockers),
            "preflight_blockers_error": f"failed to run {preflight_doctor} --json: {error}",
            "preflight_warnings": warnings,
            "preflight_mac_permissions": {},
            "preflight_input_device": {},
            "preflight_input_device_detail": "",
        }
        result.update(
            packaged_permission_hint_payload(
                blockers,
                preflight_binary,
                include_refresh_recovery=bool(warnings),
            )
        )
        result.update(preflight_next_payload(*packaged_preflight_next_command(blockers, preflight_binary)))
        return result
    if completed.returncode != 0:
        result = {
            "preflight_blockers": blockers,
            "preflight_blockers_available": bool(blockers),
            "preflight_blockers_error": completed.stderr.strip() or f"{preflight_doctor} --json failed",
            "preflight_warnings": warnings,
            "preflight_mac_permissions": {},
            "preflight_input_device": {},
            "preflight_input_device_detail": "",
        }
        result.update(
            packaged_permission_hint_payload(
                blockers,
                preflight_binary,
                include_refresh_recovery=bool(warnings),
            )
        )
        result.update(preflight_next_payload(*packaged_preflight_next_command(blockers, preflight_binary)))
        return result
    try:
        doctor_payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        result = {
            "preflight_blockers": blockers,
            "preflight_blockers_available": bool(blockers),
            "preflight_blockers_error": f"{preflight_doctor} --json returned invalid JSON: {error}",
            "preflight_warnings": warnings,
            "preflight_mac_permissions": {},
            "preflight_input_device": {},
            "preflight_input_device_detail": "",
        }
        result.update(
            packaged_permission_hint_payload(
                blockers,
                preflight_binary,
                include_refresh_recovery=bool(warnings),
            )
        )
        result.update(preflight_next_payload(*packaged_preflight_next_command(blockers, preflight_binary)))
        return result
    if not isinstance(doctor_payload, dict):
        result = {
            "preflight_blockers": blockers,
            "preflight_blockers_available": bool(blockers),
            "preflight_blockers_error": f"{preflight_doctor} --json returned a non-object payload",
            "preflight_warnings": warnings,
            "preflight_mac_permissions": {},
            "preflight_input_device": {},
            "preflight_input_device_detail": "",
        }
        result.update(
            packaged_permission_hint_payload(
                blockers,
                preflight_binary,
                include_refresh_recovery=bool(warnings),
            )
        )
        result.update(preflight_next_payload(*packaged_preflight_next_command(blockers, preflight_binary)))
        return result

    permissions = doctor_payload.get("permissions", {})
    if not isinstance(permissions, dict):
        permissions = {}
    microphone = str(permissions.get("microphone") or "unknown")
    accessibility = str(permissions.get("accessibility") or "unknown")
    expected_input_status = str(permissions.get("expected_input_device_status") or "unknown")
    mac_permissions = mac_permission_payload(permissions)
    input_device = expected_input_device_payload(permissions)
    input_device_detail = expected_input_device_detail(permissions)
    if microphone != "granted":
        blockers.append(f"Microphone permission: {microphone}")
    if accessibility != "granted":
        blockers.append(f"Accessibility permission: {accessibility}")
    if expected_input_status not in {"matched", "not_enforced"}:
        blockers.append(input_device_detail)

    ignored_blockers: list[str] = []
    ignored_reason: str | None = None
    ignored_reason = packaged_runtime_permission_blockers_ignored_reason(payload, blockers)
    if ignored_reason:
        ignored_blockers = blockers
        blockers = []

    next_command, preview_command = packaged_preflight_next_command(blockers, preflight_binary)
    result = {
        "preflight_blockers": blockers,
        "preflight_blockers_available": True,
        "preflight_blockers_error": None,
        "preflight_ignored_blockers": ignored_blockers,
        "preflight_blockers_ignored_reason": ignored_reason,
        "preflight_warnings": warnings,
        "preflight_mac_permissions": mac_permissions,
        "preflight_input_device": input_device,
        "preflight_input_device_detail": input_device_detail,
    }
    result.update(
        packaged_permission_hint_payload(
            blockers,
            preflight_binary,
            include_refresh_recovery=bool(warnings),
        )
    )
    result.update(preflight_next_payload(next_command, preview_command))
    return result


def hearing_recovery_hint(payload: dict[str, object]) -> dict[str, object]:
    capture_readiness_payload = payload.get("capture_readiness")
    capture_next = (
        capture_readiness_payload.get("next")
        if isinstance(capture_readiness_payload, dict)
        else None
    )
    if payload.get("next") == "make doubao-shadow-preflight-packaged" or capture_next == "make doubao-shadow-preflight-packaged":
        command = "make doubao-shadow-refresh-packaged"
        return {
            "recovery_command": command,
            "recovery_condition": "if packaged preflight fails due denied permissions or stale packaged helpers",
            "recovery_is_executable_command": command_is_executable(command),
            "recovery_requires_user_approval": command_requires_user_approval(command),
            "recovery_mutates_state": command_mutates_state(command),
            "recovery_requests_mac_permissions": command_requests_mac_permissions(command),
            "recovery_records_audio": command_records_audio(command),
        }
    return {
        "recovery_command": None,
        "recovery_condition": None,
        "recovery_is_executable_command": False,
        "recovery_requires_user_approval": False,
        "recovery_mutates_state": False,
        "recovery_requests_mac_permissions": False,
        "recovery_records_audio": False,
    }


def hearing_check_payload(
    pid_file: Path,
    segments: Path,
    manifest: Path | None = None,
    log_file: Path | None = None,
    min_duration: float = 0.25,
    now: datetime | None = None,
    preflight_binary: Path | None = None,
    preflight_doctor: Path | None = None,
    doubao_settings_roots: list[Path] | None = None,
) -> dict[str, object]:
    payload = status_payload(
        pid_file=pid_file,
        segments=segments,
        manifest=manifest,
        log_file=log_file,
        min_duration=min_duration,
        now=now,
    )
    hearing = payload.get("hearing_status")
    if not isinstance(hearing, dict):
        hearing = {}
    settings_hint = doubao_settings_shortcut_hints(doubao_settings_roots)
    hotkey_config_match = shadow_hotkey_config_match_payload(payload.get("config", {}), settings_hint)
    result = {
        "can_hear_next": hearing.get("can_capture_next"),
        "hearing_status": hearing,
        "capture_readiness": payload.get("capture_readiness"),
        "doubao_settings_shortcut_hints": settings_hint,
        "shadow_hotkey_config_match": hotkey_config_match,
        "transcript_visibility": TRANSCRIPT_VISIBILITY,
        "hotkey_repair_hint": hotkey_repair_hint_with_settings(
            payload.get("hotkey_repair_hint"),
            settings_hint,
        ),
        "live_verification_command": payload.get("live_verification_command"),
        "live_verification_command_is_executable": payload.get("live_verification_command_is_executable"),
        "live_verification_command_requires_user_approval": payload.get("live_verification_command_requires_user_approval"),
        "live_verification_command_mutates_state": payload.get("live_verification_command_mutates_state"),
        "live_verification_command_requests_mac_permissions": payload.get("live_verification_command_requests_mac_permissions"),
        "live_verification_command_records_audio": payload.get("live_verification_command_records_audio"),
        "next": payload.get("next"),
        "next_is_executable_command": payload.get("next_is_executable_command"),
        "next_requires_user_approval": payload.get("next_requires_user_approval"),
        "next_mutates_state": payload.get("next_mutates_state"),
        "next_requests_mac_permissions": payload.get("next_requests_mac_permissions"),
        "next_records_audio": payload.get("next_records_audio"),
        "next_role": payload.get("next_role"),
        "pending_clip_action": payload.get("pending_clip_action"),
        "pending_clip_action_is_executable_command": payload.get("pending_clip_action_is_executable_command"),
        "pending_clip_action_requires_user_approval": payload.get("pending_clip_action_requires_user_approval"),
        "pending_clip_action_mutates_state": payload.get("pending_clip_action_mutates_state"),
        "pending_clip_action_requests_mac_permissions": payload.get("pending_clip_action_requests_mac_permissions"),
        "pending_clip_action_records_audio": payload.get("pending_clip_action_records_audio"),
        "pending_clip_action_preview": payload.get("pending_clip_action_preview"),
        "pending_clip_action_preview_is_executable_command": payload.get(
            "pending_clip_action_preview_is_executable_command"
        ),
        "pending_clip_action_preview_requires_user_approval": payload.get(
            "pending_clip_action_preview_requires_user_approval"
        ),
        "pending_clip_action_preview_mutates_state": payload.get("pending_clip_action_preview_mutates_state"),
        "pending_clip_action_preview_requests_mac_permissions": payload.get(
            "pending_clip_action_preview_requests_mac_permissions"
        ),
        "pending_clip_action_preview_records_audio": payload.get("pending_clip_action_preview_records_audio"),
    }
    result.update(hearing_recovery_hint(payload))
    result.update(
        packaged_preflight_blocker_hint(
            payload,
            preflight_binary=preflight_binary,
            preflight_doctor=preflight_doctor,
        )
    )
    effective_hearing = effective_hearing_status_payload(hearing, result)
    result["can_hear_next"] = effective_hearing.get("can_capture_next")
    result["effective_hearing_status"] = effective_hearing
    result["secondary_diagnostics_deferred_until_permissions"] = packaged_preflight_has_blockers(result)
    hotkey_repair_hint = result.get("hotkey_repair_hint")
    hotkey_repair_deferred = bool(
        result["secondary_diagnostics_deferred_until_permissions"]
        and isinstance(hotkey_repair_hint, dict)
        and hotkey_repair_hint.get("available")
    )
    result["hotkey_repair_deferred_until_permissions"] = hotkey_repair_deferred
    if isinstance(hotkey_repair_hint, dict):
        hotkey_repair_hint["deferred_until_permissions"] = hotkey_repair_deferred
        hotkey_repair_hint["role"] = "secondary_after_permissions" if hotkey_repair_deferred else "primary_diagnostic"
    result.update(recommended_command_payload(result))
    result["pending_clip_cleanup_deferred_until_permissions"] = bool(
        result["secondary_diagnostics_deferred_until_permissions"]
        and result.get("pending_clip_action")
        and result.get("recommended_command") != result.get("pending_clip_action")
    )
    result.update(primary_blocker_payload(result))
    readiness_summary = readiness_summary_payload(result)
    result["primary_permission_target"] = readiness_summary.get("primary_permission_target")
    result["permission_targets"] = readiness_summary.get("permission_targets", [])
    result["permission_guidance"] = readiness_summary.get("permission_guidance", "")
    result["readiness_summary"] = readiness_summary
    return result


def print_hearing_check_json(
    pid_file: Path,
    segments: Path,
    manifest: Path | None = None,
    log_file: Path | None = None,
    min_duration: float = 0.25,
    now: datetime | None = None,
    preflight_binary: Path | None = None,
    preflight_doctor: Path | None = None,
) -> int:
    print(
        json.dumps(
            hearing_check_payload(
                pid_file=pid_file,
                segments=segments,
                manifest=manifest,
                log_file=log_file,
                min_duration=min_duration,
                now=now,
                preflight_binary=preflight_binary,
                preflight_doctor=preflight_doctor,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start, stop, or inspect the Doubao shadow recorder daemon.")
    parser.add_argument("--binary", default=Path("app/SwitchType/.build/debug/SwitchTypeDoubaoShadow"), type=Path)
    parser.add_argument("--output-dir", default=Path("bench/samples/doubao-shadow/audio"), type=Path)
    parser.add_argument("--segments", default=Path("bench/samples/doubao-shadow/segments.jsonl"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/doubao-shadow/manifest.jsonl"), type=Path)
    parser.add_argument("--pid-file", default=Path("bench/samples/doubao-shadow/shadow.pid"), type=Path)
    parser.add_argument("--log-file", default=Path("bench/samples/doubao-shadow/shadow.log"), type=Path)
    parser.add_argument("--expected-input-device", default=os.getenv("SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"))
    parser.add_argument("--hotkey-key-code", default=os.getenv("SWITCHTYPE_HOTKEY_KEY_CODE"))
    parser.add_argument("--hotkey-modifiers", default=os.getenv("SWITCHTYPE_HOTKEY_MODIFIERS"))
    parser.add_argument("--capture-focused-text", action="store_true", default=is_truthy(os.getenv("SWITCHTYPE_CAPTURE_FOCUSED_TEXT")))
    parser.add_argument("--debug-hotkey-events", action="store_true", default=is_truthy(os.getenv("SWITCHTYPE_DEBUG_HOTKEY_EVENTS")))
    parser.add_argument("--text-capture-delay-seconds", default=os.getenv("SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"))
    parser.add_argument("--text-capture-timeout-seconds", default=os.getenv("SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"))
    parser.add_argument("--min-duration", default=0.25, type=float, help="Minimum accepted WAV duration in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable status JSON.")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--hearing-check", action="store_true")
    return parser


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    args = parser().parse_args()
    if args.stop:
        return stop_daemon(pid_file=args.pid_file)
    if args.hearing_check:
        if args.json:
            return print_hearing_check_json(
                pid_file=args.pid_file,
                segments=args.segments,
                manifest=args.manifest,
                log_file=args.log_file,
                min_duration=args.min_duration,
                preflight_binary=DEFAULT_PACKAGED_SHADOW_BINARY,
                preflight_doctor=DEFAULT_PACKAGED_DOCTOR_BINARY,
            )
        return print_hearing_check(
            pid_file=args.pid_file,
            segments=args.segments,
            manifest=args.manifest,
            log_file=args.log_file,
            min_duration=args.min_duration,
            preflight_binary=DEFAULT_PACKAGED_SHADOW_BINARY,
            preflight_doctor=DEFAULT_PACKAGED_DOCTOR_BINARY,
        )
    if args.status:
        if args.json:
            print(
                json.dumps(
                    status_payload(
                        pid_file=args.pid_file,
                        segments=args.segments,
                        manifest=args.manifest,
                        log_file=args.log_file,
                        min_duration=args.min_duration,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        return print_status(
            pid_file=args.pid_file,
            segments=args.segments,
            manifest=args.manifest,
            log_file=args.log_file,
            min_duration=args.min_duration,
        )
    return start_daemon(
        binary=args.binary,
        output_dir=args.output_dir,
        segments=args.segments,
        pid_file=args.pid_file,
        log_file=args.log_file,
        expected_input_device=args.expected_input_device,
        hotkey_key_code=args.hotkey_key_code,
        hotkey_modifiers=args.hotkey_modifiers,
            capture_focused_text=args.capture_focused_text,
            text_capture_delay_seconds=args.text_capture_delay_seconds,
            text_capture_timeout_seconds=args.text_capture_timeout_seconds,
            debug_hotkey_events=args.debug_hotkey_events,
        )


if __name__ == "__main__":
    raise SystemExit(main())
