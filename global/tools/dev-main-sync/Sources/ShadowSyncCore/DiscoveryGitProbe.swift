import Darwin
import Foundation

struct DiscoveryGitProbe: Sendable {
    let account: EffectiveAccount
    #if SHADOW_SYNC_TESTING
    let observer: (@Sendable ([String]) -> Void)?
    let candidateObserver: (@Sendable (String, [String]) -> Void)?
    let processObserver: (@Sendable (ProcessIdentity) -> Void)?
    let injectWaitError: Bool
    #endif

    init(account: EffectiveAccount) {
        self.account = account
        #if SHADOW_SYNC_TESTING
        observer = nil
        candidateObserver = nil
        processObserver = nil
        injectWaitError = false
        #endif
    }

    #if SHADOW_SYNC_TESTING
    init(
        account: EffectiveAccount,
        observer: (@Sendable ([String]) -> Void)?,
        candidateObserver: (@Sendable (String, [String]) -> Void)? = nil,
        processObserver: (@Sendable (ProcessIdentity) -> Void)? = nil,
        injectWaitError: Bool = false
    ) {
        self.account = account
        self.observer = observer
        self.candidateObserver = candidateObserver
        self.processObserver = processObserver
        self.injectWaitError = injectWaitError
    }
    #endif

    func validate(
        _ candidate: RepositoryCandidate
    ) throws -> LocalRepositoryInspection {
        let retainedHandle = try RepositoryHandle.open(candidate)
        try retainedHandle.revalidate()
        do {
            try retainedHandle.rejectBusyState()
        } catch GitSafetyError.busy {
            return LocalRepositoryInspection(
                localMainCommit: nil,
                cachedMainRelation: .unavailable,
                block: .busy
            )
        }
        _ = try validateCloneOrigin(candidate)

        try retainedHandle.revalidate()
        let noLinkedWorktrees =
            try retainedHandle.verifyNoRegisteredLinkedWorktrees()
        let inspection = try LocalRepositoryInspection.inspect(
            handle: retainedHandle,
            knownNoLinkedWorktrees: noLinkedWorktrees
        ) { arguments in
            let result = try run(
                candidate: candidate,
                arguments: arguments
            )
            return LocalRepositoryCommandResult(
                status: result.status,
                stdout: result.stdout,
                stdoutTruncated: false,
                diagnostic: result.diagnostic
            )
        }
        if noLinkedWorktrees {
            guard try retainedHandle
                    .verifyNoRegisteredLinkedWorktrees() else {
                throw GitSafetyError.unsafeRepository(
                    "worktree topology changed during discovery"
                )
            }
        }
        try retainedHandle.revalidate()
        return inspection
    }

    func validateCloneOrigin(
        _ candidate: RepositoryCandidate
    ) throws -> String {
        let retainedHandle = try RepositoryHandle.open(candidate)
        try retainedHandle.revalidate()
        guard let rawIdentity = GitHubIdentity.parse(candidate.rawOrigin),
              candidate.originIdentity == rawIdentity,
              candidate.id.lowercased() == rawIdentity.canonicalName else {
            throw GitSafetyError.originChanged
        }
        let effectiveURL = try run(
            candidate: candidate,
            arguments: [
                "--no-replace-objects", "--no-lazy-fetch",
                "remote", "get-url", "--all", "origin",
            ],
            captureTransportConfiguration: true
        )
        guard effectiveURL.status == 0 else {
            throw GitSafetyError.commandFailed(
                "discovery Git probe",
                effectiveURL.status,
                effectiveURL.diagnostic
            )
        }
        guard let effectiveText = String(
            data: effectiveURL.stdout,
            encoding: .utf8
        ), !effectiveText.contains("\r") else {
            throw GitSafetyError.unsafeRepository(
                "discovery Git output is malformed"
            )
        }
        let effectiveLines = effectiveText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
        guard effectiveLines.count == 1,
              let effectiveIdentity = GitHubIdentity.parse(effectiveLines[0]),
              effectiveIdentity.canonicalName == rawIdentity.canonicalName else {
            throw GitSafetyError.originChanged
        }
        try EffectiveTransportConfiguration.validate(
            status: effectiveURL.transportConfiguration.isEmpty ? 1 : 0,
            output: effectiveURL.transportConfiguration,
            transport: effectiveIdentity.transport,
            operation: "discovery Git transport config probe",
            diagnostic: effectiveURL.diagnostic
        )
        try retainedHandle.revalidate()
        return effectiveLines[0]
    }

