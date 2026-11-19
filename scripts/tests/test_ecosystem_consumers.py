"""Synthetic source-layout checks; these do not qualify native entry or installation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
from capability_meta import build_action_plan, parse_metadata  # noqa: E402

CONSUMERS = ("agent-route", "ecosystem-search")
TOOL_RELATIVE = Path("global/tools/ecosystem-index/ecosystem_index.py")
SOURCE_REMOTE = "git@github.com:KleinPerkins/skills.git"


def tree_state(root: Path) -> dict:
    """Include Git, modes, bytes and mtimes so a source check cannot conceal writes."""
    state = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        payload = os.readlink(path) if path.is_symlink() else (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
        state[str(path.relative_to(root))] = (stat.S_IMODE(info.st_mode), info.st_mtime_ns, payload)
    return state


class ConsumerPackages(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ecosystem-consumers-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Skills source with spaces"
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / "config"),
                        XDG_CACHE_HOME=str(self.home / "cache"),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_OPTIONAL_LOCKS="0", PYTHONDONTWRITEBYTECODE="1")
        for name in CONSUMERS:
            shutil.copytree(REPO / "global/skills" / name, self.skill(name))
        shutil.copytree(REPO / TOOL_RELATIVE.parent, self.root / TOOL_RELATIVE.parent)
        self.git("init", "-q")
        self.git("remote", "add", "origin", SOURCE_REMOTE)
        self.git("add", "global")

    def skill(self, name):
        return self.root / "global/skills" / name

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], env=self.env,
                              check=True, capture_output=True, text=True, timeout=10)

    def check(self, directory, *args, env=None):
        return subprocess.run(["bash", str(directory / "install.sh"), *args],
                              env=env or self.env, capture_output=True, text=True, timeout=25)

    def assert_ready(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        value = json.loads(result.stdout)
        self.assertEqual(value, {"status": "ready", "source_root": str(self.root),
                                 "tool": str(self.root / TOOL_RELATIVE)})
        return value

    def assert_unavailable(self, result):
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {
            "status": "unavailable", "reason": "source-dependency-unverified"})

    def test_manifest_exposure_and_existing_package_contract(self):
        by_id = {m.capability_id: m for m in build_action_plan(self.root)}
        for name in (*CONSUMERS, "ecosystem-index"):
            shelf = "tools" if name == "ecosystem-index" else "skills"
            metadata = parse_metadata(self.root / "global" / shelf / name / "meta.yml")
            self.assertEqual((metadata["flavor"], metadata["post_mgmt"]), ("1", "none"))
            manifest = by_id[name]
            exposure = (manifest.expose_cursor, manifest.expose_claude, manifest.expose_codex)
            self.assertEqual(exposure, ("0", "0", "1") if name == "agent-route" else ("1", "1", "1"))
        self.assertEqual(parse_metadata(self.root / TOOL_RELATIVE.parent / "meta.yml")["shape"], "snapshot")

    def test_source_and_installed_directory_symlinks_resolve_same_tool(self):
        before = tree_state(self.base)
        for name in CONSUMERS:
            self.assert_ready(self.check(self.skill(name)))
        self.assertEqual(tree_state(self.base), before)
        for name in CONSUMERS:
            installed = self.home / ".codex/skills" / name
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.symlink_to(self.skill(name), target_is_directory=True)
            before = tree_state(self.base)
            self.assert_ready(self.check(installed, "--doctor"))
            self.assertEqual(tree_state(self.base), before)

    def test_read_only_lifecycle_never_executes_tool(self):
        tool = self.root / TOOL_RELATIVE
        marker = self.base / "TOOL_WAS_EXECUTED"
        tool.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('forbidden')\n")
        before = tree_state(self.base)
        for name in CONSUMERS:
            for arguments in ((), ("--doctor",), ("--help",)):
                result = self.check(self.skill(name), *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(tree_state(self.base), before)

    def test_copied_skill_without_source_refuses(self):
        for name in CONSUMERS:
            copied = self.base / "copied" / name
            shutil.copytree(self.skill(name), copied)
            before = tree_state(self.base)
            self.assert_unavailable(self.check(copied))
            self.assertEqual(tree_state(self.base), before)

    def test_missing_tool_refuses_without_repair(self):
        (self.root / TOOL_RELATIVE).unlink()
        before = tree_state(self.base)
        for name in CONSUMERS:
            self.assert_unavailable(self.check(self.skill(name)))
        self.assertEqual(tree_state(self.base), before)

    def test_missing_runtime_module_refuses_without_repair(self):
        module = self.root / TOOL_RELATIVE.parent / 'lib/contracts.py'
        module.unlink()
        before = tree_state(self.base)
        for name in CONSUMERS:
            self.assert_unavailable(self.check(self.skill(name)))
        self.assertEqual(tree_state(self.base), before)

    def test_symlinked_runtime_module_refuses_without_following(self):
        module = self.root / TOOL_RELATIVE.parent / 'lib/engine.py'
        external = self.base / 'external-engine.py'
        module.rename(external)
        module.symlink_to(external)
        before = tree_state(self.base)
        for name in CONSUMERS:
            self.assert_unavailable(self.check(self.skill(name)))
        self.assertEqual(tree_state(self.base), before)

    def test_untracked_runtime_descriptor_refuses(self):
        self.git('rm', '--cached', str(TOOL_RELATIVE.parent / 'tool.yml'))
        before = tree_state(self.base)
        for name in CONSUMERS:
            self.assert_unavailable(self.check(self.skill(name)))
        self.assertEqual(tree_state(self.base), before)

    def test_missing_skill_payload_refuses(self):
        for name in CONSUMERS:
            (self.skill(name) / "SKILL.md").unlink()
            self.assert_unavailable(self.check(self.skill(name)))

    def test_mismatched_or_secret_bearing_remote_refuses_without_echo(self):
        for remote in ("https://code.example/other/skills.git", "https://user:private@github.com/KleinPerkins/skills.git"):
            self.git("remote", "set-url", "origin", remote)
            for name in CONSUMERS:
                result = self.check(self.skill(name))
                self.assert_unavailable(result)
                self.assertNotIn("private", result.stdout + result.stderr)
                self.assertNotIn(remote, result.stdout + result.stderr)

    def test_accepted_remote_spellings(self):
        for remote in (SOURCE_REMOTE, "https://github.com/KleinPerkins/skills.git", "https://github.com/KleinPerkins/skills"):
            self.git("remote", "set-url", "origin", remote)
            for name in CONSUMERS:
                self.assert_ready(self.check(self.skill(name)))

    def test_symlinked_tool_or_skill_payload_refuses(self):
        tool = self.root / TOOL_RELATIVE
        external = self.base / "external-tool.py"
        tool.rename(external)
        tool.symlink_to(external)
        for name in CONSUMERS:
            self.assert_unavailable(self.check(self.skill(name)))
        tool.unlink()
        external.rename(tool)
        for name in CONSUMERS:
            source = self.skill(name) / "SKILL.md"
            external_skill = self.base / (name + ".md")
            source.rename(external_skill)
            source.symlink_to(external_skill)
            self.assert_unavailable(self.check(self.skill(name)))

    def test_untracked_dependency_or_skill_refuses(self):
        for relative in (TOOL_RELATIVE, Path("global/skills/agent-route/SKILL.md")):
            self.git("rm", "--cached", str(relative))
            self.assert_unavailable(self.check(self.skill("agent-route")))
            if relative == TOOL_RELATIVE:
                self.assert_unavailable(self.check(self.skill("ecosystem-search")))
            self.git("add", str(relative))

    def test_shell_environment_does_not_replace_source_identity(self):
        env = dict(self.env, GIT_DIR=str(self.base / "foreign.git"),
                   GIT_WORK_TREE=str(self.base / "foreign"),
                   GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="remote.origin.url",
                   GIT_CONFIG_VALUE_0="https://code.example/other/repo", PYTHONPATH=str(self.base / "foreign-python"))
        for name in CONSUMERS:
            self.assert_ready(self.check(self.skill(name), env=env))

    def test_lifecycle_rejects_legacy_mutation_options_without_writes(self):
        before = tree_state(self.base)
        for name in CONSUMERS:
            for arguments in (("--install",), ("--uninstall",), ("--apply",), ("--doctor", "extra")):
                result = self.check(self.skill(name), *arguments)
                self.assertEqual(result.returncode, 2)
        self.assertEqual(tree_state(self.base), before)

    def test_route_contains_no_legacy_runtime_and_body_is_small(self):
        route = self.skill("agent-route")
        for retired in ("lib", "scripts", "registry"):
            self.assertFalse((route / retired).exists())
        self.assertEqual(list(route.rglob("*.py")), [])
        body = (route / "SKILL.md").read_text().split("---", 2)[2]
        self.assertLessEqual(len(body.splitlines()), 150)

    def test_resolved_tool_serves_shared_search_describe_context_read_only(self):
        project = self.base / "synthetic-project"
        project.mkdir()
        (project / "eligible.json").write_text(json.dumps({
            "schema": "ecosystem-index/metadata/v1", "entities": [{
                "id": "capability:fixture", "kind": "capability", "title": "Fixture Search",
                "description": "Synthetic capability lookup", "aliases": [],
                "pointers": [{"kind": "instruction", "path": "AGENTS.md"}], "edges": []}]}))
        state = self.base / "state"
        state.mkdir(mode=0o700)
        config = state / "config.json"
        cache = state / "snapshot.json"
        config.write_text(json.dumps({"schema": "ecosystem-index/config/v1",
            "exclude_paths": [], "exclude_identities": [],
            "bounds": {"roots": 500, "entities": 5000, "input_bytes": 262144,
                       "snapshot_bytes": 20971520, "refresh_seconds": 60},
            "roots": [{"key": "fixture", "path": str(project), "identity": {"provider": None,
                "remote": "https://code.example/team/project.git"}, "scope": "permitted",
                "inventory": "configured", "title": "Fixture owner", "aliases": [],
                "storage_fields": ["title", "description", "aliases", "pointers", "edges"],
                "sources": [{"path": "eligible.json", "adapter": "json", "kind": "capability",
                    "revision": None, "fields": ["title", "description", "aliases", "pointers", "edges"]}],
                "git": None}]}))
        config.chmod(0o600)
        tool = self.root / TOOL_RELATIVE
        def invoke(*args, query=None):
            result = subprocess.run([sys.executable, "-B", str(tool), *args], input=query,
                                    env=self.env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(result.stderr, "")
            return json.loads(result.stdout)
        self.assertEqual(invoke("refresh", "--config", str(config), "--cache", str(cache))["status"], "complete")
        before = tree_state(self.base)
        for name in CONSUMERS:
            resolved = self.assert_ready(self.check(self.skill(name)))
            self.assertEqual(resolved["tool"], str(tool))
            search = invoke("search", "--cache", str(cache), query="capability:fixture")
            self.assertEqual(search["status"], "matches")
            self.assertEqual(search["candidates"][0]["entity"]["id"], "capability:fixture")
            self.assertIn("exact_id", search["candidates"][0]["contributions"])
            self.assertIn("conflicts", search["candidates"][0]["entity"])
            owner = search["candidates"][0]["entity"]["parent"]
            self.assertTrue(owner.startswith("repository:"))
            for command in ("describe", "context"):
                result = invoke(command, "--cache", str(cache), "--id", "capability:fixture")
                self.assertEqual(result["status"], "matches")
                self.assertEqual(result["coverage"], "complete")
                self.assertIn("age_seconds", result["freshness"])
                if command == "context":
                    self.assertEqual(result["source_owner"], owner)
                    self.assertEqual(result["pointers"][0]["pointer"]["path"], "AGENTS.md")
                    self.assertIn("provenance", result["pointers"][0])
                else:
                    self.assertTrue(result["entity"]["observations"])
        self.assertEqual(tree_state(self.base), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
