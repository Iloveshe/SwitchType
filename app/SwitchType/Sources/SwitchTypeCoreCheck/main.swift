import AVFoundation
import CoreGraphics
import Foundation
import SwitchTypeCore

enum CheckFailure: Error, CustomStringConvertible {
    case mismatch(name: String, expected: String, actual: String)
    case expectedError(name: String)

    var description: String {
        switch self {
        case .mismatch(let name, let expected, let actual):
            return "\(name) expected '\(expected)' but got '\(actual)'"
        case .expectedError(let name):
            return "\(name) expected an error but completed successfully"
        }
    }
}

enum WorkflowCheckError: Error {
    case pasteFailed
}

final class StubVoiceTranscriber: VoiceTranscribing {
    var transcript: String
    var error: Error?
    private(set) var audioURLs: [URL] = []

    init(transcript: String = "", error: Error? = nil) {
        self.transcript = transcript
        self.error = error
    }

    func transcribe(audioURL: URL) throws -> String {
        audioURLs.append(audioURL)
        if let error {
            throw error
        }
        return transcript
    }
}

final class StubTextPaster: TextPasting {
    var error: Error?
    private(set) var pastedTexts: [String] = []

    init(error: Error? = nil) {
        self.error = error
    }

    func paste(_ text: String) throws {
        if let error {
            throw error
        }
        pastedTexts.append(text)
    }
}

final class StubAudioCleaner: AudioCleaning {
    private(set) var cleanedURLs: [URL] = []

    func cleanup(_ url: URL) {
        cleanedURLs.append(url)
    }
}

func assertEqual(_ actual: String, _ expected: String, _ name: String) throws {
    guard actual == expected else {
        throw CheckFailure.mismatch(name: name, expected: expected, actual: actual)
    }
}

func assertEqual(_ actual: [String], _ expected: [String], _ name: String) throws {
    guard actual == expected else {
        throw CheckFailure.mismatch(name: name, expected: expected.joined(separator: " "), actual: actual.joined(separator: " "))
    }
}

func assertEqual(_ actual: Int, _ expected: Int, _ name: String) throws {
    guard actual == expected else {
        throw CheckFailure.mismatch(name: name, expected: "\(expected)", actual: "\(actual)")
    }
}

func assertClose(_ actual: TimeInterval, _ expected: TimeInterval, _ name: String) throws {
    guard abs(actual - expected) < 0.001 else {
        throw CheckFailure.mismatch(name: name, expected: "\(expected)", actual: "\(actual)")
    }
}

func assertEqual(_ actual: Bool, _ expected: Bool, _ name: String) throws {
    guard actual == expected else {
        throw CheckFailure.mismatch(name: name, expected: "\(expected)", actual: "\(actual)")
    }
}

func assertEqual(_ actual: URL, _ expected: URL, _ name: String) throws {
    guard actual.standardizedFileURL.path == expected.standardizedFileURL.path else {
        throw CheckFailure.mismatch(name: name, expected: expected.path, actual: actual.path)
    }
}

func transcriptTempFiles() -> [URL] {
    let temporaryDirectory = FileManager.default.temporaryDirectory
    let contents = (try? FileManager.default.contentsOfDirectory(
        at: temporaryDirectory,
        includingPropertiesForKeys: nil
    )) ?? []
    return contents.filter { $0.lastPathComponent.hasPrefix("switchtype-transcript-") }
}

func removeTranscriptTempFiles() {
    for url in transcriptTempFiles() {
        try? FileManager.default.removeItem(at: url)
    }
}

let replacementProcessor = PostProcessor(
    config: HotwordConfig(
        protectedTerms: ["Codex", "PR"],
        replacements: ["扣德克斯": "Codex", "皮阿尔": "PR"]
    )
)
try assertEqual(
    replacementProcessor.process("  扣德克斯 的 皮阿尔  "),
    "Codex 的 PR",
    "replacement and whitespace"
)
try assertEqual(
    replacementProcessor.process("繁體中文和後臺權限可以夾 English"),
    "繁体中文和后台权限可以夹 English",
    "traditional Chinese normalizes to simplified Chinese"
)

let workflowAudio = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-workflow-\(UUID().uuidString)")
    .appendingPathExtension("wav")
let workflowTranscriber = StubVoiceTranscriber(transcript: "扣德克斯 的 皮阿尔")
let workflowPaster = StubTextPaster()
let workflowCleaner = StubAudioCleaner()
let workflow = VoiceTypingWorkflow(
    transcriber: workflowTranscriber,
    postProcessor: replacementProcessor,
    paster: workflowPaster,
    cleaner: workflowCleaner
)
let workflowText = try workflow.transcribeAndProcess(audioURL: workflowAudio)
try assertEqual(workflowText, "Codex 的 PR", "workflow postprocesses transcript")
try assertEqual(workflowTranscriber.audioURLs.count, 1, "workflow transcribe audio count")
try assertEqual(workflowTranscriber.audioURLs[0], workflowAudio, "workflow transcribe audio URL")
try workflow.pasteAndCleanup(workflowText, audioURL: workflowAudio)
try assertEqual(workflowPaster.pastedTexts, ["Codex 的 PR"], "workflow pasted final text")
try assertEqual(workflowCleaner.cleanedURLs.count, 1, "workflow cleanup after paste count")
try assertEqual(workflowCleaner.cleanedURLs[0], workflowAudio, "workflow cleanup after paste URL")

let failingPasteAudio = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-workflow-failing-paste-\(UUID().uuidString)")
    .appendingPathExtension("wav")
let failingPasteCleaner = StubAudioCleaner()
let failingPasteWorkflow = VoiceTypingWorkflow(
    transcriber: StubVoiceTranscriber(transcript: "Codex"),
    postProcessor: replacementProcessor,
    paster: StubTextPaster(error: WorkflowCheckError.pasteFailed),
    cleaner: failingPasteCleaner
)
do {
    try failingPasteWorkflow.pasteAndCleanup("Codex", audioURL: failingPasteAudio)
    throw CheckFailure.expectedError(name: "workflow paste failure")
} catch WorkflowCheckError.pasteFailed {
}
try assertEqual(failingPasteCleaner.cleanedURLs.count, 1, "workflow cleanup on paste failure count")
try assertEqual(failingPasteCleaner.cleanedURLs[0], failingPasteAudio, "workflow cleanup on paste failure URL")

