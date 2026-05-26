import Foundation

public enum TranscriptionBackend: String, Codable, CaseIterable, Equatable {
    case localWhisper = "local_whisper"
    case command
    case httpJSON = "http_json"

    public var displayName: String {
        switch self {
        case .localWhisper:
            return "Local Whisper"
        case .command:
            return "Custom Command"
        case .httpJSON:
            return "HTTP JSON"
        }
    }
}

public enum LocalWhisperProfile: String, Codable, CaseIterable, Equatable {
    case custom
    case baseCPU = "base_cpu"
    case largeTurbo = "large_turbo"

    public var displayName: String {
        switch self {
        case .custom:
            return "Custom from asr.json"
        case .baseCPU:
            return "Base CPU"
        case .largeTurbo:
            return "Large Turbo"
        }
    }

    var modelPath: String? {
        switch self {
        case .custom:
            return nil
        case .baseCPU:
            return "./third_party/whisper.cpp/models/ggml-base.bin"
        case .largeTurbo:
            return "./third_party/whisper.cpp/models/ggml-large-v3-turbo.bin"
        }
    }

    var disableGPU: Bool? {
        switch self {
        case .custom:
            return nil
        case .baseCPU:
            return true
        case .largeTurbo:
            return false
        }
    }

    var timeoutSeconds: TimeInterval? {
        switch self {
        case .custom:
            return nil
        case .baseCPU:
            return 300
        case .largeTurbo:
            return 120
        }
    }
}

public enum HTTPASRProfile: String, Codable, CaseIterable, Equatable {
    case custom
    case qwen3OfficialLocal = "qwen3_official_local"

    public var displayName: String {
        switch self {
        case .custom:
            return "Custom from asr.json"
        case .qwen3OfficialLocal:
            return "Qwen3-ASR Official (Local HTTP)"
        }
    }

    var httpURL: String? {
        switch self {
        case .custom:
            return nil
        case .qwen3OfficialLocal:
            return "http://127.0.0.1:8765/transcribe"
        }
    }

    var httpFieldName: String? {
        switch self {
        case .custom:
            return nil
        case .qwen3OfficialLocal:
            return "audio"
        }
    }

    var httpTranscriptKey: String? {
        switch self {
        case .custom:
            return nil
        case .qwen3OfficialLocal:
            return "text"
        }
    }

    var timeoutSeconds: TimeInterval? {
        switch self {
        case .custom:
            return nil
        case .qwen3OfficialLocal:
            return 180
        }
    }
}

public struct TranscriptionConfiguration: Equatable {
    public var backend: TranscriptionBackend
    public var localWhisperProfile: LocalWhisperProfile
    public var httpASRProfile: HTTPASRProfile
    public var binaryPath: String
    public var modelPath: String
    public var disableGPU: Bool
    public var language: String
    public var initialPrompt: String?
    public var timeoutSeconds: TimeInterval
    public var transcriptOverride: String?
    public var expectedInputDeviceName: String?
    public var commandPath: String?
    public var commandArguments: [String]
    public var httpURL: String?
    public var httpHeaders: [String: String]
    public var httpFieldName: String
    public var httpTranscriptKey: String

    public init(
        backend: TranscriptionBackend = .localWhisper,
        localWhisperProfile: LocalWhisperProfile = .custom,
        httpASRProfile: HTTPASRProfile = .custom,
        binaryPath: String,
        modelPath: String,
        disableGPU: Bool = false,
        language: String = "zh",
        initialPrompt: String? = nil,
        timeoutSeconds: TimeInterval = 120,
        transcriptOverride: String? = nil,
        expectedInputDeviceName: String? = nil,
        commandPath: String? = nil,
        commandArguments: [String] = [],
        httpURL: String? = nil,
        httpHeaders: [String: String] = [:],
        httpFieldName: String = "audio",
        httpTranscriptKey: String = "text"
    ) {
        self.backend = backend
        self.localWhisperProfile = localWhisperProfile
        self.httpASRProfile = httpASRProfile
        self.binaryPath = binaryPath
        self.modelPath = modelPath
        self.disableGPU = disableGPU
        self.language = language
        self.initialPrompt = initialPrompt
        self.timeoutSeconds = timeoutSeconds
        self.transcriptOverride = transcriptOverride
        self.expectedInputDeviceName = expectedInputDeviceName
        self.commandPath = commandPath
        self.commandArguments = commandArguments
        self.httpURL = httpURL
        self.httpHeaders = httpHeaders
        self.httpFieldName = httpFieldName
        self.httpTranscriptKey = httpTranscriptKey
    }

