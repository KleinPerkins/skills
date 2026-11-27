"""Configuration-only inventory through the public CLI and the target-access boundary."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "lib"))
import configured
from store import Store


class ConfigurationInventory(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.state = self.root / "state"
        self.config = self.state / "jobs"
        self.cli = PACKAGE / "bin/local-jobs.sh"
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.root),
                    "LOCAL_JOBS_STATE": str(self.state), "LOCAL_JOBS_HOME": str(PACKAGE),
                    "LOCAL_JOBS_PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1"}

    def write(self, name, body):
        self.config.mkdir(parents=True, exist_ok=True)
        path = self.config / (name + ".yml")
        path.write_text(yaml.safe_dump(body))
        return path

    def view(self, complete=True, **overrides):
        p = subprocess.run([str(self.cli), "view-jobs", "--config-only", "--json"], text=True,
                           capture_output=True, env={**self.env, **overrides}, timeout=10)
        result = json.loads(p.stdout)
        self.assertEqual(complete, result["complete"], result)
        self.assertEqual(0 if complete else 1, p.returncode, result)
        if not complete:
            self.assertEqual([], result["instances"])
        return result

    def test_missing_state_is_observed_without_creation(self):
        self.assertEqual([], self.view()["instances"])
        self.assertFalse(self.state.exists())

    def test_operational_store_reads_with_writes_denied(self):
        entry = {"id": "inspect", "program": "/usr/bin/true"}
        path = self.write("command", {"version": 1, "instances": [entry]})
        before = path.read_bytes()
        open_path = Path.open

        def read_only(file, mode="r", *args, **kwargs):
            if file.parent == path.parent and set(mode).intersection("wax+"):
                raise PermissionError("job directory is read-only")
            return open_path(file, mode, *args, **kwargs)

        store = Store(path, field_defaults={"enabled": True})
        with patch.object(Path, "open", read_only):
            self.assertEqual([{**entry, "enabled": True}], store.list())
            with self.assertRaisesRegex(PermissionError, "read-only"):
                store.remove("inspect")
        self.assertEqual(before, path.read_bytes())
        self.assertEqual([path], list(self.config.iterdir()))

    def test_declared_values_stay_lexical_and_commands_stay_private(self):
        target = self.root / "unselected"
        self.write("incremental-git-fetch", {"version": 2, "global": {"dev_root": str(target)},
                   "defaults": {"path": "alias/../repo"}, "repos": [{"id": "reference"}]})
        self.write("command", {"instances": [{"id": "run", "program": str(target),
                   "args": ["private-arg"], "env": {"OPTION": "private-value"}}]})
        expected = [{"id": "reference", "type": "incremental-git-fetch",
                     "declared_path": "alias/../repo", "declared_root": str(target),
                     "declared_root_source": "global.dev_root"},
                    {"id": "run", "type": "command"}]
        self.assertEqual(expected, self.view()["instances"])
        def guard(original):
            def checked(path, *args, **kwargs):
                if isinstance(path, (str, bytes, Path)):
                    self.assertFalse(os.fsdecode(path).startswith(str(target)))
                return original(path, *args, **kwargs)
            return checked
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(os, "open", guard(os.open)), patch.object(os, "stat", guard(os.stat)), \
             patch.object(os, "lstat", guard(os.lstat)), patch.object(os, "readlink", guard(os.readlink)), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected dispatch")):
            self.assertEqual(expected, configured.snapshot()["instances"])

    def test_root_precedence_matches_the_fetch_backend(self):
        backend = PACKAGE / "backends/incremental-git-fetch/config.py"
        config = self.write("incremental-git-fetch", {"repos": [{"id": "ref", "path": "child"}]})
        fallback = str(self.root / "fallback")
        stored = str(self.root / "stored")
        for fixed, env_root, expected_root, source in [
            (stored, fallback, stored, "global.dev_root"),
            (None, fallback, fallback, "LOCAL_JOBS_IGF_DEV_ROOT"),
            (None, "", ".", "working-directory"),
        ]:
            with self.subTest(source=source):
                config.write_text(yaml.safe_dump({"global": {"dev_root": fixed},
                                                  "repos": [{"id": "ref", "path": "child"}]}))
                env = {"LOCAL_JOBS_IGF_DEV_ROOT": env_root, "LOCAL_JOBS_IGF_CONFIG": str(config)}
                row, = self.view(**env)["instances"]
                self.assertEqual((expected_root, source), (row["declared_root"], row["declared_root_source"]))
                actual = subprocess.check_output([sys.executable, str(backend), "repo", "ref"], text=True,
                                                 cwd=self.root, env={**self.env, **env})
                self.assertEqual(str((self.root / expected_root / "child").resolve()), json.loads(actual)["path"])

    def test_ambiguous_and_damaged_stores_do_not_return_partial_success(self):
        self.write("command", {"instances": [{"id": "same"}]})
        fetch = self.write("incremental-git-fetch", {"repos": [{"id": "same", "path": "/unused"}]})
        self.view(False)
        for body in ({"version": 0}, {"repos": "invalid"}, {"repos": [{"path": "/unused"}]}):
            fetch.write_text(yaml.safe_dump(body))
            self.view(False)
        fetch.write_text("private-value: [")
        self.assertNotIn("private-value", self.view(False)["reason"])
        fetch.unlink()
        self.write("command", {"version": 2})
        self.view(False)

    def test_overlay_and_alternate_configuration_are_reported_before_dispatch(self):
        self.view(False, LOCAL_JOBS_IGF_CONFIG=str(self.root / "elsewhere"))
        self.view(False, LOCAL_JOBS_OVERLAY_DIR=str(self.root / "elsewhere"))
        self.view(False, LOCAL_JOBS_REGISTRY=str(self.root / "elsewhere"))
        overlay = self.state / "registry.d"
        overlay.mkdir(parents=True)
        os.mkfifo(overlay / "custom.yml")
        self.assertIn("overlays", self.view(False)["reason"])

    def test_symlinks_and_special_files_are_not_followed(self):
        destination = self.root / "other"
        destination.mkdir()
        self.state.symlink_to(destination)
        self.view(False)
        self.assertEqual([], list(destination.iterdir()))
        self.state.unlink()
        self.config.mkdir(parents=True)
        file = self.config / "command.yml"
        file.symlink_to(destination / "absent")
        self.view(False)
        file.unlink()
        os.mkfifo(file)
        self.view(False)


if __name__ == "__main__":
    unittest.main()
