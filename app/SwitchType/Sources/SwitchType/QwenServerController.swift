import Foundation
import SwitchTypeCore

struct QwenServerHealth {
    let ok: Bool
    let model: String?
    let modelLoaded: Bool
    let latencyMS: Int
    let deviceMap: String?
    let dtype: String?

    var menuTitle: String {
        guard ok else {
            return "Qwen Server: Stopped"
        }
        let state = modelLoaded ? "Ready" : "Running"
        if let deviceMap, !deviceMap.isEmpty {
            return "Qwen Server: \(state) (\(deviceMap))"
        }
        return "Qwen Server: \(state)"
    }

    var logDetails: String {
        "ok=\(ok) model_loaded=\(modelLoaded) latency_ms=\(latencyMS) "
            + "device_map=\(deviceMap ?? "unknown") dtype=\(dtype ?? "unknown")"
    }
}

enum QwenServerControllerError: Error, LocalizedError {
    case unsupportedProfile
    case invalidHTTPURL(String)
    case missingPython(String)
    case missingServerScript(String)
    case noHealthResponse
    case launchctlFailed(String)

    var errorDescription: String? {
        switch self {
        case .unsupportedProfile:
            return "Qwen server controls require the Qwen3-ASR Official (Local HTTP) profile."
        case .invalidHTTPURL(let value):
            return "Invalid Qwen server URL: \(value)"
        case .missingPython(let path):
            return "Missing Qwen Python runtime: \(path)"
        case .missingServerScript(let path):
            return "Missing Qwen server script: \(path)"
        case .noHealthResponse:
            return "Qwen server did not return a health response."
        case .launchctlFailed(let message):
            return "launchctl failed: \(message)"
        }
    }
}

final class QwenServerController {
    private let configuration: TranscriptionConfiguration
    private let environment: [String: String]
    private let bundleURL: URL
    private let workingDirectory: URL

    private let launchLabel = "dev.switchtype.qwen3-asr"
    private let defaultPythonPath = "/private/tmp/switchtype-qwen3-venv/bin/python"
    private let stdoutLogPath = "/private/tmp/switchtype-qwen3-asr-server.out.log"
    private let stderrLogPath = "/private/tmp/switchtype-qwen3-asr-server.err.log"

    init(
        configuration: TranscriptionConfiguration,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundleURL: URL = Bundle.main.bundleURL,
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    ) {
        self.configuration = configuration
        self.environment = environment
        self.bundleURL = bundleURL
        self.workingDirectory = workingDirectory
    }

    var isSupported: Bool {
        configuration.httpASRProfile == .qwen3OfficialLocal
    }

    func health(timeoutSeconds: TimeInterval = 2) throws -> QwenServerHealth {
        let start = Date()
        let payload = try requestJSON(path: "/health", timeoutSeconds: timeoutSeconds)
        return QwenServerHealth(
            ok: payload["ok"] as? Bool ?? false,
            model: payload["model"] as? String,
            modelLoaded: payload["model_loaded"] as? Bool ?? false,
            latencyMS: Self.milliseconds(since: start),
            deviceMap: payload["device_map"] as? String,
            dtype: payload["dtype"] as? String
        )
    }

    func start() throws {
        try ensureSupported()
        if (try? health(timeoutSeconds: 1)).map(\.ok) == true {
            return
        }
        try? runLaunchctl(arguments: ["remove", launchLabel])

        let pythonURL = try resolvedPythonURL()
        let scriptURL = try resolvedServerScriptURL()
        let endpoint = try endpointParts()
        try runLaunchctl(arguments: [
            "submit",
            "-l", launchLabel,
            "-o", stdoutLogPath,
            "-e", stderrLogPath,
            "--",
            pythonURL.path,
            scriptURL.path,
            "--host", endpoint.host,
            "--port", String(endpoint.port),
            "--model", "Qwen/Qwen3-ASR-0.6B",
            "--language", "Chinese",
            "--device-map", environment["SWITCHTYPE_QWEN3_ASR_DEVICE_MAP"] ?? "cpu",
            "--dtype", environment["SWITCHTYPE_QWEN3_ASR_DTYPE"] ?? "auto"
        ])
    }

