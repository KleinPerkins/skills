import ShadowSyncCore
import Foundation

enum LifecycleMain {
    private enum InvocationAdmission {
        case installed
        case source(SourceAttestation)
    }

    private static let reconcileMode = "--lifecycle-reconcile"
    private static let repairMode = "--lifecycle-repair"
    private static let removeMode = "--lifecycle-remove"
    private static let doctorMode = "--lifecycle-doctor"

    static func dispatch(
        arguments: [String],
        executablePath: String
    ) -> Int32? {
        guard arguments.count >= 2,
              [reconcileMode, repairMode, removeMode, doctorMode].contains(arguments[1]) else {
            return nil
        }
        #if SHADOW_SYNC_TESTING
        FileHandle.standardError.write(
            Data("Testing bundles cannot mutate production lifecycle state.\n".utf8)
        )
        return 2
        #else
        do {
            let paths = try InstallationPaths.production()
            let admission = try invocationAdmission(
                arguments: arguments,
                installedExecutable: isCurrentInstalledExecutable(
                    executablePath: executablePath,
                    paths: paths
                )
            )
            let sourceAttestation: SourceAttestation?
            switch admission {
            case .installed:
                sourceAttestation = nil
            case let .source(attestation):
                sourceAttestation = attestation
                try sourceAttestation?.verify(
                    bundlePath: Bundle.main.bundleURL.path
                )
            }
            let lifecycle = InstallationLifecycle(
                paths: paths,
                launchAgent: SystemLaunchAgentController(),
                host: SystemInstalledHostController(),
                fault: { stage in
                    if stage == "before-promotion" {
                        try sourceAttestation?.verify(
                            bundlePath: Bundle.main.bundleURL.path
                        )
                    }
                }
            )
            switch arguments[1] {
            case reconcileMode, repairMode:
                let report = try lifecycle.install(
                    sourceBundle: Bundle.main.bundleURL.path,
                    intent: arguments[1] == repairMode ? .repair : .reconcile
                )
                printReport("install", report)
            case removeMode:
                try lifecycle.uninstall()
                print(
                    "ShadowSync verified removal OK; latest.log, canonical-root authority, and completed recovery artifacts were preserved when present."
                )
            case doctorMode:
                printReport("doctor", try lifecycle.doctor())
            default:
                return nil
            }
            return 0
        } catch {
            let message = Redactor.sanitize(String(describing: error))
            FileHandle.standardError.write(
                Data("ShadowSync lifecycle failed: \(message)\n".utf8)
            )
            return 1
        }
        #endif
    }

    private static func invocationAdmission(
        arguments: [String],
        installedExecutable: Bool
    ) throws -> InvocationAdmission {
        guard arguments.count >= 2 else {
            throw InstallationLifecycleError.unverifiedInstalledState
        }
        switch arguments[1] {
        case doctorMode:
            guard arguments.count == 2, installedExecutable else {
                throw InstallationLifecycleError.unverifiedInstalledState
            }
            return .installed
        case removeMode:
            if arguments.count == 2 {
                guard installedExecutable else {
                    throw InstallationLifecycleError.unverifiedInstalledState
                }
                return .installed
            }
            return .source(try SourceAttestation(arguments: arguments))
        case reconcileMode, repairMode:
            return .source(try SourceAttestation(arguments: arguments))
        default:
            throw InstallationLifecycleError.unverifiedInstalledState
        }
    }

