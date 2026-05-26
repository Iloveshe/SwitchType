import Foundation

public struct AppFeedback: Equatable {
    public let title: String
    public let detail: String?
    public let pulses: Bool
    public let autoHideSeconds: TimeInterval?
    public let isError: Bool

    public init(
        title: String,
        detail: String? = nil,
        pulses: Bool = false,
        autoHideSeconds: TimeInterval? = nil,
        isError: Bool = false
    ) {
        self.title = title
        self.detail = detail
        self.pulses = pulses
        self.autoHideSeconds = autoHideSeconds
        self.isError = isError
    }
}

public enum AppFeedbackFactory {
    public static func ready(hotkeyDescription: String) -> AppFeedback {
        AppFeedback(
            title: "SwitchType ready",
            detail: "Hold \(hotkeyDescription)",
            pulses: true,
            autoHideSeconds: 1.8
        )
    }

    public static let completed = AppFeedback(
        title: "Inserted",
        detail: nil,
        pulses: false,
        autoHideSeconds: 1.0
    )

    public static func feedback(for state: AppState) -> AppFeedback? {
        switch state {
        case .idle:
            return nil
        case .recording:
            return AppFeedback(title: "Listening", detail: "Release to transcribe", pulses: true)
        case .transcribing:
            return AppFeedback(title: "Transcribing", detail: "Local ASR is running", pulses: true)
        case .pasting:
            return AppFeedback(title: "Inserting", detail: nil, pulses: false)
        case .error(let message):
            return AppFeedback(
                title: "SwitchType needs attention",
                detail: message,
                pulses: false,
                autoHideSeconds: 4.0,
                isError: true
            )
        }
    }
}
