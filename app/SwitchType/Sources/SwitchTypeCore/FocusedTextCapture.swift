import ApplicationServices
import AppKit
import Foundation

public struct FocusedTextSnapshot {
    public let value: String
    public let processIdentifier: pid_t?
    public let selectedRange: NSRange?

    public init(value: String, processIdentifier: pid_t? = nil, selectedRange: NSRange? = nil) {
        self.value = value
        self.processIdentifier = processIdentifier
        self.selectedRange = selectedRange
    }
}

public struct FocusedTextDeltaAnalysis {
    public let insertedText: String?
    public let reason: String

    public init(insertedText: String?, reason: String) {
        self.insertedText = insertedText
        self.reason = reason
    }
}

public struct FocusedTextDeltaMatch {
    public let analysis: FocusedTextDeltaAnalysis
    public let beforeSnapshot: FocusedTextSnapshot?
    public let afterSnapshot: FocusedTextSnapshot?

    public init(
        analysis: FocusedTextDeltaAnalysis,
        beforeSnapshot: FocusedTextSnapshot?,
        afterSnapshot: FocusedTextSnapshot?
    ) {
        self.analysis = analysis
        self.beforeSnapshot = beforeSnapshot
        self.afterSnapshot = afterSnapshot
    }
}

public struct FocusedTextAttributeDiagnostic: Encodable {
    public let name: String
    public let status: String
    public let valueType: String?
    public let value: String?

    enum CodingKeys: String, CodingKey {
        case name
        case status
        case valueType = "value_type"
        case value
    }
}

public struct FocusedTextDiagnostic: Encodable {
    public let focusedElementFound: Bool
    public let processIdentifier: pid_t?
    public let snapshotValue: String?
    public let snapshotStatus: String
    public let attributes: [FocusedTextAttributeDiagnostic]
    public let focusedApplicationFound: Bool
    public let focusedApplicationProcessIdentifier: pid_t?
    public let focusedApplicationAttributes: [FocusedTextAttributeDiagnostic]
    public let summary: String

    enum CodingKeys: String, CodingKey {
        case focusedElementFound = "focused_element_found"
        case processIdentifier = "process_identifier"
        case snapshotValue = "snapshot_value"
        case snapshotStatus = "snapshot_status"
        case attributes
        case focusedApplicationFound = "focused_application_found"
        case focusedApplicationProcessIdentifier = "focused_application_process_identifier"
        case focusedApplicationAttributes = "focused_application_attributes"
        case summary
    }
}

public enum FocusedTextDelta {
    public static func insertedText(before: FocusedTextSnapshot?, after: FocusedTextSnapshot?) -> String? {
        analyze(before: before, after: after).insertedText
    }