    struct Result {
        let status: Int32
        let stdout: Data
        let transportConfiguration: Data
        let diagnostic: String
    }

    func run(
        candidate: RepositoryCandidate,
        workingPath: String? = nil,
        arguments: [String],
        timeoutSeconds: TimeInterval = 5,
        captureTransportConfiguration: Bool = false
    ) throws -> Result {
        _ = try GitCommandPolicy.validate(arguments)
        #if SHADOW_SYNC_TESTING
        observer?(arguments)
        candidateObserver?(candidate.path, arguments)
        #endif
        var environment = [
            "HOME": account.homeDirectory,
            "USER": account.username,
            "LOGNAME": account.username,
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS": "/usr/bin/false",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "include.path",
            "GIT_CONFIG_VALUE_0": "/dev/fd/197",
        ]
        if captureTransportConfiguration {
            environment["GIT_TRACE2_EVENT"] = "/dev/fd/199"
            environment["GIT_TRACE2_CONFIG_PARAMS"] =
                "remote.origin.uploadpack,core.sshcommand"
        }
        var stdoutPipe: [Int32] = [-1, -1]
        var stderrPipe: [Int32] = [-1, -1]
        var tracePipe: [Int32] = [-1, -1]
        guard pipe(&stdoutPipe) == 0,
              pipe(&stderrPipe) == 0,
              pipe(&tracePipe) == 0 else {
            closeDiscoveryDescriptors(stdoutPipe + stderrPipe + tracePipe)
            throw SecureStateError.systemCall("pipe discovery Git output", errno)
        }
        let stdoutRead = stdoutPipe[0]
        let stdoutWrite = stdoutPipe[1]
        let stderrRead = stderrPipe[0]
        let stderrWrite = stderrPipe[1]
        let traceRead = tracePipe[0]
        let traceWrite = tracePipe[1]
        defer {
            close(stdoutRead)
            close(stderrRead)
            close(traceRead)
        }
        for descriptor in [stdoutRead, stderrRead, traceRead] {
            let flags = fcntl(descriptor, F_GETFL)
            guard flags >= 0,
                  fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0 else {
                let code = errno
                close(stdoutWrite)
                close(stderrWrite)
                close(traceWrite)
                throw SecureStateError.systemCall(
                    "fcntl discovery Git output",
                    code
                )
            }
        }
        let retainedHandle = try RepositoryHandle.open(candidate)
        let requestedWorkingPath = workingPath ?? candidate.path
        let expectedWorkingIdentity: RepositoryDirectoryIdentity
        if let workingPath {
            expectedWorkingIdentity = try retainedHandle
                .verifyWorktreeClaim(path: workingPath).rootIdentity
        } else if let rootIdentity = candidate.rootIdentity {
            expectedWorkingIdentity = rootIdentity
        } else {
            throw GitSafetyError.unsafeRepository(
                "discovery working root lacks identity"
            )
        }
        let directoryDescriptor = try RepositoryRootPathIdentity
            .withVerifiedDirectory(
                path: requestedWorkingPath,
                expected: expectedWorkingIdentity
            ) { opened -> Int32 in
                let retained = fcntl(
                    opened.descriptor,
                    F_DUPFD_CLOEXEC,
                    0
                )
                guard retained >= 0 else {
                    throw SecureStateError.systemCall(
                        "retain discovery Git directory",
                        errno
                    )
                }
                return retained
            }
        guard directoryDescriptor >= 0 else {
            close(stdoutWrite)
            close(stderrWrite)
            close(traceWrite)
            throw SecureStateError.systemCall("open discovery Git directory", errno)
        }
        defer { close(directoryDescriptor) }
        let nullDescriptor = Darwin.open("/dev/null", O_RDONLY | O_CLOEXEC)
        guard nullDescriptor >= 0 else {
            close(stdoutWrite)
            close(stderrWrite)
            close(traceWrite)
            throw SecureStateError.systemCall("open discovery Git stdin", errno)
        }
        defer { close(nullDescriptor) }
        var startGate: [Int32] = [-1, -1]
        guard pipe(&startGate) == 0,
              fcntl(startGate[0], F_SETFD, FD_CLOEXEC) == 0,
              fcntl(startGate[1], F_SETFD, FD_CLOEXEC) == 0 else {
            let code = errno
            closeDiscoveryDescriptors(startGate)
            close(stdoutWrite)
            close(stderrWrite)
            close(traceWrite)
            throw SecureStateError.systemCall("pipe discovery Git start gate", code)
        }

        let processID: pid_t
        do {
            processID = try spawnDiscoveryGit(
                arguments: arguments,
                environment: environment,
                directoryDescriptor: directoryDescriptor,
                inputDescriptor: nullDescriptor,
                outputDescriptor: stdoutWrite,
                errorDescriptor: stderrWrite,
                traceDescriptor: traceWrite,
                startGateDescriptor: startGate[0]
            )
        } catch {
            closeDiscoveryDescriptors(startGate)
            close(stdoutWrite)
            close(stderrWrite)
            close(traceWrite)
            throw error
        }
        close(startGate[0])
        let processGeneration = RunIdentity.make()
        let processIdentity: ProcessIdentity
        do {
            processIdentity = try ProcessIdentity.capture(
                processID: processID,
                generation: processGeneration,
                expectedExecutablePath: "/usr/bin/git"
            )
            #if SHADOW_SYNC_TESTING
            processObserver?(processIdentity)
            #endif
        } catch {
            var refusal = Array("[\n".utf8)
            _ = Darwin.write(startGate[1], &refusal, refusal.count)
            close(startGate[1])
            close(stdoutWrite)
            close(stderrWrite)
            close(traceWrite)
            var blockedStatus: Int32 = 0
            while waitpid(processID, &blockedStatus, 0) < 0, errno == EINTR {}
            throw error
        }
        close(startGate[1])
        close(stdoutWrite)
        close(stderrWrite)
        close(traceWrite)

        var outputData = Data()
        var errorData = Data()
        var traceData = Data()
        var outputOverflow = false
        var errorOverflow = false
        var traceOverflow = false
        let deadline = MonotonicDeadline(
            seconds: ChildProcessBudget.seconds(
                min(max(timeoutSeconds, 0.1), 15)
            )
        )
        var waitStatus: Int32 = 0
        #if SHADOW_SYNC_TESTING
        var shouldInjectWaitError = injectWaitError
        #endif
        while true {
            drainDiscoveryOutput(
                stdoutRead,
                into: &outputData,
                limit: 1_048_576,
                overflow: &outputOverflow
            )
            drainDiscoveryOutput(
                stderrRead,
                into: &errorData,
                limit: 262_144,
                overflow: &errorOverflow
            )
            drainDiscoveryOutput(
                traceRead,
                into: &traceData,
                limit: 262_144,
                overflow: &traceOverflow
            )
            let waited: pid_t
            #if SHADOW_SYNC_TESTING
            if shouldInjectWaitError {
                shouldInjectWaitError = false
                waited = -1
                errno = EIO
            } else {
                waited = waitpid(processID, &waitStatus, WNOHANG)
            }
            #else
            waited = waitpid(processID, &waitStatus, WNOHANG)
            #endif
            if waited == processID {
                break
            }
            if waited < 0, errno != EINTR {
                let code = errno
                try cleanupDiscoveryChild(
                    processID: processID,
                    identity: processIdentity
                )
                throw SecureStateError.systemCall("waitpid discovery Git", code)
            }
            if deadline.hasExpired {
                try cleanupDiscoveryChild(
                    processID: processID,
                    identity: processIdentity
                )
                throw GitSafetyError.commandFailed("discovery Git timeout", 124, "")
            }
            var descriptors = [
                pollfd(fd: stdoutRead, events: Int16(POLLIN | POLLHUP), revents: 0),
                pollfd(fd: stderrRead, events: Int16(POLLIN | POLLHUP), revents: 0),
            ]
            _ = poll(&descriptors, 2, 2)
        }
        drainDiscoveryOutput(
            stdoutRead,
            into: &outputData,
            limit: 1_048_576,
            overflow: &outputOverflow
        )
        drainDiscoveryOutput(
            stderrRead,
            into: &errorData,
            limit: 262_144,
            overflow: &errorOverflow
        )
        drainDiscoveryOutput(
            traceRead,
            into: &traceData,
            limit: 262_144,
            overflow: &traceOverflow
        )
        guard !outputOverflow, !errorOverflow, !traceOverflow else {
            throw GitSafetyError.unsafeRepository(
                "discovery Git output exceeded its bound"
            )
        }
        try retainedHandle.revalidate()
        if let workingPath {
            _ = try retainedHandle.verifyWorktreeClaim(path: workingPath)
        }
        return Result(
            status: decodedDiscoveryStatus(waitStatus),
            stdout: outputData,
            transportConfiguration:
                captureTransportConfiguration
                    ? try transportConfigurationOutput(from: traceData)
                    : Data(),
            diagnostic: Redactor.sanitize(
                String(decoding: errorData, as: UTF8.self)
            )
        )
    }
}

