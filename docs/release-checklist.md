# SwitchType Release Checklist

Use this checklist before claiming the full SwitchType v0.1 goal is complete.

## Public Benchmark Evidence

Use this path when you want release-quality benchmark evidence without recording personal audio.

- [ ] Install the optional public dataset dependency:

```bash
./.venv/bin/pip install -r requirements-public.txt
```

- [ ] Run the default ASCEND-based public benchmark:

```bash
make public-asr
```

- [ ] Confirm the public benchmark manifest audio and report agree:

```bash
make public-readiness
```

- [ ] Generate the publishable public benchmark snapshot:

```bash
make public-summary
```

- [ ] If using another permitted dataset, import it with `make public-manifest`, validate it with `make public-check`, run `make public-benchmark`, then rerun `make public-readiness`.

This evidence can compare local ASR engines on public Mandarin-English speech. It does not prove the user's microphone, accent, personal hotwords, or the full hotkey-to-paste UI path.

## Personal Benchmark Evidence

- [ ] Record 30 real user audio samples using `bench/samples/manifest.30-template.jsonl`.

```bash
EXPECT_DEVICE_NAME="DJI MIC MINI" make record-session
make record-devices
SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make record-check
SWITCHTYPE_FFMPEG_INPUT=:2 make record-session
make record-missing
```

Use `make record-session` first when resuming the release work; it reads the current manifest state and prints the correct next commands for first recording, partial preview benchmarking, or final benchmark readiness.

If the microphone is not ffmpeg avfoundation input `:0`, select it by name, for example `SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make record-missing`. You can still set a raw avfoundation input with `SWITCHTYPE_FFMPEG_INPUT=:2`; use `SWITCHTYPE_FFMPEG_INPUT=:2 make record-session` when device-name resolution cannot list devices in the current terminal session.

The recorder shows Chinese-first prompts while recording, including `请读这句话：`, `参考文本`, `保护词`, and `保留这条录音吗？`. It retries rejected samples once by default. For noisy setup work, run `python3 bench/scripts/record_samples.py --manifest bench/samples/manifest.30-template.jsonl --missing-only --max-attempts 3`.

- [ ] Confirm recording progress:

```bash
make sample-status
```

Only `valid` samples count as recorded. Re-record any sample shown as `missing`, `too_short`, `silent`, `wrong_format`, or `unreadable`.

- [ ] Optional: run a partial benchmark preview on valid recordings before the full 30-sample set is complete:

```bash
make real-benchmark-preview
```

This writes ignored local preview files at `bench/samples/manifest.recorded-preview.jsonl` and `bench/reports/real-asr-preview.md`. It is useful for checking ASR behavior while recording, but it is not final release evidence.

- [ ] Validate all 30 audio files:

```bash
PYTHONPATH=bench python3 bench/scripts/validate_samples.py \
  --manifest bench/samples/manifest.30-template.jsonl \
  --expected-count 30 \
  --require-audio
```

- [ ] Run `whisper.cpp` benchmark with a real model.
- [ ] Run a second non-fake local ASR engine, currently SenseVoice/FunASR, so the final report is an A/B comparison.
- [ ] Optional: run the ASR plumbing smoke test before the real benchmark:

```bash
make asr-smoke
make app-asr-smoke
make app-public-asr-smoke
make app-hotwords-smoke
```

- [ ] Generate the local benchmark config:

```bash
make bootstrap-funasr
```

```bash
PYTHONPATH=bench python3 bench/scripts/create_local_config.py \
  --output bench/config/benchmark.local.json \
  --enable-sensevoice \
  --sensevoice-python .venv/bin/python \
  --sensevoice-model FunAudioLLM/SenseVoiceSmall \
  --sensevoice-hub hf \
  --sensevoice-vad-model none
```

- [ ] Confirm `bench/reports/real-asr.md` contains `Run Metadata` for generated time, config, hotwords, manifest, and report paths; at least two non-fake engines; each engine covers all 30 manifest sample IDs exactly once; each non-fake sample row has valid numeric metrics; each non-fake transcript is non-empty; and Engine Summary counts/averages match the Sample Results rows.
- [ ] Save the final benchmark report under `bench/reports/`.
- [ ] Update the root README with the real benchmark summary.

The default one-command path is:

```bash
SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall \
SWITCHTYPE_SENSEVOICE_HUB=hf \
SWITCHTYPE_SENSEVOICE_VAD_MODEL=none \
scripts/run_real_benchmark.sh
```

## App Evidence

- [ ] Build the SwiftPM app:

```bash
swift build --disable-sandbox --package-path app/SwitchType
```

- [ ] Run the core executable check:

```bash
app/SwitchType/.build/debug/SwitchTypeCoreCheck
```

- [ ] Run the app-core ASR smoke test:

```bash
make app-asr-smoke
```

- [ ] Generate the personal hotword config from the benchmark manifest:

```bash
make hotwords-config
```

- [ ] Run the app doctor and confirm ASR paths, hotwords, permissions, and input-device status:

```bash
make app-permissions
make app-doctor
SWITCHTYPE_HOTWORDS_CONFIG="${SWITCHTYPE_HOTWORDS_CONFIG:-bench/config/hotwords.example.json}" \
  app/SwitchType/.build/debug/SwitchTypeDoctor --json
```

- [ ] Package the development app:

```bash
./scripts/package_app.sh
```

