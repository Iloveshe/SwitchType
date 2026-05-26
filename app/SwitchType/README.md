# SwitchType macOS App

This is the development SwiftPM version of the SwitchType menu bar app. It can be packaged as a locally signed `.app` bundle for manual testing.

## Build

```bash
swift build --disable-sandbox --package-path app/SwitchType
app/SwitchType/.build/debug/SwitchTypeCoreCheck
./scripts/package_app.sh
```

## Run

Development debug mode, useful before a real ASR model is installed:

```bash
scripts/run_app_dev.sh --debug-transcript
```

Real ASR development mode:

```bash
scripts/run_app_dev.sh
```

To enforce the expected microphone during app recording, set the input device name before launching. Recording is refused if the current system default input device is missing or does not match:

```bash
SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME="DJI MIC MINI" scripts/run_app_dev.sh
```

The main app default hold hotkey is long-press `Control+Shift`, so it does not collide with Doubao's long-press `Option` voice shortcut. To test a different hold shortcut, set the macOS key code and comma-separated modifiers before launching:

```bash
make hotkey-probe
make hotkey-probe-packaged
```

Use the packaged probe when debugging `dist/SwitchType.app` permission behavior.

```bash
SWITCHTYPE_HOTKEY_KEY_CODE=36 SWITCHTYPE_HOTKEY_MODIFIERS="control,shift" scripts/run_app_dev.sh
```

Supported modifier names are `option`, `control`, `shift`, and `command`.

The recommended Doubao shadow recorder path runs in the background and captures focused text diffs for benchmark reconciliation:

```bash
make doubao-shadow-start-auto
```

This is local and opt-in. It defaults to Doubao's current long-press `Option` voice shortcut, records local mic audio while that key is held, and depends on Accessibility permission for reading the focused text value. It compares post-recording text against both the immediate hotkey-start snapshot and a recent idle focused-text snapshot, so matching can survive transient focus changes at hotkey start. Missed focused-text matches are recorded with `text_capture_reason` so `make doubao-shadow-status` can show where matching failed.

For packaged app runs, prefer storing the same guard in `~/.switchtype/asr.json` with `expected_input_device_name` because Finder and `open` launches do not reliably inherit shell environment variables.

If `whisper.cpp` fails while initializing Metal/GPU, force CPU mode:

```bash
SWITCHTYPE_WHISPER_NO_GPU=1 scripts/run_app_dev.sh
```

Large local models can take longer on first run. Override the app ASR timeout when needed:

```bash
SWITCHTYPE_ASR_TIMEOUT_SECONDS=300 scripts/run_app_dev.sh
```

App-core ASR smoke test without launching the menu bar UI:

```bash
make app-permissions
make app-doctor
make app-asr-smoke
make app-public-asr-smoke
make app-hotwords-smoke
```

`make app-doctor` prints the same permission, expected input device, ASR config, and hotword status that the app uses.
`make app-public-asr-smoke` expects public ASCEND audio from `make public-asr` and runs the Swift app-core transcription path on mixed Chinese-English speech.
`make app-hotwords-smoke` bypasses ASR with a transcript override, loads the hotword JSON config, and verifies the Swift app-core correction layer preserves terms such as `Codex` and `PR`.

Unsigned app bundle:

```bash
make package
open dist/SwitchType.app
```

To enforce the expected microphone for a LaunchServices `.app` run, set the variable in the user launch environment before opening the bundle:

```bash
launchctl setenv SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME "DJI MIC MINI"
open dist/SwitchType.app
launchctl unsetenv SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME
```

For `.app` launches through `open` or Finder, create `~/.switchtype/asr.json` because LaunchServices may not pass shell environment variables into the app:

```bash
make asr-config
```

```json
{
  "asr_backend": "local_whisper",
  "local_whisper_profile": "custom",
  "whisper_bin": "/absolute/path/to/whisper.cpp/build/bin/whisper-cli",
  "whisper_model": "/absolute/path/to/ggml-large-v3-turbo.bin",
  "whisper_no_gpu": false,
  "whisper_language": "zh",
  "timeout_seconds": 120,
  "expected_input_device_name": "DJI MIC MINI"
}
```

