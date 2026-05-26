import ApplicationServices
import Foundation
import SwitchTypeCore

struct PermissionReport: Encodable {
    var microphone: String
    var accessibility: String
    var inputDeviceName: String?
    var expectedInputDeviceName: String?
    var expectedInputDeviceStatus: String
    var allRequiredGranted: Bool
    var summary: String

    enum CodingKeys: String, CodingKey {
        case microphone
        case accessibility
        case inputDeviceName = "input_device_name"
        case expectedInputDeviceName = "expected_input_device_name"
        case expectedInputDeviceStatus = "expected_input_device_status"
        case allRequiredGranted = "all_required_granted"
        case summary
    }
}

struct ASRReport: Encodable {
    var backend: String
    var localWhisperProfile: String
    var httpASRProfile: String
    var whisperBin: String
    var whisperBinStatus: String
    var whisperModel: String
    var whisperModelStatus: String
    var whisperNoGPU: Bool
    var whisperLanguage: String
    var commandPath: String?
    var commandPathStatus: String?
    var httpURL: String?
    var httpTranscriptKey: String
    var timeoutSeconds: TimeInterval

    enum CodingKeys: String, CodingKey {
        case backend = "asr_backend"
        case localWhisperProfile = "local_whisper_profile"
        case httpASRProfile = "asr_http_profile"
        case whisperBin = "whisper_bin"
        case whisperBinStatus = "whisper_bin_status"
        case whisperModel = "whisper_model"
        case whisperModelStatus = "whisper_model_status"
        case whisperNoGPU = "whisper_no_gpu"
        case whisperLanguage = "whisper_language"
        case commandPath = "asr_command_path"
        case commandPathStatus = "asr_command_path_status"
        case httpURL = "asr_http_url"
        case httpTranscriptKey = "asr_http_transcript_key"
        case timeoutSeconds = "timeout_seconds"
    }
}

struct HotwordsReport: Encodable {
    var status: String
    var path: String?
    var protectedTerms: Int
    var replacements: Int

    enum CodingKeys: String, CodingKey {
        case status
        case path
        case protectedTerms = "protected_terms"
        case replacements
    }
}

struct DoctorReport: Encodable {
    var permissions: PermissionReport
    var asr: ASRReport
    var hotwords: HotwordsReport
}

func status(_ ok: Bool) -> String {
    ok ? "ok" : "missing"
}

func executableStatus(_ path: String) -> String {
    let url = SwitchTypePaths.resolve(
        path,
        relativeTo: URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    )
    return FileManager.default.isExecutableFile(atPath: url.path) ? "ok" : "missing or not executable"
}

func fileStatus(_ path: String) -> String {
    let url = SwitchTypePaths.resolve(
        path,
        relativeTo: URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    )
    return status(FileManager.default.fileExists(atPath: url.path))
}

func expectedInputDeviceStatus(_ snapshot: PermissionSnapshot) -> String {
    guard let expected = snapshot.expectedInputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines),
          !expected.isEmpty else {
        return "not_enforced"
    }
    guard let input = snapshot.inputDeviceName?.trimmingCharacters(in: .whitespacesAndNewlines),
          !input.isEmpty else {
        return "unavailable"
    }
    return AudioRecorder.inputDeviceName(input, matchesExpected: expected) ? "matched" : "mismatch"
}

func hotwordReport() -> HotwordsReport {
    let candidates = HotwordConfig.candidateURLs()
    for url in candidates where FileManager.default.fileExists(atPath: url.path) {
        if let config = try? HotwordConfig.load(from: url) {
            return HotwordsReport(
                status: "ok",
                path: url.path,
                protectedTerms: config.protectedTerms.count,
                replacements: config.replacements.count
            )
        }
        return HotwordsReport(status: "unreadable", path: url.path, protectedTerms: 0, replacements: 0)
    }
    let fallback = HotwordConfig.developerDefault
    return HotwordsReport(
        status: "developer_default",
        path: nil,
        protectedTerms: fallback.protectedTerms.count,
        replacements: fallback.replacements.count
    )
}

