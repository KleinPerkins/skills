#!/usr/bin/env python3
"""Biting tests for the continual-learning governor v3 (retarget + BLESSED/CONTAINABLE/INCOMPATIBLE
state machine + fail-closed neutralization + projection-invariant fingerprint + global-exclude
ownership). Each test fails on the pre-v3 engine and passes on v3."""
import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
HELPER_PATH = PLUGIN_DIR / "scripts" / "continual_learning_plugin.py"

spec = importlib.util.spec_from_file_location("governor", HELPER_PATH)
governor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(governor)

DESC = governor.load_json(PLUGIN_DIR / "plugin.json")
STOP_TS_REL = "hooks/continual-learning-stop.ts"
BARE_STOP_COMMAND = "bun run ${CURSOR_PLUGIN_ROOT}/hooks/continual-learning-stop.ts"
APPROVED_PROVENANCE = "4a70bef5fce38a872256f6afc7d4d5f52b3f8c0c1c94070dd07b43fcdebff517"
UPSTREAM_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "upstream-df3fb154" / "continual-learning"
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def stop_command(turns: int, minutes: int) -> str:
    return f"CONTINUAL_LEARNING_MIN_TURNS={turns} CONTINUAL_LEARNING_MIN_MINUTES={minutes} {BARE_STOP_COMMAND}"


def make_cache(
    base: Path,
    *,
    updater_from: int = 7,
    skill_from: int = 3,
    stop_from: int = 1,
    updater_to: int = 0,
    skill_to: int = 0,
    stop_to: int = 0,
    turns: int = 15,
    minutes: int = 180,
    stop_entries=None,
    hooks_raw: str | None = None,
) -> Path:
    """Build a synthetic marketplace cache root with controllable writer-token counts and cadence."""
    cache = base / "cursor-public" / "continual-learning" / "deadbeef"
    write_json(
        cache / ".cursor-plugin" / "plugin.json",
        {"name": "continual-learning", "hooks": "./hooks/hooks.json"},
    )

    def body(name_from: int, name_to: int, prefix: str) -> str:
        lines = [f"{prefix} write to AGENTS.md here.\n"] * name_from
        lines += [f"{prefix} write to agent-learnings.md here.\n"] * name_to
        return "".join(lines) or f"{prefix} no target.\n"

    (cache / "agents").mkdir(parents=True, exist_ok=True)
    (cache / "agents" / "agents-memory-updater.md").write_text(body(updater_from, updater_to, "updater"))
    (cache / "skills" / "continual-learning").mkdir(parents=True, exist_ok=True)
    (cache / "skills" / "continual-learning" / "SKILL.md").write_text(body(skill_from, skill_to, "skill"))
    stop_ts = "const t = process.env.CONTINUAL_LEARNING_MIN_TURNS;\n" + body(stop_from, stop_to, "// stop")
    (cache / "hooks").mkdir(parents=True, exist_ok=True)
    (cache / "hooks" / "continual-learning-stop.ts").write_text(stop_ts)

    if hooks_raw is not None:
        (cache / "hooks" / "hooks.json").write_text(hooks_raw)
    else:
        if stop_entries is None:
            stop_entries = [{"command": stop_command(turns, minutes)}]
        write_json(cache / "hooks" / "hooks.json", {"version": 1, "hooks": {"stop": stop_entries}})
    return cache