    public static func fromEnvironment() -> TranscriptionConfiguration {
        fromEnvironment(ProcessInfo.processInfo.environment)
    }

    public static func fromEnvironment(
        _ environment: [String: String],
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    ) -> TranscriptionConfiguration {
        let fileConfig = ASRConfig.load(
            from: asrConfigCandidates(
                environment: environment,
                homeDirectory: homeDirectory,
                workingDirectory: workingDirectory
            )
        )
        let override = environment["SWITCHTYPE_TRANSCRIPT_OVERRIDE"]
        let localWhisperProfile = localWhisperProfileValue(
            environment["SWITCHTYPE_LOCAL_WHISPER_PROFILE"]
                ?? fileConfig?.localWhisperProfile
        )
        let httpASRProfile = httpASRProfileValue(
            environment["SWITCHTYPE_ASR_HTTP_PROFILE"]
                ?? fileConfig?.asrHTTPProfile
        )
        let expectedInputDeviceName = nonEmpty(environment["SWITCHTYPE_EXPECT_INPUT_DEVICE_NAME"])
            ?? nonEmpty(fileConfig?.expectedInputDeviceName)
        let language = nonEmpty(environment["SWITCHTYPE_WHISPER_LANGUAGE"])
            ?? nonEmpty(fileConfig?.whisperLanguage)
            ?? "zh"
        let backend = backendValue(
            environment["SWITCHTYPE_ASR_BACKEND"]
                ?? fileConfig?.asrBackend
        )
        let timeoutSeconds = TimeInterval(environment["SWITCHTYPE_ASR_TIMEOUT_SECONDS"] ?? "")
            ?? fileConfig?.timeoutSeconds
            ?? (backend == .httpJSON ? httpASRProfile.timeoutSeconds : nil)
            ?? localWhisperProfile.timeoutSeconds
            ?? 120
        return TranscriptionConfiguration(
            backend: backend,
            localWhisperProfile: localWhisperProfile,
            httpASRProfile: httpASRProfile,
            binaryPath: environment["SWITCHTYPE_WHISPER_BIN"]
                ?? fileConfig?.whisperBin
                ?? "./third_party/whisper.cpp/build/bin/whisper-cli",
            modelPath: environment["SWITCHTYPE_WHISPER_MODEL"]
                ?? fileConfig?.whisperModel
                ?? localWhisperProfile.modelPath
                ?? "./third_party/whisper.cpp/models/ggml-large-v3-turbo.bin",
            disableGPU: environment["SWITCHTYPE_WHISPER_NO_GPU"].map { $0 == "1" }
                ?? fileConfig?.whisperNoGPU
                ?? localWhisperProfile.disableGPU
                ?? false,
            language: language,
            timeoutSeconds: timeoutSeconds,
            transcriptOverride: override?.isEmpty == false ? override : nil,
            expectedInputDeviceName: expectedInputDeviceName,
            commandPath: nonEmpty(environment["SWITCHTYPE_ASR_COMMAND_PATH"]) ?? nonEmpty(fileConfig?.asrCommandPath),
            commandArguments: parseStringArray(environment["SWITCHTYPE_ASR_COMMAND_ARGS"])
                ?? fileConfig?.asrCommandArgs
                ?? ["{audio}"],
            httpURL: nonEmpty(environment["SWITCHTYPE_ASR_HTTP_URL"])
                ?? nonEmpty(fileConfig?.asrHTTPURL)
                ?? httpASRProfile.httpURL,
            httpHeaders: parseStringDictionary(environment["SWITCHTYPE_ASR_HTTP_HEADERS"])
                ?? fileConfig?.asrHTTPHeaders
                ?? [:],
            httpFieldName: nonEmpty(environment["SWITCHTYPE_ASR_HTTP_FIELD_NAME"])
                ?? nonEmpty(fileConfig?.asrHTTPFieldName)
                ?? httpASRProfile.httpFieldName
                ?? "audio",
            httpTranscriptKey: nonEmpty(environment["SWITCHTYPE_ASR_HTTP_TRANSCRIPT_KEY"])
                ?? nonEmpty(fileConfig?.asrHTTPTranscriptKey)
                ?? httpASRProfile.httpTranscriptKey
                ?? "text"
        )
    }