private func transportConfigurationOutput(from trace: Data) throws -> Data {
    guard !trace.isEmpty, trace.last == 0x0A else {
        throw GitSafetyError.malformedConfig(
            "effective transport trace is incomplete"
        )
    }
    var observedVersion = false
    var names: Set<String> = []
    for line in trace.split(separator: 0x0A, omittingEmptySubsequences: true) {
        guard let value = try JSONSerialization.jsonObject(with: Data(line))
                as? [String: Any],
              let event = value["event"] as? String else {
            throw GitSafetyError.malformedConfig(
                "effective transport trace is malformed"
            )
        }
        if event == "version" {
            observedVersion = true
        }
        guard event == "def_param" else { continue }
        guard let parameter = value["param"] as? String else {
            throw GitSafetyError.malformedConfig(
                "effective transport trace parameter is malformed"
            )
        }
        let normalized = parameter.lowercased()
        if normalized == "remote.origin.uploadpack"
            || normalized == "core.sshcommand" {
            names.insert(normalized)
        }
    }
    guard observedVersion else {
        throw GitSafetyError.malformedConfig(
            "effective transport trace was not activated"
        )
    }
    var output = Data()
    for name in names.sorted() {
        output.append(Data(name.utf8))
        output.append(0)
    }
    return output
}

