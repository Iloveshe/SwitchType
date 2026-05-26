import CoreGraphics
import Foundation

public enum HotkeyControllerError: Error, LocalizedError {
    case eventTapUnavailable

    public var errorDescription: String? {
        switch self {
        case .eventTapUnavailable:
            return "Could not create global hotkey event tap. Enable Accessibility permission."
        }
    }
}

public enum HotkeyEventAction: String {
    case ignore
    case consumeOnly
    case startRecording
    case finishRecording

    public var consumesEvent: Bool {
        self != .ignore
    }

    public func shouldConsumeEvent(consumeEvents: Bool) -> Bool {
        consumeEvents && consumesEvent
    }
}

public enum HotkeyEventSource: String {
    case eventTap
    case modifierPoll
}

public struct HotkeyEventDiagnostic {
    public let source: HotkeyEventSource
    public let typeName: String
    public let keyCode: CGKeyCode
    public let modifiers: String
    public let action: HotkeyEventAction

    public init(
        source: HotkeyEventSource = .eventTap,
        type: CGEventType,
        keyCode: CGKeyCode,
        flags: CGEventFlags,
        action: HotkeyEventAction
    ) {
        self.source = source
        self.typeName = Self.name(for: type)
        self.keyCode = keyCode
        self.modifiers = HotkeyConfiguration.modifierString(from: flags)
        self.action = action
    }

    public var summary: String {
        "source=\(source.rawValue), type=\(typeName), keyCode=\(keyCode), modifiers=\(modifiers), action=\(action.rawValue)"
    }

    private static func name(for type: CGEventType) -> String {
        switch type {
        case .keyDown:
            return "keyDown"
        case .keyUp:
            return "keyUp"
        case .flagsChanged:
            return "flagsChanged"
        default:
            return "event-\(type.rawValue)"
        }
    }
}

public struct HotkeyConfiguration {
    public static let defaultKeyCode: CGKeyCode = 58
    public static let defaultRequiredFlags: CGEventFlags = [.maskAlternate]
    public static let appDefaultKeyCode: CGKeyCode = 59
    public static let appDefaultRequiredFlags: CGEventFlags = [.maskControl, .maskShift]

    public let keyCode: CGKeyCode
    public let requiredFlags: CGEventFlags

    public init(
        keyCode: CGKeyCode = Self.defaultKeyCode,
        requiredFlags: CGEventFlags = Self.defaultRequiredFlags
    ) {
        self.keyCode = keyCode
        self.requiredFlags = requiredFlags
    }

    public static func from(environment: [String: String]) -> HotkeyConfiguration {
        from(
            environment: environment,
            fallbackKeyCode: defaultKeyCode,
            fallbackRequiredFlags: defaultRequiredFlags
        )
    }

    public static func fromAppEnvironment(_ environment: [String: String]) -> HotkeyConfiguration {
        from(
            environment: environment,
            fallbackKeyCode: appDefaultKeyCode,
            fallbackRequiredFlags: appDefaultRequiredFlags
        )
    }

    private static func from(
        environment: [String: String],
        fallbackKeyCode: CGKeyCode,
        fallbackRequiredFlags: CGEventFlags
    ) -> HotkeyConfiguration {
        let keyCode = keyCodeValue(environment["SWITCHTYPE_HOTKEY_KEY_CODE"]) ?? fallbackKeyCode
        let requiredFlags = modifierFlags(environment["SWITCHTYPE_HOTKEY_MODIFIERS"]) ?? fallbackRequiredFlags
        return HotkeyConfiguration(keyCode: keyCode, requiredFlags: requiredFlags)
    }

    public static func modifierNames(from flags: CGEventFlags) -> [String] {
        let knownModifiers: [(name: String, flag: CGEventFlags)] = [
            ("control", .maskControl),
            ("option", .maskAlternate),
            ("shift", .maskShift),
            ("command", .maskCommand)
        ]
        return knownModifiers.compactMap { modifier in
            flags.contains(modifier.flag) ? modifier.name : nil
        }
    }

    public static func modifierString(from flags: CGEventFlags) -> String {
        let names = modifierNames(from: flags)
        return names.isEmpty ? "none" : names.joined(separator: ",")
    }

    public var displayName: String {
        let modifiers = Self.modifierNames(from: requiredFlags).map { name in
            name.prefix(1).uppercased() + name.dropFirst()
        }
        if Self.isModifierOnly(keyCode: keyCode, requiredFlags: requiredFlags) {
            return modifiers.joined(separator: "+")
        }
        let keyName = Self.keyDisplayName(for: keyCode)
        return (modifiers + [keyName]).joined(separator: "+")
    }

    private static func keyCodeValue(_ value: String?) -> CGKeyCode? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              let integer = UInt16(value) else {
            return nil
        }
        return CGKeyCode(integer)
    }

    private static func modifierFlags(_ value: String?) -> CGEventFlags? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else {
            return nil
        }
        var flags: CGEventFlags = []
        for rawToken in value.split(separator: ",") {
            let token = rawToken.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            switch token {
            case "option", "alt", "alternate":
                flags.insert(.maskAlternate)
            case "control", "ctrl":
                flags.insert(.maskControl)
            case "shift":
                flags.insert(.maskShift)
            case "command", "cmd", "meta":
                flags.insert(.maskCommand)
            case "none":
                continue
            default:
                return nil
            }
        }
        return flags
    }

    static func modifierFlag(for keyCode: CGKeyCode) -> CGEventFlags? {
        switch Int(keyCode) {
        case 56, 60:
            return .maskShift
        case 58, 61:
            return .maskAlternate
        case 59, 62:
            return .maskControl
        case 54, 55:
            return .maskCommand
        default:
            return nil
        }
    }

    private static func isModifierOnly(keyCode: CGKeyCode, requiredFlags: CGEventFlags) -> Bool {
        guard let configuredModifier = modifierFlag(for: keyCode) else {
            return false
        }
        return requiredFlags.contains(configuredModifier)
    }

    private static func keyDisplayName(for keyCode: CGKeyCode) -> String {
        switch Int(keyCode) {
        case 36:
            return "Return"
        case 49:
            return "Space"
        case 53:
            return "Escape"
        default:
            return "Key \(Int(keyCode))"
        }
    }
}

