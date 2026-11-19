import Darwin
import Foundation

public enum SecureStateError: Error, CustomStringConvertible {
    case accountLookup(Int32)
    case invalidAccountRecord
    case unsafePath(String)
    case systemCall(String, Int32)
    case contention(String)

    public var description: String {
        switch self {
        case let .accountLookup(code):
            return "effective account lookup failed (\(code))"
        case .invalidAccountRecord:
            return "effective account record is incomplete"
        case let .unsafePath(path):
            return "unsafe state path: \(path)"
        case let .systemCall(name, code):
            return "\(name) failed: \(String(cString: strerror(code)))"
        case let .contention(name):
            return "\(name) is already owned"
        }
    }
}

public struct EffectiveAccount: Equatable, Sendable {
    public let uid: uid_t
    public let username: String
    public let homeDirectory: String

    public static func current() throws -> EffectiveAccount {
        let uid = geteuid()
        let suggested = sysconf(_SC_GETPW_R_SIZE_MAX)
        let size = suggested > 0 ? Int(suggested) : 16_384
        var record = passwd()
        var result: UnsafeMutablePointer<passwd>?
        var buffer = [CChar](repeating: 0, count: size)
        let count = buffer.count
        let code = getpwuid_r(uid, &record, &buffer, count, &result)
        guard code == 0 else {
            throw SecureStateError.accountLookup(code)
        }
        guard result != nil, let name = record.pw_name, let home = record.pw_dir else {
            throw SecureStateError.invalidAccountRecord
        }
        let username = String(cString: name)
        let homeDirectory = String(cString: home)
        guard homeDirectory.hasPrefix("/"), !username.isEmpty else {
            throw SecureStateError.invalidAccountRecord
        }
        return EffectiveAccount(uid: uid, username: username, homeDirectory: homeDirectory)
    }

    #if SHADOW_SYNC_TESTING
    public static func isolated(homeDirectory: String) throws -> EffectiveAccount {
        let root = URL(fileURLWithPath: homeDirectory).deletingLastPathComponent().path
        _ = try TestIsolation.validateRoot(root)
        try TestIsolation.validateContainedDirectory(homeDirectory, root: root)
        let current = try Self.current()
        return EffectiveAccount(
            uid: current.uid,
            username: current.username,
            homeDirectory: homeDirectory
        )
    }
    #endif
}

public struct StateLocation: Equatable, Sendable {
    public let anchorPath: String
    public let components: [String]
    public let uid: uid_t

    public static func production() throws -> StateLocation {
        let account = try EffectiveAccount.current()
        return StateLocation(
            anchorPath: account.homeDirectory,
            components: [".local", "state", "dev-main-sync"],
            uid: account.uid
        )
    }

    init(anchorPath: String, components: [String], uid: uid_t) {
        self.anchorPath = anchorPath
        self.components = components
        self.uid = uid
    }

    #if SHADOW_SYNC_TESTING
    public static func isolated(root: String) throws -> StateLocation {
        let root = try TestIsolation.validateRoot(root)
        return StateLocation(
            anchorPath: root,
            components: ["state", "dev-main-sync"],
            uid: geteuid()
        )
    }
    #endif

    public var path: String {
        components.reduce(anchorPath) { partial, component in
            URL(fileURLWithPath: partial).appendingPathComponent(component).path
        }
    }
}

#if SHADOW_SYNC_TESTING
public enum TestIsolation {
    public static func validateRoot(_ root: String) throws -> String {
        guard root.hasPrefix("/private/tmp/"),
              !root.contains("\n"),
              !root.contains("\0"),
              !root.components(separatedBy: "/").contains("."),
              !root.components(separatedBy: "/").contains(".."),
              physicalPath(root) == root else {
            throw SecureStateError.unsafePath(root)
        }
        var info = stat()
        guard lstat(root, &info) == 0,
              (info.st_mode & S_IFMT) == S_IFDIR,
              info.st_uid == geteuid(),
              (info.st_mode & 0o077) == 0 else {
            throw SecureStateError.unsafePath(root)
        }
        return root
    }

    public static func validateContainedDirectory(
        _ path: String,
        root: String
    ) throws {
        let root = try validateRoot(root)
        guard path.hasPrefix(root + "/"),
              !path.components(separatedBy: "/").contains("."),
              !path.components(separatedBy: "/").contains(".."),
              let physical = physicalPath(path),
              physical.hasPrefix(root + "/") else {
            throw SecureStateError.unsafePath(path)
        }
        var info = stat()
        guard lstat(path, &info) == 0,
              (info.st_mode & S_IFMT) == S_IFDIR,
              info.st_uid == geteuid(),
              (info.st_mode & 0o077) == 0 else {
            throw SecureStateError.unsafePath(path)
        }
    }