let spacingProcessor = PostProcessor(config: HotwordConfig(protectedTerms: ["MCP"], replacements: [:]))
try assertEqual(
    spacingProcessor.process("这个MCP server"),
    "这个 MCP server",
    "ASCII term spacing"
)
let acronymProcessor = PostProcessor(config: HotwordConfig(protectedTerms: ["PR", "CI", "MCP"], replacements: [:]))
try assertEqual(
    acronymProcessor.process("这个 P R 的 C I 看一下，还有 M C P server"),
    "这个 PR 的 CI 看一下，还有 MCP server",
    "spaced acronym normalization"
)
let recordedVariantProcessor = PostProcessor(config: .developerDefault)
try assertEqual(
    recordedVariantProcessor.process("这个 MCPso在p one name上 say talk").contains("MCP server"),
    true,
    "recorded variant MCP server"
)
try assertEqual(
    recordedVariantProcessor.process("这个 MCPso在p one name上 say talk").contains("prelive"),
    true,
    "recorded variant prelive"
)
try assertEqual(
    recordedVariantProcessor.process("这个 MCPso在p one name上 say talk").contains("SeaTalk"),
    true,
    "recorded variant SeaTalk"
)
try assertEqual(
    recordedVariantProcessor.process("帮我生成一个Code S Promote 让它修这个FLAG test").contains("Codex prompt"),
    true,
    "recorded variant Codex prompt"
)
try assertEqual(
    recordedVariantProcessor.process("帮我生成一个Code S Promote 让它修这个FLAG test").contains("flaky test"),
    true,
    "recorded variant flaky test"
)
try assertEqual(
    recordedVariantProcessor.process("把这个branchre倒，然后再跑一次smoke").contains("branch rebase"),
    true,
    "recorded variant branch rebase"
)
try assertEqual(
    recordedVariantProcessor.process("把这个branchre倒，然后再跑一次smoke").contains("smoke test"),
    true,
    "recorded variant smoke test"
)
try assertEqual(
    recordedVariantProcessor.process("再跑一次 smoke test"),
    "再跑一次 smoke test",
    "recorded variant does not duplicate smoke test"
)
try assertEqual(
    recordedVariantProcessor.process("这个公serv的P99来腾是在阳超里边搞了").contains("Go service"),
    true,
    "recorded variant Go service"
)
try assertEqual(
    recordedVariantProcessor.process("这个公serv的P99来腾是在阳超里边搞了").contains("p99 latency"),
    true,
    "recorded variant p99 latency"
)

try assertEqual(AudioRecorder.recordingFileExtension, "wav", "recorder file extension")
try assertEqual(
    AudioRecorder.recordingSettings[AVFormatIDKey] as? Int ?? 0,
    Int(kAudioFormatLinearPCM),
    "recorder format"
)
try assertClose(
    AudioRecorder.recordingSettings[AVSampleRateKey] as? TimeInterval ?? 0,
    16_000,
    "recorder sample rate"
)
try assertEqual(
    AudioRecorder.recordingSettings[AVNumberOfChannelsKey] as? Int ?? 0,
    1,
    "recorder channel count"
)
try AudioRecorder.validateMicrophonePermission(.granted)
try AudioRecorder.validateMicrophonePermission(.notDetermined)
do {
    try AudioRecorder.validateMicrophonePermission(.denied)
    throw CheckFailure.expectedError(name: "denied microphone permission")
} catch AudioRecorderError.microphonePermissionDenied {
}
do {
    try AudioRecorder.validateMicrophonePermission(.restricted)
    throw CheckFailure.expectedError(name: "restricted microphone permission")
} catch AudioRecorderError.microphonePermissionDenied {
}
let expectedDeviceSnapshot = PermissionSnapshot(
    microphone: .granted,
    accessibility: .granted,
    inputDeviceName: "DJI MIC MINI"
)
try AudioRecorder.validateExpectedInputDevice(
    expectedDeviceSnapshot,
    expectedInputDeviceName: "dji-mic"
)
do {
    try AudioRecorder.validateExpectedInputDevice(
        PermissionSnapshot(microphone: .granted, accessibility: .granted, inputDeviceName: nil),
        expectedInputDeviceName: "DJI MIC MINI"
    )
    throw CheckFailure.expectedError(name: "missing expected input device")
} catch AudioRecorderError.inputDeviceUnavailable {
}
do {
    try AudioRecorder.validateExpectedInputDevice(
        PermissionSnapshot(microphone: .granted, accessibility: .granted, inputDeviceName: "MacBook Pro Microphone"),
        expectedInputDeviceName: "DJI MIC MINI"
    )
    throw CheckFailure.expectedError(name: "wrong expected input device")
} catch AudioRecorderError.inputDeviceMismatch {
}
do {
    try AudioRecorder.validateRecordingStarted(false)
    throw CheckFailure.expectedError(name: "recorder start failure")
} catch AudioRecorderError.recordingDidNotStart {
}
try AudioRecorder.validateRecordingStarted(true)
try assertClose(
    AudioRecorder.minimumRecordingDurationSeconds,
    0.25,
    "minimum recording duration"
)
try AudioRecorder.validateRecordingDuration(0.25)
do {
    try AudioRecorder.validateRecordingDuration(0.1)
    throw CheckFailure.expectedError(name: "too short recording")
} catch AudioRecorderError.recordingTooShort {
}

let tempConfigURL = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-hotwords-\(UUID().uuidString)")
    .appendingPathExtension("json")
try """
{
  "protected_terms": ["SeaTalk"],
  "replacements": {
    "西拓": "SeaTalk"
  }
}
""".write(to: tempConfigURL, atomically: true, encoding: .utf8)
defer { try? FileManager.default.removeItem(at: tempConfigURL) }

let loadedConfig = try HotwordConfig.load(from: tempConfigURL)
let loadedProcessor = PostProcessor(config: loadedConfig)
try assertEqual(
    loadedProcessor.process("西拓 webhook"),
    "SeaTalk webhook",
    "JSON config loading"
)

let promptConfig = HotwordConfig(
    protectedTerms: ["Codex", "MCP server"],
    replacements: ["扣德克斯": "Codex", "公serv": "Go service"]
)
let promptText = promptConfig.asrPrompt() ?? ""
try assertEqual(promptText.contains("Codex"), true, "hotword prompt includes protected terms")
try assertEqual(promptText.contains("MCP server"), true, "hotword prompt includes multi-word protected terms")
try assertEqual(promptText.contains("Go service"), true, "hotword prompt includes replacement targets")
try assertEqual(promptText.contains("扣德克斯"), false, "hotword prompt excludes incorrect source phrases")

let hotwordHomeDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-hotword-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: hotwordHomeDirectory) }
let personalHotwordURL = try HotwordConfig.ensurePersonalConfig(homeDirectory: hotwordHomeDirectory)
try assertEqual(
    personalHotwordURL.path,
    hotwordHomeDirectory.appendingPathComponent(".switchtype").appendingPathComponent("hotwords.json").path,
    "personal hotword config path"
)
let personalConfig = try HotwordConfig.load(from: personalHotwordURL)
try assertEqual(personalConfig.protectedTerms.contains("Codex"), true, "personal hotword config seeds defaults")

let editorConfig = try HotwordConfig.fromEditorText(
    protectedTermsText: " Codex \n\nMCP server\nCodex\n",
    replacementsText: "扣德克斯 => Codex\n公serv => Go service\n"
)
try assertEqual(editorConfig.protectedTerms, ["Codex", "MCP server"], "hotword editor protected terms")
try assertEqual(editorConfig.replacements["扣德克斯"] ?? "", "Codex", "hotword editor replacement Codex")
try assertEqual(editorConfig.replacements["公serv"] ?? "", "Go service", "hotword editor replacement Go service")
try assertEqual(
    editorConfig.editorProtectedTermsText,
    "Codex\nMCP server",
    "hotword editor protected terms text"
)
try assertEqual(
    editorConfig.editorReplacementsText.contains("扣德克斯 => Codex"),
    true,
    "hotword editor replacements text includes Codex replacement"
)
try assertEqual(
    editorConfig.editorReplacementsText.contains("公serv => Go service"),
    true,
    "hotword editor replacements text includes Go service replacement"
)
let editorSavedURL = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-hotwords-editor-\(UUID().uuidString)")
    .appendingPathExtension("json")