    func stop() throws {
        try runLaunchctl(arguments: ["remove", launchLabel])
    }

    func warmUp(timeoutSeconds: TimeInterval = 180) throws -> QwenServerHealth {
        let start = Date()
        let payload = try requestJSON(path: "/warmup", timeoutSeconds: timeoutSeconds)
        return QwenServerHealth(
            ok: payload["ok"] as? Bool ?? false,
            model: payload["model"] as? String,
            modelLoaded: payload["model_loaded"] as? Bool ?? false,
            latencyMS: Self.milliseconds(since: start),
            deviceMap: payload["device_map"] as? String,
            dtype: payload["dtype"] as? String
        )
    }

    private func ensureSupported() throws {
        guard isSupported else {
            throw QwenServerControllerError.unsupportedProfile
        }
    }

    private func requestJSON(path: String, timeoutSeconds: TimeInterval) throws -> [String: Any] {
        try ensureSupported()
        guard let url = serverURL(path: path) else {
            throw QwenServerControllerError.invalidHTTPURL(configuration.httpURL ?? "")
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = timeoutSeconds
        let semaphore = DispatchSemaphore(value: 0)
        var responseData: Data?
        var responseError: Error?
        URLSession.shared.dataTask(with: request) { data, _, error in
            responseData = data
            responseError = error
            semaphore.signal()
        }.resume()

        if semaphore.wait(timeout: .now() + timeoutSeconds) == .timedOut {
            throw TranscriptionServiceError.timedOut
        }
        if let responseError {
            throw responseError
        }
        guard let responseData else {
            throw QwenServerControllerError.noHealthResponse
        }
        guard let object = try JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
            throw QwenServerControllerError.noHealthResponse
        }
        return object
    }

    private func serverURL(path: String) -> URL? {
        guard let rawURL = configuration.httpURL,
              let url = URL(string: rawURL),
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.path = path
        components.query = nil
        return components.url
    }

    private func endpointParts() throws -> (host: String, port: Int) {
        guard let rawURL = configuration.httpURL,
              let url = URL(string: rawURL),
              let host = url.host else {
            throw QwenServerControllerError.invalidHTTPURL(configuration.httpURL ?? "")
        }
        return (host, url.port ?? 8765)
    }

    private func resolvedPythonURL() throws -> URL {
        let path = environment["SWITCHTYPE_QWEN3_ASR_PYTHON"] ?? defaultPythonPath
        let url = SwitchTypePaths.resolve(path, relativeTo: workingDirectory)
        guard FileManager.default.isExecutableFile(atPath: url.path) else {
            throw QwenServerControllerError.missingPython(url.path)
        }
        return url
    }

    private func resolvedServerScriptURL() throws -> URL {
        let url = projectRoot()
            .appendingPathComponent("scripts")
            .appendingPathComponent("qwen3_asr_server.py")
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw QwenServerControllerError.missingServerScript(url.path)
        }
        return url
    }

    private func projectRoot() -> URL {
        let standardizedBundleURL = bundleURL.standardizedFileURL
        if standardizedBundleURL.pathExtension == "app" {
            let parent = standardizedBundleURL.deletingLastPathComponent()
            if parent.lastPathComponent == "dist" {
                return parent.deletingLastPathComponent()
            }
        }
        return workingDirectory
    }

    private func runLaunchctl(arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = arguments

        let stderr = Pipe()
        process.standardError = stderr
        try process.run()
        process.waitUntilExit()

        if process.terminationStatus != 0 {
            let data = stderr.fileHandleForReading.readDataToEndOfFile()
            let message = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            throw QwenServerControllerError.launchctlFailed(message?.isEmpty == false ? message! : "\(process.terminationStatus)")
        }
    }

    private static func milliseconds(since start: Date) -> Int {
        Int(Date().timeIntervalSince(start) * 1000)
    }
}