class GovernorTestBase(unittest.TestCase):
    def setUp(self):
        self._env_saved = {
            k: os.environ.get(k)
            for k in (
                "CURSOR_HOME",
                "CONTINUAL_LEARNING_PLUGIN_CACHE_BASE",
                "CONTINUAL_LEARNING_HOOKSTATE_DIR",
            )
        }
        self._tmp = Path(governor.tempfile.mkdtemp(prefix="cl-gov-test-"))
        self.cursor_home = self._tmp / "cursor_home"
        self.cursor_home.mkdir(parents=True, exist_ok=True)
        self.cache_base = self._tmp / "cache"
        self.cache_base.mkdir(parents=True, exist_ok=True)
        # Redirect hookstate dir so run_apply() never writes to real cwd during tests.
        self.hookstate_dir = self._tmp / "hookstate"
        os.environ["CURSOR_HOME"] = str(self.cursor_home)
        os.environ["CONTINUAL_LEARNING_PLUGIN_CACHE_BASE"] = str(self.cache_base)
        os.environ["CONTINUAL_LEARNING_HOOKSTATE_DIR"] = str(self.hookstate_dir)
        # Isolate global-excludes ownership onto a temp file (never touch real git config).
        self.excludes_file = self._tmp / "gitignore_global"
        self._orig_excludes_target = governor.excludes_file_target
        governor.excludes_file_target = lambda: (self.excludes_file, False)
        # Control provenance_ref without touching the real meta.yml.
        self._orig_meta_field = governor.meta_field
        self._forced_provenance = None

        def fake_meta(key, path=governor.META):
            if key == "provenance_ref" and self._forced_provenance is not None:
                return self._forced_provenance
            return self._orig_meta_field(key, path)

        governor.meta_field = fake_meta

    def tearDown(self):
        governor.excludes_file_target = self._orig_excludes_target
        governor.meta_field = self._orig_meta_field
        for k, v in self._env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        governor.shutil.rmtree(self._tmp, ignore_errors=True)
        # Ensure CONTINUAL_LEARNING_HOOKSTATE_DIR is always restored even if tearDown
        # is called before setUp sets it (shouldn't happen, but defensive).
        if "CONTINUAL_LEARNING_HOOKSTATE_DIR" not in self._env_saved:
            os.environ.pop("CONTINUAL_LEARNING_HOOKSTATE_DIR", None)

    def bless(self, cache: Path) -> str:
        fp = governor.behavior_hash(cache, DESC)
        self._forced_provenance = fp
        return fp

    def writer_from_counts(self, cache: Path) -> dict[str, int]:
        out = {}
        for t in DESC["retargetTargets"]:
            out[t["file"]] = (cache / t["file"]).read_text().count(t["from"])
        return out

    def make_upstream_cache(self, revision: str = "df3fb154") -> Path:
        cache = self.cache_base / "cursor-public" / "continual-learning" / revision
        governor.shutil.copytree(UPSTREAM_FIXTURE, cache)
        fixture_skill = cache / "skills" / "continual-learning" / "SKILL.md.fixture"
        # Avoid repository capability discovery while restoring exact upstream cache bytes.
        fixture_skill.replace(fixture_skill.with_suffix(""))
        return cache


class DiscoveryTests(GovernorTestBase):
    def test_discovers_new_cache_root_immediately(self):
        cache = make_cache(self.cache_base)
        self.assertEqual(governor.discover_cache_roots(DESC), [cache])
        # A second, freshly created revision is found on the very next walk (no cached sentinel).
        cache2 = self.cache_base / "cursor-public" / "continual-learning" / "feedface"
        write_json(cache2 / ".cursor-plugin" / "plugin.json",
                   {"name": "continual-learning", "hooks": "./hooks/hooks.json"})
        write_json(cache2 / "hooks" / "hooks.json", {"version": 1, "hooks": {"stop": []}})
        (cache2 / "agents").mkdir(parents=True, exist_ok=True)
        found = governor.discover_cache_roots(DESC)
        self.assertIn(cache2, found)


class RetargetTests(GovernorTestBase):
    def test_validate_exact_counts_pass_and_fail(self):
        cache = make_cache(self.cache_base)
        ok, _ = governor.validate_retarget(cache, DESC)
        self.assertTrue(ok)
        # too many AGENTS.md tokens in the updater -> untrustworthy target -> invalid
        bad = make_cache(self.cache_base, updater_from=8)
        ok2, detail = governor.validate_retarget(bad, DESC)
        self.assertFalse(ok2)
        self.assertIn("agents-memory-updater.md", detail)

    def test_partial_retarget_still_validates_by_sum(self):
        # 4 AGENTS.md + 3 agent-learnings.md == expected 7 for the updater
        cache = make_cache(self.cache_base, updater_from=4, updater_to=3)
        ok, _ = governor.validate_retarget(cache, DESC)
        self.assertTrue(ok)

    def test_apply_retarget_removes_all_agents_md_tokens_and_is_idempotent(self):
        cache = make_cache(self.cache_base)
        changed, _ = governor.apply_retarget_all(cache, DESC)
        self.assertTrue(changed)
        # THE M1 SAFETY PROPERTY: no writer file can still write a tracked AGENTS.md.
        for t in DESC["retargetTargets"]:
            text = (cache / t["file"]).read_text()
            self.assertEqual(text.count("AGENTS.md"), 0, t["file"])
            self.assertEqual(text.count("agent-learnings.md"), t["expectedCount"], t["file"])
        # cadence projected to 50/1440
        cmd = governor.load_json(cache / "hooks" / "hooks.json")["hooks"]["stop"][0]["command"]
        self.assertIn("CONTINUAL_LEARNING_MIN_TURNS=50", cmd)
        self.assertIn("CONTINUAL_LEARNING_MIN_MINUTES=1440", cmd)
        # idempotent
        changed2, _ = governor.apply_retarget_all(cache, DESC)
        self.assertFalse(changed2)

    def test_restore_on_fail_puts_writers_back_byte_for_byte(self):
        cache = make_cache(self.cache_base)
        originals = {t["file"]: (cache / t["file"]).read_bytes() for t in DESC["retargetTargets"]}
        orig_project = governor.project_cadence
        governor.project_cadence = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(RuntimeError):
                governor.apply_retarget_all(cache, DESC)
        finally:
            governor.project_cadence = orig_project
        for rel, data in originals.items():
            self.assertEqual((cache / rel).read_bytes(), data, rel)


