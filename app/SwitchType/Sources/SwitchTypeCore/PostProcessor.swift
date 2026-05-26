import Foundation

public enum HotwordEditorValidationError: Error, Equatable, LocalizedError {
    case invalidReplacementLine(lineNumber: Int, line: String)

    public var errorDescription: String? {
        switch self {
        case .invalidReplacementLine(let lineNumber, let line):
            return "Replacement line \(lineNumber) must use `wrong => correct`: \(line)"
        }
    }
}

public struct HotwordConfig: Codable, Equatable {
    public var protectedTerms: [String]
    public var replacements: [String: String]

    private enum CodingKeys: String, CodingKey {
        case protectedTerms = "protected_terms"
        case replacements
    }

    public init(protectedTerms: [String], replacements: [String: String]) {
        self.protectedTerms = protectedTerms
        self.replacements = replacements
    }

    public static let developerDefault = HotwordConfig(
        protectedTerms: [
            "Codex",
            "MCP",
            "MCP server",
            "SeaTalk",
            "prelive",
            "Go",
            "Go service",
            "p99",
            "latency",
            "PR",
            "issue",
            "CI",
            "branch",
            "rebase",
            "main",
            "smoke test",
            "prompt",
            "flaky test"
        ],
        replacements: [
            "扣德克斯": "Codex",
            "皮阿尔": "PR",
            "马克皮": "MCP",
            "勾语言": "Go",
            "codeexp": "Codex",
            "Code S Promote": "Codex prompt",
            "口袋pro": "Codex prompt",
            "FLAG test": "flaky test",
            "fl test": "flaky test",
            "MCPso": "MCP server",
            "p one name": "prelive",
            "say talk": "SeaTalk",
            "Ctalk": "SeaTalk",
            "branchre倒": "branch rebase 到",
            "branchre": "branch rebase",
            "一次smoke": "一次 smoke test",
            "公serv": "Go service",
            "P99来腾": "p99 latency"
        ]
    )

    public static func load(from url: URL) throws -> HotwordConfig {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(HotwordConfig.self, from: data)
    }

    public func write(to url: URL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(self)
        try data.write(to: url, options: .atomic)
    }

    public static func fromEditorText(
        protectedTermsText: String,
        replacementsText: String
    ) throws -> HotwordConfig {
        var protectedTerms: [String] = []
        var seenProtectedTerms = Set<String>()
        for term in normalizedEditorLines(protectedTermsText) where !seenProtectedTerms.contains(term) {
            protectedTerms.append(term)
            seenProtectedTerms.insert(term)
        }

        var replacements: [String: String] = [:]
        for (index, rawLine) in replacementsText.components(separatedBy: .newlines).enumerated() {
            let trimmedLine = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmedLine.isEmpty else {
                continue
            }
            let parts = trimmedLine.components(separatedBy: "=>")
            guard parts.count == 2 else {
                throw HotwordEditorValidationError.invalidReplacementLine(lineNumber: index + 1, line: rawLine)
            }
            let source = parts[0].trimmingCharacters(in: .whitespacesAndNewlines)
            let target = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !source.isEmpty, !target.isEmpty else {
                throw HotwordEditorValidationError.invalidReplacementLine(lineNumber: index + 1, line: rawLine)
            }
            replacements[source] = target
        }

        return HotwordConfig(protectedTerms: protectedTerms, replacements: replacements)
    }

    public var editorProtectedTermsText: String {
        Self.uniquePreservingOrder(Self.normalizedEditorLines(protectedTerms.joined(separator: "\n")))
            .joined(separator: "\n")
    }

    public var editorReplacementsText: String {
        replacements.keys
            .sorted { lhs, rhs in
                lhs.localizedCaseInsensitiveCompare(rhs) == .orderedAscending
            }
            .map { source in
                "\(source) => \(replacements[source] ?? "")"
            }
            .joined(separator: "\n")
    }

