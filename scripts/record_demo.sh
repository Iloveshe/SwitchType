#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
SwitchType demo recording steps

1. Verify the build and local ASR plumbing:
   PYTHONPATH=bench python3 -m unittest discover -s bench/tests -v
   CLANG_MODULE_CACHE_PATH=app/SwitchType/.build/clang-module-cache swift build --disable-sandbox --package-path app/SwitchType
   app/SwitchType/.build/debug/SwitchTypeCoreCheck
   ./scripts/package_app.sh
   make asr-smoke
   make app-asr-smoke

   If whisper.cpp fails during Metal/GPU initialization, verify the CPU path:
   SWITCHTYPE_WHISPER_NO_GPU=1 make asr-smoke
   SWITCHTYPE_WHISPER_NO_GPU=1 make app-asr-smoke

2. Configure real ASR for Finder/open launches:
   make asr-config
   make hotwords-config

   Example:
   {
     "whisper_bin": "/absolute/path/to/whisper.cpp/build/bin/whisper-cli",
     "whisper_model": "/absolute/path/to/ggml-large-v3-turbo.bin",
     "whisper_no_gpu": false,
     "timeout_seconds": 120
   }

   If Metal/GPU fails on this Mac, use:
   make asr-config ARGS='--no-gpu --timeout-seconds 300 --force'

   That writes:
   {
     "whisper_bin": "/absolute/path/to/whisper.cpp/build/bin/whisper-cli",
     "whisper_model": "/absolute/path/to/ggml-large-v3-turbo.bin",
     "whisper_no_gpu": true,
     "timeout_seconds": 300
   }

3. Launch the real app bundle:
   open dist/SwitchType.app

4. Grant Microphone and Accessibility permission. Do not use debug transcript mode for the final GIF.

5. Record an 8-15 second GIF showing:
   - TextEdit focused
   - hold Control + Shift
   - say: 帮我看一下 Codex 的 PR issue 有没有过 CI
   - release
   - final text pasted by real ASR

6. Save the result as:
   docs/assets/switchtype-demo.gif

7. After the real 30-sample benchmark also exists, update final evidence:
   make release-evidence ARGS='--asr-config ~/.switchtype/asr.json \
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
     --spoken-sentence "帮我看一下 Codex 的 PR issue 有没有过 CI" \
     --pasted-output "..." \
     --hotwords-preserved yes \
     --short-recording-rejected yes \
     --hotkey-consumed yes \
     --recording-tool "..." \
     --gif-duration "8-15s" \
     --real-asr-demo yes'

8. Final gate:
   python3 scripts/check_release_ready.py --strict
EOF