    public static func personalConfigURL(
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> URL {
        homeDirectory
            .appendingPathComponent(".switchtype")
            .appendingPathComponent("asr.json")
    }

    public static func writeBackendSelection(
        _ backend: TranscriptionBackend,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) throws -> URL {
        try writePersonalConfig(homeDirectory: homeDirectory) { object in
            object["asr_backend"] = backend.rawValue
        }
    }

    public static func writeLocalWhisperProfileSelection(
        _ profile: LocalWhisperProfile,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) throws -> URL {
        try writePersonalConfig(homeDirectory: homeDirectory) { object in
            object["asr_backend"] = TranscriptionBackend.localWhisper.rawValue
            object["local_whisper_profile"] = profile.rawValue
            if let modelPath = profile.modelPath {
                object["whisper_model"] = modelPath
            }
            if let disableGPU = profile.disableGPU {
                object["whisper_no_gpu"] = disableGPU
            }
            if let timeoutSeconds = profile.timeoutSeconds {
                object["timeout_seconds"] = timeoutSeconds
            }
            if profile != .custom {
                object["whisper_language"] = "zh"
            }
        }
    }

    public static func writeHTTPASRProfileSelection(
        _ profile: HTTPASRProfile,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) throws -> URL {
        try writePersonalConfig(homeDirectory: homeDirectory) { object in
            object["asr_backend"] = TranscriptionBackend.httpJSON.rawValue
            object["asr_http_profile"] = profile.rawValue
            if let httpURL = profile.httpURL {
                object["asr_http_url"] = httpURL
            }
            if let httpFieldName = profile.httpFieldName {
                object["asr_http_field_name"] = httpFieldName
            }
            if let httpTranscriptKey = profile.httpTranscriptKey {
                object["asr_http_transcript_key"] = httpTranscriptKey
            }
            if let timeoutSeconds = profile.timeoutSeconds {
                object["timeout_seconds"] = timeoutSeconds
            }
        }
    }

    public func whisperArguments(audioPath: String, outputBasePath: String) -> [String] {
        var arguments: [String] = []
        if disableGPU {
            arguments.append("-ng")
        }
        arguments.append(contentsOf: [
            "-m",
            modelPath,
            "-f",
            audioPath,
            "-l",
            language
        ])
        if let initialPrompt = initialPrompt?.trimmingCharacters(in: .whitespacesAndNewlines),
           !initialPrompt.isEmpty {
            arguments.append(contentsOf: [
                "--prompt",
                initialPrompt,
                "--carry-initial-prompt"
            ])
        }
        arguments.append(contentsOf: [
            "-otxt",
            "-of",
            outputBasePath
        ])
        return arguments
    }

    public func resolvedCommandArguments(audioPath: String) -> [String] {
        commandArguments.map { argument in
            argument
                .replacingOccurrences(of: "{audio}", with: audioPath)
                .replacingOccurrences(of: "{language}", with: language)
                .replacingOccurrences(of: "{prompt}", with: initialPrompt ?? "")
                .replacingOccurrences(of: "{model}", with: modelPath)
        }
    }

    public func resolvedLocalWhisperBinaryURL(
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
        bundleURL: URL = Bundle.main.bundleURL
    ) -> URL {
        resolveLocalWhisperPath(binaryPath, workingDirectory: workingDirectory, bundleURL: bundleURL)
    }

    public func resolvedLocalWhisperModelURL(
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
        bundleURL: URL = Bundle.main.bundleURL
    ) -> URL {
        resolveLocalWhisperPath(modelPath, workingDirectory: workingDirectory, bundleURL: bundleURL)
    }

    private static func backendValue(_ value: String?) -> TranscriptionBackend {
        guard let value = nonEmpty(value) else {
            return .localWhisper
        }
        return TranscriptionBackend(rawValue: value) ?? .localWhisper
    }

    private static func localWhisperProfileValue(_ value: String?) -> LocalWhisperProfile {
        guard let value = nonEmpty(value) else {
            return .custom
        }
        return LocalWhisperProfile(rawValue: value) ?? .custom
    }

    private static func httpASRProfileValue(_ value: String?) -> HTTPASRProfile {
        guard let value = nonEmpty(value) else {
            return .custom
        }
        return HTTPASRProfile(rawValue: value) ?? .custom
    }

    private static func writePersonalConfig(
        homeDirectory: URL,
        mutate: (inout [String: Any]) -> Void
    ) throws -> URL {
        let url = personalConfigURL(homeDirectory: homeDirectory)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )

        var object: [String: Any] = [:]
        if FileManager.default.fileExists(atPath: url.path),
           let data = try? Data(contentsOf: url),
           let existing = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            object = existing
        }
        mutate(&object)
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: url, options: .atomic)
        return url
    }

    private func resolveLocalWhisperPath(
        _ path: String,
        workingDirectory: URL,
        bundleURL: URL
    ) -> URL {
        if path == "~" || path.hasPrefix("~/") || path.hasPrefix("/") {
            return SwitchTypePaths.resolve(path, relativeTo: workingDirectory)
        }

        let candidates = localWhisperRootCandidates(
            workingDirectory: workingDirectory,
            bundleURL: bundleURL
        ).map { root in
            SwitchTypePaths.resolve(path, relativeTo: root)
        }
        return candidates.first { FileManager.default.fileExists(atPath: $0.path) }
            ?? candidates.first
            ?? SwitchTypePaths.resolve(path, relativeTo: workingDirectory)
    }

    private func localWhisperRootCandidates(workingDirectory: URL, bundleURL: URL) -> [URL] {
        var candidates = [workingDirectory]
        if let projectRoot = Self.projectRoot(fromWhisperBinaryPath: binaryPath) {
            candidates.append(projectRoot)
        }
        if let projectRoot = Self.projectRoot(fromBundleURL: bundleURL) {
            candidates.append(projectRoot)
        }

        var seen = Set<String>()
        return candidates.filter { url in
            let path = url.standardizedFileURL.path
            guard !seen.contains(path) else {
                return false
            }
            seen.insert(path)
            return true
        }
    }

    private static func projectRoot(fromWhisperBinaryPath path: String) -> URL? {
        let marker = "/third_party/whisper.cpp/"
        guard path.hasPrefix("/"),
              let range = path.range(of: marker) else {
            return nil
        }
        return URL(fileURLWithPath: String(path[..<range.lowerBound]))
    }

    private static func projectRoot(fromBundleURL bundleURL: URL) -> URL? {
        let standardized = bundleURL.standardizedFileURL
        guard standardized.pathExtension == "app" else {
            return nil
        }
        let parent = standardized.deletingLastPathComponent()
        if parent.lastPathComponent == "dist" {
            return parent.deletingLastPathComponent()
        }
        return nil
    }

    private static func nonEmpty(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed?.isEmpty == false ? trimmed : nil
    }

    private static func parseStringArray(_ value: String?) -> [String]? {
        guard let value = nonEmpty(value) else {
            return nil
        }
        if let data = value.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String].self, from: data) {
            return decoded
        }
        let lines = value.components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return lines.isEmpty ? nil : lines
    }

    private static func parseStringDictionary(_ value: String?) -> [String: String]? {
        guard let value = nonEmpty(value),
              let data = value.data(using: .utf8) else {
            return nil
        }
        return try? JSONDecoder().decode([String: String].self, from: data)
    }

    private static func asrConfigCandidates(
        environment: [String: String],
        homeDirectory: URL,
        workingDirectory: URL
    ) -> [URL] {
        var urls: [URL] = []
        if let path = environment["SWITCHTYPE_ASR_CONFIG"], !path.isEmpty {
            urls.append(
                SwitchTypePaths.resolve(
                    path,
                    relativeTo: workingDirectory,
                    homeDirectory: homeDirectory
                )
            )
        }
        urls.append(personalConfigURL(homeDirectory: homeDirectory))
        return urls
    }
}

