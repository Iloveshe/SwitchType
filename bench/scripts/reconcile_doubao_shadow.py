from __future__ import annotations

import argparse
import csv
import errno
import json
import os
import re
import subprocess
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Sequence

try:
    from prepare_ascend_public_samples import terms_from_reference
except ModuleNotFoundError:
    from bench.scripts.prepare_ascend_public_samples import terms_from_reference

try:
    from sample_status import classify_audio
except ModuleNotFoundError:
    from bench.scripts.sample_status import classify_audio

try:
    from doubao_shadow_daemon import format_age, format_ignored_hotkey_candidates, status_payload
except ModuleNotFoundError:
    from bench.scripts.doubao_shadow_daemon import format_age, format_ignored_hotkey_candidates, status_payload

try:
    from command_safety import (
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )
except ModuleNotFoundError:
    from bench.scripts.command_safety import (
        command_mutates_state,
        command_records_audio,
        command_requests_mac_permissions,
        command_requires_user_approval,
        format_command_approval,
        format_command_safety,
    )


def load_protected_terms(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(term) for term in data.get("protected_terms", [])]


def load_segments(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
    return rows


def load_segments_if_exists(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return load_segments(path)


def load_existing_manifest(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, object]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid manifest JSON on line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            continue
        sample_id = str(row.get("id") or "").strip()
        reference = str(row.get("reference") or "").strip()
        if sample_id and reference:
            rows[sample_id] = row
    return rows


SAFE_CAPTURE_STOP_REASONS = {"hotkey_released", "record_seconds"}


class UnsupportedAsrPreviewError(ValueError):
    pass


def has_safe_capture_stop_reason(segment: dict[str, object]) -> bool:
    return str(segment.get("recording_stop_reason") or "").strip() in SAFE_CAPTURE_STOP_REASONS


def has_recording_stop_reason(segment: dict[str, object]) -> bool:
    return bool(str(segment.get("recording_stop_reason") or "").strip())


def captured_reference(segment: dict[str, object]) -> str:
    reference = str(segment.get("reference") or "").strip()
    if not reference:
        return ""
    if has_safe_capture_stop_reason(segment):
        return reference
    stop_reason = str(segment.get("recording_stop_reason") or "").strip()
    print(f"Ignored captured reference with unsafe stop reason: {stop_reason or 'missing'}")
    return ""


def safe_segment_reference(segment: dict[str, object]) -> str:
    reference = str(segment.get("reference") or "").strip()
    if not reference or not has_safe_capture_stop_reason(segment):
        return ""
    return reference


def review_reference_source_and_trust(
    *,
    existing_row: dict[str, object],
    segment: dict[str, object],
) -> tuple[str, str, str]:
    existing_reference = str(existing_row.get("reference") or "").strip()
    if existing_reference:
        return existing_reference, "existing_manifest", "yes"

    safe_reference = safe_segment_reference(segment)
    if safe_reference:
        return safe_reference, "segment_log_safe", "yes"

    return "", "", ""


def comparable_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def ascii_terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", value.lower()))


def reference_overlaps_asr_preview(reference: str, preview: str) -> bool:
    reference_text = comparable_text(reference)
    preview_text = comparable_text(preview)
    if not reference_text or not preview_text:
        return False
    if reference_text in preview_text or preview_text in reference_text:
        return True

    common_ascii_terms = ascii_terms(reference).intersection(ascii_terms(preview))
    if common_ascii_terms:
        return True

    ratio = SequenceMatcher(None, reference_text, preview_text).ratio()
    return ratio >= 0.35


def reusable_existing_reference(existing_row: dict[str, object], segment: dict[str, object]) -> str:
    reference = str(existing_row.get("reference") or "").strip()
    segment_reference = str(segment.get("reference") or "").strip()
    if reference and segment_reference and reference == segment_reference and not has_safe_capture_stop_reason(segment):
        print("Ignored existing manifest reference copied from unsafe segment capture.")
        return ""
    return reference


def reconcile_segments(
    segments_path: Path,
    manifest_path: Path,
    protected_terms: Sequence[str],
    input_func: Callable[[str], str] = input,
    preview_func: Callable[[str], str] | None = None,
    prompt_for_missing: bool = True,
    current_only: bool = False,
) -> int:
    segments = load_segments(segments_path)
    existing_manifest = load_existing_manifest(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with manifest_path.open("w", encoding="utf-8") as output:
        for index, segment in enumerate(segments, start=1):
            sample_id = str(segment.get("id") or "").strip()
            audio = str(segment.get("audio") or "").strip()
            recorded_at = str(segment.get("recorded_at") or "").strip()
            if not sample_id or not audio:
                continue
            if current_only and not has_recording_stop_reason(segment):
                existing_row = existing_manifest.get(sample_id)
                reference = reusable_existing_reference(existing_row or {}, segment)
                if not reference:
                    print("Current-only mode: skipped legacy segment without recording_stop_reason.")
                    continue
            print(f"[{index}/{len(segments)}] {sample_id}")
            if recorded_at:
                print(f"Recorded at: {recorded_at}")
            print(f"Audio: {audio}")
            existing_row = existing_manifest.get(sample_id)
            reference = reusable_existing_reference(existing_row or {}, segment)
            if reference:
                print("Using reference already in manifest.")
            else:
                reference = captured_reference(segment)
                if reference:
                    if preview_func is not None:
                        try:
                            preview = safe_asr_preview(preview_func, audio)
                        except UnsupportedAsrPreviewError as error:
                            print(f"ASR preview rejected: {error}")
                            reference = ""
                        except Exception as error:
                            print(f"ASR preview failed: {error}")
                            reference = ""
                        else:
                            if not reference_overlaps_asr_preview(reference, preview):
                                print("Ignored captured reference because ASR preview did not overlap.")
                                reference = ""
                                if prompt_for_missing and preview:
                                    print(f"ASR preview: {preview}")
                    if reference:
                        print("Using reference captured in segment log.")
                else:
                    if not prompt_for_missing:
                        print("Auto-only mode: skipped unresolved segment.")
                        reference = ""
                    elif preview_func is not None:
                        try:
                            preview = safe_asr_preview(preview_func, audio)
                        except UnsupportedAsrPreviewError as error:
                            print(f"ASR preview rejected: {error}")
                        except Exception as error:
                            print(f"ASR preview failed: {error}")
                        else:
                            if preview:
                                print(f"ASR preview: {preview}")
                    if prompt_for_missing:
                        reference = input_func("粘贴这段豆包输出的文字；直接回车跳过：").strip()
            if not reference:
                print("Skipped.")
                continue
            row = dict(existing_row or {})
            row["id"] = sample_id
            row["audio"] = audio
            row["reference"] = reference
            if "terms" not in row:
                row["terms"] = terms_from_reference(reference, protected_terms)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def reconcile_plan_payload(
    segments_path: Path,
    manifest_path: Path,
    current_only: bool = False,
    target_command: str | None = None,
    plan_command: str | None = None,
) -> dict[str, object]:
    segments = load_segments(segments_path)
    existing_manifest = load_existing_manifest(manifest_path)
    target = target_command or ("make doubao-shadow-reconcile-current" if current_only else "make doubao-shadow-reconcile")
    plan = plan_command or ("make doubao-shadow-reconcile-current-plan" if current_only else "make doubao-shadow-reconcile-plan")

    usable_segments = [
        segment
        for segment in segments
        if str(segment.get("id") or "").strip() and str(segment.get("audio") or "").strip()
    ]
    current_segments = [segment for segment in usable_segments if has_recording_stop_reason(segment)]
    legacy_segments = [segment for segment in usable_segments if not has_recording_stop_reason(segment)]
    candidates = current_segments if current_only else usable_segments
    already_in_manifest = 0
    trusted_captured_references = 0
    prompt_for_missing = 0
    sample_ids: list[str] = []
    for segment in candidates:
        sample_id = str(segment.get("id") or "").strip()
        sample_ids.append(sample_id)
        existing_row = existing_manifest.get(sample_id) or {}
        if str(existing_row.get("reference") or "").strip():
            already_in_manifest += 1
        elif str(segment.get("reference") or "").strip() and has_safe_capture_stop_reason(segment):
            trusted_captured_references += 1
        else:
            prompt_for_missing += 1

    return {
        "plan_command": plan,
        "plan_requires_user_approval": command_requires_user_approval(plan),
        "plan_mutates_state": command_mutates_state(plan),
        "plan_requests_mac_permissions": command_requests_mac_permissions(plan),
        "plan_records_audio": command_records_audio(plan),
        "target_command": target,
        "target_requires_user_approval": command_requires_user_approval(target),
        "target_mutates_state": command_mutates_state(target),
        "target_requests_mac_permissions": command_requests_mac_permissions(target),
        "target_records_audio": command_records_audio(target),
        "segments_total": len(usable_segments),
        "current_segments": len(current_segments),
        "legacy_segments": len(legacy_segments),
        "legacy_segments_skipped": len(legacy_segments) if current_only else 0,
        "manifest_samples": len(existing_manifest),
        "candidates": len(candidates),
        "already_in_manifest": already_in_manifest,
        "trusted_captured_references": trusted_captured_references,
        "will_prompt_for_missing_references": prompt_for_missing,
        "sample_ids": sample_ids,
        "does_not_write_manifest": True,
        "does_not_record_audio": True,
        "does_not_request_mac_permissions": True,
    }


def print_reconcile_plan(
    segments_path: Path,
    manifest_path: Path,
    current_only: bool = False,
    target_command: str | None = None,
    plan_command: str | None = None,
    json_output: bool = False,
) -> int:
    if json_output and plan_command is None:
        plan_command = (
            "make doubao-shadow-reconcile-current-plan-json"
            if current_only
            else "make doubao-shadow-reconcile-plan-json"
        )
    payload = reconcile_plan_payload(
        segments_path=segments_path,
        manifest_path=manifest_path,
        current_only=current_only,
        target_command=target_command,
        plan_command=plan_command,
    )
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    plan = str(payload["plan_command"])
    target = str(payload["target_command"])
    print(f"Plan: {target}")
    print(format_command_approval("Plan command", plan))
    print(
        format_command_safety(
            "Plan command",
            mutates_state=payload["plan_mutates_state"],
            requests_mac_permissions=payload["plan_requests_mac_permissions"],
            records_audio=payload["plan_records_audio"],
        )
    )
    print(format_command_approval("Target command", target))
    print(
        format_command_safety(
            "Target command",
            mutates_state=payload["target_mutates_state"],
            requests_mac_permissions=payload["target_requests_mac_permissions"],
            records_audio=payload["target_records_audio"],
        )
    )
    print(f"Segments total: {payload['segments_total']}")
    print(f"Current segments: {payload['current_segments']}")
    print(f"Legacy segments: {payload['legacy_segments']}")
    if current_only:
        print(f"Legacy segments skipped: {payload['legacy_segments_skipped']}")
    print(f"Existing manifest samples: {payload['manifest_samples']}")
    print(f"Candidate segments: {payload['candidates']}")
    print(f"Already in manifest: {payload['already_in_manifest']}")
    print(f"Trusted captured references: {payload['trusted_captured_references']}")
    print(f"Will prompt for missing references: {payload['will_prompt_for_missing_references']}")
    print("This preview does not write the manifest, prompt for references, record audio, or request macOS permissions.")
    return 0


def transcribe_asr_preview(audio: str, asr_smoke_bin: Path, environment: dict[str, str] | None = None) -> str:
    env = dict(os.environ if environment is None else environment)
    command = [str(asr_smoke_bin), "--audio", audio, "--postprocess"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0 and env.get("SWITCHTYPE_WHISPER_NO_GPU") != "1" and is_metal_failure(output):
        env["SWITCHTYPE_WHISPER_NO_GPU"] = "1"
        completed = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
        output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(output.splitlines()[-1] if output else f"{asr_smoke_bin} failed")
    return validate_asr_preview_text(completed.stdout)


def validate_asr_preview_text(preview: str) -> str:
    text = preview.strip()
    unsupported = unsupported_preview_characters(text)
    if unsupported:
        sample = "".join(dict.fromkeys(unsupported[:8]))
        raise UnsupportedAsrPreviewError(
            "unsupported script in ASR preview; expected Chinese, English, numbers, or punctuation only "
            f"(unsupported={sample})"
        )
    return text


def unsupported_preview_characters(text: str) -> list[str]:
    return [character for character in text if not is_supported_preview_character(character)]


def is_supported_preview_character(character: str) -> bool:
    if character.isspace() or character.isascii():
        return True

    codepoint = ord(character)
    if (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2A6DF
        or 0x2A700 <= codepoint <= 0x2B73F
        or 0x2B740 <= codepoint <= 0x2B81F
        or 0x2B820 <= codepoint <= 0x2CEAF
        or 0x2CEB0 <= codepoint <= 0x2EBEF
        or 0x30000 <= codepoint <= 0x3134F
    ):
        return True

    if 0x3000 <= codepoint <= 0x303F:
        return True
    if 0xFF01 <= codepoint <= 0xFF5E:
        return True

    category = unicodedata.category(character)
    return category.startswith("P") or category.startswith("S")


def safe_asr_preview(preview_func: Callable[[str], str], audio: str) -> str:
    return validate_asr_preview_text(preview_func(audio))


def is_metal_failure(output: str) -> bool:
    return "ggml_metal_buffer_init" in output or "failed to allocate buffer" in output


def write_asr_preview_report(
    segments_path: Path,
    output_path: Path,
    preview_func: Callable[[str], str],
) -> int:
    segments = load_segments(segments_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Doubao Shadow ASR Preview",
        "",
        "This file is generated from local ASR and is only an aid for matching clips to reference text. Do not use preview text as benchmark ground truth without review.",
        "",
        "| # | ID | Recorded At | Audio | Existing Reference | ASR Preview |",
        "|---|---|---|---|---|---|",
    ]
    count = 0
    for index, segment in enumerate(segments, start=1):
        sample_id = str(segment.get("id") or "").strip()
        audio = str(segment.get("audio") or "").strip()
        if not sample_id or not audio:
            continue
        recorded_at = str(segment.get("recorded_at") or "").strip()
        reference = str(segment.get("reference") or "").strip()
        try:
            preview = safe_asr_preview(preview_func, audio)
        except UnsupportedAsrPreviewError as error:
            preview = f"preview rejected: {error}"
        except Exception as error:
            preview = f"preview failed: {error}"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    markdown_cell(sample_id),
                    markdown_cell(recorded_at),
                    markdown_cell(audio),
                    markdown_cell(reference),
                    markdown_cell(preview),
                ]
            )
            + " |"
        )
        count += 1
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def print_latest_asr_preview(
    segments_path: Path,
    preview_func: Callable[[str], str],
) -> int:
    latest_segment = latest_audio_segment(load_segments(segments_path))
    if latest_segment is None:
        print("No shadow segments with audio are available.")
        return 0
    return print_segment_asr_preview(latest_segment, preview_func)


def latest_audio_segment(segments: Sequence[dict[str, object]]) -> dict[str, object] | None:
    return next(
        (
            segment
            for segment in reversed(segments)
            if str(segment.get("id") or "").strip()
            and str(segment.get("audio") or "").strip()
        ),
        None,
    )


def segment_identity(segment: dict[str, object] | None) -> tuple[str, str, str] | None:
    if segment is None:
        return None
    return (
        str(segment.get("id") or "").strip(),
        str(segment.get("audio") or "").strip(),
        str(segment.get("recorded_at") or "").strip(),
    )


def print_segment_asr_preview(
    segment: dict[str, object],
    preview_func: Callable[[str], str],
) -> int:
    sample_id = str(segment.get("id") or "").strip()
    audio = str(segment.get("audio") or "").strip()
    recorded_at = str(segment.get("recorded_at") or "").strip()
    reference = str(segment.get("reference") or "").strip()

    print(f"Latest segment: {sample_id}")
    if recorded_at:
        print(f"Recorded at: {recorded_at}")
    print(f"Audio: {audio}")
    if reference:
        print(f"Captured reference: {reference}")
    text_capture = text_capture_summary(segment)
    if text_capture:
        print(f"Text capture: {text_capture}")
    diagnostic = text_capture_diagnostic_summary(segment)
    if diagnostic:
        print(f"Text capture diagnostic: {diagnostic}")
    try:
        preview = safe_asr_preview(preview_func, audio)
    except UnsupportedAsrPreviewError as error:
        print(f"ASR preview rejected: {error}")
    except Exception as error:
        print(f"ASR preview failed: {error}")
    else:
        print(f"ASR preview: {preview}")
    return 1


def text_capture_summary(segment: dict[str, object]) -> str:
    status = str(segment.get("text_capture_status") or "").strip()
    if not status:
        return ""
    reason = str(segment.get("text_capture_reason") or "").strip()
    return f"{status}/{reason}" if reason else status


def text_capture_diagnostic_summary(segment: dict[str, object]) -> str:
    fields = [
        ("text_capture_attempts", "attempts", ""),
        ("text_capture_elapsed_seconds", "elapsed", "s"),
        ("text_capture_before_length", "before_len", ""),
        ("text_capture_after_length", "after_len", ""),
        ("text_capture_before_process_identifier", "before_pid", ""),
        ("text_capture_after_process_identifier", "after_pid", ""),
    ]
    parts = [
        f"{label}={segment[key]}{suffix}"
        for key, label, suffix in fields
        if segment.get(key) is not None
    ]
    before_location = segment.get("text_capture_before_selection_location")
    before_length = segment.get("text_capture_before_selection_length")
    if before_location is not None and before_length is not None:
        parts.append(f"before_sel={before_location}+{before_length}")
    after_location = segment.get("text_capture_after_selection_location")
    after_length = segment.get("text_capture_after_selection_length")
    if after_location is not None and after_length is not None:
        parts.append(f"after_sel={after_location}+{after_length}")
    return ", ".join(parts)


def wait_for_next_asr_preview(
    segments_path: Path,
    preview_func: Callable[[str], str],
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.5,
    load_func: Callable[[Path], Sequence[dict[str, object]]] = load_segments_if_exists,
    sleep_func: Callable[[float], None] = time.sleep,
    monotonic_func: Callable[[], float] = time.monotonic,
    recorder_running_func: Callable[[], bool] | None = None,
    status_func: Callable[[], dict[str, object]] | None = None,
) -> int:
    if recorder_running_func is not None and not recorder_running_func():
        print("Doubao shadow recorder is not running.")
        print("Start it with: make doubao-shadow-start-auto-packaged")
        return 0

    baseline_status_payload = status_func() if status_func is not None else None
    baseline_segment = latest_audio_segment(load_func(segments_path))
    baseline_identity = segment_identity(baseline_segment)
    deadline = monotonic_func() + timeout_seconds
    print(f"Waiting up to {timeout_seconds:.1f}s for the next Doubao shadow segment.")
    while True:
        latest_segment = latest_audio_segment(load_func(segments_path))
        if latest_segment is not None and segment_identity(latest_segment) != baseline_identity:
            print("New segment captured.")
            return print_segment_asr_preview(latest_segment, preview_func)

        remaining = deadline - monotonic_func()
        if remaining <= 0:
            print(f"No new shadow segment captured within {timeout_seconds:.1f}s.")
            if baseline_segment is not None:
                print(f"Latest existing segment: {str(baseline_segment.get('id') or '').strip()}")
            if status_func is not None:
                print_wait_timeout_status(status_func(), baseline_payload=baseline_status_payload)
            return 0
        sleep_func(min(poll_interval_seconds, remaining))


def hotkey_probe_command(config: dict[str, object] | None) -> str:
    binary = str((config or {}).get("binary") or "")
    if "dist/SwitchType.app" in binary:
        return "make hotkey-probe-packaged"
    return "make hotkey-probe"


def hotkey_probe_guidance(config: dict[str, object] | None) -> str:
    command = hotkey_probe_command(config)
    if command.endswith("-packaged"):
        return f"Verify packaged hotkey visibility with: {command}"
    return f"Verify hotkey visibility with: {command}"


def fixed_duration_fallback_command(config: dict[str, object] | None) -> str:
    binary = str((config or {}).get("binary") or "")
    if "dist/SwitchType.app" in binary:
        return "DURATION=5 make doubao-shadow-capture-once-packaged"
    return "DURATION=5 make doubao-shadow-record-seconds"


def enable_hotkey_diagnostics_command(config: dict[str, object] | None) -> str:
    binary = str((config or {}).get("binary") or "")
    if "dist/SwitchType.app" in binary:
        return "SWITCHTYPE_DEBUG_HOTKEY_EVENTS=1 make doubao-shadow-restart-packaged"
    return "SWITCHTYPE_DEBUG_HOTKEY_EVENTS=1 make doubao-shadow-start-auto"


def print_wait_timeout_status(payload: dict[str, object], baseline_payload: dict[str, object] | None = None) -> None:
    if payload.get("running"):
        print(f"Recorder status: running pid {payload.get('pid', 'unknown')}")
    else:
        print("Recorder status: not running")
    config = payload.get("config")
    if isinstance(config, dict):
        modifiers = str(config.get("hotkey_modifiers") or "unknown")
        key_code = str(config.get("hotkey_key_code") or "unknown")
        print(f"Configured hotkey: {modifiers} key_code={key_code}")
    hotkey_events = payload.get("hotkey_events")
    hotkey_events_observed = 0
    hotkey_events_observed_during_wait: int | None = None
    hotkey_recording_events_during_wait: int | None = None
    if isinstance(hotkey_events, dict):
        hotkey_events_observed = int(hotkey_events.get("observed") or 0)
        hotkey_events_recognized = int(hotkey_events.get("recognized") or 0)
        hotkey_events_enabled = bool(hotkey_events.get("enabled"))
        print(f"Hotkey events observed: {hotkey_events_observed}")
        print(f"Hotkey recording events: {hotkey_events_recognized}")
        baseline_hotkey_events = baseline_payload.get("hotkey_events") if isinstance(baseline_payload, dict) else None
        if isinstance(baseline_hotkey_events, dict):
            baseline_observed = int(baseline_hotkey_events.get("observed") or 0)
            baseline_recognized = int(baseline_hotkey_events.get("recognized") or 0)
            hotkey_events_observed_during_wait = max(0, hotkey_events_observed - baseline_observed)
            hotkey_recording_events_during_wait = max(0, hotkey_events_recognized - baseline_recognized)
            print(
                "Hotkey events observed during this wait: "
                f"{hotkey_events_observed_during_wait} (total since recorder start: {hotkey_events_observed})"
            )
            print(
                "Hotkey recording events during this wait: "
                f"{hotkey_recording_events_during_wait} (total since recorder start: {hotkey_events_recognized})"
            )
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
        observed_for_this_wait = (
            hotkey_events_observed_during_wait
            if hotkey_events_observed_during_wait is not None
            else hotkey_events_observed
        )
        if hotkey_events.get("diagnosis") == "events_visible_no_recording_match" and observed_for_this_wait > 0:
            print("Hotkey diagnosis: key events are visible, but none matched the recorder hotkey.")
            print("Fixed-duration fallback: DURATION=5 make doubao-shadow-capture-once-packaged")
        elif not hotkey_events_enabled:
            print("Hotkey event diagnostics are disabled.")
            print(f"Enable diagnostics with: {enable_hotkey_diagnostics_command(config if isinstance(config, dict) else None)}")
        elif observed_for_this_wait == 0:
            if hotkey_events_observed > 0:
                print("No new hotkey events were observed during this wait.")
            else:
                print("No hotkey events were observed during this wait.")
            print(hotkey_probe_guidance(config if isinstance(config, dict) else None))
            print(f"If you need a sample now: {fixed_duration_fallback_command(config if isinstance(config, dict) else None)}")
    segments = payload.get("segments")
    latest = segments.get("latest") if isinstance(segments, dict) else None
    if isinstance(latest, dict):
        parts = [f"Latest status segment: {latest.get('id', 'unknown')}"]
        age_seconds = latest.get("age_seconds")
        if isinstance(age_seconds, int):
            parts.append(f"age={format_age(age_seconds)}")
        audio_status = latest.get("audio_status")
        if isinstance(audio_status, dict):
            parts.append(f"audio={audio_status.get('state', 'unknown')}")
            duration = audio_status.get("duration_seconds")
            if duration is not None:
                parts.append(f"duration={float(duration):.2f}s")
            parts.append(f"bytes={audio_status.get('bytes', 0)}")
        print(", ".join(parts))
    observed_for_this_wait = (
        hotkey_events_observed_during_wait
        if hotkey_events_observed_during_wait is not None
        else hotkey_events_observed
    )
    if observed_for_this_wait > 0:
        print(f"If you held the Doubao hotkey during this wait, run: {hotkey_probe_command(config if isinstance(config, dict) else None)}")


def shadow_recorder_is_running(pid_file: Path) -> bool:
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as error:
        if isinstance(error, PermissionError) or error.errno == errno.EPERM:
            return True
        return False


def write_review_tsv(
    segments_path: Path,
    output_path: Path,
    preview_func: Callable[[str], str],
    existing_manifest_path: Path | None = None,
) -> int:
    segments = load_segments(segments_path)
    existing_manifest = load_existing_manifest(existing_manifest_path) if existing_manifest_path else {}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "recorded_at",
                "audio",
                "audio_state",
                "audio_duration_seconds",
                "recording_stop_reason",
                "text_capture_status",
                "text_capture_reason",
                "asr_preview",
                "reference",
                "reference_source",
                "reference_trusted",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for segment in segments:
            sample_id = str(segment.get("id") or "").strip()
            audio = str(segment.get("audio") or "").strip()
            if not sample_id or not audio:
                continue
            existing_row = existing_manifest.get(sample_id) or {}
            reference, reference_source, reference_trusted = review_reference_source_and_trust(
                existing_row=existing_row,
                segment=segment,
            )
            audio_state, _, _, audio_duration = classify_audio(Path(audio), min_duration=0.25)
            audio_duration_text = f"{audio_duration:.3f}" if audio_duration is not None else ""
            try:
                preview = safe_asr_preview(preview_func, audio)
            except UnsupportedAsrPreviewError as error:
                preview = f"preview rejected: {error}"
            except Exception as error:
                preview = f"preview failed: {error}"
            writer.writerow(
                {
                    "id": sample_id,
                    "recorded_at": str(segment.get("recorded_at") or "").strip(),
                    "audio": audio,
                    "audio_state": audio_state,
                    "audio_duration_seconds": audio_duration_text,
                    "recording_stop_reason": str(segment.get("recording_stop_reason") or "").strip(),
                    "text_capture_status": str(segment.get("text_capture_status") or "").strip(),
                    "text_capture_reason": str(segment.get("text_capture_reason") or "").strip(),
                    "asr_preview": preview,
                    "reference": reference,
                    "reference_source": reference_source,
                    "reference_trusted": reference_trusted,
                }
            )
            count += 1
    return count


def import_review_tsv(
    review_path: Path,
    manifest_path: Path,
    protected_terms: Sequence[str],
) -> int:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = list(load_existing_manifest(manifest_path).values())
    merged_rows: dict[str, dict[str, object]] = {
        str(row.get("id") or "").strip(): dict(row)
        for row in existing_rows
        if str(row.get("id") or "").strip()
    }
    existing_order = [str(row.get("id") or "").strip() for row in existing_rows if str(row.get("id") or "").strip()]
    imported_order: list[str] = []
    count = 0
    with review_path.open("r", encoding="utf-8", newline="") as input_handle:
        reader = csv.DictReader(input_handle, delimiter="\t")
        required_fields = {"id", "audio", "reference"}
        missing = required_fields.difference(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Review TSV missing required column(s): {', '.join(sorted(missing))}")
        for row in reader:
            sample_id = str(row.get("id") or "").strip()
            audio = str(row.get("audio") or "").strip()
            reference = str(row.get("reference") or "").strip()
            if not sample_id or not audio or not reference:
                continue
            if not review_row_is_trusted(row, reader.fieldnames or []):
                continue
            existing = merged_rows.get(sample_id, {})
            previous_reference = str(existing.get("reference") or "").strip()
            output_row = dict(existing)
            output_row["id"] = sample_id
            output_row["audio"] = audio
            output_row["reference"] = reference
            if previous_reference == reference and "terms" in output_row:
                pass
            else:
                output_row["terms"] = terms_from_reference(reference, protected_terms)
            merged_rows[sample_id] = output_row
            if sample_id not in existing_order and sample_id not in imported_order:
                imported_order.append(sample_id)
            count += 1
    with manifest_path.open("w", encoding="utf-8") as output:
        for sample_id in existing_order + imported_order:
            row = merged_rows.get(sample_id)
            if row:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
    return count


TRUSTED_REVIEW_VALUES = {"1", "true", "yes", "y", "trusted", "approved", "ok", "import", "keep"}
UNTRUSTED_REVIEW_VALUES = {"0", "false", "no", "n", "skip", "reject", "rejected", "untrusted"}


def review_row_is_trusted(row: dict[str, str], fieldnames: Sequence[str]) -> bool:
    trust_fields = [field for field in ("reference_trusted", "trusted", "include") if field in fieldnames]
    for field in trust_fields:
        value = str(row.get(field) or "").strip().lower()
        if not value:
            continue
        if value in UNTRUSTED_REVIEW_VALUES:
            return False
        if value in TRUSTED_REVIEW_VALUES:
            return True

    status = str(row.get("review_status") or "").strip().lower() if "review_status" in fieldnames else ""
    if status in UNTRUSTED_REVIEW_VALUES:
        return False
    if status in TRUSTED_REVIEW_VALUES:
        return True

    return True


def markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pair Doubao shadow-recorded audio segments with pasted Doubao transcripts.")
    parser.add_argument("--segments", default=Path("bench/samples/doubao-shadow/segments.jsonl"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/doubao-shadow/manifest.jsonl"), type=Path)
    parser.add_argument("--pid-file", default=Path("bench/samples/doubao-shadow/shadow.pid"), type=Path)
    parser.add_argument("--hotwords", default=Path("bench/config/hotwords.example.json"), type=Path)
    parser.add_argument("--asr-preview", action="store_true", help="Print a local ASR preview before prompting for unmatched segments.")
    parser.add_argument("--asr-smoke-bin", default=Path("app/SwitchType/.build/debug/SwitchTypeASRSmoke"), type=Path)
    parser.add_argument("--preview-only", action="store_true", help="Write a local ASR preview report and do not prompt for references.")
    parser.add_argument("--preview-output", default=Path("bench/reports/doubao-shadow-asr-preview.md"), type=Path)
    parser.add_argument("--review-output", default=Path("bench/samples/doubao-shadow/review.tsv"), type=Path)
    parser.add_argument("--review-tsv", action="store_true", help="Write an editable TSV with ASR previews and blank reference cells.")
    parser.add_argument("--import-review", default=None, type=Path, help="Import reviewed TSV references into the benchmark manifest.")
    parser.add_argument("--plan", action="store_true", help="Print a non-mutating reconcile plan and do not prompt or write the manifest.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON for --plan.")
    parser.add_argument("--auto-only", action="store_true", help="Write only existing or auto-captured references without prompting.")
    parser.add_argument("--current-only", action="store_true", help="Skip legacy shadow segments that predate recording_stop_reason metadata.")
    parser.add_argument("--latest-preview", action="store_true", help="Print a local ASR preview for only the newest captured clip.")
    parser.add_argument("--wait-next-preview", action="store_true", help="Wait for a new shadow clip, then print its local ASR preview.")
    parser.add_argument("--wait-timeout-seconds", default=30.0, type=float, help="Maximum seconds to wait for --wait-next-preview.")
    parser.add_argument("--wait-poll-seconds", default=0.5, type=float, help="Polling interval for --wait-next-preview.")
    args = parser.parse_args()

    protected_terms = load_protected_terms(args.hotwords)
    if args.import_review is not None:
        count = import_review_tsv(
            review_path=args.import_review,
            manifest_path=args.manifest,
            protected_terms=protected_terms,
        )
        print(f"Imported {count} reviewed sample(s) to {args.manifest}")
        return 0
    if args.plan:
        return print_reconcile_plan(
            segments_path=args.segments,
            manifest_path=args.manifest,
            current_only=args.current_only,
            json_output=args.json,
        )
    preview_func = None
    if args.asr_preview:
        preview_func = lambda audio: transcribe_asr_preview(audio, args.asr_smoke_bin)
    if args.review_tsv:
        if preview_func is None:
            preview_func = lambda audio: transcribe_asr_preview(audio, args.asr_smoke_bin)
        count = write_review_tsv(
            segments_path=args.segments,
            output_path=args.review_output,
            preview_func=preview_func,
            existing_manifest_path=args.manifest,
        )
        print(f"Wrote {count} review row(s) to {args.review_output}")
        return 0
    if args.latest_preview:
        if preview_func is None:
            preview_func = lambda audio: transcribe_asr_preview(audio, args.asr_smoke_bin)
        count = print_latest_asr_preview(
            segments_path=args.segments,
            preview_func=preview_func,
        )
        return 0 if count >= 0 else 1
    if args.wait_next_preview:
        if preview_func is None:
            preview_func = lambda audio: transcribe_asr_preview(audio, args.asr_smoke_bin)
        count = wait_for_next_asr_preview(
            segments_path=args.segments,
            preview_func=preview_func,
            timeout_seconds=args.wait_timeout_seconds,
            poll_interval_seconds=args.wait_poll_seconds,
            recorder_running_func=lambda: shadow_recorder_is_running(args.pid_file),
            status_func=lambda: status_payload(
                pid_file=args.pid_file,
                segments=args.segments,
                manifest=args.manifest,
            ),
        )
        return 0 if count >= 0 else 1
    if args.preview_only:
        if preview_func is None:
            preview_func = lambda audio: transcribe_asr_preview(audio, args.asr_smoke_bin)
        count = write_asr_preview_report(
            segments_path=args.segments,
            output_path=args.preview_output,
            preview_func=preview_func,
        )
        print(f"Wrote {count} ASR preview row(s) to {args.preview_output}")
        return 0
    count = reconcile_segments(
        segments_path=args.segments,
        manifest_path=args.manifest,
        protected_terms=protected_terms,
        preview_func=preview_func,
        prompt_for_missing=not args.auto_only,
        current_only=args.current_only,
    )
    print(f"Wrote {count} reconciled sample(s) to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
