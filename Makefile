.PHONY: test benchmark public-asr public-ascend public-manifest public-check public-benchmark public-readiness public-summary tts-manifest tts-benchmark sample-check sample-status record-session record-devices record-check record-missing record-next record-preview real-benchmark-preview watch-doubao-audio watch-doubao-audio-probe watch-doubao-settings-probe watch-doubao-audio-start watch-doubao-audio-status watch-doubao-audio-stop hotkey-probe hotkey-probe-packaged hotkey-probe-packaged-plan hotkey-probe-packaged-plan-json doubao-shadow-record doubao-shadow-record-seconds doubao-shadow-record-seconds-packaged doubao-shadow-record-seconds-auto-packaged doubao-shadow-capture-once-packaged doubao-shadow-capture-once-packaged-plan doubao-shadow-capture-once-packaged-plan-json doubao-shadow-preflight doubao-shadow-preflight-json doubao-shadow-preflight-packaged doubao-shadow-preflight-packaged-json doubao-shadow-refresh-packaged-plan doubao-shadow-refresh-packaged-plan-json doubao-shadow-refresh-packaged doubao-shadow-start doubao-shadow-start-packaged doubao-shadow-start-auto doubao-shadow-start-auto-packaged doubao-shadow-restart-packaged doubao-shadow-can-hear-me doubao-shadow-can-hear-me-json doubao-shadow-status doubao-shadow-status-json doubao-shadow-stop doubao-shadow-reconcile doubao-shadow-reconcile-current doubao-shadow-reconcile-current-plan doubao-shadow-reconcile-current-plan-json doubao-shadow-reconcile-plan doubao-shadow-reconcile-plan-json doubao-shadow-reconcile-auto doubao-shadow-reconcile-preview doubao-shadow-latest-preview doubao-shadow-live-verify doubao-shadow-live-verify-plan doubao-shadow-live-verify-plan-json doubao-shadow-wait-next-preview doubao-shadow-preview-transcripts doubao-shadow-review-sheet doubao-shadow-import-review doubao-shadow-benchmark qwen3-asr-server qwen3-asr-config qwen3-asr-client verification-log bootstrap-funasr asr-config hotwords-config release-inputs-preflight release-preflight release-evidence release-evidence-template swift-build swift-check package ci-package ensure-packaged-app readiness ci real-benchmark app-permissions app-request-permissions app-request-permissions-packaged app-focused-text-doctor app-doctor asr-smoke app-asr-smoke app-public-asr-smoke app-hotwords-smoke

PYTHONPATH := bench
QWEN_PYTHON ?= python3
SWIFT_CACHE := $(CURDIR)/app/SwitchType/.build/clang-module-cache
SWIFT_BUILD := CLANG_MODULE_CACHE_PATH=$(SWIFT_CACHE) swift build --disable-sandbox --package-path app/SwitchType

test:
	PYTHONPATH=$(PYTHONPATH) python3 -m unittest discover -s bench/tests -v

benchmark:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_benchmark.py \
		--config bench/config/benchmark.example.json \
		--hotwords bench/config/hotwords.example.json \
		--manifest bench/samples/manifest.example.jsonl \
		--report bench/reports/example.md \
		--generated-at example

public-asr:
	./scripts/run_public_benchmark.sh

public-ascend:
	PYTHONPATH=$(PYTHONPATH) $${PYTHON:-python3} bench/scripts/prepare_ascend_public_samples.py \
		--split $${SPLIT:-test} \
		--limit $${LIMIT:-50} \
		--manifest $${MANIFEST:-bench/samples/public/manifest.jsonl} \
		--audio-dir $${AUDIO_DIR:-bench/samples/public/audio} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		$${INCLUDE_ALL_LANGUAGES:+--include-all-languages}

public-manifest:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/import_public_manifest.py \
		$${SOURCE:+--source "$$SOURCE"} \
		$${ID_COLUMN:+--id-column "$$ID_COLUMN"} \
		$${AUDIO_COLUMN:+--audio-column "$$AUDIO_COLUMN"} \
		$${REFERENCE_COLUMN:+--reference-column "$$REFERENCE_COLUMN"} \
		$${TERMS_COLUMN:+--terms-column "$$TERMS_COLUMN"} \
		$${WAV_SCP:+--wav-scp "$$WAV_SCP"} \
		$${TEXT:+--text "$$TEXT"} \
		--output $${OUTPUT:-bench/samples/public/manifest.jsonl} \
		$${LIMIT:+--limit $$LIMIT}

