import unittest

from switchtype_bench.metrics import (
    char_error_rate,
    technical_term_accuracy,
    word_error_rate,
)


class MetricsTests(unittest.TestCase):
    def test_char_error_rate_for_chinese_text(self):
        self.assertAlmostEqual(char_error_rate("你好 Codex", "你好 Code"), 1 / 7)

    def test_word_error_rate_for_english_tokens(self):
        self.assertAlmostEqual(word_error_rate("open PR issue", "open issue"), 1 / 3)

    def test_technical_term_accuracy_counts_present_terms(self):
        score = technical_term_accuracy(["Codex", "PR", "MCP"], "Codex opened PR")
        self.assertEqual(score, {"matched": 2, "total": 3, "accuracy": 2 / 3})


if __name__ == "__main__":
    unittest.main()
