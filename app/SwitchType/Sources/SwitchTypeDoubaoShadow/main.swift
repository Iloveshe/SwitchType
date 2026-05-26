import Darwin
import Foundation
import SwitchTypeCore

setbuf(stdout, nil)
setbuf(stderr, nil)

struct ShadowSegment: Encodable {
    let id: String
    let audio: String
    let recordedAt: String
    let source: String
    var reference: String?
    var textCaptureStatus: String?
    var textCaptureReason: String?
    var textCaptureAttempts: Int?
    var textCaptureElapsedSeconds: Double?
    var textCaptureBeforeLength: Int?
    var textCaptureAfterLength: Int?
    var textCaptureBeforeProcessIdentifier: Int?
    var textCaptureAfterProcessIdentifier: Int?
    var textCaptureBeforeSelectionLocation: Int?
    var textCaptureBeforeSelectionLength: Int?
    var textCaptureAfterSelectionLocation: Int?
    var textCaptureAfterSelectionLength: Int?
    var recordingStopReason: String

    enum CodingKeys: String, CodingKey {
        case id
        case audio
        case recordedAt = "recorded_at"
        case source
        case reference
        case textCaptureStatus = "text_capture_status"
        case textCaptureReason = "text_capture_reason"
        case textCaptureAttempts = "text_capture_attempts"
        case textCaptureElapsedSeconds = "text_capture_elapsed_seconds"
        case textCaptureBeforeLength = "text_capture_before_length"
        case textCaptureAfterLength = "text_capture_after_length"
        case textCaptureBeforeProcessIdentifier = "text_capture_before_process_identifier"
        case textCaptureAfterProcessIdentifier = "text_capture_after_process_identifier"
        case textCaptureBeforeSelectionLocation = "text_capture_before_selection_location"
        case textCaptureBeforeSelectionLength = "text_capture_before_selection_length"
        case textCaptureAfterSelectionLocation = "text_capture_after_selection_location"
        case textCaptureAfterSelectionLength = "text_capture_after_selection_length"
        case recordingStopReason = "recording_stop_reason"
    }
}

enum ShadowRecorderError: Error, LocalizedError {
    case missingValue(String)

    var errorDescription: String? {
        switch self {
        case .missingValue(let option):
            return "Missing value for \(option)."
        }
    }
}

func argument(after option: String, in arguments: [String]) throws -> String? {
    guard let index = arguments.firstIndex(of: option) else {
        return nil
    }
    let valueIndex = arguments.index(after: index)
    guard valueIndex < arguments.endIndex else {
        throw ShadowRecorderError.missingValue(option)
    }
    return arguments[valueIndex]
}

func pathByAppending(_ component: String, to path: String) -> String {
    if path.hasSuffix("/") {
        return path + component
    }
    return path + "/" + component
}

final class ShadowCaptureSession {
    private let recorder: AudioRecorder
    private let outputDirPath: String
    private let outputDirURL: URL
    private let segmentsPath: String
    private let segmentsURL: URL
    private let focusedTextCapture: FocusedTextCapture?
    private let textCaptureDelaySeconds: TimeInterval
    private let textCaptureTimeoutSeconds: TimeInterval
    private let textCapturePollIntervalSeconds: TimeInterval = 0.5
    private let idleSnapshotIntervalSeconds: TimeInterval = 0.5
    private let idleSnapshotFreshnessSeconds: TimeInterval = 10.0
    private let isoFormatter = ISO8601DateFormatter()
    private let idFormatter: DateFormatter
    private var currentStartedAt: Date?
    private var currentTextSnapshots: [FocusedTextSnapshot] = []
    private var idleBaselineLogged = false
    private var idleSnapshotMonitorStarted = false
    private var lastIdleTextSnapshot: FocusedTextSnapshot?
    private var lastIdleTextSnapshotAt: Date?

    var isRecording: Bool {
        currentStartedAt != nil
    }

