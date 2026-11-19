import Darwin
import Foundation

public struct ClosedProcessCommand: Equatable, Sendable {
    public static let inheritedReadDescriptorNumber:
        Int32 = 9
    public let executable: String
    public let arguments: [String]
    public let logicalExecutable: String
    public let logicalArguments: [String]
    public let inheritedReadDescriptor: Int32?

    public init(
        executable: String,
        arguments: [String],
        logicalExecutable: String? = nil,
        logicalArguments: [String]? = nil,
        inheritedReadDescriptor: Int32? = nil
    ) {
        self.executable = executable
        self.arguments = arguments
        self.logicalExecutable = logicalExecutable ?? executable
        self.logicalArguments = logicalArguments ?? arguments
        self.inheritedReadDescriptor =
            inheritedReadDescriptor
    }
}

public final class ClosedProcessRunner: @unchecked Sendable {
    private struct ReadDescriptorSnapshot:
        Equatable {
        let identity: FileIdentity
        let size: Int64
        let modifiedSeconds: Int64
        let modifiedNanoseconds: Int64
        let changedSeconds: Int64
        let changedNanoseconds: Int64
    }

    private let outputLimit: Int
    private let audit: CommandAudit?

    public init(
        outputLimit: Int = 16_777_216,
        audit: CommandAudit? = nil
    ) {
        self.outputLimit = outputLimit
        self.audit = audit
    }