defer { try? FileManager.default.removeItem(at: editorSavedURL) }
try editorConfig.write(to: editorSavedURL)
let editorSavedConfig = try HotwordConfig.load(from: editorSavedURL)
try assertEqual(editorSavedConfig.protectedTerms, ["Codex", "MCP server"], "hotword editor saved protected terms")
try assertEqual(editorSavedConfig.replacements["公serv"] ?? "", "Go service", "hotword editor saved replacement")

do {
    _ = try HotwordConfig.fromEditorText(protectedTermsText: "Codex", replacementsText: "bad replacement line")
    throw CheckFailure.expectedError(name: "hotword editor invalid replacement")
} catch HotwordEditorValidationError.invalidReplacementLine(let lineNumber, _) {
    try assertEqual(lineNumber, 1, "hotword editor invalid line number")
}

let pathRoot = URL(fileURLWithPath: "/SwitchTypeRoot")
let pathHome = URL(fileURLWithPath: "/Users/switchtype")
try assertEqual(
    SwitchTypePaths.resolve("~/hotwords.json", relativeTo: pathRoot, homeDirectory: pathHome),
    pathHome.appendingPathComponent("hotwords.json"),
    "tilde path expansion"
)
try assertEqual(
    SwitchTypePaths.resolve("models/model.bin", relativeTo: pathRoot, homeDirectory: pathHome),
    pathRoot.appendingPathComponent("models/model.bin"),
    "relative path resolution"
)

let hotwordCandidates = HotwordConfig.candidateURLs(
    environment: ["SWITCHTYPE_HOTWORDS_CONFIG": "~/custom-hotwords.json"],
    homeDirectory: pathHome,
    bundleResourceURL: nil,
    workingDirectory: pathRoot
)
try assertEqual(
    hotwordCandidates[0],
    pathHome.appendingPathComponent("custom-hotwords.json"),
    "hotwords env tilde expansion"
)
try assertEqual(
    hotwordCandidates[1],
    pathHome.appendingPathComponent(".switchtype").appendingPathComponent("hotwords.json"),
    "hotwords personal candidate"
)

let overrideService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: "/missing/whisper-cli",
        modelPath: "/missing/model.bin",
        transcriptOverride: "扣德克斯 皮阿尔"
    )
)
try assertEqual(
    try overrideService.transcribe(audioURL: URL(fileURLWithPath: "/tmp/missing.wav")),
    "扣德克斯 皮阿尔",
    "transcript override"
)

let cpuConfiguration = TranscriptionConfiguration(
    binaryPath: "/bin/whisper-cli",
    modelPath: "/models/model.bin",
    disableGPU: true,
    initialPrompt: "简体中文术语: Codex, MCP server"
)
try assertEqual(
    cpuConfiguration.whisperArguments(audioPath: "/tmp/input.wav", outputBasePath: "/tmp/output"),
    [
        "-ng",
        "-m",
        "/models/model.bin",
        "-f",
        "/tmp/input.wav",
        "-l",
        "zh",
        "--prompt",
        "简体中文术语: Codex, MCP server",
        "--carry-initial-prompt",
        "-otxt",
        "-of",
        "/tmp/output"
    ],
    "whisper no-gpu prompt arguments"
)

let cleanASRHomeDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-clean-asr-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: cleanASRHomeDirectory) }

let environmentConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_WHISPER_BIN": "/custom/whisper-cli",
    "SWITCHTYPE_WHISPER_MODEL": "/custom/model.bin",
    "SWITCHTYPE_WHISPER_NO_GPU": "1",
    "SWITCHTYPE_WHISPER_LANGUAGE": "en",
    "SWITCHTYPE_ASR_TIMEOUT_SECONDS": "7.5"
], homeDirectory: cleanASRHomeDirectory)
try assertEqual(environmentConfiguration.binaryPath, "/custom/whisper-cli", "environment whisper binary")
try assertEqual(environmentConfiguration.modelPath, "/custom/model.bin", "environment whisper model")
try assertEqual(environmentConfiguration.language, "en", "environment whisper language")
try assertClose(environmentConfiguration.timeoutSeconds, 7.5, "environment ASR timeout")
try assertEqual(environmentConfiguration.backend.rawValue, "local_whisper", "default ASR backend")
try assertEqual(environmentConfiguration.localWhisperProfile.rawValue, "custom", "default local whisper profile")

let tempASRConfigURL = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-asr-\(UUID().uuidString)")
    .appendingPathExtension("json")
try """
{
  "whisper_bin": "/configured/whisper-cli",
  "whisper_model": "/configured/model.bin",
  "whisper_no_gpu": true,
  "whisper_language": "zh",
  "timeout_seconds": 42,
  "expected_input_device_name": "DJI MIC MINI"
}
""".write(to: tempASRConfigURL, atomically: true, encoding: .utf8)
defer { try? FileManager.default.removeItem(at: tempASRConfigURL) }

let fileConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_ASR_CONFIG": tempASRConfigURL.path
])
try assertEqual(fileConfiguration.binaryPath, "/configured/whisper-cli", "config file whisper binary")
try assertEqual(fileConfiguration.modelPath, "/configured/model.bin", "config file whisper model")
try assertEqual(fileConfiguration.disableGPU, true, "config file no-gpu")
try assertEqual(fileConfiguration.language, "zh", "config file whisper language")
try assertClose(fileConfiguration.timeoutSeconds, 42, "config file ASR timeout")
try assertEqual(fileConfiguration.expectedInputDeviceName ?? "", "DJI MIC MINI", "config file expected input device")

let emptyExpectedDeviceEnvironmentConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_ASR_CONFIG": tempASRConfigURL.path,
    "SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME": ""
])
try assertEqual(
    emptyExpectedDeviceEnvironmentConfiguration.expectedInputDeviceName ?? "",
    "DJI MIC MINI",
    "empty environment expected input device falls back to config"
)

let tempHomeDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-home-\(UUID().uuidString)")
let tildeASRConfigURL = tempHomeDirectory
    .appendingPathComponent(".switchtype")
    .appendingPathComponent("asr.json")
try FileManager.default.createDirectory(at: tildeASRConfigURL.deletingLastPathComponent(), withIntermediateDirectories: true)
try """
{
  "whisper_bin": "/tilde/whisper-cli",
  "whisper_model": "/tilde/model.bin"
}
""".write(to: tildeASRConfigURL, atomically: true, encoding: .utf8)
defer { try? FileManager.default.removeItem(at: tempHomeDirectory) }

let tildeFileConfiguration = TranscriptionConfiguration.fromEnvironment(
    ["SWITCHTYPE_ASR_CONFIG": "~/.switchtype/asr.json"],
    homeDirectory: tempHomeDirectory
)
try assertEqual(tildeFileConfiguration.binaryPath, "/tilde/whisper-cli", "tilde ASR config binary")
try assertEqual(tildeFileConfiguration.modelPath, "/tilde/model.bin", "tilde ASR config model")

let overrideConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_ASR_CONFIG": tempASRConfigURL.path,
    "SWITCHTYPE_WHISPER_BIN": "/env/whisper-cli",
    "SWITCHTYPE_WHISPER_MODEL": "/env/model.bin",
    "SWITCHTYPE_WHISPER_NO_GPU": "0",
    "SWITCHTYPE_ASR_TIMEOUT_SECONDS": "9",
    "SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME": "MacBook Pro Microphone"
])
try assertEqual(overrideConfiguration.binaryPath, "/env/whisper-cli", "environment overrides config binary")
try assertEqual(overrideConfiguration.modelPath, "/env/model.bin", "environment overrides config model")
try assertEqual(overrideConfiguration.disableGPU, false, "environment overrides config no-gpu")
try assertClose(overrideConfiguration.timeoutSeconds, 9, "environment overrides config timeout")
try assertEqual(overrideConfiguration.expectedInputDeviceName ?? "", "MacBook Pro Microphone", "environment overrides expected input device")

let commandConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_ASR_BACKEND": "command",
    "SWITCHTYPE_ASR_COMMAND_PATH": "/usr/local/bin/custom-asr",
    "SWITCHTYPE_ASR_COMMAND_ARGS": #"["--audio","{audio}","--language","{language}","--prompt","{prompt}"]"#,
    "SWITCHTYPE_WHISPER_LANGUAGE": "zh"
], homeDirectory: cleanASRHomeDirectory)
try assertEqual(commandConfiguration.backend.rawValue, "command", "environment command ASR backend")
try assertEqual(commandConfiguration.commandPath ?? "", "/usr/local/bin/custom-asr", "environment command ASR path")
try assertEqual(
    commandConfiguration.commandArguments,
    ["--audio", "{audio}", "--language", "{language}", "--prompt", "{prompt}"],
    "environment command ASR args"
)
try assertEqual(
    commandConfiguration.resolvedCommandArguments(audioPath: "/tmp/input.wav"),
    ["--audio", "/tmp/input.wav", "--language", "zh", "--prompt", ""],
    "command ASR placeholder arguments"
)

let httpConfiguration = TranscriptionConfiguration.fromEnvironment([
    "SWITCHTYPE_ASR_BACKEND": "http_json",
    "SWITCHTYPE_ASR_HTTP_URL": "https://asr.example.test/v1/transcribe",
    "SWITCHTYPE_ASR_HTTP_HEADERS": #"{"Authorization":"Bearer token"}"#,
    "SWITCHTYPE_ASR_HTTP_TRANSCRIPT_KEY": "result.text"
], homeDirectory: cleanASRHomeDirectory)
try assertEqual(httpConfiguration.backend.rawValue, "http_json", "environment HTTP ASR backend")
try assertEqual(httpConfiguration.httpURL ?? "", "https://asr.example.test/v1/transcribe", "environment HTTP ASR URL")
try assertEqual(httpConfiguration.httpHeaders["Authorization"] ?? "", "Bearer token", "environment HTTP ASR header")
try assertEqual(httpConfiguration.httpTranscriptKey, "result.text", "environment HTTP transcript key")
try assertEqual(
    try HTTPJSONTranscriptionService.extractTranscript(
        from: #"{"result":{"text":"线上 transcript"}}"#.data(using: .utf8)!,
        keyPath: "result.text"
    ),
    "线上 transcript",
    "HTTP JSON ASR transcript extraction"
)

let httpProfileHome = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-http-profile-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: httpProfileHome) }
let httpProfileURL = try TranscriptionConfiguration.writeHTTPASRProfileSelection(
    .qwen3OfficialLocal,
    homeDirectory: httpProfileHome
)
let qwenHTTPProfileConfiguration = TranscriptionConfiguration.fromEnvironment(
    [:],
    homeDirectory: httpProfileHome
)
try assertEqual(
    httpProfileURL.path,
    httpProfileHome.appendingPathComponent(".switchtype").appendingPathComponent("asr.json").path,
    "HTTP ASR profile selection path"
)
try assertEqual(qwenHTTPProfileConfiguration.backend.rawValue, "http_json", "HTTP ASR profile forces HTTP backend")
try assertEqual(
    qwenHTTPProfileConfiguration.httpASRProfile.rawValue,
    "qwen3_official_local",
    "HTTP ASR profile persisted"
)
try assertEqual(
    qwenHTTPProfileConfiguration.httpURL ?? "",
    "http://127.0.0.1:8765/transcribe",
    "Qwen3 HTTP profile URL"
)
try assertEqual(qwenHTTPProfileConfiguration.httpFieldName, "audio", "Qwen3 HTTP profile field")
try assertEqual(qwenHTTPProfileConfiguration.httpTranscriptKey, "text", "Qwen3 HTTP profile transcript key")
try assertEqual(Int(qwenHTTPProfileConfiguration.timeoutSeconds), 180, "Qwen3 HTTP profile timeout")

let asrSelectionHome = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-asr-selection-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: asrSelectionHome) }
let asrSelectionURL = try TranscriptionConfiguration.writeBackendSelection(
    .command,
    homeDirectory: asrSelectionHome
)
let selectedASRConfig = TranscriptionConfiguration.fromEnvironment(
    [:],
    homeDirectory: asrSelectionHome
)
try assertEqual(
    asrSelectionURL.path,
    asrSelectionHome.appendingPathComponent(".switchtype").appendingPathComponent("asr.json").path,
    "ASR backend selection path"
)
try assertEqual(selectedASRConfig.backend.rawValue, "command", "ASR backend selection persisted")

let whisperProfileHome = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-whisper-profile-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: whisperProfileHome) }
let whisperProfileURL = try TranscriptionConfiguration.writeLocalWhisperProfileSelection(
    .baseCPU,
    homeDirectory: whisperProfileHome
)
let baseProfileConfiguration = TranscriptionConfiguration.fromEnvironment(
    [:],
    homeDirectory: whisperProfileHome
)
try assertEqual(
    whisperProfileURL.path,
    whisperProfileHome.appendingPathComponent(".switchtype").appendingPathComponent("asr.json").path,
    "local whisper profile selection path"
)
try assertEqual(baseProfileConfiguration.backend.rawValue, "local_whisper", "local whisper profile forces local backend")
try assertEqual(baseProfileConfiguration.localWhisperProfile.rawValue, "base_cpu", "local whisper profile persisted")
try assertEqual(
    baseProfileConfiguration.modelPath,
    "./third_party/whisper.cpp/models/ggml-base.bin",
    "base CPU profile model"
)
try assertEqual(baseProfileConfiguration.disableGPU, true, "base CPU profile disables GPU")
try assertEqual(Int(baseProfileConfiguration.timeoutSeconds), 300, "base CPU profile timeout")

let largeProfileHome = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-whisper-large-profile-home-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: largeProfileHome) }
_ = try TranscriptionConfiguration.writeLocalWhisperProfileSelection(
    .largeTurbo,
    homeDirectory: largeProfileHome
)
let largeProfileConfiguration = TranscriptionConfiguration.fromEnvironment(
    [:],
    homeDirectory: largeProfileHome
)
try assertEqual(largeProfileConfiguration.localWhisperProfile.rawValue, "large_turbo", "large turbo profile persisted")
try assertEqual(
    largeProfileConfiguration.modelPath,
    "./third_party/whisper.cpp/models/ggml-large-v3-turbo.bin",
    "large turbo profile model"
)
try assertEqual(largeProfileConfiguration.disableGPU, false, "large turbo profile uses GPU by default")

