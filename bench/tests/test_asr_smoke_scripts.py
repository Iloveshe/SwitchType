import unittest
from pathlib import Path


ASR_SMOKE = Path("scripts/run_asr_smoke.sh")
APP_ASR_SMOKE = Path("scripts/run_app_asr_smoke.sh")
APP_PUBLIC_ASR_SMOKE = Path("scripts/run_app_public_asr_smoke.sh")
APP_HOTWORDS_SMOKE = Path("scripts/run_app_hotwords_smoke.sh")
APP_PERMISSIONS = Path("scripts/open_app_permissions.sh")
APP_DEV = Path("scripts/run_app_dev.sh")
APP_DELEGATE = Path("app/SwitchType/Sources/SwitchType/AppDelegate.swift")
QWEN_SERVER_CONTROLLER = Path("app/SwitchType/Sources/SwitchType/QwenServerController.swift")
APP_HUD = Path("app/SwitchType/Sources/SwitchType/VoiceTypingHUD.swift")
APP_EVENT_LOGGER = Path("app/SwitchType/Sources/SwitchType/AppEventLogger.swift")
HOTWORD_EDITOR = Path("app/SwitchType/Sources/SwitchType/HotwordEditorWindowController.swift")
HOTKEY_CONTROLLER = Path("app/SwitchType/Sources/SwitchTypeCore/HotkeyController.swift")
AUDIO_RECORDER = Path("app/SwitchType/Sources/SwitchTypeCore/AudioRecorder.swift")
SWITCHTYPE_DOCTOR = Path("app/SwitchType/Sources/SwitchTypeDoctor/main.swift")
FOCUSED_TEXT_CAPTURE = Path("app/SwitchType/Sources/SwitchTypeCore/FocusedTextCapture.swift")
PACKAGE_SCRIPT = Path("scripts/package_app.sh")
LOCAL_CODESIGN_SCRIPT = Path("scripts/create_local_codesign_identity.sh")
GITHUB_CI = Path(".github/workflows/ci.yml")
PACKAGE = Path("app/SwitchType/Package.swift")
SWITCHTYPE_ASR_SMOKE = Path("app/SwitchType/Sources/SwitchTypeASRSmoke/main.swift")
MAKEFILE = Path("Makefile")
README = Path("README.md")
APP_README = Path("app/SwitchType/README.md")


