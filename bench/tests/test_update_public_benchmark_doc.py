import tempfile
import unittest
from pathlib import Path

from bench.scripts.update_public_benchmark_doc import (
    PUBLIC_README_END,
    PUBLIC_README_START,
    build_document,
    build_readme_summary,
    extract_section,
    relative_repo_path,
    update_readme_public_summary,
)


PUBLIC_REPORT = """# SwitchType Benchmark Report

## Run Metadata

- Generated at: 2026-05-22T05:12:59+00:00
- Config: /repo/bench/config/benchmark.local.json
- Hotwords: /repo/bench/config/hotwords.example.json
- Manifest: /repo/bench/samples/public/manifest.jsonl
- Report: /repo/bench/reports/public-asr.md

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| sensevoice_funasr | 3 | 8738.3 | 0.439 | 0.573 | 1.000 |
| whisper_cpp | 3 | 6113.7 | 1.555 | 0.872 | 1.000 |

## Sample Results

| Sample | Engine | Latency ms | CER | WER | Term Accuracy | Processed Transcript |
|---|---|---:|---:|---:|---:|---|
| ascend-00004 | whisper_cpp | 6618.7 | 0.909 | 1.000 | 1.000 | So it was not a |
"""


class UpdatePublicBenchmarkDocTests(unittest.TestCase):
    def test_extract_section_keeps_engine_summary_only(self):
        self.assertEqual(
            extract_section(PUBLIC_REPORT, "## Engine Summary", "## Sample Results"),
            "## Engine Summary\n\n"
            "| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |\n"
            "|---|---:|---:|---:|---:|---:|\n"
            "| sensevoice_funasr | 3 | 8738.3 | 0.439 | 0.573 | 1.000 |\n"
            "| whisper_cpp | 3 | 6113.7 | 1.555 | 0.872 | 1.000 |",
        )

    def test_relative_repo_path_removes_local_absolute_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "bench/reports/public-asr.md"

            self.assertEqual(relative_repo_path(str(path), root), "bench/reports/public-asr.md")

    def test_build_document_includes_repro_command_sources_and_summary(self):
        document = build_document(PUBLIC_REPORT, root=Path("/repo"))

        self.assertIn("# SwitchType Public Benchmark", document)
        self.assertIn("make public-asr", document)
        self.assertIn("make public-readiness", document)
        self.assertIn("CAiRE/ASCEND", document)
        self.assertIn("bench/samples/public/manifest.jsonl", document)
        self.assertIn("| sensevoice_funasr | 3 | 8738.3 | 0.439 | 0.573 | 1.000 |", document)
        self.assertIn("not personal microphone evidence", document)

    def test_build_readme_summary_links_public_doc_and_includes_engine_table(self):
        summary = build_readme_summary(PUBLIC_REPORT, root=Path("/repo"))

        self.assertIn("Latest public benchmark: 3 ASCEND mixed samples.", summary)
        self.assertIn("[docs/public-benchmark.md](docs/public-benchmark.md)", summary)
        self.assertIn("| sensevoice_funasr | 3 | 8738.3 | 0.439 | 0.573 | 1.000 |", summary)
        self.assertIn("not personal microphone evidence", summary)

    def test_update_readme_public_summary_replaces_marked_region(self):
        readme = "\n".join(
            [
                "# SwitchType",
                "",
                PUBLIC_README_START,
                "stale",
                PUBLIC_README_END,
                "",
            ]
        )

        updated = update_readme_public_summary(readme, "fresh")

        self.assertIn(f"{PUBLIC_README_START}\nfresh\n{PUBLIC_README_END}", updated)
        self.assertNotIn("stale", updated)

    def test_makefile_exposes_public_summary_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("public-summary:", makefile)
        self.assertIn("bench/scripts/update_public_benchmark_doc.py", makefile)


if __name__ == "__main__":
    unittest.main()