    public static func analyze(before: FocusedTextSnapshot?, after: FocusedTextSnapshot?) -> FocusedTextDeltaAnalysis {
        guard let before, let after else {
            if before == nil, after == nil {
                return FocusedTextDeltaAnalysis(insertedText: nil, reason: "missing_both_snapshots")
            }
            return FocusedTextDeltaAnalysis(
                insertedText: nil,
                reason: before == nil ? "missing_before_snapshot" : "missing_after_snapshot"
            )
        }
        if let beforePID = before.processIdentifier,
           let afterPID = after.processIdentifier,
           beforePID != afterPID {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "process_changed")
        }
        if let beforeRange = before.selectedRange,
           let afterRange = after.selectedRange {
            return analyze(
                before: before.value,
                after: after.value,
                beforeSelectedRange: beforeRange,
                afterSelectedRange: afterRange
            )
        }
        return analyze(before: before.value, after: after.value)
    }

    public static func firstCapturedAnalysis(
        before: FocusedTextSnapshot?,
        afterCandidates: [FocusedTextSnapshot?]
    ) -> FocusedTextDeltaAnalysis {
        firstCapturedMatch(beforeCandidates: [before], afterCandidates: afterCandidates).analysis
    }

    public static func firstCapturedMatch(
        beforeCandidates: [FocusedTextSnapshot?],
        afterCandidates: [FocusedTextSnapshot?]
    ) -> FocusedTextDeltaMatch {
        let beforeOptions = beforeCandidates.isEmpty ? [nil] : beforeCandidates
        let afterOptions = afterCandidates.isEmpty ? [nil] : afterCandidates
        var latestMatch = FocusedTextDeltaMatch(
            analysis: analyze(before: beforeOptions[0], after: afterOptions[0]),
            beforeSnapshot: beforeOptions[0],
            afterSnapshot: afterOptions[0]
        )
        if latestMatch.analysis.insertedText != nil {
            return latestMatch
        }
        for after in afterOptions {
            for before in beforeOptions {
                latestMatch = FocusedTextDeltaMatch(
                    analysis: analyze(before: before, after: after),
                    beforeSnapshot: before,
                    afterSnapshot: after
                )
                if latestMatch.analysis.insertedText != nil {
                    return latestMatch
                }
            }
        }
        return latestMatch
    }

    public static func insertedText(before: String, after: String) -> String? {
        analyze(before: before, after: after).insertedText
    }

    public static func analyze(before: String, after: String) -> FocusedTextDeltaAnalysis {
        guard before != after else {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "unchanged")
        }

        let beforeCharacters = Array(before)
        let afterCharacters = Array(after)
        var prefixCount = 0
        while prefixCount < beforeCharacters.count,
              prefixCount < afterCharacters.count,
              beforeCharacters[prefixCount] == afterCharacters[prefixCount] {
            prefixCount += 1
        }

        var beforeSuffixIndex = beforeCharacters.count - 1
        var afterSuffixIndex = afterCharacters.count - 1
        while beforeSuffixIndex >= prefixCount,
              afterSuffixIndex >= prefixCount,
              beforeCharacters[beforeSuffixIndex] == afterCharacters[afterSuffixIndex] {
            beforeSuffixIndex -= 1
            afterSuffixIndex -= 1
        }

        guard afterSuffixIndex >= prefixCount else {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "no_inserted_text")
        }

        let inserted = String(afterCharacters[prefixCount...afterSuffixIndex])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !inserted.isEmpty else {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "empty_inserted_text")
        }
        return FocusedTextDeltaAnalysis(insertedText: inserted, reason: "captured")
    }

    private static func analyze(
        before: String,
        after: String,
        beforeSelectedRange: NSRange,
        afterSelectedRange: NSRange
    ) -> FocusedTextDeltaAnalysis {
        guard before != after else {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "unchanged")
        }

        let beforeCharacters = Array(before)
        let afterCharacters = Array(after)
        guard isValidSelectionRange(beforeSelectedRange, characterCount: beforeCharacters.count),
              isValidSelectionRange(afterSelectedRange, characterCount: afterCharacters.count) else {
            return analyze(before: before, after: after)
        }

        let prefixEnd = beforeSelectedRange.location
        let suffixStart = beforeSelectedRange.location + beforeSelectedRange.length
        let insertedEnd = afterSelectedRange.location + afterSelectedRange.length
        guard insertedEnd >= prefixEnd else {
            return anchoredFallbackOrSelectionMismatch(before: before, after: after)
        }

        let beforePrefix = String(beforeCharacters[..<prefixEnd])
        let beforeSuffix = String(beforeCharacters[suffixStart...])
        guard String(afterCharacters.prefix(prefixEnd)) == beforePrefix else {
            return anchoredFallbackOrSelectionMismatch(before: before, after: after)
        }
        guard insertedEnd <= afterCharacters.count else {
            return anchoredFallbackOrSelectionMismatch(before: before, after: after)
        }
        guard String(afterCharacters[insertedEnd...]) == beforeSuffix else {
            return anchoredFallbackOrSelectionMismatch(before: before, after: after)
        }

        let inserted = String(afterCharacters[prefixEnd..<insertedEnd])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !inserted.isEmpty else {
            return FocusedTextDeltaAnalysis(insertedText: nil, reason: "empty_inserted_text")
        }
        return FocusedTextDeltaAnalysis(insertedText: inserted, reason: "captured")
    }

    private static func anchoredFallbackOrSelectionMismatch(
        before: String,
        after: String
    ) -> FocusedTextDeltaAnalysis {
        anchoredFallbackAnalysis(before: before, after: after)
            ?? FocusedTextDeltaAnalysis(insertedText: nil, reason: "selection_range_mismatch")
    }

    private static func anchoredFallbackAnalysis(before: String, after: String) -> FocusedTextDeltaAnalysis? {
        let beforeCharacters = Array(before)
        let afterCharacters = Array(after)
        var prefixCount = 0
        while prefixCount < beforeCharacters.count,
              prefixCount < afterCharacters.count,
              beforeCharacters[prefixCount] == afterCharacters[prefixCount] {
            prefixCount += 1
        }

        var beforeSuffixIndex = beforeCharacters.count - 1
        var afterSuffixIndex = afterCharacters.count - 1
        while beforeSuffixIndex >= prefixCount,
              afterSuffixIndex >= prefixCount,
              beforeCharacters[beforeSuffixIndex] == afterCharacters[afterSuffixIndex] {
            beforeSuffixIndex -= 1
            afterSuffixIndex -= 1
        }

        let suffixCount = beforeCharacters.count - beforeSuffixIndex - 1
        guard prefixCount > 0 || suffixCount > 0 else {
            return nil
        }
        guard afterSuffixIndex >= prefixCount else {
            return nil
        }

        let inserted = String(afterCharacters[prefixCount...afterSuffixIndex])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !inserted.isEmpty else {
            return nil
        }
        return FocusedTextDeltaAnalysis(insertedText: inserted, reason: "captured")
    }

    private static func isValidSelectionRange(_ range: NSRange, characterCount: Int) -> Bool {
        guard range.location >= 0, range.length >= 0, range.location <= characterCount else {
            return false
        }
        return range.length <= characterCount - range.location
    }
}

