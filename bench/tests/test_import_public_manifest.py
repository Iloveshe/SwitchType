import json
import tempfile
import unittest
from pathlib import Path

from bench.scripts.import_public_manifest import DelimitedColumns, import_kaldi_manifest, import_manifest


class ImportPublicManifestTests(unittest.TestCase):
    def test_makefile_exposes_public_manifest_and_benchmark_targets(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("public-manifest:", makefile)
        self.assertIn("bench/scripts/import_public_manifest.py", makefile)
        self.assertIn('SOURCE:+--source "$$SOURCE"', makefile)
        self.assertIn('AUDIO_COLUMN:+--audio-column "$$AUDIO_COLUMN"', makefile)
        self.assertIn('REFERENCE_COLUMN:+--reference-column "$$REFERENCE_COLUMN"', makefile)
        self.assertIn('WAV_SCP:+--wav-scp "$$WAV_SCP"', makefile)
        self.assertIn('TEXT:+--text "$$TEXT"', makefile)
        self.assertIn("public-check:", makefile)
        self.assertIn("$${MANIFEST:-bench/samples/public/manifest.jsonl}", makefile)
        self.assertIn("--require-audio", makefile)
        self.assertIn("public-benchmark:", makefile)
        self.assertIn("bench/samples/public/manifest.jsonl", makefile)
        self.assertIn("bench/reports/public-asr.md", makefile)

    def test_imports_csv_rows_to_switchtype_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "public.csv"
            source.write_text(
                "id,audio,reference,terms\n"
                "ascend-001,/datasets/ascend/wav/utt001.wav,帮我 review Codex PR,\"Codex;PR\"\n"
                "ascend-002,/datasets/ascend/wav/utt002.wav,这个 MCP server timeout,\"MCP;server;timeout\"\n",
                encoding="utf-8",
            )
            output = root / "manifest.jsonl"

            count = import_manifest(source=source, output=output, limit=1)

            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual(
                rows,
                [
                    {
                        "id": "ascend-001",
                        "audio": "/datasets/ascend/wav/utt001.wav",
                        "reference": "帮我 review Codex PR",
                        "terms": ["Codex", "PR"],
                    }
                ],
            )

    def test_imports_custom_columns_from_huggingface_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ascend.csv"
            source.write_text(
                "id,path,transcription,language\n"
                "00001,/datasets/ascend/waves/00001.wav,嗯hello我的名字叫徐妍,mixed\n",
                encoding="utf-8",
            )
            output = root / "manifest.jsonl"

            count = import_manifest(
                source=source,
                output=output,
                columns=DelimitedColumns(audio="path", reference="transcription"),
            )

            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 1)
            self.assertEqual(
                rows,
                [
                    {
                        "id": "00001",
                        "audio": "/datasets/ascend/waves/00001.wav",
                        "reference": "嗯hello我的名字叫徐妍",
                        "terms": [],
                    }
                ],
            )

    def test_imports_kaldi_wav_scp_and_text_to_switchtype_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav_scp = root / "wav.scp"
            wav_scp.write_text(
                "utt001 /datasets/cs-dialogue/short_wav/dev/utt001.wav\n"
                "utt002 /datasets/cs-dialogue/short_wav/dev/utt002.wav\n"
                "utt003 /datasets/cs-dialogue/short_wav/dev/utt003.wav\n",
                encoding="utf-8",
            )
            text = root / "text"
            text.write_text(
                "utt001 帮我看一下 Codex PR\n"
                "utt002 这个 MCP server timeout\n"
                "utt004 没有音频的转写要跳过\n",
                encoding="utf-8",
            )
            output = root / "manifest.jsonl"

            count = import_kaldi_manifest(wav_scp=wav_scp, text=text, output=output, limit=2)

            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(count, 2)
            self.assertEqual(
                rows,
                [
                    {
                        "id": "utt001",
                        "audio": "/datasets/cs-dialogue/short_wav/dev/utt001.wav",
                        "reference": "帮我看一下 Codex PR",
                        "terms": [],
                    },
                    {
                        "id": "utt002",
                        "audio": "/datasets/cs-dialogue/short_wav/dev/utt002.wav",
                        "reference": "这个 MCP server timeout",
                        "terms": [],
                    },
                ],
            )

    def test_rejects_kaldi_import_with_empty_text_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav_scp = root / "wav.scp"
            wav_scp.write_text("utt001 /datasets/utt001.wav\n", encoding="utf-8")
            text = root / "text"
            text.write_text("", encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                import_kaldi_manifest(wav_scp=wav_scp, text=text, output=root / "manifest.jsonl")

            self.assertIn("No transcript rows found", str(raised.exception))

    def test_rejects_source_without_required_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "public.csv"
            source.write_text("id,audio,text\nutt001,a.wav,hello\n", encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                import_manifest(source=source, output=root / "manifest.jsonl")

            self.assertIn("Missing required column(s): reference", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
