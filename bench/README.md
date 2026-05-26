# SwitchType Benchmark

The benchmark evaluates local ASR output against reference transcripts for Chinese-English developer dictation.

## Manifest Format

Each JSONL row describes one audio sample:

```json
{"id":"sample-001","audio":"bench/samples/audio/sample-001.wav","reference":"帮我看一下 Codex 的 PR issue 有没有过 CI","terms":["Codex","PR","issue","CI"]}
```

## Config Format

Engines are subprocess command templates. Tokens in braces are replaced by the runner.

- `{audio}`: input audio path
- `{output}`: temporary transcript output path
- `{output_without_suffix}`: transcript output path without extension, useful for `whisper.cpp -of`
- `{model}`: model path from config

Use `type: "fake"` for local smoke tests. Set heavyweight engines to `"enabled": false` until their local dependencies and models are installed.

To evaluate the official `Qwen/Qwen3-ASR-0.6B` model without changing the benchmark runner, start the local HTTP service and use the command-client config. The app uses the same service through `asr_http_profile: qwen3_official_local`.

```bash
python3.11 -m venv /private/tmp/switchtype-qwen3-venv
/private/tmp/switchtype-qwen3-venv/bin/pip install -r requirements-qwen3-asr.txt
QWEN_PYTHON=/private/tmp/switchtype-qwen3-venv/bin/python make qwen3-asr-server
PYTHONPATH=bench python3 bench/scripts/run_benchmark.py \
  --config bench/config/benchmark.qwen3-official.example.json \
  --hotwords bench/config/hotwords.example.json \
  --manifest bench/samples/doubao-shadow/manifest.jsonl \
  --report bench/reports/doubao-shadow-qwen3.md
```

## Commands

```bash
PYTHONPATH=bench python3 -m unittest discover -s bench/tests -v
PYTHONPATH=bench python3 bench/scripts/run_benchmark.py \
  --config bench/config/benchmark.example.json \
  --hotwords bench/config/hotwords.example.json \
  --manifest bench/samples/manifest.example.jsonl \
  --report bench/reports/example.md
```

Benchmark reports start with `## Run Metadata`, recording the generated time plus config, hotwords, manifest, and report paths for reproducibility. Use `--generated-at <value>` only when a deterministic example report is needed.

## Public Dataset Sanity Benchmark

