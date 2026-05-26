# Public Speech Data Sources

Use this page when the benchmark needs real speech before personal recordings exist.
Download third-party datasets outside this repository, import local paths into
`bench/samples/public/manifest.jsonl`, and keep the audio files uncommitted.

Public data is valid for Phase 1 ASR engine comparison. It is not evidence for
the user's microphone, accent, personal hotwords, or the macOS global hotkey to
paste workflow.

## Recommended Order

1. Start with ASCEND. It is small, public on Hugging Face, and already supported by `make public-asr`.
2. Add MagicHub Dev/Test only if a sign-in download and non-commercial/no-derivatives terms are acceptable.
3. Add CS-Dialogue when a much larger non-commercial Mandarin-English dialogue set is worth the 25 GB download.
4. Use Common Voice, AISHELL-1, and LibriSpeech as monolingual controls, not as code-switching evidence.

## Source Matrix

| Source | Best Use | Access | License Notes | Size / Duration |
|---|---|---|---|---|
| [CAiRE/ASCEND](https://huggingface.co/datasets/CAiRE/ASCEND) | Default Mandarin-English code-switch benchmark | Hugging Face `datasets` | CC-BY-SA 4.0 | 1.22 GB, 10.62 hours, ~12.3k utterances |
| [BAAI/CS-Dialogue](https://huggingface.co/datasets/BAAI/CS-Dialogue) | Larger spontaneous Mandarin-English dialogue benchmark | Hugging Face download | CC BY-NC-SA 4.0, non-commercial | 25.4 GB, 104.02 hours |
| [MagicHub ASR-DevCECoMiCSC](https://magichub.com/datasets/dev-set-of-chinese-english-code-mixing-conversational-speech-corpus/) | Mobile-recorded Mandarin with English phrases | Sign-in download | CC BY-NC-ND 4.0 / Magic Data terms | 715 MB, about 12 hours |
| [MagicHub ASR-SECoMiCSC](https://magichub.com/datasets/chinese-english-code-mixing-conversational-speech-corpus/) | Alternate held-out Mandarin-English conversational set | Sign-in download | CC BY-NC-ND 4.0 / Magic Data terms | 579 MB, about 10 hours |
| [Mozilla Common Voice zh-CN](https://mozilladatacollective.com/datasets/cmn3iaztg00e4mb070uvufz7q) | Mandarin monolingual control | Mozilla Data Collective | CC0-1.0, do not identify speakers or re-host the dataset | 21.38 GB, 1073.77 recorded hours |
| [Mozilla Common Voice English](https://mozilladatacollective.com/datasets/cmndapwry02jnmh07dyo46mot) | English monolingual control | Mozilla Data Collective | CC0-1.0, do not identify speakers or re-host the dataset | 87.84 GB, 3765.76 recorded hours |
| [AISHELL-1](https://www.openslr.org/33/) | Mandarin standard ASR baseline | OpenSLR | Apache License v2.0 | 15 GB speech archive |
| [LibriSpeech](https://www.openslr.org/12?version=1) | English standard ASR baseline | OpenSLR | CC BY 4.0 | dev/test subsets are ~300 MB each; full corpus about 1000 hours |

## Import Paths

For ASCEND, use the built-in path:

```bash
./.venv/bin/pip install -r requirements-public.txt
make public-asr
make public-readiness
make public-summary
```

For CSV or TSV exports with `id`, `audio`, `reference`, and optional `terms`:

```bash
make public-manifest SOURCE=/path/to/public-code-switch.csv LIMIT=50
make public-check
make public-benchmark CONFIG=bench/config/benchmark.local.json
```

For Kaldi-style indexes such as CS-Dialogue `wav.scp` plus `text`:

```bash
make public-manifest \
  WAV_SCP=/path/to/CS-Dialogue/data/index/short_wav/test/wav.scp \
  TEXT=/path/to/CS-Dialogue/data/index/short_wav/test/text \
  LIMIT=50
make public-check
make public-benchmark CONFIG=bench/config/benchmark.local.json
```

## Evidence Boundaries

Allowed claims from public data:

- `whisper.cpp` and SenseVoice/FunASR can be compared on reproducible public speech.
- The benchmark runner, metrics, post-processing, and report generation work.
- The Swift app-core transcription path can be smoke-tested with `make app-public-asr-smoke`.

Claims that still require personal or manual evidence:

- The selected physical microphone is the one being recorded.
- The user's accent, speaking speed, and technical vocabulary are handled well.
- Personal hotwords improve real dictation output.
- Holding `Option + Space` records, transcribes, and pastes into the active app.
- The final demo GIF shows the real local app workflow.
