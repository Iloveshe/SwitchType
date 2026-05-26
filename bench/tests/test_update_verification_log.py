import json
import tempfile
import unittest
import wave
from pathlib import Path

from scripts.check_release_ready import parse_verification_log
from scripts.update_verification_log import audio_sample_status, build_log


REPORT = """# SwitchType Benchmark Report

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 30 | 400.0 | 0.100 | 0.200 | 0.950 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| sample-001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
"""


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


class UpdateVerificationLogTests(unittest.TestCase):
    def test_build_log_extracts_benchmark_fields_without_faking_manual_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/manifest.jsonl"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "bench/samples/audio/sample-001.wav", "reference": "Codex"})
                + "\n",
                encoding="utf-8",
            )
            report = root / "bench/reports/real-asr.md"
            report.parent.mkdir(parents=True)
            report.write_text(REPORT, encoding="utf-8")

            log = build_log(
                root=root,
                date="2026-05-21",
                manifest=manifest,
                benchmark_report=report,
                app_build=root / "dist/SwitchType-0.1.0.zip",
                gif_path=root / "docs/assets/switchtype-demo.gif",
                benchmark_command="env SWITCHTYPE_WHISPER_BIN=/opt/whisper make real-benchmark",
                manual_fields={},
            )
            fields = parse_verification_log(log)

            self.assertEqual(fields["Benchmark Run/Date"], "2026-05-21")
            self.assertEqual(fields["Benchmark Run/Manifest"], "bench/samples/manifest.jsonl")
            self.assertEqual(fields["Benchmark Run/Audio sample count"], "0/1 valid (1 missing)")
            self.assertEqual(fields["Benchmark Run/ASR engines"], "whisper_cpp")
            self.assertEqual(fields["Benchmark Run/Report path"], "bench/reports/real-asr.md")
            self.assertIn("whisper_cpp: 30 samples", fields["Benchmark Run/Result summary"])
            self.assertIn("env SWITCHTYPE_WHISPER_BIN=/opt/whisper make real-benchmark", log)
            self.assertEqual(fields["App Manual Verification/Launch method"], "")
            self.assertEqual(fields["Demo Asset/GIF path"], "")

    def test_build_log_accepts_manual_evidence_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = root / "docs/assets/switchtype-demo.gif"
            gif.parent.mkdir(parents=True)
            gif.write_bytes(b"GIF89a")
            app_build = root / "dist/SwitchType-0.1.0.zip"
            app_build.parent.mkdir(parents=True)
            app_build.write_bytes(b"zip")

            log = build_log(
                root=root,
                date="2026-05-21",
                manifest=root / "bench/samples/manifest.30-template.jsonl",
                benchmark_report=root / "bench/reports/real-asr.md",
                app_build=app_build,
                gif_path=gif,
                benchmark_command="scripts/run_real_benchmark.sh",
                manual_fields={
                    "launch_method": "dist/SwitchType.app",
                    "microphone_permission": "granted",
                    "accessibility_permission": "granted",
                    "hotword_config_path": "bench/config/hotwords.example.json",
                    "input_app": "TextEdit",
                    "spoken_sentence": "帮我看一下 Codex PR",
                    "pasted_output": "帮我看一下 Codex PR",
                    "hotwords_preserved": "yes",
                    "short_recording_rejected": "yes",
                    "hotkey_consumed": "yes",
                    "recording_tool": "Kap",
                    "gif_duration": "8s",
                    "real_asr_demo": "yes",
                    "final_result": "strict readiness passed",
                },
            )
            fields = parse_verification_log(log)

            self.assertEqual(fields["App Manual Verification/App build"], "dist/SwitchType-0.1.0.zip")
            self.assertEqual(fields["App Manual Verification/Microphone permission"], "granted")
            self.assertEqual(fields["App Manual Verification/Short recording rejected"], "yes")
            self.assertEqual(fields["App Manual Verification/Hotkey consumed"], "yes")
            self.assertEqual(fields["Demo Asset/GIF path"], "docs/assets/switchtype-demo.gif")
            self.assertEqual(fields["Demo Asset/Shows real ASR rather than debug transcript mode"], "yes")
            self.assertEqual(fields["Final Readiness/Result"], "strict readiness passed")

    def test_audio_sample_status_counts_wrong_wav_format(self):
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

            self.assertEqual(audio_sample_status(manifest, root), "0/1 valid (1 wrong format)")

    def test_audio_sample_status_counts_silent_wav(self):
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

            self.assertEqual(audio_sample_status(manifest, root), "0/1 valid (1 silent)")


if __name__ == "__main__":
    unittest.main()