    init(
        recorder: AudioRecorder,
        outputDirPath: String,
        segmentsPath: String,
        focusedTextCapture: FocusedTextCapture? = nil,
        textCaptureDelaySeconds: TimeInterval = 1.5,
        textCaptureTimeoutSeconds: TimeInterval = 4.0
    ) {
        self.recorder = recorder
        self.outputDirPath = outputDirPath
        self.outputDirURL = URL(fileURLWithPath: outputDirPath)
        self.segmentsPath = segmentsPath
        self.segmentsURL = URL(fileURLWithPath: segmentsPath)
        self.focusedTextCapture = focusedTextCapture
        self.textCaptureDelaySeconds = textCaptureDelaySeconds
        self.textCaptureTimeoutSeconds = textCaptureTimeoutSeconds
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        self.idFormatter = formatter
    }

    func prepare() throws {
        try FileManager.default.createDirectory(at: outputDirURL, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: segmentsURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        startIdleSnapshotMonitor()
    }

    @discardableResult
    func start() -> Date? {
        guard currentStartedAt == nil else {
            return nil
        }
        do {
            currentTextSnapshots = []
            let startSnapshot = focusedTextCapture?.snapshot()
            let idleSnapshot = freshLastIdleTextSnapshot()
            if let startSnapshot {
                currentTextSnapshots.append(startSnapshot)
            }
            if let idleSnapshot {
                currentTextSnapshots.append(idleSnapshot)
                if startSnapshot == nil {
                    print("Using last idle focused text snapshot as recording baseline.")
                }
            }
            try recorder.startRecording()
            let startedAt = Date()
            currentStartedAt = startedAt
            print("Shadow recording started.")
            scheduleMissingBeforeSnapshotRetry(startedAt: startedAt)
            return startedAt
        } catch {
            currentTextSnapshots = []
            print("Shadow recording start failed: \(error.localizedDescription)")
            return nil
        }
    }

    func stopIfRecording(startedAt expectedStartedAt: Date, reason: String) {
        guard currentStartedAt == expectedStartedAt else {
            return
        }
        stop(reason: reason)
    }

    private func startIdleSnapshotMonitor() {
        guard focusedTextCapture != nil, !idleSnapshotMonitorStarted else {
            return
        }
        idleSnapshotMonitorStarted = true
        scheduleIdleSnapshot()
    }

    private func scheduleIdleSnapshot() {
        DispatchQueue.main.asyncAfter(deadline: .now() + idleSnapshotIntervalSeconds) { [weak self] in
            self?.captureIdleSnapshot()
        }
    }

    private func captureIdleSnapshot() {
        defer {
            scheduleIdleSnapshot()
        }
        guard currentStartedAt == nil else {
            return
        }
        guard let snapshot = focusedTextCapture?.snapshot() else {
            return
        }
        lastIdleTextSnapshot = snapshot
        lastIdleTextSnapshotAt = Date()
        if !idleBaselineLogged {
            idleBaselineLogged = true
            print("Focused text idle baseline captured.")
        }
    }

    private func freshLastIdleTextSnapshot(now: Date = Date()) -> FocusedTextSnapshot? {
        guard let snapshot = lastIdleTextSnapshot,
              let capturedAt = lastIdleTextSnapshotAt,
              now.timeIntervalSince(capturedAt) <= idleSnapshotFreshnessSeconds else {
            return nil
        }
        return snapshot
    }

    private func scheduleMissingBeforeSnapshotRetry(startedAt: Date) {
        guard focusedTextCapture != nil, currentTextSnapshots.isEmpty else {
            return
        }
        for delay in [0.05, 0.25] {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.retryMissingBeforeSnapshot(startedAt: startedAt)
            }
        }
    }

    private func retryMissingBeforeSnapshot(startedAt expectedStartedAt: Date) {
        guard currentStartedAt == expectedStartedAt, currentTextSnapshots.isEmpty else {
            return
        }
        guard let snapshot = focusedTextCapture?.snapshot() else {
            return
        }
        currentTextSnapshots.append(snapshot)
        print("Recovered focused text before snapshot during recording.")
    }