    public func run(
        command: ClosedProcessCommand,
        environment: [String: String],
        workingDirectoryDescriptor: Int32,
        account: EffectiveAccount,
        timeout: TimeInterval,
        cancellation: CancellationToken
    ) throws -> ProcessResult {
        let executableIdentity = try Self.validateExecutable(
            command.executable,
            allowedOwners: [0, account.uid]
        )
        let inheritedIdentity = try command
            .inheritedReadDescriptor.map {
                try Self.validateReadDescriptor(
                    $0,
                    allowedOwners: [0, account.uid]
                )
            }
        try Self.validateEnvironment(environment, account: account)
        guard timeout > 0, timeout <= 300,
              !command.arguments.contains(where: {
                  $0.contains("\0")
              }) else {
            throw GitSafetyError.unsafeRepository(
                "closed process request is invalid"
            )
        }
        var out: [Int32] = [-1, -1]
        var err: [Int32] = [-1, -1]
        var gate: [Int32] = [-1, -1]
        guard pipe(&out) == 0, pipe(&err) == 0, pipe(&gate) == 0 else {
            Self.close(out + err + gate)
            throw SecureStateError.systemCall(
                "create closed process pipes",
                errno
            )
        }
        let outRead = out[0]
        let outWrite = out[1]
        let errRead = err[0]
        let errWrite = err[1]
        let gateRead = gate[0]
        let gateWrite = gate[1]
        defer {
            Self.close([outRead, errRead, gateRead])
        }
        for descriptor in [outRead, errRead] {
            let flags = fcntl(descriptor, F_GETFL)
            guard flags >= 0,
                  fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0 else {
                Self.close([outWrite, errWrite, gateWrite])
                throw SecureStateError.systemCall(
                    "configure closed process pipe",
                    errno
                )
            }
        }
        let null = Darwin.open(
            "/dev/null",
            O_RDONLY | O_CLOEXEC
        )
        guard null >= 0 else {
            Self.close([outWrite, errWrite, gateWrite])
            throw SecureStateError.systemCall("open /dev/null", errno)
        }
        defer { Darwin.close(null) }
        do {
            try cancellation.beginChildAdmission(
                startGateWrite: gateWrite
            )
        } catch {
            Self.close([outWrite, errWrite, gateWrite])
            throw error
        }
        audit?.record(CommandInvocation(
            executable: command.logicalExecutable,
            arguments: command.logicalArguments,
            environmentKeys: environment.keys.sorted(),
            spawnArguments: [command.executable] + command.arguments
        ))
        let pid: pid_t
        do {
            pid = try Self.spawnSuspended(
                command: command,
                environment: environment,
                workingDirectoryDescriptor:
                    workingDirectoryDescriptor,
                standardInput: null,
                standardOutput: outWrite,
                standardError: errWrite,
                inheritedReadDescriptor:
                    command.inheritedReadDescriptor
            )
        } catch {
            cancellation.childAdmissionFailed()
            Self.close([outWrite, errWrite])
            throw error
        }
        let published = cancellation.publishAndReleaseChild(
            processID: pid,
            leaseDescriptor: workingDirectoryDescriptor,
            executablePath: command.executable
        )
        Self.close([outWrite, errWrite])
        var executableDrift = false
        do {
            let observed = try Self.validateExecutable(
                command.executable,
                allowedOwners: [0, account.uid]
            )
            executableDrift = observed != executableIdentity
        } catch {
            executableDrift = true
        }
        var inheritedDescriptorDrift = false
        if let descriptor =
                command.inheritedReadDescriptor,
           let inheritedIdentity {
            do {
                inheritedDescriptorDrift =
                    try Self.validateReadDescriptor(
                        descriptor,
                        allowedOwners: [0, account.uid]
                    ) != inheritedIdentity
            } catch {
                inheritedDescriptorDrift = true
            }
        }
        if !published || executableDrift
            || inheritedDescriptorDrift {
            let signalled = cancellation.signalActive(
                processID: pid,
                signal: SIGKILL
            )
            // A suspended, unpublished child cannot have created
            // descendants. If identity publication failed, the exact
            // unreaped PID returned by posix_spawn remains safe to stop.
            if !signalled {
                _ = kill(pid, SIGKILL)
            }
        }
        // The final identity check must precede SIGCONT. If admission
        // failed, queue termination before allowing the suspended process
        // group to advance and be reaped.
        _ = kill(-pid, SIGCONT)

        let deadline = MonotonicDeadline(
            seconds: ChildProcessBudget.seconds(timeout)
        )
        var terminationDeadline: MonotonicDeadline?
        var sentKill = false
        var timedOut = false
        var waitStatus: Int32 = 0
        var reaped = false
        var stdout = Capture()
        var stderr = Capture()
        defer { cancellation.clear(processID: pid) }
        while !reaped {
            drain(outRead, into: &stdout)
            drain(errRead, into: &stderr)
            let waited = waitpid(pid, &waitStatus, WNOHANG)
            if waited == pid {
                reaped = true
                break
            }
            if waited < 0, errno != EINTR {
                throw SecureStateError.systemCall(
                    "waitpid closed process",
                    errno
                )
            }
            let stopping = cancellation.isCancelled
                || deadline.hasExpired
                || !published
            if deadline.hasExpired {
                timedOut = true
            }
            if stopping, terminationDeadline == nil {
                terminationDeadline = MonotonicDeadline(
                    seconds: ProcessOwnershipTiming.termGrace
                )
                _ = cancellation.signalActive(
                    processID: pid,
                    signal: SIGTERM
                )
            }
            if let terminationDeadline,
               terminationDeadline.hasExpired,
               !sentKill {
                _ = cancellation.signalActive(
                    processID: pid,
                    signal: SIGKILL
                )
                sentKill = true
            }
            var descriptors = [
                pollfd(
                    fd: outRead,
                    events: Int16(POLLIN | POLLHUP),
                    revents: 0
                ),
                pollfd(
                    fd: errRead,
                    events: Int16(POLLIN | POLLHUP),
                    revents: 0
                ),
            ]
            _ = poll(&descriptors, 2, 50)
        }
        drainUntilEOF(outRead, into: &stdout)
        drainUntilEOF(errRead, into: &stderr)
        do {
            executableDrift =
                try Self.validateExecutable(
                    command.executable,
                    allowedOwners: [0, account.uid]
                ) != executableIdentity
        } catch {
            executableDrift = true
        }
        if let descriptor =
                command.inheritedReadDescriptor,
           let inheritedIdentity {
            do {
                inheritedDescriptorDrift =
                    try Self.validateReadDescriptor(
                        descriptor,
                        allowedOwners: [0, account.uid]
                    ) != inheritedIdentity
            } catch {
                inheritedDescriptorDrift = true
            }
        }
        if executableDrift || inheritedDescriptorDrift {
            throw GitSafetyError.unsafeRepository(
                "closed executable or inherited input identity changed during admission"
            )
        }
        return ProcessResult(
            status: Self.decodedStatus(waitStatus),
            stdout: stdout.data,
            stderr: stderr.data,
            stdoutTruncated: stdout.truncated,
            stderrTruncated: stderr.truncated,
            outputByteLimit: outputLimit,
            timedOut: timedOut,
            cancelled: cancellation.isCancelled,
            terminationRequested:
                !published || terminationDeadline != nil,
            processID: pid
        )
    }

    public static func environment(
        account: EffectiveAccount,
        frozenConfigPath: String = "/dev/null"
    ) -> [String: String] {
        [
            "HOME": account.homeDirectory,
            "USER": account.username,
            "LOGNAME": account.username,
            "PATH": ClosedGitEnvironment.fixedPath,
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": "/private/tmp",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS": "/usr/bin/false",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_CONFIG_GLOBAL": frozenConfigPath,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_GRAFT_FILE": "/dev/null",
        ]
    }