public struct HotkeyEventState {
    private var isPressed = false
    private let configuration: HotkeyConfiguration

    public init(configuration: HotkeyConfiguration = HotkeyConfiguration()) {
        self.configuration = configuration
    }

    public mutating func handle(type: CGEventType, keyCode: CGKeyCode, flags: CGEventFlags) -> HotkeyEventAction {
        guard matchesConfiguredKey(keyCode, type: type, flags: flags) else {
            return .ignore
        }

        if type == .flagsChanged {
            let requiredModifiersArePressed = flags.intersection(configuration.requiredFlags) == configuration.requiredFlags
            if requiredModifiersArePressed {
                if isPressed {
                    return .consumeOnly
                }
                isPressed = true
                return .startRecording
            }
            if isPressed {
                isPressed = false
                return .finishRecording
            }
            return .ignore
        }

        if type == .keyDown {
            if isPressed {
                return .consumeOnly
            }
            guard flags.intersection(configuration.requiredFlags) == configuration.requiredFlags else {
                return .ignore
            }
            isPressed = true
            return .startRecording
        }

        if type == .keyUp, isPressed {
            isPressed = false
            return .finishRecording
        }

        return .ignore
    }

    public mutating func handlePolledFlags(_ flags: CGEventFlags) -> HotkeyEventAction {
        guard isModifierOnlyConfiguration else {
            return .ignore
        }
        return handle(type: .flagsChanged, keyCode: configuration.keyCode, flags: flags)
    }

    public mutating func reset() {
        isPressed = false
    }

    var isModifierOnlyConfiguration: Bool {
        guard let configuredModifier = HotkeyConfiguration.modifierFlag(for: configuration.keyCode) else {
            return false
        }
        return configuration.requiredFlags.contains(configuredModifier)
    }

    private func matchesConfiguredKey(_ keyCode: CGKeyCode, type: CGEventType, flags: CGEventFlags) -> Bool {
        if keyCode == configuration.keyCode {
            return true
        }

        if type == .flagsChanged,
           keyCode == 0,
           isModifierOnlyConfiguration {
            let requiredModifiersArePressed = flags.intersection(configuration.requiredFlags) == configuration.requiredFlags
            return isPressed || requiredModifiersArePressed
        }

        guard isModifierOnlyConfiguration,
              let candidateModifier = HotkeyConfiguration.modifierFlag(for: keyCode),
              configuration.requiredFlags.contains(candidateModifier) else {
            return false
        }
        return true
    }
}

public final class HotkeyController {
    public var onRecordingRequested: (() -> Void)?
    public var onRecordingFinished: (() -> Void)?
    public var onEventObserved: ((HotkeyEventDiagnostic) -> Void)?

    private let consumeEvents: Bool
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var hotkeyState = HotkeyEventState()

    public init(
        consumeEvents: Bool = true,
        configuration: HotkeyConfiguration = HotkeyConfiguration()
    ) {
        self.consumeEvents = consumeEvents
        self.hotkeyState = HotkeyEventState(configuration: configuration)
    }

    public func start() throws {
        guard eventTap == nil else {
            return
        }

        let mask = (1 << CGEventType.keyDown.rawValue)
            | (1 << CGEventType.keyUp.rawValue)
            | (1 << CGEventType.flagsChanged.rawValue)
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: consumeEvents ? .defaultTap : .listenOnly,
            eventsOfInterest: CGEventMask(mask),
            callback: hotkeyCallback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ) else {
            throw HotkeyControllerError.eventTapUnavailable
        }

        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            throw HotkeyControllerError.eventTapUnavailable
        }

        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        eventTap = tap
        runLoopSource = source
    }

    public func stop() {
        if let eventTap {
            CGEvent.tapEnable(tap: eventTap, enable: false)
        }
        if let runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }
        self.eventTap = nil
        self.runLoopSource = nil
        hotkeyState.reset()
    }

    fileprivate func handle(type: CGEventType, event: CGEvent) -> Bool {
        let keyCode = CGKeyCode(event.getIntegerValueField(.keyboardEventKeycode))
        let action = hotkeyState.handle(type: type, keyCode: keyCode, flags: event.flags)
        onEventObserved?(HotkeyEventDiagnostic(type: type, keyCode: keyCode, flags: event.flags, action: action))
        handle(action: action)
        return action.shouldConsumeEvent(consumeEvents: consumeEvents)
    }

    private func handle(action: HotkeyEventAction) {
        switch action {
        case .startRecording:
            onRecordingRequested?()
        case .finishRecording:
            onRecordingFinished?()
        case .consumeOnly, .ignore:
            break
        }
    }
}

private let hotkeyCallback: CGEventTapCallBack = { _, type, event, userInfo in
    guard let userInfo else {
        return Unmanaged.passUnretained(event)
    }
    let controller = Unmanaged<HotkeyController>.fromOpaque(userInfo).takeUnretainedValue()
    if controller.handle(type: type, event: event) {
        return nil
    }
    return Unmanaged.passUnretained(event)
}