class FingerprintTests(GovernorTestBase):
    def test_bare_upstream_and_governed_projection_keep_approved_hash(self):
        """The pinned upstream bare hook and its governed projection are one behavior."""
        cache = self.make_upstream_cache()
        self.assertEqual(governor.meta_field("provenance_ref"), APPROVED_PROVENANCE)
        expected_from = {t["file"]: t["expectedCount"] for t in DESC["retargetTargets"]}

        ok, detail = governor.validate_retarget(cache, DESC)
        self.assertTrue(ok, detail)
        self.assertEqual(self.writer_from_counts(cache), expected_from)

        before = governor.behavior_hash(cache, DESC)
        before_state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(before, APPROVED_PROVENANCE)
        self.assertEqual(before_state, governor.STATE_BLESSED)

        changed, _ = governor.apply_retarget_all(cache, DESC)
        self.assertTrue(changed)
        after = governor.behavior_hash(cache, DESC)
        after_state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(after, APPROVED_PROVENANCE)
        self.assertEqual(after, before)
        self.assertEqual(after_state, governor.STATE_BLESSED)

        command = governor.load_json(cache / "hooks" / "hooks.json")["hooks"]["stop"][0][
            "command"
        ]
        self.assertEqual(command, stop_command(50, 1440))
        self.assertEqual(
            self.writer_from_counts(cache),
            {t["file"]: 0 for t in DESC["retargetTargets"]},
        )
        for target in DESC["retargetTargets"]:
            text = (cache / target["file"]).read_text()
            self.assertEqual(text.count(target["to"]), target["expectedCount"], target["file"])

    def test_unrecognized_command_shapes_are_never_blessed(self):
        variants = {
            "unrelated env": f"UNRELATED=1 {BARE_STOP_COMMAND}",
            "partial cadence": f"CONTINUAL_LEARNING_MIN_TURNS=80 {BARE_STOP_COMMAND}",
            "reordered cadence": (
                "CONTINUAL_LEARNING_MIN_MINUTES=960 CONTINUAL_LEARNING_MIN_TURNS=80 "
                f"{BARE_STOP_COMMAND}"
            ),
            "wrong runner": "node ${CURSOR_PLUGIN_ROOT}/hooks/continual-learning-stop.ts",
            "extra suffix": f"{stop_command(80, 960)} --unexpected",
            "shell chain": f"{stop_command(80, 960)} && echo unexpected",
            "extra whitespace": (
                "CONTINUAL_LEARNING_MIN_TURNS=80  CONTINUAL_LEARNING_MIN_MINUTES=960 "
                f"{BARE_STOP_COMMAND}"
            ),
        }
        for index, (name, command) in enumerate(variants.items()):
            with self.subTest(name=name):
                cache = self.make_upstream_cache(f"bad-{index}")
                hooks_path = cache / "hooks" / "hooks.json"
                hooks = governor.load_json(hooks_path)
                hooks["hooks"]["stop"][0]["command"] = command
                write_json(hooks_path, hooks)

                actual = governor.behavior_hash(cache, DESC)
                state, _ = governor.classify_root(cache, DESC)
                self.assertNotEqual(actual, APPROVED_PROVENANCE)
                self.assertNotEqual(state, governor.STATE_BLESSED)

    def test_fingerprint_is_projection_invariant(self):
        """Retargeting the writers and projecting cadence must NOT change the behavior fingerprint,
        otherwise every projection would self-drift the cache out of BLESSED."""
        cache = make_cache(self.cache_base, turns=15, minutes=180)
        before = governor.behavior_hash(cache, DESC)
        governor.apply_retarget_all(cache, DESC)
        after = governor.behavior_hash(cache, DESC)
        self.assertEqual(before, after)

    def test_fingerprint_changes_when_real_behavior_changes(self):
        cache = make_cache(self.cache_base)
        before = governor.behavior_hash(cache, DESC)
        # inject a genuinely new instruction line (not a target token, not an env value)
        p = cache / "agents" / "agents-memory-updater.md"
        p.write_text(p.read_text() + "NEW BEHAVIOR: also delete files.\n")
        self.assertNotEqual(governor.behavior_hash(cache, DESC), before)