private struct ASRConfig: Decodable {
    var asrBackend: String?
    var localWhisperProfile: String?
    var asrHTTPProfile: String?
    var whisperBin: String?
    var whisperModel: String?
    var whisperNoGPU: Bool?
    var whisperLanguage: String?
    var timeoutSeconds: TimeInterval?
    var expectedInputDeviceName: String?
    var asrCommandPath: String?
    var asrCommandArgs: [String]?
    var asrHTTPURL: String?
    var asrHTTPHeaders: [String: String]?
    var asrHTTPFieldName: String?
    var asrHTTPTranscriptKey: String?

    private enum CodingKeys: String, CodingKey {
        case asrBackend = "asr_backend"
        case localWhisperProfile = "local_whisper_profile"
        case asrHTTPProfile = "asr_http_profile"
        case whisperBin = "whisper_bin"
        case whisperModel = "whisper_model"
        case whisperNoGPU = "whisper_no_gpu"
        case whisperLanguage = "whisper_language"
        case timeoutSeconds = "timeout_seconds"
        case expectedInputDeviceName = "expected_input_device_name"
        case asrCommandPath = "asr_command_path"
        case asrCommandArgs = "asr_command_args"
        case asrHTTPURL = "asr_http_url"
        case asrHTTPHeaders = "asr_http_headers"
        case asrHTTPFieldName = "asr_http_field_name"
        case asrHTTPTranscriptKey = "asr_http_transcript_key"
    }

