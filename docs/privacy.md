# Privacy

SwitchType is designed as a local-first voice typing tool.

## Audio

In v0.1, audio is recorded locally on the Mac while the configured hotkey is held. The app writes a temporary 16 kHz mono PCM WAV file, sends it to the configured local ASR engine, and removes the file after processing.

Audio is not sent to cloud ASR by SwitchType.

## Transcripts

Transcripts are generated locally. The final transcript is written to the clipboard and pasted into the active app.

Temporary ASR transcript files are removed after each transcription attempt, including failure paths where the local ASR process exits with an error after writing partial output.

Benchmark reports may include raw or processed transcript text. Review generated reports before committing or publishing them.

## Models and Engines

SwitchType invokes local ASR binaries configured by the user, such as `whisper.cpp`. Model files and third-party engine code are not committed to this repository.

Only run ASR binaries and models from sources you trust.

## Permissions

The macOS app requires:

- Microphone permission to record speech.
- Accessibility permission to observe the global hotkey and send paste events.

The app menu shows current permission status so users can confirm what has been granted.

## Local Files Ignored by Git

The repository ignores generated app bundles, local model binaries, local benchmark configs, audio recordings, and smoke-test audio outputs. This reduces the chance of publishing private speech data by accident.