- [ ] Grant Microphone permission.
- [ ] Grant Accessibility permission.
- [ ] Confirm the app menu shows current Microphone and Accessibility status plus the expected audio input device name.
- [ ] Launch `dist/SwitchType.app`.
- [ ] Hold `Option + Space`, speak one technical sentence, release, and verify paste into TextEdit.
- [ ] Confirm a quick accidental tap shorter than 0.25 seconds is rejected and does not trigger ASR/paste.
- [ ] Confirm the trigger hotkey itself does not leave an extra space or character in TextEdit.
- [ ] Confirm the app loads hotwords from `SWITCHTYPE_HOTWORDS_CONFIG`, `~/.switchtype/hotwords.json`, or bundled resources.
- [ ] Complete the manual verification record in `docs/manual-app-verification.md`.
- [ ] Draft `docs/verification-log.md` from current evidence:

```bash
python3 scripts/update_verification_log.py \
  --app-date YYYY-MM-DD \
  --launch-method dist/SwitchType.app \
  --microphone-permission granted \
  --accessibility-permission granted \
  --hotword-config-path ~/.switchtype/hotwords.json \
  --input-app TextEdit \
  --spoken-sentence "..." \
  --pasted-output "..." \
  --hotwords-preserved yes \
  --short-recording-rejected yes \
  --hotkey-consumed yes \
  --recording-tool "..." \
  --gif-duration "..." \
  --real-asr-demo yes
```

- [ ] Or run the full evidence workflow with the same manual fields. Use `ARGS='--dry-run'` first to preview the commands. The ASR environment options are forwarded to the smoke checks, release input preflight, and real benchmark, and the verification log records the exact benchmark command. The workflow writes `Final Readiness/Result` after a pre-final strict check passes.

```bash
make release-evidence-template
make release-evidence ARGS='--whisper-bin third_party/whisper.cpp/build/bin/whisper-cli \
  --whisper-model third_party/whisper.cpp/models/ggml-large-v3-turbo.bin \
  --hotwords-config ~/.switchtype/hotwords.json \
  --funasr-python .venv/bin/python \
  --sensevoice-model FunAudioLLM/SenseVoiceSmall \
  --sensevoice-hub hf \
  --sensevoice-vad-model none \
  --app-date YYYY-MM-DD \
  --launch-method dist/SwitchType.app \
  --microphone-permission granted \
  --accessibility-permission granted \
  --hotword-config-path ~/.switchtype/hotwords.json \
  --input-app TextEdit \
  --spoken-sentence "..." \
  --pasted-output "..." \
  --hotwords-preserved yes \
  --short-recording-rejected yes \
  --hotkey-consumed yes \
  --recording-tool "..." \
  --gif-duration "..." \
  --real-asr-demo yes'
```

## GitHub Evidence

- [ ] `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, and `docs/privacy.md` are present.
- [ ] README explains install, model setup, benchmark usage, app usage, limitations, and roadmap.
- [ ] `docs/verification-log.md` contains the final benchmark, app, and demo evidence.
- [ ] Demo GIF exists at `docs/assets/switchtype-demo.gif`, is at least 10 KB, and is at least 640x360 pixels.
- [ ] `docs/demo.md` matches the final demo.
- [ ] Generated `.app` bundles and model binaries are not committed.
- [ ] `git status --short` is clean.

## Automated Readiness Check

Run the non-strict check during development:

```bash
make readiness
```

The default checker verifies files, generated artifacts, Python tests, and the Swift core executable check. Run `swift build --disable-sandbox --package-path app/SwitchType` and `./scripts/package_app.sh` separately first; launching SwiftPM from inside Python can fail in nested sandbox environments.

Use the preflight at any point to diagnose the current evidence gaps:

```bash
make release-inputs-preflight
make release-preflight
```

The inputs preflight checks only prerequisites that must exist before the final workflow can generate benchmark/log evidence: local ASR dependencies, real audio sample readiness, and the demo GIF. The full preflight also checks the real benchmark report, README benchmark summary, and verification log. Both are diagnostic only and do not create or fake any evidence.

After the real recordings, app manual verification details, and demo GIF are ready, preview or run the final evidence workflow:

```bash
python3 scripts/run_release_evidence.py --dry-run \
  --hotwords-config ~/.switchtype/hotwords.json \
  --funasr-python .venv/bin/python \
  --sensevoice-model FunAudioLLM/SenseVoiceSmall \
  --sensevoice-hub hf \
  --sensevoice-vad-model none \
  --app-date YYYY-MM-DD \
  --launch-method dist/SwitchType.app \
  --microphone-permission granted \
  --accessibility-permission granted \
  --hotword-config-path ~/.switchtype/hotwords.json \
  --input-app TextEdit \
  --spoken-sentence "..." \
  --pasted-output "..." \
  --hotwords-preserved yes \
  --short-recording-rejected yes \
  --hotkey-consumed yes \
  --recording-tool "..." \
  --gif-duration "..." \
  --real-asr-demo yes
```

The final evidence workflow runs `make release-inputs-preflight`, validates audio, optionally runs smoke checks, generates the real benchmark and README benchmark summary, packages the app, updates `docs/verification-log.md` without the final result, runs a pre-final strict check with only that field ignored, writes `Final Readiness/Result: strict readiness passed`, then runs `make release-preflight` and the strict readiness check.

Run the strict check only after real audio, real benchmark output, the final GIF, and a completed verification log exist:

```bash
python3 scripts/check_release_ready.py --strict
```