    public static func awaEnvironment(
        account: EffectiveAccount
    ) -> [String: String] {
        var result = environment(account: account)
        result["AWA_POLICY"] =
            account.homeDirectory
                + "/dev/_ops/policy/worktree-policy.yml"
        result["AWA_GOVERNED_ROOT"] =
            account.homeDirectory + "/dev"
        return result
    }

    private static func validateEnvironment(
        _ environment: [String: String],
        account: EffectiveAccount
    ) throws {
        let required = Self.environment(account: account)
        let baseKeys = Set(required.keys)
        let awaKeys = Set([
            "AWA_POLICY",
            "AWA_GOVERNED_ROOT",
        ])
        let observedKeys = Set(environment.keys)
        let hasClosedAWAOverlay =
            observedKeys == baseKeys.union(awaKeys)
                && environment["AWA_POLICY"]
                    == account.homeDirectory
                        + "/dev/_ops/policy/worktree-policy.yml"
                && environment["AWA_GOVERNED_ROOT"]
                    == account.homeDirectory + "/dev"
        guard (
                observedKeys == baseKeys
                    || hasClosedAWAOverlay
              ),
              environment["HOME"] == account.homeDirectory,
              environment["USER"] == account.username,
              environment["LOGNAME"] == account.username,
              environment["PATH"] == ClosedGitEnvironment.fixedPath,
              environment["LANG"] == "C",
              environment["LC_ALL"] == "C",
              environment["TMPDIR"] == "/private/tmp",
              environment["GIT_TERMINAL_PROMPT"] == "0",
              environment["GIT_ASKPASS"] == "/usr/bin/false",
              environment["SSH_ASKPASS"] == "/usr/bin/false",
              environment["GIT_CONFIG_NOSYSTEM"] == "1",
              environment["GIT_NO_REPLACE_OBJECTS"] == "1",
              environment["GIT_GRAFT_FILE"] == "/dev/null",
              environment["GIT_CONFIG_GLOBAL"]?.hasPrefix("/") == true else {
            throw GitSafetyError.unsafeRepository(
                "closed process environment is invalid"
            )
        }
    }

    private static func validateExecutable(
        _ path: String,
        allowedOwners: Set<uid_t>
    ) throws -> FileIdentity {
        guard path.hasPrefix("/"),
              !path.contains("\n"),
              !path.contains("\r"),
              !path.contains("\0") else {
            throw GitSafetyError.unsafeRepository(
                "closed executable path is invalid"
            )
        }
        let descriptor = Darwin.open(
            path,
            O_RDONLY | O_NOFOLLOW | O_CLOEXEC
        )
        guard descriptor >= 0 else {
            throw SecureStateError.systemCall(
                "open closed executable",
                errno
            )
        }
        defer { Darwin.close(descriptor) }
        var opened = stat()
        var observed = stat()
        guard fstat(descriptor, &opened) == 0,
              lstat(path, &observed) == 0,
              FileIdentity(opened).isRegular,
              opened.st_dev == observed.st_dev,
              opened.st_ino == observed.st_ino,
              (
                opened.st_uid == 0
                    ? opened.st_nlink >= 1
                    : opened.st_nlink == 1
              ),
              allowedOwners.contains(opened.st_uid),
              (opened.st_mode & 0o022) == 0,
              (opened.st_mode & 0o111) != 0 else {
            throw GitSafetyError.unsafeRepository(
                "closed executable identity is unsafe"
            )
        }
        return FileIdentity(opened)
    }

    private static func validateReadDescriptor(
        _ descriptor: Int32,
        allowedOwners: Set<uid_t>
    ) throws -> ReadDescriptorSnapshot {
        var info = stat()
        let flags = fcntl(descriptor, F_GETFL)
        guard descriptor >= 0,
              flags >= 0,
              flags & O_ACCMODE == O_RDONLY,
              fstat(descriptor, &info) == 0,
              FileIdentity(info).isRegular,
              allowedOwners.contains(info.st_uid),
              (
                info.st_uid == 0
                    ? info.st_nlink >= 1
                    : info.st_nlink == 1
              ),
              (info.st_mode & 0o022) == 0,
              info.st_size >= 0,
              info.st_size <= 16_777_216 else {
            throw GitSafetyError.unsafeRepository(
                "closed inherited input is unsafe"
            )
        }
        return ReadDescriptorSnapshot(
            identity: FileIdentity(info),
            size: Int64(info.st_size),
            modifiedSeconds:
                Int64(info.st_mtimespec.tv_sec),
            modifiedNanoseconds:
                Int64(info.st_mtimespec.tv_nsec),
            changedSeconds:
                Int64(info.st_ctimespec.tv_sec),
            changedNanoseconds:
                Int64(info.st_ctimespec.tv_nsec)
        )
    }

