#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


PLUGIN_DIR = Path(__file__).resolve().parents[1]
MANAGER_PATH = PLUGIN_DIR / "scripts" / "manage.py"

spec = importlib.util.spec_from_file_location("keep_awake_manage", MANAGER_PATH)
manage = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manage
spec.loader.exec_module(manage)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def plugin_copy(root: Path, expose: str) -> Path:
    """Copy the plugin with an explicit `expose:` so dispatcher tests do not depend on live meta."""
    target = root / "plugin-copy" / PLUGIN_DIR.name
    shutil.copytree(PLUGIN_DIR, target, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    meta = target / "meta.yml"
    lines = [
        f"expose: {expose}" if line.startswith("expose:") else line
        for line in meta.read_text(encoding="utf-8").splitlines()
    ]
    meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_fake_osascript(path: Path, output: str, exit_code: int = 0) -> None:
    """Stand in for /usr/bin/osascript, pointed at via KEEP_AWAKE_OSASCRIPT.

    Mirrors test_runtime.py's fake-osascript executables (a small Python script reading stdin and
    printing a canned response) so closed-display-mode probes can be exercised without a real
    Amphetamine/osascript on the CI Linux runner.
    """
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdin.read()\n"
        f"print({output!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_fake_ps(path: Path, comm: str) -> None:
    """Stand in for /bin/ps, pointed at via KEEP_AWAKE_PS -- the same override the runtime hook's
    own caffeinate_alive_and_owned() uses. Always prints a fixed `comm` value regardless of the pid
    argument, decoupling "is this pid alive" (checked for real via os.kill, unmocked) from "does
    ps say it's ours" (fully controllable here).
    """
    path.write_text(f"#!/usr/bin/env python3\nprint({comm!r})\n", encoding="utf-8")
    path.chmod(0o755)


def dead_pid() -> int:
    """A pid guaranteed not to correspond to any running process: spawn a trivial, instantly-
    exiting child and wait for it to be reaped, so os.kill(pid, 0) reliably raises
    ProcessLookupError afterward (no os.kill mocking needed).
    """
    proc = subprocess.Popen(["true"])
    proc.wait(timeout=5)
    return proc.pid


class ManageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = manage.load_json(PLUGIN_DIR / "plugin.json")

    def prepare_home(self, root: Path, hooks: dict | None = None) -> tuple[Path, Path, Path]:
        cursor = root / ".cursor"
        skills = cursor / "skills"
        skills.mkdir(parents=True)
        (skills / "keep-awake").symlink_to(PLUGIN_DIR, target_is_directory=True)
        hooks_path = cursor / "hooks.json"
        if hooks is not None:
            write_json(hooks_path, hooks)
        state = root / "state"
        return cursor, hooks_path, state

    def env(self, cursor: Path, state: Path, root: Path, platform: str = "darwin"):
        return mock.patch.dict(
            os.environ,
            {
                "KEEP_AWAKE_CURSOR_HOME": str(cursor),
                "KEEP_AWAKE_STATE_ROOT": str(state),
                "KEEP_AWAKE_APP_PATH": str(root / "missing-Amphetamine.app"),
                "KEEP_AWAKE_PROCESS_RUNNING": "0",
                "KEEP_AWAKE_PLATFORM": platform,
                "KEEP_AWAKE_NOW": "10000",
                # Existing lifecycle tests isolate hooks/state behavior. Dedicated tests below
                # exercise the real local-jobs integration in a hermetic temporary state root.
                "KEEP_AWAKE_LOCAL_JOBS_DISABLE": "1",
            },
            clear=False,
        )

    def quiet(self):
        return contextlib.redirect_stdout(io.StringIO())

    @staticmethod
    def _kill_and_reap(proc: subprocess.Popen) -> None:
        # Mirrors test_runtime.py's _kill_and_reap: a bare proc.kill() at teardown leaves a
        # reapable zombie (surfaces as a noisy ResourceWarning) until this test process exits.
        # wait() is a harmless no-op for a pid a test already terminated and reaped itself.
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def test_descriptor_hash_matches_meta(self):
        self.assertEqual(manage.validate_descriptor(self.descriptor), [])
        self.assertEqual(
            manage.canonical_json_hash(),
            manage.meta_field("descriptor_ref"),
        )

    def test_bash_runtime_reads_back_the_same_numeric_fields_manage_py_writes(self):
        # Guard-rail for the documented state.json schema duplication (manage.py's full Python
        # writer/validator vs. keep-awake-refill.sh's dependency-free bash sed/regex extraction of
        # the 3 numeric fields it actually consumes). Deliberately not unified -- the bash hot path
        # stays dependency-free -- so this instead extracts the CURRENT is_uint/read_state_number
        # function bodies straight out of the real runtime script (not a hardcoded copy, so a
        # future edit to the regex is exercised here too) and proves they read back exactly what
        # manage.py's own writer produced.
        runtime_source = manage.RUNTIME_PATH.read_text(encoding="utf-8")

        def extract_function(name: str) -> str:
            start = runtime_source.index(f"{name}() {{")
            end = runtime_source.index("\n}\n", start) + len("\n}")
            return runtime_source[start:end]

        harness = "\n".join(
            [
                "#!/bin/bash",
                "set -u",
                'SED="${KEEP_AWAKE_SED:-/usr/bin/sed}"',
                'STATE_FILE="$1"',
                extract_function("is_uint"),
                extract_function("read_state_number"),
                "for key in last_attempt last_success lease_expiry; do",
                '  read_state_number "$key"',
                "done",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness_path = root / "harness.sh"
            harness_path.write_text(harness, encoding="utf-8")
            harness_path.chmod(0o755)

            state_file = root / "state" / "state.json"
            written = {
                "last_attempt": 1753600000,
                "last_success": 1753599950,
                "lease_expiry": 1753601150,
                "last_status": "started",
                "last_error": "",
            }
            manage.atomic_write_state(state_file, written)

            result = subprocess.run(
                [str(harness_path), str(state_file)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            read_back = [int(line) for line in result.stdout.splitlines()]
            self.assertEqual(
                read_back,
                [written["last_attempt"], written["last_success"], written["lease_expiry"]],
            )

    def test_validate_descriptor_rejects_state_root_without_leading_tilde_or_slash(self):
        # Mirrors the runtime hook's own leading ~/ or / requirement (keep-awake-refill.sh); a
        # descriptor that violates it must fail loudly here instead of the runtime silently
        # no-op'ing forever.
        bad = dict(self.descriptor, stateRoot="relative/not-rooted")
        errors = manage.validate_descriptor(bad)
        self.assertTrue(any("stateRoot" in error for error in errors))

    def test_validate_descriptor_accepts_absolute_state_root(self):
        good = dict(self.descriptor, stateRoot="/tmp/keep-awake-state")
        self.assertEqual(manage.validate_descriptor(good), [])

    def test_legacy_descriptor_uses_safe_maintenance_defaults(self):
        legacy = dict(self.descriptor)
        legacy.pop("maintenanceEnabled", None)
        legacy.pop("maintenanceIntervalSeconds", None)
        legacy.pop("activityWindowSeconds", None)
        self.assertEqual(manage.validate_descriptor(legacy), [])
        self.assertEqual(manage.maintenance_config(legacy), (False, 300, 14400))

    def test_validate_descriptor_rejects_invalid_maintenance_bounds(self):
        bad = dict(
            self.descriptor,
            maintenanceEnabled="true",
            maintenanceIntervalSeconds=59,
            activityWindowSeconds=0,
        )
        errors = manage.validate_descriptor(bad)
        self.assertTrue(any("maintenanceEnabled" in error for error in errors))
        self.assertTrue(any("maintenanceIntervalSeconds" in error for error in errors))
        self.assertTrue(any("activityWindowSeconds" in error for error in errors))

    def test_apply_creates_exact_stable_link_rows_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                self.assertEqual(manage.run_apply(), 0)

            data = read_json(hooks_path)
            expected = manage.desired_hook_rows(self.descriptor)
            self.assertEqual(data["hooks"]["beforeSubmitPrompt"], [expected["beforeSubmitPrompt"]])
            self.assertEqual(data["hooks"]["preToolUse"], [expected["preToolUse"]])
            self.assertEqual(
                expected["beforeSubmitPrompt"]["command"],
                "./skills/keep-awake/scripts/hooks/keep-awake-refill.sh beforeSubmitPrompt",
            )
            self.assertEqual(
                expected["preToolUse"]["command"],
                "./skills/keep-awake/scripts/hooks/keep-awake-refill.sh preToolUse",
            )
            self.assertFalse(hooks_path.with_name(hooks_path.name + manage.BACKUP_SUFFIX).exists())

    def test_apply_run_and_uninstall_maintenance_job_through_real_local_jobs(self):
        local_jobs = PLUGIN_DIR.parents[1] / "skills" / "local-jobs" / "scripts" / "local-jobs.sh"
        self.assertTrue(local_jobs.is_file(), local_jobs)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            local_state = root / "local-jobs"
            local_state.mkdir()
            (local_state / "config.yml").write_text(
                "label_root: org.example.keep-awake-tests\n",
                encoding="utf-8",
            )
            launch_agents = root / "LaunchAgents"
            with self.env(cursor, state, root):
                os.environ.pop("KEEP_AWAKE_LOCAL_JOBS_DISABLE", None)
                os.environ.update(
                    {
                        "KEEP_AWAKE_LOCAL_JOBS": str(local_jobs),
                        "LOCAL_JOBS_STATE": str(local_state),
                        "LOCAL_JOBS_LAUNCHAGENTS_DIR": str(launch_agents),
                        "LOCAL_JOBS_LAUNCHD_DISABLE": "1",
                        # The co-located wrapper intentionally strips harness overrides
                        # unless this fixture-only opt-in is explicit.
                        "LOCAL_JOBS_PRESERVE_HARNESS_ENV": "1",
                        "LOCAL_JOBS_PYTHON": sys.executable,
                    }
                )
                with self.quiet():
                    self.assertEqual(manage.run_apply(), 0)

                view = subprocess.run(
                    [str(local_jobs), "view-jobs", "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=os.environ.copy(),
                    timeout=15,
                )
                self.assertEqual(view.returncode, 0, view.stderr)
                payload = json.loads(view.stdout)
                rows = [
                    row
                    for row in payload["instances"]
                    if row.get("id") == manage.MAINTENANCE_JOB_ID
                ]
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["type"], "command")
                self.assertEqual(row["program"], str(manage.maintenance_program_path()))
                self.assertEqual(row["args"], [])
                self.assertEqual(row["schedule"]["seconds"], 300)
                self.assertEqual(
                    row["launchd_label"],
                    "org.example.keep-awake-tests.command.keep-awake-maintenance",
                )

                with contextlib.redirect_stdout(io.StringIO()) as doctor_output:
                    self.assertEqual(manage.run_doctor(), 0)
                self.assertIn("maintenance timer:", doctor_output.getvalue())
                self.assertIn("Cursor activity lease: not yet observed", doctor_output.getvalue())
                self.assertFalse(state.exists())

                run = subprocess.run(
                    [
                        str(local_jobs),
                        "run-job",
                        "--type",
                        "command",
                        "--id",
                        manage.MAINTENANCE_JOB_ID,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=os.environ.copy(),
                    timeout=15,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("{}\n", run.stdout)
                self.assertIn('"status":"success"', run.stdout)

                with self.quiet():
                    self.assertEqual(manage.run_uninstall(), 0)
                view_after = subprocess.run(
                    [str(local_jobs), "view-jobs", "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=os.environ.copy(),
                    timeout=15,
                )
                self.assertEqual(view_after.returncode, 0, view_after.stderr)
                remaining = [
                    row
                    for row in json.loads(view_after.stdout)["instances"]
                    if row.get("id") == manage.MAINTENANCE_JOB_ID
                ]
                self.assertEqual(remaining, [])
                self.assertTrue(hooks_path.exists())

    def test_maintenance_reconciliation_fails_closed_on_degraded_local_jobs_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, _hooks_path, state = self.prepare_home(root)
            fake = root / "local-jobs"
            fake.write_text(
                "#!/bin/bash\n"
                'if [ "$1" = "view-jobs" ]; then printf "not-json\\n"; exit 0; fi\n'
                "exit 0\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            with self.env(cursor, state, root):
                os.environ.pop("KEEP_AWAKE_LOCAL_JOBS_DISABLE", None)
                os.environ["KEEP_AWAKE_LOCAL_JOBS"] = str(fake)
                with self.assertRaises(manage.LifecycleError):
                    manage.reconcile_maintenance_job(self.descriptor)

    def test_apply_refuses_malformed_hooks_without_clobbering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            hooks_path.write_text("{ definitely-not-json\n", encoding="utf-8")
            before = hooks_path.read_bytes()
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 1)
            self.assertEqual(hooks_path.read_bytes(), before)
            self.assertFalse(hooks_path.with_name(hooks_path.name + manage.BACKUP_SUFFIX).exists())

    def test_apply_dedupes_owned_rows_and_prunes_only_exact_legacy_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            legacy = manage.legacy_hook_rows(cursor)
            near_legacy = dict(legacy["beforeSubmitPrompt"], extra="preserve-me")
            original = {
                "version": 1,
                "custom": {"preserve": True},
                "hooks": {
                    "beforeSubmitPrompt": [
                        {"command": "unrelated-before"},
                        {"description": self.descriptor["marker"], "command": "old-one"},
                        {"description": self.descriptor["marker"], "command": "old-two"},
                        legacy["beforeSubmitPrompt"],
                        near_legacy,
                    ],
                    "preToolUse": [
                        {"command": "unrelated-tool"},
                        {"description": self.descriptor["marker"], "command": "old-tool"},
                    ],
                    "stop": [{"command": "unrelated-stop"}, legacy["stop"]],
                    "afterFileEdit": [
                        {"description": self.descriptor["marker"], "command": "wrong-event"}
                    ],
                },
            }
            write_json(hooks_path, original)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)

            data = read_json(hooks_path)
            all_rows = [row for rows in data["hooks"].values() for row in rows]
            owned = [row for row in all_rows if row.get("description") == self.descriptor["marker"]]
            self.assertEqual(len(owned), 2)
            self.assertIn({"command": "unrelated-before"}, data["hooks"]["beforeSubmitPrompt"])
            self.assertIn({"command": "unrelated-tool"}, data["hooks"]["preToolUse"])
            self.assertIn({"command": "unrelated-stop"}, data["hooks"]["stop"])
            self.assertIn(near_legacy, data["hooks"]["beforeSubmitPrompt"])
            self.assertNotIn(legacy["beforeSubmitPrompt"], data["hooks"]["beforeSubmitPrompt"])
            self.assertNotIn(legacy["stop"], data["hooks"]["stop"])
            self.assertNotIn("afterFileEdit", data["hooks"])
            self.assertEqual(data["custom"], {"preserve": True})
            backup = hooks_path.with_name(hooks_path.name + manage.BACKUP_SUFFIX)
            self.assertEqual(read_json(backup), original)

    def test_cas_retry_preserves_concurrent_unrelated_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(
                root,
                {"version": 1, "hooks": {"sessionStart": [{"command": "existing"}]}},
            )
            injected = False

            def concurrent_write(path: Path, _attempt: int) -> None:
                nonlocal injected
                if injected:
                    return
                injected = True
                current = read_json(path)
                current["hooks"]["postToolUse"] = [{"command": "concurrent"}]
                write_json(path, current)

            with self.env(cursor, state, root):
                changed, _ = manage.reconcile_hooks(
                    self.descriptor,
                    install=True,
                    remove_legacy=True,
                    path=hooks_path,
                    pre_commit=concurrent_write,
                )
            self.assertTrue(changed)
            data = read_json(hooks_path)
            self.assertEqual(data["hooks"]["postToolUse"], [{"command": "concurrent"}])
            self.assertEqual(data["hooks"]["sessionStart"], [{"command": "existing"}])

    def test_doctor_flags_near_miss_legacy_row_that_survived_removal(self):
        # Regression: removal and doctor used to share the same exact-match check, so a near-miss
        # legacy row (hand-edited, or a predecessor-version shape) that survives removal was also
        # invisible to doctor. doctor must flag it via the looser signature match even though
        # removal correctly leaves it alone (removal stays conservatively exact-match-only).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            legacy = manage.legacy_hook_rows(cursor)
            near_legacy = dict(legacy["beforeSubmitPrompt"], extra="preserve-me")
            write_json(
                hooks_path,
                {"version": 1, "hooks": {"beforeSubmitPrompt": [near_legacy]}},
            )
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            data = read_json(hooks_path)
            self.assertIn(near_legacy, data["hooks"]["beforeSubmitPrompt"])
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            self.assertIn("legacy-signature row", output.getvalue())

    def test_uninstall_removes_owned_and_predecessor_rows_and_state_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            legacy = manage.legacy_hook_rows(cursor)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            data = read_json(hooks_path)
            data["hooks"]["beforeSubmitPrompt"].append({"command": "unrelated"})
            data["hooks"]["stop"] = [legacy["stop"], {"command": "leave-stop"}]
            write_json(hooks_path, data)
            state.mkdir(parents=True)
            (state / "state.json").write_text(
                '{"last_attempt":1,"last_success":1,"lease_expiry":2,'
                '"last_status":"started","last_error":""}\n',
                encoding="utf-8",
            )
            write_json(state / "activity.json", {"last_hook_activity": 1})
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_uninstall(), 0)

            final = read_json(hooks_path)
            rows = [row for event_rows in final["hooks"].values() for row in event_rows]
            self.assertFalse(any(row.get("description") == self.descriptor["marker"] for row in rows))
            self.assertNotIn(legacy["stop"], final["hooks"].get("stop", []))
            self.assertIn({"command": "unrelated"}, final["hooks"]["beforeSubmitPrompt"])
            self.assertIn({"command": "leave-stop"}, final["hooks"]["stop"])
            self.assertFalse((state / "state.json").exists())
            self.assertFalse((state / "activity.json").exists())
            self.assertFalse((state / "stop.fence").exists())

    def test_uninstall_records_capability_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "capability-local.yml"
            cursor, _hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet(), mock.patch.dict(
                os.environ, {"CAPABILITY_LOCAL_REGISTRY": str(registry)}
            ):
                self.assertEqual(manage.run_apply(), 0)
                self.assertEqual(manage.run_uninstall(), 0)
            self.assertTrue(registry.is_file())
            self.assertIn("keep-awake", registry.read_text(encoding="utf-8"))

    def test_uninstall_fails_when_opt_out_not_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, _hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet(), mock.patch.object(
                manage, "record_plugin_opt_out", return_value=False
            ):
                self.assertEqual(manage.run_apply(), 0)
                self.assertEqual(manage.run_uninstall(), 1)

    def test_uninstall_holds_stop_fence_across_timer_and_runtime_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            observed: list[str] = []

            def observe(stage: str, result):
                def inner(*_args, **_kwargs):
                    self.assertTrue(manage.stop_fence_path(self.descriptor).exists())
                    observed.append(stage)
                    return result

                return inner

            with self.env(cursor, state, root), mock.patch.object(
                manage,
                "remove_maintenance_job",
                side_effect=observe("timer", "removed maintenance timer"),
            ), mock.patch.object(
                manage,
                "reconcile_hooks",
                side_effect=observe("hooks", (True, "updated hooks")),
            ), mock.patch.object(
                manage,
                "uninstall_caffeinate_state",
                side_effect=observe("caffeinate", "no caffeinate"),
            ), mock.patch.object(
                manage,
                "remove_owned_state",
                side_effect=observe("state", False),
            ), mock.patch.object(
                manage,
                "remove_activity_state",
                side_effect=observe("activity", False),
            ), self.quiet():
                self.assertEqual(manage.run_uninstall(), 0)

            self.assertEqual(observed, ["timer", "hooks", "caffeinate", "state", "activity"])
            self.assertFalse(manage.stop_fence_path(self.descriptor).exists())

    def test_uninstall_timer_failure_leaves_fence_and_runtime_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            before = hooks_path.read_bytes()
            with self.env(cursor, state, root), mock.patch.object(
                manage,
                "remove_maintenance_job",
                side_effect=manage.LifecycleError("local-jobs unavailable"),
            ), mock.patch.object(manage, "reconcile_hooks") as reconcile, self.quiet():
                self.assertEqual(manage.run_uninstall(), 1)
            reconcile.assert_not_called()
            self.assertEqual(hooks_path.read_bytes(), before)
            self.assertTrue((state / "stop.fence").exists())

    def test_non_darwin_apply_removes_owned_rows_but_preserves_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            legacy = manage.legacy_hook_rows(cursor)
            write_json(
                hooks_path,
                {
                    "version": 1,
                    "hooks": {
                        "beforeSubmitPrompt": [
                            {"description": self.descriptor["marker"], "command": "owned"},
                            legacy["beforeSubmitPrompt"],
                            {"command": "unrelated"},
                        ]
                    },
                },
            )
            with self.env(cursor, state, root, platform="linux"), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            rows = read_json(hooks_path)["hooks"]["beforeSubmitPrompt"]
            self.assertIn(legacy["beforeSubmitPrompt"], rows)
            self.assertIn({"command": "unrelated"}, rows)
            self.assertFalse(any(row.get("description") == self.descriptor["marker"] for row in rows))

    def test_non_darwin_apply_is_inert_when_hooks_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root, platform="linux"), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            self.assertFalse(hooks_path.exists())

    def test_fresh_machine_doctor_is_read_only_and_amphetamine_absence_is_dormant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            before = hooks_path.read_bytes()
            backup = hooks_path.with_name(hooks_path.name + manage.BACKUP_SUFFIX)
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 0)
            self.assertIn("READY but dormant", output.getvalue())
            self.assertEqual(hooks_path.read_bytes(), before)
            self.assertFalse(backup.exists())
            self.assertFalse(state.exists())

    def test_install_dispatcher_supports_fresh_machine_without_amphetamine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            plugin = plugin_copy(root, "cursor")
            (cursor / "skills" / "keep-awake").unlink()
            (cursor / "skills" / "keep-awake").symlink_to(plugin, target_is_directory=True)
            with self.env(cursor, state, root):
                env = os.environ.copy()
                apply_result = subprocess.run(
                    ["bash", str(plugin / "install.sh"), "--apply"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                )
                doctor_result = subprocess.run(
                    ["bash", str(plugin / "install.sh"), "--doctor"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                )
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            self.assertEqual(doctor_result.returncode, 0, doctor_result.stderr)
            self.assertIn("READY but dormant", doctor_result.stdout)
            self.assertTrue(hooks_path.exists())
            self.assertFalse(state.exists())

    def test_install_dispatcher_expose_none_installs_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            plugin = plugin_copy(root, "none")
            with self.env(cursor, state, root):
                env = os.environ.copy()
                results = {
                    action: subprocess.run(
                        ["bash", str(plugin / "install.sh"), f"--{action}"],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                        check=False,
                    )
                    for action in ("apply", "repair", "doctor")
                }
            for action, result in results.items():
                self.assertEqual(result.returncode, 0, f"{action}: {result.stderr}")
                self.assertIn("not installed locally", result.stdout)
            self.assertFalse(hooks_path.exists())
            self.assertFalse(state.exists())

    def test_doctor_reports_installed_but_quit_as_ready_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, _hooks_path, state = self.prepare_home(root)
            app = root / "Amphetamine.app"
            app.mkdir()
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_APP_PATH"] = str(app)
                with self.quiet():
                    self.assertEqual(manage.run_apply(), 0)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(manage.run_doctor(), 0)
            self.assertIn("READY but inactive", output.getvalue())

    def test_closed_display_mode_status_never_launches_amphetamine_when_not_running(self):
        # Safety-critical guard: `tell application id` on a not-running app auto-launches it, which
        # would silently violate plugin.json's backend.autoLaunch:false merely by running doctor.
        # The fake osascript would answer "true" (and prove it ran) if ever invoked; it must not be.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            osascript = root / "fake-osascript"
            write_fake_osascript(osascript, "true")
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_PROCESS_RUNNING"] = "0"
                os.environ["KEEP_AWAKE_OSASCRIPT"] = str(osascript)
                status = manage.closed_display_mode_status(self.descriptor)
            self.assertEqual(status, "unknown")

    def test_doctor_reports_closed_display_mode_healthy_when_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            app = root / "Amphetamine.app"
            app.mkdir()
            osascript = root / "fake-osascript"
            write_fake_osascript(osascript, "true")
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_APP_PATH"] = str(app)
                with self.quiet():
                    self.assertEqual(manage.run_apply(), 0)
                os.environ["KEEP_AWAKE_PROCESS_RUNNING"] = "1"
                os.environ["KEEP_AWAKE_OSASCRIPT"] = str(osascript)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(manage.run_doctor(), 0)
            rendered = output.getvalue()
            self.assertIn("READY: Amphetamine is running", rendered)
            self.assertIn("OK   Mac will not sleep on display/lid close", rendered)
            self.assertNotIn("WARN", rendered)

    def test_doctor_warns_when_closed_display_mode_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            app = root / "Amphetamine.app"
            app.mkdir()
            osascript = root / "fake-osascript"
            write_fake_osascript(osascript, "false")
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_APP_PATH"] = str(app)
                with self.quiet():
                    self.assertEqual(manage.run_apply(), 0)
                os.environ["KEEP_AWAKE_PROCESS_RUNNING"] = "1"
                os.environ["KEEP_AWAKE_OSASCRIPT"] = str(osascript)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(manage.run_doctor(), 0)
            rendered = output.getvalue()
            self.assertIn("READY: Amphetamine is running", rendered)
            self.assertIn("WARN the Mac WILL sleep when the display/lid is closed", rendered)
            self.assertIn("Allow System to Sleep When Display is Closed", rendered)
            self.assertIn("Do Not Show This Message Again", rendered)

    def test_doctor_closed_display_mode_check_is_fail_safe_on_osascript_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            app = root / "Amphetamine.app"
            app.mkdir()
            osascript = root / "fake-osascript"
            write_fake_osascript(osascript, "Not authorized to send Apple events.", exit_code=1)
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_APP_PATH"] = str(app)
                with self.quiet():
                    self.assertEqual(manage.run_apply(), 0)
                os.environ["KEEP_AWAKE_PROCESS_RUNNING"] = "1"
                os.environ["KEEP_AWAKE_OSASCRIPT"] = str(osascript)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(manage.run_doctor(), 0)
            rendered = output.getvalue()
            self.assertIn("READY: Amphetamine is running", rendered)
            self.assertNotIn("WARN", rendered)
            self.assertNotIn("OK   Mac will not sleep", rendered)

    def test_repair_refuses_malformed_hooks_without_touching_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            hooks_path.write_text("{bad\n", encoding="utf-8")
            before = hooks_path.read_bytes()
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_repair(), 1)
            self.assertEqual(hooks_path.read_bytes(), before)
            self.assertFalse(state.exists())

    def test_repair_clears_only_an_expired_ownership_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "state.json",
                    {
                        "last_attempt": 9900,
                        "last_success": 9800,
                        "lease_expiry": 9999,
                        "last_status": "started",
                        "last_error": "",
                    },
                )
                self.assertEqual(manage.run_repair(), 0)
            repaired = read_json(state / "state.json")
            self.assertEqual(repaired["lease_expiry"], 0)
            self.assertEqual(repaired["last_status"], "ownership-expired")

    def test_clear_expired_ownership_cas_retries_around_concurrent_runtime_write(self):
        # Regression for the state-json-repair TOCTOU finding: a concurrent runtime write landing
        # between clear_expired_ownership()'s read and write must not be silently clobbered.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            state_file = state / "state.json"
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state_file,
                    {
                        "last_attempt": 9900,
                        "last_success": 9800,
                        "lease_expiry": 9999,
                        "last_status": "started",
                        "last_error": "",
                    },
                )
                injected = False

                def concurrent_runtime_write(_path: Path, _attempt: int) -> None:
                    nonlocal injected
                    if injected:
                        return
                    injected = True
                    manage.atomic_write_state(
                        state_file,
                        {
                            "last_attempt": 10500,
                            "last_success": 10500,
                            "lease_expiry": 11700,
                            "last_status": "refreshed",
                            "last_error": "",
                        },
                    )

                changed, message = manage.clear_expired_ownership(
                    self.descriptor, pre_commit=concurrent_runtime_write
                )
            # The fingerprint check must detect the concurrent write and retry with a fresh read;
            # the fresh read shows a now-current (non-expired) lease, so the correct outcome is
            # "declined, already current" -- NOT a forced write of the stale pre-race payload.
            self.assertTrue(injected)
            self.assertFalse(changed)
            self.assertEqual(message, "owned state is current")
            final = read_json(state_file)
            # The concurrent runtime write's fresher lease must survive untouched; a TOCTOU bug
            # would instead force through the stale payload and clobber it to "ownership-expired".
            self.assertEqual(final["last_status"], "refreshed")
            self.assertEqual(final["lease_expiry"], 11700)

    def test_recent_actual_hook_tcc_error_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "state.json",
                    {
                        "last_attempt": 10000,
                        "last_success": 0,
                        "lease_expiry": 0,
                        "last_status": "error",
                        "last_error": "Not authorized to send Apple events. (-1743)",
                    },
                )
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            self.assertIn("Apple Events (TCC) permission error", output.getvalue())

    def test_recent_non_tcc_hook_error_is_still_surfaced_by_doctor(self):
        # Regression for the P1 finding: doctor's error surfacing used to be keyword-gated to
        # TCC tokens, so an unrecognized osascript/Amphetamine failure (the runtime's catch-all
        # "unexpected osascript response" branch) never reached doctor output. Any recent
        # last_status=="error" must be reported, TCC-shaped or not.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "state.json",
                    {
                        "last_attempt": 10000,
                        "last_success": 0,
                        "lease_expiry": 0,
                        "last_status": "error",
                        "last_error": "unexpected osascript response: mystery-outcome|42",
                    },
                )
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            rendered = output.getvalue()
            self.assertIn("unexpected osascript response: mystery-outcome|42", rendered)
            self.assertNotIn("TCC) permission error", rendered)

    def test_doctor_reports_missing_stable_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            link = cursor / "skills" / "keep-awake"
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            link.unlink()
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            self.assertIn(f"stable Cursor link is missing: {link}", output.getvalue())

    def test_doctor_reports_wrong_target_stable_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            link = cursor / "skills" / "keep-awake"
            wrong_target = root / "not-keep-awake"
            wrong_target.mkdir()
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            link.unlink()
            link.symlink_to(wrong_target, target_is_directory=True)
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            self.assertIn(f"stable Cursor link resolves to the wrong source: {link}", output.getvalue())

    def test_doctor_reports_dangling_stable_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            link = cursor / "skills" / "keep-awake"
            dangling_target = root / "does-not-exist"
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            link.unlink()
            link.symlink_to(dangling_target, target_is_directory=True)
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            self.assertIn("stable Cursor link is broken", output.getvalue())

    def test_validate_descriptor_rejects_non_boolean_caffeinate_supplement_enabled(self):
        bad = dict(self.descriptor, caffeinateSupplementEnabled="true")
        errors = manage.validate_descriptor(bad)
        self.assertTrue(any("caffeinateSupplementEnabled" in error for error in errors))

    def test_validate_caffeinate_state_rejects_non_positive_pid(self):
        # validate_caffeinate_state still returns the parsed dict alongside errors (mirroring
        # validate_owned_state) -- callers gate on `errors`/`data is None`, not on data's absence.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "caffeinate.json"
            for bad_pid in (0, -1, True):
                with self.subTest(pid=bad_pid):
                    write_json(path, {"pid": bad_pid, "expiry": 100, "status": "started"})
                    data, errors = manage.validate_caffeinate_state(path)
                    self.assertTrue(any("pid must be a positive integer" in error for error in errors))

            manage.atomic_write_state(path, {"pid": 123, "expiry": 100, "status": "started"})
            data, errors = manage.validate_caffeinate_state(path)
            self.assertEqual(errors, [])
            self.assertEqual(data["pid"], 123)

    def test_validate_caffeinate_state_rejects_schema_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "caffeinate.json"
            write_json(path, {"pid": 123, "expiry": 100, "status": "started", "extra": "field"})
            _, errors = manage.validate_caffeinate_state(path)
            self.assertTrue(any("fields do not match the bounded schema" in error for error in errors))

    def test_validate_activity_state_enforces_bounded_exact_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.json"
            write_json(path, {"last_hook_activity": 123})
            path.chmod(0o600)
            data, errors = manage.validate_activity_state(path)
            self.assertEqual(errors, [])
            self.assertEqual(data, {"last_hook_activity": 123})

            write_json(path, {"last_hook_activity": -1, "extra": True})
            path.chmod(0o600)
            _, errors = manage.validate_activity_state(path)
            self.assertTrue(any("fields do not match the bounded schema" in error for error in errors))
            self.assertTrue(any("non-negative integer" in error for error in errors))

    def test_caffeinate_process_identity_matches_accepts_bare_name_and_full_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, comm in enumerate(("caffeinate", "/usr/bin/caffeinate")):
                with self.subTest(comm=comm):
                    fake_ps = root / f"fake-ps-{index}"
                    write_fake_ps(fake_ps, comm)
                    with mock.patch.dict(os.environ, {"KEEP_AWAKE_PS": str(fake_ps)}, clear=False):
                        self.assertTrue(manage.caffeinate_process_identity_matches(12345))
            fake_ps_bad = root / "fake-ps-bad"
            write_fake_ps(fake_ps_bad, "not-caffeinate")
            with mock.patch.dict(os.environ, {"KEEP_AWAKE_PS": str(fake_ps_bad)}, clear=False):
                self.assertFalse(manage.caffeinate_process_identity_matches(12345))

    def test_doctor_reports_caffeinate_disabled_via_descriptor(self):
        disabled = dict(self.descriptor, caffeinateSupplementEnabled=False)
        line, errors = manage.describe_caffeinate_status(disabled, None)
        self.assertEqual(line, "caffeinate supplement: disabled via plugin.json")
        self.assertEqual(errors, [])

    def test_doctor_reports_caffeinate_cold_start_even_while_amphetamine_dormant(self):
        # self.env()'s KEEP_AWAKE_APP_PATH points at a nonexistent app -- Amphetamine "dormant" --
        # proving the caffeinate line is unconditional, not nested inside the READY-and-running
        # branch.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 0)
            rendered = output.getvalue()
            self.assertIn("READY but dormant", rendered)
            self.assertIn("caffeinate supplement: not yet tracked (cold start)", rendered)

    def test_doctor_flags_mismatch_when_tracked_caffeinate_pid_is_dead(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "caffeinate.json",
                    {"pid": dead_pid(), "expiry": 20000, "status": "started"},
                )
            with self.env(cursor, state, root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage.run_doctor(), 1)
            rendered = output.getvalue()
            self.assertIn("READY but dormant", rendered)
            self.assertIn("is tracked but NOT alive/owned", rendered)
            self.assertIn("FAIL caffeinate supplement mismatch", rendered)

    def test_doctor_reports_alive_and_owned_caffeinate_regardless_of_amphetamine_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            proc = subprocess.Popen(["sleep", "30"])
            self.addCleanup(self._kill_and_reap, proc)
            fake_ps = root / "fake-ps"
            write_fake_ps(fake_ps, "caffeinate")
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "caffeinate.json",
                    {"pid": proc.pid, "expiry": 20000, "status": "started"},
                )
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_PS"] = str(fake_ps)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(manage.run_doctor(), 0)
            rendered = output.getvalue()
            # Amphetamine is still dormant (self.env's default) -- alive/owned reporting does not
            # depend on Amphetamine's own install/run state.
            self.assertIn("READY but dormant", rendered)
            self.assertIn(f"pid {proc.pid} alive and owned", rendered)

    def test_uninstall_caffeinate_kill_is_non_fatal_and_does_not_block_rest_of_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            proc = subprocess.Popen(["sleep", "30"])
            self.addCleanup(self._kill_and_reap, proc)
            fake_ps = root / "fake-ps"
            write_fake_ps(fake_ps, "caffeinate")
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "caffeinate.json",
                    {"pid": proc.pid, "expiry": 20000, "status": "started"},
                )
                manage.atomic_write_state(
                    state / "state.json",
                    {
                        "last_attempt": 1,
                        "last_success": 1,
                        "lease_expiry": 2,
                        "last_status": "started",
                        "last_error": "",
                    },
                )
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_PS"] = str(fake_ps)
                with mock.patch("os.kill", side_effect=PermissionError), self.quiet():
                    self.assertEqual(manage.run_uninstall(), 0)

            # Non-fatal: the rest of uninstall still ran (owned hook rows and state.json removed)
            # even though the caffeinate process could not be signaled.
            data = read_json(hooks_path)
            rows = [row for event_rows in data["hooks"].values() for row in event_rows]
            self.assertFalse(any(row.get("description") == self.descriptor["marker"] for row in rows))
            self.assertFalse((state / "state.json").exists())
            # Never delete tracking for a process that might still be running.
            self.assertTrue((state / "caffeinate.json").exists())
            self.assertIsNone(proc.poll())

    def test_repair_clears_caffeinate_sidecar_without_killing_on_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            proc = subprocess.Popen(["sleep", "30"])
            self.addCleanup(self._kill_and_reap, proc)
            fake_ps = root / "fake-ps"
            write_fake_ps(fake_ps, "not-caffeinate")
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                # expiry already in the past -- anomalously alive past its own tracked timeout.
                manage.atomic_write_state(
                    state / "caffeinate.json", {"pid": proc.pid, "expiry": 1, "status": "started"}
                )
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_PS"] = str(fake_ps)
                os.environ["KEEP_AWAKE_NOW"] = "20000"
                message = manage.repair_caffeinate_state(self.descriptor)
            self.assertIn("removed expired owned caffeinate state", message)
            self.assertFalse((state / "caffeinate.json").exists())
            # Identity mismatch -- never signaled, still running.
            self.assertIsNone(proc.poll())

    def test_stop_owned_caffeinate_never_deletes_sidecar_retracked_to_a_new_pid_mid_wait(self):
        """Regression test: _stop_owned_caffeinate's post-SIGTERM confirmation wait (up to 1s) is
        long enough for a concurrent runtime-hook tick to land in the middle of it, decide a
        refresh is due, fork a brand-new caffeinate, and retrack that new pid into the sidecar --
        all before this function's own final liveness re-check returns. The eventual sidecar
        removal must be skipped in that case, or the hook's freshly-tracked live process would be
        silently orphaned (untracked) by the very cleanup that was only ever supposed to be
        removing the OLD, now-dead pid's entry.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            old_pid = 987654
            new_pid = 123456
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                # expiry already in the past -- anomalously alive past its own tracked timeout.
                manage.atomic_write_state(
                    state / "caffeinate.json", {"pid": old_pid, "expiry": 1, "status": "started"}
                )
            calls = {"n": 0}

            def fake_alive_and_owned(pid_arg):
                self.assertEqual(pid_arg, old_pid)
                calls["n"] += 1
                # Call 1 is repair_caffeinate_state's own pre-check ("anomalously alive past its
                # timeout?") -- must be True so it delegates into _stop_owned_caffeinate at all.
                # Call 2 is that function's wait-loop condition; returning False there ends the
                # loop immediately (already dead). Call 3 is its post-loop re-check -- exactly
                # where a concurrent hook tick's retrack would land: after death is confirmed but
                # before the sidecar is re-read for deletion.
                if calls["n"] == 1:
                    return True
                if calls["n"] == 3:
                    manage.atomic_write_state(
                        state / "caffeinate.json",
                        {"pid": new_pid, "expiry": 99999, "status": "started"},
                    )
                return False

            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_NOW"] = "20000"
                with mock.patch("os.kill"), mock.patch.object(
                    manage, "caffeinate_alive_and_owned", side_effect=fake_alive_and_owned
                ):
                    message = manage.repair_caffeinate_state(self.descriptor)
            self.assertGreaterEqual(calls["n"], 3)
            self.assertIn("stopped owned caffeinate process", message)
            self.assertIn("refers to a different pid", message)
            # The hook's freshly-retracked pid must survive untouched -- never silently dropped.
            data = read_json(state / "caffeinate.json")
            self.assertEqual(data["pid"], new_pid)

    def test_stop_owned_caffeinate_reports_plain_success_when_sidecar_already_gone_mid_wait(self):
        """A sidecar that a concurrent actor (e.g. the bash hook's own Amphetamine-absent cleanup
        branch) already removed by the time _stop_owned_caffeinate re-reads it is a plain success
        -- there is no stale tracking left for the old pid either way -- and must NOT be reported
        as "tracked state now refers to a different pid", which would misleadingly suggest an
        unresolved pid conflict when nothing is tracked at all.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            old_pid = 987654
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "caffeinate.json", {"pid": old_pid, "expiry": 1, "status": "started"}
                )
            calls = {"n": 0}

            def fake_alive_and_owned(pid_arg):
                self.assertEqual(pid_arg, old_pid)
                calls["n"] += 1
                if calls["n"] == 1:
                    return True
                if calls["n"] == 3:
                    (state / "caffeinate.json").unlink()
                return False

            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_NOW"] = "20000"
                with mock.patch("os.kill"), mock.patch.object(
                    manage, "caffeinate_alive_and_owned", side_effect=fake_alive_and_owned
                ):
                    message = manage.repair_caffeinate_state(self.descriptor)
            self.assertGreaterEqual(calls["n"], 3)
            self.assertIn("stopped owned caffeinate process", message)
            self.assertNotIn("different pid", message)
            self.assertFalse((state / "caffeinate.json").exists())

    def test_repair_kills_and_clears_anomalously_alive_owned_caffeinate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cursor, hooks_path, state = self.prepare_home(root)
            proc = subprocess.Popen(["sleep", "30"])
            self.addCleanup(self._kill_and_reap, proc)
            fake_ps = root / "fake-ps"
            write_fake_ps(fake_ps, "caffeinate")
            with self.env(cursor, state, root), self.quiet():
                self.assertEqual(manage.run_apply(), 0)
                manage.atomic_write_state(
                    state / "caffeinate.json", {"pid": proc.pid, "expiry": 1, "status": "started"}
                )
            # This test's own Python process is the direct parent of `proc`, so a real SIGTERM
            # leaves a zombie (still "alive" to kill -0) until reaped -- unlike production, where
            # the runtime script that spawns caffeinate exits and lets launchd reap it promptly.
            # A background thread blocked in wait() reaps it the instant SIGTERM lands, well
            # within _stop_owned_caffeinate's 1s retry budget.
            reaper = threading.Thread(target=proc.wait)
            reaper.start()
            with self.env(cursor, state, root):
                os.environ["KEEP_AWAKE_PS"] = str(fake_ps)
                os.environ["KEEP_AWAKE_NOW"] = "20000"
                message = manage.repair_caffeinate_state(self.descriptor)
            reaper.join(timeout=2)
            self.assertFalse(reaper.is_alive())
            self.assertIn("stopped owned caffeinate process", message)
            self.assertFalse((state / "caffeinate.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