The menu bar `ASR Backend` submenu switches `asr_backend` in this file and reloads the transcription workflow. The `Local Whisper Profile` submenu switches common local whisper model presets under the same file:

- `large_turbo`: `ggml-large-v3-turbo.bin`, GPU enabled, 120-second timeout.
- `base_cpu`: `ggml-base.bin`, CPU-only, 300-second timeout.
- `custom`: keep the explicit `whisper_*` fields from `asr.json`.

The `HTTP ASR Profile` submenu switches reusable HTTP model presets:

- `qwen3_official_local`: local official `Qwen/Qwen3-ASR-0.6B` HTTP service at `http://127.0.0.1:8765/transcribe`, multipart field `audio`, transcript key `text`, 180-second timeout.
- `custom`: keep the explicit `asr_http_*` fields from `asr.json`.

Supported ASR backends are:

- `local_whisper`: the built-in whisper.cpp runner.
- `command`: runs `asr_command_path` with `asr_command_args`; the command must print the transcript to stdout. Arguments can use `{audio}`, `{language}`, `{prompt}`, and `{model}` placeholders.
- `http_json`: uploads the WAV file as multipart form data to `asr_http_url`, then reads the transcript from `asr_http_transcript_key`.

Example command backend:

```json
{
  "asr_backend": "command",
  "asr_command_path": "/absolute/path/to/custom-asr-wrapper",
  "asr_command_args": ["--audio", "{audio}", "--language", "{language}", "--prompt", "{prompt}"],
  "whisper_language": "zh",
  "timeout_seconds": 120
}
```

Example HTTP backend:

```json
{
  "asr_backend": "http_json",
  "asr_http_profile": "custom",
  "asr_http_url": "https://asr.example.test/transcribe",
  "asr_http_headers": {
    "Authorization": "Bearer <token>"
  },
  "asr_http_field_name": "audio",
  "asr_http_transcript_key": "text",
  "timeout_seconds": 120
}
```

Official Qwen3-ASR validation uses the same HTTP backend without bundling the model into the app:

```bash
python3.11 -m venv /private/tmp/switchtype-qwen3-venv
/private/tmp/switchtype-qwen3-venv/bin/pip install -r requirements-qwen3-asr.txt
QWEN_PYTHON=/private/tmp/switchtype-qwen3-venv/bin/python make qwen3-asr-server
QWEN_PYTHON=/private/tmp/switchtype-qwen3-venv/bin/python make qwen3-asr-config
```

This starts a local service for `Qwen/Qwen3-ASR-0.6B` at `http://127.0.0.1:8765/transcribe` and points `~/.switchtype/asr.json` at it with `asr_http_profile: qwen3_official_local`. You can also choose `HTTP ASR Profile -> Qwen3-ASR Official (Local HTTP)` from the app menu after the service is running. Keep this as an experimental backend until the shadow benchmark proves accuracy and latency are good enough.

When the Qwen profile is selected, the app also exposes a `Qwen Server` submenu:

- `Check Qwen Server`: calls `/health` and reports `Running` or `Ready` with the current device map.
- `Start Local Qwen Server`: starts the local server through `launchctl` using `SWITCHTYPE_QWEN3_ASR_PYTHON` or `/private/tmp/switchtype-qwen3-venv/bin/python`.
- `Warm Up Qwen Server`: calls `/warmup` so the model is loaded before the first dictation.
- `Stop Local Qwen Server`: removes the `dev.switchtype.qwen3-asr` launchctl job.

App logs in `~/Library/Logs/SwitchType/app.log` include recording, audio size, HTTP body, HTTP roundtrip, post-processing, paste, and end-to-end latency lines. The Qwen server logs `qwen_asr_latency_ms` with upload parsing, temp-file write, model load, inference, total server time, device map, and dtype to `/private/tmp/switchtype-qwen3-asr-server.out.log`.

If Metal/GPU initialization fails, generate a CPU-only config:

```bash
make asr-config ARGS='--no-gpu --timeout-seconds 300 --force'
```

