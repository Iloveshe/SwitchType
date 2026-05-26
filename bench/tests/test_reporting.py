import tempfile
import unittest
from pathlib import Path

from switchtype_bench.reporting import BenchmarkMetadata, BenchmarkRow, summarize_by_engine, write_markdown_report


class ReportingTests(unittest.TestCase):
    def test_summarize_by_engine_aggregates_rows(self):
        rows = [
            BenchmarkRow("s1", "fake", 10.0, "a", "a", 0.1, 0.2, 1, 2, 0.5),
            BenchmarkRow("s2", "fake", 30.0, "b", "b", 0.3, 0.4, 2, 2, 1.0),
        ]

        summary = summarize_by_engine(rows)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0].engine, "fake")
        self.assertEqual(summary[0].sample_count, 2)
        self.assertEqual(summary[0].average_latency_ms, 20.0)
        self.assertAlmostEqual(summary[0].average_cer, 0.2)
        self.assertAlmostEqual(summary[0].average_wer, 0.3)
        self.assertAlmostEqual(summary[0].term_accuracy, 0.75)

    def test_report_contains_summary_and_sample_sections(self):
        rows = [
            BenchmarkRow("s1", "fake", 10.0, "raw", "processed", 0.1, 0.2, 1, 1, 1.0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"

            write_markdown_report(path, rows)

            report = path.read_text(encoding="utf-8")
            self.assertIn("## Engine Summary", report)
            self.assertIn("| fake | 1 | 10.0 | 0.100 | 0.200 | 1.000 |", report)
            self.assertIn("## Sample Results", report)
            self.assertIn("| s1 | fake | 10.0 | 0.100 | 0.200 | 1.000 | processed |", report)

    def test_report_contains_run_metadata_when_provided(self):
        rows = [
            BenchmarkRow("s1", "fake", 10.0, "raw", "processed", 0.1, 0.2, 1, 1, 1.0),
        ]
        metadata = BenchmarkMetadata(
            generated_at="2026-05-21T10:30:00Z",
            config_path="bench/config/benchmark.local.json",
            hotwords_path="~/.switchtype/hotwords.json",
            manifest_path="bench/samples/manifest.30-template.jsonl",
            report_path="bench/reports/real-asr.md",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"

            write_markdown_report(path, rows, metadata=metadata)

            report = path.read_text(encoding="utf-8")
            self.assertIn("## Run Metadata", report)
            self.assertIn("- Generated at: 2026-05-21T10:30:00Z", report)
            self.assertIn("- Config: bench/config/benchmark.local.json", report)
            self.assertIn("- Hotwords: ~/.switchtype/hotwords.json", report)
            self.assertIn("- Manifest: bench/samples/manifest.30-template.jsonl", report)
            self.assertIn("- Report: bench/reports/real-asr.md", report)


if __name__ == "__main__":
    unittest.main()
