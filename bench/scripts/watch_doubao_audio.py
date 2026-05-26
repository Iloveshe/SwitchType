from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DOUBAO_KEYWORDS = (
    "doubao",
    "bytedance",
    "inputmethod",
    "doubaoime",
    "asr",
    "voice",
    "record",
    "speech",
)
DOUBAO_SETTINGS_PATH_TERMS = (
    "config",
    "setting",
    "settings",
    "pftconfig",
    "preference",
    "shortcut",
    "hotkey",
    "keycode",
    "voice",
    "speech",
    "asr",
)
DOUBAO_SETTINGS_TEXT_TERMS = (
    "hotkey",
    "shortcut",
    "keycode",
    "key_code",
    "modifier",
    "option",
    "shift",
    "command",
    "control",
    "voice",
    "speech",
    "asr",
    "microphone",
    "快捷",
    "快捷键",
    "语音",
    "麦克风",
)
DOUBAO_SHORTCUT_SETTING_KEYS = (
    "asrShortcutKeyCode",
    "asrShortcutModifierFlags",
    "asrShortcutKeyDisplay",
    "isStartASRShortcutEnable",
    "isGloableASRShortcutEnable",
    "isGlobalASRShortcutEnable",
)
DOUBAO_SHORTCUT_DISPLAY_VALUES = (
    "Option",
    "Shift",
    "Control",
    "Command",
    "Fn",
)
SHORTCUT_DISPLAY_MODIFIERS = {
    "option": "option",
    "shift": "shift",
    "control": "control",
    "command": "command",
}
SHORTCUT_MODIFIER_FLAGS = (
    ("control", 1 << 18),
    ("option", 1 << 19),
    ("shift", 1 << 17),
    ("command", 1 << 20),
)


@dataclass(frozen=True)
class CapturedAudio:
    path: Path
    source_path: Path
    audio_format: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    byte_count: int
    modified_ns: int


@dataclass(frozen=True)
class FileChange:
    status: str
    path: Path
    before: FileSnapshot | None
    after: FileSnapshot


def audio_format_from_header(header: bytes) -> str | None:
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        major_brand = header[8:12].lower()
        if major_brand in {b"m4a ", b"mp42", b"mp41", b"isom", b"qt  "}:
            return "m4a"
    if header.startswith(b"caff"):
        return "caf"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF6) == 0xF0:
        return "aac"
    if header.startswith(b"#!AMR"):
        return "amr"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    return None


def is_candidate_path(path: Path) -> bool:
    normalized = str(path).casefold()
    return any(keyword in normalized for keyword in DOUBAO_KEYWORDS)


def default_watch_roots(
    home: Path | None = None,
    tmp: Path | None = None,
) -> list[Path]:
    home = Path.home() if home is None else home
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) if tmp is None else tmp
    return [
        home / "Library/Application Support/DoubaoIme",
        home / "Library/Caches/com.bytedance.inputmethod.doubaoime",
        tmp,
    ]


def default_probe_roots(
    home: Path | None = None,
    tmp: Path | None = None,
) -> list[Path]:
    home = Path.home() if home is None else home
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) if tmp is None else tmp
    return [
        home / "Library/Application Support/DoubaoIme",
        home / "Library/Caches/com.bytedance.inputmethod.doubaoime",
        home / "Library/Caches/com.bytedance.inputmethod.doubaoime.settings",
        home / "Library/HTTPStorages/com.bytedance.inputmethod.doubaoime",
        home / "Library/HTTPStorages/com.bytedance.inputmethod.doubaoime.settings",
        tmp,
    ]


def default_settings_roots(home: Path | None = None) -> list[Path]:
    home = Path.home() if home is None else home
    return [
        home / "Library/Application Support/DoubaoIme",
        home / "Library/Caches/com.bytedance.inputmethod.doubaoime.settings",
        home / "Library/HTTPStorages/com.bytedance.inputmethod.doubaoime.settings",
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_header(path: Path, byte_count: int = 64) -> bytes:
    with path.open("rb") as handle:
        return handle.read(byte_count)


def printable_preview(data: bytes, limit: int = 96) -> str:
    preview = data[:limit]
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in preview)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.casefold()
    return [term for term in terms if term.casefold() in lowered]


def unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def snippets_for_terms(text: str, terms: tuple[str, ...], radius: int = 48, limit: int = 8) -> list[str]:
    compact = compact_text(text)
    lowered = compact.casefold()
    snippets: list[str] = []
    for term in terms:
        index = lowered.find(term.casefold())
        if index < 0:
            continue
        start = max(index - radius, 0)
        end = min(index + len(term) + radius, len(compact))
        snippet = compact[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return snippets


def shortcut_display_values(text: str) -> list[str]:
    compact = compact_text(text)
    lowered = compact.casefold()
    values: list[str] = []
    if matched_terms(text, DOUBAO_SHORTCUT_SETTING_KEYS):
        for value in DOUBAO_SHORTCUT_DISPLAY_VALUES:
            if f"V{value}".casefold() in lowered:
                values.append(value)
    for anchor in ("asrShortcutKeyDisplay", "voiceShortcut"):
        index = lowered.find(anchor.casefold())
        if index < 0:
            continue
        window = compact[index : index + 160]
        values.extend(matched_terms(window, DOUBAO_SHORTCUT_DISPLAY_VALUES))
    return unique_ordered(values)


def parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def embedded_bplist_payloads(data: bytes) -> list[object]:
    starts = unique_ordered([str(index) for index in (0, data.find(b"bplist00")) if index >= 0])
    non_zero_end = len(data.rstrip(b"\x00")) or len(data)
    end_candidates = [len(data), non_zero_end]
    if len(data) >= 4:
        declared_length = int.from_bytes(data[:4], "little", signed=False)
        end_candidates.extend([declared_length, 4 + declared_length])
        bplist_start = data.find(b"bplist00")
        if bplist_start >= 0:
            end_candidates.append(bplist_start + declared_length)
    payloads: list[object] = []
    seen_slices: set[tuple[int, int]] = set()
    for raw_start in starts:
        start = int(raw_start)
        for end in end_candidates:
            if end <= start or end > len(data) or (start, end) in seen_slices:
                continue
            seen_slices.add((start, end))
            try:
                payloads.append(plistlib.loads(data[start:end]))
            except (plistlib.InvalidFileException, ValueError, TypeError, EOFError):
                continue
    return payloads


def resolve_nskeyed_value(value: object, objects: list[object]) -> object:
    if isinstance(value, plistlib.UID):
        try:
            return objects[value.data]
        except (IndexError, TypeError):
            return None
    return value


def nskeyed_archive_root_dictionary(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    objects = payload.get("$objects")
    top = payload.get("$top")
    if not isinstance(objects, list) or not isinstance(top, dict):
        return {}
    root = resolve_nskeyed_value(top.get("root"), objects)
    if not isinstance(root, dict):
        return {}
    keys = root.get("NS.keys")
    values = root.get("NS.objects")
    if not isinstance(keys, list) or not isinstance(values, list):
        return {}
    decoded: dict[str, object] = {}
    for key_ref, value_ref in zip(keys, values):
        key = resolve_nskeyed_value(key_ref, objects)
        if not isinstance(key, str):
            continue
        value = resolve_nskeyed_value(value_ref, objects)
        if isinstance(value, (str, int, bool)):
            decoded[key] = value
    return decoded


def shortcut_setting_values_from_text(text: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for key in DOUBAO_SHORTCUT_SETTING_KEYS:
        if key == "asrShortcutKeyDisplay":
            match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"', text)
            if match:
                values[key] = match.group(1)
            continue
        match = re.search(rf'"{re.escape(key)}"\s*:\s*(-?\d+|true|false)', text, flags=re.IGNORECASE)
        if not match:
            continue
        raw_value = match.group(1)
        if raw_value.casefold() in {"true", "false"}:
            values[key] = raw_value.casefold() == "true"
        else:
            values[key] = int(raw_value)
    return values


def shortcut_setting_values_from_data(data: bytes, text: str) -> dict[str, object]:
    values = shortcut_setting_values_from_text(text)
    for payload in embedded_bplist_payloads(data):
        decoded = nskeyed_archive_root_dictionary(payload)
        for key in DOUBAO_SHORTCUT_SETTING_KEYS:
            if key in decoded:
                values[key] = decoded[key]
    return values


def shortcut_display_values_from_settings(values: dict[str, object]) -> list[str]:
    display = values.get("asrShortcutKeyDisplay")
    return [display] if isinstance(display, str) and display.strip() else []


def modifier_names_from_flags(flags: int) -> list[str]:
    return [name for name, mask in SHORTCUT_MODIFIER_FLAGS if flags & mask]


def suggested_modifiers_from_shortcut_settings(
    values: dict[str, object],
    display_values: list[str],
) -> str | None:
    flags = parse_int(values.get("asrShortcutModifierFlags"))
    if flags is not None:
        names = modifier_names_from_flags(flags)
        if names:
            return ",".join(names)
    display_modifiers: list[str] = []
    for value in display_values:
        modifier = SHORTCUT_DISPLAY_MODIFIERS.get(value.casefold())
        if modifier and modifier not in display_modifiers:
            display_modifiers.append(modifier)
    return ",".join(display_modifiers) if display_modifiers else None


def settings_probe_row(
    path: Path,
    max_file_bytes: int = 2_000_000,
    read_bytes: int = 262_144,
) -> dict[str, object] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    path_text = str(path)
    path_terms = matched_terms(path_text, DOUBAO_SETTINGS_PATH_TERMS)
    if stat.st_size > max_file_bytes and not path_terms:
        return None
    try:
        with path.open("rb") as handle:
            data = handle.read(min(read_bytes, max_file_bytes))
    except OSError:
        data = b""
    text = data.decode("utf-8", errors="ignore")
    text_terms = matched_terms(text, DOUBAO_SETTINGS_TEXT_TERMS)
    if not path_terms and not text_terms:
        return None
    snippets = snippets_for_terms(text, DOUBAO_SETTINGS_TEXT_TERMS)
    visible_shortcut_setting_keys = matched_terms(text, DOUBAO_SHORTCUT_SETTING_KEYS)
    shortcut_setting_values = shortcut_setting_values_from_data(data, text)
    display_values = unique_ordered(
        shortcut_display_values(text) + shortcut_display_values_from_settings(shortcut_setting_values)
    )
    score = len(path_terms) * 4 + len(text_terms) * 15 + len(snippets) * 6
    score += len(visible_shortcut_setting_keys) * 20 + len(display_values) * 10
    score += len(shortcut_setting_values) * 10
    if stat.st_size <= max_file_bytes:
        score += 2
    return {
        "path": path_text,
        "bytes": stat.st_size,
        "read_bytes": min(len(data), max_file_bytes),
        "path_terms": path_terms,
        "matched_terms": sorted(set(path_terms + text_terms), key=str.casefold),
        "snippets": snippets,
        "visible_shortcut_setting_keys": visible_shortcut_setting_keys,
        "shortcut_display_values": display_values,
        "shortcut_setting_values": shortcut_setting_values,
        "settings_score": score,
        "skipped_full_read": stat.st_size > max_file_bytes,
    }


def shortcut_hints_from_settings_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    visible_setting_keys: list[str] = []
    display_values: list[str] = []
    key_codes: list[str] = []
    modifier_flags: list[str] = []
    suggested_key_code: str | None = None
    suggested_modifiers: str | None = None
    candidate_files: list[str] = []
    for row in rows:
        row_keys = row.get("visible_shortcut_setting_keys", [])
        row_values = row.get("shortcut_display_values", [])
        row_setting_values = row.get("shortcut_setting_values", {})
        if not isinstance(row_keys, list):
            row_keys = []
        if not isinstance(row_values, list):
            row_values = []
        if not isinstance(row_setting_values, dict):
            row_setting_values = {}
        visible_setting_keys.extend(str(value) for value in row_keys)
        display_values.extend(str(value) for value in row_values)
        key_code = parse_int(row_setting_values.get("asrShortcutKeyCode"))
        modifier_flag = parse_int(row_setting_values.get("asrShortcutModifierFlags"))
        if key_code is not None:
            key_codes.append(str(key_code))
            if suggested_key_code is None:
                suggested_key_code = str(key_code)
        if modifier_flag is not None:
            modifier_flags.append(str(modifier_flag))
        row_suggested_modifiers = suggested_modifiers_from_shortcut_settings(row_setting_values, [str(value) for value in row_values])
        if row_suggested_modifiers and suggested_modifiers is None:
            suggested_modifiers = row_suggested_modifiers
        if row_keys or row_values or row_setting_values:
            path = str(row.get("path", ""))
            if path:
                candidate_files.append(path)
    return {
        "visible_setting_keys": unique_ordered(visible_setting_keys),
        "display_values": unique_ordered(display_values),
        "key_codes": [int(value) for value in unique_ordered(key_codes)],
        "modifier_flags": [int(value) for value in unique_ordered(modifier_flags)],
        "suggested_hotkey_key_code": suggested_key_code,
        "suggested_hotkey_modifiers": suggested_modifiers,
        "candidate_files": unique_ordered(candidate_files)[:20],
    }


def build_settings_probe_report(
    roots: list[Path],
    max_file_bytes: int = 2_000_000,
    read_bytes: int = 262_144,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for root in roots:
        for path in iter_files(root):
            row = settings_probe_row(path, max_file_bytes=max_file_bytes, read_bytes=read_bytes)
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda row: (-int(row.get("settings_score", 0)), str(row.get("path", ""))))
    return {
        "roots": [str(root) for root in roots],
        "candidate_file_count": len(rows),
        "candidate_files": rows,
        "shortcut_hints": shortcut_hints_from_settings_rows(rows),
    }


def build_settings_probe_markdown(report: dict[str, object]) -> str:
    rows = list(report.get("candidate_files", []))
    shortcut_hints = report.get("shortcut_hints")
    if not isinstance(shortcut_hints, dict):
        shortcut_hints = {"visible_setting_keys": [], "display_values": [], "candidate_files": []}
    visible_keys = list(shortcut_hints.get("visible_setting_keys", []))
    display_values = list(shortcut_hints.get("display_values", []))
    key_codes = list(shortcut_hints.get("key_codes", []))
    modifier_flags = list(shortcut_hints.get("modifier_flags", []))
    suggested_key_code = str(shortcut_hints.get("suggested_hotkey_key_code") or "").strip()
    suggested_modifiers = str(shortcut_hints.get("suggested_hotkey_modifiers") or "").strip()
    candidate_files = list(shortcut_hints.get("candidate_files", []))
    lines = [
        "# Doubao Settings Probe",
        "",
        f"- Candidate files: {report.get('candidate_file_count', 0)}",
        "",
        "## Shortcut hints",
        "",
    ]
    if visible_keys or display_values:
        lines.append(f"- Visible setting keys: {', '.join(str(value) for value in visible_keys) or 'none'}")
        lines.append(f"- Display values near shortcut settings: {', '.join(str(value) for value in display_values) or 'none'}")
        if suggested_key_code or suggested_modifiers:
            lines.append(
                "- Suggested hotkey: "
                f"keyCode={suggested_key_code or 'unknown'}, modifiers={suggested_modifiers or 'unknown'}"
            )
        if key_codes:
            lines.append(f"- Parsed key codes: {', '.join(str(value) for value in key_codes)}")
        if modifier_flags:
            lines.append(f"- Parsed modifier flags: {', '.join(str(value) for value in modifier_flags)}")
        lines.append(f"- Candidate files with shortcut hints: {len(candidate_files)}")
    else:
        lines.append("No explicit ASR shortcut setting keys were readable.")
    lines.append("")
    if not rows:
        lines.extend(
            [
                "No readable hotkey or voice setting candidates were found.",
                "",
                "## Next actions",
                "",
                "- Use `TIMEOUT=30 make hotkey-probe-packaged` when you are ready to explicitly approve hotkey listening.",
                "- Keep using the shadow recorder status commands to avoid mistaking stale clips for current capture evidence.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["## Top candidates", ""])
    for row in rows[:20]:
        terms = ", ".join(row.get("matched_terms", [])) or "path-only"
        lines.extend(
            [
                f"### {row.get('path', '')}",
                "",
                f"- Score: {row.get('settings_score', 0)}",
                f"- Bytes: {row.get('bytes', 0)}",
                f"- Matched terms: {terms}",
                "",
            ]
        )
        snippets = row.get("snippets")
        if isinstance(snippets, list) and snippets:
            lines.append("Snippets:")
            for snippet in snippets[:5]:
                lines.append(f"- `{snippet}`")
            lines.append("")

    lines.extend(
        [
            "## Next actions",
            "",
            "- Treat this as a static hint only. It does not prove the active Doubao voice shortcut unless the setting is readable and clearly named.",
            "- If no clear shortcut is visible, use `TIMEOUT=30 make hotkey-probe-packaged` for the explicit hotkey-listening diagnostic.",
            "",
        ]
    )
    return "\n".join(lines)


def write_settings_probe_report(
    output_path: Path,
    summary_path: Path | None,
    roots: list[Path],
    max_file_bytes: int = 2_000_000,
    read_bytes: int = 262_144,
) -> dict[str, object]:
    report = build_settings_probe_report(
        roots=roots,
        max_file_bytes=max_file_bytes,
        read_bytes=read_bytes,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(build_settings_probe_markdown(report), encoding="utf-8")
    return report


def capture_audio_file(
    source: Path,
    output_dir: Path,
    manifest: Path,
    captured_at: str | None = None,
) -> CapturedAudio:
    header = read_header(source)
    audio_format = audio_format_from_header(header)
    if audio_format is None:
        raise ValueError(f"Not a recognized audio file: {source}")

    captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    byte_count = source.stat().st_size
    digest = sha256_file(source)
    safe_time = captured_at.replace(":", "").replace("+", "Z")
    target = output_dir / f"doubao-{safe_time}-{digest[:12]}.{audio_format}"
    shutil.copy2(source, target)

    row = {
        "captured_at": captured_at,
        "source_path": str(source),
        "captured_path": str(target),
        "format": audio_format,
        "bytes": byte_count,
        "sha256": digest,
    }
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    return CapturedAudio(
        path=target,
        source_path=source,
        audio_format=audio_format,
        byte_count=byte_count,
        sha256=digest,
    )


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in {"__pycache__", ".git"}]
        for filename in filenames:
            files.append(Path(current_root) / filename)
    return files


def collect_existing(roots: list[Path]) -> set[Path]:
    existing: set[Path] = set()
    for root in roots:
        existing.update(iter_files(root))
    return existing


def snapshot_files(roots: list[Path]) -> dict[Path, FileSnapshot]:
    snapshot: dict[Path, FileSnapshot] = {}
    for root in roots:
        for path in iter_files(root):
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[path] = FileSnapshot(
                path=path,
                byte_count=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
    return snapshot


def diff_snapshots(
    before: dict[Path, FileSnapshot],
    after: dict[Path, FileSnapshot],
) -> list[FileChange]:
    changes: list[FileChange] = []
    for path, after_snapshot in after.items():
        before_snapshot = before.get(path)
        if before_snapshot is None:
            changes.append(FileChange(status="created", path=path, before=None, after=after_snapshot))
        elif (
            before_snapshot.byte_count != after_snapshot.byte_count
            or before_snapshot.modified_ns != after_snapshot.modified_ns
        ):
            changes.append(FileChange(status="modified", path=path, before=before_snapshot, after=after_snapshot))
    return sorted(changes, key=lambda change: str(change.path))


def build_file_change_rows(changes: list[FileChange]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for change in changes:
        try:
            header = read_header(change.path, byte_count=128)
        except OSError:
            header = b""
        rows.append(
            {
                "status": change.status,
                "path": str(change.path),
                "bytes": change.after.byte_count,
                "before_bytes": change.before.byte_count if change.before else None,
                "modified_ns": change.after.modified_ns,
                "before_modified_ns": change.before.modified_ns if change.before else None,
                "candidate_path": is_candidate_path(change.path),
                "audio_format": audio_format_from_header(header),
                "header_hex": header[:32].hex(),
                "printable_preview": printable_preview(header),
            }
        )
    return rows


def rank_probe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for row in rows:
        scored = dict(row)
        path = str(row.get("path", ""))
        normalized = path.casefold()
        preview = str(row.get("printable_preview", "")).casefold()
        status = str(row.get("status", ""))
        reasons: list[str] = []
        score = 0

        if row.get("audio_format"):
            score += 100
            reasons.append("recognized audio")
        if row.get("candidate_path"):
            score += 10
            reasons.append("Doubao-like path")
        if status == "created":
            score += 15
            reasons.append("created during probe")
        elif status == "modified":
            score += 5
            reasons.append("modified during probe")
        if row.get("before_bytes") is not None and row.get("bytes") != row.get("before_bytes"):
            score += 10
            reasons.append("byte count changed")
        if any(keyword in normalized for keyword in ("asr", "voice", "record", "speech", "audio", "stt")):
            score += 25
            reasons.append("ASR or voice name")
        if "/log/alog/" in normalized:
            score += 15
            reasons.append("Doubao runtime log")
        if "cache.db-wal" in normalized or "httpstorages" in normalized:
            score += 12
            reasons.append("network cache changed")
        if "pftconfig" in normalized or preview.startswith("pftconfig"):
            score += 4
            reasons.append("Parfait settings changed")

        scored["probe_score"] = score
        scored["probe_reasons"] = reasons
        ranked.append(scored)
    return sorted(ranked, key=lambda item: (-int(item["probe_score"]), str(item.get("path", ""))))


def build_probe_markdown(report: dict[str, object]) -> str:
    rows = rank_probe_rows(list(report.get("changed_files", [])))
    lines = [
        "# Doubao Probe Summary",
        "",
        f"- Started: {report.get('started_at', '')}",
        f"- Ended: {report.get('ended_at', '')}",
        f"- Changed files: {report.get('changed_file_count', 0)}",
        "",
    ]
    if not rows:
        lines.extend(
            [
                "No file changes were observed during the probe window.",
                "",
                "## Next actions",
                "",
                "- Re-run the probe while actively using Doubao voice input.",
                "- If this remains empty, Doubao may keep audio in memory or outside the watched roots.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["## Top candidates", ""])
    for row in rows[:20]:
        reasons = ", ".join(row.get("probe_reasons", [])) or "no specific signal"
        audio = row.get("audio_format") or "non-audio"
        lines.extend(
            [
                f"### {row.get('path', '')}",
                "",
                f"- Score: {row.get('probe_score', 0)}",
                f"- Status: {row.get('status', '')}",
                f"- Type: {audio}",
                f"- Bytes: {row.get('before_bytes')} -> {row.get('bytes')}",
                f"- Reasons: {reasons}",
                "",
            ]
        )

    has_audio = any(row.get("audio_format") for row in rows)
    has_log_or_cache = any(
        "Doubao runtime log" in row.get("probe_reasons", [])
        or "network cache changed" in row.get("probe_reasons", [])
        for row in rows
    )
    lines.extend(["## Next actions", ""])
    if has_audio:
        lines.append("- Inspect the recognized audio candidate, convert it to 16 kHz mono WAV, and match it to the spoken reference.")
    if has_log_or_cache:
        lines.append("- Inspect the top log/cache candidates around the probe time for transcript or request metadata; do not treat them as release evidence until matched to a reference.")
    if not has_audio:
        lines.append("- No standard audio container was detected. Keep the conservative watcher running, and consider collecting local mic audio paired with Doubao's pasted transcript.")
    lines.append("")
    return "\n".join(lines)


def parse_doubao_process_rows(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    marker = "/library/input methods/doubaoime.app/"
    for line in output.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        command = parts[2]
        if marker not in command.casefold():
            continue
        rows.append({"pid": parts[0], "ppid": parts[1], "command": command})
    return rows


def find_doubao_process_rows() -> list[dict[str, str]]:
    try:
        completed = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    return parse_doubao_process_rows(completed.stdout)


def write_probe_report(
    output_path: Path,
    summary_path: Path | None,
    roots: list[Path],
    before: dict[Path, FileSnapshot],
    after: dict[Path, FileSnapshot],
    started_at: str,
    ended_at: str,
    process_rows: list[dict[str, str]],
) -> dict[str, object]:
    changes = diff_snapshots(before, after)
    report = {
        "started_at": started_at,
        "ended_at": ended_at,
        "roots": [str(root) for root in roots],
        "processes": process_rows,
        "before_file_count": len(before),
        "after_file_count": len(after),
        "changed_file_count": len(changes),
        "changed_files": build_file_change_rows(changes),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(build_probe_markdown(report), encoding="utf-8")
    return report


def should_inspect(path: Path, tmp_root: Path, include_tmp_all_audio: bool) -> bool:
    try:
        path.relative_to(tmp_root)
        in_tmp = True
    except ValueError:
        in_tmp = False
    if in_tmp and not include_tmp_all_audio:
        return is_candidate_path(path)
    return True


def scan_once(
    roots: list[Path],
    output_dir: Path,
    manifest: Path,
    seen: set[Path],
    tmp_root: Path,
    include_tmp_all_audio: bool = False,
    min_bytes: int = 512,
    min_age_seconds: float = 0.25,
) -> list[CapturedAudio]:
    captured: list[CapturedAudio] = []
    now = time.time()
    for root in roots:
        for path in iter_files(root):
            if path in seen:
                continue
            seen.add(path)
            if not should_inspect(path, tmp_root=tmp_root, include_tmp_all_audio=include_tmp_all_audio):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size < min_bytes or now - stat.st_mtime < min_age_seconds:
                continue
            try:
                header = read_header(path)
            except OSError:
                continue
            if audio_format_from_header(header) is None:
                continue
            try:
                captured.append(capture_audio_file(path, output_dir, manifest))
            except OSError:
                continue
    return captured


def run_watcher(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else default_watch_roots()
    tmp_root = Path(os.environ.get("TMPDIR", "/tmp"))
    seen: set[Path] = set() if args.capture_existing else collect_existing(roots)
    started_at = time.time()
    print("Watching for new Doubao audio candidates:")
    for root in roots:
        print(f"- {root}")
    print(f"Output: {args.output_dir}")
    print(f"Manifest: {args.manifest}")
    sys.stdout.flush()

    while True:
        captured = scan_once(
            roots=roots,
            output_dir=args.output_dir,
            manifest=args.manifest,
            seen=seen,
            tmp_root=tmp_root,
            include_tmp_all_audio=args.include_tmp_all_audio,
            min_bytes=args.min_bytes,
            min_age_seconds=args.min_age_seconds,
        )
        for item in captured:
            print(f"Captured {item.audio_format}: {item.path} ({item.byte_count} bytes)")
        if captured:
            sys.stdout.flush()
        if args.once:
            return 0
        if args.duration_seconds and time.time() - started_at >= args.duration_seconds:
            return 0
        time.sleep(args.poll_seconds)


def run_probe(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else default_probe_roots()
    duration = args.duration_seconds or 20.0
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    before = snapshot_files(roots)
    start_processes = [
        {"pid": row["pid"], "ppid": row["ppid"], "command": row["command"], "phase": "start"}
        for row in find_doubao_process_rows()
    ]

    print("Probing Doubao file changes. Use Doubao voice input now.")
    print(f"Duration: {duration:.1f}s")
    for root in roots:
        print(f"- {root}")
    sys.stdout.flush()

    deadline = time.time() + duration
    while time.time() < deadline:
        time.sleep(min(args.poll_seconds, max(deadline - time.time(), 0.0)))

    after = snapshot_files(roots)
    ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    process_rows = start_processes + [
        {"pid": row["pid"], "ppid": row["ppid"], "command": row["command"], "phase": "end"}
        for row in find_doubao_process_rows()
    ]
    report = write_probe_report(
        output_path=args.probe_output,
        summary_path=args.probe_summary,
        roots=roots,
        before=before,
        after=after,
        started_at=started_at,
        ended_at=ended_at,
        process_rows=process_rows,
    )
    print(f"Wrote probe report: {args.probe_output}")
    if args.probe_summary:
        print(f"Wrote probe summary: {args.probe_summary}")
    print(f"Changed files: {report['changed_file_count']}")
    for row in report["changed_files"][:20]:
        audio = row["audio_format"] or "non-audio"
        print(f"- {row['status']} {audio} {row['path']}")
    if report["changed_file_count"] > 20:
        print(f"... {report['changed_file_count'] - 20} more change(s) in report")
    return 0


def run_settings_probe(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else default_settings_roots()
    report = write_settings_probe_report(
        output_path=args.settings_output,
        summary_path=args.settings_summary,
        roots=roots,
        max_file_bytes=args.settings_max_file_bytes,
        read_bytes=args.settings_read_bytes,
    )
    print("Probed Doubao settings without listening or recording.")
    for root in roots:
        print(f"- {root}")
    print(f"Wrote settings probe report: {args.settings_output}")
    if args.settings_summary:
        print(f"Wrote settings probe summary: {args.settings_summary}")
    print(f"Candidate settings files: {report['candidate_file_count']}")
    for row in report["candidate_files"][:10]:
        terms = ", ".join(row.get("matched_terms", [])) or "path-only"
        print(f"- score={row['settings_score']} terms={terms} {row['path']}")
    if report["candidate_file_count"] > 10:
        print(f"... {report['candidate_file_count'] - 10} more candidate(s) in report")
    return 0


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


def start_daemon(args: argparse.Namespace) -> int:
    pid = read_pid(args.pid_file)
    if pid and process_is_running(pid):
        print(f"Doubao watcher already running: pid {pid}")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--output-dir",
        str(args.output_dir),
        "--manifest",
        str(args.manifest),
        "--pid-file",
        str(args.pid_file),
        "--log-file",
        str(args.log_file),
        "--poll-seconds",
        str(args.poll_seconds),
        "--min-bytes",
        str(args.min_bytes),
        "--min-age-seconds",
        str(args.min_age_seconds),
    ]
    for root in args.root or []:
        command.extend(["--root", root])
    if args.include_tmp_all_audio:
        command.append("--include-tmp-all-audio")
    if args.capture_existing:
        command.append("--capture-existing")

    with args.log_file.open("ab") as log, open(os.devnull, "rb") as stdin:
        process = subprocess.Popen(
            command,
            stdin=stdin,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    args.pid_file.write_text(str(process.pid), encoding="utf-8")
    print(f"Started Doubao watcher: pid {process.pid}")
    print(f"Log: {args.log_file}")
    print(f"Manifest: {args.manifest}")
    return 0


def stop_daemon(pid_file: Path) -> int:
    pid = read_pid(pid_file)
    if not pid:
        print("Doubao watcher is not running.")
        return 0
    if process_is_running(pid):
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Doubao watcher: pid {pid}")
    else:
        print(f"Doubao watcher pid file was stale: pid {pid}")
    pid_file.unlink(missing_ok=True)
    return 0


def print_status(pid_file: Path, manifest: Path) -> int:
    pid = read_pid(pid_file)
    if pid and process_is_running(pid):
        print(f"Doubao watcher running: pid {pid}")
    else:
        print("Doubao watcher not running.")
    if manifest.exists():
        count = sum(1 for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip())
        print(f"Captured audio files: {count}")
    else:
        print("Captured audio files: 0")
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch Doubao input-method cache directories for newly created local audio files."
    )
    parser.add_argument("--root", action="append", default=[], help="Directory to watch. Defaults to Doubao app data and TMPDIR.")
    parser.add_argument("--output-dir", default=Path("bench/samples/doubao-capture/audio"), type=Path)
    parser.add_argument("--manifest", default=Path("bench/samples/doubao-capture/manifest.jsonl"), type=Path)
    parser.add_argument("--probe-output", default=Path("bench/samples/doubao-capture/probe.json"), type=Path)
    parser.add_argument("--probe-summary", default=Path("bench/samples/doubao-capture/probe.md"), type=Path)
    parser.add_argument("--settings-output", default=Path("bench/samples/doubao-capture/settings-probe.json"), type=Path)
    parser.add_argument("--settings-summary", default=Path("bench/samples/doubao-capture/settings-probe.md"), type=Path)
    parser.add_argument("--settings-max-file-bytes", default=2_000_000, type=int)
    parser.add_argument("--settings-read-bytes", default=262_144, type=int)
    parser.add_argument("--pid-file", default=Path("bench/samples/doubao-capture/watcher.pid"), type=Path)
    parser.add_argument("--log-file", default=Path("bench/samples/doubao-capture/watcher.log"), type=Path)
    parser.add_argument("--poll-seconds", default=1.0, type=float)
    parser.add_argument("--min-bytes", default=512, type=int)
    parser.add_argument("--min-age-seconds", default=0.25, type=float)
    parser.add_argument("--duration-seconds", default=0.0, type=float)
    parser.add_argument("--include-tmp-all-audio", action="store_true", help="Inspect all TMPDIR files with audio magic, not just Doubao-like paths.")
    parser.add_argument("--capture-existing", action="store_true", help="Capture matching files that already exist at startup.")
    parser.add_argument("--once", action="store_true", help="Scan once and exit.")
    parser.add_argument("--probe", action="store_true", help="Record a before/after metadata report while using Doubao voice input.")
    parser.add_argument("--settings-probe", action="store_true", help="Scan Doubao settings files for visible hotkey or voice-input strings.")
    parser.add_argument("--daemon", action="store_true", help="Start the watcher in the background.")
    parser.add_argument("--stop", action="store_true", help="Stop the background watcher.")
    parser.add_argument("--status", action="store_true", help="Print background watcher status.")
    return parser


def main() -> int:
    args = parser().parse_args()
    if args.stop:
        return stop_daemon(args.pid_file)
    if args.status:
        return print_status(args.pid_file, args.manifest)
    if args.daemon:
        return start_daemon(args)
    if args.settings_probe:
        return run_settings_probe(args)
    if args.probe:
        return run_probe(args)
    return run_watcher(args)


if __name__ == "__main__":
    raise SystemExit(main())
