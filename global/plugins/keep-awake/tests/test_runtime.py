#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
RUNTIME = PLUGIN_DIR / "scripts" / "hooks" / "keep-awake-refill.sh"
MAINTENANCE_WRAPPER = (
    PLUGIN_DIR / "scripts" / "maintenance" / "keep-awake-maintenance.sh"
)


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def write_state(path: Path, **overrides) -> None:
    data = {
        "last_attempt": 0,
        "last_success": 0,
        "lease_expiry": 0,
        "last_status": "",
        "last_error": "",
    }
    data.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_caffeinate_state(path: Path, **overrides) -> None:
    data = {"pid": 1, "expiry": 0, "status": "started"}
    data.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_activity_state(path: Path, last_hook_activity: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps({"last_hook_activity": last_hook_activity}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._spawned_caffeinate_procs: dict[int, subprocess.Popen] = {}

    def make_environment(self, root: Path) -> tuple[dict[str, str], Path, Path]:
        app = root / "Amphetamine.app"
        app.mkdir()
        state_root = root / "state"
        log = root / "osascript-calls.jsonl"
        pgrep = root / "mock-pgrep"
        osascript = root / "mock-osascript"
        plutil = root / "mock-plutil"
        caffeinate = root / "mock-caffeinate"
        ps = root / "mock-ps"
        # Allocated outside `root` (via mkstemp, not the per-test TemporaryDirectory) and cleaned up
        # by its own addCleanup below, independent of `root`'s lifecycle: every test method's `with
        # tempfile.TemporaryDirectory()` block exits -- deleting `root` -- before unittest's
        # addCleanup phase runs, so a log path living under `root` would already be gone by the time
        # cleanup tries to read it for pids to kill.
        caffeinate_log_fd, caffeinate_log_name = tempfile.mkstemp(prefix="keep-awake-caffeinate-log-")
        os.close(caffeinate_log_fd)
        caffeinate_log = Path(caffeinate_log_name)
        self.addCleanup(self._kill_logged_caffeinates, caffeinate_log)
        write_executable(
            pgrep,
            """
            #!/bin/bash
            [ "${MOCK_PROCESS_RUNNING:-1}" = "1" ]
            """,
        )
        write_executable(
            plutil,
            r"""
            #!/usr/bin/env python3
            import json
            import sys

            key = sys.argv[sys.argv.index("-extract") + 1]
            descriptor = json.load(open(sys.argv[-1], encoding="utf-8"))
            value = descriptor
            for part in key.split("."):
                value = value[part]
            if isinstance(value, bool):
                print("true" if value else "false")
            else:
                print(value)
            """,
        )
        write_executable(
            osascript,
            r"""
            #!/usr/bin/env python3
            import json
            import os
            import sys

            source = sys.stdin.read()
            with open(os.environ["MOCK_OSA_LOG"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"argv": sys.argv[1:], "source": source}) + "\n")

            exit_code = int(os.environ.get("MOCK_OSA_EXIT", "0"))
            if exit_code:
                print(os.environ.get("MOCK_OSA_ERROR", "mock Apple Events error"))
                raise SystemExit(exit_code)

            malformed = os.environ.get("MOCK_OSA_MALFORMED_RESULT")
            if malformed is not None:
                print(malformed)
                raise SystemExit(0)

            code = int(os.environ.get("MOCK_SESSION_CODE", "-3"))
            now = int(sys.argv[2])
            lease = int(sys.argv[3])
            tolerance = int(sys.argv[5])
            refresh_threshold = int(sys.argv[10])
            if code == -3:
                outcome = "started"
            elif code > 0:
                expected = lease - now
                if lease > now and expected > 0 and abs(code - expected) <= tolerance:
                    outcome = "refreshed" if code <= refresh_threshold else "preserved-owned"
                else:
                    outcome = "preserved-finite"
            else:
                outcome = "preserved-special"
            print(f"{outcome}|{code}")
            """,
        )
        write_executable(
            caffeinate,
            r"""
            #!/bin/bash
            # Mocks /usr/bin/caffeinate: logs its own start (pid + argv) to the shared jsonl trail,
            # like the existing mock-osascript, then blocks until signaled. Polls on a short interval
            # rather than a single long-blocking command so the TERM trap below fires promptly instead
            # of only after some foreground command returns -- tests can then observe create-before-
            # destroy ordering (by log line order) and never touch a real caffeinate process on the
            # machine running these tests.
            printf '{"event":"start","pid":%d,"argv":"%s"}\n' "$$" "$*" >> "$MOCK_CAFFEINATE_LOG"
            if [ "${MOCK_CAFFEINATE_EXIT_IMMEDIATELY:-0}" = "1" ]; then
              exit 1
            fi
            trap 'printf "{\"event\":\"sigterm\",\"pid\":%d}\n" "$$" >> "$MOCK_CAFFEINATE_LOG"; exit 0' TERM
            while true; do
              sleep 0.05
            done
            """,
        )
        write_executable(
            ps,
            r"""
            #!/bin/bash
            # Mocks /bin/ps for the caffeinate identity check (`ps -p PID -o comm=`). Returns
            # MOCK_PS_COMM (default "caffeinate") regardless of which pid was asked about, so tests can
            # decouple "is this pid alive" (checked for real via kill -0, unmocked) from "does ps say
            # it's ours" (fully controllable here) -- this is how the PID-reuse tests simulate an
            # identity mismatch without waiting for a real OS pid recycle. MOCK_PS_FLIP_AFTER_CALLS, if
            # set, returns MOCK_PS_COMM for that many calls and a fixed unrelated value after, proving
            # the re-check immediately before a kill (not just the initial read) is the one consulted.
            count=0
            if [ -n "${MOCK_PS_COUNT_FILE:-}" ]; then
              [ -f "$MOCK_PS_COUNT_FILE" ] && count="$(cat "$MOCK_PS_COUNT_FILE")"
              count=$((count + 1))
              printf '%s' "$count" > "$MOCK_PS_COUNT_FILE"
            fi
            if [ -n "${MOCK_PS_FLIP_AFTER_CALLS:-}" ] && [ "$count" -gt "${MOCK_PS_FLIP_AFTER_CALLS}" ]; then
              printf '%s\n' "${MOCK_PS_UNRELATED_COMM:-unrelated-process}"
            else
              printf '%s\n' "${MOCK_PS_COMM:-caffeinate}"
            fi
            """,
        )
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(root),
                "KEEP_AWAKE_PLATFORM": "Darwin",
                "KEEP_AWAKE_DURATION_SECONDS": "120",
                "KEEP_AWAKE_THROTTLE_SECONDS": "5",
                "KEEP_AWAKE_TIMEOUT_SECONDS": "1",
                "KEEP_AWAKE_DISPLAY_SLEEP_ALLOWED": "false",
                "KEEP_AWAKE_PREVENT_SCREEN_SAVER": "true",
                "KEEP_AWAKE_STATE_ROOT": str(state_root),
                "KEEP_AWAKE_APP_NAME": "Amphetamine",
                "KEEP_AWAKE_PROCESS": "Amphetamine",
                "KEEP_AWAKE_BUNDLE_ID": "com.if.Amphetamine",
                "KEEP_AWAKE_APP_PATH": str(app),
                "KEEP_AWAKE_PLUTIL": str(plutil),
                "KEEP_AWAKE_PGREP": str(pgrep),
                "KEEP_AWAKE_OSASCRIPT": str(osascript),
                "KEEP_AWAKE_CAFFEINATE_SUPPLEMENT_ENABLED": "true",
                "KEEP_AWAKE_MAINTENANCE_ENABLED": "true",
                "KEEP_AWAKE_ACTIVITY_WINDOW_SECONDS": "60",
                "KEEP_AWAKE_CAFFEINATE": str(caffeinate),
                "KEEP_AWAKE_PS": str(ps),
                "KEEP_AWAKE_NOW": "100",
                "MOCK_PROCESS_RUNNING": "1",
                "MOCK_SESSION_CODE": "-3",
                "MOCK_OSA_LOG": str(log),
                "MOCK_CAFFEINATE_LOG": str(caffeinate_log),
            }
        )
        return env, state_root, log

    def _kill_logged_caffeinates(self, caffeinate_log: Path) -> None:
        try:
            events = self.caffeinate_events(caffeinate_log)
        except OSError:
            events = []
        for event in events:
            if event.get("event") != "start":
                continue
            pid = event.get("pid")
            if not isinstance(pid, int):
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
        try:
            caffeinate_log.unlink()
        except FileNotFoundError:
            pass

    def caffeinate_events(self, caffeinate_log: Path) -> list[dict]:
        if not caffeinate_log.exists():
            return []
        events = []
        for line in caffeinate_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
        return events

    def caffeinate_state(self, state_root: Path) -> dict:
        return json.loads((state_root / "caffeinate.json").read_text(encoding="utf-8"))

    def run_hook(self, env: dict[str, str], event: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RUNTIME), event],
            input="{}",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=5,
        )

    def calls(self, log: Path) -> list[dict]:
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def state(self, state_root: Path) -> dict:
        return json.loads((state_root / "state.json").read_text(encoding="utf-8"))

    def activity(self, state_root: Path) -> dict:
        return json.loads((state_root / "activity.json").read_text(encoding="utf-8"))

    def spawn_mock_caffeinate(self, env: dict[str, str]) -> int:
        # Spawns the SAME mock binary the runtime itself would invoke, directly from the test, to
        # seed a genuinely-alive "already running" caffeinate process a test can then track via
        # caffeinate.json -- real liveness (kill -0) and real identity (ps, itself mocked) both
        # resolve exactly as they would for a process the runtime spawned itself.
        proc = subprocess.Popen(
            [env["KEEP_AWAKE_CAFFEINATE"], "manual-seed"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        self.addCleanup(self._kill_and_reap, proc)
        self._spawned_caffeinate_procs[proc.pid] = proc
        caffeinate_log = Path(env["MOCK_CAFFEINATE_LOG"])

        def started() -> bool:
            return any(
                e["event"] == "start" and e["pid"] == proc.pid
                for e in self.caffeinate_events(caffeinate_log)
            )

        self.assertTrue(wait_until(started), "manually-seeded mock caffeinate never logged its start")
        return proc.pid

    @staticmethod
    def _kill_and_reap(proc: subprocess.Popen) -> None:
        # A cleanup-time kill() alone leaves a reapable zombie until this test process itself
        # exits (Popen.__del__ only warns, it does not wait) -- harmless, but noisy: it surfaces
        # as a ResourceWarning on every test that seeds a still-alive mock caffeinate. wait() here
        # is a no-op (returns immediately) for a pid already reaped by an in-test
        # assert_caffeinate_pid_dead call.
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def assert_caffeinate_pid_dead(self, pid: int) -> None:
        # A pid returned by spawn_mock_caffeinate is a direct child of THIS test process, so once
        # the runtime sends it SIGTERM it becomes a zombie -- still visible to a bare `kill -0` --
        # until this process reaps it via the Popen handle. A pid the runtime script spawns for
        # itself has no such issue: it is reparented to launchd once the runtime script exits,
        # which reaps it promptly, so a plain pid_alive() check is reliable for those.
        proc = self._spawned_caffeinate_procs.get(pid)
        if proc is not None:
            proc.wait(timeout=2)
            return
        self.assertFalse(pid_alive(pid))

    def test_event_specific_non_block_responses_on_non_darwin(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            env["KEEP_AWAKE_PLATFORM"] = "Linux"
            prompt = self.run_hook(env, "beforeSubmitPrompt")
            tool = self.run_hook(env, "preToolUse")
            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            self.assertEqual(tool.returncode, 0, tool.stderr)
            self.assertEqual(prompt.stdout, "{}\n")
            self.assertEqual(tool.stdout, '{"permission":"allow"}\n')
            self.assertFalse(state_root.exists())
            self.assertEqual(self.calls(log), [])

    def test_missing_app_and_stopped_process_are_noops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, log = self.make_environment(root)
            Path(env["KEEP_AWAKE_APP_PATH"]).rmdir()
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "{}\n")
            self.assertEqual(self.calls(log), [])
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 100})
            self.assertFalse((state_root / "state.json").exists())
            self.assertFalse((state_root / "caffeinate.json").exists())

            Path(env["KEEP_AWAKE_APP_PATH"]).mkdir()
            env["MOCK_PROCESS_RUNNING"] = "0"
            result = self.run_hook(env, "preToolUse")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '{"permission":"allow"}\n')
            self.assertEqual(self.calls(log), [])
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 100})
            self.assertFalse((state_root / "state.json").exists())
            self.assertFalse((state_root / "caffeinate.json").exists())

    def test_hook_activity_is_refreshed_even_when_main_attempt_is_throttled(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            self.assertEqual(self.run_hook(env, "beforeSubmitPrompt").returncode, 0)
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 100})
            self.assertEqual(len(self.calls(log)), 1)

            env["KEEP_AWAKE_NOW"] = "101"
            result = self.run_hook(env, "preToolUse")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '{"permission":"allow"}\n')
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 101})
            self.assertEqual(len(self.calls(log)), 1)

    def test_unknown_event_and_stop_fence_are_strict_noops(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            unknown = self.run_hook(env, "maintenance-typo")
            self.assertEqual(unknown.returncode, 0, unknown.stderr)
            self.assertEqual(unknown.stdout, "{}\n")
            self.assertFalse(state_root.exists())
            self.assertEqual(self.calls(log), [])

            state_root.mkdir(parents=True)
            (state_root / "stop.fence").write_text("uninstalling\n", encoding="utf-8")
            prompt = self.run_hook(env, "beforeSubmitPrompt")
            maintenance = self.run_hook(env, "maintenance")
            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            self.assertEqual(maintenance.returncode, 0, maintenance.stderr)
            self.assertFalse((state_root / "activity.json").exists())
            self.assertFalse((state_root / "state.json").exists())
            self.assertFalse((state_root / "caffeinate.json").exists())
            self.assertEqual(self.calls(log), [])

    def test_maintenance_wrapper_fails_safe_with_pre_v3_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
            legacy.pop("maintenanceEnabled")
            legacy.pop("maintenanceIntervalSeconds")
            legacy.pop("activityWindowSeconds")
            descriptor = root / "plugin.json"
            descriptor.write_text(json.dumps(legacy), encoding="utf-8")
            state_root = root / "state"
            env = os.environ.copy()
            env.update(
                {
                    "KEEP_AWAKE_DESCRIPTOR": str(descriptor),
                    "KEEP_AWAKE_PYTHON": sys.executable,
                    "KEEP_AWAKE_PLATFORM": "Darwin",
                    "KEEP_AWAKE_STATE_ROOT": str(state_root),
                }
            )
            result = subprocess.run(
                [str(MAINTENANCE_WRAPPER)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(state_root.exists())

    def test_maintenance_requires_recent_hook_activity_and_never_renews_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))

            cold = self.run_hook(env, "maintenance")
            self.assertEqual(cold.returncode, 0, cold.stderr)
            self.assertFalse(state_root.exists())
            self.assertEqual(self.calls(log), [])

            write_activity_state(state_root / "activity.json", 39)
            stale = self.run_hook(env, "maintenance")
            self.assertEqual(stale.returncode, 0, stale.stderr)
            self.assertEqual(self.calls(log), [])
            self.assertFalse((state_root / "state.json").exists())
            self.assertFalse((state_root / "caffeinate.json").exists())
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 39})

            write_activity_state(state_root / "activity.json", 40)
            recent = self.run_hook(env, "maintenance")
            self.assertEqual(recent.returncode, 0, recent.stderr)
            self.assertEqual(len(self.calls(log)), 1)
            self.assertTrue((state_root / "state.json").exists())
            self.assertTrue((state_root / "caffeinate.json").exists())
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 40})

    def test_maintenance_rejects_future_activity_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_activity_state(state_root / "activity.json", 101)
            result = self.run_hook(env, "maintenance")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.calls(log), [])
            self.assertFalse((state_root / "state.json").exists())
            self.assertFalse((state_root / "caffeinate.json").exists())

    def test_runtime_defaults_are_loaded_from_plugin_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, _state_root, log = self.make_environment(root)
            for key in (
                "KEEP_AWAKE_DURATION_SECONDS",
                "KEEP_AWAKE_THROTTLE_SECONDS",
                "KEEP_AWAKE_TIMEOUT_SECONDS",
                "KEEP_AWAKE_DISPLAY_SLEEP_ALLOWED",
                "KEEP_AWAKE_PREVENT_SCREEN_SAVER",
                "KEEP_AWAKE_MAINTENANCE_ENABLED",
                "KEEP_AWAKE_ACTIVITY_WINDOW_SECONDS",
                "KEEP_AWAKE_STATE_ROOT",
                "KEEP_AWAKE_APP_NAME",
                "KEEP_AWAKE_PROCESS",
                "KEEP_AWAKE_BUNDLE_ID",
            ):
                env.pop(key)
            env["KEEP_AWAKE_NOW"] = "1000"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(
                (root / ".local" / "state" / "keep-awake" / "state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["lease_expiry"], 2200)
            self.assertEqual(state["last_status"], "started")
            # bundleId also fell back to the real plugin.json descriptor and produced a working
            # AppleScript invocation (not an empty/missing-BUNDLE_ID fail-open no-op).
            self.assertTrue(log.exists())
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(calls[-1]["argv"][-2], "com.if.Amphetamine")
            # Refresh threshold is derived (2x throttleSeconds), not descriptor-sourced -- confirms
            # it fell back correctly using the real plugin.json's throttleSeconds (300) too.
            self.assertEqual(calls[-1]["argv"][-1], "600")
            self.assertEqual(
                json.loads(
                    (root / ".local" / "state" / "keep-awake" / "activity.json").read_text(
                        encoding="utf-8"
                    )
                ),
                {"last_hook_activity": 1000},
            )

    def test_throttle_is_strict_before_and_due_at_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            self.assertEqual(self.run_hook(env, "beforeSubmitPrompt").returncode, 0)
            env["KEEP_AWAKE_NOW"] = "104"
            self.assertEqual(self.run_hook(env, "preToolUse").returncode, 0)
            self.assertEqual(len(self.calls(log)), 1)
            self.assertEqual(self.state(state_root)["last_attempt"], 100)

            env["KEEP_AWAKE_NOW"] = "105"
            self.assertEqual(self.run_hook(env, "preToolUse").returncode, 0)
            self.assertEqual(len(self.calls(log)), 2)
            self.assertEqual(self.state(state_root)["last_attempt"], 105)

    def test_stale_legacy_lock_is_upgraded_but_future_lock_is_not_stolen(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_state(state_root / "state.json")
            lock = state_root / ".lock"
            lock.mkdir()
            (lock / "acquired").write_text("1\n", encoding="utf-8")

            stale = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(stale.returncode, 0, stale.stderr)
            self.assertEqual(len(self.calls(log)), 1)
            self.assertFalse(lock.exists())

        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_state(state_root / "state.json")
            lock = state_root / ".lock"
            lock.mkdir()
            (lock / "acquired").write_text("101\n", encoding="utf-8")

            future = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(future.returncode, 0, future.stderr)
            self.assertEqual(self.calls(log), [])
            self.assertTrue(lock.exists())
            self.assertEqual(self.activity(state_root), {"last_hook_activity": 100})

    def test_release_lock_never_deletes_a_replacement_owner(self):
        runtime_source = RUNTIME.read_text(encoding="utf-8")
        start = runtime_source.index("release_lock() {")
        end = runtime_source.index("\n}\n", start) + len("\n}\n")
        release_lock_source = runtime_source[start:end]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / ".lock"
            lock.mkdir()
            (lock / "owner").write_text("replacement\n", encoding="utf-8")
            harness = root / "release-lock.sh"
            harness.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                'RM="/bin/rm"\n'
                "LOCK_HELD=1\n"
                f'LOCK_DIR="{lock}"\n'
                'LOCK_OWNER="original"\n'
                f"{release_lock_source}\n"
                "release_lock\n"
                f'[ -d "{lock}" ]\n',
                encoding="utf-8",
            )
            harness.chmod(0o755)
            result = subprocess.run(
                [str(harness)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(lock.exists())

    def test_no_session_starts_owned_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, _log = self.make_environment(Path(directory))
            env["MOCK_SESSION_CODE"] = "-3"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = self.state(state_root)
            self.assertEqual(state["last_success"], 100)
            self.assertEqual(state["lease_expiry"], 220)
            self.assertEqual(state["last_status"], "started")

    def test_infinite_trigger_and_app_date_sessions_are_preserved(self):
        for code in (0, -1, -2):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                env, state_root, _log = self.make_environment(Path(directory))
                write_state(
                    state_root / "state.json",
                    last_attempt=90,
                    last_success=50,
                    lease_expiry=180,
                    last_status="started",
                )
                env["MOCK_SESSION_CODE"] = str(code)
                result = self.run_hook(env, "beforeSubmitPrompt")
                self.assertEqual(result.returncode, 0, result.stderr)
                state = self.state(state_root)
                self.assertEqual(state["last_success"], 50)
                self.assertEqual(state["lease_expiry"], 0)
                self.assertEqual(state["last_status"], "preserved-special")

    def test_matching_owned_finite_session_near_expiry_refreshes(self):
        # remaining(8) <= refresh threshold (2 * 5s throttle = 10) -- close enough to expiry that
        # the full teardown/rebuild (and its brief assertion gap) is worth paying for.
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, _log = self.make_environment(Path(directory))
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=108,
                last_status="started",
            )
            env["MOCK_SESSION_CODE"] = "8"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = self.state(state_root)
            self.assertEqual(state["last_success"], 100)
            self.assertEqual(state["lease_expiry"], 220)
            self.assertEqual(state["last_status"], "refreshed")

    def test_matching_owned_finite_session_within_lease_is_preserved_without_restart(self):
        # remaining(80) is well above the refresh threshold (10) -- confirmed ours, but far too
        # early to justify a teardown/rebuild, so only screen-saver suppression is reasserted and
        # the tracked lease is left exactly as it was (not extended, not cleared).
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=180,
                last_status="started",
            )
            env["MOCK_SESSION_CODE"] = "80"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(self.calls(log)), 1)
            state = self.state(state_root)
            self.assertEqual(state["last_attempt"], 100)
            self.assertEqual(state["last_success"], 50)
            self.assertEqual(state["lease_expiry"], 180)
            self.assertEqual(state["last_status"], "preserved-owned")

    def test_mismatched_manual_finite_session_is_preserved_and_lease_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, _log = self.make_environment(Path(directory))
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=180,
                last_status="started",
            )
            env["MOCK_SESSION_CODE"] = "45"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = self.state(state_root)
            self.assertEqual(state["last_success"], 50)
            self.assertEqual(state["lease_expiry"], 0)
            self.assertEqual(state["last_status"], "preserved-finite")

    def test_applescript_uses_correct_session_options_and_prevents_screen_saver(self):
        with tempfile.TemporaryDirectory() as directory:
            env, _state_root, log = self.make_environment(Path(directory))
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            call = self.calls(log)[0]
            self.assertEqual(call["argv"][0], "-")
            self.assertEqual(call["argv"][3], "2")
            # Trailing "10" is the derived refresh threshold (2x the 5s test throttle).
            self.assertEqual(call["argv"][5:], ["1", "false", "true", "com.if.Amphetamine", "10"])
            self.assertIn(
                "start new session with options {duration:durationMinutes, interval:minutes, "
                "displaySleepAllowed:displaySleep}",
                call["source"],
            )
            self.assertIn("prevent screen saver", call["source"])
            self.assertIn("set remaining to session time remaining", call["source"])
            # Screen-saver suppression is reasserted on a comfortably-within-lease tick too (not
            # only started|/refreshed|), decoupling it from the session-restart cadence.
            self.assertIn('return "preserved-owned|" & remaining', call["source"])
            self.assertIn("refreshThresholdSeconds", call["source"])
            # Addressed by bundle id (finding #10), not display name, for rename/relocation
            # resistance -- with the compile-time terms hint custom Amphetamine vocabulary needs.
            self.assertIn('tell application id backendID', call["source"])
            self.assertNotIn('tell application "Amphetamine"', call["source"])
            self.assertIn('using terms from application "Amphetamine"', call["source"])

    def test_osascript_error_is_rate_limited_without_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=170,
                last_status="started",
            )
            env["MOCK_OSA_EXIT"] = "1"
            env["MOCK_OSA_ERROR"] = 'Not authorized to send Apple events. (-1743) "quoted"'
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = self.state(state_root)
            self.assertEqual(state["last_attempt"], 100)
            self.assertEqual(state["last_success"], 50)
            self.assertEqual(state["lease_expiry"], 170)
            self.assertEqual(state["last_status"], "error")
            self.assertIn("-1743", state["last_error"])
            self.assertLessEqual(len(state["last_error"]), 240)

            env["KEEP_AWAKE_NOW"] = "101"
            second = self.run_hook(env, "preToolUse")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout, '{"permission":"allow"}\n')
            self.assertEqual(len(self.calls(log)), 1)

    def test_state_write_failure_prevents_unthrottled_applescript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, _state_root, log = self.make_environment(root)
            blocker = root / "not-a-directory"
            blocker.write_text("block", encoding="utf-8")
            env["KEEP_AWAKE_STATE_ROOT"] = str(blocker / "state")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "{}\n")
            self.assertEqual(self.calls(log), [])

    def test_error_state_remains_valid_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, _log = self.make_environment(Path(directory))
            env["MOCK_OSA_EXIT"] = "1"
            env["MOCK_OSA_ERROR"] = ('bad "Apple Event"\\line\n' * 100)
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            state_file = state_root / "state.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertLessEqual(len(state["last_error"]), 240)
            self.assertLessEqual(state_file.stat().st_size, 4096)

    def test_unexpected_osascript_result_fails_open_with_bounded_error_state(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=180,
                last_status="started",
            )
            # A malformed/unrecognized AppleScript result: exit 0 (no osascript-level error) but a
            # body matching none of the started|refreshed|preserved-finite|preserved-special
            # prefixes the runtime's case statement recognizes.
            env["MOCK_OSA_MALFORMED_RESULT"] = "a-totally-unrecognized-response-shape"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "{}\n")
            self.assertEqual(len(self.calls(log)), 1)
            state = self.state(state_root)
            # Fail-open: no false success, no lease extension -- both stay at their pre-call values.
            self.assertEqual(state["last_success"], 50)
            self.assertEqual(state["lease_expiry"], 180)
            self.assertEqual(state["last_attempt"], 100)
            self.assertEqual(state["last_status"], "error")
            self.assertIn("unexpected osascript response", state["last_error"])
            self.assertIn("a-totally-unrecognized-response-shape", state["last_error"])
            self.assertLessEqual(len(state["last_error"]), 240)

    def test_configured_relative_hook_command_executes_from_cursor_home_layout(self):
        # ~/.cursor/hooks.json's actual configured command is the relative
        # './skills/keep-awake/scripts/hooks/keep-awake-refill.sh', executed with Cursor's home
        # directory as cwd -- not the absolute RUNTIME path every other test in this file uses.
        # Prove that exact configured invocation shape (relative path + the real
        # ~/.cursor/skills/keep-awake symlink layout) also works end to end.
        with tempfile.TemporaryDirectory() as directory:
            cursor_home = Path(directory)
            env, state_root, log = self.make_environment(cursor_home)
            skills_dir = cursor_home / "skills"
            skills_dir.mkdir()
            (skills_dir / "keep-awake").symlink_to(PLUGIN_DIR, target_is_directory=True)

            result = subprocess.run(
                ["./skills/keep-awake/scripts/hooks/keep-awake-refill.sh", "beforeSubmitPrompt"],
                input="{}",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cursor_home,
                check=False,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "{}\n")
            self.assertEqual(len(self.calls(log)), 1)
            self.assertEqual(self.state(state_root)["last_status"], "started")

    def test_overlapping_invocations_serialize_through_lock_and_fire_osascript_once(self):
        # Proves the finding-#3 fix: two hook invocations overlapping across the throttle
        # read-through-attempt-stamp-write critical section must not both fire an Apple Event.
        # A mkdir wrapper delays only the bare lock-acquisition mkdir call (not write_state's
        # "mkdir -p", which is left fast) so two independently-launched subprocesses reliably
        # collide on the real, atomic underlying mkdir syscall instead of racing on OS scheduling
        # luck alone.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, log = self.make_environment(root)
            # The lock only engages once a state root already exists (see acquire_lock's no-op
            # contract for a never-yet-attempted install); pre-seed it so both racers really
            # contend on the lock instead of skipping it.
            write_state(
                state_root / "state.json",
                last_attempt=0,
                last_success=0,
                lease_expiry=0,
                last_status="",
            )
            delayed_mkdir = root / "mock-mkdir-delay"
            write_executable(
                delayed_mkdir,
                """
                #!/bin/bash
                if [ "$1" = "-p" ]; then
                  exec /bin/mkdir "$@"
                fi
                sleep "${MOCK_MKDIR_LOCK_DELAY:-0}"
                exec /bin/mkdir "$@"
                """,
            )
            env["KEEP_AWAKE_MKDIR"] = str(delayed_mkdir)
            env["MOCK_MKDIR_LOCK_DELAY"] = "0.3"
            # Far past last_attempt=0 plus THROTTLE_SECONDS, so both racers would pass the
            # throttle check individually if the lock did not serialize them.
            env["KEEP_AWAKE_NOW"] = "1000"

            procs = [
                subprocess.Popen(
                    [str(RUNTIME), "beforeSubmitPrompt"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                for _ in range(2)
            ]
            results = [proc.communicate(input="{}", timeout=10) for proc in procs]
            for proc, (stdout, stderr) in zip(procs, results):
                self.assertEqual(proc.returncode, 0, stderr)
                self.assertEqual(stdout, "{}\n")

            # Exactly one racer won the lock and fired the single Apple Event; the other detected
            # the live lock and failed open without ever invoking osascript.
            self.assertEqual(len(self.calls(log)), 1)
            state = self.state(state_root)
            self.assertEqual(state["last_attempt"], 1000)
            self.assertEqual(state["last_status"], "started")

    def test_started_and_refreshed_applescript_never_mention_closed_display_mode(self):
        # Regression guard for the operator's manually-set Amphetamine preference "Allow System to
        # Sleep When Display is Closed" (Preferences -> Sessions -> checkbox). That preference is a
        # wholly separate Amphetamine API surface from displaySleepAllowed and "prevent screen
        # saver" above: per manage.py's closed_display_mode_status() docstring, its own sdef getter
        # is the read-only `closed display mode enabled`, and its *mutating* setters are `enable
        # closed display mode` / `disable closed display mode` -- commands this runtime hook must
        # never send in either branch that actually issues an Apple Event (session creation
        # ("started", remaining is -3) or session recreation ("refreshed", remaining <=
        # refreshThresholdSeconds)), since either would risk the unattended one-time system-warning
        # dialog Amphetamine's own docs warn about (see SKILL.md's "Preferences -> Sessions"
        # section). This captures the REAL AppleScript text handed to osascript for both branches
        # (not just a static grep of this file), so a future edit that starts conditionally
        # injecting a closed-display-mode call would fail this test even if it left every other
        # assertion in this file untouched.
        forbidden_phrases = (
            "closed display mode",
            "enable closed display mode",
            "disable closed display mode",
        )

        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            env["MOCK_SESSION_CODE"] = "-3"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.state(state_root)["last_status"], "started")
            started_source = self.calls(log)[-1]["source"].lower()
            for phrase in forbidden_phrases:
                self.assertNotIn(phrase, started_source)

        with tempfile.TemporaryDirectory() as directory:
            env, state_root, log = self.make_environment(Path(directory))
            # Same near-expiry setup as test_matching_owned_finite_session_near_expiry_refreshes:
            # remaining(8) <= refresh threshold (2 * 5s throttle = 10) forces the teardown/rebuild
            # "refreshed" path rather than the no-restart "preserved-owned" path.
            write_state(
                state_root / "state.json",
                last_attempt=90,
                last_success=50,
                lease_expiry=108,
                last_status="started",
            )
            env["MOCK_SESSION_CODE"] = "8"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.state(state_root)["last_status"], "refreshed")
            refreshed_source = self.calls(log)[-1]["source"].lower()
            for phrase in forbidden_phrases:
                self.assertNotIn(phrase, refreshed_source)

    def test_caffeinate_cold_start_spawns_process(self):
        with tempfile.TemporaryDirectory() as directory:
            env, state_root, _log = self.make_environment(Path(directory))
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "start")
            argv = events[0]["argv"].split()
            # -d and -i retain the existing display/idle assertions; -s adds PreventSystemSleep
            # while on AC so Maintenance Sleep cannot bypass those idle-only assertion classes.
            self.assertIn("-d", argv)
            self.assertIn("-i", argv)
            self.assertIn("-s", argv)
            self.assertEqual(argv[argv.index("-t") + 1], "120")

            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], events[0]["pid"])
            self.assertEqual(caff_state["status"], "started")
            self.assertEqual(caff_state["expiry"], 100 + 120)
            self.assertTrue(pid_alive(caff_state["pid"]))

    def test_caffeinate_alive_and_owned_with_time_remaining_is_a_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            # expiry(300) - now(100) = 200, well above the refresh threshold (10): nothing to do.
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=300, status="started")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            # Only the manual seed's own start event -- no new spawn, no kill.
            self.assertEqual(len(events), 1)
            self.assertTrue(pid_alive(old_pid))
            self.assertEqual(
                self.caffeinate_state(state_root), {"pid": old_pid, "expiry": 300, "status": "started"}
            )

    def test_caffeinate_refresh_spawns_new_before_killing_old(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            # expiry(108) - now(100) = 8 <= refresh threshold (2 * 5s throttle = 10): due.
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=108, status="started")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            caffeinate_log = Path(env["MOCK_CAFFEINATE_LOG"])

            def old_was_killed() -> bool:
                return any(
                    e["event"] == "sigterm" and e["pid"] == old_pid
                    for e in self.caffeinate_events(caffeinate_log)
                )

            self.assertTrue(wait_until(old_was_killed), "old caffeinate never observed its SIGTERM")
            events = self.caffeinate_events(caffeinate_log)

            # The core property: the new process's own start log line appears BEFORE the old
            # process's sigterm log line -- overlap, not a gap.
            new_start_index = next(
                i for i, e in enumerate(events) if e["event"] == "start" and e["pid"] != old_pid
            )
            old_sigterm_index = next(
                i for i, e in enumerate(events) if e["event"] == "sigterm" and e["pid"] == old_pid
            )
            self.assertLess(new_start_index, old_sigterm_index)

            self.assert_caffeinate_pid_dead(old_pid)
            caff_state = self.caffeinate_state(state_root)
            self.assertNotEqual(caff_state["pid"], old_pid)
            self.assertEqual(caff_state["status"], "refreshed")
            self.assertEqual(caff_state["expiry"], 100 + 120)
            self.assertTrue(pid_alive(caff_state["pid"]))

    def test_caffeinate_failed_respawn_leaves_old_process_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=108, status="started")
            env["MOCK_CAFFEINATE_EXIT_IMMEDIATELY"] = "1"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            self.assertFalse(any(e["event"] == "sigterm" for e in events))
            self.assertTrue(pid_alive(old_pid))
            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], old_pid)
            self.assertEqual(caff_state["status"], "refresh-failed")
            self.assertEqual(caff_state["expiry"], 108)

    def test_caffeinate_startup_interruption_reaps_candidate_and_preserves_old(self):
        for target in ("hook", "launcher"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env, state_root, _log = self.make_environment(root)
                old_pid = self.spawn_mock_caffeinate(env)
                write_caffeinate_state(
                    state_root / "caffeinate.json", pid=old_pid, expiry=108, status="started"
                )
                ready = root / "startup-wait-ready"
                sleeper = root / "startup-sleep"
                write_executable(
                    sleeper,
                    r"""
                    #!/bin/bash
                    if [ "$1" = "0.05" ]; then
                      printf '%s\n' "$PPID" > "$MOCK_STARTUP_WAIT_READY"
                      /bin/sleep 0.25
                    else
                      exec /bin/sleep "$@"
                    fi
                    """,
                )
                env["KEEP_AWAKE_SLEEP"] = str(sleeper)
                env["MOCK_STARTUP_WAIT_READY"] = str(ready)
                hook = subprocess.Popen(
                    [str(RUNTIME), "beforeSubmitPrompt"], env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, start_new_session=True,
                )
                self.addCleanup(self._kill_and_reap, hook)
                self.assertTrue(wait_until(ready.exists), "startup wait was never entered")
                events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
                replacement = next(e["pid"] for e in events if e["event"] == "start" and e["pid"] != old_pid)
                os.kill(hook.pid if target == "hook" else int(ready.read_text()), signal.SIGTERM)
                stdout, stderr = hook.communicate(timeout=5)
                self.assertEqual(hook.returncode, 0, stderr)
                self.assertEqual(json.loads(stdout), {})
                self.assert_caffeinate_pid_dead(replacement)
                self.assertTrue(pid_alive(old_pid))
                self.assertEqual(self.caffeinate_state(state_root)["pid"], old_pid)

    def test_caffeinate_pid_reuse_by_unrelated_process_is_not_trusted_at_initial_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            unrelated = subprocess.Popen(["sleep", "300"])
            self.addCleanup(self._kill_and_reap, unrelated)
            # Tracked pid is genuinely alive but `ps` says it is not caffeinate -- simulates the
            # tracked pid having been recycled by the OS onto an unrelated process after a crash.
            write_caffeinate_state(
                state_root / "caffeinate.json", pid=unrelated.pid, expiry=108, status="started"
            )
            env["MOCK_PS_COMM"] = "unrelated-process"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            # Treated as not-owned -> cold-start branch: a brand new caffeinate is spawned and the
            # unrelated process is left completely alone (never signaled).
            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "start")
            self.assertNotEqual(events[0]["pid"], unrelated.pid)
            self.assertIsNone(unrelated.poll())
            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], events[0]["pid"])
            self.assertEqual(caff_state["status"], "started")

    def test_caffeinate_pid_reuse_is_rechecked_immediately_before_kill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=108, status="started")
            # First ps call (the initial ownership read) reports a match; every call after (the
            # re-check immediately before the kill) reports an unrelated process -- proves the
            # re-check, not just the initial read, is what gates the kill.
            env["MOCK_PS_FLIP_AFTER_CALLS"] = "1"
            env["MOCK_PS_COUNT_FILE"] = str(root / "ps-call-count")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            self.assertFalse(any(e["event"] == "sigterm" and e["pid"] == old_pid for e in events))
            self.assertTrue(pid_alive(old_pid))

            new_starts = [e for e in events if e["event"] == "start" and e["pid"] != old_pid]
            self.assertEqual(len(new_starts), 1)
            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], new_starts[0]["pid"])
            self.assertEqual(caff_state["status"], "refreshed")

    def test_caffeinate_killed_when_amphetamine_stops_even_while_throttled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=5000, status="started")
            # A fresh last_attempt means the AppleScript flow below would itself be throttled --
            # proves the caffeinate cleanup branch (placed before the throttle check) still runs.
            write_state(
                state_root / "state.json",
                last_attempt=100,
                last_success=100,
                lease_expiry=5000,
                last_status="started",
            )
            env["MOCK_PROCESS_RUNNING"] = "0"
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            caffeinate_log = Path(env["MOCK_CAFFEINATE_LOG"])

            def old_was_killed() -> bool:
                return any(
                    e["event"] == "sigterm" and e["pid"] == old_pid
                    for e in self.caffeinate_events(caffeinate_log)
                )

            self.assertTrue(wait_until(old_was_killed), "owned caffeinate was never killed")
            self.assert_caffeinate_pid_dead(old_pid)
            self.assertFalse((state_root / "caffeinate.json").exists())

    def test_caffeinate_killed_when_amphetamine_app_is_fully_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=5000, status="started")
            Path(env["KEEP_AWAKE_APP_PATH"]).rmdir()
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            caffeinate_log = Path(env["MOCK_CAFFEINATE_LOG"])

            def old_was_killed() -> bool:
                return any(
                    e["event"] == "sigterm" and e["pid"] == old_pid
                    for e in self.caffeinate_events(caffeinate_log)
                )

            self.assertTrue(wait_until(old_was_killed), "owned caffeinate was never killed")
            self.assert_caffeinate_pid_dead(old_pid)
            self.assertFalse((state_root / "caffeinate.json").exists())

    def test_caffeinate_missing_binary_preserves_existing_tracked_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, log = self.make_environment(root)
            old_pid = self.spawn_mock_caffeinate(env)
            write_caffeinate_state(state_root / "caffeinate.json", pid=old_pid, expiry=5000, status="started")
            env["KEEP_AWAKE_CAFFEINATE"] = str(root / "does-not-exist-caffeinate")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            # Old, still-genuinely-owned process is left completely alone (never signaled), and the
            # sidecar only gets an error status -- never a fabricated new pid.
            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            self.assertFalse(any(e["event"] == "sigterm" for e in events))
            self.assertTrue(pid_alive(old_pid))
            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], old_pid)
            self.assertEqual(caff_state["status"], "error-missing-binary")

            # The rest of the script (the AppleScript flow) is unaffected by the missing binary.
            self.assertEqual(len(self.calls(log)), 1)
            self.assertEqual(self.state(state_root)["last_status"], "started")

    def test_caffeinate_missing_binary_at_cold_start_writes_no_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, log = self.make_environment(root)
            env["KEEP_AWAKE_CAFFEINATE"] = str(root / "does-not-exist-caffeinate")
            result = self.run_hook(env, "beforeSubmitPrompt")
            self.assertEqual(result.returncode, 0, result.stderr)

            # Never invent a pid to satisfy the pid>0 schema: nothing was ever tracked, so nothing
            # gets written.
            self.assertFalse((state_root / "caffeinate.json").exists())
            self.assertEqual(len(self.calls(log)), 1)
            self.assertEqual(self.state(state_root)["last_status"], "started")

    def test_caffeinate_overlapping_invocations_never_double_spawn_or_kill(self):
        # Mirrors test_overlapping_invocations_serialize_through_lock_and_fire_osascript_once for
        # the caffeinate path: the caffeinate decide/spawn/kill block shares the same lock-protected
        # critical section, so two concurrent hook invocations must never both spawn or double-kill.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, state_root, _log = self.make_environment(root)
            write_state(
                state_root / "state.json",
                last_attempt=0,
                last_success=0,
                lease_expiry=0,
                last_status="",
            )
            delayed_mkdir = root / "mock-mkdir-delay"
            write_executable(
                delayed_mkdir,
                """
                #!/bin/bash
                if [ "$1" = "-p" ]; then
                  exec /bin/mkdir "$@"
                fi
                sleep "${MOCK_MKDIR_LOCK_DELAY:-0}"
                exec /bin/mkdir "$@"
                """,
            )
            env["KEEP_AWAKE_MKDIR"] = str(delayed_mkdir)
            env["MOCK_MKDIR_LOCK_DELAY"] = "0.3"
            env["KEEP_AWAKE_NOW"] = "1000"

            procs = [
                subprocess.Popen(
                    [str(RUNTIME), "beforeSubmitPrompt"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                for _ in range(2)
            ]
            results = [proc.communicate(input="{}", timeout=10) for proc in procs]
            for proc, (stdout, stderr) in zip(procs, results):
                self.assertEqual(proc.returncode, 0, stderr)
                self.assertEqual(stdout, "{}\n")

            # Exactly one racer won the lock and spawned exactly one caffeinate process; the loser
            # failed open without ever touching caffeinate.
            events = self.caffeinate_events(Path(env["MOCK_CAFFEINATE_LOG"]))
            starts = [e for e in events if e["event"] == "start"]
            self.assertEqual(len(starts), 1)
            self.assertTrue(pid_alive(starts[0]["pid"]))
            caff_state = self.caffeinate_state(state_root)
            self.assertEqual(caff_state["pid"], starts[0]["pid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
