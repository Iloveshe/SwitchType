import AppKit
import SwitchTypeCore

final class HotwordEditorWindowController: NSWindowController {
    private let protectedTermsTextView = NSTextView()
    private let replacementsTextView = NSTextView()
    private let statusLabel = NSTextField(labelWithString: "")
    private let onSave: (HotwordConfig) -> Void
    private let onOpenJSON: () -> Void

    init(
        config: HotwordConfig,
        onSave: @escaping (HotwordConfig) -> Void,
        onOpenJSON: @escaping () -> Void
    ) {
        self.onSave = onSave
        self.onOpenJSON = onOpenJSON

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 680, height: 520),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Edit Hotwords"
        window.isReleasedWhenClosed = false
        super.init(window: window)

        protectedTermsTextView.string = config.editorProtectedTermsText
        replacementsTextView.string = config.editorReplacementsText
        window.contentView = makeContentView()
        window.center()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func saveAndReload() {
        do {
            let config = try HotwordConfig.fromEditorText(
                protectedTermsText: protectedTermsTextView.string,
                replacementsText: replacementsTextView.string
            )
            let url = try HotwordConfig.ensurePersonalConfig()
            try config.write(to: url)
            statusLabel.textColor = .secondaryLabelColor
            statusLabel.stringValue = "Saved and reloaded."
            onSave(config)
        } catch {
            statusLabel.textColor = .systemRed
            statusLabel.stringValue = error.localizedDescription
            NSSound.beep()
        }
    }

    @objc private func openJSON() {
        onOpenJSON()
    }

    private func makeContentView() -> NSView {
        let contentView = NSView()
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 18, left: 18, bottom: 18, right: 18)
        stack.translatesAutoresizingMaskIntoConstraints = false

        let editors = NSStackView()
        editors.orientation = .horizontal
        editors.alignment = .top
        editors.distribution = .fillEqually
        editors.spacing = 12
        editors.translatesAutoresizingMaskIntoConstraints = false
        editors.addArrangedSubview(makeEditorColumn(
            title: "Hotwords",
            textView: protectedTermsTextView
        ))
        editors.addArrangedSubview(makeEditorColumn(
            title: "Corrections (wrong => correct)",
            textView: replacementsTextView
        ))

        statusLabel.textColor = .secondaryLabelColor
        statusLabel.lineBreakMode = .byTruncatingTail
        statusLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let buttonRow = NSStackView()
        buttonRow.orientation = .horizontal
        buttonRow.alignment = .centerY
        buttonRow.spacing = 10

        let openButton = NSButton(title: "Open JSON", target: self, action: #selector(openJSON))
        openButton.bezelStyle = .rounded
        let saveButton = NSButton(title: "Save & Reload", target: self, action: #selector(saveAndReload))
        saveButton.bezelStyle = .rounded
        saveButton.keyEquivalent = "\r"

        buttonRow.addArrangedSubview(openButton)
        buttonRow.addArrangedSubview(NSView())
        buttonRow.addArrangedSubview(saveButton)
        buttonRow.setHuggingPriority(.defaultLow, for: .horizontal)

        stack.addArrangedSubview(editors)
        stack.addArrangedSubview(statusLabel)
        stack.addArrangedSubview(buttonRow)
        contentView.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            stack.topAnchor.constraint(equalTo: contentView.topAnchor),
            stack.bottomAnchor.constraint(equalTo: contentView.bottomAnchor),
            editors.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -36),
            editors.heightAnchor.constraint(greaterThanOrEqualToConstant: 370),
            buttonRow.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -36),
            statusLabel.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -36)
        ])
        return contentView
    }

    private func makeEditorColumn(title: String, textView: NSTextView) -> NSView {
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 13, weight: .semibold)

        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.borderType = .bezelBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false

        configureTextView(textView)
        scrollView.documentView = textView

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(label)
        stack.addArrangedSubview(scrollView)

        NSLayoutConstraint.activate([
            scrollView.widthAnchor.constraint(equalTo: stack.widthAnchor),
            scrollView.heightAnchor.constraint(greaterThanOrEqualToConstant: 340)
        ])
        return stack
    }

    private func configureTextView(_ textView: NSTextView) {
        textView.isRichText = false
        textView.allowsUndo = true
        textView.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.isHorizontallyResizable = false
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: 0,
            height: CGFloat.greatestFiniteMagnitude
        )
    }
}
