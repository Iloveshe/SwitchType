import unittest
from pathlib import Path


class DoubaoShadowRecorderTests(unittest.TestCase):
    def test_package_exposes_shadow_recorder_executable(self):
        package = Path("app/SwitchType/Package.swift").read_text(encoding="utf-8")

        self.assertIn('executable(name: "SwitchTypeDoubaoShadow"', package)
        self.assertIn('name: "SwitchTypeDoubaoShadow"', package)

    def test_shadow_recorder_uses_passthrough_hotkey_listener(self):
        source = Path("app/SwitchType/Sources/SwitchTypeDoubaoShadow/main.swift").read_text(encoding="utf-8")
        core_source = Path("app/SwitchType/Sources/SwitchTypeCore/HotkeyController.swift").read_text(encoding="utf-8")

        self.assertIn("setbuf(stdout, nil)", source)
        self.assertIn("setbuf(stderr, nil)", source)
        self.assertIn("HotkeyController(consumeEvents: false, configuration: hotkeyConfiguration)", source)
        self.assertIn("Doubao shadow recorder armed", source)
        self.assertIn("segments.jsonl", source)
        self.assertIn("--capture-focused-text", source)
        self.assertIn("FocusedTextCapture", source)
        self.assertIn("text_capture_status", source)
        self.assertIn("text_capture_reason", source)
        self.assertIn("text_capture_attempts", source)
        self.assertIn("text_capture_elapsed_seconds", source)
        self.assertIn("text_capture_before_length", source)
        self.assertIn("text_capture_after_length", source)
        self.assertIn("text_capture_before_process_identifier", source)
        self.assertIn("text_capture_after_process_identifier", source)
        self.assertIn("text_capture_before_selection_location", source)
        self.assertIn("text_capture_before_selection_length", source)
        self.assertIn("text_capture_after_selection_location", source)
        self.assertIn("text_capture_after_selection_length", source)
        self.assertIn("FocusedTextDelta.firstCapturedMatch", source)
        self.assertIn("recording_stop_reason", source)
        self.assertIn("hotkey_released", source)
        self.assertIn("max_duration", source)
        self.assertIn("scheduleMissingBeforeSnapshotRetry", source)
        self.assertIn("Recovered focused text before snapshot", source)
        self.assertIn("startIdleSnapshotMonitor", source)
        self.assertIn("lastIdleTextSnapshot", source)
        self.assertIn("Using last idle focused text snapshot", source)
        self.assertIn("Focused text idle baseline captured.", source)
        self.assertIn("--text-capture-timeout-seconds", source)
        self.assertIn("finalizeWhenReferenceAvailable", source)
        self.assertIn("Waiting up to", source)
        self.assertIn("FocusedTextDelta.firstCapturedMatch", source)
        self.assertIn("CGEventType.flagsChanged", core_source)
        self.assertIn("consumeEvents ? .defaultTap : .listenOnly", core_source)
        self.assertNotIn("CGEventSource.flagsState(.combinedSessionState)", core_source)
        self.assertNotIn("releaseMonitor", core_source)

    def test_shadow_recorder_can_log_hotkey_event_diagnostics(self):
        source = Path("app/SwitchType/Sources/SwitchTypeDoubaoShadow/main.swift").read_text(encoding="utf-8")
        core_source = Path("app/SwitchType/Sources/SwitchTypeCore/HotkeyController.swift").read_text(encoding="utf-8")
        makefile = Path("Makefile").read_text(encoding="utf-8")
        daemon = Path("bench/scripts/doubao_shadow_daemon.py").read_text(encoding="utf-8")

        self.assertIn("HotkeyEventDiagnostic", core_source)
        self.assertIn("onEventObserved", core_source)
        self.assertIn("--debug-hotkey-events", source)
        self.assertIn("hotkeyController.onEventObserved", source)
        self.assertIn("Hotkey event:", source)
        self.assertIn("SWITCHTYPE_DEBUG_HOTKEY_EVENTS", makefile)
        self.assertIn("--debug-hotkey-events", makefile)
        self.assertIn("debug_hotkey_events", daemon)

    def test_shadow_recorder_supports_fixed_duration_mic_probe(self):
        source = Path("app/SwitchType/Sources/SwitchTypeDoubaoShadow/main.swift").read_text(encoding="utf-8")
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("--record-seconds", source)
        self.assertIn("--max-record-seconds", source)
        self.assertIn("stopIfRecording(startedAt:", source)
        self.assertIn("Maximum recording duration reached.", source)
        self.assertIn("Doubao shadow one-shot recording started", source)
        self.assertIn("doubao-shadow-record-seconds:", makefile)
        self.assertIn("--record-seconds", makefile)

    def test_makefile_exposes_packaged_fixed_duration_fallback(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-capture-once-packaged:", makefile)
        self.assertIn("doubao-shadow-record-seconds-packaged: ensure-packaged-app", makefile)
        self.assertIn("doubao-shadow-record-seconds-auto-packaged:", makefile)
        self.assertNotIn("doubao-shadow-record-seconds-packaged: package", makefile)
        self.assertIn("dist/SwitchType.app/Contents/MacOS/SwitchTypeDoubaoShadow", makefile)
        self.assertIn("SWITCHTYPE_CAPTURE_FOCUSED_TEXT=1", makefile)
        self.assertIn('DURATION=$${DURATION:-5}', makefile)
        self.assertIn("SWITCHTYPE_TEXT_CAPTURE_DELAY_SECONDS", makefile)
        self.assertIn("SWITCHTYPE_TEXT_CAPTURE_TIMEOUT_SECONDS", makefile)
        self.assertIn("bench/scripts/run_doubao_shadow_capture_once.py", makefile)

    def test_fixed_duration_fallback_has_pre_record_delay(self):
        source = Path("app/SwitchType/Sources/SwitchTypeDoubaoShadow/main.swift").read_text(encoding="utf-8")
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("--pre-record-delay-seconds", source)
        self.assertIn("preRecordDelay", source)
        self.assertIn("Doubao shadow one-shot recording will start", source)
        self.assertIn("RunLoop.main.run(until: Date().addingTimeInterval(preRecordDelay))", source)
        self.assertIn("oneShotTextCaptureDrainSlack", source)
        self.assertIn("max(textCaptureDelay, textCaptureTimeout) + oneShotTextCaptureDrainSlack", source)
        self.assertIn("--pre-record-delay-seconds $${PRE_DELAY:-2}", makefile)
        self.assertIn("PRE_DELAY=$${PRE_DELAY:-2}", makefile)

    def test_makefile_exposes_doubao_shadow_target(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        self.assertIn("doubao-shadow-record:", makefile)
        self.assertIn("SwitchTypeDoubaoShadow", makefile)
        self.assertIn("bench/samples/doubao-shadow/segments.jsonl", makefile)

    def test_docs_describe_opt_in_shadow_recording_boundary(self):
        readme = Path("bench/README.md").read_text(encoding="utf-8")

        self.assertIn("Doubao Shadow Recorder", readme)
        self.assertIn("explicit opt-in", readme)
        self.assertIn("does not consume", readme)


if __name__ == "__main__":
    unittest.main()