private func cleanupDiscoveryChild(
    processID: pid_t,
    identity: ProcessIdentity
) throws {
    var status: Int32 = 0
    let initial = waitpid(processID, &status, WNOHANG)
    if initial == processID || (initial < 0 && errno == ECHILD) {
        return
    }
    guard initial == 0 || (initial < 0 && errno == EINTR) else {
        throw SecureStateError.systemCall("waitpid discovery cleanup", errno)
    }
    guard identity.isCurrent(expectedGeneration: identity.generation),
          OwnedProcessSignal.send(
              SIGTERM,
              to: identity,
              expectedGeneration: identity.generation
          ) else {
        if !identity.isCurrent(expectedGeneration: identity.generation) {
            try reapExitedDiscoveryChild(processID: processID, status: &status)
            return
        }
        throw ProcessOwnershipError.unverifiedOwner
    }
    let termDeadline = MonotonicDeadline(seconds: ProcessOwnershipTiming.termGrace)
    while !termDeadline.hasExpired {
        let waited = waitpid(processID, &status, WNOHANG)
        if waited == processID || (waited < 0 && errno == ECHILD) {
            return
        }
        if waited < 0, errno != EINTR {
            throw SecureStateError.systemCall("waitpid discovery TERM", errno)
        }
        usleep(20_000)
    }
    guard identity.isCurrent(expectedGeneration: identity.generation),
          OwnedProcessSignal.send(
              SIGKILL,
              to: identity,
              expectedGeneration: identity.generation
          ) else {
        if !identity.isCurrent(expectedGeneration: identity.generation) {
            try reapExitedDiscoveryChild(processID: processID, status: &status)
            return
        }
        throw ProcessOwnershipError.unverifiedOwner
    }
    let killDeadline = MonotonicDeadline(seconds: ProcessOwnershipTiming.postKillReap)
    while !killDeadline.hasExpired {
        let waited = waitpid(processID, &status, WNOHANG)
        if waited == processID || (waited < 0 && errno == ECHILD) {
            return
        }
        if waited < 0, errno != EINTR {
            throw SecureStateError.systemCall("waitpid discovery KILL", errno)
        }
        usleep(20_000)
    }
    throw ProcessOwnershipError.unavailable("discovery Git child reap")
}

private func reapExitedDiscoveryChild(
    processID: pid_t,
    status: inout Int32
) throws {
    let deadline = MonotonicDeadline(seconds: ProcessOwnershipTiming.postKillReap)
    while !deadline.hasExpired {
        let waited = waitpid(processID, &status, WNOHANG)
        if waited == processID || (waited < 0 && errno == ECHILD) {
            return
        }
        if waited < 0, errno != EINTR {
            throw SecureStateError.systemCall("waitpid discovery exited child", errno)
        }
        usleep(20_000)
    }
    throw ProcessOwnershipError.unavailable("discovery exited child reap")
}

