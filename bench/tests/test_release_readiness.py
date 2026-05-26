import json
import os
import tempfile
import unittest
import wave
from pathlib import Path

import scripts.check_release_ready as release_ready


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


def gif_bytes(width: int, height: int, payload_bytes: int = 0) -> bytes:
    return (
        b"GIF89a"
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
        + b"\x80\x00\x00"
        + (b"\x00" * payload_bytes)
    )


def valid_benchmark_report(include_metadata: bool = True) -> str:
    metadata = """## Run Metadata

- Generated at: 2026-05-21T10:30:00+00:00
- Config: bench/config/benchmark.local.json
- Hotwords: ~/.switchtype/hotwords.json
- Manifest: bench/samples/manifest.30-template.jsonl
- Report: bench/reports/real-asr.md

""" if include_metadata else ""
    return f"""# SwitchType Benchmark Report

{metadata}## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 405.0 | 0.100 | 0.200 | 1.000 |
| sensevoice | 2 | 505.0 | 0.200 | 0.300 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-002 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
"""


def complete_verification_log(
    audio_sample_count: str = "30/30 valid",
    asr_engines: str = "whisper_cpp, sensevoice",
    report_path: str = "bench/reports/real-asr.md",
    benchmark_command: str = "env SWITCHTYPE_ENABLE_SENSEVOICE=1 make real-benchmark",
    hotword_config_path: str = "bench/config/hotwords.example.json",
    app_build: str = "dist/SwitchType-0.1.0.zip",
    launch_method: str = "dist/SwitchType.app",
    microphone_permission: str = "granted",
    accessibility_permission: str = "granted",
    spoken_sentence: str = "帮我看一下 Codex 的 PR issue 有没有过 CI",
    pasted_output: str = "帮我看一下 Codex 的 PR issue 有没有过 CI",
    hotwords_preserved: str = "yes",
    short_recording_rejected: str = "yes",
    hotkey_consumed: str = "yes",
    real_asr_demo: str = "yes",
    final_result: str = "strict readiness passed",
) -> str:
    return f"""# SwitchType Verification Log

## Benchmark Run

- Date: 2026-05-21
- Machine: macOS
- Manifest: bench/samples/manifest.30-template.jsonl
- Audio sample count: {audio_sample_count}
- ASR engines: {asr_engines}
- Report path: {report_path}
- Command:

```bash
{benchmark_command}
```

- Result summary: whisper_cpp and sensevoice completed

## App Manual Verification

- Date: 2026-05-21
- App build: {app_build}
- Launch method: {launch_method}
- Microphone permission: {microphone_permission}
- Accessibility permission: {accessibility_permission}
- Hotword config path: {hotword_config_path}
- Input app: TextEdit
- Spoken sentence: {spoken_sentence}
- Pasted output: {pasted_output}
- Hotwords preserved: {hotwords_preserved}
- Short recording rejected: {short_recording_rejected}
- Hotkey consumed: {hotkey_consumed}

## Demo Asset

- GIF path: docs/assets/switchtype-demo.gif
- Duration: 8s
- Shows real ASR rather than debug transcript mode: {real_asr_demo}

## Final Readiness

- Result: {final_result}
"""


def write_hotword_config(root: Path, path: str = "bench/config/hotwords.example.json") -> None:
    config = root / path
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "protected_terms": ["Codex", "MCP", "SeaTalk", "prelive", "Go", "PR", "issue", "CI"],
                "replacements": {"扣德克斯": "Codex", "皮阿尔": "PR"},
            }
        ),
        encoding="utf-8",
    )
    write_app_build(root)


def write_app_build(root: Path) -> None:
    build = root / "dist/SwitchType-0.1.0.zip"
    build.parent.mkdir(parents=True, exist_ok=True)
    build.write_bytes(b"zip")


