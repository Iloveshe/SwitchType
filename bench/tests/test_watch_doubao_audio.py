import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from plistlib import UID
from unittest.mock import patch

from bench.scripts.watch_doubao_audio import (
    audio_format_from_header,
    build_probe_markdown,
    build_settings_probe_markdown,
    build_settings_probe_report,
    build_file_change_rows,
    capture_audio_file,
    default_settings_roots,
    default_watch_roots,
    diff_snapshots,
    is_candidate_path,
    parse_doubao_process_rows,
    rank_probe_rows,
    process_is_running,
    snapshot_files,
    write_probe_report,
)


class WatchDoubaoAudioTests(unittest.TestCase):
    def test_audio_format_from_header_detects_common_formats(self):
        examples = {
            "wav": b"RIFF\x24\x00\x00\x00WAVEfmt ",
            "m4a": b"\x00\x00\x00\x18ftypM4A ",
            "caf": b"caff\x00\x01\x00\x00",
            "ogg": b"OggS\x00\x02",
            "flac": b"fLaC\x00\x00",
            "mp3": b"ID3\x04\x00",
            "aac": b"\xff\xf1\x50\x80",
            "amr": b"#!AMR\n",
            "webm": b"\x1a\x45\xdf\xa3\x9fB\x86\x81",
        }

        for expected, header in examples.items():
            with self.subTest(expected=expected):
                self.assertEqual(audio_format_from_header(header), expected)

    def test_audio_format_from_header_rejects_plain_data(self):
        self.assertIsNone(audio_format_from_header(b"not an audio file"))

    def test_candidate_path_filters_tmp_noise_by_name(self):
        self.assertTrue(is_candidate_path(Path("/tmp/DoubaoIme/voice-cache-1")))
        self.assertTrue(is_candidate_path(Path("/tmp/bytedance-asr-recording")))
        self.assertFalse(is_candidate_path(Path("/tmp/com.apple.TelephonyUtilities/concatenated_audio.m4a")))

    def test_default_roots_include_doubao_and_tmp_candidates(self):
        roots = default_watch_roots(home=Path("/Users/example"), tmp=Path("/tmp/example"))

        self.assertIn(Path("/Users/example/Library/Application Support/DoubaoIme"), roots)
        self.assertIn(Path("/Users/example/Library/Caches/com.bytedance.inputmethod.doubaoime"), roots)
        self.assertIn(Path("/tmp/example"), roots)

    def test_default_settings_roots_include_doubao_settings_locations(self):
        roots = default_settings_roots(home=Path("/Users/example"))

        self.assertIn(Path("/Users/example/Library/Application Support/DoubaoIme"), roots)
        self.assertIn(Path("/Users/example/Library/Caches/com.bytedance.inputmethod.doubaoime.settings"), roots)
        self.assertIn(Path("/Users/example/Library/HTTPStorages/com.bytedance.inputmethod.doubaoime.settings"), roots)

    def test_settings_probe_ranks_visible_voice_hotkey_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / "DoubaoIme" / "Parfait" / "settings" / "voice-shortcut.pftconfig"
            settings.parent.mkdir(parents=True)
            settings.write_text(
                (
                    '{"voiceShortcut":"Option","hotkey_key_code":58,'
                    '"asrShortcutKeyCode":58,"asrShortcutModifierFlags":524288,'
                    '"asrShortcutKeyDisplay":"Option","快捷键":"Option"}'
                ),
                encoding="utf-8",
            )
            opaque = root / "DoubaoIme" / "Parfait" / "settings" / "opaque.pftconfig"
            opaque.write_bytes(b"\x00\x01\x02not much")

            report = build_settings_probe_report([root])
            rows = report["candidate_files"]

            self.assertEqual(report["candidate_file_count"], 2)
            self.assertEqual(rows[0]["path"], str(settings))
            self.assertIn("voice", rows[0]["matched_terms"])
            self.assertIn("hotkey", rows[0]["matched_terms"])
            self.assertIn("快捷", rows[0]["matched_terms"])
            self.assertTrue(any("voiceShortcut" in snippet for snippet in rows[0]["snippets"]))
            self.assertGreater(rows[0]["settings_score"], rows[1]["settings_score"])
            self.assertEqual(rows[0]["visible_shortcut_setting_keys"], ["asrShortcutKeyCode", "asrShortcutModifierFlags", "asrShortcutKeyDisplay"])
            self.assertEqual(rows[0]["shortcut_display_values"], ["Option"])
            self.assertEqual(report["shortcut_hints"]["display_values"], ["Option"])
            self.assertEqual(report["shortcut_hints"]["key_codes"], [58])
            self.assertEqual(report["shortcut_hints"]["modifier_flags"], [524288])
            self.assertEqual(report["shortcut_hints"]["suggested_hotkey_key_code"], "58")
            self.assertEqual(report["shortcut_hints"]["suggested_hotkey_modifiers"], "option")
            self.assertIn("asrShortcutKeyCode", report["shortcut_hints"]["visible_setting_keys"])
            self.assertIn(str(settings), report["shortcut_hints"]["candidate_files"])

    def test_settings_probe_extracts_nskeyed_shortcut_display_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / "DoubaoIme" / "MMKV" / "com.apple.xpc.activity"
            settings.parent.mkdir(parents=True)
            settings.write_bytes(b"asrShortcutKeyDisplay_" + (b"x" * 220) + b"VOptionQ0")

            report = build_settings_probe_report([root])

            self.assertEqual(report["shortcut_hints"]["display_values"], ["Option"])
            self.assertIn(str(settings), report["shortcut_hints"]["candidate_files"])

    def test_settings_probe_extracts_nskeyed_shortcut_key_code_and_modifier_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / "DoubaoIme" / "MMKV" / "com.apple.xpc.activity"
            settings.parent.mkdir(parents=True)
            archive = {
                "$version": 100000,
                "$archiver": "NSKeyedArchiver",
                "$top": {"root": UID(1)},
                "$objects": [
                    "$null",
                    {
                        "NS.keys": [UID(2), UID(3), UID(4)],
                        "NS.objects": [UID(5), UID(6), UID(7)],
                        "$class": UID(8),
                    },
                    "asrShortcutKeyCode",
                    "asrShortcutModifierFlags",
                    "asrShortcutKeyDisplay",
                    58,
                    0,
                    "Option",
                    {"$classname": "NSDictionary", "$classes": ["NSDictionary", "NSObject"]},
                ],
            }
            bplist = plistlib.dumps(archive, fmt=plistlib.FMT_BINARY)
            settings.write_bytes((len(bplist) + 8).to_bytes(4, "little") + b"\x00" * 8 + bplist + b"\x00" * 16)

            report = build_settings_probe_report([root])
            row = report["candidate_files"][0]
            hints = report["shortcut_hints"]

            self.assertEqual(row["shortcut_setting_values"]["asrShortcutKeyCode"], 58)
            self.assertEqual(row["shortcut_setting_values"]["asrShortcutModifierFlags"], 0)
            self.assertEqual(row["shortcut_setting_values"]["asrShortcutKeyDisplay"], "Option")
            self.assertEqual(hints["key_codes"], [58])
            self.assertEqual(hints["modifier_flags"], [0])
            self.assertEqual(hints["suggested_hotkey_key_code"], "58")
            self.assertEqual(hints["suggested_hotkey_modifiers"], "option")
            self.assertIn(str(settings), hints["candidate_files"])

    def test_settings_probe_markdown_explains_when_no_visible_settings_are_found(self):
        report = {
            "roots": ["/Users/example/Library/Application Support/DoubaoIme"],
            "candidate_file_count": 0,
            "candidate_files": [],
        }

        markdown = build_settings_probe_markdown(report)

        self.assertIn("Doubao Settings Probe", markdown)
        self.assertIn("No readable hotkey or voice setting candidates were found.", markdown)

    def test_settings_probe_markdown_prints_suggested_hotkey_when_readable(self):
        report = {
            "roots": ["/Users/example/Library/Application Support/DoubaoIme"],
            "candidate_file_count": 1,
            "shortcut_hints": {
                "visible_setting_keys": ["asrShortcutKeyCode", "asrShortcutModifierFlags", "asrShortcutKeyDisplay"],
                "display_values": ["Option"],
                "key_codes": [58],
                "modifier_flags": [0],
                "suggested_hotkey_key_code": "58",
                "suggested_hotkey_modifiers": "option",
                "candidate_files": ["/Users/example/Library/Application Support/DoubaoIme/MMKV/com.apple.xpc.activity"],
            },
            "candidate_files": [
                {
                    "path": "/Users/example/Library/Application Support/DoubaoIme/MMKV/com.apple.xpc.activity",
                    "settings_score": 100,
                    "bytes": 2048,
                    "matched_terms": ["asr", "shortcut"],
                    "snippets": [],
                }
            ],
        }

        markdown = build_settings_probe_markdown(report)

        self.assertIn("Suggested hotkey: keyCode=58, modifiers=option", markdown)
        self.assertIn("Parsed key codes: 58", markdown)
        self.assertIn("Parsed modifier flags: 0", markdown)

    def test_capture_audio_file_copies_audio_and_appends_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "DoubaoIme" / "voice-cache"
            source.parent.mkdir()
            source.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)
            output_dir = root / "capture"
            manifest = output_dir / "manifest.jsonl"

            captured = capture_audio_file(source, output_dir, manifest, captured_at="2026-05-22T00:00:00Z")

            self.assertTrue(captured.path.exists())
            self.assertEqual(captured.path.suffix, ".wav")
            self.assertEqual(captured.path.read_bytes(), source.read_bytes())
            row = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(row["source_path"], str(source))
            self.assertEqual(row["captured_path"], str(captured.path))
            self.assertEqual(row["format"], "wav")
            self.assertEqual(row["bytes"], source.stat().st_size)

    def test_makefile_exposes_doubao_watcher_targets(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("watch-doubao-audio-start:", makefile)
        self.assertIn("watch-doubao-audio-status:", makefile)
        self.assertIn("watch-doubao-audio-stop:", makefile)
        self.assertIn("bench/scripts/watch_doubao_audio.py --daemon", makefile)

    def test_file_snapshots_report_created_and_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "DoubaoIme" / "Log" / "session.bin"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"before")
            before = snapshot_files([root])

            existing.write_bytes(b"after-change")
            created = root / "DoubaoIme" / "voice-cache"
            created.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)
            after = snapshot_files([root])

            changes = diff_snapshots(before, after)

            by_path = {change.path: change for change in changes}
            self.assertEqual(by_path[existing].status, "modified")
            self.assertEqual(by_path[created].status, "created")

    def test_probe_rows_include_audio_format_and_header_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "DoubaoIme" / "voice-cache"
            audio.parent.mkdir()
            audio.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)
            before = {}
            after = snapshot_files([root])
            changes = diff_snapshots(before, after)

            rows = build_file_change_rows(changes)

            self.assertEqual(rows[0]["status"], "created")
            self.assertEqual(rows[0]["audio_format"], "wav")
            self.assertTrue(rows[0]["header_hex"].startswith("52494646"))
            self.assertIn("RIFF", rows[0]["printable_preview"])

    def test_probe_report_writes_json_with_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "probe.json"
            summary = root / "probe.md"
            changed = root / "DoubaoIme" / "asrHistory.db"
            changed.parent.mkdir()
            changed.write_bytes(b"not-audio-but-interesting")
            before = {}
            after = snapshot_files([root])

            report = write_probe_report(
                output_path=output,
                summary_path=summary,
                roots=[root],
                before=before,
                after=after,
                started_at="2026-05-22T00:00:00Z",
                ended_at="2026-05-22T00:00:10Z",
                process_rows=[{"pid": "991", "command": "DoubaoIme"}],
            )

            self.assertEqual(report["changed_file_count"], 1)
            self.assertEqual(report["processes"][0]["command"], "DoubaoIme")
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["changed_files"][0]["audio_format"], None)
            self.assertIn("not-audio", saved["changed_files"][0]["printable_preview"])
            self.assertIn("Doubao Probe Summary", summary.read_text(encoding="utf-8"))

    def test_probe_ranking_prioritizes_audio_and_asr_named_changes(self):
        rows = [
            {
                "status": "modified",
                "path": "/tmp/unrelated/cache.bin",
                "bytes": 4096,
                "before_bytes": 4096,
                "candidate_path": False,
                "audio_format": None,
                "printable_preview": "cache",
            },
            {
                "status": "modified",
                "path": "/Users/example/Library/Application Support/DoubaoIme/Recorder/asrHistory.db",
                "bytes": 8192,
                "before_bytes": 4096,
                "candidate_path": True,
                "audio_format": None,
                "printable_preview": "opaque",
            },
            {
                "status": "created",
                "path": "/tmp/DoubaoIme/voice-cache",
                "bytes": 32000,
                "before_bytes": None,
                "candidate_path": True,
                "audio_format": "wav",
                "printable_preview": "RIFF",
            },
        ]

        ranked = rank_probe_rows(rows)

        self.assertEqual(ranked[0]["path"], "/tmp/DoubaoIme/voice-cache")
        self.assertGreater(ranked[0]["probe_score"], ranked[1]["probe_score"])
        self.assertIn("recognized audio", ranked[0]["probe_reasons"])

    def test_probe_markdown_mentions_top_candidates_and_next_actions(self):
        report = {
            "started_at": "2026-05-22T00:00:00Z",
            "ended_at": "2026-05-22T00:00:20Z",
            "changed_file_count": 1,
            "changed_files": [
                {
                    "status": "created",
                    "path": "/tmp/DoubaoIme/voice-cache",
                    "bytes": 32000,
                    "before_bytes": None,
                    "candidate_path": True,
                    "audio_format": "wav",
                    "printable_preview": "RIFF",
                }
            ],
        }

        markdown = build_probe_markdown(report)

        self.assertIn("Doubao Probe Summary", markdown)
        self.assertIn("/tmp/DoubaoIme/voice-cache", markdown)
        self.assertIn("Next actions", markdown)

    def test_process_parser_ignores_transcript_mentions(self):
        output = "\n".join(
            [
                " 991 1 /Library/Input Methods/DoubaoIme.app/Contents/MacOS/DoubaoIme",
                " 123 1 /Applications/Codex.app/Contents/MacOS/Codex user said DoubaoIme",
            ]
        )

        rows = parse_doubao_process_rows(output)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pid"], "991")

    def test_makefile_exposes_doubao_probe_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("watch-doubao-audio-probe:", makefile)
        self.assertIn("bench/scripts/watch_doubao_audio.py --probe", makefile)
        self.assertIn("watch-doubao-settings-probe:", makefile)
        self.assertIn("bench/scripts/watch_doubao_audio.py --settings-probe", makefile)

    def test_process_is_running_treats_permission_error_as_alive(self):
        with patch("bench.scripts.watch_doubao_audio.os.kill", side_effect=PermissionError):
            self.assertTrue(process_is_running(12345))


if __name__ == "__main__":
    unittest.main()
