import ApplicationServices
import AVFoundation
import Foundation

public enum PermissionState: String, Equatable {
    case granted
    case denied
    case notDetermined
    case restricted
    case unknown

    public var displayText: String {
        switch self {
        case .granted:
            return "granted"
        case .denied:
            return "denied"
        case .notDetermined:
            return "not determined"
        case .restricted:
            return "restricted"
        case .unknown:
            return "unknown"
        }
    }
}

public struct PermissionSnapshot: Equatable {
    public var microphone: PermissionState
    public var accessibility: PermissionState
    public var inputDeviceName: String?
    public var expectedInputDeviceName: String?

    public init(
        microphone: PermissionState,
        accessibility: PermissionState,
        inputDeviceName: String? = nil,
        expectedInputDeviceName: String? = nil
    ) {
        self.microphone = microphone
        self.accessibility = accessibility
        self.inputDeviceName = inputDeviceName
        self.expectedInputDeviceName = expectedInputDeviceName
    }

    public var summary: String {
        let trimmedInputName = inputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let input = if let trimmedInputName, !trimmedInputName.isEmpty {
            trimmedInputName
        } else {
            "unknown"
        }
        var parts = [
            "Microphone: \(microphone.displayText)",
            "Accessibility: \(accessibility.displayText)",
            "Input: \(input)"
        ]
        if let expected = expectedInputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines), !expected.isEmpty {
            let status: String
            if input == "unknown" {
                status = "unavailable"
            } else if AudioRecorder.inputDeviceName(input, matchesExpected: expected) {
                status = "matched"
            } else {
                status = "mismatch"
            }
            parts.append("Expected input: \(expected) (\(status))")
        }
        return parts.joined(separator: ", ")
    }

    public var allRequiredGranted: Bool {
        microphone == .granted && accessibility == .granted
    }
}

public enum PermissionDiagnostics {
    public static func snapshot(expectedInputDeviceName: String? = nil) -> PermissionSnapshot {
        PermissionSnapshot(
            microphone: microphoneState(),
            accessibility: AXIsProcessTrusted() ? .granted : .denied,
            inputDeviceName: defaultInputDeviceName(),
            expectedInputDeviceName: expectedInputDeviceName
        )
    }

    private static func microphoneState() -> PermissionState {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return .granted
        case .denied:
            return .denied
        case .notDetermined:
            return .notDetermined
        case .restricted:
            return .restricted
        @unknown default:
            return .unknown
        }
    }

    private static func defaultInputDeviceName() -> String? {
        AVCaptureDevice.default(for: .audio)?.localizedName
    }
}
