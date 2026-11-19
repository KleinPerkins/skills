#if SHADOW_SYNC_TESTING
import Darwin
import Foundation

public enum M4SelfTestRunner {
    public static func runAll(
        onPass: (String) -> Void = { _ in }
    ) throws -> [String] {
        signal(SIGPIPE, SIG_IGN)
        let tests: [(String, () throws -> Void)] = [
            ("m4-fixed-cancellation-bounds", testCancellationBounds),
            ("m4-process-identity-signal-proof", testProcessIdentitySignalProof),
            ("m4-term-kill-nested-reap", testTermKillAndNestedReap),
            ("m4-launcher-host-challenge", testLauncherAndHostChallenge),
            ("m4-host-control-rejections", testHostControlRejections),
            ("m4-host-control-client-bounds", testHostControlClientBounds),
            ("m4-stale-socket-refusal", testStaleSocketRefusal),
            ("m4-surviving-operation-recovery-block", testRecoveryBlocking),
            ("m4-interrupted-reconstruction", testInterruptedReconstruction),
            ("m4-log-intent-control-framing", testLogIntentControlFraming),
        ]
        var completed: [String] = []
        for (name, test) in tests {
            do {
                try test()
                completed.append(name)
                onPass(name)
            } catch {
                throw M4SelfTestError.failed(name, String(describing: error))
            }
        }
        return completed
    }

    private static func testCancellationBounds() throws {
        var machine = CancellationEscalationStateMachine(requestedAt: 100)
        try check(
            machine.nextAction(at: 101.999, ownerVerified: true) == .waitForCooperation,
            "cooperative acknowledgement ended early"
        )
        try check(
            machine.nextAction(at: 102, ownerVerified: true) == .sendTerm,
            "TERM was not sent at two seconds"
        )
        try check(
            machine.nextAction(at: 106.999, ownerVerified: true) == .waitForCooperation,
            "TERM grace ended early"
        )
        try check(
            machine.nextAction(at: 107, ownerVerified: true) == .sendKill,
            "KILL was not sent after five seconds"
        )
        try check(
            machine.nextAction(at: 108.999, ownerVerified: true) == .waitForCooperation,
            "post-KILL reap ended early"
        )
        try check(
            machine.nextAction(at: 109, ownerVerified: true) == .needsAttention,
            "surviving holder did not require attention"
        )
        var unverified = CancellationEscalationStateMachine(requestedAt: 0)
        try check(
            unverified.nextAction(at: 30, ownerVerified: false) == .needsAttention,
            "unverified owner was eligible for signalling"
        )
        let repeated = CancellationToken()
        repeated.cancel()
        repeated.cancel()
        try check(repeated.isCancelled, "repeated cancellation lost terminal state")
    }

    private static func testProcessIdentitySignalProof() throws {
        let readiness = try M4TemporaryDirectory()
        let ready = readiness.path + "/identity-ready"
        let child = try spawnGroup(
            script: "trap 'exit 0' TERM; : > '\(ready)'; while :; do sleep 1; done"
        )
        defer { forceReap(child) }
        try waitForReadiness(at: ready, processID: child)
        let identity = try ProcessIdentity.capture(
            processID: child,
            generation: RunIdentity.make()
        )
        try check(identity.processGroupID == child, "child is not its group leader")
        try check(
            !OwnedProcessSignal.send(
                SIGTERM,
                to: identity,
                expectedGeneration: RunIdentity.make()
            ),
            "generation mismatch was signalled"
        )
        try check(kill(child, 0) == 0, "unverified signal changed the unrelated child")
        try check(
            OwnedProcessSignal.send(
                SIGTERM,
                to: identity,
                expectedGeneration: identity.generation
            ),
            "verified cooperative signal was refused"
        )
        _ = wait(child, timeout: 2)
        try check(
            !identity.isCurrent(expectedGeneration: identity.generation),
            "reaped PID retained stale authority"
        )
    }