    private static func physicalPath(_ path: String) -> String? {
        guard let pointer = realpath(path, nil) else {
            return nil
        }
        defer { free(pointer) }
        return String(cString: pointer)
    }
}
#endif

public struct FileIdentity: Codable, Equatable, Sendable {
    public let device: UInt64
    public let inode: UInt64
    public let owner: UInt32
    public let mode: UInt16
    public let linkCount: UInt16

    init(_ value: stat) {
        device = UInt64(value.st_dev)
        inode = UInt64(value.st_ino)
        owner = UInt32(value.st_uid)
        mode = UInt16(value.st_mode)
        linkCount = UInt16(value.st_nlink)
    }

    var isDirectory: Bool {
        (mode_t(mode) & S_IFMT) == S_IFDIR
    }

    var isRegular: Bool {
        (mode_t(mode) & S_IFMT) == S_IFREG
    }

    func matchesStableNode(_ other: FileIdentity) -> Bool {
        device == other.device
            && inode == other.inode
            && owner == other.owner
            && mode == other.mode
    }
}

final class OwnedFileDescriptor: @unchecked Sendable {
    private let lock = NSLock()
    private var rawValue: Int32

    init(_ rawValue: Int32) {
        self.rawValue = rawValue
    }

    var value: Int32 {
        lock.lock()
        defer { lock.unlock() }
        return rawValue
    }

    func closeNow() {
        lock.lock()
        let fd = rawValue
        rawValue = -1
        lock.unlock()
        if fd >= 0 {
            close(fd)
        }
    }

    deinit {
        closeNow()
    }
}

public final class SecureStateDirectory: @unchecked Sendable {
    let descriptor: OwnedFileDescriptor
    public let path: String
    public let uid: uid_t

    private init(descriptor: Int32, path: String, uid: uid_t) {
        self.descriptor = OwnedFileDescriptor(descriptor)
        self.path = path
        self.uid = uid
    }

    public static func open(_ location: StateLocation) throws -> SecureStateDirectory {
        try open(location, create: true, repairPermissions: true)
    }

    public static func openExisting(_ location: StateLocation) throws -> SecureStateDirectory {
        try open(location, create: false, repairPermissions: false)
    }