    #if SHADOW_SYNC_TESTING
    static func testingAdmissionMatrix() -> Bool {
        func sourceArguments(_ mode: String) -> [String] {
            [
                "ShadowSync", mode,
                "--source-installer", "/private/tmp/source/install.sh",
                "--source-revision", String(repeating: "a", count: 40),
                "--source-input-sha256", String(repeating: "b", count: 64),
                "--metadata-contract-sha256", String(repeating: "c", count: 64),
            ]
        }
        func kind(
            _ arguments: [String],
            installed: Bool
        ) -> String? {
            guard let admission = try? invocationAdmission(
                arguments: arguments,
                installedExecutable: installed
            ) else {
                return nil
            }
            switch admission {
            case .installed: return "installed"
            case .source: return "source"
            }
        }
        return kind(["ShadowSync", doctorMode], installed: true) == "installed"
            && kind(["ShadowSync", doctorMode], installed: false) == nil
            && kind(["ShadowSync", removeMode], installed: true) == "installed"
            && kind(["ShadowSync", removeMode], installed: false) == nil
            && kind(sourceArguments(removeMode), installed: false) == "source"
            && kind(sourceArguments(reconcileMode), installed: false) == "source"
            && kind(sourceArguments(repairMode), installed: false) == "source"
            && kind(sourceArguments(doctorMode), installed: false) == nil
            && kind(["ShadowSync", reconcileMode], installed: true) == nil
            && kind(
                Array(sourceArguments(repairMode).dropLast()),
                installed: false
            ) == nil
    }
    #endif

    #if !SHADOW_SYNC_TESTING
    private static func isCurrentInstalledExecutable(
        executablePath: String,
        paths: InstallationPaths
    ) -> Bool {
        let expected = paths.app + "/Contents/MacOS/ShadowSync"
        guard let identity = try? ProcessIdentity.capture(
            processID: getpid(),
            generation: RunIdentity.make(),
            expectedExecutablePath: expected
        ) else {
            return false
        }
        return identity.userID == geteuid()
            && identity.isCurrent(
                expectedGeneration: identity.generation,
                requireGroupLeader: false
            )
            && URL(fileURLWithPath: executablePath)
                .resolvingSymlinksInPath().path
                == URL(fileURLWithPath: expected)
                    .resolvingSymlinksInPath().path
    }
    #endif

    private static func printReport(
        _ action: String,
        _ report: InstallationDoctorReport
    ) {
        print(
            "ShadowSync \(action) OK "
                + "version=\(report.release.version) "
                + "build=\(report.release.buildNumber) "
                + "source=\(report.release.sourceRevision) "
                + "source-sha256=\(report.release.sourceInputSHA256) "
                + "metadata-contract-sha256=\(report.release.metadataContractSHA256) "
                + "bundle-sha256=\(report.bundleSHA256) "
                + "launcher-loaded=\(report.launcherLoaded) "
                + "launcher-running=\(report.launcherRunning)"
        )
    }
}

private struct SourceAttestation: Sendable {
    let installer: String
    let revision: String
    let sourceInputSHA256: String
    let metadataContractSHA256: String

    init(arguments: [String]) throws {
        guard arguments.count == 10,
              arguments[2] == "--source-installer",
              arguments[4] == "--source-revision",
              arguments[6] == "--source-input-sha256",
              arguments[8] == "--metadata-contract-sha256" else {
            throw InstallationLifecycleError.unverifiedInstalledState
        }
        installer = arguments[3]
        revision = arguments[5]
        sourceInputSHA256 = arguments[7]
        metadataContractSHA256 = arguments[9]
    }

    func verify(bundlePath: String) throws {
        let release = try ReleaseIdentity.load(bundlePath: bundlePath)
        try release.validate(requireProduction: true)
        guard release.sourceRevision == revision,
              release.sourceInputSHA256 == sourceInputSHA256,
              release.metadataContractSHA256 == metadataContractSHA256 else {
            throw InstallationLifecycleError.unverifiedInstalledState
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [installer, "--source-identity"]
        process.environment = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_ATTR_NOSYSTEM": "1",
        ]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        let reader = pipe.fileHandleForReading
        let writer = pipe.fileHandleForWriting
        defer {
            try? reader.close()
            try? writer.close()
        }
        try process.run()
        guard OwnedProcessReaper.wait(for: process, timeout: 10) else {
            throw InstallationLifecycleError.unverifiedInstalledState
        }
        let output = String(
            decoding: reader.readDataToEndOfFile(),
            as: UTF8.self
        )
        guard process.terminationStatus == 0,
              output.contains("source-revision=\(revision)\n"),
              output.contains("source-input-sha256=\(sourceInputSHA256)\n"),
              output.contains(
                "metadata-contract-sha256=\(metadataContractSHA256)\n"
              ) else {
            throw InstallationLifecycleError.unverifiedInstalledState
        }
    }
}
