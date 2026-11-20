#!/usr/bin/env python3
"""Hermetic installer, rollback and installed-entrypoint qualification."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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
            with self.assertRaises(OSError): installer.install(args)
        self.assertEqual(self.pointers(), before)
        self.assertEqual((self.runtime / "classifications.json").stat().st_mode & 0o777, 0o640)
        self.assertFalse(list(self.runtime.glob(".policy-*")))
        self.assertFalse(list(self.runtime.glob(".link-*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