func buildReport(
    configuration: TranscriptionConfiguration,
    permissionSnapshot: PermissionSnapshot
) -> DoctorReport {
    DoctorReport(
        permissions: PermissionReport(
            microphone: permissionSnapshot.microphone.rawValue,
            accessibility: permissionSnapshot.accessibility.rawValue,
            inputDeviceName: permissionSnapshot.inputDeviceName,
            expectedInputDeviceName: permissionSnapshot.expectedInputDeviceName,
            expectedInputDeviceStatus: expectedInputDeviceStatus(permissionSnapshot),
            allRequiredGranted: permissionSnapshot.allRequiredGranted,
            summary: permissionSnapshot.summary
        ),
        asr: ASRReport(
            backend: configuration.backend.rawValue,
            localWhisperProfile: configuration.localWhisperProfile.rawValue,
            httpASRProfile: configuration.httpASRProfile.rawValue,
            whisperBin: configuration.binaryPath,
            whisperBinStatus: executableStatus(configuration.binaryPath),
            whisperModel: configuration.modelPath,
            whisperModelStatus: fileStatus(configuration.modelPath),
            whisperNoGPU: configuration.disableGPU,
            whisperLanguage: configuration.language,
            commandPath: configuration.commandPath,
            commandPathStatus: configuration.commandPath.map(executableStatus),
            httpURL: configuration.httpURL,
            httpTranscriptKey: configuration.httpTranscriptKey,
            timeoutSeconds: configuration.timeoutSeconds
        ),
        hotwords: hotwordReport()
    )
}

func printHumanReport(_ report: DoctorReport) {
    print("SwitchType Doctor")
    print("Permissions: \(report.permissions.summary)")
    print("ASR:")
    print("  asr_backend: \(report.asr.backend)")
    print("  local_whisper_profile: \(report.asr.localWhisperProfile)")
    print("  asr_http_profile: \(report.asr.httpASRProfile)")
    print("  whisper_bin: \(report.asr.whisperBin) [\(report.asr.whisperBinStatus)]")
    print("  whisper_model: \(report.asr.whisperModel) [\(report.asr.whisperModelStatus)]")
    print("  whisper_no_gpu: \(report.asr.whisperNoGPU)")
    print("  whisper_language: \(report.asr.whisperLanguage)")
    if let commandPath = report.asr.commandPath {
        print("  asr_command_path: \(commandPath) [\(report.asr.commandPathStatus ?? "unknown")]")
    }
    if let httpURL = report.asr.httpURL {
        print("  asr_http_url: \(httpURL)")
        print("  asr_http_transcript_key: \(report.asr.httpTranscriptKey)")
    }
    print("  timeout_seconds: \(report.asr.timeoutSeconds)")
    print("  expected_input_device_name: \(report.permissions.expectedInputDeviceName ?? "not enforced")")
    print("Hotwords:")
    switch report.hotwords.status {
    case "ok":
        print(
            "  hotwords: ok: \(report.hotwords.path ?? "") "
            + "(\(report.hotwords.protectedTerms) protected terms, \(report.hotwords.replacements) replacements)"
        )
    case "unreadable":
        print("  hotwords: unreadable: \(report.hotwords.path ?? "")")
    default:
        print(
            "  hotwords: developer default "
            + "(\(report.hotwords.protectedTerms) protected terms, \(report.hotwords.replacements) replacements)"
        )
    }
}

func requestMicrophonePermission() -> Bool {
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    AudioRecorder().requestMicrophonePermission { allowed in
        granted = allowed
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 60)
    print("Microphone permission request: \(granted ? "granted" : "not granted")")
    return granted
}

func promptAccessibilityPermission() -> Bool {
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    print("Accessibility permission prompt: \(trusted ? "already granted" : "prompted or still denied")")
    return trusted
}

func argument(after option: String, in arguments: [String]) -> String? {
    guard let index = arguments.firstIndex(of: option),
          arguments.indices.contains(arguments.index(after: index)) else {
        return nil
    }
    return arguments[arguments.index(after: index)]
}

let arguments = Array(CommandLine.arguments.dropFirst())
if arguments.contains("--request-microphone") {
    _ = requestMicrophonePermission()
}
if arguments.contains("--prompt-accessibility") {
    _ = promptAccessibilityPermission()
}
if arguments.contains("--focused-text-json") {
    let delay = argument(after: "--focused-text-delay-seconds", in: arguments)
        .flatMap(Double.init) ?? 0
    if delay > 0 {
        Thread.sleep(forTimeInterval: delay)
    }
    let diagnostic = FocusedTextCapture().diagnosticSnapshot()
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(diagnostic)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

let configuration = TranscriptionConfiguration.fromEnvironment()
let permissionSnapshot = PermissionDiagnostics.snapshot(expectedInputDeviceName: configuration.expectedInputDeviceName)
let report = buildReport(configuration: configuration, permissionSnapshot: permissionSnapshot)

if arguments.contains("--json") {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(report)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
} else {
    printHumanReport(report)
}