    static func load(from urls: [URL]) -> ASRConfig? {
        for url in urls where FileManager.default.fileExists(atPath: url.path) {
            if let data = try? Data(contentsOf: url),
               let config = try? JSONDecoder().decode(ASRConfig.self, from: data) {
                return config
            }
        }
        return nil
    }
}

public enum TranscriptionServiceError: Error, LocalizedError {
    case missingBinary(String)
    case missingModel(String)
    case missingCommand(String)
    case missingHTTPURL
    case invalidHTTPURL(String)
    case processFailed(String)
    case noTranscript
    case timedOut

    public var errorDescription: String? {
        switch self {
        case .missingBinary(let path):
            return "Missing whisper.cpp binary: \(path)"
        case .missingModel(let path):
            return "Missing whisper.cpp model: \(path)"
        case .missingCommand(let path):
            return "Missing ASR command: \(path)"
        case .missingHTTPURL:
            return "Missing ASR HTTP URL."
        case .invalidHTTPURL(let value):
            return "Invalid ASR HTTP URL: \(value)"
        case .processFailed(let message):
            return "Transcription failed: \(message)"
        case .noTranscript:
            return "Transcription finished without transcript output."
        case .timedOut:
            return "Transcription timed out."
        }
    }
}

public typealias TranscriptionEventLogger = (String) -> Void

private struct ProcessResult {
    var status: Int32
    var stdout: String
    var stderr: String
}

private final class ProcessOutputBuffer {
    private let lock = NSLock()
    private var data = Data()

    func append(_ chunk: Data) {
        guard !chunk.isEmpty else {
            return
        }
        lock.lock()
        data.append(chunk)
        lock.unlock()
    }

    func appendAvailableData(from handle: FileHandle) {
        append(handle.availableData)
    }

    func text() -> String {
        lock.lock()
        let snapshot = data
        lock.unlock()
        return String(data: snapshot, encoding: .utf8) ?? ""
    }
}

private enum ProcessRunner {
    static func run(
        executableURL: URL,
        arguments: [String],
        timeoutSeconds: TimeInterval
    ) throws -> ProcessResult {
        let process = Process()
        process.executableURL = executableURL
        process.arguments = arguments

        let stdout = Pipe()
        let stderr = Pipe()
        let stdoutBuffer = ProcessOutputBuffer()
        let stderrBuffer = ProcessOutputBuffer()
        process.standardOutput = stdout
        process.standardError = stderr
        stdout.fileHandleForReading.readabilityHandler = { handle in
            stdoutBuffer.appendAvailableData(from: handle)
        }
        stderr.fileHandleForReading.readabilityHandler = { handle in
            stderrBuffer.appendAvailableData(from: handle)
        }
        defer {
            stdout.fileHandleForReading.readabilityHandler = nil
            stderr.fileHandleForReading.readabilityHandler = nil
        }

        try process.run()
        if !waitUntilExit(process, timeoutSeconds: timeoutSeconds) {
            process.terminate()
            throw TranscriptionServiceError.timedOut
        }
        stdout.fileHandleForReading.readabilityHandler = nil
        stderr.fileHandleForReading.readabilityHandler = nil
        stdoutBuffer.append(stdout.fileHandleForReading.readDataToEndOfFile())
        stderrBuffer.append(stderr.fileHandleForReading.readDataToEndOfFile())

        return ProcessResult(
            status: process.terminationStatus,
            stdout: stdoutBuffer.text(),
            stderr: stderrBuffer.text()
        )
    }

    private static func waitUntilExit(_ process: Process, timeoutSeconds: TimeInterval) -> Bool {
        guard timeoutSeconds > 0 else {
            process.waitUntilExit()
            return true
        }

        let deadline = Date().addingTimeInterval(timeoutSeconds)
        while process.isRunning {
            if Date() >= deadline {
                return false
            }
            Thread.sleep(forTimeInterval: min(0.02, max(0, deadline.timeIntervalSinceNow)))
        }
        return true
    }
}