let profileProjectRoot = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-profile-root-\(UUID().uuidString)")
let profileWhisperBin = profileProjectRoot
    .appendingPathComponent("third_party/whisper.cpp/build/bin/whisper-cli")
let profileLargeModel = profileProjectRoot
    .appendingPathComponent("third_party/whisper.cpp/models/ggml-large-v3-turbo.bin")
let unrelatedWorkingDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-unrelated-cwd-\(UUID().uuidString)")
try FileManager.default.createDirectory(at: profileWhisperBin.deletingLastPathComponent(), withIntermediateDirectories: true)
try FileManager.default.createDirectory(at: profileLargeModel.deletingLastPathComponent(), withIntermediateDirectories: true)
try FileManager.default.createDirectory(at: unrelatedWorkingDirectory, withIntermediateDirectories: true)
try Data().write(to: profileWhisperBin)
try Data().write(to: profileLargeModel)
defer {
    try? FileManager.default.removeItem(at: profileProjectRoot)
    try? FileManager.default.removeItem(at: unrelatedWorkingDirectory)
}
let packagedProfileConfiguration = TranscriptionConfiguration(
    localWhisperProfile: .largeTurbo,
    binaryPath: profileWhisperBin.path,
    modelPath: "./third_party/whisper.cpp/models/ggml-large-v3-turbo.bin"
)
try assertEqual(
    packagedProfileConfiguration.resolvedLocalWhisperModelURL(workingDirectory: unrelatedWorkingDirectory),
    profileLargeModel,
    "local whisper profile resolves relative model from absolute whisper binary root"
)

let fakeWhisper = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-fake-whisper-\(UUID().uuidString)")
let fakeModel = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-fake-model-\(UUID().uuidString).bin")
let fakeAudio = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-fake-audio-\(UUID().uuidString).wav")
try """
#!/usr/bin/env python3
import pathlib
import sys

output = pathlib.Path(sys.argv[sys.argv.index("-of") + 1]).with_suffix(".txt")
output.write_text("", encoding="utf-8")
""".write(to: fakeWhisper, atomically: true, encoding: .utf8)
try Data().write(to: fakeModel)
try Data().write(to: fakeAudio)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fakeWhisper.path)
defer {
    try? FileManager.default.removeItem(at: fakeWhisper)
    try? FileManager.default.removeItem(at: fakeModel)
    try? FileManager.default.removeItem(at: fakeAudio)
}

let emptyTranscriptService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: fakeWhisper.path,
        modelPath: fakeModel.path
    )
)
do {
    _ = try emptyTranscriptService.transcribe(audioURL: fakeAudio)
    throw CheckFailure.expectedError(name: "empty transcript file")
} catch TranscriptionServiceError.noTranscript {
}

let slowWhisper = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-slow-whisper-\(UUID().uuidString)")
try """
#!/usr/bin/env python3
import time

time.sleep(2)
""".write(to: slowWhisper, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: slowWhisper.path)
defer {
    try? FileManager.default.removeItem(at: slowWhisper)
}

let timeoutService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: slowWhisper.path,
        modelPath: fakeModel.path,
        timeoutSeconds: 0.1
    )
)
do {
    _ = try timeoutService.transcribe(audioURL: fakeAudio)
    throw CheckFailure.expectedError(name: "transcription timeout")
} catch TranscriptionServiceError.timedOut {
}

let noisyWhisper = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-noisy-whisper-\(UUID().uuidString)")
try """
#!/usr/bin/env python3
import pathlib
import sys

for _ in range(2048):
    sys.stderr.write("progress-log-line-" + ("x" * 1024) + "\\n")
    sys.stderr.flush()

output = pathlib.Path(sys.argv[sys.argv.index("-of") + 1]).with_suffix(".txt")
output.write_text("Codex PR", encoding="utf-8")
""".write(to: noisyWhisper, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: noisyWhisper.path)
defer {
    try? FileManager.default.removeItem(at: noisyWhisper)
}

let noisyService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: noisyWhisper.path,
        modelPath: fakeModel.path,
        timeoutSeconds: 5
    )
)
try assertEqual(
    try noisyService.transcribe(audioURL: fakeAudio),
    "Codex PR",
    "large stderr transcription"
)

let failingWhisper = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-failing-whisper-\(UUID().uuidString)")
try """
#!/usr/bin/env python3
import pathlib
import sys

output = pathlib.Path(sys.argv[sys.argv.index("-of") + 1]).with_suffix(".txt")
output.write_text("partial transcript", encoding="utf-8")
sys.stderr.write("boom")
sys.exit(2)
""".write(to: failingWhisper, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: failingWhisper.path)
defer {
    try? FileManager.default.removeItem(at: failingWhisper)
    removeTranscriptTempFiles()
}

removeTranscriptTempFiles()
let failingService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: failingWhisper.path,
        modelPath: fakeModel.path
    )
)
do {
    _ = try failingService.transcribe(audioURL: fakeAudio)
    throw CheckFailure.expectedError(name: "failed transcription cleanup")
} catch TranscriptionServiceError.processFailed {
}
try assertEqual(transcriptTempFiles().isEmpty, true, "failed transcription temp cleanup")

let gpuFallbackWhisper = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-gpu-fallback-whisper-\(UUID().uuidString)")
try """
#!/usr/bin/env python3
import pathlib
import sys

output = pathlib.Path(sys.argv[sys.argv.index("-of") + 1]).with_suffix(".txt")
if "-ng" not in sys.argv:
    output.write_text("partial gpu transcript", encoding="utf-8")
    sys.stderr.write("ggml_metal_buffer_init: error: failed to allocate buffer")
    sys.exit(2)
output.write_text("CPU fallback transcript", encoding="utf-8")
""".write(to: gpuFallbackWhisper, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: gpuFallbackWhisper.path)
defer {
    try? FileManager.default.removeItem(at: gpuFallbackWhisper)
    removeTranscriptTempFiles()
}

removeTranscriptTempFiles()
let gpuFallbackService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        binaryPath: gpuFallbackWhisper.path,
        modelPath: fakeModel.path,
        disableGPU: false
    )
)
try assertEqual(
    try gpuFallbackService.transcribe(audioURL: fakeAudio),
    "CPU fallback transcript",
    "Metal failure retries whisper in CPU mode"
)
try assertEqual(transcriptTempFiles().isEmpty, true, "CPU fallback temp cleanup")

let fakeCommandASR = FileManager.default.temporaryDirectory
    .appendingPathComponent("switchtype-command-asr-\(UUID().uuidString)")
try """
#!/usr/bin/env python3
import sys

print("command transcript:" + sys.argv[-1])
""".write(to: fakeCommandASR, atomically: true, encoding: .utf8)
try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fakeCommandASR.path)
defer { try? FileManager.default.removeItem(at: fakeCommandASR) }
let commandService = TranscriptionService(
    configuration: TranscriptionConfiguration(
        backend: .command,
        binaryPath: "/missing/whisper-cli",
        modelPath: "/missing/model.bin",
        commandPath: fakeCommandASR.path,
        commandArguments: ["{audio}"]
    )
)
try assertEqual(
    try commandService.transcribe(audioURL: fakeAudio),
    "command transcript:\(fakeAudio.path)",
    "command ASR service output"
)