    private static func testTermKillAndNestedReap() throws {
        let readiness = try M4TemporaryDirectory()
        let responsiveReady = readiness.path + "/responsive-ready"
        let responsive = try spawnGroup(
            script: "trap 'exit 0' TERM; sleep 30 & : > '\(responsiveReady)'; while :; do sleep 1; done"
        )
        defer { forceReap(responsive) }
        try waitForReadiness(at: responsiveReady, processID: responsive)
        let responsiveIdentity: ProcessIdentity
        do {
            responsiveIdentity = try ProcessIdentity.capture(
                processID: responsive,
                generation: RunIdentity.make()
            )
        } catch {
            throw M4SelfTestError.message(
                "responsive identity capture failed: \(error)"
            )
        }
        try check(
            OwnedProcessSignal.send(
                SIGTERM,
                to: responsiveIdentity,
                expectedGeneration: responsiveIdentity.generation
            ),
            "responsive group TERM failed"
        )
        try check(wait(responsive, timeout: 2) != nil, "responsive group was not reaped")
        try check(groupGone(responsive), "responsive nested group survived")

        let stubbornReady = readiness.path + "/stubborn-ready"
        let stubborn = try spawnGroup(
            script: "exec /usr/bin/python3 -c 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); open(\"\(stubbornReady)\", \"w\").close(); time.sleep(30)'"
        )
        defer { forceReap(stubborn) }
        try waitForReadiness(at: stubbornReady, processID: stubborn)
        let stubbornIdentity: ProcessIdentity
        do {
            stubbornIdentity = try ProcessIdentity.capture(
                processID: stubborn,
                generation: RunIdentity.make()
            )
        } catch {
            throw M4SelfTestError.message(
                "stubborn identity capture failed: \(error)"
            )
        }
        try check(
            OwnedProcessSignal.send(
                SIGTERM,
                to: stubbornIdentity,
                expectedGeneration: stubbornIdentity.generation
            ),
            "stubborn group TERM failed"
        )
        usleep(150_000)
        try check(kill(stubborn, 0) == 0, "stubborn group did not exercise escalation")
        let reverified: ProcessIdentity
        do {
            reverified = try ProcessIdentity.capture(
                processID: stubborn,
                generation: stubbornIdentity.generation
            )
        } catch {
            throw M4SelfTestError.message(
                "stubborn identity revalidation failed: \(error)"
            )
        }
        try check(
            reverified.startSeconds == stubbornIdentity.startSeconds
                && reverified.startMicroseconds == stubbornIdentity.startMicroseconds
                && reverified.processGroupID == stubbornIdentity.processGroupID,
            "stubborn group identity changed before KILL"
        )
        try check(
            OwnedProcessSignal.send(
                SIGKILL,
                to: reverified,
                expectedGeneration: stubbornIdentity.generation
            ),
            "stubborn group KILL failed"
        )
        try check(wait(stubborn, timeout: 2) != nil, "stubborn group was not reaped")
        try check(groupGone(stubborn), "stubborn nested group survived")
    }

    private static func testLauncherAndHostChallenge() throws {
        let temporary = try M4TemporaryDirectory()
        let location = try StateLocation.isolated(root: temporary.path)
        let authority = try LauncherAuthority.acquire(at: location)
        do {
            _ = try LauncherAuthority.acquire(at: location)
            throw M4SelfTestError.message("second launcher acquired ownership")
        } catch SecureStateError.contention {
            // Expected.
        }
        let activated = DispatchSemaphore(value: 0)
        let server = try HostControlServer(
            authority: authority,
            executablePath: CommandLine.arguments[0],
            onActivation: {
                activated.signal()
                return true
            }
        )
        try server.start()
        defer { server.stop() }
        try HostControlClient.activate(at: location)
        try check(
            activated.wait(timeout: .now() + 2) == .success,
            "same-UID activation was not routed"
        )
        let state = try SecureStateDirectory.open(location)
        let registration = try HostRegistrationStore.read(state: state)
        try check(registration.isValid, "live host registration was not verified")
    }

