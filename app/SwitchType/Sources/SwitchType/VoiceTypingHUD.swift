import AppKit
import SwitchTypeCore

final class VoiceTypingHUD {
    private let panel: NSPanel
    private let dotView = NSView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let detailLabel = NSTextField(labelWithString: "")
    private var pulseTimer: Timer?
    private var hideWorkItem: DispatchWorkItem?
    private var pulseVisible = true

    init() {
        panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 320, height: 78),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        configureContent()
    }

    func show(_ feedback: AppFeedback) {
        hideWorkItem?.cancel()
        titleLabel.stringValue = feedback.title
        detailLabel.stringValue = feedback.detail ?? ""
        detailLabel.isHidden = feedback.detail == nil
        dotView.layer?.backgroundColor = feedback.isError
            ? NSColor.systemRed.cgColor
            : NSColor.systemBlue.cgColor
        positionPanel()
        panel.orderFrontRegardless()
        feedback.pulses ? startPulse() : stopPulse()
        if let autoHideSeconds = feedback.autoHideSeconds {
            let workItem = DispatchWorkItem { [weak self] in
                self?.hide()
            }
            hideWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + autoHideSeconds, execute: workItem)
        }
    }

    func hide() {
        hideWorkItem?.cancel()
        hideWorkItem = nil
        stopPulse()
        panel.orderOut(nil)
    }

    private func configureContent() {
        let background = NSVisualEffectView()
        background.material = .hudWindow
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 16
        background.layer?.masksToBounds = true

        dotView.translatesAutoresizingMaskIntoConstraints = false
        dotView.wantsLayer = true
        dotView.layer?.cornerRadius = 7
        dotView.layer?.backgroundColor = NSColor.systemBlue.cgColor

        titleLabel.font = .systemFont(ofSize: 16, weight: .semibold)
        titleLabel.textColor = .white
        detailLabel.font = .systemFont(ofSize: 12, weight: .regular)
        detailLabel.textColor = .secondaryLabelColor

        let textStack = NSStackView(views: [titleLabel, detailLabel])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 3

        let stack = NSStackView(views: [dotView, textStack])
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 12

        background.addSubview(stack)
        panel.contentView = background

        NSLayoutConstraint.activate([
            dotView.widthAnchor.constraint(equalToConstant: 14),
            dotView.heightAnchor.constraint(equalToConstant: 14),
            stack.leadingAnchor.constraint(equalTo: background.leadingAnchor, constant: 22),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: background.trailingAnchor, constant: -22),
            stack.centerYAnchor.constraint(equalTo: background.centerYAnchor)
        ])
    }

    private func positionPanel() {
        guard let frame = NSScreen.main?.visibleFrame else {
            return
        }
        let width: CGFloat = 320
        let height: CGFloat = 78
        let origin = NSPoint(
            x: frame.midX - width / 2,
            y: frame.maxY - height - 72
        )
        panel.setFrame(NSRect(origin: origin, size: NSSize(width: width, height: height)), display: true)
    }

    private func startPulse() {
        stopPulse()
        pulseVisible = true
        dotView.alphaValue = 1.0
        pulseTimer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: true) { [weak self] _ in
            guard let self else {
                return
            }
            pulseVisible.toggle()
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.22
                self.dotView.animator().alphaValue = self.pulseVisible ? 1.0 : 0.35
            }
        }
    }

    private func stopPulse() {
        pulseTimer?.invalidate()
        pulseTimer = nil
        dotView.alphaValue = 1.0
    }
}
