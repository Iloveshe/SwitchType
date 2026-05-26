import Foundation

public enum SwitchTypePaths {
    public static func resolve(
        _ path: String,
        relativeTo root: URL,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> URL {
        if path == "~" {
            return homeDirectory
        }
        if path.hasPrefix("~/") {
            return homeDirectory.appendingPathComponent(String(path.dropFirst(2)))
        }

        if path.hasPrefix("/") {
            return URL(fileURLWithPath: path)
        }
        return root.appendingPathComponent(path)
    }
}
