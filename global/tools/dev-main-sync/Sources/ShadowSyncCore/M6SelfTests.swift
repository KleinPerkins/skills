#if SHADOW_SYNC_TESTING
import Darwin
import Foundation

public enum M6SelfTestRunner {
    public static func runAll(
        record: (String) -> Void
    ) throws -> [String] {
        var passed: [String] = []
        func run(_ name: String, _ body: () throws -> Void) throws {
            try body()
            passed.append(name)
            record(name)
        }

        try run("m6-release-identity-contract") {
            let first = try identity(revision: String(repeating: "a", count: 40))
            let second = try identity(revision: String(repeating: "b", count: 40))
            try check(first != second, "producing revisions were not retained")
            try check(
                first.sameInstallContract(as: second),
                "identical source contracts across revisions did not reconcile as a no-op"
            )
            try first.validate(requireProduction: true)
        }

        try run("m6-release-identity-refusals") {
            var dictionary: [String: Any] = [
                "DevMainSyncReleaseSchema": ReleaseIdentity.schemaName,
                "CFBundleShortVersionString": ReleaseIdentity.version,
                "CFBundleVersion": ReleaseIdentity.buildNumber,
                "DevMainSyncSourceRevision": String(repeating: "a", count: 40),
                "DevMainSyncSourceInputSHA256": String(repeating: "b", count: 64),
                "DevMainSyncMetadataContractSHA256": String(repeating: "c", count: 64),
                "DevMainSyncArchitecture": "arm64",
                "LSMinimumSystemVersion": ReleaseIdentity.minimumSystemVersion,
                "DevMainSyncBuildMode": "production",
            ]
            _ = try ReleaseIdentity(infoDictionary: dictionary)
            dictionary["CFBundleShortVersionString"] = "0.1.0"
            dictionary["CFBundleVersion"] = "2"
            _ = try ReleaseIdentity(infoDictionary: dictionary)
            dictionary["CFBundleShortVersionString"] =
                ReleaseIdentity.version
            dictionary["CFBundleVersion"] = "1"
            _ = try ReleaseIdentity(infoDictionary: dictionary)
            guard let currentBuild = Int(
                ReleaseIdentity.buildNumber
            ) else {
                throw M6SelfTestError.message(
                    "current build number is invalid"
                )
            }
            dictionary["CFBundleVersion"] =
                String(currentBuild + 1)
            do {
                _ = try ReleaseIdentity(infoDictionary: dictionary)
                throw M6SelfTestError.message(
                    "future build metadata was accepted"
                )
            } catch is ReleaseIdentityError {}
            dictionary["CFBundleVersion"] =
                ReleaseIdentity.buildNumber
            dictionary["DevMainSyncSourceInputSHA256"] = "../unsafe"
            do {
                _ = try ReleaseIdentity(infoDictionary: dictionary)
                throw M6SelfTestError.message("invalid source digest was accepted")
            } catch is ReleaseIdentityError {}
        }

        try run("m6-lifecycle-run-lock-race") {
            let root = try temporaryRoot()
            defer { try? FileManager.default.removeItem(atPath: root) }
            let location = try StateLocation.isolated(root: root)
            let run = try RunAuthority.acquireRun(at: location)
            defer { run.release() }
            do {
                _ = try RunAuthority.acquireLifecycleMutation(at: location)
                throw M6SelfTestError.message("lifecycle mutation overlapped a run")
            } catch let SecureStateError.contention(name) {
                try check(name == "lifecycle.lock", "wrong lifecycle contention: \(name)")
            }
        }

        try run("m6-surviving-operation-lease") {
            let root = try temporaryRoot()
            defer { try? FileManager.default.removeItem(atPath: root) }
            let location = try StateLocation.isolated(root: root)
            let run = try RunAuthority.acquireRun(at: location)
            let lease = try run.duplicateOperationLease()
            run.release()
            defer { close(lease) }
            do {
                _ = try RunAuthority.acquireLifecycleMutation(at: location)
                throw M6SelfTestError.message("lifecycle mutation ignored operation lease")
            } catch let SecureStateError.contention(name) {
                try check(name == "operation.lock", "wrong operation contention: \(name)")
            }
        }

        try run("m6-host-control-actions") {
            let generation = RunIdentity.make()
            for action in [
                HostControlAction.activate,
                .readiness,
                .lifecycleExit,
            ] {
                let request = HostControlRequest(
                    action: action,
                    expectedGeneration: generation
                )
                let data = try JSONEncoder().encode(request)
                let decoded = try JSONDecoder().decode(
                    HostControlRequest.self,
                    from: data
                )
                try check(decoded == request, "host action did not round-trip")
            }
        }

        try run("m6-launcher-handoff-single-owner") {
            let root = try temporaryRoot()
            defer { try? FileManager.default.removeItem(atPath: root) }
            let location = try StateLocation.isolated(root: root)
            let first = try LauncherAuthority.acquire(at: location)
            defer { first.release() }
            do {
                _ = try LauncherAuthority.acquire(at: location)
                throw M6SelfTestError.message("duplicate launcher acquired authority")
            } catch let SecureStateError.contention(name) {
                try check(name == "launcher.lock", "wrong launcher contention: \(name)")
            }
        }

        try run("m6-retired-lock-namespace-cannot-split") {
            let root = try temporaryRoot()
            defer { try? FileManager.default.removeItem(atPath: root) }
            let location = try StateLocation.isolated(root: root)
            let authority = try RunAuthority.acquireLifecycleMutation(at: location)
            let state = authority.stateDirectory
            try authority.acquireRetirementNamespace()
            try state.removeStableLockFiles()
            do {
                _ = try LauncherAuthority.acquire(at: location)
                throw M6SelfTestError.message(
                    "replacement lock namespace bypassed retained-log authority"
                )
            } catch let SecureStateError.contention(name) {
                try check(name == "latest.log", "wrong retired-namespace contention")
            }
            for name in [
                "launcher.lock", "lifecycle.lock", "operation.lock", "run.lock",
            ] {
                var info = stat()
                try check(
                    fstatat(
                        state.descriptor.value,
                        name,
                        &info,
                        AT_SYMLINK_NOFOLLOW
                    ) != 0 && errno == ENOENT,
                    "retired lock was recreated while namespace authority was held"
                )
            }
            authority.release()
            let replacement = try LauncherAuthority.acquire(at: location)
            replacement.release()
        }

        return passed
    }

    private static func identity(revision: String) throws -> ReleaseIdentity {
        try ReleaseIdentity(
            sourceRevision: revision,
            sourceInputSHA256: String(repeating: "b", count: 64),
            metadataContractSHA256: String(repeating: "c", count: 64),
            architecture: "arm64",
            buildMode: "production"
        )
    }

    private static func temporaryRoot() throws -> String {
        var template = Array("/private/tmp/dev-main-sync-m6-self.XXXXXX".utf8CString)
        guard let pointer = mkdtemp(&template) else {
            throw M6SelfTestError.message("could not create private test root")
        }
        let path = String(cString: pointer)
        guard chmod(path, 0o700) == 0 else {
            throw M6SelfTestError.message("could not secure private test root")
        }
        return path
    }

    private static func check(
        _ condition: @autoclosure () -> Bool,
        _ message: String
    ) throws {
        if !condition() {
            throw M6SelfTestError.message(message)
        }
    }
}

private enum M6SelfTestError: Error {
    case message(String)
}
#endif