    private static func spawnSuspended(
        command: ClosedProcessCommand,
        environment: [String: String],
        workingDirectoryDescriptor: Int32,
        standardInput: Int32,
        standardOutput: Int32,
        standardError: Int32,
        inheritedReadDescriptor: Int32?
    ) throws -> pid_t {
        var actions: posix_spawn_file_actions_t?
        var attributes: posix_spawnattr_t?
        guard posix_spawn_file_actions_init(&actions) == 0,
              posix_spawnattr_init(&attributes) == 0 else {
            throw SecureStateError.systemCall(
                "initialize closed process spawn",
                errno
            )
        }
        defer {
            posix_spawn_file_actions_destroy(&actions)
            posix_spawnattr_destroy(&attributes)
        }
        var code = posix_spawn_file_actions_addfchdir(
            &actions,
            workingDirectoryDescriptor
        )
        if code == 0 {
            code = posix_spawn_file_actions_adddup2(
                &actions,
                standardInput,
                STDIN_FILENO
            )
        }
        if code == 0 {
            code = posix_spawn_file_actions_adddup2(
                &actions,
                standardOutput,
                STDOUT_FILENO
            )
        }
        if code == 0 {
            code = posix_spawn_file_actions_adddup2(
                &actions,
                standardError,
                STDERR_FILENO
            )
        }
        if code == 0,
           let inheritedReadDescriptor {
            code = posix_spawn_file_actions_adddup2(
                &actions,
                inheritedReadDescriptor,
                ClosedProcessCommand
                    .inheritedReadDescriptorNumber
            )
        }
        guard code == 0 else {
            throw SecureStateError.systemCall(
                "configure closed process spawn",
                code
            )
        }
        let flags = Int16(
            POSIX_SPAWN_SETPGROUP
                | POSIX_SPAWN_CLOEXEC_DEFAULT
                | POSIX_SPAWN_START_SUSPENDED
        )
        code = posix_spawnattr_setflags(&attributes, flags)
        if code == 0 {
            code = posix_spawnattr_setpgroup(&attributes, 0)
        }
        guard code == 0 else {
            throw SecureStateError.systemCall(
                "configure closed process group",
                code
            )
        }
        let argv = [command.executable] + command.arguments
        let env = environment.keys.sorted().map {
            "\($0)=\(environment[$0]!)"
        }
        return try withCStringArray(argv) { arguments in
            try withCStringArray(env) { environment in
                var pid: pid_t = 0
                let result = posix_spawn(
                    &pid,
                    command.executable,
                    &actions,
                    &attributes,
                    arguments,
                    environment
                )
                guard result == 0 else {
                    throw SecureStateError.systemCall(
                        "spawn closed process",
                        result
                    )
                }
                return pid
            }
        }
    }

    private struct Capture {
        var data = Data()
        var truncated = false
    }

    private func drain(_ fd: Int32, into capture: inout Capture) {
        var bytes = [UInt8](repeating: 0, count: 8_192)
        while true {
            let count = Darwin.read(fd, &bytes, bytes.count)
            if count > 0 {
                let remaining = max(
                    0,
                    outputLimit - capture.data.count
                )
                capture.data.append(
                    contentsOf: bytes.prefix(min(count, remaining))
                )
                if count > remaining {
                    capture.truncated = true
                }
                continue
            }
            if count < 0, errno == EINTR {
                continue
            }
            return
        }
    }

    private func drainUntilEOF(
        _ fd: Int32,
        into capture: inout Capture
    ) {
        for _ in 0..<20 {
            let before = capture.data.count
            drain(fd, into: &capture)
            if capture.data.count == before {
                var descriptor = pollfd(
                    fd: fd,
                    events: Int16(POLLIN | POLLHUP),
                    revents: 0
                )
                let result = poll(&descriptor, 1, 10)
                if result <= 0
                    || (descriptor.revents & Int16(POLLHUP)) != 0 {
                    drain(fd, into: &capture)
                    return
                }
            }
        }
    }

    private static func decodedStatus(_ status: Int32) -> Int32 {
        if (status & 0x7F) == 0 {
            return (status >> 8) & 0xFF
        }
        return 128 + (status & 0x7F)
    }

    private static func close(_ descriptors: [Int32]) {
        for descriptor in descriptors where descriptor >= 0 {
            Darwin.close(descriptor)
        }
    }

    private static func withCStringArray<T>(
        _ values: [String],
        _ body: (UnsafeMutablePointer<
            UnsafeMutablePointer<CChar>?
        >) throws -> T
    ) rethrows -> T {
        var storage = values.map { strdup($0) }
        storage.append(nil)
        defer {
            for pointer in storage where pointer != nil {
                free(pointer)
            }
        }
        return try storage.withUnsafeMutableBufferPointer {
            try body($0.baseAddress!)
        }
    }
}