public final class TranscriptionService {
    private let configuration: TranscriptionConfiguration
    private let eventLogger: TranscriptionEventLogger?

    public init(
        configuration: TranscriptionConfiguration = .fromEnvironment(),
        eventLogger: TranscriptionEventLogger? = nil
    ) {
        self.configuration = configuration
        self.eventLogger = eventLogger
    }

    public func transcribe(audioURL: URL) throws -> String {
        if let transcriptOverride = configuration.transcriptOverride {
            eventLogger?(
                "latency asr_override backend=\(configuration.backend.rawValue) chars=\(transcriptOverride.count)"
            )
            return transcriptOverride
        }

        eventLogger?(
            "latency asr_begin backend=\(configuration.backend.rawValue) "
                + "local_profile=\(configuration.localWhisperProfile.rawValue) "
                + "http_profile=\(configuration.httpASRProfile.rawValue) "
                + "timeout_seconds=\(Int(configuration.timeoutSeconds)) "
                + "audio=\(audioURL.lastPathComponent) "
                + "audio_bytes=\(Self.fileSizeBytes(audioURL))"
        )
        let startedAt = Date()
        do {
            let transcript: String
            switch configuration.backend {
            case .localWhisper:
                transcript = try LocalWhisperTranscriptionService(
                    configuration: configuration,
                    eventLogger: eventLogger
                ).transcribe(audioURL: audioURL)
            case .command:
                transcript = try CommandTranscriptionService(
                    configuration: configuration,
                    eventLogger: eventLogger
                ).transcribe(audioURL: audioURL)
            case .httpJSON:
                transcript = try HTTPJSONTranscriptionService(
                    configuration: configuration,
                    eventLogger: eventLogger
                ).transcribe(audioURL: audioURL)
            }
            eventLogger?(
                "latency asr_total_ms=\(Self.milliseconds(since: startedAt)) "
                    + "backend=\(configuration.backend.rawValue) chars=\(transcript.count)"
            )
            return transcript
        } catch {
            eventLogger?(
                "latency asr_failed_ms=\(Self.milliseconds(since: startedAt)) "
                    + "backend=\(configuration.backend.rawValue) error=\(error.localizedDescription)"
            )
            throw error
        }
    }

    private static func fileSizeBytes(_ url: URL) -> Int64 {
        let values = try? url.resourceValues(forKeys: [.fileSizeKey])
        return Int64(values?.fileSize ?? 0)
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}

private final class LocalWhisperTranscriptionService {
    private let configuration: TranscriptionConfiguration
    private let eventLogger: TranscriptionEventLogger?

    init(configuration: TranscriptionConfiguration, eventLogger: TranscriptionEventLogger?) {
        self.configuration = configuration
        self.eventLogger = eventLogger
    }

    func transcribe(audioURL: URL) throws -> String {
        let binaryURL = configuration.resolvedLocalWhisperBinaryURL()
        let modelURL = configuration.resolvedLocalWhisperModelURL()
        guard FileManager.default.isExecutableFile(atPath: binaryURL.path) else {
            throw TranscriptionServiceError.missingBinary(configuration.binaryPath)
        }
        guard FileManager.default.fileExists(atPath: modelURL.path) else {
            throw TranscriptionServiceError.missingModel(configuration.modelPath)
        }

        let outputBase = FileManager.default.temporaryDirectory
            .appendingPathComponent("switchtype-transcript-\(UUID().uuidString)")
        let transcriptURL = outputBase.appendingPathExtension("txt")
        defer { try? FileManager.default.removeItem(at: transcriptURL) }

        var commandConfiguration = configuration
        commandConfiguration.modelPath = modelURL.path
        let result = try runWhisper(
            binaryURL: binaryURL,
            configuration: commandConfiguration,
            audioURL: audioURL,
            outputBase: outputBase
        )
        if result.status != 0 {
            if shouldRetryWithCPUFallback(result: result, configuration: commandConfiguration) {
                try? FileManager.default.removeItem(at: transcriptURL)
                var cpuConfiguration = commandConfiguration
                cpuConfiguration.disableGPU = true
                let fallbackResult = try runWhisper(
                    binaryURL: binaryURL,
                    configuration: cpuConfiguration,
                    audioURL: audioURL,
                    outputBase: outputBase
                )
                if fallbackResult.status != 0 {
                    throw TranscriptionServiceError.processFailed(
                        cpuFallbackFailureMessage(
                            originalStderr: result.stderr,
                            fallbackStderr: fallbackResult.stderr
                        )
                    )
                }
                return try readTranscript(from: transcriptURL, result: fallbackResult)
            }
            throw TranscriptionServiceError.processFailed(
                result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            )
        }
        return try readTranscript(from: transcriptURL, result: result)
    }