public-check:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/validate_samples.py \
		--manifest $${MANIFEST:-bench/samples/public/manifest.jsonl} \
		--require-audio \
		$${EXPECTED_COUNT:+--expected-count $$EXPECTED_COUNT}

public-benchmark:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_benchmark.py \
		--config $${CONFIG:-bench/config/benchmark.local.json} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		--manifest $${MANIFEST:-bench/samples/public/manifest.jsonl} \
		--report $${REPORT:-bench/reports/public-asr.md}

public-readiness:
	python3 scripts/check_public_benchmark_ready.py

public-summary:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/update_public_benchmark_doc.py

tts-manifest:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/create_tts_smoke_sample.py \
		--source-manifest $${SOURCE_MANIFEST:-bench/samples/manifest.30-template.jsonl} \
		--manifest $${MANIFEST:-bench/samples/tts/manifest.jsonl} \
		--audio-dir $${AUDIO_DIR:-bench/samples/tts/audio} \
		$${LIMIT:+--limit $$LIMIT}

tts-benchmark:
	./scripts/run_tts_manifest_benchmark.sh

sample-check:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/validate_samples.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--expected-count 30

sample-status:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/sample_status.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--all

record-session:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/recording_session.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		$${EXPECT_DEVICE_NAME:+--device-name "$$EXPECT_DEVICE_NAME"} \
		$${SWITCHTYPE_FFMPEG_INPUT:+--ffmpeg-input "$$SWITCHTYPE_FFMPEG_INPUT"}

record-devices:
	python3 bench/scripts/record_samples.py --list-devices \
		$${EXPECT_DEVICE_NAME:+--expect-device-name "$$EXPECT_DEVICE_NAME"}

record-check:
	python3 bench/scripts/record_samples.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--missing-only \
		--limit $${LIMIT:-1} \
		--dry-run

record-missing:
	python3 bench/scripts/record_samples.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--missing-only

record-next:
	python3 bench/scripts/record_samples.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--missing-only \
		--limit $${LIMIT:-5}

record-preview:
	python3 bench/scripts/record_samples.py \
		--manifest bench/samples/manifest.30-template.jsonl \
		--missing-only \
		--limit $${LIMIT:-1} \
		--preview-asr

verification-log:
	python3 scripts/update_verification_log.py

bootstrap-funasr:
	./scripts/bootstrap_funasr.sh

asr-config:
	python3 scripts/create_asr_config.py $(ARGS)

qwen3-asr-server:
	$(QWEN_PYTHON) scripts/qwen3_asr_server.py \
		--host $${HOST:-127.0.0.1} \
		--port $${PORT:-8765} \
		--model $${MODEL:-Qwen/Qwen3-ASR-0.6B} \
		--language $${LANGUAGE:-Chinese} \
		--device-map $${DEVICE_MAP:-cpu} \
		--dtype $${DTYPE:-auto}

