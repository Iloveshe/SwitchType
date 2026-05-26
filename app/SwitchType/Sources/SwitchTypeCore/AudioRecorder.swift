import AVFoundation
import Foundation

public enum AudioRecorderError: Error, LocalizedError {
    case alreadyRecording
    case notRecording
    case microphonePermissionDenied
    case inputDeviceUnavailable
    case inputDeviceMismatch
    case recordingDidNotStart
    case recordingTooShort

    public var errorDescription: String? {
        switch self {
        case .alreadyRecording:
            return "Recording is already active."
        case .notRecording:
            return "Recording is not active."
        case .microphonePermissionDenied:
            return "Microphone permission is denied or restricted."
        case .inputDeviceUnavailable:
            return "Expected microphone input device is unavailable."
        case .inputDeviceMismatch:
            return "Current microphone input device does not match the expected device."
        case .recordingDidNotStart:
            return "Recording did not start."
        case .recordingTooShort:
            return "Recording is too short. Hold the configured hotkey while speaking."
        }
    }
}

public final class AudioRecorder: NSObject {
    public static let recordingFileExtension = "wav"
    public static let minimumRecordingDurationSeconds: TimeInterval = 0.25
    public static let recordingSettings: [String: Any] = [
        AVFormatIDKey: Int(kAudioFormatLinearPCM),
        AVSampleRateKey: 16_000.0,
        AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsFloatKey: false,
        AVLinearPCMIsBigEndianKey: false
    ]

    private let expectedInputDeviceName: String?
    private var recorder: AVAudioRecorder?
    private var currentURL: URL?

    public init(expectedInputDeviceName: String? = ProcessInfo.processInfo.environment["SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"]) {
        let trimmedExpectedName = expectedInputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.expectedInputDeviceName = if let trimmedExpectedName, !trimmedExpectedName.isEmpty {
            trimmedExpectedName
        } else {
            nil
        }
        super.init()
    }

    public func requestMicrophonePermission(_ completion: @escaping (Bool) -> Void) {
        AVCaptureDevice.requestAccess(for: .audio, completionHandler: completion)
    }

    public static func validateMicrophonePermission(_ state: PermissionState) throws {
        switch state {
        case .denied, .restricted:
            throw AudioRecorderError.microphonePermissionDenied
        case .granted, .notDetermined, .unknown:
            return
        }
    }

    public static func normalizedInputDeviceName(_ name: String) -> String {
        String(name.unicodeScalars.filter { scalar in
            CharacterSet.alphanumerics.contains(scalar)
        }).lowercased()
    }

    public static func inputDeviceName(_ actualName: String, matchesExpected expectedName: String) -> Bool {
        let actual = actualName.trimmingCharacters(in: .whitespacesAndNewlines)
        let expected = expectedName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !actual.isEmpty, !expected.isEmpty else {
            return false
        }
        if actual.compare(expected, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame {
            return true
        }
        return normalizedInputDeviceName(actual).contains(normalizedInputDeviceName(expected))
    }

    public static func validateExpectedInputDevice(
        _ snapshot: PermissionSnapshot,
        expectedInputDeviceName: String?
    ) throws {
        guard let expectedInputDeviceName = expectedInputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines),
              !expectedInputDeviceName.isEmpty else {
            return
        }
        guard let actualInputDeviceName = snapshot.inputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines),
              !actualInputDeviceName.isEmpty else {
            throw AudioRecorderError.inputDeviceUnavailable
        }
        guard inputDeviceName(actualInputDeviceName, matchesExpected: expectedInputDeviceName) else {
            throw AudioRecorderError.inputDeviceMismatch
        }
    }

    public static func validateRecordingStarted(_ started: Bool) throws {
        guard started else {
            throw AudioRecorderError.recordingDidNotStart
        }
    }

    public static func validateRecordingDuration(_ duration: TimeInterval) throws {
        guard duration >= minimumRecordingDurationSeconds else {
            throw AudioRecorderError.recordingTooShort
        }
    }

    public func startRecording() throws {
        guard recorder == nil else {
            throw AudioRecorderError.alreadyRecording
        }
        let permissionSnapshot = PermissionDiagnostics.snapshot()
        try Self.validateMicrophonePermission(permissionSnapshot.microphone)
        try Self.validateExpectedInputDevice(permissionSnapshot, expectedInputDeviceName: expectedInputDeviceName)

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("switchtype-\(UUID().uuidString)")
            .appendingPathExtension(Self.recordingFileExtension)
        let recorder = try AVAudioRecorder(url: url, settings: Self.recordingSettings)
        recorder.prepareToRecord()
        do {
            try Self.validateRecordingStarted(recorder.record())
        } catch {
            cleanup(url)
            throw error
        }
        self.recorder = recorder
        self.currentURL = url
    }

    public func warmUp() throws {
        guard recorder == nil else {
            return
        }
        let permissionSnapshot = PermissionDiagnostics.snapshot()
        guard permissionSnapshot.microphone == .granted else {
            throw AudioRecorderError.microphonePermissionDenied
        }
        try Self.validateMicrophonePermission(permissionSnapshot.microphone)
        try Self.validateExpectedInputDevice(permissionSnapshot, expectedInputDeviceName: expectedInputDeviceName)

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("switchtype-warmup-\(UUID().uuidString)")
            .appendingPathExtension(Self.recordingFileExtension)
        defer { cleanup(url) }

        let recorder = try AVAudioRecorder(url: url, settings: Self.recordingSettings)
        recorder.prepareToRecord()
        try Self.validateRecordingStarted(recorder.record())
        Thread.sleep(forTimeInterval: 0.05)
        recorder.stop()
    }

    public func stopRecording() throws -> URL {
        guard let recorder, let currentURL else {
            throw AudioRecorderError.notRecording
        }
        let duration = recorder.currentTime
        recorder.stop()
        self.recorder = nil
        self.currentURL = nil
        do {
            try Self.validateRecordingDuration(duration)
        } catch {
            cleanup(currentURL)
            throw error
        }
        return currentURL
    }

    public func cleanup(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }
}