try assertEqual(AppState.idle.canBeginRecording, true, "idle can begin recording")
try assertEqual(AppState.error("previous failure").canBeginRecording, true, "error can begin recording")
try assertEqual(AppState.recording.canBeginRecording, false, "recording cannot begin recording")
try assertEqual(AppState.transcribing.canBeginRecording, false, "transcribing cannot begin recording")
try assertEqual(AppState.pasting.canBeginRecording, false, "pasting cannot begin recording")

let permissionSnapshot = PermissionSnapshot(
    microphone: .granted,
    accessibility: .denied,
    inputDeviceName: "DJI MIC MINI"
)
try assertEqual(
    permissionSnapshot.summary,
    "Microphone: granted, Accessibility: denied, Input: DJI MIC MINI",
    "permission summary"
)
let matchedExpectedPermissionSnapshot = PermissionSnapshot(
    microphone: .granted,
    accessibility: .granted,
    inputDeviceName: "DJI MIC MINI",
    expectedInputDeviceName: "dji-mic"
)
try assertEqual(
    matchedExpectedPermissionSnapshot.summary,
    "Microphone: granted, Accessibility: granted, Input: DJI MIC MINI, Expected input: dji-mic (matched)",
    "permission summary matched expected input"
)
let mismatchedExpectedPermissionSnapshot = PermissionSnapshot(
    microphone: .granted,
    accessibility: .granted,
    inputDeviceName: "MacBook Pro Microphone",
    expectedInputDeviceName: "DJI MIC MINI"
)
try assertEqual(
    mismatchedExpectedPermissionSnapshot.summary,
    "Microphone: granted, Accessibility: granted, Input: MacBook Pro Microphone, Expected input: DJI MIC MINI (mismatch)",
    "permission summary mismatched expected input"
)
let unavailableExpectedPermissionSnapshot = PermissionSnapshot(
    microphone: .granted,
    accessibility: .granted,
    inputDeviceName: nil,
    expectedInputDeviceName: "DJI MIC MINI"
)
try assertEqual(
    unavailableExpectedPermissionSnapshot.summary,
    "Microphone: granted, Accessibility: granted, Input: unknown, Expected input: DJI MIC MINI (unavailable)",
    "permission summary unavailable expected input"
)

try assertEqual(Int(HotkeyConfiguration.defaultKeyCode), 58, "default hotkey uses left option key")
try assertEqual(
    HotkeyConfiguration.defaultRequiredFlags.contains(.maskAlternate),
    true,
    "default hotkey requires option modifier"
)
try assertEqual(Int(HotkeyConfiguration.appDefaultKeyCode), 59, "app default hotkey uses left control key")
try assertEqual(
    HotkeyConfiguration.appDefaultRequiredFlags.contains(.maskControl),
    true,
    "app default hotkey requires control modifier"
)
try assertEqual(
    HotkeyConfiguration.appDefaultRequiredFlags.contains(.maskShift),
    true,
    "app default hotkey requires shift modifier"
)
let appDefaultHotkey = HotkeyConfiguration.fromAppEnvironment([:])
try assertEqual(Int(appDefaultHotkey.keyCode), 59, "empty app environment uses control-shift key code")
try assertEqual(appDefaultHotkey.requiredFlags.contains(.maskControl), true, "empty app environment uses control")
try assertEqual(appDefaultHotkey.requiredFlags.contains(.maskShift), true, "empty app environment uses shift")
try assertEqual(appDefaultHotkey.displayName, "Control+Shift", "app default hotkey display name")

var hotkeyState = HotkeyEventState()
let startAction = hotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [.maskAlternate])
try assertEqual(startAction.rawValue, HotkeyEventAction.startRecording.rawValue, "hotkey starts recording")
try assertEqual(startAction.consumesEvent, true, "hotkey start consumes key event")
try assertEqual(startAction.shouldConsumeEvent(consumeEvents: false), false, "shadow hotkey start passes through")
try assertEqual(startAction.shouldConsumeEvent(consumeEvents: true), true, "normal hotkey start consumes")

let repeatAction = hotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [.maskAlternate])
try assertEqual(repeatAction.rawValue, HotkeyEventAction.consumeOnly.rawValue, "hotkey repeat is consumed without restart")
try assertEqual(repeatAction.consumesEvent, true, "hotkey repeat consumes key event")

let finishAction = hotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [])
try assertEqual(finishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "hotkey finishes recording")
try assertEqual(finishAction.consumesEvent, true, "hotkey finish consumes key event")
try assertEqual(finishAction.shouldConsumeEvent(consumeEvents: false), false, "shadow hotkey finish passes through")

let ignoredAction = hotkeyState.handle(type: .keyDown, keyCode: 49, flags: [])
try assertEqual(ignoredAction.rawValue, HotkeyEventAction.ignore.rawValue, "space without option is ignored")
try assertEqual(ignoredAction.consumesEvent, false, "ignored hotkey does not consume event")

let optionSpaceOverride = HotkeyConfiguration.from(environment: [
    "SWITCHTYPE_HOTKEY_KEY_CODE": "49",
    "SWITCHTYPE_HOTKEY_MODIFIERS": "option"
])
try assertEqual(Int(optionSpaceOverride.keyCode), 49, "option-space override key code")
try assertEqual(optionSpaceOverride.requiredFlags.contains(.maskAlternate), true, "option-space override modifier")

let appEnvironmentOverride = HotkeyConfiguration.fromAppEnvironment([
    "SWITCHTYPE_HOTKEY_KEY_CODE": "49",
    "SWITCHTYPE_HOTKEY_MODIFIERS": "option"
])
try assertEqual(Int(appEnvironmentOverride.keyCode), 49, "app environment override key code")
try assertEqual(appEnvironmentOverride.requiredFlags.contains(.maskAlternate), true, "app environment override modifier")
try assertEqual(appEnvironmentOverride.displayName, "Option+Space", "app environment override display name")

try assertEqual(
    AppFeedbackFactory.ready(hotkeyDescription: appDefaultHotkey.displayName).title,
    "SwitchType ready",
    "ready feedback title"
)
try assertEqual(
    AppFeedbackFactory.ready(hotkeyDescription: appDefaultHotkey.displayName).detail ?? "",
    "Hold Control+Shift",
    "ready feedback hotkey detail"
)
try assertEqual(
    AppFeedbackFactory.feedback(for: .recording)?.title ?? "",
    "Listening",
    "recording feedback title"
)
try assertEqual(
    AppFeedbackFactory.feedback(for: .recording)?.pulses ?? false,
    true,
    "recording feedback pulses"
)
try assertEqual(
    AppFeedbackFactory.feedback(for: .transcribing)?.title ?? "",
    "Transcribing",
    "transcribing feedback title"
)
try assertEqual(
    AppFeedbackFactory.feedback(for: .pasting)?.title ?? "",
    "Inserting",
    "pasting feedback title"
)
try assertEqual(
    AppFeedbackFactory.feedback(for: .idle) == nil,
    true,
    "idle feedback hides"
)
try assertEqual(
    AppFeedbackFactory.completed.title,
    "Inserted",
    "completed feedback title"
)

