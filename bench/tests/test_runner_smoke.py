import json
import tempfile
import unittest
from pathlib import Path

from switchtype_bench.runner import run_benchmark


class RunnerSmokeTests(unittest.TestCase):
    def test_fake_engine_generates_markdown_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "benchmark.json"
            hotwords_path = root / "hotwords.json"
            manifest_path = root / "manifest.jsonl"
            report_path = root / "report.md"

            config_path.write_text(
                json.dumps(
                    {
                        "timeout_seconds": 5,
                        "engines": [
                            {
                                "name": "fake",
                                "type": "fake",
                                "enabled": True,
                                "transcript": "扣德克斯 皮阿尔",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            hotwords_path.write_text(
                json.dumps(
                    {
                        "protected_terms": ["Codex", "PR"],
                        "replacements": {"扣德克斯": "Codex", "皮阿尔": "PR"},
                    }
                ),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "id": "sample-001",
                        "audio": "missing.wav",
                        "reference": "Codex PR",
                        "terms": ["Codex", "PR"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_benchmark(config_path, hotwords_path, manifest_path, report_path)

            self.assertEqual(result.engine_count, 1)
            self.assertEqual(result.sample_count, 1)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("## Run Metadata", report)
            self.assertIn(f"- Config: {config_path}", report)
            self.assertIn(f"- Hotwords: {hotwords_path}", report)
            self.assertIn(f"- Manifest: {manifest_path}", report)
            self.assertIn(f"- Report: {report_path}", report)
            self.assertIn("| sample-001 | fake |", report)


if __name__ == "__main__":
    unittest.main()