    func stop(reason: String) {
        guard let startedAt = currentStartedAt else {
            return
        }
        currentStartedAt = nil
        do {
            let temporaryURL = try recorder.stopRecording()
            let id = "doubao-shadow-\(idFormatter.string(from: startedAt))-\(UUID().uuidString.prefix(8).lowercased())"
            let filename = "\(id).wav"
            let targetURL = outputDirURL.appendingPathComponent(filename)
            try? FileManager.default.removeItem(at: targetURL)
            try FileManager.default.moveItem(at: temporaryURL, to: targetURL)
            let audioPath = pathByAppending(filename, to: outputDirPath)
            let segment = ShadowSegment(
                id: id,
                audio: audioPath,
                recordedAt: isoFormatter.string(from: startedAt),
                source: "doubao-shadow",
                reference: nil,
                textCaptureStatus: nil,
                textCaptureReason: nil,
                textCaptureAttempts: nil,
                textCaptureElapsedSeconds: nil,
                textCaptureBeforeLength: nil,
                textCaptureAfterLength: nil,
                textCaptureBeforeProcessIdentifier: nil,
                textCaptureAfterProcessIdentifier: nil,
                textCaptureBeforeSelectionLocation: nil,
                textCaptureBeforeSelectionLength: nil,
                textCaptureAfterSelectionLocation: nil,
                textCaptureAfterSelectionLength: nil,
                recordingStopReason: reason
            )
            let beforeSnapshots = currentTextSnapshots
            currentTextSnapshots = []
            print("Saved shadow audio: \(audioPath)")
            if focusedTextCapture != nil, textCaptureTimeoutSeconds > 0 {
                let initialDelay = max(textCaptureDelaySeconds, 0)
                let deadline = Date().addingTimeInterval(max(textCaptureTimeoutSeconds, initialDelay))
                print("Waiting up to \(textCaptureTimeoutSeconds)s for focused text capture.")
                let captureStartedAt = Date()
                DispatchQueue.main.asyncAfter(deadline: .now() + initialDelay) { [weak self] in
                    self?.finalizeWhenReferenceAvailable(
                        segment: segment,
                        beforeSnapshots: beforeSnapshots,
                        deadline: deadline,
                        captureStartedAt: captureStartedAt,
                        afterSnapshots: []
                    )
                }
                return
            }
            finalize(segment: segment, beforeSnapshots: beforeSnapshots)
        } catch {
            currentTextSnapshots = []
            print("Shadow recording ignored: \(error.localizedDescription)")
        }
    }

    private func finalizeWhenReferenceAvailable(
        segment: ShadowSegment,
        beforeSnapshots: [FocusedTextSnapshot],
        deadline: Date,
        captureStartedAt: Date,
        afterSnapshots: [FocusedTextSnapshot?]
    ) {
        var updatedSnapshots = afterSnapshots
        updatedSnapshots.append(focusedTextCapture?.snapshot())
        let match = FocusedTextDelta.firstCapturedMatch(
            beforeCandidates: beforeSnapshots.map(Optional.some),
            afterCandidates: updatedSnapshots
        )
        if match.analysis.insertedText != nil || Date() >= deadline {
            finalize(
                segment: segment,
                beforeSnapshots: beforeSnapshots,
                match: match,
                afterSnapshots: updatedSnapshots,
                captureStartedAt: captureStartedAt
            )
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + textCapturePollIntervalSeconds) { [weak self] in
            self?.finalizeWhenReferenceAvailable(
                segment: segment,
                beforeSnapshots: beforeSnapshots,
                deadline: deadline,
                captureStartedAt: captureStartedAt,
                afterSnapshots: updatedSnapshots
            )
        }
    }