let configuredHotkey = HotkeyConfiguration.from(environment: [
    "SWITCHTYPE_HOTKEY_KEY_CODE": "36",
    "SWITCHTYPE_HOTKEY_MODIFIERS": "control,shift"
])
try assertEqual(Int(configuredHotkey.keyCode), 36, "configured hotkey key code")
try assertEqual(configuredHotkey.requiredFlags.contains(.maskControl), true, "configured hotkey control modifier")
try assertEqual(configuredHotkey.requiredFlags.contains(.maskShift), true, "configured hotkey shift modifier")
try assertEqual(
    HotkeyConfiguration.modifierString(from: [.maskControl, .maskShift]),
    "control,shift",
    "configured hotkey modifier string"
)
try assertEqual(
    FocusedTextDelta.insertedText(before: "Log: ", after: "Log: 帮我生成一个 Codex prompt 让它修 flaky test") ?? "",
    "帮我生成一个 Codex prompt 让它修 flaky test",
    "focused text delta extracts appended Doubao text"
)
try assertEqual(
    FocusedTextDelta.insertedText(before: "prefix suffix", after: "prefix Codex PR suffix") ?? "",
    "Codex PR",
    "focused text delta extracts inserted middle text"
)
try assertEqual(
    FocusedTextDelta.insertedText(before: "Codex", after: "Codex") == nil,
    true,
    "focused text delta ignores unchanged text"
)
try assertEqual(
    FocusedTextDelta.insertedText(
        before: FocusedTextSnapshot(value: "Codex", processIdentifier: 1),
        after: FocusedTextSnapshot(value: "Codex PR", processIdentifier: 2)
    ) == nil,
    true,
    "focused text delta rejects different focused processes"
)
let missingBeforeDelta = FocusedTextDelta.analyze(before: nil, after: FocusedTextSnapshot(value: "Codex PR"))
try assertEqual(missingBeforeDelta.reason, "missing_before_snapshot", "focused text delta explains missing before snapshot")
try assertEqual(missingBeforeDelta.insertedText == nil, true, "focused text delta has no inserted text without before snapshot")

let selectedRangeInsertedDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "prefix suffix", processIdentifier: 1, selectedRange: NSRange(location: 7, length: 0)),
    after: FocusedTextSnapshot(value: "prefix Codex PR suffix", processIdentifier: 1, selectedRange: NSRange(location: 16, length: 0))
)
try assertEqual(
    selectedRangeInsertedDelta.insertedText ?? "",
    "Codex PR",
    "focused text delta uses selected range insertion point"
)
try assertEqual(
    selectedRangeInsertedDelta.reason,
    "captured",
    "focused text delta selected range capture reason"
)

let selectedRangeReplacementDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "prefix old suffix", processIdentifier: 1, selectedRange: NSRange(location: 7, length: 3)),
    after: FocusedTextSnapshot(value: "prefix Codex suffix", processIdentifier: 1, selectedRange: NSRange(location: 12, length: 0))
)
try assertEqual(
    selectedRangeReplacementDelta.insertedText ?? "",
    "Codex",
    "focused text delta uses selected range replacement"
)

let selectedRangeMismatchDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "prefix suffix", processIdentifier: 1, selectedRange: NSRange(location: 7, length: 0)),
    after: FocusedTextSnapshot(value: "unrelated 要求后续变更 text", processIdentifier: 1, selectedRange: NSRange(location: 4, length: 0))
)
try assertEqual(
    selectedRangeMismatchDelta.insertedText == nil,
    true,
    "focused text delta rejects selected range mismatch instead of coarse diff"
)
try assertEqual(
    selectedRangeMismatchDelta.reason,
    "selection_range_mismatch",
    "focused text delta explains selected range mismatch"
)

let selectedRangeAnchoredFallbackDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "prefix suffix", processIdentifier: 1, selectedRange: NSRange(location: 0, length: 0)),
    after: FocusedTextSnapshot(value: "prefix Codex suffix", processIdentifier: 1, selectedRange: NSRange(location: 12, length: 0))
)
try assertEqual(
    selectedRangeAnchoredFallbackDelta.insertedText ?? "",
    "Codex",
    "focused text delta falls back to anchored diff when selection range is stale"
)
try assertEqual(
    selectedRangeAnchoredFallbackDelta.reason,
    "captured",
    "focused text delta captures stale selected range with anchored text"
)

let invalidSelectionRangeFallbackDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "", processIdentifier: 1, selectedRange: NSRange(location: 2082, length: 111)),
    after: FocusedTextSnapshot(value: "你好 Codex", processIdentifier: 1, selectedRange: NSRange(location: 8, length: 0))
)
try assertEqual(
    invalidSelectionRangeFallbackDelta.insertedText ?? "",
    "你好 Codex",
    "focused text delta falls back when accessibility selection ranges are out of value bounds"
)
try assertEqual(
    invalidSelectionRangeFallbackDelta.reason,
    "captured",
    "focused text delta captures via coarse diff when selection ranges are invalid"
)

let missingBothDelta = FocusedTextDelta.analyze(before: nil, after: nil)
try assertEqual(missingBothDelta.reason, "missing_both_snapshots", "focused text delta explains when both snapshots are missing")

let missingAfterDelta = FocusedTextDelta.analyze(before: FocusedTextSnapshot(value: "Codex"), after: nil)
try assertEqual(missingAfterDelta.reason, "missing_after_snapshot", "focused text delta explains missing after snapshot")

let unchangedDelta = FocusedTextDelta.analyze(before: FocusedTextSnapshot(value: "Codex"), after: FocusedTextSnapshot(value: "Codex"))
try assertEqual(unchangedDelta.reason, "unchanged", "focused text delta explains unchanged text")

let changedProcessDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "Codex", processIdentifier: 1),
    after: FocusedTextSnapshot(value: "Codex PR", processIdentifier: 2)
)
try assertEqual(changedProcessDelta.reason, "process_changed", "focused text delta explains process change")

let capturedDelta = FocusedTextDelta.analyze(
    before: FocusedTextSnapshot(value: "Log: "),
    after: FocusedTextSnapshot(value: "Log: Codex PR")
)
try assertEqual(capturedDelta.insertedText ?? "", "Codex PR", "focused text delta analysis extracts inserted text")
try assertEqual(capturedDelta.reason, "captured", "focused text delta analysis marks captured text")
let delayedCapturedDelta = FocusedTextDelta.firstCapturedAnalysis(
    before: FocusedTextSnapshot(value: "Log: "),
    afterCandidates: [
        FocusedTextSnapshot(value: "Log: "),
        FocusedTextSnapshot(value: "Log: Codex PR"),
    ]
)
try assertEqual(
    delayedCapturedDelta.insertedText ?? "",
    "Codex PR",
    "focused text delta selects later captured snapshot"
)
let processChangedThenIdleBaselineMatch = FocusedTextDelta.firstCapturedMatch(
    beforeCandidates: [
        FocusedTextSnapshot(value: "Chrome title", processIdentifier: 1),
        FocusedTextSnapshot(value: "Log: ", processIdentifier: 2, selectedRange: NSRange(location: 5, length: 0)),
    ],
    afterCandidates: [
        FocusedTextSnapshot(value: "Log: 你好你好", processIdentifier: 2, selectedRange: NSRange(location: 9, length: 0)),
    ]
)
try assertEqual(
    processChangedThenIdleBaselineMatch.analysis.insertedText ?? "",
    "你好你好",
    "focused text delta selects matching idle baseline after a transient process change"
)
try assertEqual(
    Int(processChangedThenIdleBaselineMatch.beforeSnapshot?.processIdentifier ?? 0),
    2,
    "focused text delta reports the matching before snapshot"
)
let delayedUnmatchedDelta = FocusedTextDelta.firstCapturedAnalysis(
    before: FocusedTextSnapshot(value: "Log: "),
    afterCandidates: [
        nil,
        FocusedTextSnapshot(value: "Log: "),
    ]
)
try assertEqual(
    delayedUnmatchedDelta.reason,
    "unchanged",
    "focused text delta keeps last unmatched reason"
)
var configuredHotkeyState = HotkeyEventState(configuration: configuredHotkey)
let configuredStartAction = configuredHotkeyState.handle(type: .keyDown, keyCode: 36, flags: [.maskControl, .maskShift])
try assertEqual(configuredStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "configured hotkey starts recording")
var defaultOnlyHotkeyState = HotkeyEventState(configuration: configuredHotkey)
let defaultOnlyAction = defaultOnlyHotkeyState.handle(type: .keyDown, keyCode: 49, flags: [.maskAlternate])
try assertEqual(defaultOnlyAction.rawValue, HotkeyEventAction.ignore.rawValue, "default hotkey ignored when custom hotkey configured")