public final class FocusedTextCapture {
    public init() {}

    public func snapshot() -> FocusedTextSnapshot? {
        guard let focusedElement = Self.focusedElement() else {
            return nil
        }
        guard let value = Self.stringAttribute(kAXValueAttribute as String, from: focusedElement) else {
            return nil
        }

        var pid: pid_t = 0
        let pidResult = AXUIElementGetPid(focusedElement, &pid)
        return FocusedTextSnapshot(
            value: value,
            processIdentifier: pidResult == .success ? pid : nil,
            selectedRange: Self.rangeAttribute(kAXSelectedTextRangeAttribute as String, from: focusedElement)
        )
    }

    public func diagnosticSnapshot(maxValueCharacters: Int = 280) -> FocusedTextDiagnostic {
        let focusedApplication = Self.focusedApplication()
        var appPid: pid_t = 0
        let appPidResult = focusedApplication.map { AXUIElementGetPid($0, &appPid) } ?? .failure
        let appAttributes = focusedApplication.map { app in
            [
                kAXRoleAttribute as String,
                kAXTitleAttribute as String,
                kAXDescriptionAttribute as String,
                kAXFocusedWindowAttribute as String,
                kAXFocusedUIElementAttribute as String,
            ].map { name in
                Self.attributeDiagnostic(name, from: app, maxValueCharacters: maxValueCharacters)
            }
        } ?? []

        guard let focusedElement = Self.focusedElement() else {
            return FocusedTextDiagnostic(
                focusedElementFound: false,
                processIdentifier: nil,
                snapshotValue: nil,
                snapshotStatus: "missing_focused_element",
                attributes: [],
                focusedApplicationFound: focusedApplication != nil,
                focusedApplicationProcessIdentifier: appPidResult == .success ? appPid : nil,
                focusedApplicationAttributes: appAttributes,
                summary: "No focused accessibility element is available."
            )
        }

        var pid: pid_t = 0
        let pidResult = AXUIElementGetPid(focusedElement, &pid)
        let processIdentifier = pidResult == .success ? pid : nil
        let attributeNames = [
            kAXRoleAttribute as String,
            kAXSubroleAttribute as String,
            kAXTitleAttribute as String,
            kAXDescriptionAttribute as String,
            kAXValueAttribute as String,
            kAXSelectedTextAttribute as String,
            kAXPlaceholderValueAttribute as String,
            kAXSelectedTextRangeAttribute as String,
            kAXNumberOfCharactersAttribute as String,
            kAXChildrenAttribute as String,
        ]
        let attributes = attributeNames.map {
            Self.attributeDiagnostic($0, from: focusedElement, maxValueCharacters: maxValueCharacters)
        }
        let value = Self.stringAttribute(kAXValueAttribute as String, from: focusedElement)
        let status = value == nil ? "value_unavailable" : "ok"
        return FocusedTextDiagnostic(
            focusedElementFound: true,
            processIdentifier: processIdentifier,
            snapshotValue: value.map { Self.truncated($0, maxCharacters: maxValueCharacters) },
            snapshotStatus: status,
            attributes: attributes,
            focusedApplicationFound: focusedApplication != nil,
            focusedApplicationProcessIdentifier: appPidResult == .success ? appPid : nil,
            focusedApplicationAttributes: appAttributes,
            summary: "Focused element found; AXValue is \(status)."
        )
    }

