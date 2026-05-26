import tempfile
import unittest
import wave
from pathlib import Path

from bench.scripts.update_public_benchmark_doc import (
    PUBLIC_README_END,
    PUBLIC_README_START,
    build_document,
    build_readme_summary,
)
from scripts import check_public_benchmark_ready as public_ready


def write_test_wav(path: Path, seconds: float = 0.25) -> None:
    rate = 16000
    frames = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * frames)


def valid_public_report() -> str:
    return """# SwitchType Public Benchmark Report

## Run Metadata

- Generated at: 2026-05-22T10:30:00+00:00
- Config: bench/config/benchmark.local.json
- Hotwords: bench/config/hotwords.example.json
- Manifest: bench/samples/public/manifest.jsonl
- Report: bench/reports/public-asr.md

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| whisper_cpp | 2 | 405.0 | 0.100 | 0.200 | 1.000 |
| sensevoice_funasr | 2 | 505.0 | 0.200 | 0.300 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| ascend-00001 | whisper_cpp | 400.0 | 0.100 | 0.200 | 1.000 | Codex PR |
| ascend-00002 | whisper_cpp | 410.0 | 0.100 | 0.200 | 1.000 | MCP server |
| ascend-00001 | sensevoice_funasr | 500.0 | 0.200 | 0.300 | 1.000 | Codex PR |
| ascend-00002 | sensevoice_funasr | 510.0 | 0.200 | 0.300 | 1.000 | MCP server |
"""


class PublicBenchmarkReadinessTests(unittest.TestCase):
    def test_collect_checks_accepts_public_manifest_audio_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "bench/samples/public/manifest.jsonl"
            manifest.parent.mkdir(parents=True)
            write_test_wav(root / "bench/samples/public/audio/ascend-00001.wav")
            write_test_wav(root / "bench/samples/public/audio/ascend-00002.wav")
            manifest.write_text(
                '{"id":"ascend-00001","audio":"bench/samples/public/audio/ascend-00001.wav","reference":"Codex PR"}\n'
                '{"id":"ascend-00002","audio":"bench/samples/public/audio/ascend-00002.wav","reference":"MCP server"}\n',
                encoding="utf-8",
            )
            report = root / "bench/reports/public-asr.md"
            report.parent.mkdir(parents=True)
            report.write_text(valid_public_report(), encoding="utf-8")
            doc = root / "docs/public-benchmark.md"
            doc.parent.mkdir(parents=True)
            doc.write_text(build_document(valid_public_report(), root=root), encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                f"# SwitchType\n\n{PUBLIC_README_START}\n"
                f"{build_readme_summary(valid_public_report(), root=root)}\n"
                f"{PUBLIC_README_END}\n",
                encoding="utf-8",
            )

            checks = public_ready.collect_checks(root=root)

        self.assertTrue(all(check.ok for check in checks), checks)

    def test_public_doc_check_rejects_stale_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "bench/reports/public-asr.md"
            report.parent.mkdir(parents=True)
            report.write_text(valid_public_report(), encoding="utf-8")
            doc = root / "docs/public-benchmark.md"
            doc.parent.mkdir(parents=True)
            doc.write_text("# stale\n", encoding="utf-8")

            check = public_ready.public_doc_check(root=root)

        self.assertFalse(check.ok)
        self.assertEqual(check.name, "public benchmark doc")
        self.assertIn("stale", check.detail)

    def test_public_readme_check_rejects_stale_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "bench/reports/public-asr.md"
            report.parent.mkdir(parents=True)
            report.write_text(valid_public_report(), encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                f"# SwitchType\n\n{PUBLIC_README_START}\nstale\n{PUBLIC_README_END}\n",
                encoding="utf-8",
            )

            check = public_ready.public_readme_check(root=root)

        self.assertFalse(check.ok)
        self.assertEqual(check.name, "README public benchmark summary")
        self.assertIn("stale", check.detail)

    def test_public_audio_check_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            check = public_ready.public_audio_check(root=root)

        self.assertFalse(check.ok)
        self.assertEqual(check.name, "public audio samples")
        self.assertIn("manifest missing", check.detail)

    def test_makefile_exposes_public_readiness_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("public-readiness:", makefile)
        self.assertIn("scripts/check_public_benchmark_ready.py", makefile)


if __name__ == "__main__":
    unittest.main()