var appDefaultHotkeyState = HotkeyEventState(configuration: appDefaultHotkey)
let appDefaultPartialAction = appDefaultHotkeyState.handle(type: .flagsChanged, keyCode: 59, flags: [.maskControl])
try assertEqual(appDefaultPartialAction.rawValue, HotkeyEventAction.ignore.rawValue, "app default waits for both control and shift")
let appDefaultStartAction = appDefaultHotkeyState.handle(type: .flagsChanged, keyCode: 56, flags: [.maskControl, .maskShift])
try assertEqual(appDefaultStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "app default control-shift starts recording")
let appDefaultRepeatAction = appDefaultHotkeyState.handle(type: .flagsChanged, keyCode: 60, flags: [.maskControl, .maskShift])
try assertEqual(appDefaultRepeatAction.rawValue, HotkeyEventAction.consumeOnly.rawValue, "app default control-shift repeat is consumed")
let appDefaultFinishAction = appDefaultHotkeyState.handle(type: .flagsChanged, keyCode: 56, flags: [.maskControl])
try assertEqual(appDefaultFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "app default control-shift release finishes recording")
var appDefaultSyntheticHotkeyState = HotkeyEventState(configuration: appDefaultHotkey)
let appDefaultSyntheticIdleAction = appDefaultSyntheticHotkeyState.handle(type: .flagsChanged, keyCode: 0, flags: [])
try assertEqual(appDefaultSyntheticIdleAction.rawValue, HotkeyEventAction.ignore.rawValue, "app default ignores keyCode zero before hotkey is pressed")
let appDefaultSyntheticStartAction = appDefaultSyntheticHotkeyState.handle(type: .flagsChanged, keyCode: 0, flags: [.maskControl, .maskShift])
try assertEqual(appDefaultSyntheticStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "app default starts on synthetic modifier-only event")
let appDefaultSyntheticFinishAction = appDefaultSyntheticHotkeyState.handle(type: .flagsChanged, keyCode: 0, flags: [])
try assertEqual(appDefaultSyntheticFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "app default finishes on synthetic modifier-only release")
var appDefaultPollingState = HotkeyEventState(configuration: appDefaultHotkey)
let appDefaultPollingStartAction = appDefaultPollingState.handlePolledFlags([.maskControl, .maskShift])
try assertEqual(appDefaultPollingStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "app default polling starts recording")
let appDefaultPollingFinishAction = appDefaultPollingState.handlePolledFlags([])
try assertEqual(appDefaultPollingFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "app default polling finishes recording")

let optionOnlyHotkey = HotkeyConfiguration(keyCode: 58, requiredFlags: [.maskAlternate])
var optionOnlyHotkeyState = HotkeyEventState(configuration: optionOnlyHotkey)
let optionOnlyStartAction = optionOnlyHotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [.maskAlternate])
try assertEqual(optionOnlyStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "modifier-only option hotkey starts recording")
let optionOnlyRepeatAction = optionOnlyHotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [.maskAlternate])
try assertEqual(optionOnlyRepeatAction.rawValue, HotkeyEventAction.consumeOnly.rawValue, "modifier-only option repeat is consumed without restart")
let optionOnlyFinishAction = optionOnlyHotkeyState.handle(type: .flagsChanged, keyCode: 58, flags: [])
try assertEqual(optionOnlyFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "modifier-only option release finishes recording")
var optionEitherSideHotkeyState = HotkeyEventState(configuration: optionOnlyHotkey)
let optionEitherSideStartAction = optionEitherSideHotkeyState.handle(type: .flagsChanged, keyCode: 61, flags: [.maskAlternate])
try assertEqual(optionEitherSideStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "modifier-only option accepts either option key")
let optionEitherSideFinishAction = optionEitherSideHotkeyState.handle(type: .flagsChanged, keyCode: 61, flags: [])
try assertEqual(optionEitherSideFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "modifier-only option release accepts either option key")
var optionSyntheticHotkeyState = HotkeyEventState(configuration: optionOnlyHotkey)
let optionSyntheticStartAction = optionSyntheticHotkeyState.handle(type: .flagsChanged, keyCode: 0, flags: [.maskAlternate])
try assertEqual(optionSyntheticStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "modifier-only option starts on synthetic keyCode zero event")
let optionSyntheticFinishAction = optionSyntheticHotkeyState.handle(type: .flagsChanged, keyCode: 0, flags: [])
try assertEqual(optionSyntheticFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "modifier-only option finishes on synthetic keyCode zero release")
var optionPollingHotkeyState = HotkeyEventState(configuration: optionOnlyHotkey)
let optionPollingStartAction = optionPollingHotkeyState.handlePolledFlags([.maskAlternate])
try assertEqual(optionPollingStartAction.rawValue, HotkeyEventAction.startRecording.rawValue, "modifier-only polling starts recording")
let optionPollingRepeatAction = optionPollingHotkeyState.handlePolledFlags([.maskAlternate])
try assertEqual(optionPollingRepeatAction.rawValue, HotkeyEventAction.consumeOnly.rawValue, "modifier-only polling repeat does not restart")
let optionPollingFinishAction = optionPollingHotkeyState.handlePolledFlags([])
try assertEqual(optionPollingFinishAction.rawValue, HotkeyEventAction.finishRecording.rawValue, "modifier-only polling finishes recording")
let eventTapDiagnostic = HotkeyEventDiagnostic(
    source: .eventTap,
    type: .flagsChanged,
    keyCode: 58,
    flags: [.maskAlternate],
    action: .startRecording
)
try assertEqual(
    eventTapDiagnostic.summary,
    "source=eventTap, type=flagsChanged, keyCode=58, modifiers=option, action=startRecording",
    "hotkey event diagnostic reports event tap source"
)
let modifierPollDiagnostic = HotkeyEventDiagnostic(
    source: .modifierPoll,
    type: .flagsChanged,
    keyCode: 58,
    flags: [],
    action: .finishRecording
)
try assertEqual(
    modifierPollDiagnostic.summary,
    "source=modifierPoll, type=flagsChanged, keyCode=58, modifiers=none, action=finishRecording",
    "hotkey event diagnostic reports modifier polling source"
)

print("SwitchTypeCoreCheck passed")