    private func finalize(
        segment: ShadowSegment,
        beforeSnapshots: [FocusedTextSnapshot] = [],
        match precomputedMatch: FocusedTextDeltaMatch? = nil,
        afterSnapshots precomputedAfterSnapshots: [FocusedTextSnapshot?]? = nil,
        captureStartedAt: Date? = nil
    ) {
        var finalSegment = segment
        if let focusedTextCapture {
            let afterSnapshots = precomputedAfterSnapshots ?? [focusedTextCapture.snapshot()]
            let match = precomputedMatch ?? FocusedTextDelta.firstCapturedMatch(
                beforeCandidates: beforeSnapshots.map(Optional.some),
                afterCandidates: afterSnapshots
            )
            let beforeSnapshot = match.beforeSnapshot
            let afterSnapshot = match.afterSnapshot ?? afterSnapshots.last ?? nil
            let delta = match.analysis
            finalSegment.textCaptureAttempts = afterSnapshots.count
            finalSegment.textCaptureElapsedSeconds = captureStartedAt.map {
                roundedSeconds(Date().timeIntervalSince($0))
            }
            finalSegment.textCaptureBeforeLength = beforeSnapshot?.value.count
            finalSegment.textCaptureAfterLength = afterSnapshot?.value.count
            finalSegment.textCaptureBeforeProcessIdentifier = beforeSnapshot?.processIdentifier.map(Int.init)
            finalSegment.textCaptureAfterProcessIdentifier = afterSnapshot?.processIdentifier.map(Int.init)
            finalSegment.textCaptureBeforeSelectionLocation = beforeSnapshot?.selectedRange?.location
            finalSegment.textCaptureBeforeSelectionLength = beforeSnapshot?.selectedRange?.length
            finalSegment.textCaptureAfterSelectionLocation = afterSnapshot?.selectedRange?.location
            finalSegment.textCaptureAfterSelectionLength = afterSnapshot?.selectedRange?.length
            if let reference = delta.insertedText {
                finalSegment.reference = reference
                finalSegment.textCaptureStatus = "captured"
                print("Captured focused text reference: \(reference)")
            } else {
                finalSegment.textCaptureStatus = "unmatched"
                finalSegment.textCaptureReason = delta.reason
                print("Focused text reference was not captured (\(delta.reason)); reconcile will prompt for this segment.")
            }
        }
        do {
            try append(finalSegment)
            print("Updated segment log: \(segmentsPath)")
        } catch {
            print("Shadow segment log update failed: \(error.localizedDescription)")
        }
    }

    private func roundedSeconds(_ seconds: TimeInterval) -> Double {
        (seconds * 1000).rounded() / 1000
    }

    private func append(_ segment: ShadowSegment) throws {
        let data = try JSONEncoder().encode(segment)
        guard let line = String(data: data, encoding: .utf8)?.appending("\n"),
              let lineData = line.data(using: .utf8) else {
            return
        }
        if FileManager.default.fileExists(atPath: segmentsURL.path) {
            let handle = try FileHandle(forWritingTo: segmentsURL)
            try handle.seekToEnd()
            try handle.write(contentsOf: lineData)
            try handle.close()
        } else {
            FileManager.default.createFile(atPath: segmentsURL.path, contents: lineData)
        }
    }
}