private func spawnDiscoveryGit(
    arguments: [String],
    environment: [String: String],
    directoryDescriptor: Int32,
    inputDescriptor: Int32,
    outputDescriptor: Int32,
    errorDescriptor: Int32,
    traceDescriptor: Int32,
    startGateDescriptor: Int32
) throws -> pid_t {
    var actions: posix_spawn_file_actions_t?
    var attributes: posix_spawnattr_t?
    guard posix_spawn_file_actions_init(&actions) == 0,
          posix_spawnattr_init(&attributes) == 0 else {
        throw SecureStateError.systemCall("posix_spawn discovery Git init", errno)
    }
    defer {
        posix_spawn_file_actions_destroy(&actions)
        posix_spawnattr_destroy(&attributes)
    }
    var code = posix_spawn_file_actions_addfchdir(&actions, directoryDescriptor)
    if code == 0 {
        code = posix_spawn_file_actions_adddup2(
            &actions, inputDescriptor, STDIN_FILENO
        )
    }
    if code == 0 {
        code = posix_spawn_file_actions_adddup2(
            &actions, outputDescriptor, STDOUT_FILENO
        )
    }
    if code == 0 {
        code = posix_spawn_file_actions_adddup2(
            &actions, errorDescriptor, STDERR_FILENO
        )
    }
    if code == 0 {
        code = posix_spawn_file_actions_adddup2(
            &actions,
            startGateDescriptor,
            197
        )
    }
    if code == 0 {
        code = posix_spawn_file_actions_adddup2(
            &actions,
            traceDescriptor,
            199
        )
    }
    guard code == 0 else {
        throw SecureStateError.systemCall(
            "posix_spawn discovery Git file action",
            code
        )
    }
    let flags = Int16(POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT)
    code = posix_spawnattr_setflags(&attributes, flags)
    if code == 0 {
        code = posix_spawnattr_setpgroup(&attributes, 0)
    }
    guard code == 0 else {
        throw SecureStateError.systemCall(
            "posix_spawn discovery Git attributes",
            code
        )
    }
    return try withDiscoveryCStringArray(["/usr/bin/git"] + arguments) { argv in
        try withDiscoveryCStringArray(
            environment.keys.sorted().map { "\($0)=\(environment[$0]!)" }
        ) { envp in
            for attempt in 0..<4 {
                var processID: pid_t = 0
                let spawnCode = posix_spawn(
                    &processID,
                    "/usr/bin/git",
                    &actions,
                    &attributes,
                    argv,
                    envp
                )
                if spawnCode == 0 {
                    return processID
                }
                guard spawnCode == EAGAIN, attempt < 3 else {
                    throw SecureStateError.systemCall(
                        "posix_spawn discovery Git",
                        spawnCode
                    )
                }
                usleep(10_000)
            }
            throw SecureStateError.systemCall("posix_spawn discovery Git", EAGAIN)
        }
    }
}

private func drainDiscoveryOutput(
    _ descriptor: Int32,
    into data: inout Data,
    limit: Int,
    overflow: inout Bool
) {
    var bytes = [UInt8](repeating: 0, count: 4_096)
    while true {
        let count = Darwin.read(descriptor, &bytes, bytes.count)
        if count > 0 {
            let remaining = max(0, limit - data.count)
            if remaining > 0 {
                data.append(contentsOf: bytes.prefix(min(count, remaining)))
            }
            if count > remaining {
                overflow = true
            }
            continue
        }
        if count < 0, errno == EINTR {
            continue
        }
        return
    }
}

private func decodedDiscoveryStatus(_ status: Int32) -> Int32 {
    if (status & 0x7F) == 0 {
        return (status >> 8) & 0xFF
    }
    return 128 + (status & 0x7F)
}

private func closeDiscoveryDescriptors(_ descriptors: [Int32]) {
    for descriptor in descriptors where descriptor >= 0 {
        close(descriptor)
    }
}

private func withDiscoveryCStringArray<T>(
    _ strings: [String],
    _ body: (UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>) throws -> T
) rethrows -> T {
    let pointers = strings.map { strdup($0) }
    defer {
        for pointer in pointers {
            free(pointer)
        }
    }
    var mutable = pointers + [nil]
    return try mutable.withUnsafeMutableBufferPointer {
        try body($0.baseAddress!)
    }
}
