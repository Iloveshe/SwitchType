# SwitchType Public Benchmark

This document is generated from a local public-dataset ASR run. It is useful for comparing local ASR engines before personal recordings exist, but it is not personal microphone evidence and does not verify the global hotkey-to-paste UI workflow.

## Dataset

- Default source: [CAiRE/ASCEND](https://huggingface.co/datasets/CAiRE/ASCEND), filtered to Mandarin-English `language=mixed` rows.
- Additional compatible sources: [BAAI/CS-Dialogue](https://huggingface.co/datasets/BAAI/CS-Dialogue), [MagicHub ASR-DevCECoMiCSC](https://magichub.com/datasets/dev-set-of-chinese-english-code-mixing-conversational-speech-corpus/), and [Mozilla Common Voice zh-CN](https://mozilladatacollective.com/datasets/cmn3iaztg00e4mb070uvufz7q) for monolingual Mandarin baseline work.
- Third-party audio files are not committed; generated audio and reports stay under ignored local paths.

## Reproduce

```bash
./.venv/bin/pip install -r requirements-public.txt
make public-asr
make public-readiness
make public-summary
```

## Snapshot

- Generated at: `2026-05-22T05:45:33+00:00`
- Config: `bench/config/benchmark.local.json`
- Hotwords: `bench/config/hotwords.example.json`
- Manifest: `bench/samples/public/manifest.jsonl`
- Source report: `bench/reports/public-asr.md`

## Engine Summary

| Engine | Samples | Avg Latency ms | Avg CER | Avg WER | Term Accuracy |
|---|---:|---:|---:|---:|---:|
| sensevoice_funasr | 30 | 6653.9 | 0.329 | 0.377 | 1.000 |
| whisper_cpp | 30 | 2104.2 | 0.504 | 0.448 | 1.000 |

## Interpretation

Use this table to decide which local ASR path is worth optimizing next. Treat the numbers as a reproducible smoke benchmark unless the sample count is large enough for the claim being made.
