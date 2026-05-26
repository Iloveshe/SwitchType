# SwitchType Demo Guide

This guide defines the demo assets needed before publishing SwitchType on GitHub.

## Demo Story

The demo should show one complete workflow:

1. Open a text editor or browser text field.
2. Launch `dist/SwitchType.app`.
3. Hold `Option + Space`.
4. Say: `帮我看一下 Codex 的 PR issue 有没有过 CI`.
5. Release `Option + Space`.
6. Show the recognized text pasted into the active field.
7. Show the benchmark report with the same terms protected by the hotword config.

## Required Assets

- `docs/assets/demo-storyboard.svg`: static storyboard for README previews.
- `docs/assets/switchtype-demo.gif`: final screen recording for GitHub README.
- `bench/reports/real-asr.md`: final real local ASR benchmark report.
- `bench/reports/example.md`: generated fake-ASR smoke report for development only.

The GIF should be recorded after real local ASR is configured, because a demo with fake ASR would misrepresent the product.

## Recording Checklist

Before recording:

```bash
PYTHONPATH=bench python3 -m unittest discover -s bench/tests -v
swift build --package-path app/SwitchType
app/SwitchType/.build/debug/SwitchTypeCoreCheck
./scripts/package_app.sh
```

Manual setup:

1. Install or build `whisper.cpp`.
2. Place the selected model under `models/` or set `SWITCHTYPE_WHISPER_MODEL`.
3. Run `make hotwords-config` to create `~/.switchtype/hotwords.json` from the benchmark manifest terms.
4. Grant Microphone permission.
5. Grant Accessibility permission.
6. Run `dist/SwitchType.app`.
7. Verify `Option + Space` records and pastes into TextEdit.

Recommended final GIF length: 8-15 seconds. The automated strict check expects a real screen-recording-sized GIF: at least 10 KB and at least 640x360 pixels.

For early UI verification before the model exists, run `scripts/run_app_dev.sh --debug-transcript`. Do not use debug transcript mode for the final GIF.

## Static Preview

Use `docs/assets/demo-storyboard.svg` in the README until the real GIF exists. Replace it with `docs/assets/switchtype-demo.gif` only after a real ASR-backed app run is recorded.