To generate the config with a persisted microphone guard:

```bash
make asr-config ARGS='--expected-input-device-name "DJI MIC MINI" --force'
```

The Python release and benchmark helpers read the same file, so `make release-inputs-preflight`, `scripts/run_real_benchmark.sh`, and `make release-evidence` use the same whisper.cpp paths unless you override them with environment variables or command flags.

## Permissions

The app needs:

- Microphone permission for recording.
- Accessibility permission for the global hotkey event tap and Cmd-V paste automation.

Run `make app-permissions` to open the relevant macOS Privacy & Security panes and print the follow-up commands. Run `make app-request-permissions` to ask macOS to show the Microphone and Accessibility prompts for the SwiftPM debug `SwitchTypeDoctor`; after `make package`, run `make app-request-permissions-packaged` when testing `dist/SwitchType.app` or the packaged Doubao shadow recorder. The packaged permission target reuses the existing app bundle so it does not replace the app while asking for permissions.
Run `make app-focused-text-doctor` with the target text field focused to verify whether the packaged helper can read `AXValue` and related focused-element attributes. Use `DELAY=3 make app-focused-text-doctor` when you need a few seconds to click back into the target input field.
The menu includes actions to request microphone permission, request Accessibility permission, and open Accessibility settings.
It also shows the current Microphone and Accessibility permission status plus the system default audio input device name. When `expected_input_device_name` or `SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME` is set, the same status line shows whether the expected input is matched, mismatched, or unavailable.

## Hotword Config

The app loads hotwords from the first available source:

1. `SWITCHTYPE_HOTWORDS_CONFIG`
2. `~/.switchtype/hotwords.json`
3. `hotwords.example.json` bundled in `dist/SwitchType.app`
4. The development repo path `../../bench/config/hotwords.example.json`

Environment paths may be absolute, relative to the launch working directory, or use `~` for the current user's home directory.
The JSON format matches `bench/config/hotwords.example.json`.
Generate a personal config from the 30-sample manifest when you are running the optional personal benchmark:

```bash
make hotwords-config
```

Add custom replacement rules with repeated `--replacement source=target` arguments:

```bash
make hotwords-config ARGS='--replacement 扣德克斯=Codex --force'
```

## Current Behavior

- Hold the configured hotkey to start recording. The main app default is long-press `Control+Shift`.
- Release the configured hotkey to stop recording.
- Recording uses temporary 16 kHz mono PCM WAV files for local ASR compatibility.
- When `SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME` is set, recording starts only if the current system default input device matches that name.
- Recordings shorter than 0.25 seconds are rejected and cleaned up before ASR runs.
- Matching hotkey events are consumed so the target text field does not receive the trigger keystroke.
- The app invokes a local whisper.cpp-compatible binary.
- The transcript is post-processed with developer hotwords.
- The final text is copied to the clipboard and pasted into the active app.

`./scripts/package_app.sh` creates a development-signed bundle at `dist/SwitchType.app` and a zip archive at `dist/SwitchType-0.1.0.zip`. A notarized release build is not part of the current v0.1 target. By default the script requires the `SwitchType Local Development` codesigning identity so Microphone and Accessibility permissions stay stable across rebuilds. Run `./scripts/create_local_codesign_identity.sh` and `make package` outside the sandbox when refreshing the app. For throwaway builds only, explicitly set `SWITCHTYPE_CODESIGN_IDENTITY=-` to use ad-hoc signing.

Manual app verification steps are documented in `docs/manual-app-verification.md`.

The public benchmark path does not require personal recordings. A personal release that claims microphone and hotkey-to-paste behavior still needs real-ASR GUI verification in `docs/verification-log.md` and the final demo GIF at `docs/assets/switchtype-demo.gif`.

## Verification Note

This machine currently has Command Line Tools without the full Xcode XCTest module. `SwitchTypeCoreCheck` is a SwiftPM executable check that validates core post-processing without XCTest. In sandboxed environments, running the built executable directly can be more reliable than `swift run` because it avoids user-level SwiftPM cache writes.
