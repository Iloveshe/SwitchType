import Foundation
import SwitchTypeCore

struct SmokeFailure: Error, CustomStringConvertible {
    let message: String

    var description: String {
        message
    }
}

func argument(after flag: String, in arguments: [String]) -> String? {
    guard let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1) else {
        return nil
    }
    return arguments[index + 1]
}

func hasFlag(_ flag: String, in arguments: [String]) -> Bool {
    arguments.contains(flag)
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let audioPath = argument(after: "--audio", in: arguments) else {
    throw SmokeFailure(message: "Usage: SwitchTypeASRSmoke --audio <wav> [--expect <text>] [--postprocess]")
}
let expected = argument(after: "--expect", in: arguments)

var transcript = try TranscriptionService().transcribe(audioURL: URL(fileURLWithPath: audioPath))
if hasFlag("--postprocess", in: arguments) {
    transcript = PostProcessor(config: HotwordConfig.loadDefault()).process(transcript)
}
guard !transcript.isEmpty else {
    throw SmokeFailure(message: "Transcription returned an empty transcript.")
}
if let expected, !transcript.localizedCaseInsensitiveContains(expected) {
    throw SmokeFailure(message: "Transcript did not contain expected text '\(expected)': \(transcript)")
}

print(transcript)