qwen3-asr-config:
	$(QWEN_PYTHON) scripts/create_qwen3_asr_http_config.py \
		--url $${URL:-http://127.0.0.1:8765/transcribe} \
		--timeout-seconds $${TIMEOUT:-180}

qwen3-asr-client:
	$(QWEN_PYTHON) scripts/qwen3_asr_client.py \
		--url $${URL:-http://127.0.0.1:8765/transcribe} \
		$${AUDIO:?set AUDIO=/path/to/audio.wav}

hotwords-config:
	python3 scripts/create_hotwords_config.py $(ARGS)

release-preflight:
	python3 scripts/release_preflight.py

release-inputs-preflight:
	python3 scripts/release_preflight.py --inputs-only

release-evidence:
	python3 scripts/run_release_evidence.py $(ARGS)

release-evidence-template:
	python3 scripts/run_release_evidence.py --template \
		$${APP_DATE:+--app-date "$$APP_DATE"}

swift-build:
	$(SWIFT_BUILD)

swift-check: swift-build
	app/SwitchType/.build/debug/SwitchTypeCoreCheck

package: swift-build
	./scripts/package_app.sh
	plutil -lint dist/SwitchType.app/Contents/Info.plist
	test -f dist/SwitchType-0.1.0.zip

ensure-packaged-app:
	@test -x dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow || { echo "Missing packaged shadow recorder. Run: make package"; exit 1; }
	@test -x dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor || { echo "Missing packaged doctor. Run: make package"; exit 1; }
	@test -x dist/SwitchType.app/Contents/MacOS/SwitchTypeHotkeyProbe || { echo "Missing packaged hotkey probe. Run: make package"; exit 1; }

readiness:
	python3 scripts/check_release_ready.py

ci-package:
	SWITCHTYPE_CODESIGN_IDENTITY=- $(MAKE) package

ci: test benchmark sample-check swift-check ci-package readiness

real-benchmark:
	./scripts/run_real_benchmark.sh

real-benchmark-preview:
	./scripts/run_recorded_benchmark_preview.sh

watch-doubao-audio:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py

watch-doubao-audio-probe:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py --probe --duration-seconds $${DURATION:-20}

watch-doubao-settings-probe:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py --settings-probe

watch-doubao-audio-start:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py --daemon

watch-doubao-audio-status:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py --status

watch-doubao-audio-stop:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/watch_doubao_audio.py --stop

hotkey-probe: swift-build
	TIMEOUT=$${TIMEOUT:-0}; PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_hotkey_probe.py \
		--binary app/SwitchType/.build/debug/SwitchTypeHotkeyProbe \
		--timeout-seconds $$TIMEOUT \
		--package-command "make hotkey-probe"

hotkey-probe-packaged: ensure-packaged-app
	TIMEOUT=$${TIMEOUT:-0}; PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_hotkey_probe.py \
		--binary dist/SwitchType.app/Contents/MacOS/SwitchTypeHotkeyProbe \
		--timeout-seconds $$TIMEOUT \
		--package-command "make package"

hotkey-probe-packaged-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/hotkey_probe_plan.py --human

hotkey-probe-packaged-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/hotkey_probe_plan.py

doubao-shadow-record: swift-build
	mkdir -p bench/samples/doubao-shadow/audio
	app/SwitchType/.build/debug/SwitchTypeDoubaoShadow \
		--output-dir bench/samples/doubao-shadow/audio \
		--segments bench/samples/doubao-shadow/segments.jsonl \
		$${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:+--expected-input-device "$$SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"} \
		$${SWITCHTYPE_HOTKEY_KEY_CODE:+--hotkey-key-code "$$SWITCHTYPE_HOTKEY_KEY_CODE"} \
		$${SWITCHTYPE_HOTKEY_MODIFIERS:+--hotkey-modifiers "$$SWITCHTYPE_HOTKEY_MODIFIERS"} \
		$${SWITCHTYPE_CAPTURE_FOCUSED_TEXT:+--capture-focused-text} \
		$${SWITCHTYPE_DEBUG_HOTKEY_EVENTS:+--debug-hotkey-events} \
		$${SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS:+--text-capture-delay-seconds "$$SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"} \
		$${SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS:+--text-capture-timeout-seconds "$$SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"}

doubao-shadow-record-seconds: swift-build
	mkdir -p bench/samples/doubao-shadow/audio
	app/SwitchType/.build/debug/SwitchTypeDoubaoShadow \
		--record-seconds $${DURATION:-5} \
		--pre-record-delay-seconds $${PRE_DELAY:-2} \
		--output-dir bench/samples/doubao-shadow/audio \
		--segments bench/samples/doubao-shadow/segments.jsonl \
		$${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:+--expected-input-device "$$SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"} \
		$${SWITCHTYPE_CAPTURE_FOCUSED_TEXT:+--capture-focused-text} \
		$${SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS:+--text-capture-delay-seconds "$$SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"} \
		$${SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS:+--text-capture-timeout-seconds "$$SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"}

doubao-shadow-record-seconds-packaged: ensure-packaged-app
	mkdir -p bench/samples/doubao-shadow/audio
	dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow \
		--record-seconds $${DURATION:-5} \
		--pre-record-delay-seconds $${PRE_DELAY:-2} \
		--output-dir bench/samples/doubao-shadow/audio \
		--segments bench/samples/doubao-shadow/segments.jsonl \
		$${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:+--expected-input-device "$$SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"} \
		$${SWITCHTYPE_CAPTURE_FOCUSED_TEXT:+--capture-focused-text} \
		$${SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS:+--text-capture-delay-seconds "$$SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"} \
		$${SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS:+--text-capture-timeout-seconds "$$SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"}

doubao-shadow-record-seconds-auto-packaged:
	SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1 \
	DURATION=$${DURATION:-5} \
	PRE_DELAY=$${PRE_DELAY:-2} \
	$(MAKE) doubao-shadow-record-seconds-packaged

doubao-shadow-capture-once-packaged:
	MAKE="$(MAKE)" PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_doubao_shadow_capture_once.py

doubao-shadow-capture-once-packaged-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_capture_once_plan.py --human

doubao-shadow-capture-once-packaged-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_capture_once_plan.py

doubao-shadow-preflight: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_preflight.py \
		--binary app/SwitchType/.build/debug/SwitchTypeDoubaoShadow \
		--doctor app/SwitchType/.build/debug/SwitchTypeDoctor \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--min-duration $${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25}

doubao-shadow-preflight-json: swift-build
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_preflight.py \
		--binary app/SwitchType/.build/debug/SwitchTypeDoubaoShadow \
		--doctor app/SwitchType/.build/debug/SwitchTypeDoctor \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--min-duration $${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25} \
		--json

doubao-shadow-preflight-packaged: ensure-packaged-app
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_preflight.py \
		--binary dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow \
		--doctor dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--min-duration $${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25}

doubao-shadow-preflight-packaged-json: ensure-packaged-app
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_preflight.py \
		--binary dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow \
		--doctor dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--min-duration $${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25} \
		--json

doubao-shadow-refresh-packaged-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_refresh_plan.py --human

doubao-shadow-refresh-packaged-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_refresh_plan.py

doubao-shadow-refresh-packaged:
	$(MAKE) doubao-shadow-stop
	$(MAKE) package
	$(MAKE) app-request-permissions-packaged
	$(MAKE) doubao-shadow-preflight-packaged

doubao-shadow-start: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --start \
		$${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:+--expected-input-device "$$SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"} \
		$${SWITCHTYPE_HOTKEY_KEY_CODE:+--hotkey-key-code "$$SWITCHTYPE_HOTKEY_KEY_CODE"} \
		$${SWITCHTYPE_HOTKEY_MODIFIERS:+--hotkey-modifiers "$$SWITCHTYPE_HOTKEY_MODIFIERS"} \
		$${SWITCHTYPE_CAPTURE_FOCUSED_TEXT:+--capture-focused-text} \
		$${SWITCHTYPE_DEBUG_HOTKEY_EVENTS:+--debug-hotkey-events} \
		$${SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS:+--text-capture-delay-seconds "$$SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"} \
		$${SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS:+--text-capture-timeout-seconds "$$SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"}

doubao-shadow-start-packaged: ensure-packaged-app
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --start \
		--binary dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow \
		$${SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME:+--expected-input-device "$$SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"} \
		$${SWITCHTYPE_HOTKEY_KEY_CODE:+--hotkey-key-code "$$SWITCHTYPE_HOTKEY_KEY_CODE"} \
		$${SWITCHTYPE_HOTKEY_MODIFIERS:+--hotkey-modifiers "$$SWITCHTYPE_HOTKEY_MODIFIERS"} \
		$${SWITCHTYPE_CAPTURE_FOCUSED_TEXT:+--capture-focused-text} \
		$${SWITCHTYPE_DEBUG_HOTKEY_EVENTS:+--debug-hotkey-events} \
		$${SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS:+--text-capture-delay-seconds "$$SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS"} \
		$${SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS:+--text-capture-timeout-seconds "$$SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS"}

doubao-shadow-start-auto: doubao-shadow-preflight
	SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1 \
	SWITCHTYPE_HOTKEY_KEY_CODE=$${SWITCHTYPE_HOTKEY_KEY_CODE:-58} \
	SWITCHTYPE_HOTKEY_MODIFIERS=$${SWITCHTYPE_HOTKEY_MODIFIERS:-option} \
	$(MAKE) doubao-shadow-start

doubao-shadow-start-auto-packaged: doubao-shadow-preflight-packaged
	SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1 \
	SWITCHTYPE_HOTKEY_KEY_CODE=$${SWITCHTYPE_HOTKEY_KEY_CODE:-58} \
	SWITCHTYPE_HOTKEY_MODIFIERS=$${SWITCHTYPE_HOTKEY_MODIFIERS:-option} \
	$(MAKE) doubao-shadow-start-packaged

doubao-shadow-restart-packaged:
	$(MAKE) doubao-shadow-stop
	$(MAKE) doubao-shadow-start-auto-packaged

doubao-shadow-status:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --status

doubao-shadow-status-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --status --json

doubao-shadow-can-hear-me:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --hearing-check

doubao-shadow-can-hear-me-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --hearing-check --json

doubao-shadow-stop:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_daemon.py --stop

doubao-shadow-reconcile:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json}

doubao-shadow-reconcile-current:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		--current-only

doubao-shadow-reconcile-current-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--current-only \
		--plan

doubao-shadow-reconcile-current-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--current-only \
		--plan \
		--json

doubao-shadow-reconcile-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--plan

doubao-shadow-reconcile-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--plan \
		--json

doubao-shadow-reconcile-auto: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		--asr-preview \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke \
		--auto-only

doubao-shadow-reconcile-preview: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		--asr-preview \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke

doubao-shadow-latest-preview: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--asr-preview \
		--latest-preview \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke

doubao-shadow-live-verify:
	$(MAKE) doubao-shadow-wait-next-preview

doubao-shadow-live-verify-plan:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_live_verify_plan.py --human

doubao-shadow-live-verify-plan-json:
	@PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/doubao_shadow_live_verify_plan.py

doubao-shadow-wait-next-preview:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--pid-file $${PID_FILE:-bench/samples/doubao-shadow/shadow.pid} \
		--asr-preview \
		--wait-next-preview \
		--wait-timeout-seconds $${TIMEOUT:-30} \
		--wait-poll-seconds $${POLL:-0.5} \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke

doubao-shadow-preview-transcripts: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--asr-preview \
		--preview-only \
		--preview-output $${PREVIEW_OUTPUT:-bench/reports/doubao-shadow-asr-preview.md} \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke

doubao-shadow-review-sheet: swift-build
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--asr-preview \
		--review-tsv \
		--review-output $${REVIEW_OUTPUT:-bench/samples/doubao-shadow/review.tsv} \
		--asr-smoke-bin app/SwitchType/.build/debug/SwitchTypeASRSmoke

doubao-shadow-import-review:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/reconcile_doubao_shadow.py \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--hotwords $${HOTWORDS:-bench/config/hotwords.example.json} \
		--import-review $${REVIEW_INPUT:-bench/samples/doubao-shadow/review.tsv}

doubao-shadow-benchmark:
	PYTHONPATH=$(PYTHONPATH) python3 bench/scripts/run_doubao_shadow_benchmark.py \
		--segments $${SEGMENTS:-bench/samples/doubao-shadow/segments.jsonl} \
		--manifest $${MANIFEST:-bench/samples/doubao-shadow/manifest.jsonl} \
		--preview-manifest $${PREVIEW_MANIFEST:-bench/samples/doubao-shadow/manifest.valid.jsonl} \
		--report $${REPORT:-bench/reports/doubao-shadow-preview.md} \
		--min-duration $${SWITCHTYPE_SAMPLE_MIN_DURATION:-0.25}

app-permissions:
	./scripts/open_app_permissions.sh

app-request-permissions: swift-build
	app/SwitchType/.build/debug/SwitchTypeDoctor --request-microphone --prompt-accessibility

app-request-permissions-packaged: ensure-packaged-app
	dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor --request-microphone --prompt-accessibility

app-focused-text-doctor: ensure-packaged-app
	dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor --focused-text-json \
		--focused-text-delay-seconds $${DELAY:-0}

app-doctor: swift-build
	SWITCHTYPE_HOTWORDS_CONFIG="$${SWITCHTYPE_HOTWORDS_CONFIG:-$(CURDIR)/bench/config/hotwords.example.json}" \
		app/SwitchType/.build/debug/SwitchTypeDoctor

asr-smoke:
	./scripts/run_asr_smoke.sh

app-asr-smoke: swift-build
	./scripts/run_app_asr_smoke.sh

app-public-asr-smoke: swift-build
	./scripts/run_app_public_asr_smoke.sh

app-hotwords-smoke: swift-build
	./scripts/run_app_hotwords_smoke.sh
