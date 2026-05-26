import AppKit
import CoreGraphics
import Foundation

public enum PasteboardTyperError: Error, LocalizedError {
    case pasteboardWriteFailed
    case eventCreationFailed

    public var errorDescription: String? {
        switch self {
        case .pasteboardWriteFailed:
            return "Could not write text to the clipboard."
        case .eventCreationFailed:
            return "Could not create paste keyboard events."
        }
    }
}

public final class PasteboardTyper {
    public init() {}

    public func paste(_ text: String) throws {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        guard pasteboard.setString(text, forType: .string) else {
            throw PasteboardTyperError.pasteboardWriteFailed
        }

        guard let source = CGEventSource(stateID: .hidSystemState),
              let keyDown = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: true),
              let keyUp = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: false) else {
            throw PasteboardTyperError.eventCreationFailed
        }

        keyDown.flags = .maskCommand
        keyUp.flags = .maskCommand
        keyDown.post(tap: .cghidEventTap)
        keyUp.post(tap: .cghidEventTap)
    }
}

