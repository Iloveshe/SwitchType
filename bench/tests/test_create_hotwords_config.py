import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CreateHotwordsConfigTests(unittest.TestCase):
    def test_create_hotwords_config_merges_base_and_manifest_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.json"
            base.write_text(
                json.dumps(
                    {
                        "protected_terms": ["Codex", "PR"],
                        "replacements": {"扣德克斯": "Codex"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.jsonl"
            manifest.write_text(
                json.dumps({"id": "sample-001", "audio": "a.wav", "reference": "Codex PR", "terms": ["PR", "MCP"]})
                + "\n"
                + json.dumps({"id": "sample-002", "audio": "b.wav", "reference": "SeaTalk", "terms": ["SeaTalk", "MCP"]})
                + "\n",
                encoding="utf-8",
            )
            output = root / "hotwords.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/create_hotwords_config.py",
                    "--base-config",
                    str(base),
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(config["protected_terms"], ["Codex", "PR", "MCP", "SeaTalk"])
        self.assertEqual(config["replacements"], {"扣德克斯": "Codex"})

    def test_create_hotwords_config_accepts_replacement_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.json"
            base.write_text('{"protected_terms": [], "replacements": {}}', encoding="utf-8")
            manifest = root / "manifest.jsonl"
            manifest.write_text("", encoding="utf-8")
            output = root / "hotwords.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/create_hotwords_config.py",
                    "--base-config",
                    str(base),
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(output),
                    "--replacement",
                    "皮阿尔=PR",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(config["replacements"], {"皮阿尔": "PR"})

    def test_create_hotwords_config_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "hotwords.json"
            output.write_text("existing", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/create_hotwords_config.py",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("--force", completed.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_makefile_exposes_hotwords_config_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("hotwords-config:", makefile)
        self.assertIn("scripts/create_hotwords_config.py", makefile)


if __name__ == "__main__":
    unittest.main()
