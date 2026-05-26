# Contributing to SwitchType

SwitchType is a local-first macOS voice typing tool for bilingual developer workflows.

## Development Setup

Run the standard local verification path:

```bash
make ci
```

Useful focused commands:

```bash
make test
make benchmark
make sample-check
make swift-check
make package
make readiness
```

## Real ASR Work

Real ASR changes should include:

- The ASR engine and model used.
- The manifest path.
- The generated benchmark report path.
- A short summary of CER, WER, latency, and technical-term accuracy.

Use:

```bash
./scripts/bootstrap_whisper_cpp.sh large-v3-turbo
scripts/run_real_benchmark.sh
```

Do not commit model binaries, recorded personal audio, local benchmark configs, generated app bundles, or private transcripts.

## App Workflow Work

App behavior changes should include manual verification notes:

- Microphone permission status.
- Accessibility permission status.
- App launch method.
- Input app used for paste verification.
- Spoken sentence and pasted output.
- Whether hotwords were preserved.

Use `docs/manual-app-verification.md` and `docs/verification-log.md` for release evidence.

## Pull Requests

Before opening a PR:

```bash
make ci
git status --short
```

Include verification output in the PR description. If a check cannot run locally, explain why and what evidence covers the same behavior.