Public Mandarin-English code-switching datasets such as [ASCEND](https://huggingface.co/datasets/CAiRE/ASCEND) or [BAAI/CS-Dialogue](https://huggingface.co/datasets/BAAI/CS-Dialogue) are useful for a reproducible Phase 1 benchmark and can be used before any personal recordings exist. Public audio does not verify the user's microphone, speaking style, personal technical terms, hotword corrections, or the macOS hotkey-to-paste workflow.
The curated source matrix is in [../docs/public-datasets.md](../docs/public-datasets.md).

For the fastest path, export mixed utterances from ASCEND directly:

```bash
./.venv/bin/pip install -r requirements-public.txt
make public-asr
make public-readiness
make public-summary
```

`make public-asr` downloads `CAiRE/ASCEND` through Hugging Face `datasets`, keeps rows where `language=mixed` by default, writes 16 kHz mono WAV files under ignored `bench/samples/public/audio/`, validates them, creates `bench/config/benchmark.local.json`, and writes `bench/reports/public-asr.md`. Override the defaults with `SWITCHTYPE_PUBLIC_LIMIT`, `SWITCHTYPE_PUBLIC_SPLIT`, `SWITCHTYPE_PUBLIC_TIMEOUT_SECONDS`, or the same `SWITCHTYPE_SENSEVOICE_*` variables used by the real benchmark. The default 900-second timeout is useful for first-run SenseVoice model downloads; after the model is cached, shorter timeouts are fine. `make public-readiness` verifies that the public manifest audio is readable and that the report covers the same sample IDs with at least two non-fake engines. `make public-summary` converts the ignored local report into `docs/public-benchmark.md`.

Download any permitted public dataset outside the repository, prepare a local CSV or TSV with columns `id`, `audio`, `reference`, and optional semicolon-separated `terms`, then import it:

```bash
make public-manifest SOURCE=/path/to/public-code-switch.csv LIMIT=50
make public-check
make public-benchmark CONFIG=bench/config/benchmark.local.json
```

For ASCEND-style Hugging Face exports with columns such as `id`, `path`, and `transcription`, map the column names:

```bash
make public-manifest \
  SOURCE=/path/to/ascend.csv \
  AUDIO_COLUMN=path \
  REFERENCE_COLUMN=transcription \
  LIMIT=50
make public-check
make public-benchmark CONFIG=bench/config/benchmark.local.json
```

For CS-Dialogue-style Kaldi indexes, point directly at `wav.scp` and `text`:

```bash
make public-manifest \
  WAV_SCP=/path/to/CS-Dialogue/data/index/short_wav/test/wav.scp \
  TEXT=/path/to/CS-Dialogue/data/index/short_wav/test/text \
  LIMIT=50
make public-check
make public-benchmark CONFIG=bench/config/benchmark.local.json
```

The importer writes `bench/samples/public/manifest.jsonl` by default, and the benchmark writes `bench/reports/public-asr.md` by default. Both paths are ignored because they contain local dataset paths and generated results. Do not commit third-party audio files. Treat this report as public benchmark evidence, not personal microphone or hotkey-to-paste evidence.

## Recording the 30-Sample Set

`bench/samples/manifest.30-template.jsonl` contains 30 Chinese-English developer prompts. Edit the references to match sentences you actually say, then record the audio files:

```bash
PYTHONPATH=bench python3 bench/scripts/validate_samples.py \
  --manifest bench/samples/manifest.30-template.jsonl \
  --expected-count 30

python3 bench/scripts/record_samples.py \
  --manifest bench/samples/manifest.30-template.jsonl \
  --seconds 8

EXPECT_DEVICE_NAME="DJI MIC MINI" make record-session
make record-devices
SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make record-check
SWITCHTYPE_FFMPEG_INPUT=:2 make record-session
make record-next
make real-benchmark-preview
make record-missing

PYTHONPATH=bench python3 bench/scripts/validate_samples.py \
  --manifest bench/samples/manifest.30-template.jsonl \
  --expected-count 30 \
  --require-audio
```

`make record-session` prints a status-aware command plan from the current manifest: first preview recording when no valid audio exists, partial preview benchmark plus next batch when some samples are valid, or the final real benchmark command once all 30 are valid.

The recorder uses `ffmpeg` first and falls back to `rec` from sox. Run `make record-devices` to list macOS avfoundation inputs, then set `SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make record-next` or pass `--ffmpeg-input-name "DJI MIC MINI"` to select a physical microphone by name. Run `SWITCHTYPE_FFMPEG_INPUT_NAME="DJI MIC MINI" make record-check` to verify the resolved input and next recorder command without capturing audio. You can also set `SWITCHTYPE_FFMPEG_INPUT=:2` or pass `--ffmpeg-input :2` if you prefer a raw avfoundation index. Use `SWITCHTYPE_FFMPEG_INPUT=:2 make record-session` when device-name resolution cannot list devices in the current terminal session. Run with `--dry-run` to preview prompts and commands without recording. Use `--missing-only` or `make record-missing` to resume a partial recording session; existing WAV files must be readable 16 kHz mono files, contain non-zero audio signal, and be at least `--min-duration` long, otherwise they are treated as invalid and recorded again.

After you press Return, the recorder counts down and reprints the full sentence in a `请读这句话：` block immediately before capture starts. The ffmpeg recorder runs with quiet logging so the prompt stays visible while you speak. Review and confirmation prompts are Chinese-first: `参考文本`, `保护词`, and `保留这条录音吗？`. Rejected recordings are retried once by default, so a silent or too-short first attempt does not stop the whole batch. Pass `--max-attempts 3` to allow more attempts for each prompt.

Use `make record-next` to record the next five missing or invalid samples. Override the batch size with `LIMIT=3 make record-next`. To re-record one sample, run `python3 bench/scripts/record_samples.py --sample-id sample-017`.

Track recording progress:

```bash
make sample-status
PYTHONPATH=bench python3 bench/scripts/sample_status.py --manifest bench/samples/manifest.30-template.jsonl --json
```

`sample_status.py` uses the same default 0.25s WAV minimum, non-silent signal check, and 16 kHz mono WAV format requirement as the recorder and the strict release gate. Existing files are reported as `valid`, `missing`, `too_short`, `silent`, `wrong_format`, or `unreadable`; only `valid` samples count as recorded.

To run ASR on the samples you have recorded so far, use:

```bash
make real-benchmark-preview
```

This writes `bench/samples/manifest.recorded-preview.jsonl` with only valid current recordings, runs the local ASR benchmark in partial mode, and writes `bench/reports/real-asr-preview.md`. Both files are ignored. The final release benchmark remains strict and still requires all 30 real samples.

### Doubao Cache Watcher

If Doubao input method is already running, you can watch for newly created temporary audio files while you use its voice input:

```bash
make watch-doubao-audio-start
make watch-doubao-audio-status
make watch-doubao-audio-stop
```

The watcher is conservative. It monitors Doubao's app-data/cache folders plus `$TMPDIR`, but in `$TMPDIR` it only inspects paths whose names look related to Doubao, ByteDance, ASR, voice, record, or speech. It copies only files whose header matches a known audio container such as WAV, M4A/MP4, CAF, Ogg, FLAC, MP3, AAC, AMR, or WebM. Captured files and the JSONL manifest are written under ignored path `bench/samples/doubao-capture/`.

Use this as an experiment to discover whether Doubao leaves local voice-input audio behind. It is not final release evidence unless the captured audio is reviewed, converted to the benchmark WAV format, matched to references, and validated like the normal 30-sample manifest.

To dig deeper when the conservative watcher captures nothing, run a short before/after probe while speaking one sentence with Doubao:

```bash
DURATION=20 make watch-doubao-audio-probe
```

The probe does not copy unknown files. It records metadata, the first bytes, and printable previews for files that were created or modified in Doubao app data, Doubao caches, HTTP storage, and `$TMPDIR`, then writes ignored reports to `bench/samples/doubao-capture/probe.json` and `bench/samples/doubao-capture/probe.md`. Treat these reports as private because they can include local paths and short header snippets. Use the Markdown summary to decide whether a changed file is a real audio/transcript source before adding it to the normal capture flow.

To inspect Doubao settings without waiting, listening for hotkeys, or recording, run:

```bash
make watch-doubao-settings-probe
```

The static settings probe scans Doubao settings/cache locations for visible strings related to voice input, shortcuts, modifiers, and hotkeys, then writes ignored private reports to `bench/samples/doubao-capture/settings-probe.json` and `bench/samples/doubao-capture/settings-probe.md`. The JSON includes `shortcut_hints` with readable ASR shortcut setting keys, nearby display values such as `Option`, parsed key codes/modifier flags, `suggested_hotkey_key_code`, `suggested_hotkey_modifiers`, and the candidate files that exposed them. Treat it as a hint only: if the shortcut is not clearly readable there, the explicit `TIMEOUT=30 make hotkey-probe-packaged` diagnostic is still the reliable way to identify the active shortcut.

### Doubao Shadow Recorder

When the cache watcher does not find reusable audio, use the explicit opt-in shadow recorder to capture your local microphone while you keep using Doubao normally:

```bash
make doubao-shadow-record
```

This builds and runs `SwitchTypeDoubaoShadow`, a small local helper that listens for the same hold-hotkey press/release pattern as Doubao but does not consume those hotkey events. The recommended daemon target defaults to Doubao's current long-press `Option` voice shortcut; modifier-only shortcuts accept either physical side of the same modifier, so left Option and right Option both match the default. Modifier-only shortcuts also poll the current system modifier state as a fallback, which helps when the global event tap does not deliver a flagsChanged event. Doubao still receives the shortcut and continues its normal voice-input flow. Each held hotkey segment is saved as a 16 kHz mono WAV under ignored path `bench/samples/doubao-shadow/audio/`, and metadata is appended to ignored `bench/samples/doubao-shadow/segments.jsonl`.

This mode is for deliberate local data collection, not hidden recording: you start it explicitly, it prints that it is armed, macOS still enforces Microphone and Accessibility permissions, and all captured files stay local. The segment log does not include a reference transcript yet, so these clips are not benchmark-ready until they are matched with the text Doubao inserted.

For a less interrupting long-running session, use the daemon wrapper. The `-auto` target is the recommended shadow mode while you keep using Doubao: it starts the background recorder and enables focused-text capture by default, so most clips can be matched with the text Doubao inserted without another prompt.

```bash
make doubao-shadow-preflight
make doubao-shadow-preflight-packaged-json
make doubao-shadow-start-auto
make app-request-permissions-packaged
make doubao-shadow-start-auto-packaged
make doubao-shadow-refresh-packaged-plan
make doubao-shadow-refresh-packaged-plan-json
make doubao-shadow-refresh-packaged
make doubao-shadow-restart-packaged
make doubao-shadow-can-hear-me
make doubao-shadow-can-hear-me-json
make doubao-shadow-status
make doubao-shadow-stop
make doubao-shadow-live-verify
make doubao-shadow-live-verify-plan
make doubao-shadow-live-verify-plan-json
make doubao-shadow-capture-once-packaged-plan
make doubao-shadow-capture-once-packaged-plan-json
make hotkey-probe-packaged-plan-json
make doubao-shadow-preview-transcripts
make doubao-shadow-review-sheet
make doubao-shadow-import-review
make doubao-shadow-reconcile-current-plan
make doubao-shadow-reconcile-current-plan-json
make doubao-shadow-reconcile-current
make doubao-shadow-reconcile-preview
```

`make doubao-shadow-preflight` does not record. It checks the shadow recorder binary, current Microphone/Accessibility permissions, expected input-device status, current shadow sample counts, and the next command before you start the background recorder. `make doubao-shadow-preflight-packaged-json` returns the same packaged checks as machine-readable JSON, including `shadow_hearing_status`, `mac_permissions`, `input_device`, `input_device_detail`, `permission_guidance`, `permission_targets`, `readiness_summary`, `preview`, `preview_is_executable_command`, `preview_requires_user_approval`, `preview_mutates_state`, `preview_requests_mac_permissions`, `preview_records_audio`, `next`, `next_is_executable_command`, `next_requires_user_approval`, `next_mutates_state`, `next_requests_mac_permissions`, `next_records_audio`, `recommended_command_plan`, `recommended_command_approval_reasons`, and `recommended_command_approval_summary`. `shadow_hearing_status` is the preflight-safe copy of the status message that answers whether the recorder can capture the next utterance now; `mac_permissions` is the structured Microphone/Accessibility state; `input_device` is the structured current/expected/status object, and `input_device_detail` reports the same packaged microphone state without making callers parse `checks`; `permission_targets` is the structured list of SwitchType/Codex/Terminal-style processes to grant when permissions are missing. `readiness_summary` rolls the preflight result into `primary_blocker`, `primary_blocker_detail`, `primary_recovery_command`, `primary_permission_target`, `permission_targets`, `blocked_by`, `user_action_required`, `safe_to_run_now`, and the recommended command's approval/state/permission/audio flags so UI code does not need to parse individual checks. When preflight checks fail, `readiness_summary.status` is `blocked`; any lower-level recorder status is preserved separately as `underlying_shadow_status` and `underlying_shadow_reason`. In the packaged workflow it also warns when `Packaged hotkey probe is stale`, which means `dist/SwitchType.app` should be refreshed before probe-based hotkey diagnosis is reliable. When the packaged preflight recommends `make doubao-shadow-refresh-packaged`, `recommended_command_plan` embeds the non-executing plan preview, `recommended_command_approval_reasons` exposes approval reasons as a flat list, and `recommended_command_approval_summary` exposes approval step counts, mutating steps, permission-prompt steps, and recording steps. For the packaged workflow, run `make package`, then `make app-request-permissions-packaged`, then `make doubao-shadow-start-auto-packaged`; these runtime targets reuse the existing `dist/SwitchType.app` instead of repackaging on every run, because replacing a local unsigned app can invalidate the macOS permission grant you just approved. If the packaged helper is stale while an old daemon is still running, `make doubao-shadow-refresh-packaged-plan` previews the recovery sequence without changing anything, `make doubao-shadow-refresh-packaged-plan-json` prints the same plan with top-level `command_mutates_state`, `command_requests_mac_permissions`, `command_records_audio`, `plan_mutates_state`, `plan_requests_mac_permissions`, `plan_records_audio`, legacy top-level `records_audio: false`, packaged `permission_targets`, and per-step `mutates_state`, `requests_mac_permissions`, `records_audio`, and `approval_reason` fields. `make doubao-shadow-refresh-packaged` runs it in order: stop the daemon, rebuild the package, request packaged permissions, then rerun packaged preflight. Use `make doubao-shadow-restart-packaged` to replace an older debug daemon with the packaged helper after preflight passes.

`readiness_summary` mirrors `recommended_command_approval_reasons` so automation that only consumes the summary can explain why the recovery command needs approval without parsing the full plan.

If you only want audio segments and plan to reconcile all text later, start the daemon without automatic text capture:

```bash
make doubao-shadow-start
make doubao-shadow-status
make doubao-shadow-stop
```

The daemon writes its pid and log under ignored `bench/samples/doubao-shadow/`. If you want to require a specific microphone, set `SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME`, for example `SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME="DJI MIC MINI" make doubao-shadow-start-auto`.

`readiness_summary` includes `primary_blocker`, `primary_blocker_detail`, `primary_recovery_command`, `preview_command`, `preview_safe_to_run_now`, `next_safe_command`, and `next_user_approval_command` when there is a safe non-mutating preview command to show before the approval-required recovery command. It also mirrors `next_role`, `pending_clip_action`, and `pending_clip_action_preview`, so automation that only consumes the summary can distinguish sample cleanup from the primary recovery command. When the latest captured segment was recorded before the current shadow recorder binary was built, `hearing_status.latest_segment_recorded_before_current_recorder_binary` is true and `blocked_by` includes `latest_segment_before_current_recorder_binary` so callers do not trust stale failure evidence.

`make doubao-shadow-refresh-packaged-plan` human output is generated from the same safe plan data as the JSON output. It prints `Primary permission target`, `approval_steps`, `permission_prompt_steps`, per-step safety flags, and each `approval_reason`, while still not stopping processes, rebuilding, requesting permissions, or recording.

`make doubao-shadow-live-verify-plan` and `make doubao-shadow-live-verify-plan-json` preview the live-verification step without waiting for speech, running ASR, writing files, requesting permissions, or recording. The JSON plan is also used in `recommended_command_plan` when the recommended command is `TIMEOUT=30 make doubao-shadow-live-verify`.

`make doubao-shadow-capture-once-packaged-plan` and `make doubao-shadow-capture-once-packaged-plan-json` preview the fixed-duration fallback without recording, writing files, running ASR, requesting permissions, or starting capture. When hotkey diagnostics show key events but no matching recording events, `recommended_command_plan` points to this JSON plan before the approval-required `DURATION=5 make doubao-shadow-capture-once-packaged` command.

`make hotkey-probe-packaged-plan` and `make hotkey-probe-packaged-plan-json` preview the packaged hotkey probe without listening for hotkeys, writing files, requesting permissions, or recording. Low-confidence `hotkey_repair_hint` output points to this JSON plan before the approval-required `TIMEOUT=30 make hotkey-probe-packaged` diagnostic.

`make doubao-shadow-can-hear-me` is the shortest read-only check for the question "can you hear my next Doubao utterance now?"; it prints yes/no/unknown, the hearing status message, the transcript visibility boundary, `Primary blocker`, `Primary recovery`, `Primary permission target`, the next action command, and whether that command needs user approval. When readable, it also prints a `Doubao settings shortcut hint` line from the static settings probe, including parsed `keyCode` and `modifiers` when available, plus whether the current shadow recorder hotkey matches those settings, so you can compare Doubao's configured ASR shortcut with the shadow recorder's event diagnosis. When audio-capture recovery differs from the action next, it also prints a separate `Capture diagnostic` command. When a packaged shadow helper is running, it also runs the read-only packaged preflight and prints the likely recovery command, current packaged preflight blockers, the current packaged macOS permission summary, the current packaged input device detail, permission guidance for the process that needs Microphone/Accessibility access, warnings such as a stale packaged hotkey probe, and the current packaged preflight preview/next command when known. `make doubao-shadow-can-hear-me-json` prints the same compact answer for automation as JSON, including `can_hear_next`, `effective_hearing_status`, `hearing_status`, `capture_readiness`, `doubao_settings_shortcut_hints` with `suggested_hotkey_key_code` and `suggested_hotkey_modifiers`, `shadow_hotkey_config_match`, `transcript_visibility`, `readiness_summary`, `primary_blocker`, `primary_blocker_detail`, `primary_permission_target`, `permission_targets`, `permission_guidance`, `primary_recovery_command`, `hotkey_repair_hint`, `hotkey_repair_deferred_until_permissions`, `next`, `next_role`, `next_is_executable_command`, `next_requires_user_approval`, `next_mutates_state`, `next_requests_mac_permissions`, `next_records_audio`, `pending_clip_action`, `pending_clip_action_preview`, `preflight_blockers`, `preflight_mac_permissions`, `preflight_input_device`, `preflight_input_device_detail`, `preflight_permission_guidance`, `preflight_permission_targets`, `preflight_warnings`, `preflight_next`, `preflight_next_mutates_state`, `preflight_next_requests_mac_permissions`, `preflight_next_records_audio`, `preflight_preview`, `preflight_preview_mutates_state`, `preflight_preview_requests_mac_permissions`, `preflight_preview_records_audio`, `recommended_command`, `recommended_command_approval_reasons`, `recommended_command_mutates_state`, `recommended_command_requests_mac_permissions`, `recommended_command_records_audio`, `recommended_command_plan`, and `recovery_command` with its approval and `recovery_records_audio` fields when a follow-up recovery is known. `effective_hearing_status` is the user-facing answer after packaged preflight blockers are applied; `hearing_status` preserves the lower-level recorder/hotkey state for debugging. `primary_blocker` is the single highest-priority blocker callers should surface first; for missing packaged permissions it is `packaged_permissions_denied`, with `primary_permission_target` set to the app/process to grant and `primary_recovery_command` set to `make doubao-shadow-refresh-packaged`. `readiness_summary` is the UI-friendly rollup with the same primary fields, `blocked_by`, `user_action_required`, `safe_to_run_now`, and the recommended command's approval/state/permission/audio flags, so callers do not need to parse every lower-level diagnostic. The permission guidance names SwitchType/Codex/Terminal-style hosts when those permissions are missing, not DoubaoIme. `recommended_command` is the single command a caller should surface first, chosen from the most specific available recovery hint; hotkey repair or hotkey-probe diagnostics take precedence over the audio-recording fallback, and `recommended_command_plan` embeds the safe read-only plan preview when that command has one. If `recommended_command` differs from a pending `make doubao-shadow-reconcile-current` action, `next_role` is `pending_clip_action` and automation should treat `pending_clip_action` plus `pending_clip_action_preview` as sample-cleanup work, not the primary blocker. `hotkey_repair_hint` is present when diagnostics saw ignored shortcut events; it includes the observed candidate, inferred modifiers, confidence, confidence reasons, caution text, a diagnostic command for low-confidence candidates, and a packaged restart command only when the candidate is high-confidence. When packaged permissions are currently blocked, `hotkey_repair_deferred_until_permissions` is true and the hint also sets `deferred_until_permissions` plus `role=secondary_after_permissions`, so callers can keep permission recovery as the primary action. Low-confidence candidates are reported without a restart command. `make doubao-shadow-status` reports the daemon process, whether the recorder can capture the next Doubao utterance, captured segment count, automatically captured references, current hotkey segments that still need reconciliation, legacy early-format segments that are still pending, latest segment age, latest local recorded time, and audio state, focused-text capture counts, hotkey event diagnostics when debug logging is enabled, benchmark manifest sample count, and the manifest audio readiness split (`valid`, `missing`, `too_short`, `unreadable`, `wrong_format`, `silent`). It separates total observed key events from hotkey recording events, so unrelated ignored keystrokes do not look like successful trigger detection. Use it after a recording session to decide whether the next step is `make doubao-shadow-reconcile-current`, more recording, or `make doubao-shadow-benchmark`. `make doubao-shadow-reconcile-current` skips legacy early-format segments and handles only current hotkey recordings. If the manifest already has at least one valid audio row, status prefers `make doubao-shadow-benchmark` even when older clips still need reconciliation; the benchmark target writes a valid-only preview manifest and runs partial mode. Use `make doubao-shadow-status-json` when automation needs the same status as machine-readable JSON, including `next_role`, `pending_clip_action`, `pending_clip_action_preview`, `next_is_executable_command`, `next_requires_user_approval`, `next_mutates_state`, `next_requests_mac_permissions`, `next_records_audio`, `live_verification_command_is_executable`, `live_verification_command_requires_user_approval`, `live_verification_command_mutates_state`, `live_verification_command_requests_mac_permissions`, `live_verification_command_records_audio`, `hotkey_repair_hint`, the matching `capture_readiness` fields, `hearing_status` for a direct "can it hear me now?" message, and `segments.latest.recorded_at_local` for local-time freshness checks. If a packaged shadow daemon has a stale latest clip and no observed hotkey events, `capture_readiness` points to `make doubao-shadow-preflight-packaged` so permissions and stale bundled helpers are checked before another wait; if existing current clips still need references, the action `next` can still prefer `make doubao-shadow-reconcile-current`. To answer "did the shadow recorder hear my next Doubao utterance?" after preflight passes, run `TIMEOUT=30 make doubao-shadow-live-verify`, then hold the Doubao voice shortcut and speak; it first checks that the recorder is running, waits for a new segment after the command starts, and prints a local ASR preview only for that new clip. The wait path does not rebuild Swift before listening; if a new clip is captured but preview fails, it still reports the captured segment. If the wait times out, it prints recorder status, configured hotkey, total hotkey event counts, hotkey event deltas for this wait window, latest segment age, latest audio state, and whether to enable hotkey diagnostics, run the packaged hotkey probe, or use the fixed-duration fallback.

`effective_hearing_status` is the user-facing can-hear-me answer after packaged preflight blockers are applied; `hearing_status` preserves the lower-level recorder/hotkey state for debugging.

If a sandboxed caller sees packaged preflight permission denials but the running packaged recorder has a recent valid clip from the current binary, `can-hear-me` keeps the user-facing status `armed` and prints those denials as `Current packaged preflight ignored blockers`; run `make doubao-shadow-preflight-packaged` outside the sandbox for the authoritative TCC permission check.

The human `make doubao-shadow-can-hear-me` output also prints a flat `Recommended command approval reasons` line, expands recommended refresh-plan steps, and prints each step's `approval_reason`. The JSON response exposes `recommended_command_approval_reasons` and `recommended_command_approval_summary` at the top level, and the plan JSON includes top-level `approval_summary` for step counts, mutating steps, permission-prompt steps, and recording steps.
If an ignored hotkey candidate conflicts with the readable Doubao settings hint, the human output prints `Hotkey repair settings conflict`, the JSON `hotkey_repair_hint` sets `settings_conflict` with the expected modifier display values, and `readiness_summary.blocked_by` includes `hotkey_candidate_conflicts_with_doubao_settings`.
The same human output prints `Next safe command` for a non-mutating preview step and `Next user-approval command` for the recovery command that needs explicit approval.
When packaged permissions are blocked, hotkey/capture checks and existing-clip cleanup are still shown as secondary work after permissions; human hotkey repair lines are labeled `Secondary hotkey repair`, JSON sets `secondary_diagnostics_deferred_until_permissions` and `pending_clip_cleanup_deferred_until_permissions`, and `readiness_summary.blocked_by` lists `microphone_permission_denied` / `accessibility_permission_denied` before lower-priority hotkey or stale-clip blockers so UI callers can avoid surfacing those paths as the primary action.

If the wait times out even though you held the Doubao shortcut, enable hotkey event diagnostics for one run:

```bash
SWITCHTYPE_DEBUG_HOTKEY_EVENTS=1 make doubao-shadow-restart-packaged
tail -f bench/samples/doubao-shadow/shadow.log
```

`Hotkey event:` lines show each observed key event or modifier polling state change and whether the recorder treated it as `startRecording`, `finishRecording`, `consumeOnly`, or `ignore`. `source=eventTap` means the global event tap saw the key event; `source=modifierPoll` means the fallback detected the current system modifier state. No event lines means neither path saw the shortcut; `action=ignore` means the configured key code or modifiers need to be updated. `make doubao-shadow-status` and `make doubao-shadow-can-hear-me` print a `Hotkey repair hint` for ignored candidates, and print a `Hotkey repair command` only for high-confidence candidates; otherwise use `make hotkey-probe-packaged`.

If `make doubao-shadow-status` or `TIMEOUT=30 make doubao-shadow-live-verify` shows key events but `Hotkey recording events: 0`, use the packaged fixed-duration fallback while the shortcut match is being diagnosed:

```bash
DURATION=5 make doubao-shadow-capture-once-packaged
```

Run it, use the default 2-second pre-record delay to focus the target text field and start Doubao voice input, speak during that fixed window, then let the wrapper print a local preview for the newest clip and return to `make doubao-shadow-status`. If recording fails or no new segment appears, it skips preview to avoid showing an old clip but still prints status. The fallback records through the packaged helper identity, does not rely on the shadow hotkey match, and enables focused-text capture by default so a successful Doubao insertion can be matched back to the clip. Override the setup delay with `PRE_DELAY=0` or `PRE_DELAY=4`.

To reduce manual reconciliation without the `-auto` target, enable focused text capture while using Doubao in a normal text field:

```bash
SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1 make doubao-shadow-start
```

With this opt-in flag, the shadow recorder keeps a recent idle focused-text snapshot, snapshots the focused text value before recording, waits briefly after the hotkey is released, snapshots it again, and writes the detected inserted text into the segment log as `reference` when the before/after diff is unambiguous. The idle snapshot reduces misses when Doubao or macOS temporarily changes focus as the hotkey starts. It still records only after you start the local daemon, and macOS Accessibility permission controls whether focused text can be read. If text capture is unavailable or ambiguous, the segment log records `text_capture_reason` and `make doubao-shadow-status` summarizes those reasons before `make doubao-shadow-reconcile` falls back to asking you to paste that segment's Doubao output.

If your Doubao voice shortcut is not long-press `Option`, set the key code and modifier list before starting the shadow recorder:

```bash
make hotkey-probe
make hotkey-probe-packaged
make hotkey-probe-packaged-plan-json
TIMEOUT=30 make hotkey-probe-packaged
```

The probe listens without consuming the shortcut and prints `SWITCHTYPE_HOTKEY_KEY_CODE` plus `SWITCHTYPE_HOTKEY_MODIFIERS` values for normal keys and modifier-only shortcuts you can copy into the shadow recorder command. Set `TIMEOUT=30` to return cleanly instead of waiting forever. Prefer `make hotkey-probe-packaged` when you are using `dist/SwitchType.app`, because it runs the helper from the same bundle as the packaged shadow recorder and uses the same macOS permission entry. If the packaged probe reports that the binary does not support `--timeout-seconds`, rebuild with `make package`, then refresh packaged permissions with `make app-request-permissions-packaged`.

```bash
SWITCHTYPE_HOTKEY_KEY_CODE=36 SWITCHTYPE_HOTKEY_MODIFIERS="control,shift" make doubao-shadow-start-auto
```

Supported modifier names are `option`, `control`, `shift`, and `command`.

After a shadow-recording session, pair any unresolved clips with Doubao's inserted text and run a preview benchmark:

```bash
make doubao-shadow-reconcile-current
make doubao-shadow-benchmark
```

`make doubao-shadow-preview-transcripts` writes ignored report `bench/reports/doubao-shadow-asr-preview.md` with one local ASR preview row per captured clip. Use it as an index for identifying clips, not as benchmark ground truth. For a batch review workflow, run `make doubao-shadow-review-sheet`, edit only the `reference` column in ignored TSV `bench/samples/doubao-shadow/review.tsv`, then run `make doubao-shadow-import-review` to create ignored benchmark manifest `bench/samples/doubao-shadow/manifest.jsonl`; the import step derives protected terms from the reviewed reference text and ignores ASR preview text. The review TSV also includes `audio_state`, `audio_duration_seconds`, `recording_stop_reason`, `text_capture_status`, and `text_capture_reason` so you can quickly filter valid clips and separate trusted captured text from clips that need manual review. `make doubao-shadow-reconcile-auto` is conservative: it only accepts automatically captured focused-text references after a safe stop reason and a local ASR-preview overlap check, so stale focused-text diffs stay out of the benchmark manifest. `make doubao-shadow-reconcile-current-plan` previews current hotkey reconciliation without writing the manifest, and `make doubao-shadow-reconcile-current-plan-json` prints the same read-only plan as JSON. `make doubao-shadow-reconcile-current` skips legacy early-format clips and prompts only for current hotkey recordings. `make doubao-shadow-reconcile` reads `segments.jsonl`, reuses any references already saved in `bench/samples/doubao-shadow/manifest.jsonl`, uses trusted automatically captured segment references when present, asks you to paste the matching Doubao output only for unresolved clips, auto-detects protected terms from `bench/config/hotwords.example.json`, and rewrites ignored `bench/samples/doubao-shadow/manifest.jsonl`. Use `make doubao-shadow-reconcile-preview` when you want a local ASR preview printed before each unresolved prompt. You can rerun reconciliation after later recording sessions without re-answering already reconciled segments. `make doubao-shadow-benchmark` first checks that captured audio, references, and valid WAV files are ready; if not, it prints the next command instead of entering the lower-level benchmark path. When ready, it writes ignored report `bench/reports/doubao-shadow-preview.md`. The shadow benchmark disables SenseVoice by default so this preview can run as a whisper.cpp-only local smoke check; set `SWITCHTYPE_ENABLE_SENSEVOICE=1` to opt into FunASR for this path.

## Real ASR Engines

The example config keeps heavyweight engines disabled so tests and smoke runs work without downloaded models.

To run `whisper.cpp`, install or build the binary, set its command path in the config, set the model path, and change `"enabled": false` to `"enabled": true`.

```bash
./scripts/bootstrap_whisper_cpp.sh large-v3-turbo
make asr-config
PYTHONPATH=bench python3 bench/scripts/create_local_config.py \
  --output bench/config/benchmark.local.json
```

If you already configured the macOS app with `~/.switchtype/asr.json`, the benchmark helpers read the same file. To use a different config for one run, pass `--asr-config /path/to/asr.json` to `create_local_config.py` or set `SWITCHTYPE_ASR_CONFIG=/path/to/asr.json` for `scripts/run_real_benchmark.sh`.

Use `--whisper-no-gpu` or `SWITCHTYPE_WHISPER_NO_GPU=1` with the helper scripts when `whisper.cpp` cannot initialize Metal/GPU in the current environment.

To run SenseVoice/FunASR, install its Python dependencies in your local environment, then enable the engine in the config with `--enable-sensevoice --sensevoice-python .venv/bin/python` or use the real benchmark helper, which enables SenseVoice by default and uses `.venv/bin/python` when it exists: `scripts/run_real_benchmark.sh`. Set `SWITCHTYPE_ENABLE_SENSEVOICE=0` only for whisper-only smoke work. The config calls `bench/scripts/run_sensevoice.py`, which wraps FunASR `AutoModel`, runs SenseVoiceSmall locally, and writes the transcript file used by the benchmark runner.

Use `make bootstrap-funasr` to create or update the local `.venv` from `requirements-sensevoice.txt`.

SenseVoice model downloads default to the ignored local cache `models/modelscope-cache/`. Set `SWITCHTYPE_MODELSCOPE_CACHE=/path/to/cache` to reuse another cache location.

Use `make hotwords-config` to generate `~/.switchtype/hotwords.json` from `bench/config/hotwords.example.json` plus the `terms` fields in `bench/samples/manifest.30-template.jsonl`. `scripts/run_real_benchmark.sh` uses this personal config automatically when it exists, and falls back to `bench/config/hotwords.example.json` otherwise. Set `SWITCHTYPE_HOTWORDS_CONFIG=/path/to/hotwords.json` to override it for one run.

If ModelScope is slow, use the Hugging Face fallback with `--sensevoice-model FunAudioLLM/SenseVoiceSmall --sensevoice-hub hf --sensevoice-vad-model none` in `create_local_config.py`, or set `SWITCHTYPE_SENSEVOICE_MODEL=FunAudioLLM/SenseVoiceSmall SWITCHTYPE_SENSEVOICE_HUB=hf SWITCHTYPE_SENSEVOICE_VAD_MODEL=none` for `scripts/run_real_benchmark.sh`. Hugging Face cache files are also stored below the same ignored cache directory.

The strict release gate requires at least two non-fake engines, with each engine covering every sample ID in `bench/samples/manifest.30-template.jsonl`.

## ASR Smoke Test

After `whisper.cpp` is installed, run:

```bash
make asr-smoke
```

This generates a synthetic macOS `say` sample and writes `bench/reports/asr-smoke.md`. Use it to check the local ASR command path before recording the real 30-sample benchmark. Do not use it as release evidence.

In restricted environments where `say` writes an empty audio file, the smoke script falls back to the `whisper.cpp` JFK sample when that source checkout is present.

To validate the complete 30-sample manifest path before recording personal audio, generate synthetic macOS `say` audio for every manifest row and run the local ASR benchmark:

```bash
make tts-manifest
make tts-benchmark
```

The generated manifest and WAV files stay under ignored `bench/samples/tts/`, and the report is written to ignored `bench/reports/tts-asr.md`. This is useful for catching broken references, hotwords, local ASR config, and report generation before the real recording session. It is not personal microphone evidence and must not be used for release accuracy claims.

In restricted sandboxed terminals, `say` may produce empty audio. Run the TTS manifest command from a normal macOS Terminal session when that happens.