    private func runWhisper(
        binaryURL: URL,
        configuration: TranscriptionConfiguration,
        audioURL: URL,
        outputBase: URL
    ) throws -> ProcessResult {
        let startedAt = Date()
        let result = try ProcessRunner.run(
            executableURL: binaryURL,
            arguments: configuration.whisperArguments(
                audioPath: audioURL.path,
                outputBasePath: outputBase.path
            ),
            timeoutSeconds: configuration.timeoutSeconds
        )
        eventLogger?(
            "latency local_whisper_process_ms=\(Self.milliseconds(since: startedAt)) "
                + "status=\(result.status) gpu_disabled=\(configuration.disableGPU)"
        )
        return result
    }

    private func readTranscript(from transcriptURL: URL, result: ProcessResult) throws -> String {
        let startedAt = Date()
        let transcript: String
        if FileManager.default.fileExists(atPath: transcriptURL.path) {
            transcript = try String(contentsOf: transcriptURL, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        } else {
            transcript = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        guard !transcript.isEmpty else {
            throw TranscriptionServiceError.noTranscript
        }
        eventLogger?(
            "latency local_whisper_read_transcript_ms=\(Self.milliseconds(since: startedAt)) chars=\(transcript.count)"
        )
        return transcript
    }

    private func shouldRetryWithCPUFallback(
        result: ProcessResult,
        configuration: TranscriptionConfiguration
    ) -> Bool {
        guard !configuration.disableGPU else {
            return false
        }
        return isMetalInitializationFailure(result.stderr) || isMetalInitializationFailure(result.stdout)
    }

    private func isMetalInitializationFailure(_ output: String) -> Bool {
        let lowercased = output.lowercased()
        return lowercased.contains("ggml_metal_buffer_init")
            || lowercased.contains("failed to allocate buffer")
            || (lowercased.contains("metal") && lowercased.contains("failed"))
    }

    private func cpuFallbackFailureMessage(originalStderr: String, fallbackStderr: String) -> String {
        let original = originalStderr.trimmingCharacters(in: .whitespacesAndNewlines)
        let fallback = fallbackStderr.trimmingCharacters(in: .whitespacesAndNewlines)
        return """
        Metal/GPU transcription failed; CPU fallback was attempted but also failed.

        Original GPU error:
        \(original)

        CPU fallback error:
        \(fallback)
        """
        .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}

public final class CommandTranscriptionService {
    private let configuration: TranscriptionConfiguration
    private let eventLogger: TranscriptionEventLogger?

    public init(configuration: TranscriptionConfiguration, eventLogger: TranscriptionEventLogger? = nil) {
        self.configuration = configuration
        self.eventLogger = eventLogger
    }

    public func transcribe(audioURL: URL) throws -> String {
        let commandPath = configuration.commandPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !commandPath.isEmpty else {
            throw TranscriptionServiceError.missingCommand("")
        }
        let commandURL = SwitchTypePaths.resolve(
            commandPath,
            relativeTo: URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        )
        guard FileManager.default.isExecutableFile(atPath: commandURL.path) else {
            throw TranscriptionServiceError.missingCommand(commandPath)
        }

        let startedAt = Date()
        let result = try ProcessRunner.run(
            executableURL: commandURL,
            arguments: configuration.resolvedCommandArguments(audioPath: audioURL.path),
            timeoutSeconds: configuration.timeoutSeconds
        )
        eventLogger?(
            "latency command_process_ms=\(Self.milliseconds(since: startedAt)) status=\(result.status)"
        )
        if result.status != 0 {
            throw TranscriptionServiceError.processFailed(result.stderr.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        let transcript = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !transcript.isEmpty else {
            throw TranscriptionServiceError.noTranscript
        }
        return transcript
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}

public final class HTTPJSONTranscriptionService {
    private let configuration: TranscriptionConfiguration
    private let eventLogger: TranscriptionEventLogger?

    public init(configuration: TranscriptionConfiguration, eventLogger: TranscriptionEventLogger? = nil) {
        self.configuration = configuration
        self.eventLogger = eventLogger
    }

    public func transcribe(audioURL: URL) throws -> String {
        guard let rawURL = configuration.httpURL?.trimmingCharacters(in: .whitespacesAndNewlines),
              !rawURL.isEmpty else {
            throw TranscriptionServiceError.missingHTTPURL
        }
        guard let url = URL(string: rawURL) else {
            throw TranscriptionServiceError.invalidHTTPURL(rawURL)
        }

        let boundary = "SwitchTypeBoundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = configuration.timeoutSeconds
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        for (name, value) in configuration.httpHeaders {
            request.setValue(value, forHTTPHeaderField: name)
        }
        let bodyStartedAt = Date()
        let body = try multipartBody(
            audioURL: audioURL,
            fieldName: configuration.httpFieldName,
            boundary: boundary
        )
        eventLogger?(
            "latency http_body_ms=\(Self.milliseconds(since: bodyStartedAt)) "
                + "audio_bytes=\(Self.fileSizeBytes(audioURL)) body_bytes=\(body.count)"
        )
        request.httpBody = body

        let semaphore = DispatchSemaphore(value: 0)
        var responseData: Data?
        var response: URLResponse?
        var responseError: Error?
        let roundtripStartedAt = Date()
        URLSession.shared.dataTask(with: request) { data, urlResponse, error in
            responseData = data
            response = urlResponse
            responseError = error
            semaphore.signal()
        }.resume()

        if semaphore.wait(timeout: .now() + configuration.timeoutSeconds) == .timedOut {
            throw TranscriptionServiceError.timedOut
        }
        if let responseError {
            throw responseError
        }
        let roundtripMS = Self.milliseconds(since: roundtripStartedAt)
        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
        let responseByteCount = responseData?.count ?? 0
        eventLogger?(
            "latency http_roundtrip_ms=\(roundtripMS) "
                + "status=\(statusCode) response_bytes=\(responseByteCount) "
                + Self.serverLatencySummary(from: response as? HTTPURLResponse)
        )
        if let httpResponse = response as? HTTPURLResponse,
           !(200..<300).contains(httpResponse.statusCode) {
            throw TranscriptionServiceError.processFailed("HTTP \(httpResponse.statusCode)")
        }
        guard let responseData else {
            throw TranscriptionServiceError.noTranscript
        }
        let extractStartedAt = Date()
        let transcript = try Self.extractTranscript(from: responseData, keyPath: configuration.httpTranscriptKey)
        eventLogger?(
            "latency http_extract_ms=\(Self.milliseconds(since: extractStartedAt)) chars=\(transcript.count)"
        )
        return transcript
    }

    public static func extractTranscript(from data: Data, keyPath: String) throws -> String {
        let object = try JSONSerialization.jsonObject(with: data)
        let keys = keyPath.split(separator: ".").map(String.init)
        let value = keys.reduce(object as Any?) { current, key in
            guard let dictionary = current as? [String: Any] else {
                return nil
            }
            return dictionary[key]
        }
        guard let transcript = value as? String,
              !transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw TranscriptionServiceError.noTranscript
        }
        return transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func multipartBody(audioURL: URL, fieldName: String, boundary: String) throws -> Data {
        var data = Data()
        data.append(Data("--\(boundary)\r\n".utf8))
        data.append(Data("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(audioURL.lastPathComponent)\"\r\n".utf8))
        data.append(Data("Content-Type: audio/wav\r\n\r\n".utf8))
        data.append(try Data(contentsOf: audioURL))
        data.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return data
    }

    private static func serverLatencySummary(from response: HTTPURLResponse?) -> String {
        guard let response else {
            return "server_total_ms=unknown"
        }
        var entries: [String] = []
        for (name, value) in response.allHeaderFields {
            let rawName = String(describing: name)
            let lowercased = rawName.lowercased()
            guard lowercased.hasPrefix("x-switchtype-server-") else {
                continue
            }
            let key = lowercased
                .replacingOccurrences(of: "x-switchtype-server-", with: "server_")
                .replacingOccurrences(of: "-", with: "_")
            entries.append("\(key)=\(value)")
        }
        return entries.sorted().joined(separator: " ")
    }

    private static func fileSizeBytes(_ url: URL) -> Int64 {
        let values = try? url.resourceValues(forKeys: [.fileSizeKey])
        return Int64(values?.fileSize ?? 0)
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}
