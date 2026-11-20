#!/usr/bin/env python3
"""Hermetic installer, rollback and installed-entrypoint qualification."""
from __future__ import annotations

import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("install_runtime", SKILL / "scripts/install_runtime.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.source = self.root / "source"
        shutil.copytree(SKILL, self.source, ignore=shutil.ignore_patterns("__pycache__"))
        self.runtime = self.home / ".local/share/continual-learning-consolidate"
        self.bin_dir = self.home / ".local/bin"
        self.policy = self.root / "candidate-policy.json"
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": []}))
        self.job = self.home / ".local-jobs/jobs/command.yml"
        self.job.parent.mkdir(parents=True)
        self.job.write_text("instances:\n  - id: continual-learning-consolidate\n    enabled: false\n    schedule: '18:00'\n")
        self.capture = self.home / "capture-marker"
        self.capture.write_bytes(b"unchanged capture control")
        self.fake_jobs = self.root / "local-jobs"
        self.fake_jobs.write_text("#!/bin/sh\necho called >> \"$HOME/job-calls\"\nexit 99\n")
        self.fake_jobs.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME": str(self.runtime), "CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR": str(self.bin_dir), "LOCAL_JOBS_CLI": str(self.fake_jobs), "PYTHONDONTWRITEBYTECODE": "1"}

    def stop_process(self, process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def run_install(self, *args: str, success: bool = True) -> dict | None:
        result = subprocess.run(["bash", str(self.source / "install.sh"), "--no-schedule", *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success else None

    def initial(self) -> dict:
        return self.run_install("--policy", str(self.policy), "--expected-policy-sha256", "absent")

    def pointers(self) -> tuple[str, str, bytes]:
        return (os.readlink(self.runtime / "current"), os.readlink(self.bin_dir / "continual-learning-consolidate"), (self.runtime / "classifications.json").read_bytes())

    def test_installed_runtime_executes_only_synthetic_home_and_route(self) -> None:
        before = (self.job.read_bytes(), self.capture.read_bytes())
        receipt = self.initial()
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Keep this synthetic durable preference.\n")
        route = self.root / "fake-route.sh"
        route.write_text("#!/bin/sh\nprintf '%s\\n' '{\"roots\": []}'\n")
        binary = self.bin_dir / "continual-learning-consolidate"
        result = subprocess.run([str(binary), "--home", str(self.home), "--agent-route", str(route), "--json"], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["classification_sha256"], receipt["classification_sha256"])
        self.assertIn("synthetic durable preference", (self.home / "AGENTS.md").read_text())
        self.assertEqual((self.job.read_bytes(), self.capture.read_bytes()), before)
        self.assertFalse((self.home / "job-calls").exists())
        self.assertEqual((self.runtime / "classifications.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse(list((self.runtime / "releases").rglob("__pycache__")))

    def test_custom_runtime_uses_its_installed_default_policy(self) -> None:
        self.runtime = self.root / "custom-runtime"
        self.env["CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME"] = str(self.runtime)
        receipt = self.initial()
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Synthetic seed.\n")
        route = self.root / "route.sh"
        route.write_text("#!/bin/sh\nprintf '%s\\n' '{\"roots\":[]}'\n")
        result = subprocess.run([str(self.bin_dir / "continual-learning-consolidate"), "--home", str(self.home), "--agent-route", str(route), "--json"], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["classification_sha256"], receipt["classification_sha256"])

    def test_all_executable_dependencies_are_addressed_and_reusable(self) -> None:
        previous = self.initial()["release_id"]
        self.assertEqual(self.run_install()["release_id"], previous)
        for name in ["scripts/lib/memory.py", "scripts/lib/classifications.py", "scripts/continual_learning_consolidate.py", "scripts/install_runtime.py"]:
            with (self.source / name).open("a") as handle:
                handle.write("\n# synthetic dependency update\n")
            current = self.run_install()["release_id"]
            self.assertNotEqual(current, previous, name)
            self.assertEqual(Path(os.readlink(self.runtime / "current")).name, current)
            previous = current
        self.assertEqual(len(list((self.runtime / "releases").iterdir())), 5)
        self.assertFalse(list(self.runtime.glob(".stage-*")))

    def test_missing_invalid_and_conflicting_policy_refuse_without_pointer_change(self) -> None:
        self.run_install(success=False)
        self.assertFalse((self.runtime / "current").exists())
        self.initial()
        before = self.pointers()
        self.policy.write_bytes(b'{"schema": "unsupported"}')
        installed_hash = hashlib.sha256(before[2]).hexdigest()
        self.run_install("--policy", str(self.policy), "--expected-policy-sha256", installed_hash, success=False)
        self.assertEqual(self.pointers(), before)
        self.run_install("--policy", str(self.policy), success=False)
        self.assertEqual(self.pointers(), before)

    def test_policy_replacement_requires_exact_preimage(self) -> None:
        self.initial()
        before = self.pointers()
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": [str(self.home / "recovery")]}))
        self.run_install("--policy", str(self.policy), "--expected-policy-sha256", "absent", success=False)
        self.assertEqual(self.pointers(), before)
        self.run_install("--policy", str(self.policy), "--expected-policy-sha256", hashlib.sha256(before[2]).hexdigest())
        self.assertEqual((self.runtime / "classifications.json").read_bytes(), self.policy.read_bytes())

    def test_rollback_is_guarded_and_keeps_both_releases(self) -> None:
        old = self.initial()["release_id"]
        with (self.source / "scripts/lib/memory.py").open("a") as handle:
            handle.write("\n# update\n")
        new = self.run_install()["release_id"]
        self.run_install("--rollback-to", old, success=False)
        self.run_install("--rollback-to", old, "--expected-current", old, success=False)
        self.assertEqual(Path(self.pointers()[0]).name, new)
        self.run_install("--rollback-to", old, "--expected-current", new)
        self.assertEqual(Path(self.pointers()[0]).name, old)
        self.assertEqual(len(list((self.runtime / "releases").iterdir())), 2)
        self.assertFalse((self.home / "job-calls").exists())

    def test_expected_current_checks_exact_pointer_and_policy_mode_is_private(self) -> None:
        release_id = self.initial()["release_id"]
        policy = self.runtime / "classifications.json"
        policy.chmod(0o644)
        self.run_install()
        self.assertEqual(policy.stat().st_mode & 0o777, 0o600)
        current = self.runtime / "current"
        current.unlink()
        unrelated_target = str(self.root / "elsewhere" / release_id)
        current.symlink_to(unrelated_target)
        self.run_install("--expected-current", release_id, success=False)
        self.assertEqual(os.readlink(current), unrelated_target)

    def test_rollback_forces_runtime_only_without_no_schedule_flag(self) -> None:
        old = self.initial()["release_id"]
        with (self.source / "scripts/lib/memory.py").open("a") as handle:
            handle.write("\n# next release\n")
        new = self.run_install()["release_id"]
        previous_job = self.job.read_bytes()
        result = subprocess.run(["bash", str(self.source / "install.sh"), "--rollback-to", old, "--expected-current", new], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(self.pointers()[0]).name, old)
        self.assertFalse((self.home / "job-calls").exists())
        self.assertEqual(self.job.read_bytes(), previous_job)

    def test_rollback_validates_policy_with_target_release(self) -> None:
        validator = self.source / "scripts/lib/classifications.py"
        original = validator.read_text()
        validator.write_text(original + "\nBasePolicy = Policy\nclass Policy(BasePolicy):\n    def __init__(self, payload, digest):\n        super().__init__(payload, digest)\n        if payload['excluded_paths']:\n            raise PolicyError('synthetic old target rejects this policy')\n")
        old = self.initial()["release_id"]
        validator.write_text(original)
        previous_hash = hashlib.sha256(self.pointers()[2]).hexdigest()
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": [str(self.home / "new-only")]}))
        new = self.run_install("--policy", str(self.policy), "--expected-policy-sha256", previous_hash)["release_id"]
        before = self.pointers()
        self.run_install("--rollback-to", old, "--expected-current", new, success=False)
        self.assertEqual(self.pointers(), before)

    def test_loaded_old_runtime_refuses_after_pointer_switch(self) -> None:
        old = self.initial()["release_id"]
        with (self.source / "scripts/continual_learning_consolidate.py").open("a") as handle:
            handle.write("\n# next addressed release\n")
        new = self.run_install()["release_id"]
        self.run_install("--rollback-to", old, "--expected-current", new)
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Synthetic seed.\n")
        target = self.home / "AGENTS.md"
        target.write_bytes(b"prior output")
        route = self.root / "route.sh"
        called = self.root / "route-called"
        route.write_text(f"#!/bin/sh\ntouch '{called}'\nprintf '%s\\n' '{{\"roots\":[]}}'\n")
        ready = self.root / "loaded-old"
        main = self.runtime / "releases" / old / "scripts/continual_learning_consolidate.py"
        program = f"import importlib.util,sys;from pathlib import Path;s=importlib.util.spec_from_file_location('loaded_old',Path({str(main)!r}));m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);Path({str(ready)!r}).touch();m.consolidate_home(Path({str(self.home)!r}),Path({str(route)!r}))"
        with (self.runtime / ".install.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            process = subprocess.Popen([sys.executable, "-B", "-c", program], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(self.stop_process, process)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists())
                self.assertIsNone(process.poll())
                installer.atomic_link(self.runtime / "current", str(self.runtime / "releases" / new))
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        try:
            _, stderr = process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("installed runtime changed before startup", stderr)
            self.assertFalse(called.exists())
            self.assertEqual(target.read_bytes(), b"prior output")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_loaded_script_bytes_cannot_borrow_new_symlink_identity(self) -> None:
        old = self.initial()["release_id"]
        source_main = self.source / "scripts/continual_learning_consolidate.py"
        source_main.write_text(source_main.read_text().replace("edit agent-learnings.md sources", "edit only agent-learnings.md sources"))
        self.run_install()
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Synthetic seed.\n")
        target = self.home / "AGENTS.md"
        target.write_bytes(b"prior output")
        called = self.root / "route-called"
        route = self.root / "route.sh"
        route.write_text(f"#!/bin/sh\ntouch '{called}'\nprintf '%s\\n' '{{\"roots\":[]}}'\n")
        old_main = self.runtime / "releases" / old / "scripts/continual_learning_consolidate.py"
        binary = self.bin_dir / "continual-learning-consolidate"
        # Model Python having read old bytes before current is resolved: the
        # executed code is old, while __file__ still names the stable bin link.
        program = f"import sys,types;from pathlib import Path;m=types.ModuleType('loaded_old');m.__file__={str(binary)!r};sys.modules[m.__name__]=m;exec(compile(Path({str(old_main)!r}).read_bytes(),m.__file__,'exec'),m.__dict__);m.consolidate_home(Path({str(self.home)!r}),Path({str(route)!r}))"
        result = subprocess.run([sys.executable, "-B", "-c", program], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed runtime changed before startup", result.stderr)
        self.assertFalse(called.exists())
        self.assertEqual(target.read_bytes(), b"prior output")

    def test_projection_holds_shared_install_lock(self) -> None:
        self.initial()
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Synthetic seed.\n")
        route = self.root / "blocking-route.sh"
        entered, release = self.root / "entered", self.root / "continue"
        route.write_text(f"#!/bin/sh\ntouch '{entered}'\nwhile [ ! -e '{release}' ]; do sleep 0.01; done\nprintf '%s\\n' '{{\"roots\":[]}}'\n")
        process = subprocess.Popen([str(self.bin_dir / "continual-learning-consolidate"), "--home", str(self.home), "--agent-route", str(route), "--json"], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_process, process)
        try:
            deadline = time.monotonic() + 5
            while not entered.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(entered.exists())
            with (self.runtime / ".install.lock").open("a") as lock:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release.touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertTrue(json.loads(stdout)["changed"])
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_nonmanaged_binary_symlink_is_preserved(self) -> None:
        self.initial()
        before = self.pointers()
        binary = self.bin_dir / "continual-learning-consolidate"
        binary.unlink()
        unrelated = str(self.root / "unrelated-tool")
        binary.symlink_to(unrelated)
        self.run_install(success=False)
        self.assertEqual(os.readlink(binary), unrelated)
        self.assertEqual(os.readlink(self.runtime / "current"), before[0])
        self.assertEqual((self.runtime / "classifications.json").read_bytes(), before[2])

    def test_corrupted_release_and_occupied_bin_refuse(self) -> None:
        release = self.initial()["release_id"]
        before = self.pointers()
        (self.runtime / "releases" / release / "scripts/lib/memory.py").write_text("corrupted")
        self.run_install(success=False)
        self.assertEqual(self.pointers(), before)
        binary = self.bin_dir / "continual-learning-consolidate"
        binary.unlink()
        binary.write_text("unrelated occupant")
        self.run_install(success=False)
        self.assertEqual(binary.read_text(), "unrelated occupant")

    def test_reused_release_requires_executable_entrypoint_mode(self) -> None:
        release_id = self.initial()["release_id"]
        before = self.pointers()
        entrypoint = self.runtime / "releases" / release_id / "scripts/continual_learning_consolidate.py"
        entrypoint.chmod(0o644)
        self.run_install(success=False)
        self.assertEqual(self.pointers(), before)

    def test_existing_policy_snapshot_does_not_follow_replacement(self) -> None:
        self.initial()
        policy = self.runtime / "classifications.json"
        before = policy.read_bytes()
        other = self.root / "other-policy"
        other.write_bytes(b"different bytes")
        original_open = os.open
        swapped = False
        def swap_after_open(path, flags, *args, **kwargs):
            nonlocal swapped
            descriptor = original_open(path, flags, *args, **kwargs)
            if Path(path) == policy and not swapped:
                swapped = True
                policy.rename(self.root / "preserved-policy")
                policy.symlink_to(other)
            return descriptor
        with mock.patch.object(installer.os, "open", side_effect=swap_after_open):
            content, mode = installer.read_policy_preimage(policy)
        self.assertTrue(swapped)
        self.assertEqual((content, mode), (before, 0o600))
        with self.assertRaises(OSError): installer.read_policy_preimage(policy)

    def test_persistent_inverse_failure_attempts_all_and_blocks_runtime(self) -> None:
        self.initial()
        before = self.pointers()
        with (self.source / "scripts/lib/memory.py").open("a") as handle:
            handle.write("\n# next release\n")
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": [str(self.home / "new-only")]}))
        args = SimpleNamespace(runtime=self.runtime, bin_dir=self.bin_dir, expected_current=None, policy=self.policy, expected_policy_sha256=hashlib.sha256(before[2]).hexdigest(), rollback_to=None, source=self.source)
        real_link = installer.atomic_link
        calls = []
        binary = self.bin_dir / "continual-learning-consolidate"
        def persistent_failure(path: Path, target: str | None) -> None:
            calls.append((path.name, target))
            if path == binary or (path == self.runtime / "current" and target == before[0]):
                raise OSError("synthetic persistent pointer failure")
            real_link(path, target)
        with mock.patch.object(installer, "atomic_link", side_effect=persistent_failure):
            with self.assertRaises(ValueError) as caught: installer.install(args)
        report = json.loads(str(caught.exception).split("recovery=", 1)[1])
        self.assertFalse(report["current"]["restored"])
        self.assertTrue(report["binary"]["restored"])
        self.assertTrue(report["policy"]["restored"])
        self.assertTrue(report["runtime_blocked"])
        self.assertEqual(sum(name == "continual-learning-consolidate" for name, _ in calls), 2)
        self.assertEqual((self.runtime / "classifications.json").read_bytes(), before[2])
        (self.home / "agent-learnings.md").write_text("## Learned User Preferences\n- Synthetic seed.\n")
        target = self.home / "AGENTS.md"
        target.write_bytes(b"prior output")
        route = self.root / "route.sh"
        route.write_text("#!/bin/sh\nprintf '%s\\n' '{\"roots\":[]}'\n")
        command = [str(binary), "--home", str(self.home), "--agent-route", str(route), "--json"]
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installation recovery is incomplete", result.stderr)
        self.assertEqual(target.read_bytes(), b"prior output")
        self.run_install()
        self.assertEqual((self.runtime / ".install.lock").read_bytes(), b"")
        repaired = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(repaired.returncode, 0, repaired.stderr)

    def test_publication_syncs_precede_marker_clear_and_sync_failure_blocks(self) -> None:
        self.initial()
        before = self.pointers()
        with (self.source / "scripts/lib/memory.py").open("a") as handle:
            handle.write("\n# next addressed release\n")
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": [str(self.home / "new-only")]}))
        args = SimpleNamespace(runtime=self.runtime, bin_dir=self.bin_dir, expected_current=None, policy=self.policy, expected_policy_sha256=hashlib.sha256(before[2]).hexdigest(), rollback_to=None, source=self.source)
        events = []
        sync, marker, link, policy_write = installer.fsync_directory, installer.recovery_marker, installer.atomic_link, installer.atomic_bytes
        def record_sync(path): events.append(("sync", path)); sync(path)
        def record_marker(lock, pending): events.append(("marker", pending)); marker(lock, pending)
        def record_link(path, target): events.append(("publish", path)); link(path, target)
        def record_policy(path, data, mode=0o600): events.append(("publish", path)); policy_write(path, data, mode)
        with mock.patch.object(installer, "fsync_directory", side_effect=record_sync), mock.patch.object(installer, "recovery_marker", side_effect=record_marker), mock.patch.object(installer, "atomic_link", side_effect=record_link), mock.patch.object(installer, "atomic_bytes", side_effect=record_policy):
            installer.install(args)
        clear = events.index(("marker", False))
        self.assertIn(("sync", self.runtime / "releases"), events[:clear])
        for position, event in enumerate(events):
            if event[0] != "publish": continue
            end = next((i for i in range(position + 1, len(events)) if events[i][0] in {"publish", "marker"}), len(events))
            self.assertIn(("sync", event[1].parent), events[position + 1:end])
        args.policy = None
        args.expected_policy_sha256 = None
        def fail_bin_sync(path):
            if path == self.bin_dir: raise OSError("synthetic directory sync failure")
            sync(path)
        with mock.patch.object(installer, "fsync_directory", side_effect=fail_bin_sync):
            with self.assertRaises(ValueError) as caught: installer.install(args)
        recovery = json.loads(str(caught.exception).split("recovery=", 1)[1])
        self.assertTrue(recovery["runtime_blocked"])
        self.assertIn("inverse_error", recovery["binary"])
        self.assertTrue((self.runtime / ".install.lock").read_bytes())

    def test_candidate_policy_inputs_are_bounded_regular_nofollow_files(self) -> None:
        self.initial()
        before = self.pointers()
        previous_hash = hashlib.sha256(before[2]).hexdigest()
        fifo = self.root / "candidate-fifo"
        os.mkfifo(fifo, mode=0o600)
        symlink = self.root / "candidate-link"
        symlink.symlink_to(self.policy)
        oversized = self.root / "candidate-oversize"
        oversized.write_bytes(self.policy.read_bytes() + b" " * (1024 * 1024))
        for candidate in [fifo, symlink, oversized]:
            with self.subTest(candidate=candidate.name):
                result = subprocess.run(["bash", str(self.source / "install.sh"), "--no-schedule", "--policy", str(candidate), "--expected-policy-sha256", previous_hash], env=self.env, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.pointers(), before)

    def test_release_integrity_reads_refuse_nonregular_alias_and_oversize_files(self) -> None:
        release_id = self.initial()["release_id"]
        release = self.runtime / "releases" / release_id
        before = self.pointers()
        targets = [self.source / "scripts/lib/memory.py", release / "scripts/lib/memory.py", release / "manifest.json"]
        for target in targets:
            original, mode = target.read_bytes(), target.stat().st_mode & 0o777
            backup = self.root / (target.name + "-backup")
            backup.write_bytes(original)
            for shape in ["fifo", "symlink", "oversize"]:
                with self.subTest(target=str(target), shape=shape):
                    target.unlink()
                    try:
                        if shape == "fifo": os.mkfifo(target, mode=mode)
                        elif shape == "symlink": target.symlink_to(backup)
                        else: target.write_bytes(original + b" " * (1024 * 1024))
                        result = subprocess.run(["bash", str(self.source / "install.sh"), "--no-schedule"], env=self.env, capture_output=True, text=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0)
                        if shape == "oversize": self.assertIn("1 MiB limit", result.stderr)
                        self.assertEqual(self.pointers(), before)
                        with (self.runtime / ".install.lock").open("a+") as lock:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        target.unlink(missing_ok=True)
                        target.write_bytes(original)
                        target.chmod(mode)

    def test_runtime_code_integrity_reads_refuse_and_release_lock(self) -> None:
        release_id = self.initial()["release_id"]
        entry = self.runtime / "releases" / release_id / "scripts/continual_learning_consolidate.py"
        original = entry.read_bytes()
        backup = entry.parent / "probe-original.py"
        backup.write_bytes(original)
        route = self.root / "route.sh"
        route.write_text("#!/bin/sh\nprintf '%s\\n' '{\"roots\":[]}'\n")
        target = self.home / "AGENTS.md"
        target.write_bytes(b"prior output")
        program = f"import sys,types,json;from pathlib import Path;m=types.ModuleType('probe');m.__file__={str(entry)!r};sys.modules[m.__name__]=m;exec(compile(Path({str(backup)!r}).read_bytes(),m.__file__,'exec'),m.__dict__);m._read_bullets=lambda *a,**k:(_ for _ in ()).throw(AssertionError('memory must not be read'))\ntry:m.consolidate_home(Path({str(self.home)!r}),Path({str(route)!r}))\nexcept m.ConsolidationError as error:print(json.dumps({{'blocked':str(error)}}))\nelse:raise AssertionError('corrupted code accepted')"
        for shape in ["fifo", "symlink", "oversize"]:
            with self.subTest(shape=shape):
                entry.unlink()
                try:
                    if shape == "fifo": os.mkfifo(entry, mode=0o755)
                    elif shape == "symlink": entry.symlink_to(backup)
                    else: entry.write_bytes(original + b" " * (1024 * 1024))
                    result = subprocess.run([sys.executable, "-B", "-c", program], env=self.env, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("cannot verify installed runtime code", json.loads(result.stdout)["blocked"])
                    self.assertEqual(target.read_bytes(), b"prior output")
                    with (self.runtime / ".install.lock").open("a+") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    entry.unlink(missing_ok=True)
                    entry.write_bytes(original)
                    entry.chmod(0o755)

    def test_failed_pointer_swap_restores_policy_and_runtime(self) -> None:
        self.initial()
        (self.runtime / "classifications.json").chmod(0o640)
        with (self.source / "scripts/lib/memory.py").open("a") as handle:
            handle.write("\n# new release before injected pointer failure\n")
        before = self.pointers()
        self.policy.write_text(json.dumps({"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": [str(self.home / "recovery")]}))
        args = SimpleNamespace(runtime=self.runtime, bin_dir=self.bin_dir, expected_current=None, policy=self.policy, expected_policy_sha256=hashlib.sha256(before[2]).hexdigest(), rollback_to=None, source=self.source)
        real_link = installer.atomic_link
        calls = 0
        def fail_once(path: Path, target: str | None) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic pointer failure")
            real_link(path, target)
        with mock.patch.object(installer, "atomic_link", side_effect=fail_once):
            with self.assertRaises(ValueError): installer.install(args)
        self.assertEqual(self.pointers(), before)
        self.assertEqual((self.runtime / "classifications.json").stat().st_mode & 0o777, 0o640)
        self.assertFalse(list(self.runtime.glob(".policy-*")))
        self.assertFalse(list(self.runtime.glob(".link-*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