class ReleaseReadinessTests(unittest.TestCase):
    def test_engine_summary_rows_parse_markdown(self):
        report = """# Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 30 | 400.0 | 0.100 | 0.200 | 0.950 |

## Sample Results
"""

        self.assertEqual(
            release_ready._engine_summary_rows(report),
            [
                {
                    "engine": "whisper_cpp",
                    "samples": "30",
                    "avg_latency_ms": "400.0",
                    "avg_cer": "0.100",
                    "avg_wer": "0.200",
                    "term_accuracy": "0.950",
                }
            ],
        )

    def test_sample_result_rows_parse_markdown(self):
        report = """# Report

## Sample Results

| Sample | Engine | Latency ms |
|---|---|---:|
| sample-001 | whisper_cpp | 1.0 |
| sample-002 | fake | 0.0 |
"""

        self.assertEqual(
            release_ready._sample_result_rows(report),
            [
                {
                    "sample": "sample-001",
                    "engine": "whisper_cpp",
                    "latency_ms": "1.0",
                    "cer": "",
                    "wer": "",
                    "term_accuracy": "",
                    "processed_transcript": "",
                },
                {
                    "sample": "sample-002",
                    "engine": "fake",
                    "latency_ms": "0.0",
                    "cer": "",
                    "wer": "",
                    "term_accuracy": "",
                    "processed_transcript": "",
                },
            ],
        )

    def test_parse_verification_log_ignores_code_blocks(self):
        text = """# Log

## Benchmark Run

- Date: 2026-05-21
- Command:

```bash
scripts/run_real_benchmark.sh
```

- Result summary: whisper_cpp passed

## Demo Asset

- Shows real ASR rather than debug transcript mode: yes
"""

        self.assertEqual(
            release_ready.parse_verification_log(text),
            {
                "Benchmark Run/Date": "2026-05-21",
                "Benchmark Run/Command": "scripts/run_real_benchmark.sh",
                "Benchmark Run/Result summary": "whisper_cpp passed",
                "Demo Asset/Shows real ASR rather than debug transcript mode": "yes",
            },
        )

    def test_parse_verification_log_does_not_fill_distant_code_blocks(self):
        text = """# Log

## Benchmark Run

- Result summary:

## Final Readiness

```bash
python3 scripts/check_release_ready.py --strict
```

- Result:
"""

        self.assertEqual(
            release_ready.parse_verification_log(text),
            {
                "Benchmark Run/Result summary": "",
                "Final Readiness/Result": "",
            },
        )

    def test_verification_log_requires_benchmark_command(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(benchmark_command=""), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Command", check.detail)

    def test_verification_log_requires_all_audio_samples_valid(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(audio_sample_count="0/30 valid"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Audio sample count", check.detail)

    def test_verification_log_requires_two_asr_engines(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(asr_engines="whisper_cpp"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("ASR engines", check.detail)

    def test_verification_log_requires_real_report_path(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(report_path="bench/reports/example.md"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Report path", check.detail)

    def test_verification_log_requires_packaged_app_build_path(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            (root / "dist/SwitchType-0.1.0.zip").write_bytes(b"zip")
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(app_build="app/SwitchType/.build/debug/SwitchType"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("App build", check.detail)

    def test_verification_log_requires_existing_app_build_path(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            (root / "dist/SwitchType-0.1.0.zip").unlink()
            log.write_text(complete_verification_log(), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("App build", check.detail)

    def test_verification_log_requires_hotword_config_path(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(hotword_config_path=""), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Hotword config path", check.detail)

    def test_verification_log_requires_existing_hotword_config(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_app_build(root)
            log.write_text(complete_verification_log(hotword_config_path="bench/config/missing.json"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Hotword config", check.detail)

    def test_verification_log_requires_packaged_app_launch_method(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(launch_method="scripts/run_app_dev.sh"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Launch method", check.detail)

    def test_verification_log_requires_pasted_output_to_preserve_config_terms(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(
                complete_verification_log(pasted_output="帮我看一下 扣德克斯 的 皮阿尔 有没有过"),
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Pasted output", check.detail)

    def test_verification_log_requires_granted_microphone_permission(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(microphone_permission="denied"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Microphone permission", check.detail)

    def test_verification_log_requires_granted_accessibility_permission(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(accessibility_permission="denied"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Accessibility permission", check.detail)

    def test_verification_log_requires_hotwords_preserved(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(hotwords_preserved="no"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Hotwords preserved", check.detail)

    def test_verification_log_requires_short_recording_rejected(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(short_recording_rejected="no"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Short recording rejected", check.detail)

    def test_verification_log_requires_hotkey_consumed(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(hotkey_consumed="no"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Hotkey consumed", check.detail)

    def test_verification_log_requires_final_readiness_passed(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(final_result="strict readiness failed"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Final readiness", check.detail)

    def test_verification_log_can_ignore_pending_final_readiness_for_prefinal_gate(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(final_result=""), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check(
                    "docs/verification-log.md",
                    require_final_result=False,
                )
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok)

    def test_verification_log_rejects_not_passed_final_readiness(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(final_result="not passed"), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("Final readiness", check.detail)

    def test_verification_log_accepts_success_values(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            write_hotword_config(root)
            log.write_text(complete_verification_log(), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok)

    def test_verification_log_accepts_tilde_hotword_config_path(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            log = root / "docs/verification-log.md"
            log.parent.mkdir(parents=True)
            hotwords = home / ".switchtype/hotwords.json"
            hotwords.parent.mkdir(parents=True)
            hotwords.write_text(
                json.dumps(
                    {
                        "protected_terms": ["Codex", "PR"],
                        "replacements": {"扣德克斯": "Codex"},
                    }
                ),
                encoding="utf-8",
            )
            write_app_build(root)
            log.write_text(complete_verification_log(hotword_config_path="~/.switchtype/hotwords.json"), encoding="utf-8")
            previous_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            release_ready.ROOT = root
            try:
                check = release_ready.verification_log_check("docs/verification-log.md")
            finally:
                release_ready.ROOT = original_root
                if previous_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = previous_home

            self.assertTrue(check.ok)

    def test_strict_audio_check_rejects_unreadable_wav(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "bench/samples/audio/sample-001.wav"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"not a real wav")
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.strict_audio_check("bench/samples/manifest.jsonl", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("invalid", check.detail)

    def test_strict_audio_check_rejects_silent_wav(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "bench/samples/audio/sample-001.wav"
            write_test_wav(audio, signal=False)
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.strict_audio_check("bench/samples/manifest.jsonl", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("silent", check.detail)

    def test_strict_audio_check_rejects_wrong_sample_rate_wav(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "bench/samples/audio/sample-001.wav"
            write_test_wav(audio, rate=8000)
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.strict_audio_check("bench/samples/manifest.jsonl", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("wrong format", check.detail)

    def test_strict_audio_check_rejects_stereo_wav(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "bench/samples/audio/sample-001.wav"
            write_test_wav(audio, channels=2)
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.strict_audio_check("bench/samples/manifest.jsonl", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("wrong format", check.detail)

    def test_strict_audio_check_requires_expected_count(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "bench/samples/audio/sample-001.wav"
            write_test_wav(audio)
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.strict_audio_check("bench/samples/manifest.jsonl", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("1/2", check.detail)

    def test_gif_check_rejects_non_gif_file(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "docs/assets/switchtype-demo.gif"
            gif.parent.mkdir(parents=True)
            gif.write_text("not a gif", encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.gif_check("docs/assets/switchtype-demo.gif")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("not a GIF", check.detail)

    def test_gif_check_rejects_tiny_gif_file(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "docs/assets/switchtype-demo.gif"
            gif.parent.mkdir(parents=True)
            gif.write_bytes(gif_bytes(width=1, height=1))
            release_ready.ROOT = root
            try:
                check = release_ready.gif_check("docs/assets/switchtype-demo.gif")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("too small", check.detail)

    def test_gif_check_rejects_small_dimensions(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "docs/assets/switchtype-demo.gif"
            gif.parent.mkdir(parents=True)
            gif.write_bytes(gif_bytes(width=320, height=240, payload_bytes=12_000))
            release_ready.ROOT = root
            try:
                check = release_ready.gif_check("docs/assets/switchtype-demo.gif")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("dimensions", check.detail)

    def test_gif_check_accepts_screen_recording_like_gif(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "docs/assets/switchtype-demo.gif"
            gif.parent.mkdir(parents=True)
            gif.write_bytes(gif_bytes(width=1280, height=720, payload_bytes=12_000))
            release_ready.ROOT = root
            try:
                check = release_ready.gif_check("docs/assets/switchtype-demo.gif")
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok)
            self.assertIn("1280x720", check.detail)

    def test_benchmark_report_check_requires_run_metadata(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"}),
                        json.dumps({"id": "sample-002", "audio": "bench/samples/audio/sample-002.wav", "reference": "MCP server"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(valid_benchmark_report(include_metadata=False), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("run metadata", check.detail)

    def test_benchmark_report_check_accepts_run_metadata(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"}),
                        json.dumps({"id": "sample-002", "audio": "bench/samples/audio/sample-002.wav", "reference": "MCP server"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(valid_benchmark_report(), encoding="utf-8")
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok)
            self.assertIn("2 non-fake engine(s)", check.detail)

    def test_benchmark_report_check_allows_table_rounding_difference(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/public/manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "ascend-00004", "audio": "a.wav", "reference": "a"}),
                        json.dumps({"id": "ascend-00009", "audio": "b.wav", "reference": "b"}),
                        json.dumps({"id": "ascend-00028", "audio": "c.wav", "reference": "c"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/public-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Run Metadata

- Generated at: 2026-05-22T05:12:59+00:00
- Config: bench/config/benchmark.local.json
- Hotwords: bench/config/hotwords.example.json
- Manifest: bench/samples/public/manifest.jsonl
- Report: bench/reports/public-asr.md

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| sensevoice_funasr | 3 | 8738.3 | 0.439 | 0.573 | 1.000 |
| whisper_cpp | 3 | 6113.7 | 1.555 | 0.872 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| ascend-00004 | whisper_cpp | 6618.7 | 0.909 | 1.000 | 1.000 | So it was not a |
| ascend-00009 | whisper_cpp | 6103.4 | 0.256 | 0.615 | 1.000 | ISM Information Systems Management |
| ascend-00028 | whisper_cpp | 5619.1 | 3.500 | 1.000 | 1.000 | Okay, food chain. |
| ascend-00004 | sensevoice_funasr | 9396.3 | 0.636 | 1.000 | 1.000 | That it was the. |
| ascend-00009 | sensevoice_funasr | 8240.3 | 0.179 | 0.385 | 1.000 | ISM information systems management. |
| ascend-00028 | sensevoice_funasr | 8578.2 | 0.500 | 0.333 | 1.000 | ok. |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check(
                    "bench/reports/public-asr.md",
                    3,
                    manifest_path="bench/samples/public/manifest.jsonl",
                )
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok, check.detail)

    def test_benchmark_report_check_requires_manifest_sample_ids(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "sample-001",
                                "audio": "bench/samples/audio/sample-001.wav",
                                "reference": "Codex PR",
                            }
                        ),
                        json.dumps(
                            {
                                "id": "sample-002",
                                "audio": "bench/samples/audio/sample-002.wav",
                                "reference": "MCP server",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 400.0 | 0.100 | 0.200 | 0.950 |
| sensevoice | 2 | 500.0 | 0.200 | 0.300 | 0.850 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-999 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-998 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-999 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-998 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("missing manifest sample ids", check.detail)

    def test_benchmark_report_check_rejects_incomplete_non_fake_engine_summary(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "sample-001",
                                "audio": "bench/samples/audio/sample-001.wav",
                                "reference": "Codex PR",
                            }
                        ),
                        json.dumps(
                            {
                                "id": "sample-002",
                                "audio": "bench/samples/audio/sample-002.wav",
                                "reference": "MCP server",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 400.0 | 0.100 | 0.200 | 0.950 |
| sensevoice | 1 | 500.0 | 0.200 | 0.300 | 0.850 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-002 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("non-fake engine sample count", check.detail)

    def test_benchmark_report_check_requires_two_non_fake_engines(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "sample-001",
                                "audio": "bench/samples/audio/sample-001.wav",
                                "reference": "Codex PR",
                            }
                        ),
                        json.dumps(
                            {
                                "id": "sample-002",
                                "audio": "bench/samples/audio/sample-002.wav",
                                "reference": "MCP server",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 400.0 | 0.100 | 0.200 | 0.950 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("at least 2 non-fake engines", check.detail)

    def test_benchmark_report_check_rejects_malformed_non_fake_sample_metrics(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"})
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 1 | 400.0 | 0.100 | 0.200 | 0.950 |
| sensevoice | 1 | 500.0 | 0.200 | 0.300 | 0.850 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | N/A | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("malformed sample metrics", check.detail)

    def test_benchmark_report_check_rejects_empty_non_fake_transcript(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"})
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 1 | 400.0 | 0.100 | 0.200 | 0.950 |
| sensevoice | 1 | 500.0 | 0.200 | 0.300 | 0.850 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 |  |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 1)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("empty transcript", check.detail)

    def test_benchmark_report_check_rejects_summary_sample_count_mismatch(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"}),
                        json.dumps({"id": "sample-002", "audio": "bench/samples/audio/sample-002.wav", "reference": "MCP server"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 3 | 405.0 | 0.100 | 0.200 | 1.000 |
| sensevoice | 2 | 505.0 | 0.200 | 0.300 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-002 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("summary sample count", check.detail)

    def test_benchmark_report_check_rejects_summary_average_mismatch(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"}),
                        json.dumps({"id": "sample-002", "audio": "bench/samples/audio/sample-002.wav", "reference": "MCP server"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 999.0 | 0.100 | 0.200 | 1.000 |
| sensevoice | 2 | 505.0 | 0.200 | 0.300 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-002 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("summary average", check.detail)

    def test_benchmark_report_check_rejects_duplicate_non_fake_sample_rows(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.30-template.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex PR"}),
                        json.dumps({"id": "sample-002", "audio": "bench/samples/audio/sample-002.wav", "reference": "MCP server"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 3 | 406.7 | 0.100 | 0.200 | 1.000 |
| sensevoice | 2 | 505.0 | 0.200 | 0.300 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| sample-001 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | Codex PR again |
| sample-002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| sample-001 | sensevoice | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| sample-002 | sensevoice | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
""",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.benchmark_report_check("bench/reports/real-asr.md", 2)
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("duplicate sample row", check.detail)

    def test_readme_benchmark_summary_rejects_placeholder_after_report_exists(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "# SwitchType\n\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->\n"
                "Real ASR benchmark results have not been recorded yet.\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                "# SwitchType Benchmark Report\n\n"
                "## Engine Summary\n\n"
                "| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |\n"
                "|---|---:|---:|---:|---:|---:|\n"
                "| whisper_cpp | 2 | 400.0 | 0.100 | 0.200 | 0.950 |\n\n"
                "## Sample Results\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.readme_benchmark_summary_check("README.md", "bench/reports/real-asr.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("not updated", check.detail)

    def test_readme_benchmark_summary_requires_real_report(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text(
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->\n"
                "placeholder\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.readme_benchmark_summary_check("README.md", "bench/reports/real-asr.md")
            finally:
                release_ready.ROOT = original_root

            self.assertFalse(check.ok)
            self.assertIn("real benchmark report missing", check.detail)

    def test_readme_benchmark_summary_accepts_report_summary(self):
        original_root = release_ready.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = (
                "## Engine Summary\n\n"
                "| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |\n"
                "|---|---:|---:|---:|---:|---:|\n"
                "| whisper_cpp | 2 | 400.0 | 0.100 | 0.200 | 0.950 |"
            )
            readme = root / "README.md"
            readme.write_text(
                "# SwitchType\n\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->\n"
                f"{summary}\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                "# SwitchType Benchmark Report\n\n"
                f"{summary}\n\n"
                "## Sample Results\n",
                encoding="utf-8",
            )
            release_ready.ROOT = root
            try:
                check = release_ready.readme_benchmark_summary_check("README.md", "bench/reports/real-asr.md")
            finally:
                release_ready.ROOT = original_root

            self.assertTrue(check.ok)


if __name__ == "__main__":
    unittest.main()