    private static func testHostControlRejections() throws {
        let temporary = try M4TemporaryDirectory()
        let location = try StateLocation.isolated(root: temporary.path)
        let authority = try LauncherAuthority.acquire(at: location)
        let server = try HostControlServer(
            authority: authority,
            executablePath: CommandLine.arguments[0],
            onActivation: { true }
        )
        try server.start()
        defer { server.stop() }
        let state = try SecureStateDirectory.open(location)
        let registration = try HostRegistrationStore.read(state: state)

        let malformed = try rawHostExchange(
            location: location,
            request: Data("{bad}\n".utf8)
        )
        let malformedResponse = try decodedHostResponse(malformed)
        try check(
            !malformedResponse.accepted,
            "malformed activation lacked a generic rejection"
        )

        let wrongRequest = HostControlRequest(
            expectedGeneration: RunIdentity.make()
        )
        var wrongBytes = try JSONEncoder().encode(wrongRequest)
        wrongBytes.append(0x0A)
        let wrong = try decodedHostResponse(
            rawHostExchange(location: location, request: wrongBytes)
        )
        try check(!wrong.accepted, "wrong generation was accepted")
        try check(wrong.nonce == wrongRequest.nonce, "rejection nonce changed")

        let partialStarted = MonotonicInstant.now()
        let partial = try rawHostExchange(
            location: location,
            request: Data(#"{"schema":"partial""#.utf8),
            keepWriteOpen: true
        )
        let partialResponse = try decodedHostResponse(partial)
        try check(
            !partialResponse.accepted,
            "partial request was accepted"
        )
        try check(
            MonotonicInstant.now().milliseconds(since: partialStarted) < 2_000,
            "partial request did not complete within its bound"
        )

        let oversized = try rawHostExchange(
            location: location,
            request: Data(repeating: UInt8(ascii: "x"), count: 17_000)
        )
        let oversizedResponse = try decodedHostResponse(oversized)
        try check(
            !oversizedResponse.accepted,
            "oversized request was accepted"
        )
        try check(registration.isValid, "rejected request invalidated live host")
    }

    private static func testHostControlClientBounds() throws {
        enum Behavior {
            case silent
            case partial
            case eof
            case oversized
        }
        let descriptorsBefore = openDescriptorCount()
        for behavior in [Behavior.silent, .partial, .eof, .oversized] {
            let temporary = try M4TemporaryDirectory()
            let location = try StateLocation.isolated(root: temporary.path)
            let authority = try LauncherAuthority.acquire(at: location)
            let state = authority.stateDirectory
            let generation = RunIdentity.make()
            let registration = HostRegistration(
                identity: try ProcessIdentity.capture(
                    processID: getpid(),
                    generation: generation,
                    expectedExecutablePath: CommandLine.arguments[0]
                )
            )
            try HostRegistrationStore.write(registration, state: state)
            let listener = try makeHostListener(
                path: state.path + "/host.sock"
            )
            let finished = DispatchSemaphore(value: 0)
            Thread.detachNewThread {
                defer {
                    close(listener)
                    finished.signal()
                }
                let peer = accept(listener, nil, nil)
                guard peer >= 0 else { return }
                defer { close(peer) }
                var buffer = [UInt8](repeating: 0, count: 4_096)
                _ = Darwin.read(peer, &buffer, buffer.count)
                switch behavior {
                case .silent:
                    usleep(1_500_000)
                case .partial:
                    var bytes = Array("{}".utf8)
                    _ = Darwin.write(peer, &bytes, bytes.count)
                case .eof:
                    break
                case .oversized:
                    var bytes = Data(repeating: UInt8(ascii: "x"), count: 17_000)
                    bytes.append(0x0A)
                    bytes.withUnsafeBytes { raw in
                        if let base = raw.baseAddress {
                            _ = Darwin.write(peer, base, raw.count)
                        }
                    }
                }
            }
            let started = MonotonicInstant.now()
            do {
                try HostControlClient.activate(at: location)
                throw M4SelfTestError.message(
                    "invalid host response was accepted"
                )
            } catch M4SelfTestError.message {
                throw M4SelfTestError.message("invalid host response was accepted")
            } catch {
                // Expected.
            }
            try check(
                MonotonicInstant.now().milliseconds(since: started) < 2_000,
                "activation client exceeded its response bound"
            )
            try check(
                finished.wait(timeout: .now() + 2) == .success,
                "fake host listener did not close"
            )
            authority.release()
        }
        try check(
            openDescriptorCount() <= descriptorsBefore + 1,
            "host control tests leaked descriptors"
        )
    }

    private static func rawHostExchange(
        location: StateLocation,
        request: Data,
        keepWriteOpen: Bool = false
    ) throws -> Data {
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else {
            throw M4SelfTestError.system("host test socket", errno)
        }
        defer { close(descriptor) }
        var timeout = timeval(tv_sec: 2, tv_usec: 0)
        guard setsockopt(
            descriptor,
            SOL_SOCKET,
            SO_RCVTIMEO,
            &timeout,
            socklen_t(MemoryLayout<timeval>.size)
        ) == 0 else {
            throw M4SelfTestError.system("host test timeout", errno)
        }
        try connectHostSocket(
            descriptor,
            path: location.path + "/host.sock"
        )
        try request.withUnsafeBytes { raw in
            guard let base = raw.baseAddress else { return }
            var offset = 0
            while offset < raw.count {
                let count = Darwin.write(
                    descriptor,
                    base.advanced(by: offset),
                    raw.count - offset
                )
                guard count > 0 else {
                    throw M4SelfTestError.system("host test write", errno)
                }
                offset += count
            }
        }
        if !keepWriteOpen {
            _ = shutdown(descriptor, SHUT_WR)
        }
        var response = Data()
        var bytes = [UInt8](repeating: 0, count: 4_096)
        while response.count <= 20_000 {
            let count = Darwin.read(descriptor, &bytes, bytes.count)
            if count > 0 {
                response.append(contentsOf: bytes.prefix(count))
                if response.contains(0x0A) { break }
                continue
            }
            if count < 0, errno == EINTR { continue }
            break
        }
        return response
    }

    private static func decodedHostResponse(
        _ data: Data
    ) throws -> HostControlResponse {
        guard data.last == 0x0A else {
            throw M4SelfTestError.message("host response lacked newline")
        }
        return try JSONDecoder().decode(
            HostControlResponse.self,
            from: data.dropLast()
        )
    }

    private static func makeHostListener(path: String) throws -> Int32 {
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else {
            throw M4SelfTestError.system("fake host socket", errno)
        }
        do {
            try bindHostSocket(descriptor, path: path)
            guard listen(descriptor, 1) == 0 else {
                throw M4SelfTestError.system("fake host listen", errno)
            }
            return descriptor
        } catch {
            close(descriptor)
            throw error
        }
    }

    private static func connectHostSocket(
        _ descriptor: Int32,
        path: String
    ) throws {
        var address = try hostSocketAddress(path: path)
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(
                    descriptor,
                    $0,
                    socklen_t(MemoryLayout<sockaddr_un>.size)
                )
            }
        }
        guard result == 0 else {
            throw M4SelfTestError.system("fake host connect", errno)
        }
    }

    private static func bindHostSocket(
        _ descriptor: Int32,
        path: String
    ) throws {
        var address = try hostSocketAddress(path: path)
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(
                    descriptor,
                    $0,
                    socklen_t(MemoryLayout<sockaddr_un>.size)
                )
            }
        }
        guard result == 0, chmod(path, 0o600) == 0 else {
            throw M4SelfTestError.system("fake host bind", errno)
        }
    }

    private static func hostSocketAddress(path: String) throws -> sockaddr_un {
        let pathBytes = Array(path.utf8CString)
        var address = sockaddr_un()
        guard pathBytes.count <= MemoryLayout.size(ofValue: address.sun_path) else {
            throw M4SelfTestError.message("fake host socket path is too long")
        }
        address.sun_family = sa_family_t(AF_UNIX)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        withUnsafeMutableBytes(of: &address.sun_path) { destination in
            destination.initializeMemory(as: UInt8.self, repeating: 0)
            pathBytes.withUnsafeBytes { destination.copyBytes(from: $0) }
        }
        return address
    }

    private static func openDescriptorCount() -> Int {
        (try? FileManager.default.contentsOfDirectory(atPath: "/dev/fd").count)
            ?? 0
    }

    private static func testStaleSocketRefusal() throws {
        let temporary = try M4TemporaryDirectory()
        let location = try StateLocation.isolated(root: temporary.path)
        let authority = try LauncherAuthority.acquire(at: location)
        let state = authority.stateDirectory
        let socketPath = state.path + "/host.sock"
        try Data("sentinel".utf8).write(to: URL(fileURLWithPath: socketPath))
        let server = try HostControlServer(
            authority: authority,
            executablePath: CommandLine.arguments[0],
            onActivation: { true }
        )
        do {
            try server.start()
            throw M4SelfTestError.message("regular stale socket path was removed")
        } catch ProcessOwnershipError.unsafeSocket {
            // Expected.
        }
        let retained = try Data(contentsOf: URL(fileURLWithPath: socketPath))
        try check(
            retained == Data("sentinel".utf8),
            "unsafe stale socket bytes changed"
        )
        server.stop()

        let liveTemporary = try M4TemporaryDirectory()
        let liveLocation = try StateLocation.isolated(root: liveTemporary.path)
        let liveAuthority = try LauncherAuthority.acquire(at: liveLocation)
        let livePath = liveAuthority.stateDirectory.path + "/host.sock"
        let liveListener = try makeHostListener(path: livePath)
        defer {
            close(liveListener)
            _ = unlink(livePath)
        }
        let liveServer = try HostControlServer(
            authority: liveAuthority,
            executablePath: CommandLine.arguments[0],
            onActivation: { true }
        )
        do {
            try liveServer.start()
            throw M4SelfTestError.message("live unverified socket was replaced")
        } catch ProcessOwnershipError.unsafeSocket {
            // Expected.
        }
        var liveInfo = stat()
        try check(
            lstat(livePath, &liveInfo) == 0
                && (liveInfo.st_mode & S_IFMT) == S_IFSOCK,
            "live unverified socket was unlinked"
        )
        liveServer.stop()

        let deadTemporary = try M4TemporaryDirectory()
        let deadLocation = try StateLocation.isolated(root: deadTemporary.path)
        let deadAuthority = try LauncherAuthority.acquire(at: deadLocation)
        let deadPath = deadAuthority.stateDirectory.path + "/host.sock"
        let deadListener = try makeHostListener(path: deadPath)
        close(deadListener)
        let replacement = try HostControlServer(
            authority: deadAuthority,
            executablePath: CommandLine.arguments[0],
            onActivation: { true }
        )
        try replacement.start()
        replacement.stop()
    }

    private static func testRecoveryBlocking() throws {
        let temporary = try M4TemporaryDirectory()
        let location = try StateLocation.isolated(root: temporary.path)
        let authority = try RunAuthority.acquireRun(at: location)
        defer { authority.release() }
        let lease = try authority.duplicateOperationLease()
        authority.release()
        defer { close(lease) }
        try check(
            RunRecoveryInspector.inspect(at: location) == .operationStillActive,
            "surviving operation lease did not block recovery"
        )
        let lifecycle: RunAuthority?
        do {
            lifecycle = try RunAuthority.acquireLifecycleMutation(at: location)
        } catch {
            lifecycle = nil
        }
        try check(lifecycle == nil, "surviving lease did not block lifecycle mutation")
    }

    private static func testInterruptedReconstruction() throws {
        let candidates = (1...4).map { index in
            RepositoryCandidate(
                id: "fixture-owner/recovery-\(index)",
                displayName: "Recovery \(index)",
                path: "/private/tmp/recovery-\(index)",
                rawOrigin: "https://github.com/fixture-owner/recovery-\(index).git"
            )
        }
        let run = RunIdentity.make()
        let intent = RunIntent(
            run: run,
            startedAt: "2026-09-04T00:00:00.000Z",
            candidates: candidates
        )
        let completed = RepositoryResult(
            repository: candidates[0],
            code: .updated,
            fetched: true,
            mainUpdated: true,
            beforeCommit: "a",
            targetCommit: "b",
            afterCommit: "b",
            startedAt: intent.startedAt,
            endedAt: intent.startedAt,
            durationMilliseconds: 1,
            explanation: "completed"
        )
        var records = [
            LogRecord(run: run, sequence: 1, type: "run_intent", intent: intent),
            LogRecord(
                run: run,
                sequence: 2,
                type: "event",
                event: RunEvent(
                    run: run,
                    sequence: 1,
                    type: .repositoryResult,
                    result: completed
                )
            ),
            LogRecord(
                run: run,
                sequence: 3,
                type: "repository_checkpoint",
                checkpoint: RepositoryCheckpoint(
                    repository: candidates[1],
                    startedAt: intent.startedAt,
                    beforeCommit: "before-0",
                    targetCommit: nil,
                    fetched: false
                )
            ),
        ]
        for (offset, candidate) in candidates.dropFirst().dropLast().enumerated() {
            records.append(LogRecord(
                run: run,
                sequence: records.count + 1,
                type: "repository_checkpoint",
                checkpoint: RepositoryCheckpoint(
                    repository: candidate,
                    startedAt: intent.startedAt,
                    beforeCommit: "before-\(offset)",
                    targetCommit: "target-\(offset)",
                    fetched: true
                )
            ))
        }
        let report = try require(InterruptedRunReconstructor.reconstruct(
            records: records
        ) { checkpoint in
            checkpoint.repository == candidates[1]
                ? .updated(checkpoint.targetCommit!)
                : .ambiguous("different")
        }, "interrupted run was not reconstructed")
        try check(
            report.summary == InterruptedRunReconstructor.summary,
            "interrupted aggregate copy changed"
        )
        try check(
            report.results.map(\.code)
                == [.updated, .updatedBeforeCancellation, .needsAttention, .cancelledPending],
            "completed/updated/ambiguous/pending outcomes changed"
        )
        try check(report.results[0] == completed, "completed result was rolled back")

        let fixture = try M1GitFixture()
        defer { fixture.remove() }
        let current = String(
            decoding: try fixture.gitOutput(["rev-parse", "refs/heads/main"]),
            as: UTF8.self
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        let actualRun = RunIdentity.make()
        let actualStartedAt = WallClock.timestamp()
        do {
            let authority = try RunAuthority.acquireRun(at: fixture.stateLocation)
            let writer = try RunLogWriter(authority: authority, runID: actualRun)
            try writer.append(
                type: "run_intent",
                intent: RunIntent(
                    run: actualRun,
                    startedAt: actualStartedAt,
                    candidates: [fixture.candidate],
                    repositoryModel: "v2"
                )
            )
            try writer.append(
                type: "repository_checkpoint",
                checkpoint: RepositoryCheckpoint(
                    repository: fixture.candidate,
                    startedAt: actualStartedAt,
                    beforeCommit: current,
                    targetCommit: nil,
                    fetched: false
                )
            )
            try writer.flush()
            authority.release()
        }
        guard case let .previousReport(actualReport) =
                RunRecoveryInspector.inspect(at: fixture.stateLocation) else {
            throw M4SelfTestError.message("descriptor-safe postflight did not reconstruct")
        }
        try check(
            actualReport.results.map(\.code) == [.cancelledNoUpdate],
            "descriptor-safe unchanged postflight was misclassified"
        )
    }

    private static func testLogIntentControlFraming() throws {
        let temporary = try M4TemporaryDirectory()
        let location = try StateLocation.isolated(root: temporary.path)
        let authority = try RunAuthority.acquireRun(at: location)
        defer { authority.release() }
        let run = RunIdentity.make()
        let candidate = RepositoryCandidate(
            id: "fixture-owner/log",
            displayName: "Log",
            path: "/private/tmp/log",
            rawOrigin: "https://github.com/fixture-owner/log.git"
        )
        let writer = try RunLogWriter(authority: authority, runID: run)
        try writer.append(
            type: "run_intent",
            intent: RunIntent(
                run: run,
                startedAt: WallClock.timestamp(),
                candidates: [candidate]
            )
        )
        try writer.append(
            type: "control",
            data: "cancel\n{\"type\":\"run_finished\",\"token\":\"ghp_abcdefghijklmnopqrstuvwxyz\"}"
        )
        try writer.flush()
        let records = try RunLogReader.records(state: authority.stateDirectory)
        try check(records.count == 2, "forged newline changed record framing")
        try check(
            records[1].data?.contains("ghp_abcdefghijklmnopqrstuvwxyz") == false,
            "seeded token survived redaction"
        )
        let attributes = try FileManager.default.attributesOfItem(atPath: writer.path)
        try check(
            (attributes[.posixPermissions] as? NSNumber)?.uint16Value == 0o600,
            "latest log mode is not private"
        )
    }

    private static func spawnGroup(script: String) throws -> pid_t {
        var attributes: posix_spawnattr_t?
        guard posix_spawnattr_init(&attributes) == 0 else {
            throw M4SelfTestError.system("spawn attributes", errno)
        }
        defer { posix_spawnattr_destroy(&attributes) }
        var code = posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETPGROUP))
        if code == 0 {
            code = posix_spawnattr_setpgroup(&attributes, 0)
        }
        guard code == 0 else {
            throw M4SelfTestError.system("spawn group", code)
        }
        let arguments = ["/bin/sh", "-c", script]
        let pointers = arguments.map { strdup($0) }
        defer {
            pointers.forEach { pointer in
                if let pointer {
                    free(UnsafeMutableRawPointer(pointer))
                }
            }
        }
        var argv = pointers + [nil]
        var processID: pid_t = 0
        code = argv.withUnsafeMutableBufferPointer {
            posix_spawn(&processID, "/bin/sh", nil, &attributes, $0.baseAddress, environ)
        }
        guard code == 0 else {
            throw M4SelfTestError.system("spawn helper", code)
        }
        return processID
    }

    private static func waitForReadiness(
        at path: String,
        processID: pid_t,
        timeout: TimeInterval = 5
    ) throws {
        let deadline = MonotonicDeadline(seconds: timeout)
        while !deadline.hasExpired {
            var info = stat()
            if lstat(path, &info) == 0 {
                try check(
                    (info.st_mode & S_IFMT) == S_IFREG
                        && info.st_uid == geteuid(),
                    "process readiness marker is unsafe"
                )
                return
            }
            guard errno == ENOENT else {
                throw M4SelfTestError.system("inspect process readiness", errno)
            }
            guard kill(processID, 0) == 0 else {
                throw M4SelfTestError.message(
                    "process exited before publishing readiness"
                )
            }
            usleep(10_000)
        }
        throw M4SelfTestError.message("process readiness timed out")
    }

    private static func wait(_ processID: pid_t, timeout: TimeInterval) -> Int32? {
        let deadline = MonotonicDeadline(seconds: timeout)
        var status: Int32 = 0
        while !deadline.hasExpired {
            let result = waitpid(processID, &status, WNOHANG)
            if result == processID { return status }
            if result < 0, errno == ECHILD { return status }
            usleep(10_000)
        }
        return nil
    }

    private static func forceReap(_ processID: pid_t) {
        if kill(processID, 0) == 0 {
            _ = kill(-processID, SIGKILL)
        }
        var status: Int32 = 0
        while waitpid(processID, &status, 0) < 0, errno == EINTR {}
    }

    private static func groupGone(_ processID: pid_t) -> Bool {
        if kill(-processID, 0) == 0 {
            return false
        }
        return errno == ESRCH
    }

    private static func check(
        _ condition: @autoclosure () -> Bool,
        _ message: String
    ) throws {
        guard condition() else { throw M4SelfTestError.message(message) }
    }

    private static func require<T>(_ value: T?, _ message: String) throws -> T {
        guard let value else { throw M4SelfTestError.message(message) }
        return value
    }
}

private final class M4TemporaryDirectory {
    let path: String

    init() throws {
        var template = Array("/private/tmp/dev-main-sync-m4.XXXXXX".utf8CString)
        guard let result = mkdtemp(&template) else {
            throw M4SelfTestError.system("mkdtemp", errno)
        }
        path = String(cString: result)
        guard chmod(path, 0o700) == 0 else {
            throw M4SelfTestError.system("chmod test root", errno)
        }
    }

    deinit {
        try? FileManager.default.removeItem(atPath: path)
    }
}

private enum M4SelfTestError: Error {
    case failed(String, String)
    case message(String)
    case system(String, Int32)
}
#endif
