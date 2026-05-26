// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SwitchType",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "SwitchType", targets: ["SwitchType"]),
        .executable(name: "SwitchTypeASRSmoke", targets: ["SwitchTypeASRSmoke"]),
        .executable(name: "SwitchTypeDoubaoShadow", targets: ["SwitchTypeDoubaoShadow"]),
        .executable(name: "SwitchTypeDoctor", targets: ["SwitchTypeDoctor"]),
        .executable(name: "SwitchTypeHotkeyProbe", targets: ["SwitchTypeHotkeyProbe"]),
        .executable(name: "SwitchTypeCoreCheck", targets: ["SwitchTypeCoreCheck"])
    ],
    targets: [
        .target(
            name: "SwitchTypeCore",
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchType",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchTypeASRSmoke",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchTypeDoubaoShadow",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchTypeDoctor",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchTypeHotkeyProbe",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        ),
        .executableTarget(
            name: "SwitchTypeCoreCheck",
            dependencies: ["SwitchTypeCore"],
            swiftSettings: [
                .swiftLanguageMode(.v5)
            ]
        )
    ]
)
