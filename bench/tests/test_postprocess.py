import unittest
from pathlib import Path

from switchtype_bench.config import load_hotword_config
from switchtype_bench.postprocess import HotwordConfig, PostProcessor


class PostProcessorTests(unittest.TestCase):
    def test_replacements_and_whitespace(self):
        processor = PostProcessor(
            HotwordConfig(
                protected_terms=["Codex", "PR"],
                replacements={"扣德克斯": "Codex", "皮阿尔": "PR"},
            )
        )
        self.assertEqual(processor.process("  扣德克斯 的 皮阿尔  "), "Codex 的 PR")

    def test_ascii_token_spacing(self):
        processor = PostProcessor(HotwordConfig(protected_terms=["MCP"], replacements={}))
        self.assertEqual(processor.process("这个MCP server"), "这个 MCP server")

    def test_spaced_protected_acronyms_are_normalized(self):
        processor = PostProcessor(HotwordConfig(protected_terms=["PR", "CI", "MCP"], replacements={}))
        self.assertEqual(
            processor.process("这个 P R 的 C I 看一下，还有 M C P server"),
            "这个 PR 的 CI 看一下，还有 MCP server",
        )

    def test_example_hotwords_correct_recorded_preview_variants(self):
        processor = PostProcessor(load_hotword_config(Path("bench/config/hotwords.example.json")))

        examples = {
            "这个 MCPso在p one name上 say talk": ["MCP server", "prelive", "SeaTalk"],
            "帮我生成一个Code S Promote 让它修这个FLAG test": ["Codex prompt", "flaky test"],
            "把这个branchre倒，然后再跑一次smoke": ["branch rebase", "smoke test"],
            "这个公serv的P99来腾是在阳超里边搞了": ["Go service", "p99 latency"],
        }

        for raw, expected_terms in examples.items():
            with self.subTest(raw=raw):
                processed = processor.process(raw)
                for term in expected_terms:
                    self.assertIn(term, processed)

    def test_example_hotwords_do_not_duplicate_existing_smoke_test(self):
        processor = PostProcessor(load_hotword_config(Path("bench/config/hotwords.example.json")))

        self.assertEqual(processor.process("再跑一次 smoke test"), "再跑一次 smoke test")


if __name__ == "__main__":
    unittest.main()
