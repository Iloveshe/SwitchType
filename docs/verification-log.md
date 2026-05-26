# SwitchType Verification Log

Fill this in with real local evidence before marking the v0.1 goal complete.

## Benchmark Run

Expected successful values: `Audio sample count: 30/30 valid`, at least two non-fake ASR engines, `Report path: bench/reports/real-asr.md`, and a real benchmark command.

- Date:
- Machine:
- Manifest:
- Audio sample count:
- ASR engines:
- Report path:
- Command:

```bash
scripts/run_real_benchmark.sh
```

- Result summary:

## App Manual Verification

Expected successful values: `App build: dist/SwitchType-0.1.0.zip`, `Launch method: dist/SwitchType.app`, `Microphone permission: granted`, `Accessibility permission: granted`, a real `Hotword config path`, `Pasted output` preserving the protected terms from the spoken sentence, `Hotwords preserved: yes`, `Short recording rejected: yes`, and `Hotkey consumed: yes`.

- Date:
- App build: dist/SwitchType-0.1.0.zip
- Launch method: dist/SwitchType.app
- Microphone permission:
- Accessibility permission:
- Hotword config path:
- Input app:
- Spoken sentence:
- Pasted output:
- Hotwords preserved:
- Short recording rejected:
- Hotkey consumed:

## Demo Asset

Expected successful value: `Shows real ASR rather than debug transcript mode: yes`.

- GIF path:
- Recording command/tool:
- Duration:
- Shows real ASR rather than debug transcript mode:

## Final Readiness

```bash
python3 scripts/check_release_ready.py --strict
```

Expected successful value: `Result: strict readiness passed`.

- Result:
