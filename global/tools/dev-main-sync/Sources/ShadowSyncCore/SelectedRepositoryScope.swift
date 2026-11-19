import Darwin
import ShadowSyncCatalog
import Foundation

public enum SelectedRepositoryScopeError:
    Error, CustomStringConvertible, Equatable {
    case invalidIntent
    case policyUnavailable
    case catalogDegraded(String)
    case changed
    case unknown(String)
    case ambiguous(String)
    case forbidden(String)
    case unsafeTraversal(String)

    public var description: String {
        switch self {
        case .invalidIntent:
            return "Repository selection is empty or invalid."
        case .policyUnavailable:
            return "The current repository policy is unavailable."
        case let .catalogDegraded(reason):
            return "Repository selection cannot continue: \(reason)"
        case .changed:
            return "Repository locations changed — reload before continuing."
        case let .unknown(id):
            return "Selected repository is no longer present: \(id)"
        case let .ambiguous(id):
            return "Selected repository is ambiguous: \(id)"
        case let .forbidden(id):
            return "Selected repository is no longer allowed: \(id)"
        case let .unsafeTraversal(id):
            return "Selected repository location is unsafe: \(id)"
        }
    }
}

public struct ValidatedSelectedRepository:
    Equatable, Sendable {
    public let repositoryID: String
    public let locator: RepositorySelectionLocator
    public let governedRootPath: String
    public let policyRootPath: String
    public let repositoryPath: String
    public let rootIdentity: FileIdentity
    public let repositoryIdentity: FileIdentity
}

public struct ValidatedSelectedRepositoryScope:
    Equatable, Sendable {
    public let selectionGeneration: UInt64
    public let policyDigest: String
    public let catalogGeneration: UInt64
    public let repositories: [ValidatedSelectedRepository]

    public var repositoryIDs: Set<String> {
        Set(repositories.map(\.repositoryID))
    }

    public var repositoryPaths: Set<String> {
        Set(repositories.map(\.repositoryPath))
    }

    public func exactRepositoryScope(
        repositoryID: String
    ) throws -> ValidatedSelectedRepositoryScope {
        let matches = repositories.filter {
            $0.repositoryID == repositoryID
        }
        guard matches.count == 1 else {
            throw matches.isEmpty
                ? SelectedRepositoryScopeError.unknown(repositoryID)
                : SelectedRepositoryScopeError.ambiguous(repositoryID)
        }
        return ValidatedSelectedRepositoryScope(
            selectionGeneration: selectionGeneration,
            policyDigest: policyDigest,
            catalogGeneration: catalogGeneration,
            repositories: matches
        )
    }

    public func admits(_ candidate: RepositoryCandidate) -> Bool {
        repositories.contains {
            $0.repositoryID == candidate.id
                && $0.repositoryPath == candidate.path
                && $0.repositoryIdentity.device
                    == candidate.rootIdentity?.device
                && $0.repositoryIdentity.inode
                    == candidate.rootIdentity?.inode
        }
    }

    #if SHADOW_SYNC_TESTING
    public static func testing(
        candidates: [RepositoryCandidate]
    ) throws -> ValidatedSelectedRepositoryScope {
        let grouped = Dictionary(
            grouping: candidates,
            by: \.id
        )
        var repositories: [ValidatedSelectedRepository] = []
        for (index, repositoryID) in grouped.keys.sorted().enumerated() {
            guard let candidate = grouped[repositoryID]?.first else {
                continue
            }
            var repositoryInfo = stat()
            guard lstat(candidate.path, &repositoryInfo) == 0 else {
                throw SelectedRepositoryScopeError.changed
            }
            let identity = FileIdentity(repositoryInfo)
            repositories.append(
                ValidatedSelectedRepository(
                    repositoryID: repositoryID,
                    locator: try RepositorySelectionLocator(
                        governedRoot: "testing",
                        components: ["repository-\(index)"]
                    ),
                    governedRootPath:
                        URL(fileURLWithPath: candidate.path)
                            .deletingLastPathComponent().path,
                    policyRootPath:
                        URL(fileURLWithPath: candidate.path)
                            .deletingLastPathComponent().path,
                    repositoryPath: candidate.path,
                    rootIdentity: identity,
                    repositoryIdentity: identity
                )
            )
        }
        return ValidatedSelectedRepositoryScope(
            selectionGeneration: 1,
            policyDigest: String(repeating: "0", count: 64),
            catalogGeneration: 1,
            repositories: repositories
        )
    }

    public static func testing(
        plan: Body3BatchPlan
    ) throws -> ValidatedSelectedRepositoryScope {
        let candidates = plan.nodes.flatMap {
            node -> [RepositoryCandidate] in
            switch node.payload {
            case let .operation(operation):
                return [
                    operation.target.canonicalClone.sourceSnapshot,
                ]
            case let .removal(candidate),
                 let .residue(candidate):
                return [candidate.clone.sourceSnapshot]
            case let .retention(selection):
                return [selection.candidate.clone.sourceSnapshot]
            case let .confirmation(selections):
                return selections.map {
                    $0.candidate.clone.sourceSnapshot
                }
            case .reinspection, .policyInvalidation:
                return []
            }
        }
        return try testing(candidates: candidates)
    }
    #endif
}

public final class SelectedRepositoryScopeBinder:
    @unchecked Sendable {
    private let governedRootPath: String
    private let policyRootPath: String
    private let logicalRoot: String
    private let policyPathPrefix: [String]
    private let expectedUID: uid_t
    private let catalogLimits: RepositorySelectionCatalogLimits

    public static func production() throws
        -> SelectedRepositoryScopeBinder {
        let account = try EffectiveAccount.current()
        return SelectedRepositoryScopeBinder(
            governedRootPath: account.homeDirectory,
            policyRootPath: URL(
                fileURLWithPath: account.homeDirectory
            ).appendingPathComponent("dev", isDirectory: true).path,
            logicalRoot: "~",
            policyPathPrefix: ["dev"],
            expectedUID: account.uid
        )
    }

    public init(
        governedRootPath: String,
        policyRootPath: String? = nil,
        logicalRoot: String,
        policyPathPrefix: [String] = [],
        expectedUID: uid_t = geteuid(),
        catalogLimits: RepositorySelectionCatalogLimits =
            RepositorySelectionCatalogLimits()
    ) {
        self.governedRootPath = governedRootPath
        self.policyRootPath = policyRootPath ?? governedRootPath
        self.logicalRoot = logicalRoot
        self.policyPathPrefix = policyPathPrefix
        self.expectedUID = expectedUID
        self.catalogLimits = catalogLimits
    }

    public func processFreeCatalog(
        preferences: RepositorySelectionPreferenceDocument?,
        canonicalLocators:
            [String: RepositorySelectionLocator] = [:],
        sessionEntries:
            [RepositorySelectionPreferenceEntry] = [],
        generation: UInt64
    ) throws -> RepositorySelectionCatalogResult {
        let root = try openRoot()
        defer { close(root.descriptor) }
        let policy: RepositoryPolicy
        do {
            policy = try RepositoryPolicyLoader.load(
                rootPath: policyRootPath
            )
        } catch {
            throw SelectedRepositoryScopeError.policyUnavailable
        }
        let projection = try selectionPolicy(policy)
        let rootSelectionIdentity =
            RepositorySelectionCatalogIdentity(
                device: root.identity.device,
                inode: root.identity.inode,
                owner: root.identity.owner
            )
        let catalogRoot = try RepositorySelectionCatalogRoot(
            logicalKey: logicalRoot,
            descriptor: root.descriptor,
            identity: rootSelectionIdentity
        )
        return RepositorySelectionCatalogDiscovery.discoverCatalog(
            configuration: RepositorySelectionCatalogConfiguration(
                roots: [catalogRoot],
                policy: projection,
                preferences: preferences,
                canonicalLocators: canonicalLocators,
                sessionEntries: sessionEntries,
                generation: generation,
                limits: catalogLimits
            )
        )
    }

    public func bind(
        intent: RepositorySelectionIntent
    ) throws -> ValidatedSelectedRepositoryScope {
        guard !intent.entries.isEmpty else {
            throw SelectedRepositoryScopeError.invalidIntent
        }
        let root = try openRoot()
        defer { close(root.descriptor) }
        let policy: RepositoryPolicy
        do {
            policy = try RepositoryPolicyLoader.load(
                rootPath: policyRootPath
            )
        } catch {
            throw SelectedRepositoryScopeError.policyUnavailable
        }
        let projection = try selectionPolicy(policy)
        let rootSelectionIdentity =
            RepositorySelectionCatalogIdentity(
                device: root.identity.device,
                inode: root.identity.inode,
                owner: root.identity.owner
            )
        guard intent.policyDigest == policy.admissionSHA256,
              intent.rootIdentities == [
                  logicalRoot: rootSelectionIdentity
              ] else {
            throw SelectedRepositoryScopeError.changed
        }
        let catalogRoot = try RepositorySelectionCatalogRoot(
            logicalKey: logicalRoot,
            descriptor: root.descriptor,
            identity: rootSelectionIdentity
        )
        let catalog = RepositorySelectionCatalogDiscovery.discoverCatalog(
            configuration: RepositorySelectionCatalogConfiguration(
                roots: [catalogRoot],
                policy: projection,
                preferences: nil,
                canonicalLocators: Dictionary(
                    uniqueKeysWithValues: intent.entries.map {
                        ($0.repositoryID, $0.locator)
                    }
                ),
                generation: intent.generation,
                limits: catalogLimits
            )
        )
        guard catalog.isComplete else {
            throw SelectedRepositoryScopeError.catalogDegraded(
                catalog.degradedReason?.operatorExplanation
                    ?? "catalog incomplete"
            )
        }
        guard catalog.catalog.policyDigest == intent.policyDigest,
              catalog.catalog.rootIdentities
                == intent.rootIdentities else {
            throw SelectedRepositoryScopeError.changed
        }
        var bound: [ValidatedSelectedRepository] = []
        for entry in intent.entries {
            guard entry.locator.governedRoot == logicalRoot else {
                throw SelectedRepositoryScopeError.forbidden(
                    entry.repositoryID
                )
            }
            let matches = catalog.catalog.candidates.filter {
                $0.id == entry.repositoryID
                    && $0.locator == entry.locator
            }
            guard matches.count == 1, let candidate = matches.first else {
                let idMatches = catalog.catalog.candidates.filter {
                    $0.id == entry.repositoryID
                        || $0.locator == entry.locator
                }
                throw idMatches.isEmpty
                    ? SelectedRepositoryScopeError.unknown(
                        entry.repositoryID
                    )
                    : SelectedRepositoryScopeError.ambiguous(
                        entry.repositoryID
                    )
            }
            guard candidate.isVisible,
                  candidate.isEligible,
                  candidate.policyDisposition == .writable,
                  candidate.catalogRootIdentity
                    == rootSelectionIdentity,
                  let expectedRepositoryIdentity =
                    intent.repositoryIdentities[entry],
                  candidate.catalogRepositoryIdentity
                    == expectedRepositoryIdentity,
                  !projection.isArtifactOrHiddenPrefix(
                      entry.locator.components
                  ) else {
                throw SelectedRepositoryScopeError.forbidden(
                    entry.repositoryID
                )
            }
            let repository = try traverse(
                entry: entry,
                root: root
            )
            guard RepositorySelectionCatalogIdentity(
                device: repository.repositoryIdentity.device,
                inode: repository.repositoryIdentity.inode,
                owner: repository.repositoryIdentity.owner
            ) == expectedRepositoryIdentity else {
                throw SelectedRepositoryScopeError.changed
            }
            bound.append(repository)
        }
        var finalRoot = stat()
        guard fstat(root.descriptor, &finalRoot) == 0,
              FileIdentity(finalRoot) == root.identity else {
            throw SelectedRepositoryScopeError.changed
        }
        guard Set(bound.map(\.repositoryID)).count == bound.count,
              Set(bound.map(\.repositoryPath)).count == bound.count else {
            throw SelectedRepositoryScopeError.ambiguous(
                "duplicate selected scope"
            )
        }
        return ValidatedSelectedRepositoryScope(
            selectionGeneration: intent.generation,
            policyDigest: policy.admissionSHA256,
            catalogGeneration: catalog.catalog.generation,
            repositories: bound.sorted {
                $0.repositoryID == $1.repositoryID
                    ? $0.locator < $1.locator
                    : $0.repositoryID < $1.repositoryID
            }
        )
    }

    public func canonicalLocators(
        records: [RepositoryAuthorityRecord]
    ) -> [String: RepositorySelectionLocator] {
        records.reduce(into: [:]) { result, record in
            let root = URL(
                fileURLWithPath: governedRootPath,
                isDirectory: true
            ).standardizedFileURL.path
            let canonical = URL(
                fileURLWithPath: record.canonicalRoot,
                isDirectory: true
            ).standardizedFileURL.path
            let relative: String
            if canonical == root {
                relative = ""
            } else if canonical.hasPrefix(root + "/") {
                relative = String(
                    canonical.dropFirst(root.count + 1)
                )
            } else {
                return
            }
            let components = relative.isEmpty
                ? [] : relative.split(separator: "/").map(String.init)
            guard let locator = try? RepositorySelectionLocator(
                governedRoot: logicalRoot,
                components: components
            ) else {
                return
            }
            result[record.repositoryID] = locator
        }
    }

    public func canonicalRootPath(
        for locator: RepositorySelectionLocator
    ) -> String? {
        guard locator.governedRoot == logicalRoot else {
            return nil
        }
        let suffix = locator.components.joined(separator: "/")
        return suffix.isEmpty
            ? governedRootPath
            : governedRootPath + "/" + suffix
    }

    private struct OpenedRoot {
        let descriptor: Int32
        let physicalPath: String
        let identity: FileIdentity
    }

    private func openRoot() throws -> OpenedRoot {
        let descriptor = Darwin.open(
            governedRootPath,
            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        )
        guard descriptor >= 0 else {
            throw SelectedRepositoryScopeError.changed
        }
        do {
            var info = stat()
            guard fstat(descriptor, &info) == 0,
                  FileIdentity(info).isDirectory,
                  info.st_uid == expectedUID,
                  (info.st_mode & 0o022) == 0 else {
                throw SelectedRepositoryScopeError.changed
            }
            let path = try descriptorPath(descriptor)
            return OpenedRoot(
                descriptor: descriptor,
                physicalPath: path,
                identity: FileIdentity(info)
            )
        } catch {
            close(descriptor)
            throw error
        }
    }

    private func traverse(
        entry: RepositorySelectionPreferenceEntry,
        root: OpenedRoot
    ) throws -> ValidatedSelectedRepository {
        var current = dup(root.descriptor)
        guard current >= 0 else {
            throw SelectedRepositoryScopeError.unsafeTraversal(
                entry.repositoryID
            )
        }
        defer { close(current) }
        var identity = root.identity
        for component in entry.locator.components {
            let next = openat(
                current,
                component,
                O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
            )
            guard next >= 0 else {
                throw SelectedRepositoryScopeError.changed
            }
            close(current)
            current = next
            var info = stat()
            guard fstat(current, &info) == 0,
                  FileIdentity(info).isDirectory,
                  info.st_uid == expectedUID,
                  (info.st_mode & 0o022) == 0 else {
                throw SelectedRepositoryScopeError.unsafeTraversal(
                    entry.repositoryID
                )
            }
            identity = FileIdentity(info)
            var rootInfo = stat()
            guard fstat(root.descriptor, &rootInfo) == 0,
                  FileIdentity(rootInfo) == root.identity else {
                throw SelectedRepositoryScopeError.changed
            }
        }
        var gitInfo = stat()
        guard fstatat(
            current,
            ".git",
            &gitInfo,
            AT_SYMLINK_NOFOLLOW
        ) == 0,
              (gitInfo.st_mode & S_IFMT) == S_IFDIR
                || (gitInfo.st_mode & S_IFMT) == S_IFREG else {
            throw SelectedRepositoryScopeError.changed
        }
        let physical = try descriptorPath(current)
        guard physical == root.physicalPath
                + "/" + entry.locator.relativePath else {
            throw SelectedRepositoryScopeError.changed
        }
        return ValidatedSelectedRepository(
            repositoryID: entry.repositoryID,
            locator: entry.locator,
            governedRootPath: root.physicalPath,
            policyRootPath: policyRootPath,
            repositoryPath: physical,
            rootIdentity: root.identity,
            repositoryIdentity: identity
        )
    }

    private func selectionPolicy(
        _ policy: RepositoryPolicy
    ) throws -> RepositorySelectionPolicy {
        func prefixed(_ path: String) -> String {
            let prefix = policyPathPrefix.joined(separator: "/")
            guard !prefix.isEmpty else { return path }
            return path == "." ? prefix : prefix + "/" + path
        }
        let shelves = policyPathPrefix.isEmpty
            ? [
                ["capabilities"],
                ["personal"],
                ["affirm", "src"],
                ["affirm", "vendor"],
            ]
            : [
                policyPathPrefix,
                policyPathPrefix + ["capabilities"],
                policyPathPrefix + ["personal"],
                policyPathPrefix + ["affirm", "src"],
                policyPathPrefix + ["affirm", "vendor"],
            ]
        return try RepositorySelectionPolicy(
            shelfPaths: shelves,
            excludedPaths: policy.excludedPaths.map(prefixed),
            readOnlyPaths: policy.readOnlyPaths.map(prefixed),
            artifactPaths: policy.artifactPaths.map(prefixed),
            writablePaths: policyPathPrefix.isEmpty
                ? [] : [
                    policyPathPrefix.joined(separator: "/"),
                ],
            digest: policy.admissionSHA256
        )
    }

    private func descriptorPath(_ descriptor: Int32) throws -> String {
        var buffer = [CChar](repeating: 0, count: Int(MAXPATHLEN))
        guard fcntl(descriptor, F_GETPATH, &buffer) == 0 else {
            throw SelectedRepositoryScopeError.changed
        }
        return String(
            decoding: buffer.prefix { $0 != 0 }.map {
                UInt8(bitPattern: $0)
            },
            as: UTF8.self
        )
    }
}
