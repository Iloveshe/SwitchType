import CoreGraphics
import Foundation
import SwitchTypeCore

final class HotkeyProbe {
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var finished = false

    func start(timeoutSeconds: TimeInterval) throws {
        let mask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.flagsChanged.rawValue)
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: CGEventMask(mask),
            callback: hotkeyProbeCallback,
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

        if timeoutSeconds > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + timeoutSeconds) { [weak self] in
                self?.timeout(after: timeoutSeconds)
            }
        }
    }

    fileprivate func handle(type: CGEventType, event: CGEvent) {
        let keyCode = CGKeyCode(event.getIntegerValueField(.keyboardEventKeycode))
        if type == .keyDown {
            guard Self.modifierFlag(for: keyCode) == nil else {
                return
            }
            report(keyCode: keyCode, modifiers: HotkeyConfiguration.modifierString(from: event.flags))
            return
        }

        if type == .flagsChanged,
           let modifierFlag = Self.modifierFlag(for: keyCode),
           event.flags.contains(modifierFlag) {
            report(keyCode: keyCode, modifiers: HotkeyConfiguration.modifierString(from: event.flags))
            return
        }
    }

    private func report(keyCode: CGKeyCode, modifiers: String) {
        guard !finished else {
            return
        }
        finished = true
        print("")
        print("Detected hotkey:")
        print("SWITCHTYPE_HOTKEY_KEY_CODE=\(keyCode)")
        print("SWITCHTYPE_HOTKEY_MODIFIERS=\"\(modifiers)\"")
        print("")
        print("Example:")
        print("SWITCHTYPE_HOTKEY_KEY_CODE=\(keyCode) SWITCHTYPE_HOTKEY_MODIFIERS=\"\(modifiers)\" make doubao-shadow-start-auto")
        stop()
        CFRunLoopStop(CFRunLoopGetMain())
    }

    private func timeout(after seconds: TimeInterval) {
        guard !finished else {
            return
        }
        finished = true
        print("")
        print("No hotkey detected within \(Self.format(seconds: seconds)) seconds.")
        print("Run this probe again while pressing the Doubao voice shortcut.")
        stop()
        CFRunLoopStop(CFRunLoopGetMain())
    }

    private func stop() {
        if let eventTap {
            CGEvent.tapEnable(tap: eventTap, enable: false)
        }
        if let runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }
        eventTap = nil
        runLoopSource = nil
    }

    private static func modifierFlag(for keyCode: CGKeyCode) -> CGEventFlags? {
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

    private static func format(seconds: TimeInterval) -> String {
        if seconds.rounded() == seconds {
            return String(Int(seconds))
        }
        return String(format: "%.1f", seconds)
    }
}

private let hotkeyProbeCallback: CGEventTapCallBack = { _, type, event, userInfo in
    guard let userInfo else {
        return Unmanaged.passUnretained(event)
    }
    let probe = Unmanaged<HotkeyProbe>.fromOpaque(userInfo).takeUnretainedValue()
    probe.handle(type: type, event: event)
    return Unmanaged.passUnretained(event)
}

enum ProbeArgumentError: LocalizedError {
    case missingValue(String)
    case invalidTimeout(String)
    case unknownArgument(String)

    var errorDescription: String? {
        switch self {
        case let .missingValue(argument):
            return "\(argument) requires a value"
        case let .invalidTimeout(value):
            return "Invalid --timeout-seconds value: \(value)"
        case let .unknownArgument(argument):
            return "Unknown argument: \(argument)"
        }
    }
}

struct ProbeOptions {
    var timeoutSeconds: TimeInterval = 0
}

func parseOptions(arguments: [String]) throws -> ProbeOptions {
    var options = ProbeOptions()
    var index = 0
    while index < arguments.count {
        let argument = arguments[index]
        switch argument {
        case "--timeout-seconds":
            let valueIndex = index + 1
            guard valueIndex < arguments.count else {
                throw ProbeArgumentError.missingValue(argument)
            }
            let value = arguments[valueIndex]
            guard let seconds = TimeInterval(value), seconds >= 0 else {
                throw ProbeArgumentError.invalidTimeout(value)
            }
            options.timeoutSeconds = seconds
            index += 2
        case "--help", "-h":
            print("Usage: SwitchTypeHotkeyProbe [--timeout-seconds seconds]")
            exit(0)
        default:
            throw ProbeArgumentError.unknownArgument(argument)
        }
    }
    return options
}

let probe = HotkeyProbe()

do {
    let options = try parseOptions(arguments: Array(CommandLine.arguments.dropFirst()))
    print("Press the Doubao voice shortcut once.")
    print("This probe uses a listen-only event tap and does not consume the key event.")
    if options.timeoutSeconds > 0 {
        print("Timeout: \(Int(options.timeoutSeconds)) seconds.")
    } else {
        print("Press Control-C to cancel.")
    }
    try probe.start(timeoutSeconds: options.timeoutSeconds)
    CFRunLoopRun()
} catch {
    FileHandle.standardError.write(Data("Hotkey probe failed: \(error.localizedDescription)\n".utf8))
    exit(2)
}