    public static func personalURL(
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> URL {
        homeDirectory
            .appendingPathComponent(".switchtype")
            .appendingPathComponent("hotwords.json")
    }

    public static func ensurePersonalConfig(
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) throws -> URL {
        let url = personalURL(homeDirectory: homeDirectory)
        guard !FileManager.default.fileExists(atPath: url.path) else {
            return url
        }

        try developerDefault.write(to: url)
        return url
    }

    public func asrPrompt(maxTerms: Int = 80) -> String? {
        let terms = Array(
            Set(protectedTerms + replacements.values)
        )
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted { lhs, rhs in
                lhs.localizedCaseInsensitiveCompare(rhs) == .orderedAscending
            }
            .prefix(maxTerms)

        guard !terms.isEmpty else {
            return nil
        }
        return "请用简体中文转写，可保留英文技术词。可能出现的术语：" + terms.joined(separator: ", ")
    }

    public static func candidateURLs(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
        bundleResourceURL: URL? = Bundle.main.resourceURL,
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    ) -> [URL] {
        var urls: [URL] = []
        if let path = environment["SWITCHTYPE_HOTWORDS_CONFIG"], !path.isEmpty {
            urls.append(SwitchTypePaths.resolve(path, relativeTo: workingDirectory, homeDirectory: homeDirectory))
        }
        urls.append(
            homeDirectory
                .appendingPathComponent(".switchtype")
                .appendingPathComponent("hotwords.json")
        )
        if let bundleResourceURL {
            urls.append(bundleResourceURL.appendingPathComponent("hotwords.example.json"))
        }
        urls.append(
            workingDirectory.appendingPathComponent("../../bench/config/hotwords.example.json")
        )
        return urls
    }

    public static func loadDefault(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
        bundleResourceURL: URL? = Bundle.main.resourceURL,
        workingDirectory: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    ) -> HotwordConfig {
        for url in candidateURLs(
            environment: environment,
            homeDirectory: homeDirectory,
            bundleResourceURL: bundleResourceURL,
            workingDirectory: workingDirectory
        ) where FileManager.default.fileExists(atPath: url.path) {
            if let config = try? load(from: url) {
                return config
            }
        }
        return .developerDefault
    }

    private static func normalizedEditorLines(_ text: String) -> [String] {
        text.components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func uniquePreservingOrder(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var output: [String] = []
        for value in values where !seen.contains(value) {
            output.append(value)
            seen.insert(value)
        }
        return output
    }
}

public final class PostProcessor {
    private let config: HotwordConfig

    public init(config: HotwordConfig) {
        self.config = config
    }

    public func process(_ text: String) -> String {
        var output = simplifyChinese(text.trimmingCharacters(in: .whitespacesAndNewlines))
        for (source, target) in config.replacements {
            output = output.replacingOccurrences(of: source, with: target)
        }
        output = collapseWhitespace(output)
        for term in config.protectedTerms where term.canBeConverted(to: .ascii) {
            output = normalizeSpacedAcronym(term, in: output)
            output = spaceAsciiTerm(term, in: output)
        }
        return output.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func simplifyChinese(_ text: String) -> String {
        let mutable = NSMutableString(string: text)
        guard CFStringTransform(mutable, nil, "Traditional-Simplified" as CFString, false) else {
            return text
        }
        return mutable as String
    }

    private func collapseWhitespace(_ text: String) -> String {
        text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
    }

    private func spaceAsciiTerm(_ term: String, in text: String) -> String {
        let escaped = NSRegularExpression.escapedPattern(for: term)
        var output = text.replacingOccurrences(
            of: "(\\p{Han})(\(escaped))",
            with: "$1 $2",
            options: .regularExpression
        )
        output = output.replacingOccurrences(
            of: "(\(escaped))(\\p{Han})",
            with: "$1 $2",
            options: .regularExpression
        )
        return collapseWhitespace(output)
    }

    private func normalizeSpacedAcronym(_ term: String, in text: String) -> String {
        guard term.count >= 2,
              term == term.uppercased(),
              term.range(of: #"^[A-Z]+$"#, options: .regularExpression) != nil else {
            return text
        }

        let spacedLetters = term.map { NSRegularExpression.escapedPattern(for: String($0)) }
            .joined(separator: #"\s+"#)
        return text.replacingOccurrences(
            of: #"(?i)\b"# + spacedLetters + #"\b"#,
            with: term,
            options: .regularExpression
        )
    }
}
