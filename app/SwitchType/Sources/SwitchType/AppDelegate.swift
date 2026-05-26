import AppKit
import ApplicationServices
import Foundation
import SwitchTypeCore

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let recorder: AudioRecorder
    private var transcriptionConfiguration: TranscriptionConfiguration
    private let hotkeyConfiguration: HotkeyConfiguration
    private let hotkeyController: HotkeyController
    private var workflow: VoiceTypingWorkflow
    private let expectedInputDeviceName: String?
    private let logger: AppEventLogger
    private lazy var feedbackHUD = VoiceTypingHUD()
    private var hotwordEditorWindowController: HotwordEditorWindowController?
    private var asrBackendMenuItems: [TranscriptionBackend: NSMenuItem] = [:]
    private var localWhisperProfileMenuItems: [LocalWhisperProfile: NSMenuItem] = [:]
    private var httpASRProfileMenuItems: [HTTPASRProfile: NSMenuItem] = [:]
    private let qwenServerStatusMenuItem = NSMenuItem(title: "Qwen Server: Unknown", action: nil, keyEquivalent: "")
    private var recordingStartedAt: Date?

    private var statusItem: NSStatusItem?
    private let statusMenuItem = NSMenuItem(title: AppState.idle.title, action: nil, keyEquivalent: "")
    private let permissionsMenuItem = NSMenuItem(title: PermissionDiagnostics.snapshot().summary, action: nil, keyEquivalent: "")
    private var state: AppState = .idle {
        didSet {
            statusMenuItem.title = state.title
            statusItem?.button?.title = shortTitle(for: state)
            logger.write("state changed: \(state.title)")
            showStateFeedback()
        }
    }

    override init() {
        var transcriptionConfiguration = TranscriptionConfiguration.fromEnvironment()
        let hotwordConfig = Self.loadHotwordConfig()
        transcriptionConfiguration.initialPrompt = hotwordConfig.asrPrompt()
        let hotkeyConfiguration = HotkeyConfiguration.fromAppEnvironment(ProcessInfo.processInfo.environment)
        let recorder = AudioRecorder(expectedInputDeviceName: transcriptionConfiguration.expectedInputDeviceName)
        let logger = AppEventLogger()
        self.transcriptionConfiguration = transcriptionConfiguration
        self.expectedInputDeviceName = transcriptionConfiguration.expectedInputDeviceName
        self.recorder = recorder
        self.logger = logger
        self.hotkeyConfiguration = hotkeyConfiguration
        self.hotkeyController = HotkeyController(configuration: hotkeyConfiguration)
        self.workflow = Self.makeWorkflow(
            transcriptionConfiguration: transcriptionConfiguration,
            hotwordConfig: hotwordConfig,
            recorder: recorder,
            eventLogger: { logger.write($0) }
        )
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        logger.write("launch hotkey=\(hotkeyConfiguration.displayName)")
        configureMenu()
        configureHotkey()
        warmUpRecorder()
    }

    func applicationWillTerminate(_ notification: Notification) {
        hotkeyController.stop()
    }

    private func configureMenu() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        configureStatusButton(item.button)

        let menu = NSMenu()
        menu.addItem(statusMenuItem)
        menu.addItem(permissionsMenuItem)
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Start Hotkey Listener", action: #selector(startHotkey), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Stop Hotkey Listener", action: #selector(stopHotkey), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(makeASRBackendMenuItem())
        menu.addItem(makeLocalWhisperProfileMenuItem())
        menu.addItem(makeHTTPASRProfileMenuItem())
        menu.addItem(makeQwenServerMenuItem())
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Edit Hotwords...", action: #selector(showHotwordEditor), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Reload Hotwords", action: #selector(reloadHotwords), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Refresh Permission Status", action: #selector(refreshPermissionStatus), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Request Microphone Permission", action: #selector(requestMicrophonePermission), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Request Accessibility Permission", action: #selector(requestAccessibilityPermission), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Open Accessibility Settings", action: #selector(openAccessibilitySettings), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit SwitchType", action: #selector(quit), keyEquivalent: "q"))
        item.menu = menu
        statusItem = item
        refreshPermissionStatus()
        updateASRBackendMenuState()
        refreshQwenServerStatus()
    }

    private func makeASRBackendMenuItem() -> NSMenuItem {
        asrBackendMenuItems = [:]
        let item = NSMenuItem(title: "ASR Backend", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "ASR Backend")
        for backend in TranscriptionBackend.allCases {
            let backendItem = NSMenuItem(
                title: backend.displayName,
                action: #selector(setASRBackend(_:)),
                keyEquivalent: ""
            )
            backendItem.target = self
            backendItem.representedObject = backend.rawValue
            submenu.addItem(backendItem)
            asrBackendMenuItems[backend] = backendItem
        }
        item.submenu = submenu
        return item
    }

    private func makeHTTPASRProfileMenuItem() -> NSMenuItem {
        httpASRProfileMenuItems = [:]
        let item = NSMenuItem(title: "HTTP ASR Profile", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "HTTP ASR Profile")
        for profile in HTTPASRProfile.allCases {
            let profileItem = NSMenuItem(
                title: profile.displayName,
                action: #selector(setHTTPASRProfile(_:)),
                keyEquivalent: ""
            )
            profileItem.target = self
            profileItem.representedObject = profile.rawValue
            submenu.addItem(profileItem)
            httpASRProfileMenuItems[profile] = profileItem
        }
        item.submenu = submenu
        return item
    }

    private func makeLocalWhisperProfileMenuItem() -> NSMenuItem {
        localWhisperProfileMenuItems = [:]
        let item = NSMenuItem(title: "Local Whisper Profile", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "Local Whisper Profile")
        for profile in LocalWhisperProfile.allCases {
            let profileItem = NSMenuItem(
                title: profile.displayName,
                action: #selector(setLocalWhisperProfile(_:)),
                keyEquivalent: ""
            )
            profileItem.target = self
            profileItem.representedObject = profile.rawValue
            submenu.addItem(profileItem)
            localWhisperProfileMenuItems[profile] = profileItem
        }
        item.submenu = submenu
        return item
    }

    private func makeQwenServerMenuItem() -> NSMenuItem {
        let item = NSMenuItem(title: "Qwen Server", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "Qwen Server")
        submenu.addItem(qwenServerStatusMenuItem)
        submenu.addItem(NSMenuItem.separator())

        let checkItem = NSMenuItem(title: "Check Qwen Server", action: #selector(refreshQwenServerStatus), keyEquivalent: "")
        checkItem.target = self
        submenu.addItem(checkItem)

        let startItem = NSMenuItem(title: "Start Local Qwen Server", action: #selector(startQwenServer), keyEquivalent: "")
        startItem.target = self
        submenu.addItem(startItem)

        let warmUpItem = NSMenuItem(title: "Warm Up Qwen Server", action: #selector(warmUpQwenServer), keyEquivalent: "")
        warmUpItem.target = self
        submenu.addItem(warmUpItem)

        let stopItem = NSMenuItem(title: "Stop Local Qwen Server", action: #selector(stopQwenServer), keyEquivalent: "")
        stopItem.target = self
        submenu.addItem(stopItem)

        item.submenu = submenu
        return item
    }

    private func configureStatusButton(_ button: NSStatusBarButton?) {
        guard let button else {
            logger.write("status item configured: button=false")
            return
        }

        if let image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "SwitchType voice input") {
            image.isTemplate = true
            button.image = image
        }
        button.imagePosition = .imageLeft
        button.title = shortTitle(for: state)
        button.toolTip = "SwitchType voice input"
        logger.write("status item configured: button=true title=\(button.title)")
    }

    @objc private func showHotwordEditor() {
        let controller = HotwordEditorWindowController(
            config: Self.loadHotwordConfig(),
            onSave: { [weak self] hotwordConfig in
                DispatchQueue.main.async {
                    self?.applyHotwordConfig(hotwordConfig, logPrefix: "hotwords saved and reloaded")
                }
            },
            onOpenJSON: { [weak self] in
                DispatchQueue.main.async {
                    self?.openHotwordsFile()
                }
            }
        )
        hotwordEditorWindowController = controller
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        logger.write("hotword editor opened")
    }

    private static func loadHotwordConfig() -> HotwordConfig {
        HotwordConfig.loadDefault()
    }

    private static func makeWorkflow(
        transcriptionConfiguration: TranscriptionConfiguration,
        hotwordConfig: HotwordConfig,
        recorder: AudioRecorder,
        eventLogger: @escaping TranscriptionEventLogger
    ) -> VoiceTypingWorkflow {
        var configuration = transcriptionConfiguration
        configuration.initialPrompt = hotwordConfig.asrPrompt()
        return VoiceTypingWorkflow(
            transcriber: TranscriptionService(configuration: configuration, eventLogger: eventLogger),
            postProcessor: PostProcessor(config: hotwordConfig),
            paster: PasteboardTyper(),
            cleaner: recorder
        )
    }

    private func configureHotkey() {
        hotkeyController.onRecordingRequested = { [weak self] in
            DispatchQueue.main.async {
                self?.startRecording()
            }
        }
        hotkeyController.onRecordingFinished = { [weak self] in
            DispatchQueue.main.async {
                self?.finishRecording()
            }
        }
        hotkeyController.onEventObserved = { [weak self] diagnostic in
            guard diagnostic.typeName == "flagsChanged" || diagnostic.action != .ignore else {
                return
            }
            self?.logger.write("hotkey \(diagnostic.summary)")
        }
        startHotkey()
    }

    @objc private func startHotkey() {
        do {
            try hotkeyController.start()
            logger.write("hotkey listener started: \(hotkeyConfiguration.displayName)")
            if state != .recording && state != .transcribing && state != .pasting {
                state = .idle
                showReadyFeedback()
            }
        } catch HotkeyControllerError.eventTapUnavailable {
            logger.write("hotkey listener failed: event tap unavailable")
            let trusted = requestAccessibilityTrustPrompt()
            if !trusted {
                openAccessibilitySettings()
            }
            refreshPermissionStatus()
            state = trusted
                ? .error("Could not create global hotkey event tap. Restart SwitchType and try again.")
                : .error("Enable Accessibility for SwitchType, then restart the hotkey listener.")
        } catch {
            logger.write("hotkey listener failed: \(error.localizedDescription)")
            state = .error(error.localizedDescription)
        }
    }

    @objc private func stopHotkey() {
        hotkeyController.stop()
        logger.write("hotkey listener stopped")
        state = .idle
        feedbackHUD.hide()
    }

    @objc private func refreshPermissionStatus() {
        let snapshot = PermissionDiagnostics.snapshot(expectedInputDeviceName: expectedInputDeviceName)
        permissionsMenuItem.title = snapshot.summary
    }

    @objc private func openHotwordsFile() {
        do {
            let url = try HotwordConfig.ensurePersonalConfig()
            logger.write("hotwords file opened: \(url.path)")
            NSWorkspace.shared.open(url)
        } catch {
            logger.write("hotwords file open failed: \(error.localizedDescription)")
            state = .error("Could not create hotwords file: \(error.localizedDescription)")
        }
    }

    @objc private func reloadHotwords() {
        let hotwordConfig = Self.loadHotwordConfig()
        applyHotwordConfig(hotwordConfig, logPrefix: "hotwords reloaded")
    }

    @objc private func setASRBackend(_ sender: NSMenuItem) {
        guard let rawValue = sender.representedObject as? String,
              let backend = TranscriptionBackend(rawValue: rawValue) else {
            return
        }

        do {
            let url = try TranscriptionConfiguration.writeBackendSelection(backend)
            transcriptionConfiguration = Self.loadTranscriptionConfiguration()
            updateASRBackendMenuState()
            refreshQwenServerStatus()
            applyHotwordConfig(Self.loadHotwordConfig(), logPrefix: "asr backend selected: \(backend.rawValue)")
            logger.write("asr backend selection saved: \(url.path)")
        } catch {
            logger.write("asr backend selection failed: \(error.localizedDescription)")
            state = .error("Could not save ASR backend: \(error.localizedDescription)")
        }
    }

    @objc private func setLocalWhisperProfile(_ sender: NSMenuItem) {
        guard let rawValue = sender.representedObject as? String,
              let profile = LocalWhisperProfile(rawValue: rawValue) else {
            return
        }

        do {
            let url = try TranscriptionConfiguration.writeLocalWhisperProfileSelection(profile)
            transcriptionConfiguration = Self.loadTranscriptionConfiguration()
            updateASRBackendMenuState()
            refreshQwenServerStatus()
            applyHotwordConfig(Self.loadHotwordConfig(), logPrefix: "local whisper profile selected: \(profile.rawValue)")
            logger.write("local whisper profile selection saved: \(url.path)")
        } catch {
            logger.write("local whisper profile selection failed: \(error.localizedDescription)")
            state = .error("Could not save Local Whisper profile: \(error.localizedDescription)")
        }
    }

    @objc private func setHTTPASRProfile(_ sender: NSMenuItem) {
        guard let rawValue = sender.representedObject as? String,
              let profile = HTTPASRProfile(rawValue: rawValue) else {
            return
        }

        do {
            let url = try TranscriptionConfiguration.writeHTTPASRProfileSelection(profile)
            transcriptionConfiguration = Self.loadTranscriptionConfiguration()
            updateASRBackendMenuState()
            refreshQwenServerStatus()
            applyHotwordConfig(Self.loadHotwordConfig(), logPrefix: "http asr profile selected: \(profile.rawValue)")
            logger.write("http asr profile selection saved: \(url.path)")
        } catch {
            logger.write("http asr profile selection failed: \(error.localizedDescription)")
            state = .error("Could not save HTTP ASR profile: \(error.localizedDescription)")
        }
    }

    private static func loadTranscriptionConfiguration() -> TranscriptionConfiguration {
        var configuration = TranscriptionConfiguration.fromEnvironment()
        configuration.initialPrompt = loadHotwordConfig().asrPrompt()
        return configuration
    }

    private func updateASRBackendMenuState() {
        for (backend, item) in asrBackendMenuItems {
            item.state = backend == transcriptionConfiguration.backend ? .on : .off
        }
        for (profile, item) in localWhisperProfileMenuItems {
            item.state = profile == transcriptionConfiguration.localWhisperProfile ? .on : .off
        }
        for (profile, item) in httpASRProfileMenuItems {
            item.state = profile == transcriptionConfiguration.httpASRProfile ? .on : .off
        }
    }

    @objc private func refreshQwenServerStatus() {
        let controller = QwenServerController(configuration: transcriptionConfiguration)
        guard controller.isSupported else {
            qwenServerStatusMenuItem.title = "Qwen Server: Not selected"
            return
        }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                let health = try controller.health()
                self?.logger.write(
                    "qwen server health \(health.logDetails)"
                )
                DispatchQueue.main.async {
                    self?.qwenServerStatusMenuItem.title = health.menuTitle
                }
            } catch {
                self?.logger.write("qwen server health failed: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    self?.qwenServerStatusMenuItem.title = "Qwen Server: Stopped"
                }
            }
        }
    }

    @objc private func startQwenServer() {
        runQwenServerAction("qwen server started") { controller in
            try controller.start()
            Thread.sleep(forTimeInterval: 0.5)
            return try controller.health(timeoutSeconds: 2)
        }
    }

    @objc private func stopQwenServer() {
        runQwenServerAction("qwen server stopped") { controller in
            try controller.stop()
            return QwenServerHealth(ok: false, model: nil, modelLoaded: false, latencyMS: 0, deviceMap: nil, dtype: nil)
        }
    }

    @objc private func warmUpQwenServer() {
        runQwenServerAction("qwen server warmup") { controller in
            try controller.warmUp()
        }
    }

    private func runQwenServerAction(
        _ logPrefix: String,
        work: @escaping (QwenServerController) throws -> QwenServerHealth
    ) {
        let controller = QwenServerController(configuration: transcriptionConfiguration)
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                let health = try work(controller)
                self?.logger.write(
                    "\(logPrefix) \(health.logDetails)"
                )
                DispatchQueue.main.async {
                    self?.qwenServerStatusMenuItem.title = health.menuTitle
                    if self?.state != .recording && self?.state != .transcribing && self?.state != .pasting {
                        self?.state = .idle
                    }
                }
            } catch {
                self?.logger.write("\(logPrefix) failed: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    self?.qwenServerStatusMenuItem.title = "Qwen Server: Error"
                    self?.state = .error(error.localizedDescription)
                }
            }
        }
    }

    private func applyHotwordConfig(_ hotwordConfig: HotwordConfig, logPrefix: String) {
        transcriptionConfiguration.initialPrompt = hotwordConfig.asrPrompt()
        workflow = Self.makeWorkflow(
            transcriptionConfiguration: transcriptionConfiguration,
            hotwordConfig: hotwordConfig,
            recorder: recorder,
            eventLogger: { [logger] message in logger.write(message) }
        )
        logger.write("\(logPrefix): protected_terms=\(hotwordConfig.protectedTerms.count), replacements=\(hotwordConfig.replacements.count)")
        if state != .recording && state != .transcribing && state != .pasting {
            state = .idle
            showReadyFeedback()
        }
    }

    @objc private func requestMicrophonePermission() {
        recorder.requestMicrophonePermission { [weak self] granted in
            DispatchQueue.main.async {
                self?.state = granted ? .idle : .error("Microphone permission denied")
                self?.refreshPermissionStatus()
            }
        }
    }

    @objc private func requestAccessibilityPermission() {
        let trusted = requestAccessibilityTrustPrompt()
        state = trusted ? .idle : .error("Accessibility permission not granted")
        refreshPermissionStatus()
    }

    @objc private func openAccessibilitySettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") else {
            return
        }
        NSWorkspace.shared.open(url)
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func startRecording() {
        guard state.canBeginRecording else {
            logger.write("recording request ignored in state: \(state.title)")
            return
        }
        logger.write("recording requested")
        state = .recording
        do {
            let start = Date()
            try recorder.startRecording()
            recordingStartedAt = Date()
            logger.write("recorder started in \(Self.durationText(since: start))")
        } catch {
            recordingStartedAt = nil
            logger.write("recorder failed: \(error.localizedDescription)")
            state = .error(error.localizedDescription)
        }
    }

    private func warmUpRecorder() {
        logger.write("recorder warmup requested")
        let snapshot = PermissionDiagnostics.snapshot(expectedInputDeviceName: expectedInputDeviceName)
        switch snapshot.microphone {
        case .granted:
            performRecorderWarmUp()
        case .notDetermined:
            logger.write("microphone permission request started")
            recorder.requestMicrophonePermission { [weak self] granted in
                guard let self else {
                    return
                }
                logger.write("microphone permission request completed: \(granted ? "granted" : "denied")")
                DispatchQueue.main.async {
                    self.refreshPermissionStatus()
                }
                if granted {
                    self.performRecorderWarmUp()
                }
            }
        case .denied, .restricted:
            logger.write("recorder warmup skipped: Microphone permission is denied or restricted.")
        case .unknown:
            logger.write("recorder warmup skipped: Microphone permission is unknown.")
        }
    }

    private func performRecorderWarmUp() {
        let start = Date()
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self else {
                return
            }
            do {
                try recorder.warmUp()
                logger.write("recorder warmup completed in \(Self.durationText(since: start))")
            } catch {
                logger.write("recorder warmup skipped: \(error.localizedDescription)")
            }
        }
    }

    private func finishRecording() {
        guard state == .recording else {
            logger.write("finish recording ignored in state: \(state.title)")
            return
        }

        logger.write("recording finish requested")
        do {
            let stopStartedAt = Date()
            let audioURL = try recorder.stopRecording()
            let stoppedAt = Date()
            logger.write("recorder stopped: \(audioURL.lastPathComponent)")
            if let recordingStartedAt {
                logger.write(
                    "latency recording_ms=\(Self.milliseconds(from: recordingStartedAt, to: stoppedAt)) "
                        + "stop_recording_ms=\(Self.milliseconds(since: stopStartedAt)) "
                        + "audio=\(audioURL.lastPathComponent)"
                )
            }
            recordingStartedAt = nil
            logger.write("latency audio_bytes=\(Self.fileSizeBytes(audioURL)) audio=\(audioURL.lastPathComponent)")
            state = .transcribing
            let recordingFinishedAt = Date()
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.transcribeAndPaste(audioURL: audioURL, recordingFinishedAt: recordingFinishedAt)
            }
        } catch {
            recordingStartedAt = nil
            logger.write("recording finish failed: \(error.localizedDescription)")
            state = .error(error.localizedDescription)
        }
    }

    private func transcribeAndPaste(audioURL: URL, recordingFinishedAt: Date) {
        do {
            let transcriptionStartedAt = Date()
            let result = try workflow.transcribeAndProcessWithMetrics(audioURL: audioURL)
            let finalText = result.finalText
            let transcriptionMS = Self.milliseconds(since: transcriptionStartedAt)
            logger.write(
                "latency workflow_transcribe_ms=\(result.transcribeMS) "
                    + "workflow_postprocess_ms=\(result.postprocessMS) "
                    + "raw_chars=\(result.rawText.count) final_chars=\(finalText.count)"
            )
            logger.write("latency workflow_postprocess_ms=\(result.postprocessMS) final_chars=\(finalText.count)")
            logger.write("latency transcription_ms=\(transcriptionMS) audio=\(audioURL.lastPathComponent) chars=\(finalText.count)")
            logger.write("transcription completed")
            DispatchQueue.main.async { [weak self] in
                self?.paste(finalText, audioURL: audioURL, recordingFinishedAt: recordingFinishedAt)
            }
        } catch {
            DispatchQueue.main.async { [weak self] in
                self?.workflow.cleanup(audioURL)
                self?.logger.write("transcription failed: \(error.localizedDescription)")
                self?.state = .error(error.localizedDescription)
            }
        }
    }

    private func paste(_ text: String, audioURL: URL, recordingFinishedAt: Date) {
        do {
            state = .pasting
            let pasteStartedAt = Date()
            try workflow.pasteAndCleanup(text, audioURL: audioURL)
            logger.write("latency paste_ms=\(Self.milliseconds(since: pasteStartedAt)) chars=\(text.count)")
            logger.write("latency e2e_ms=\(Self.milliseconds(since: recordingFinishedAt)) chars=\(text.count)")
            logger.write("paste completed")
            state = .idle
            feedbackHUD.show(AppFeedbackFactory.completed)
        } catch {
            logger.write("paste failed: \(error.localizedDescription)")
            state = .error(error.localizedDescription)
        }
    }

    private func showReadyFeedback() {
        feedbackHUD.show(AppFeedbackFactory.ready(hotkeyDescription: hotkeyConfiguration.displayName))
    }

    private func showStateFeedback() {
        if let feedback = AppFeedbackFactory.feedback(for: state) {
            feedbackHUD.show(feedback)
        } else {
            feedbackHUD.hide()
        }
    }

    private func requestAccessibilityTrustPrompt() -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        let trusted = AXIsProcessTrustedWithOptions(options)
        logger.write("accessibility trust prompt requested: \(trusted ? "trusted" : "not trusted")")
        return trusted
    }

    private static func durationText(since start: Date) -> String {
        String(format: "%.3fs", Date().timeIntervalSince(start))
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }

    private static func milliseconds(from start: Date, to end: Date) -> Int {
        Int(end.timeIntervalSince(start) * 1000)
    }

    private static func fileSizeBytes(_ url: URL) -> Int64 {
        let values = try? url.resourceValues(forKeys: [.fileSizeKey])
        return Int64(values?.fileSize ?? 0)
    }

    private func shortTitle(for state: AppState) -> String {
        switch state {
        case .idle:
            return " SwitchType"
        case .recording:
            return " REC"
        case .transcribing:
            return " ASR"
        case .pasting:
            return " PST"
        case .error:
            return " ERR"
        }
    }
}
