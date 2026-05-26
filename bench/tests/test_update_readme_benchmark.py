import tempfile
import unittest
from pathlib import Path

from bench.scripts.update_readme_benchmark import extract_engine_summary, update_readme


class UpdateReadmeBenchmarkTests(unittest.TestCase):
    def test_extract_engine_summary(self):
        report = """# Report

## Engine Summary

| Engine | Samples |
|---|---:|
| whisper | 30 |

## Sample Results

| Sample | Engine |
"""

        self.assertEqual(
            extract_engine_summary(report),
            "## Engine Summary\n\n| Engine | Samples |\n|---|---:|\n| whisper | 30 |",
        )

    def test_update_readme_replaces_marked_region(self):
        readme = """# SwitchType

<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->
old
<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->
"""

        updated = update_readme(readme, "new summary")

        self.assertIn("new summary", updated)
        self.assertNotIn("\nold\n", updated)

    def test_script_updates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            report = root / "report.md"
            readme.write_text(
                "# SwitchType\n\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_START -->\n"
                "old\n"
                "<!-- SWITCHTYPE_BENCHMARK_SUMMARY_END -->\n",
                encoding="utf-8",
            )
            report.write_text(
                "# Report\n\n"
                "## Engine Summary\n\n"
                "| Engine | Samples |\n"
                "|---|---:|\n"
                "| fake | 2 |\n\n"
                "## Sample Results\n\n",
                encoding="utf-8",
            )

            from bench.scripts import update_readme_benchmark

            summary = update_readme_benchmark.extract_engine_summary(report.read_text(encoding="utf-8"))
            readme.write_text(
                update_readme_benchmark.update_readme(readme.read_text(encoding="utf-8"), summary),
                encoding="utf-8",
            )

            self.assertIn("| fake | 2 |", readme.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