class ClassifyTests(GovernorTestBase):
    def test_blessed_when_fingerprint_matches(self):
        cache = make_cache(self.cache_base)
        self.bless(cache)
        state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(state, governor.STATE_BLESSED)

    def test_containable_when_fingerprint_drifts(self):
        cache = make_cache(self.cache_base)
        self._forced_provenance = "0" * 64  # stale bless
        state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(state, governor.STATE_CONTAINABLE)

    def test_incompatible_when_counts_unidentifiable(self):
        cache = make_cache(self.cache_base, skill_from=9)
        state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(state, governor.STATE_INCOMPATIBLE)

    def test_incompatible_when_cadence_ambiguous(self):
        cmd = stop_command(15, 180)
        cache = make_cache(self.cache_base, stop_entries=[{"command": cmd}, {"command": cmd}])
        state, _ = governor.classify_root(cache, DESC)
        self.assertEqual(state, governor.STATE_INCOMPATIBLE)


class NeutralizeTests(GovernorTestBase):
    def _stop_entries(self, cache: Path):
        return governor.load_json(cache / "hooks" / "hooks.json")["hooks"].get("stop", [])

    def test_neutralize_rewrites_command_to_noop(self):
        cache = make_cache(self.cache_base, skill_from=9)  # INCOMPATIBLE
        governor.neutralize(cache, DESC)
        entries = self._stop_entries(cache)
        for e in entries:
            self.assertNotIn(STOP_TS_REL, e.get("command", ""))
        # exactly the governed no-op remains
        self.assertTrue(any("neutralized" in e.get("command", "") for e in entries))

    def test_neutralize_empty_when_command_unlocatable(self):
        cache = make_cache(self.cache_base, skill_from=9,
                           stop_entries=[{"command": "bun run something-else.ts"}])
        governor.neutralize(cache, DESC)
        # our stop-hook script is not present; governor still must ensure it can't run -> command kept
        # only if unrelated; the continual-learning command specifically must be absent.
        for e in self._stop_entries(cache):
            self.assertNotIn(STOP_TS_REL, e.get("command", ""))

    def test_neutralize_unparseable_hooks_writes_contained_empty_stop(self):
        cache = make_cache(self.cache_base, skill_from=9, hooks_raw="{ this is not json ")
        governor.neutralize(cache, DESC)
        data = governor.load_json(cache / "hooks" / "hooks.json")
        self.assertEqual(data["hooks"]["stop"], [])


class GlobalExcludeTests(GovernorTestBase):
    def test_ensure_adds_both_and_check_passes_idempotently(self):
        changed, _ = governor.ensure_global_excludes(DESC, apply=True)
        self.assertTrue(changed)
        text = self.excludes_file.read_text()
        self.assertIn("agent-learnings.md", text)
        self.assertIn(".cursor/hooks/state/", text)
        ok, _ = governor.check_global_excludes(DESC)
        self.assertTrue(ok)
        # idempotent: second apply adds nothing
        changed2, _ = governor.ensure_global_excludes(DESC, apply=True)
        self.assertFalse(changed2)