class ASRSmokeScriptTests(unittest.TestCase):
    def test_asr_smoke_resolves_whisper_paths_from_shared_asr_config(self):
        script = ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn('scripts/resolve_asr_config.py" --key whisper_bin', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_model', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_no_gpu', script)

    def test_app_asr_smoke_resolves_whisper_paths_from_shared_asr_config(self):
        script = APP_ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn('scripts/resolve_asr_config.py" --key whisper_bin', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_model', script)
        self.assertIn('scripts/resolve_asr_config.py" --key whisper_no_gpu', script)
        self.assertIn('SMOKE_LANGUAGE="${SWITCHTYPE_APP_ASR_SMOKE_LANGUAGE:-en}"', script)
        self.assertIn('SWITCHTYPE_WHISPER_LANGUAGE="$SMOKE_LANGUAGE"', script)

    def test_app_asr_smoke_suggests_cpu_fallback_when_metal_fails(self):
        script = APP_ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn("ggml_metal_buffer_init", script)
        self.assertIn("SWITCHTYPE_WHISPER_NO_GPU=1 make app-asr-smoke", script)

    def test_makefile_exposes_app_public_asr_smoke_target(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")

        self.assertIn("app-public-asr-smoke:", makefile)
        self.assertIn("./scripts/run_app_public_asr_smoke.sh", makefile)

    def test_app_public_asr_smoke_uses_public_mixed_sample(self):
        script = APP_PUBLIC_ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn("SwitchTypeASRSmoke", script)
        self.assertIn('PUBLIC_SAMPLE_ID="${SWITCHTYPE_APP_PUBLIC_SAMPLE_ID:-ascend-00009}"', script)
        self.assertIn('EXPECTED_TEXT="${SWITCHTYPE_APP_PUBLIC_ASR_EXPECT:-Information}"', script)
        self.assertIn('SMOKE_AUDIO="${SWITCHTYPE_APP_PUBLIC_ASR_AUDIO:-$ROOT_DIR/bench/samples/public/audio/$PUBLIC_SAMPLE_ID.wav}"', script)
        self.assertIn('Run: make public-asr', script)
        self.assertIn('SWITCHTYPE_WHISPER_BIN="$WHISPER_BIN"', script)
        self.assertIn('SWITCHTYPE_WHISPER_MODEL="$WHISPER_MODEL"', script)
        self.assertIn('SWITCHTYPE_WHISPER_NO_GPU="$WHISPER_NO_GPU"', script)

    def test_app_public_asr_smoke_suggests_cpu_fallback_when_metal_fails(self):
        script = APP_PUBLIC_ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn("ggml_metal_buffer_init", script)
        self.assertIn("SWITCHTYPE_WHISPER_NO_GPU=1 make app-public-asr-smoke", script)

    def test_switchtype_asr_smoke_can_postprocess_transcript(self):
        source = SWITCHTYPE_ASR_SMOKE.read_text(encoding="utf-8")

        self.assertIn('--postprocess', source)
        self.assertIn('PostProcessor(config: HotwordConfig.loadDefault())', source)

    def test_makefile_exposes_app_hotwords_smoke_target(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")

        self.assertIn("app-hotwords-smoke:", makefile)
        self.assertIn("./scripts/run_app_hotwords_smoke.sh", makefile)

    def test_app_hotwords_smoke_uses_transcript_override_and_hotword_config(self):
        script = APP_HOTWORDS_SMOKE.read_text(encoding="utf-8")

        self.assertIn('TRANSCRIPT_OVERRIDE="${SWITCHTYPE_APP_HOTWORDS_TRANSCRIPT:-扣德克斯 的 皮阿尔 issue}"', script)
        self.assertIn('EXPECTED_TEXT="${SWITCHTYPE_APP_HOTWORDS_EXPECT:-Codex 的 PR issue}"', script)
        self.assertIn('SWITCHTYPE_TRANSCRIPT_OVERRIDE="$TRANSCRIPT_OVERRIDE"', script)
        self.assertIn('SWITCHTYPE_HOTWORDS_CONFIG="${SWITCHTYPE_HOTWORDS_CONFIG:-$ROOT_DIR/bench/config/hotwords.example.json}"', script)
        self.assertIn("--postprocess", script)

    def test_app_dev_documents_expected_input_device_guard(self):
        script = APP_DEV.read_text(encoding="utf-8")

        self.assertIn("SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME", script)
        self.assertIn("Expected input device", script)

    def test_app_delegate_shows_expected_input_device_in_permission_status(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")

        self.assertIn("private let expectedInputDeviceName", source)
        self.assertIn("PermissionDiagnostics.snapshot(expectedInputDeviceName: expectedInputDeviceName)", source)

    def test_app_delegate_uses_non_doubao_default_hotkey(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")

        self.assertIn("HotkeyConfiguration.fromAppEnvironment", source)

    def test_app_menu_can_switch_asr_backends(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")
        transcription = Path("app/SwitchType/Sources/SwitchTypeCore/TranscriptionService.swift").read_text(encoding="utf-8")
        doctor = SWITCHTYPE_DOCTOR.read_text(encoding="utf-8")

        self.assertIn("ASR Backend", source)
        self.assertIn("Local Whisper Profile", source)
        self.assertIn("HTTP ASR Profile", source)
        self.assertIn("setASRBackend", source)
        self.assertIn("setLocalWhisperProfile", source)
        self.assertIn("setHTTPASRProfile", source)
        self.assertIn("writeBackendSelection", source)
        self.assertIn("writeLocalWhisperProfileSelection", source)
        self.assertIn("writeHTTPASRProfileSelection", source)
        self.assertIn("asr backend selected", source)
        self.assertIn("local whisper profile selected", source)
        self.assertIn("http asr profile selected", source)
        self.assertIn("TranscriptionBackend", transcription)
        self.assertIn("LocalWhisperProfile", transcription)
        self.assertIn("HTTPASRProfile", transcription)
        self.assertIn("Local Whisper", transcription)
        self.assertIn("Custom Command", transcription)
        self.assertIn("HTTP JSON", transcription)
        self.assertIn("Base CPU", transcription)
        self.assertIn("Large Turbo", transcription)
        self.assertIn("Qwen3-ASR Official (Local HTTP)", transcription)
        self.assertIn("shouldRetryWithCPUFallback", transcription)
        self.assertIn("failed to allocate buffer", transcription)
        self.assertIn("Custom from asr.json", transcription)
        self.assertIn("case localWhisper = \"local_whisper\"", transcription)
        self.assertIn("case baseCPU = \"base_cpu\"", transcription)
        self.assertIn("case largeTurbo = \"large_turbo\"", transcription)
        self.assertIn("case qwen3OfficialLocal = \"qwen3_official_local\"", transcription)
        self.assertIn("case command", transcription)
        self.assertIn("case httpJSON = \"http_json\"", transcription)
        self.assertIn("CommandTranscriptionService", transcription)
        self.assertIn("HTTPJSONTranscriptionService", transcription)
        self.assertIn("asr_backend", doctor)
        self.assertIn("local_whisper_profile", doctor)
        self.assertIn("asr_http_profile", doctor)

    def test_app_menu_can_control_local_qwen_server_and_log_latency(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")
        transcription = Path("app/SwitchType/Sources/SwitchTypeCore/TranscriptionService.swift").read_text(encoding="utf-8")
        qwen_controller = QWEN_SERVER_CONTROLLER.read_text(encoding="utf-8")
        server = Path("scripts/qwen3_asr_server.py").read_text(encoding="utf-8")

        self.assertIn("Qwen Server", source)
        self.assertIn("Check Qwen Server", source)
        self.assertIn("Start Local Qwen Server", source)
        self.assertIn("Stop Local Qwen Server", source)
        self.assertIn("Warm Up Qwen Server", source)
        self.assertIn("refreshQwenServerStatus", source)
        self.assertIn("startQwenServer", source)
        self.assertIn("stopQwenServer", source)
        self.assertIn("warmUpQwenServer", source)
        self.assertIn("qwen server health", source)
        self.assertIn("qwen server started", source)
        self.assertIn("qwen server stopped", source)
        self.assertIn("qwen server warmup", source)
        self.assertIn("latency recording_ms", source)
        self.assertIn("latency audio_bytes", source)
        self.assertIn("latency workflow_postprocess_ms", source)
        self.assertIn("latency transcription_ms", source)
        self.assertIn("latency http_body_ms", transcription)
        self.assertIn("latency http_roundtrip_ms", transcription)
        self.assertIn("latency http_extract_ms", transcription)
        self.assertIn("latency paste_ms", source)
        self.assertIn("latency e2e_ms", source)
        self.assertIn("final class QwenServerController", qwen_controller)
        self.assertIn("dev.switchtype.qwen3-asr", qwen_controller)
        self.assertIn("launchctl", qwen_controller)
        self.assertIn("/private/tmp/switchtype-qwen3-venv/bin/python", qwen_controller)
        self.assertIn("/health", qwen_controller)
        self.assertIn("/warmup", qwen_controller)
        self.assertIn("SWITCHTYPE_QWEN3_ASR_PYTHON", qwen_controller)
        self.assertIn("model_loaded", server)
        self.assertIn("device_map", server)
        self.assertIn("dtype", server)
        self.assertIn("read_upload_ms", server)
        self.assertIn("write_temp_ms", server)
        self.assertIn("load_ms", server)
        self.assertIn("infer_ms", server)
        self.assertIn("server_total_ms", server)
        self.assertIn("def warm_up", server)
        self.assertIn("qwen_asr_latency_ms", server)

    def test_modifier_hotkey_does_not_use_polling_release_detection(self):
        source = HOTKEY_CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("CGEventType.flagsChanged", source)
        self.assertIn("case .finishRecording", source)
        self.assertNotIn("startModifierPollMonitorIfNeeded", source)
        self.assertNotIn("startReleaseMonitor", source)
        self.assertNotIn("CGEventSource.flagsState", source)

    def test_app_shows_visible_voice_typing_feedback(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")
        hud = APP_HUD.read_text(encoding="utf-8")
        logger = APP_EVENT_LOGGER.read_text(encoding="utf-8")

        self.assertIn("VoiceTypingHUD", source)
        self.assertIn('NSImage(systemSymbolName: "mic.fill"', source)
        self.assertIn('"SwitchType voice input"', source)
        self.assertIn('" SwitchType"', source)
        self.assertIn("status item configured", source)
        self.assertIn("showReadyFeedback", source)
        self.assertIn("AppFeedbackFactory.feedback(for: state)", source)
        self.assertIn("AppEventLogger", source)
        self.assertIn("onEventObserved", source)
        self.assertIn("hotkey listener started", source)
        self.assertLess(source.index("state = .recording"), source.index("try recorder.startRecording()"))
        self.assertIn("orderFrontRegardless", hud)
        self.assertIn("Timer.scheduledTimer", hud)
        self.assertIn("Library/Logs/SwitchType", logger)
        self.assertIn("FileHandle(forWritingTo:", logger)

    def test_app_menu_can_open_and_reload_hotwords(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")
        editor = HOTWORD_EDITOR.read_text(encoding="utf-8")
        postprocessor = Path("app/SwitchType/Sources/SwitchTypeCore/PostProcessor.swift").read_text(encoding="utf-8")
        transcription = Path("app/SwitchType/Sources/SwitchTypeCore/TranscriptionService.swift").read_text(encoding="utf-8")

        self.assertIn("Edit Hotwords...", source)
        self.assertIn("Reload Hotwords", source)
        self.assertIn("HotwordEditorWindowController", source)
        self.assertIn("showHotwordEditor", source)
        self.assertNotIn('NSMenuItem(title: "Open Hotwords File"', source)
        self.assertIn("HotwordConfig.ensurePersonalConfig()", source)
        self.assertIn("hotwords reloaded", source)
        self.assertIn("hotwordConfig.asrPrompt()", source)
        self.assertIn("Save & Reload", editor)
        self.assertIn("Open JSON", editor)
        self.assertIn("NSTextView", editor)
        self.assertIn("fromEditorText", editor)
        self.assertIn("editorProtectedTermsText", editor)
        self.assertIn("editorReplacementsText", editor)
        self.assertIn("onSave", editor)
        self.assertIn("public func asrPrompt", postprocessor)
        self.assertIn("public static func ensurePersonalConfig", postprocessor)
        self.assertIn('"--prompt"', transcription)
        self.assertIn('"--carry-initial-prompt"', transcription)

    def test_app_warms_recorder_before_first_hotkey_recording(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")
        recorder = AUDIO_RECORDER.read_text(encoding="utf-8")

        self.assertIn("warmUpRecorder()", source)
        self.assertIn("recorder warmup requested", source)
        self.assertIn("microphone permission request started", source)
        self.assertIn("recorder.requestMicrophonePermission", source)
        self.assertIn("performRecorderWarmUp()", source)
        self.assertIn("recorder.warmUp()", source)
        self.assertIn("recorder started in", source)
        self.assertIn("public func warmUp()", recorder)
        self.assertIn("permissionSnapshot.microphone == .granted", recorder)
        self.assertIn("Thread.sleep(forTimeInterval: 0.05)", recorder)
        self.assertIn("switchtype-warmup-", recorder)
        self.assertIn("defer { cleanup(url) }", recorder)

    def test_app_delegate_can_request_accessibility_permission(self):
        source = APP_DELEGATE.read_text(encoding="utf-8")

        self.assertIn("Request Accessibility Permission", source)
        self.assertIn("AXIsProcessTrustedWithOptions", source)
        self.assertIn("kAXTrustedCheckOptionPrompt", source)
        self.assertIn("requestAccessibilityTrustPrompt()", source)
        self.assertIn("HotkeyControllerError.eventTapUnavailable", source)

    def test_app_doctor_target_reports_permissions_asr_and_hotwords(self):
        package = PACKAGE.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        source = SWITCHTYPE_DOCTOR.read_text(encoding="utf-8")
        transcription = Path("app/SwitchType/Sources/SwitchTypeCore/TranscriptionService.swift").read_text(encoding="utf-8")

        self.assertIn('.executable(name: "SwitchTypeDoctor"', package)
        self.assertIn('name: "SwitchTypeDoctor"', package)
        self.assertIn("app-doctor:", makefile)
        self.assertIn("SwitchTypeDoctor", makefile)
        self.assertIn("SWITCHTYPE_HOTWORDS_CONFIG", makefile)
        self.assertIn("PermissionDiagnostics.snapshot(expectedInputDeviceName: configuration.expectedInputDeviceName)", source)
        self.assertIn("whisper_bin", source)
        self.assertIn("asr_backend", source)
        self.assertIn("local_whisper_profile", source)
        self.assertIn("whisper_language", source)
        self.assertIn("hotwords", source)
        self.assertIn('environment["SWITCHTYPE_ASR_BACKEND"]', transcription)
        self.assertIn('?? "zh"', transcription)
        self.assertIn('environment["SWITCHTYPE_WHISPER_LANGUAGE"]', transcription)
        self.assertIn('case whisperLanguage = "whisper_language"', transcription)

    def test_app_postprocessor_normalizes_traditional_chinese_to_simplified(self):
        source = Path("app/SwitchType/Sources/SwitchTypeCore/PostProcessor.swift").read_text(encoding="utf-8")
        check = Path("app/SwitchType/Sources/SwitchTypeCoreCheck/main.swift").read_text(encoding="utf-8")

        self.assertIn("Traditional-Simplified", source)
        self.assertIn("simplifyChinese", source)
        self.assertIn("繁體中文和後臺權限可以夾 English", check)
        self.assertIn("繁体中文和后台权限可以夹 English", check)

    def test_app_doctor_supports_json_for_release_preflight(self):
        source = SWITCHTYPE_DOCTOR.read_text(encoding="utf-8")

        self.assertIn('"--json"', source)
        self.assertIn("DoctorReport", source)
        self.assertIn("JSONEncoder", source)
        self.assertIn("expected_input_device_status", source)

    def test_app_doctor_can_request_mac_permissions(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        source = SWITCHTYPE_DOCTOR.read_text(encoding="utf-8")

        self.assertIn("app-request-permissions:", makefile)
        self.assertIn("app-request-permissions-packaged: ensure-packaged-app", makefile)
        self.assertNotIn("app-request-permissions-packaged: package", makefile)
        self.assertIn("--request-microphone", makefile)
        self.assertIn("--prompt-accessibility", makefile)
        self.assertIn("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor --request-microphone --prompt-accessibility", makefile)
        self.assertIn('"--request-microphone"', source)
        self.assertIn('"--prompt-accessibility"', source)
        self.assertIn("requestMicrophonePermission", source)
        self.assertIn("DispatchSemaphore", source)
        self.assertIn("AXIsProcessTrustedWithOptions", source)
        self.assertIn("kAXTrustedCheckOptionPrompt", source)

    def test_app_doctor_can_debug_focused_text_capture(self):
        source = SWITCHTYPE_DOCTOR.read_text(encoding="utf-8")
        core_source = FOCUSED_TEXT_CAPTURE.read_text(encoding="utf-8")

        self.assertIn('"--focused-text-json"', source)
        self.assertIn('"--focused-text-delay-seconds"', source)
        self.assertIn("FocusedTextCapture().diagnosticSnapshot", source)
        self.assertIn("FocusedTextDiagnostic", core_source)
        self.assertIn("NSWorkspace.shared.frontmostApplication", core_source)
        self.assertIn("kAXFocusedUIElementAttribute", core_source)
        self.assertIn("kAXFocusedApplicationAttribute", core_source)
        self.assertIn("kAXValueAttribute", core_source)

    def test_packaged_app_includes_doctor_and_shadow_helpers(self):
        script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('cp "$BUILD_DIR/SwitchTypeDoctor"', script)
        self.assertIn('cp "$BUILD_DIR/SwitchTypeDoubaoShadow"', script)

    def test_packaged_app_is_signed_as_bundle_with_stable_identifier(self):
        script = PACKAGE_SCRIPT.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        ci = GITHUB_CI.read_text(encoding="utf-8")

        self.assertIn("SWITCHTYPE_CODESIGN_IDENTITY", script)
        self.assertIn("SWITCHTYPE_LOCAL_CODESIGN_IDENTITY", script)
        self.assertIn("SwitchType Local Development", script)
        self.assertIn("security find-identity -v -p codesigning", script)
        self.assertIn("Unable to find required local codesigning identity", script)
        self.assertIn("Run ./scripts/create_local_codesign_identity.sh outside the sandbox", script)
        self.assertNotIn('CODE_SIGN_IDENTITY="-"', script)
        self.assertIn("codesign --force --deep --sign", script)
        self.assertIn("--identifier dev.switchtype.SwitchType", script)
        self.assertLess(script.index("codesign --force --deep"), script.index('zip -qr "$(basename "$ARCHIVE_PATH")"'))
        self.assertIn("ci-package:", makefile)
        self.assertIn("SWITCHTYPE_CODESIGN_IDENTITY=- $(MAKE) package", makefile)
        self.assertIn("SWITCHTYPE_CODESIGN_IDENTITY=- make package", ci)

    def test_local_codesign_identity_script_creates_code_signing_certificate(self):
        script = LOCAL_CODESIGN_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("SwitchType Local Development", script)
        self.assertIn("extendedKeyUsage = codeSigning", script)
        self.assertIn("openssl req", script)
        self.assertIn("openssl pkcs12", script)
        self.assertIn("security import", script)
        self.assertIn("-T /usr/bin/codesign", script)
        self.assertIn("security find-identity -v -p codesigning", script)

    def test_makefile_exposes_packaged_focused_text_doctor(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")

        self.assertIn("app-focused-text-doctor:", makefile)
        self.assertIn("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoctor --focused-text-json", makefile)
        self.assertIn("--focused-text-delay-seconds $${DELAY:-0}", makefile)

    def test_docs_point_packaged_shadow_permissions_at_packaged_doctor(self):
        readme = README.read_text(encoding="utf-8")
        app_readme = APP_README.read_text(encoding="utf-8")

        self.assertIn("make app-request-permissions-packaged", readme)
        self.assertIn("make app-request-permissions-packaged", app_readme)

    def test_app_permissions_opens_relevant_privacy_panes(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        script = APP_PERMISSIONS.read_text(encoding="utf-8")

        self.assertIn("app-permissions", makefile)
        self.assertIn("./scripts/open_app_permissions.sh", makefile)
        self.assertIn("Privacy_Microphone", script)
        self.assertIn("Privacy_Accessibility", script)
        self.assertIn("make app-doctor", script)
        self.assertIn("make app-request-permissions-packaged", script)
        self.assertIn("SwitchTypeDoctor --json", script)


if __name__ == "__main__":
    unittest.main()
