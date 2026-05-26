import Foundation

public protocol VoiceTranscribing {
    func transcribe(audioURL: URL) throws -> String
}

public protocol TextPasting {
    func paste(_ text: String) throws
}

public protocol AudioCleaning {
    func cleanup(_ url: URL)
}

public struct VoiceTypingTranscriptionResult {
    public let rawText: String
    public let finalText: String
    public let transcribeMS: Int
    public let postprocessMS: Int
}

public final class VoiceTypingWorkflow {
    private let transcriber: VoiceTranscribing
    private let postProcessor: PostProcessor
    private let paster: TextPasting
    private let cleaner: AudioCleaning

    public init(
        transcriber: VoiceTranscribing,
        postProcessor: PostProcessor,
        paster: TextPasting,
        cleaner: AudioCleaning
    ) {
        self.transcriber = transcriber
        self.postProcessor = postProcessor
        self.paster = paster
        self.cleaner = cleaner
    }

    public func transcribeAndProcess(audioURL: URL) throws -> String {
        try transcribeAndProcessWithMetrics(audioURL: audioURL).finalText
    }

    public func transcribeAndProcessWithMetrics(audioURL: URL) throws -> VoiceTypingTranscriptionResult {
        let transcribeStartedAt = Date()
        let rawText = try transcriber.transcribe(audioURL: audioURL)
        let transcribeMS = Self.milliseconds(since: transcribeStartedAt)
        let postprocessStartedAt = Date()
        let finalText = postProcessor.process(rawText)
        let postprocessMS = Self.milliseconds(since: postprocessStartedAt)
        return VoiceTypingTranscriptionResult(
            rawText: rawText,
            finalText: finalText,
            transcribeMS: transcribeMS,
            postprocessMS: postprocessMS
        )
    }

    public func pasteAndCleanup(_ text: String, audioURL: URL) throws {
        defer { cleaner.cleanup(audioURL) }
        try paster.paste(text)
    }

    public func cleanup(_ audioURL: URL) {
        cleaner.cleanup(audioURL)
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}

extension TranscriptionService: VoiceTranscribing {}
extension PasteboardTyper: TextPasting {}
extension AudioRecorder: AudioCleaning {}