class HookstateGitignoreTests(GovernorTestBase):
    """Tests for ensure_hookstate_gitignore() — the self-ignoring state-dir fix."""

    def test_creates_gitignore_with_star_content(self):
        ws = self._tmp / "workspace"
        ws.mkdir()
        changed, _ = governor.ensure_hookstate_gitignore(workspace_root=ws)
        self.assertTrue(changed)
        gi = ws / ".cursor" / "hooks" / "state" / ".gitignore"
        self.assertTrue(gi.exists(), ".gitignore not created")
        self.assertEqual(gi.read_text(), "*\n")

    def test_idempotent_second_call_returns_false(self):
        ws = self._tmp / "workspace"
        ws.mkdir()
        governor.ensure_hookstate_gitignore(workspace_root=ws)
        changed2, _ = governor.ensure_hookstate_gitignore(workspace_root=ws)
        self.assertFalse(changed2)
        gi = ws / ".cursor" / "hooks" / "state" / ".gitignore"
        self.assertEqual(gi.read_text(), "*\n")

    def test_overwrites_wrong_content(self):
        ws = self._tmp / "workspace"
        state_dir = ws / ".cursor" / "hooks" / "state"
        state_dir.mkdir(parents=True)
        gi = state_dir / ".gitignore"
        gi.write_text("# stale content\n")
        changed, _ = governor.ensure_hookstate_gitignore(workspace_root=ws)
        self.assertTrue(changed)
        self.assertEqual(gi.read_text(), "*\n")

    def test_creates_dir_when_absent(self):
        ws = self._tmp / "workspace2"
        ws.mkdir()
        state_dir = ws / ".cursor" / "hooks" / "state"
        self.assertFalse(state_dir.exists())
        governor.ensure_hookstate_gitignore(workspace_root=ws)
        self.assertTrue(state_dir.is_dir())
        self.assertTrue((state_dir / ".gitignore").exists())

    def test_git_status_invisible_after_gitignore_written(self):
        """In a real nested git repo, state residue is invisible after the fix."""
        repo = self._tmp / "git_repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"],
                       check=True, capture_output=True)

        # Simulate workspace rooted at a SUBDIRECTORY of the repo (the problematic case).
        workspace = repo / "projects" / "my-project"
        workspace.mkdir(parents=True)

        # Write the .gitignore FIRST (as the governor would at session start).
        governor.ensure_hookstate_gitignore(workspace_root=workspace)

        # Now simulate the stop hook writing state files.
        state_dir = workspace / ".cursor" / "hooks" / "state"
        (state_dir / "continual-learning.json").write_text('{"version":1}\n')
        (state_dir / "continual-learning-index.json").write_text('{}\n')

        # Add a sibling tracked file to confirm normal tracking still works.
        tracked = repo / "README.md"
        tracked.write_text("hello\n")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"],
                       check=True, capture_output=True)

        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        lines = result.stdout.strip().splitlines()
        # The tracked README.md shows up; state residue must NOT.
        for line in lines:
            self.assertNotIn("continual-learning", line,
                             f"state residue visible in git status: {line!r}")
        self.assertTrue(any("README.md" in ln for ln in lines),
                        "expected README.md to appear in git status")

    def test_run_apply_writes_hookstate_gitignore_via_env(self):
        """run_apply() must call ensure_hookstate_gitignore (redirected via env var)."""
        cache = make_cache(self.cache_base)
        self.bless(cache)
        # hookstate_dir is already set to self._tmp/hookstate via setUp env var
        rc = governor.run_apply(cache_only=True)
        self.assertEqual(rc, 0)
        gi = self.hookstate_dir / ".gitignore"
        self.assertTrue(gi.exists(), "run_apply did not write hookstate .gitignore")
        self.assertEqual(gi.read_text(), "*\n")


class RunApplyEndToEndTests(GovernorTestBase):
    def test_blessed_apply_returns_zero_and_strips_all_agents_md(self):
        cache = make_cache(self.cache_base)
        self.bless(cache)
        rc = governor.run_apply(cache_only=False)
        self.assertEqual(rc, 0)
        for t in DESC["retargetTargets"]:
            self.assertEqual((cache / t["file"]).read_text().count("AGENTS.md"), 0, t["file"])
        # state marker written BLESSED
        marker = governor.load_json(governor.governor_state_dir() / "state.json")
        self.assertEqual(marker["worst"], governor.STATE_BLESSED)
        # sessionStart reapply hook installed into the (temp) cursor hooks.json
        hj = governor.load_json(self.cursor_home / "hooks.json")
        markers = [e.get("description") for e in hj["hooks"]["sessionStart"]]
        self.assertIn(DESC["sessionStart"]["marker"], markers)

    def test_incompatible_apply_returns_one_and_neutralizes(self):
        cache = make_cache(self.cache_base, skill_from=9)
        rc = governor.run_apply(cache_only=True)
        self.assertEqual(rc, 1)
        for e in governor.load_json(cache / "hooks" / "hooks.json")["hooks"].get("stop", []):
            self.assertNotIn(STOP_TS_REL, e.get("command", ""))
        marker = governor.load_json(governor.governor_state_dir() / "state.json")
        self.assertEqual(marker["worst"], governor.STATE_INCOMPATIBLE)

    def test_containable_apply_retargets_but_flags(self):
        cache = make_cache(self.cache_base)
        self._forced_provenance = "0" * 64
        rc = governor.run_apply(cache_only=True)
        # CONTAINABLE still retargets (rc 0) but is flagged for re-bless
        self.assertEqual(rc, 0)
        for t in DESC["retargetTargets"]:
            self.assertEqual((cache / t["file"]).read_text().count("AGENTS.md"), 0, t["file"])
        marker = governor.load_json(governor.governor_state_dir() / "state.json")
        self.assertEqual(marker["worst"], governor.STATE_CONTAINABLE)


class LockTests(GovernorTestBase):
    def test_apply_lock_grants_when_free(self):
        with governor.apply_lock() as got:
            self.assertTrue(got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