    private static func focusedElement() -> AXUIElement? {
        let systemWide = AXUIElementCreateSystemWide()
        var focusedObject: CFTypeRef?
        if AXUIElementCopyAttributeValue(
            systemWide,
            kAXFocusedUIElementAttribute as CFString,
            &focusedObject
        ) == .success,
           let focusedObject,
           CFGetTypeID(focusedObject) == AXUIElementGetTypeID() {
            return (focusedObject as! AXUIElement)
        }

        guard let focusedApplication = focusedApplication() else {
            return nil
        }
        var appFocusedObject: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            focusedApplication,
            kAXFocusedUIElementAttribute as CFString,
            &appFocusedObject
        ) == .success,
              let appFocusedObject,
              CFGetTypeID(appFocusedObject) == AXUIElementGetTypeID() else {
            return nil
        }
        return (appFocusedObject as! AXUIElement)
    }

    private static func focusedApplication() -> AXUIElement? {
        let systemWide = AXUIElementCreateSystemWide()
        var focusedObject: CFTypeRef?
        if AXUIElementCopyAttributeValue(
            systemWide,
            kAXFocusedApplicationAttribute as CFString,
            &focusedObject
        ) == .success,
           let focusedObject,
           CFGetTypeID(focusedObject) == AXUIElementGetTypeID() {
            return (focusedObject as! AXUIElement)
        }

        guard let frontmostApplication = NSWorkspace.shared.frontmostApplication else {
            return nil
        }
        return AXUIElementCreateApplication(frontmostApplication.processIdentifier)
    }

    private static func stringAttribute(_ name: String, from element: AXUIElement) -> String? {
        var valueObject: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &valueObject) == .success,
              let valueObject else {
            return nil
        }
        return valueObject as? String
    }

    private static func rangeAttribute(_ name: String, from element: AXUIElement) -> NSRange? {
        var valueObject: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &valueObject) == .success,
              let valueObject,
              CFGetTypeID(valueObject) == AXValueGetTypeID() else {
            return nil
        }
        let axValue = valueObject as! AXValue
        guard AXValueGetType(axValue) == .cfRange else {
            return nil
        }
        var range = CFRange()
        guard AXValueGetValue(axValue, .cfRange, &range) else {
            return nil
        }
        return NSRange(location: range.location, length: range.length)
    }

    private static func attributeDiagnostic(
        _ name: String,
        from element: AXUIElement,
        maxValueCharacters: Int
    ) -> FocusedTextAttributeDiagnostic {
        var valueObject: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(element, name as CFString, &valueObject)
        guard result == .success, let valueObject else {
            return FocusedTextAttributeDiagnostic(
                name: name,
                status: String(describing: result),
                valueType: nil,
                value: nil
            )
        }
        let described = describe(valueObject, maxValueCharacters: maxValueCharacters)
        return FocusedTextAttributeDiagnostic(
            name: name,
            status: "success",
            valueType: described.valueType,
            value: described.value
        )
    }

    private static func describe(
        _ valueObject: CFTypeRef,
        maxValueCharacters: Int
    ) -> (valueType: String, value: String) {
        if let string = valueObject as? String {
            return ("String", truncated(string, maxCharacters: maxValueCharacters))
        }
        if let number = valueObject as? NSNumber {
            return ("NSNumber", number.stringValue)
        }
        if let array = valueObject as? [Any] {
            return ("Array", "count=\(array.count)")
        }
        if CFGetTypeID(valueObject) == AXUIElementGetTypeID() {
            return ("AXUIElement", "<AXUIElement>")
        }
        if CFGetTypeID(valueObject) == AXValueGetTypeID() {
            let axValue = valueObject as! AXValue
            switch AXValueGetType(axValue) {
            case .axError:
                var error = AXError.success
                if AXValueGetValue(axValue, .axError, &error) {
                    return ("AXValue.axError", String(describing: error))
                }
                return ("AXValue.axError", "<unreadable>")
            case .cfRange:
                var range = CFRange()
                if AXValueGetValue(axValue, .cfRange, &range) {
                    return ("AXValue.cfRange", "location=\(range.location), length=\(range.length)")
                }
                return ("AXValue.cfRange", "<unreadable>")
            case .cgPoint:
                var point = CGPoint.zero
                if AXValueGetValue(axValue, .cgPoint, &point) {
                    return ("AXValue.cgPoint", "x=\(point.x), y=\(point.y)")
                }
                return ("AXValue.cgPoint", "<unreadable>")
            case .cgSize:
                var size = CGSize.zero
                if AXValueGetValue(axValue, .cgSize, &size) {
                    return ("AXValue.cgSize", "width=\(size.width), height=\(size.height)")
                }
                return ("AXValue.cgSize", "<unreadable>")
            case .cgRect:
                var rect = CGRect.zero
                if AXValueGetValue(axValue, .cgRect, &rect) {
                    return ("AXValue.cgRect", "x=\(rect.origin.x), y=\(rect.origin.y), width=\(rect.width), height=\(rect.height)")
                }
                return ("AXValue.cgRect", "<unreadable>")
            case .illegal:
                return ("AXValue.illegal", "<illegal>")
            @unknown default:
                return ("AXValue.unknown", "<unknown>")
            }
        }
        return (String(describing: type(of: valueObject)), truncated(String(describing: valueObject), maxCharacters: maxValueCharacters))
    }

    private static func truncated(_ value: String, maxCharacters: Int) -> String {
        guard value.count > maxCharacters else {
            return value
        }
        let endIndex = value.index(value.startIndex, offsetBy: maxCharacters)
        return String(value[..<endIndex]) + "..."
    }
}
