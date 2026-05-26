import Foundation

final class AppEventLogger {
    private let logURL: URL
    private let formatter = ISO8601DateFormatter()
    private let queue = DispatchQueue(label: "dev.switchtype.app-event-logger")

    init(
        logURL: URL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/SwitchType", isDirectory: true)
            .appendingPathComponent("app.log")
    ) {
        self.logURL = logURL
    }

    func write(_ message: String) {
        let line = "\(formatter.string(from: Date())) \(message)\n"
        queue.async { [logURL] in
            do {
                try FileManager.default.createDirectory(
                    at: logURL.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                let data = Data(line.utf8)
                if FileManager.default.fileExists(atPath: logURL.path) {
                    let handle = try FileHandle(forWritingTo: logURL)
                    defer {
                        try? handle.close()
                    }
                    try handle.seekToEnd()
                    try handle.write(contentsOf: data)
                } else {
                    try data.write(to: logURL, options: .atomic)
                }
            } catch {
                // Logging must never interfere with the hotkey path.
            }
        }
    }
}
