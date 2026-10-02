// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CalBar",
    platforms: [.macOS(.v15)],
    targets: [
        .target(name: "CalBarCore"),
        .executableTarget(name: "CalBar", dependencies: ["CalBarCore"]),
        .executableTarget(name: "CalBarCoreChecks", dependencies: ["CalBarCore"], path: "Tests/CalBarCoreTests"),
    ]
)
