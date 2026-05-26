# Manual App Verification

Use this guide to verify the macOS app workflow before real ASR models are installed, and again after `whisper.cpp` is configured.

## Debug Transcript Mode

This mode still verifies the app lifecycle, menu bar process, global hotkey, microphone recording path, technical-term post-processing, clipboard write, and Cmd-V paste. It bypasses only the ASR subprocess by returning a fixed transcript.

```bash
scripts/run_app_dev.sh --debug-transcript
```

Then:

1. Open TextEdit or any text field.
2. Grant Microphone permission if prompted.
3. Grant Accessibility permission if the hotkey or paste event is blocked.
4. Hold `Option + Space`.
5. Say anything for one or two seconds.
6. Release `Option + Space`.
7. Confirm this text is pasted:

```text
帮我看一下 Codex 的 PR issue 有没有过 CI
```

Also confirm the target text field did not receive an extra leading or trailing Option+Space character before the pasted output.

The debug transcript contains common ASR mistakes (`扣德克斯`, `皮阿尔`), so a successful paste also proves the hotword correction layer ran.

Quickly tap and release `Option + Space` for less than 0.25 seconds. Confirm the app rejects that accidental short recording and does not paste anything.

Before recording final evidence, run:

```bash
make app-permissions
make app-doctor
app/SwitchType/.build/debug/SwitchTypeDoctor --json
```

The JSON output is what `make release-preflight` uses to reject missing Microphone permission, missing Accessibility permission, or a mismatched expected input device.

## Real ASR Mode

After `whisper.cpp` and a model are available:

```bash
./scripts/bootstrap_whisper_cpp.sh large-v3-turbo
scripts/run_app_dev.sh
```

Then repeat the same TextEdit workflow and confirm the pasted text comes from your actual speech.

## Evidence to Capture

Record the result in `docs/release-checklist.md` before marking the release complete:

- Permission status: Microphone granted, Accessibility granted.
- App build: `dist/SwitchType-0.1.0.zip`.
- App launch method: `dist/SwitchType.app` for final release evidence. Debug transcript mode is only for development checks.
- Input app used for paste verification.
- Spoken sentence.
- Pasted output.
- Whether hotwords were preserved.
- Whether the short-recording rejection was verified.
- Whether the trigger hotkey was consumed without adding extra text.
