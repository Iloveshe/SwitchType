import tempfile
import unittest
from pathlib import Path

from scripts.hotwords_config import resolve_hotwords_path


class HotwordsConfigTests(unittest.TestCase):
    def test_environment_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            resolved = resolve_hotwords_path(
                root,
                {"SWITCHTYPE_HOTWORDS_CONFIG": "custom/hotwords.json"},
                home=home,
            )

        self.assertEqual(resolved, root / "custom/hotwords.json")

    def test_personal_config_is_default_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            personal = home / ".switchtype/hotwords.json"
            personal.parent.mkdir(parents=True)
            personal.write_text("{}", encoding="utf-8")

            resolved = resolve_hotwords_path(root, {}, home=home)

        self.assertEqual(resolved, personal)

    def test_falls_back_to_repo_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"

            resolved = resolve_hotwords_path(root, {}, home=home)

        self.assertEqual(resolved, root / "bench/config/hotwords.example.json")


if __name__ == "__main__":
    unittest.main()
