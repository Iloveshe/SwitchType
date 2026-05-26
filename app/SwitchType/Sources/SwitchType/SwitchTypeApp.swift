import SwiftUI

@main
struct SwitchTypeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            Text("SwitchType runs from the menu bar.")
                .padding()
        }
    }
}