    private static func open(
        _ location: StateLocation,
        create: Bool,
        repairPermissions: Bool
    ) throws -> SecureStateDirectory {
        let anchor = Darwin.open(location.anchorPath, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard anchor >= 0 else {
            throw SecureStateError.systemCall("open state anchor", errno)
        }
        var current = anchor
        var currentOwned = true
        defer {
            if currentOwned {
                close(current)
            }
        }
        try validateDirectory(fd: current, uid: location.uid, requirePrivate: false, label: location.anchorPath)

        for (index, component) in location.components.enumerated() {
            guard !component.isEmpty, component != ".", component != "..", !component.contains("/") else {
                throw SecureStateError.unsafePath(component)
            }
            if create, mkdirat(current, component, 0o700) != 0, errno != EEXIST {
                throw SecureStateError.systemCall("mkdirat \(component)", errno)
            }
            let next = openat(current, component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
            guard next >= 0 else {
                throw SecureStateError.systemCall("openat \(component)", errno)
            }
            if current != anchor || index > 0 {
                close(current)
            } else {
                close(anchor)
            }
            current = next
            try validateDirectory(
                fd: current,
                uid: location.uid,
                requirePrivate: index == location.components.count - 1,
                repairPermissions: repairPermissions,
                label: component
            )
        }
        currentOwned = false
        return SecureStateDirectory(descriptor: current, path: location.path, uid: location.uid)
    }

    private static func validateDirectory(
        fd: Int32,
        uid: uid_t,
        requirePrivate: Bool,
        repairPermissions: Bool = false,
        label: String
    ) throws {
        var info = stat()
        guard fstat(fd, &info) == 0 else {
            throw SecureStateError.systemCall("fstat \(label)", errno)
        }
        let identity = FileIdentity(info)
        guard identity.isDirectory, info.st_uid == uid else {
            throw SecureStateError.unsafePath(label)
        }
        if requirePrivate {
            if repairPermissions {
                guard fchmod(fd, 0o700) == 0 else {
                    throw SecureStateError.systemCall("fchmod state directory", errno)
                }
            }
            guard (info.st_mode & 0o077) == 0 || refreshedPrivateMode(fd) else {
                throw SecureStateError.unsafePath(label)
            }
        }
    }

    private static func refreshedPrivateMode(_ fd: Int32) -> Bool {
        var refreshed = stat()
        return fstat(fd, &refreshed) == 0 && (refreshed.st_mode & 0o077) == 0
    }

    func openRegularFile(
        named name: String,
        flags: Int32,
        create: Bool,
        mode: mode_t = 0o600,
        repairPermissions: Bool = true
    ) throws -> Int32 {
        guard !name.isEmpty, name != ".", name != "..", !name.contains("/") else {
            throw SecureStateError.unsafePath(name)
        }
        let openFlags = flags | O_NOFOLLOW | O_CLOEXEC | (create ? O_CREAT : 0)
        let fd = openat(descriptor.value, name, openFlags, mode)
        guard fd >= 0 else {
            throw SecureStateError.systemCall("openat \(name)", errno)
        }
        do {
            try validateRegular(
                fd: fd,
                name: name,
                repairPermissions: repairPermissions
            )
            return fd
        } catch {
            close(fd)
            throw error
        }
    }

    func validateRegular(
        fd: Int32,
        name: String,
        repairPermissions: Bool = true
    ) throws {
        var opened = stat()
        guard fstat(fd, &opened) == 0 else {
            throw SecureStateError.systemCall("fstat \(name)", errno)
        }
        guard FileIdentity(opened).isRegular,
              opened.st_uid == uid,
              opened.st_nlink == 1 else {
            throw SecureStateError.unsafePath(name)
        }
        if repairPermissions {
            guard fchmod(fd, 0o600) == 0 else {
                throw SecureStateError.systemCall("fchmod \(name)", errno)
            }
        } else if (opened.st_mode & 0o077) != 0 {
            throw SecureStateError.unsafePath(name)
        }
        var relative = stat()
        guard fstatat(descriptor.value, name, &relative, AT_SYMLINK_NOFOLLOW) == 0 else {
            throw SecureStateError.systemCall("fstatat \(name)", errno)
        }
        guard opened.st_dev == relative.st_dev,
              opened.st_ino == relative.st_ino,
              FileIdentity(relative).isRegular,
              relative.st_nlink == 1 else {
            throw SecureStateError.unsafePath(name)
        }
    }

    func ownedEntryIdentity(
        named name: String,
        allowSocket: Bool
    ) throws -> FileIdentity {
        guard !name.isEmpty, name != ".", name != "..", !name.contains("/") else {
            throw SecureStateError.unsafePath(name)
        }
        var info = stat()
        guard fstatat(descriptor.value, name, &info, AT_SYMLINK_NOFOLLOW) == 0 else {
            throw SecureStateError.systemCall("fstatat \(name)", errno)
        }
        let type = info.st_mode & S_IFMT
        guard info.st_uid == uid,
              ((allowSocket && type == S_IFSOCK)
                || (type == S_IFREG && info.st_nlink == 1)) else {
            throw SecureStateError.unsafePath(name)
        }
        return FileIdentity(info)
    }

    func removeOwnedEntry(
        named name: String,
        expected: FileIdentity
    ) throws {
        guard !["lifecycle.lock", "operation.lock", "run.lock", "launcher.lock"]
            .contains(name) else {
            throw SecureStateError.unsafePath(name)
        }
        let observed = try ownedEntryIdentity(
            named: name,
            allowSocket: (mode_t(expected.mode) & S_IFMT) == S_IFSOCK
        )
        guard observed.matchesStableNode(expected) else {
            throw SecureStateError.unsafePath(name)
        }
        guard unlinkat(descriptor.value, name, 0) == 0 else {
            throw SecureStateError.systemCall("unlinkat \(name)", errno)
        }
    }

    func renameOwnedEntry(
        named source: String,
        to destination: String,
        expected: FileIdentity
    ) throws {
        let protected = [
            "lifecycle.lock", "operation.lock", "run.lock", "launcher.lock",
        ]
        guard !protected.contains(source),
              !protected.contains(destination),
              !source.isEmpty,
              source != ".",
              source != "..",
              !source.contains("/"),
              !destination.isEmpty,
              destination != ".",
              destination != "..",
              !destination.contains("/") else {
            throw SecureStateError.unsafePath(source)
        }
        var destinationInfo = stat()
        guard fstatat(
            descriptor.value,
            destination,
            &destinationInfo,
            AT_SYMLINK_NOFOLLOW
        ) != 0, errno == ENOENT else {
            throw SecureStateError.unsafePath(destination)
        }
        let allowSocket = (mode_t(expected.mode) & S_IFMT) == S_IFSOCK
        let observed = try ownedEntryIdentity(
            named: source,
            allowSocket: allowSocket
        )
        guard observed.matchesStableNode(expected),
              renameat(
                descriptor.value,
                source,
                descriptor.value,
                destination
              ) == 0 else {
            throw SecureStateError.unsafePath(source)
        }
        let renamed = try ownedEntryIdentity(
            named: destination,
            allowSocket: allowSocket
        )
        guard renamed.matchesStableNode(expected) else {
            _ = renameat(
                descriptor.value,
                destination,
                descriptor.value,
                source
            )
            throw SecureStateError.unsafePath(destination)
        }
        guard fsync(descriptor.value) == 0 else {
            let code = errno
            _ = renameat(
                descriptor.value,
                destination,
                descriptor.value,
                source
            )
            _ = fsync(descriptor.value)
            throw SecureStateError.systemCall(
                "fsync state namespace",
                code
            )
        }
    }

    func ensureStableLockFiles() throws {
        for name in ["lifecycle.lock", "operation.lock", "run.lock", "launcher.lock"] {
            let descriptor = try openRegularFile(
                named: name,
                flags: O_RDWR,
                create: true
            )
            close(descriptor)
        }
    }

    func ensureRetainedLog() throws {
        let descriptor = try openRegularFile(
            named: "latest.log",
            flags: O_RDWR,
            create: true
        )
        close(descriptor)
    }

    func removeStableLockFiles(
        afterRemoving: (String) throws -> Void = { _ in }
    ) throws {
        let names = ["launcher.lock", "run.lock", "operation.lock", "lifecycle.lock"]
        let identities = try Dictionary(uniqueKeysWithValues: names.map {
            ($0, try ownedEntryIdentity(named: $0, allowSocket: false))
        })
        for name in names {
            guard let expected = identities[name] else {
                throw SecureStateError.unsafePath(name)
            }
            let observed = try ownedEntryIdentity(named: name, allowSocket: false)
            guard observed.matchesStableNode(expected),
                  unlinkat(descriptor.value, name, 0) == 0 else {
                throw SecureStateError.unsafePath(name)
            }
            try afterRemoving(name)
        }
        guard fsync(descriptor.value) == 0 else {
            throw SecureStateError.systemCall("fsync retired state namespace", errno)
        }
    }
}

public final class RunAuthority: @unchecked Sendable {
    private let state: SecureStateDirectory
    private let namespace: OwnedFileDescriptor
    private let lifecycle: OwnedFileDescriptor
    private let operation: OwnedFileDescriptor
    private let run: OwnedFileDescriptor?

    public var stateDirectory: SecureStateDirectory { state }

    private init(
        state: SecureStateDirectory,
        namespace: Int32,
        lifecycle: Int32,
        operation: Int32,
        run: Int32?
    ) {
        self.state = state
        self.namespace = OwnedFileDescriptor(namespace)
        self.lifecycle = OwnedFileDescriptor(lifecycle)
        self.operation = OwnedFileDescriptor(operation)
        self.run = run.map(OwnedFileDescriptor.init)
    }

    public static func acquireRun(at location: StateLocation) throws -> RunAuthority {
        let state = try SecureStateDirectory.open(location)
        try state.ensureRetainedLog()
        let namespace = try acquireLock(state: state, name: "latest.log", operation: LOCK_SH)
        do {
            try state.ensureStableLockFiles()
            let lifecycle = try acquireLock(
                state: state,
                name: "lifecycle.lock",
                operation: LOCK_SH
            )
            do {
                let operation = try acquireLock(
                    state: state,
                    name: "operation.lock",
                    operation: LOCK_EX
                )
                do {
                    let run = try acquireLock(
                        state: state,
                        name: "run.lock",
                        operation: LOCK_EX
                    )
                    return RunAuthority(
                        state: state,
                        namespace: namespace,
                        lifecycle: lifecycle,
                        operation: operation,
                        run: run
                    )
                } catch {
                    close(operation)
                    throw error
                }
            } catch {
                close(lifecycle)
                throw error
            }
        } catch {
            close(namespace)
            throw error
        }
    }

    public static func acquireLifecycleMutation(at location: StateLocation) throws -> RunAuthority {
        let state = try SecureStateDirectory.open(location)
        try state.ensureRetainedLog()
        let namespace = try acquireLock(state: state, name: "latest.log", operation: LOCK_SH)
        do {
            try state.ensureStableLockFiles()
            let lifecycle = try acquireLock(
                state: state,
                name: "lifecycle.lock",
                operation: LOCK_EX
            )
            do {
                let operation = try acquireLock(
                    state: state,
                    name: "operation.lock",
                    operation: LOCK_EX
                )
                return RunAuthority(
                    state: state,
                    namespace: namespace,
                    lifecycle: lifecycle,
                    operation: operation,
                    run: nil
                )
            } catch {
                close(lifecycle)
                throw error
            }
        } catch {
            close(namespace)
            throw error
        }
    }

    private static func acquireLock(
        state: SecureStateDirectory,
        name: String,
        operation: Int32
    ) throws -> Int32 {
        let fd = try state.openRegularFile(named: name, flags: O_RDWR, create: true)
        guard flock(fd, operation | LOCK_NB) == 0 else {
            let code = errno
            close(fd)
            if code == EWOULDBLOCK {
                throw SecureStateError.contention(name)
            }
            throw SecureStateError.systemCall("flock \(name)", code)
        }
        let existing = fcntl(fd, F_GETFD)
        guard existing >= 0, fcntl(fd, F_SETFD, existing | FD_CLOEXEC) == 0 else {
            let code = errno
            close(fd)
            throw SecureStateError.systemCall("fcntl \(name)", code)
        }
        return fd
    }

    func duplicateOperationLease() throws -> Int32 {
        let copy = dup(operation.value)
        guard copy >= 0 else {
            throw SecureStateError.systemCall("dup operation lease", errno)
        }
        let flags = fcntl(copy, F_GETFD)
        guard flags >= 0, fcntl(copy, F_SETFD, flags | FD_CLOEXEC) == 0 else {
            let code = errno
            close(copy)
            throw SecureStateError.systemCall("fcntl operation lease", code)
        }
        return copy
    }

    func permitStagedHostAdmission() throws {
        lifecycle.closeNow()
    }

    func acquireRetirementNamespace(timeout: TimeInterval = 5) throws {
        let deadline = MonotonicDeadline(seconds: timeout)
        repeat {
            if flock(namespace.value, LOCK_EX | LOCK_NB) == 0 {
                return
            }
            let code = errno
            guard code == EWOULDBLOCK else {
                throw SecureStateError.systemCall(
                    "upgrade retained-log authority",
                    code
                )
            }
            Thread.sleep(forTimeInterval: 0.05)
        } while !deadline.hasExpired
        throw SecureStateError.contention("latest.log")
    }

    public func release() {
        run?.closeNow()
        operation.closeNow()
        lifecycle.closeNow()
        namespace.closeNow()
    }
}

public final class LifecycleAdmissionAuthority: @unchecked Sendable {
    public let stateDirectory: SecureStateDirectory
    private let namespace: OwnedFileDescriptor
    private let lifecycle: OwnedFileDescriptor

    private init(state: SecureStateDirectory, namespace: Int32, lifecycle: Int32) {
        stateDirectory = state
        self.namespace = OwnedFileDescriptor(namespace)
        self.lifecycle = OwnedFileDescriptor(lifecycle)
    }

    public static func acquire(at location: StateLocation) throws -> LifecycleAdmissionAuthority {
        let state = try SecureStateDirectory.openExisting(location)
        let namespace = try state.openRegularFile(
            named: "latest.log",
            flags: O_RDONLY,
            create: false,
            repairPermissions: false
        )
        guard flock(namespace, LOCK_SH | LOCK_NB) == 0 else {
            let code = errno
            close(namespace)
            if code == EWOULDBLOCK {
                throw SecureStateError.contention("latest.log")
            }
            throw SecureStateError.systemCall("flock latest.log", code)
        }
        let descriptor = try state.openRegularFile(
            named: "lifecycle.lock",
            flags: O_RDONLY,
            create: false,
            repairPermissions: false
        )
        guard flock(descriptor, LOCK_SH | LOCK_NB) == 0 else {
            let code = errno
            close(descriptor)
            close(namespace)
            if code == EWOULDBLOCK {
                throw SecureStateError.contention("lifecycle.lock")
            }
            throw SecureStateError.systemCall("flock lifecycle.lock", code)
        }
        return LifecycleAdmissionAuthority(
            state: state,
            namespace: namespace,
            lifecycle: descriptor
        )
    }

    public func release() {
        lifecycle.closeNow()
        namespace.closeNow()
    }
}
