# SwitchType macOS App Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first SwiftPM macOS menu bar app source for hold-to-record local voice typing.

**Architecture:** The app is a SwiftPM executable that uses SwiftUI/AppKit for lifecycle and menu bar status, AVFoundation for recording, a CGEvent tap for the hold hotkey, a subprocess transcription service for `whisper.cpp`, deterministic post-processing, and NSPasteboard plus Cmd-V event injection for output.

**Tech Stack:** SwiftPM, Swift 5 language mode on Swift 6 compiler, SwiftUI, AppKit, AVFoundation, CoreGraphics, executable Swift checks.

---

## File Structure

- Create: `app/SwitchType/Package.swift`
- Create: `app/SwitchType/README.md`
- Create: `app/SwitchType/Sources/SwitchType/SwitchTypeApp.swift`
- Create: `app/SwitchType/Sources/SwitchType/AppDelegate.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/AppState.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/AudioRecorder.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/HotkeyController.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/TranscriptionService.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/PostProcessor.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCore/PasteboardTyper.swift`
- Create: `app/SwitchType/Sources/SwitchTypeCoreCheck/main.swift`
- Modify: `.gitignore`
- Modify: `README.md`

## Tasks

- [ ] Add SwiftPM package metadata with a `SwitchType` executable target and `SwitchTypeCoreCheck` executable target.
- [ ] Add `AppState` to centralize visible menu bar states.
- [ ] Add `PostProcessor` and executable check coverage for replacements and ASCII technical-term spacing.
- [ ] Add `AudioRecorder` with AVFoundation recording to local temporary `.m4a` files.
- [ ] Add `HotkeyController` using a CGEvent tap for `Option + Space` key-down and key-up.
- [ ] Add `TranscriptionService` that invokes a local whisper.cpp-compatible command using environment variables for binary/model paths.
- [ ] Add `PasteboardTyper` that writes final text to `NSPasteboard` and sends Cmd-V.
- [ ] Add `AppDelegate` and SwiftUI entry point to wire menu bar UI, recording, transcription, post-processing, and paste.
- [ ] Add app README with build, run, permissions, and environment variable setup.
- [ ] Run `swift build --package-path app/SwitchType`.
- [ ] Run `app/SwitchType/.build/debug/SwitchTypeCoreCheck`.
- [ ] Commit the app phase.

## Verification

- Swift package builds.
- Swift package executable checks pass.
- CLI benchmark tests still pass.
- README documents that the SwiftPM executable is a development build, that `SwitchTypeCoreCheck` replaces XCTest in the current Command Line Tools environment, and that full `.app` packaging/manual GUI verification remains for the release phase.
