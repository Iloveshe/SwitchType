import Foundation

public enum AppState: Equatable {
    case idle
    case recording
    case transcribing
    case pasting
    case error(String)

    public var title: String {
        switch self {
        case .idle:
            return "SwitchType: Idle"
        case .recording:
            return "SwitchType: Recording"
        case .transcribing:
            return "SwitchType: Transcribing"
        case .pasting:
            return "SwitchType: Pasting"
        case .error(let message):
            return "SwitchType: \(message)"
        }
    }

    public var canBeginRecording: Bool {
        switch self {
        case .idle, .error:
            return true
        case .recording, .transcribing, .pasting:
            return false
        }
    }
}