let arguments = Array(CommandLine.arguments.dropFirst())
let outputDir = try argument(after: "--output-dir", in: arguments) ?? "bench/samples/doubao-shadow/audio"
let segments = try argument(after: "--segments", in: arguments) ?? "bench/samples/doubao-shadow/segments.jsonl"
let expectedInputDevice = try argument(after: "--expected-input-device", in: arguments)
let hotkeyKeyCode = try argument(after: "--hotkey-key-code", in: arguments)
let hotkeyModifiers = try argument(after: "--hotkey-modifiers", in: arguments)
let recordSeconds = TimeInterval(try argument(after: "--record-seconds", in: arguments) ?? "")
let preRecordDelay = TimeInterval(try argument(after: "--pre-record-delay-seconds", in: arguments) ?? "") ?? 0.0
let maxRecordSeconds = TimeInterval(try argument(after: "--max-record-seconds", in: arguments) ?? "") ?? 60.0
let captureFocusedText = arguments.contains("--capture-focused-text")
let debugHotkeyEvents = arguments.contains("--debug-hotkey-events")
let textCaptureDelay = TimeInterval(try argument(after: "--text-capture-delay-seconds", in: arguments) ?? "") ?? 1.5
let textCaptureTimeout = TimeInterval(try argument(after: "--text-capture-timeout-seconds", in: arguments) ?? "") ?? 4.0
let oneShotTextCaptureDrainSlack: TimeInterval = 0.75
var hotkeyEnvironment = ProcessInfo.processInfo.environment
if let hotkeyKeyCode {
    hotkeyEnvironment["SWITCHTYPE_HOTKEY_KEY_CODE"] = hotkeyKeyCode
}
if let hotkeyModifiers {
    hotkeyEnvironment["SWITCHTYPE_HOTKEY_MODIFIERS"] = hotkeyModifiers
}
let hotkeyConfiguration = HotkeyConfiguration.from(environment: hotkeyEnvironment)

let recorder = AudioRecorder(expectedInputDeviceName: expectedInputDevice)
let captureSession = ShadowCaptureSession(
    recorder: recorder,
    outputDirPath: outputDir,
    segmentsPath: segments,
    focusedTextCapture: captureFocusedText ? FocusedTextCapture() : nil,
    textCaptureDelaySeconds: textCaptureDelay,
    textCaptureTimeoutSeconds: textCaptureTimeout
)
try captureSession.prepare()

if let recordSeconds {
    if preRecordDelay > 0 {
        print("Doubao shadow one-shot recording will start in \(preRecordDelay)s. Focus the target text field and start Doubao voice input now.")
        RunLoop.main.run(until: Date().addingTimeInterval(preRecordDelay))
    }
    print("Doubao shadow one-shot recording started for \(recordSeconds)s.")
    guard captureSession.start() != nil else {
        exit(2)
    }
    RunLoop.main.run(until: Date().addingTimeInterval(recordSeconds))
    captureSession.stop(reason: "record_seconds")
    if captureFocusedText, textCaptureTimeout > 0 {
        RunLoop.main.run(
            until: Date().addingTimeInterval(max(textCaptureDelay, textCaptureTimeout) + oneShotTextCaptureDrainSlack)
        )
    }
    exit(0)
}

let hotkeyController = HotkeyController(consumeEvents: false, configuration: hotkeyConfiguration)
if debugHotkeyEvents {
    hotkeyController.onEventObserved = { diagnostic in
        print("Hotkey event: \(diagnostic.summary)")
    }
}
hotkeyController.onRecordingRequested = {
    guard let startedAt = captureSession.start() else {
        return
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + maxRecordSeconds) {
        if captureSession.isRecording {
            print("Maximum recording duration reached.")
            captureSession.stopIfRecording(startedAt: startedAt, reason: "max_duration")
        }
    }
}
hotkeyController.onRecordingFinished = {
    captureSession.stop(reason: "hotkey_released")
}

try hotkeyController.start()
print("Doubao shadow recorder armed. It records local mic audio while the configured hotkey is held.")
print("The listener does not consume the hotkey, so Doubao can keep receiving the same shortcut.")
print("Hotkey key code: \(hotkeyConfiguration.keyCode)")
print("Hotkey modifiers: \(hotkeyEnvironment["SWITCHTYPE_HOTKEY_MODIFIERS"] ?? "option")")
print("Focused text capture: \(captureFocusedText ? "enabled" : "disabled")")
print("Debug hotkey events: \(debugHotkeyEvents ? "enabled" : "disabled")")
print("Audio output: \(outputDir)")
print("Segment log: \(segments)")
print("Press Control-C to stop.")
RunLoop.main.run()
