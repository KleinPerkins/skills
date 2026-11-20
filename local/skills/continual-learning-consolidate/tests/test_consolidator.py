#!/usr/bin/env python3
"""Tests for admission, fail-closed output, idempotence, and process boundaries."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
MAIN_PATH = SKILL_DIR / "scripts" / "continual_learning_consolidate.py"
SPEC = importlib.util.spec_from_file_location("consolidator", MAIN_PATH)
assert SPEC and SPEC.loader
consolidator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consolidator
SPEC.loader.exec_module(consolidator)


def learned(*bullets: str) -> str:
    return (
        "## Learned User Preferences\n\n"
        + "".join(f"- {bullet}\n" for bullet in bullets)
    )


class Harness:
    def __init__(self, root: Path) -> None:
        self.home = (root / "home").resolve()
        self.home.mkdir()
        self.route = root / "agent-route.sh"
        self.route.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        self.roots: list[dict[str, object]] = []
        self.commands: list[list[str]] = []
        self.policy_path = self.home / ".local/share/continual-learning-consolidate/classifications.json"
        self.policy_path.parent.mkdir(parents=True)
        self.policy = {"schema": "memory-source-classification/v1", "repositories": [], "excluded_paths": []}

    def seed(self, *bullets: str) -> None:
        (self.home / "agent-learnings.md").write_text(
            learned(*bullets), encoding="utf-8"
        )

    def source(
        self,
        relative: str,
        origin: str,
        *bullets: str,
        classification: str = "personal",
        identity: str | None = None,
    ) -> Path:
        root = self.home / relative
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "agent-learnings.md").write_text(
            learned(*bullets), encoding="utf-8"
        )
        identity = identity or "repo-" + hashlib.sha256(origin.lower().encode()).hexdigest()[:12]
        rows = self.policy["repositories"]
        row = next((row for row in rows if row["repository_id"] == identity), None)
        if row is None:
            row = {"repository_id": identity, "classification": classification, "active_bindings": [], "origin_aliases": [origin]}
            rows.append(row)
        common = str(root / ".git")
        row["active_bindings"].append({"primary_path": str(root), "git_common_dir": common})
        self.roots.append(
            {
                "abs_path": str(root),
                "exists": True,
                "primary_abs_path": str(root),
                "git_common_dir": common,
                "origin": origin,
                "live_origin": origin,
            }
        )
        return root

    def runner(self, command: list[str], **_: object) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"home_root": str(self.home), "roots": self.roots}),
            stderr="",
        )

    def run(self, *, dry_run: bool = False, write_policy: bool = True) -> dict[str, object]:
        if write_policy:
            self.policy_path.write_text(json.dumps(self.policy))
        return consolidator.consolidate_home(
            self.home,
            self.route,
            dry_run=dry_run,
            policy_path=self.policy_path,
            runner=self.runner,
        )


class AdmissionTests(unittest.TestCase):
    def test_admission_firewall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            seed_one = "Prefer simple durable systems for every operator."
            seed_two = "The owner maintains several personal tooling projects."
            shared = "Shared recurring operational fact lives in this system."
            work_only = "Work only recurring launch process detail stays local."
            duplicate_clone = "Duplicate clone evidence must not promote by itself."
            harness.seed(seed_one, seed_two)

            harness.source(
                "dev/affirm/work-a",
                "Affirm/work-a",
                seed_one,
                shared,
                work_only,
                classification="work",
            )
            harness.source(
                "dev/affirm/work-b",
                "Affirm/work-b",
                work_only,
                classification="work",
            )
            harness.source(
                "dev/personal/personal-a",
                "KleinPerkins/personal-a",
                shared,
                "A personal one off detail remains workspace local.",
            )
            harness.source(
                "clone-one",
                "KleinPerkins/duplicate",
                duplicate_clone,
            )
            harness.source(
                "clone-two",
                "KleinPerkins/duplicate",
                duplicate_clone,
            )

            report = harness.run()
            output = (harness.home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(seed_one, output)
            self.assertIn(seed_two, output)
            self.assertIn(shared, output)
            self.assertNotIn(work_only, output)
            self.assertNotIn("personal one off", output)
            self.assertNotIn(duplicate_clone, output)
            self.assertEqual(report["canonical_bullets"], 3)
            self.assertEqual(report["matched_home_seed"], 1)
            self.assertGreaterEqual(report["work_only_rejected"], 2)

    def test_same_origin_clones_are_not_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A stable home seed is always admitted.")
            repeated = "Matching clone bullets are not independent root evidence."
            harness.source("one", "KleinPerkins/same", repeated)
            harness.source("two", "KleinPerkins/same", repeated)

            harness.run()
            output = (harness.home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn(repeated, output)


class FailClosedTests(unittest.TestCase):
    def test_scanner_block_leaves_output_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            fake_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789"
            harness.seed(f"Unsafe token {fake_token} must block.")
            target = harness.home / "AGENTS.md"
            target.write_bytes(b"prior output\n")

            with self.assertRaises(consolidator.ConsolidationError):
                harness.run()
            self.assertEqual(target.read_bytes(), b"prior output\n")

    def test_scanner_exception_leaves_output_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A safe source bullet remains available here.")
            target = harness.home / "AGENTS.md"
            target.write_bytes(b"prior output\n")

            with mock.patch.object(
                consolidator.memory, "scan", side_effect=RuntimeError("scanner crash")
            ):
                with self.assertRaises(consolidator.ConsolidationError):
                    harness.run()
            self.assertEqual(target.read_bytes(), b"prior output\n")

    def test_missing_seed_leaves_output_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            target = harness.home / "AGENTS.md"
            target.write_bytes(b"prior output\n")

            with self.assertRaises(consolidator.ConsolidationError):
                harness.run()
            self.assertEqual(target.read_bytes(), b"prior output\n")

    def test_source_parse_failure_leaves_output_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A safe source bullet remains available here.")
            broken = harness.source(
                "dev/personal/broken",
                "KleinPerkins/broken",
                "Temporary valid value.",
            )
            (broken / "agent-learnings.md").write_bytes(b"\xff\xfe")
            target = harness.home / "AGENTS.md"
            target.write_bytes(b"prior output\n")

            with self.assertRaises(consolidator.ConsolidationError):
                harness.run()
            self.assertEqual(target.read_bytes(), b"prior output\n")

    def test_nonmachine_placeholder_source_is_skipped_not_blocking(self) -> None:
        # A fresh clone/worktree placeholder (valid UTF-8, non-empty, no machine
        # headings) must be skipped like an empty file, never fail the run. Kept free
        # of any governed-sibling repo identifiers so the repo's zero-link invariant
        # stays green (see .github/scripts/verify-skills.sh); the exact bytes are
        # irrelevant to the code path under test (non-empty + valid UTF-8 + no machine
        # headings) -- only the shape of an auto-generated human-readable stub matters.
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A stable home seed bullet is always admitted.")
            placeholder = harness.source(
                "dev/personal/fresh-clone-wt",
                "KleinPerkins/fresh-clone",
                "temporary value to be overwritten",
            )
            (placeholder / "agent-learnings.md").write_text(
                "# Agent learnings\n\n"
                "Machine-local continual-learning memory for this clone. "
                "Never commit this file.\n",
                encoding="utf-8",
            )
            target = harness.home / "AGENTS.md"

            report = harness.run()

            output = target.read_text(encoding="utf-8")
            self.assertTrue(report["changed"])
            self.assertIn("A stable home seed bullet", output)
            self.assertNotIn("Machine-local continual-learning memory", output)


class ProjectionTests(unittest.TestCase):
    def test_projection_uses_compact_generated_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A stable home seed is always admitted.")

            harness.run()
            output = (harness.home / "AGENTS.md").read_text(encoding="utf-8")

            self.assertTrue(
                output.startswith(
                    "<!-- generated; edit agent-learnings.md sources, not this file -->\n"
                    "## Learned User Preferences\n"
                    "- A stable home seed is always admitted."
                )
            )
            self.assertNotIn("## Learned User Preferences\n\n-", output)

    def test_idempotence_skips_second_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A stable home seed is always admitted.")
            first = harness.run()
            target = harness.home / "AGENTS.md"
            first_bytes = target.read_bytes()
            first_mtime = target.stat().st_mtime_ns
            second = harness.run()

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertEqual(target.read_bytes(), first_bytes)
            self.assertEqual(target.stat().st_mtime_ns, first_mtime)

    def test_agents_output_is_not_memory_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("Only the machine local seed is an input source.")
            (harness.home / "AGENTS.md").write_text(
                learned("Hand edited output must be discarded."),
                encoding="utf-8",
            )

            harness.run()
            output = (harness.home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Only the machine local seed", output)
            self.assertNotIn("Hand edited output", output)

    def test_only_process_call_is_agent_route_never_git_or_gh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            harness.seed("A stable home seed is always admitted.")

            harness.run(dry_run=True)
            self.assertEqual(len(harness.commands), 1)
            command = harness.commands[0]
            self.assertEqual(
                command,
                ["/bin/bash", str(harness.route), "map", "--json"],
            )
            executables = {Path(part).name for part in command}
            self.assertNotIn("git", executables)
            self.assertNotIn("gh", executables)


class ClassificationTests(unittest.TestCase):
    def test_assignment_overrides_owner_and_employer_looking_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            shared = "Accepted personal evidence corroborates this reusable practice."
            work_only = "Work-only process detail must remain within its workspaces."
            h.source("dev/employer/personal", "Employer/personal-archive", shared, classification="personal")
            h.source("personal/other", "Person/other", shared)
            h.source("personal/work", "Person/analytics", work_only, classification="work")
            h.source("future-employer/work", "Future/work", work_only, classification="work")
            h.run()
            output = (h.home / "AGENTS.md").read_text()
            self.assertIn(shared, output)
            self.assertNotIn(work_only, output)

    def test_work_linked_worktrees_never_become_personal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            phrase = "Recurring work evidence remains private across native worktrees."
            for i in range(2):
                h.source(f"work-primary-{i}", f"Employer/repo-{i}", phrase, classification="work")
                root = dict(h.roots[-1])
                path = h.home / f"native-worktree-{i}"
                path.mkdir()
                (path / "agent-learnings.md").write_text(learned(phrase))
                root["abs_path"] = str(path)
                admin = Path(root["git_common_dir"]) / "worktrees" / f"native-{i}"
                admin.mkdir(parents=True)
                (path / ".git").write_text("gitdir: " + str(admin) + "\n")
                (admin / "commondir").write_text("../..\n")
                (admin / "gitdir").write_text(str(path / ".git") + "\n")
                h.roots.append(root)
            report = h.run()
            self.assertEqual(report["workspace_sources"], 4)
            self.assertNotIn(phrase, (h.home / "AGENTS.md").read_text())

    def test_equivalent_origins_and_clones_share_logical_identity(self) -> None:
        variants = ["git@GitHub.com:Example/One.git", "https://github.com/example/one/", "ssh://git@github.com/EXAMPLE/one.git/", "github.com/example/one", "EXAMPLE/One.git/"]
        self.assertEqual({consolidator.classifications.normalize_origin(v) for v in variants}, {"github.com/example/one"})
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            phrase = "A single logical repository cannot corroborate its own clones."
            for i, origin in enumerate(variants):
                h.source(f"clone-{i}", origin, phrase, identity="accepted-one")
            report = h.run()
            self.assertEqual(report["workspace_sources"], len(variants))
            self.assertEqual(report["unknown_or_excluded_roots"], 0)
            self.assertNotIn(phrase, (h.home / "AGENTS.md").read_text())

    def test_origin_ports_preserve_distinct_endpoints_and_reject_invalid_ports(self) -> None:
        normalize = consolidator.classifications.normalize_origin
        base = "github.com/example/repository"
        for origin in ["ssh://git@github.com:22/example/repository.git", "https://github.com:443/example/repository", "http://github.com:80/example/repository", "git://github.com:9418/example/repository"]:
            self.assertEqual(normalize(origin), base)
        for origin in ["ssh://git@github.com:2222/example/repository", "https://github.com:2222/example/repository", "github.com:2222/example/repository"]:
            value = normalize(origin)
            self.assertEqual(value, "github.com:2222/example/repository")
            self.assertEqual(normalize(value), value)
            self.assertNotEqual(value, base)
        for origin in ["ssh://git@github.com:bad/example/repository", "https://github.com:65536/example/repository", "https://github.com:0/example/repository", "github.com:bad/example/repository"]:
            with self.assertRaises(consolidator.classifications.PolicyError): normalize(origin)

    def test_accepted_aliases_deduplicate_across_clones_but_conflict_within_one_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            phrase = "Accepted logical aliases still cannot corroborate one repository twice."
            original = "git@github.com:Example/one-original.git"
            successor = "https://github.com/example/one"
            h.source("original", original, phrase, identity="logical-one")
            second = h.source("successor", successor, phrase, identity="logical-one")
            h.policy["repositories"][0]["origin_aliases"].append(successor)
            h.roots[0]["origin"] = "https://github.com/example/one-original/"
            report = h.run()
            self.assertEqual(report["workspace_sources"], 2)
            self.assertEqual(report["unknown_or_excluded_roots"], 0)
            self.assertNotIn(phrase, (h.home / "AGENTS.md").read_text())
            h.roots[1]["origin"] = original
            (second / "agent-learnings.md").write_bytes(b"\xff")
            report = h.run()
            self.assertEqual(report["workspace_sources"], 1)
            self.assertEqual(report["unknown_or_excluded_roots"], 1)

    def test_unknowns_never_open_memory_or_corroborate(self) -> None:
        for change in ["unassigned", "unknown", "missing-primary", "missing-common", "changed-common", "changed-origin"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                h = Harness(Path(directory))
                h.seed("Keep a durable machine-local seed.")
                phrase = "A lone accepted personal source requires independent evidence."
                h.source("personal", "Example/personal", phrase)
                unknown = h.source("unknown", "Example/unknown", phrase)
                if change == "unassigned":
                    h.policy["repositories"].pop()
                elif change == "unknown":
                    h.policy["repositories"][-1]["classification"] = "unknown"
                elif change.startswith("missing-"):
                    h.roots[-1].pop("primary_abs_path" if change == "missing-primary" else "git_common_dir")
                elif change == "changed-common":
                    h.roots[-1]["git_common_dir"] = str(h.home / "unvalidated-store")
                else:
                    h.roots[-1]["live_origin"] = "https://github.com/other/identity"
                # Unreadable memory is a sentinel: opening it would block the run.
                (unknown / "agent-learnings.md").write_bytes(b"\xff")
                report = h.run()
                self.assertEqual(report["unknown_or_excluded_roots"], 1)
                self.assertNotIn(phrase, (h.home / "AGENTS.md").read_text())

    def test_clone_bindings_never_match_a_primary_common_cross_product(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            h.source("one", "Example/same", "First clone.", identity="same")
            second = h.source("two", "Example/same", "Second clone.", identity="same")
            h.roots[-1]["primary_abs_path"] = h.roots[0]["primary_abs_path"]
            (second / "agent-learnings.md").write_bytes(b"\xff")
            self.assertEqual(h.run()["unknown_or_excluded_roots"], 1)

    def test_recovery_and_retired_roots_excluded_despite_active_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            h.source("active", "Example/active", "A single local fact stays local.")
            for name in ["recovery/archive", "retired-linked-root"]:
                path = h.home / name
                path.mkdir(parents=True)
                (path / "agent-learnings.md").write_bytes(b"\xff")
                row = dict(h.roots[0], abs_path=str(path))
                h.roots.append(row)
                h.policy["excluded_paths"].append(str(path.parent if name.startswith("recovery/") else path))
            report = h.run()
            self.assertEqual(report["unknown_or_excluded_roots"], 2)
            self.assertEqual(report["workspace_sources"], 1)

    def test_discovered_root_symlink_cannot_erase_lexical_exclusion(self) -> None:
        for prefix in ["recovery", "unreviewed-alias"]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                h = Harness(Path(directory))
                h.seed("Keep a durable machine-local seed.")
                active = h.source("active", "Example/active", "Initial memory.")
                (active / "agent-learnings.md").write_bytes(b"\xff")
                alias = h.home / prefix / "alias"
                alias.parent.mkdir()
                alias.symlink_to(active, target_is_directory=True)
                h.policy["excluded_paths"] = [str(h.home / "recovery")]
                # Only the alias is discovered; borrowing its target would read
                # the invalid sentinel, despite the accepted target metadata.
                h.roots[0]["abs_path"] = str(alias)
                report = h.run()
                self.assertEqual(report["unknown_or_excluded_roots"], 1)
                self.assertEqual(report["workspace_sources"], 0)

    def test_active_memory_symlink_cannot_read_excluded_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            active = h.source("active", "Example/active", "Temporary source.")
            recovery = h.home / "recovery"
            recovery.mkdir()
            excluded = recovery / "agent-learnings.md"
            excluded.write_bytes(b"\xff")
            h.policy["excluded_paths"] = [str(recovery)]
            candidate = active / "agent-learnings.md"
            candidate.unlink()
            candidate.symlink_to(excluded)
            report = h.run()
            self.assertEqual(report["unknown_or_excluded_roots"], 1)
            self.assertEqual(report["workspace_sources"], 0)

    def test_workspace_memory_symlink_swap_is_blocked_at_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            active = h.source("active", "Example/active", "Initial regular memory.")
            recovery = h.home / "recovery"
            recovery.mkdir()
            excluded = recovery / "agent-learnings.md"
            excluded.write_text(learned("Excluded memory must never be read through a raced alias."))
            h.policy["excluded_paths"] = [str(recovery)]
            candidate = active / "agent-learnings.md"
            target = h.home / "AGENTS.md"
            target.write_bytes(b"prior output")
            original_read = consolidator._read_bullets
            def swap_at_open(path: Path, **kwargs):
                if path == candidate:
                    self.assertTrue(kwargs["no_follow"])
                    candidate.unlink()
                    candidate.symlink_to(excluded)
                return original_read(path, **kwargs)
            with mock.patch.object(consolidator, "_read_bullets", side_effect=swap_at_open):
                with self.assertRaises(consolidator.ConsolidationError): h.run()
            self.assertEqual(target.read_bytes(), b"prior output")

    def test_workspace_directory_swap_keeps_the_opened_admitted_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            phrase = "Original admitted directory memory is corroborated by another repository."
            active = h.source("active", "Example/active", phrase)
            h.source("other", "Example/other", phrase)
            recovery = h.home / "recovery"
            recovery.mkdir()
            excluded = "Excluded directory memory must never be opened."
            (recovery / "agent-learnings.md").write_text(learned(excluded))
            h.policy["excluded_paths"] = [str(recovery)]
            candidate = active / "agent-learnings.md"
            original_read = consolidator._read_bullets
            def swap_directory(path: Path, **kwargs):
                if path == candidate:
                    active.rename(h.home / "held-active")
                    active.symlink_to(recovery, target_is_directory=True)
                return original_read(path, **kwargs)
            with mock.patch.object(consolidator, "_read_bullets", side_effect=swap_directory):
                h.run()
            output = (h.home / "AGENTS.md").read_text()
            self.assertIn(phrase, output)
            self.assertNotIn(excluded, output)

    def test_forged_route_root_cannot_borrow_an_accepted_binding(self) -> None:
        for shape in ["missing-git", "unrelated-git-directory", "missing-registration", "wrong-backpointer"]:
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as directory:
                h = Harness(Path(directory))
                h.seed("Keep a durable machine-local seed.")
                h.source("accepted", "Example/accepted", "A single accepted source.")
                forged = h.home / "forged"
                forged.mkdir()
                (forged / "agent-learnings.md").write_bytes(b"\xff")
                root = dict(h.roots[0], abs_path=str(forged))
                if shape == "unrelated-git-directory":
                    (forged / ".git").mkdir()
                elif shape in {"missing-registration", "wrong-backpointer"}:
                    admin = Path(root["git_common_dir"]) / "worktrees/forged"
                    admin.mkdir(parents=True)
                    (forged / ".git").write_text("gitdir: " + str(admin) + "\n")
                    if shape == "wrong-backpointer":
                        (admin / "commondir").write_text("../..\n")
                        (admin / "gitdir").write_text(str(h.home / "another-root/.git") + "\n")
                h.roots.append(root)
                report = h.run()
                self.assertEqual(report["unknown_or_excluded_roots"], 1)
                self.assertEqual(report["workspace_sources"], 1)

    def test_invalid_policy_preserves_output_and_precedes_seed_reads(self) -> None:
        cases = ["missing", "json", "schema", "classification", "duplicate-id", "common-conflict", "primary-conflict", "cross-role-conflict", "origin-conflict", "duplicate-key", "excluded-binding", "noncanonical", "extra-field"]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                h = Harness(Path(directory))
                h.seed("Keep a durable machine-local seed.")
                h.source("one", "Example/one", "One independent source.")
                h.source("two", "Example/two", "Another independent source.")
                first, second = h.policy["repositories"]
                if case == "schema": h.policy["schema"] = "unsupported/v9"
                elif case == "classification": first["classification"] = "guess"
                elif case == "duplicate-id": second["repository_id"] = first["repository_id"]
                elif case in {"common-conflict", "primary-conflict"}:
                    key = "git_common_dir" if case == "common-conflict" else "primary_path"
                    second["active_bindings"][0][key] = first["active_bindings"][0][key]
                elif case == "cross-role-conflict": second["active_bindings"][0]["git_common_dir"] = first["active_bindings"][0]["primary_path"]
                elif case == "origin-conflict": second["origin_aliases"] = ["git@github.com:example/one.git/"]
                elif case == "excluded-binding": h.policy["excluded_paths"] = [str(h.home / "one")]
                elif case == "noncanonical": first["active_bindings"][0]["primary_path"] += "/../one"
                elif case == "extra-field": first["allow_all_clones"] = True
                h.policy_path.write_text(json.dumps(h.policy))
                if case == "missing": h.policy_path.unlink()
                elif case == "json": h.policy_path.write_bytes(b"{")
                elif case == "duplicate-key": h.policy_path.write_text('{"schema":"old","schema":"new"}')
                target = h.home / "AGENTS.md"
                target.write_bytes(b"prior output")
                with mock.patch.object(consolidator, "_read_bullets", side_effect=AssertionError("must not read memory")):
                    with self.assertRaises(consolidator.ConsolidationError): h.run(write_policy=False)
                self.assertEqual(target.read_bytes(), b"prior output")

    def test_shared_observed_origin_cannot_bypass_optional_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            for i in range(2):
                h.source(f"clone-{i}", "Example/same", "One logical origin cannot corroborate itself.", identity=f"different-{i}")
                h.policy["repositories"][-1]["origin_aliases"] = []
            target = h.home / "AGENTS.md"
            target.write_bytes(b"prior output")
            with self.assertRaises(consolidator.ConsolidationError): h.run()
            self.assertEqual(target.read_bytes(), b"prior output")

    def test_policy_must_be_a_nofollow_regular_file(self) -> None:
        for shape in ["symlink", "fifo"]:
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as directory:
                h = Harness(Path(directory))
                h.seed("Keep a durable machine-local seed.")
                other = h.home / "other-policy.json"
                other.write_text(json.dumps(h.policy))
                if shape == "symlink": h.policy_path.symlink_to(other)
                else: os.mkfifo(h.policy_path)
                target = h.home / "AGENTS.md"
                target.write_bytes(b"prior output")
                with self.assertRaises(consolidator.ConsolidationError): h.run(write_policy=False)
                self.assertEqual(target.read_bytes(), b"prior output")

    def test_discovery_failure_preserves_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            h.policy_path.write_text(json.dumps(h.policy))
            target = h.home / "AGENTS.md"
            target.write_bytes(b"prior output")
            for result in [SimpleNamespace(returncode=1, stderr="unavailable", stdout=""), SimpleNamespace(returncode=0, stderr="", stdout="bad JSON")]:
                with self.assertRaises(consolidator.ConsolidationError):
                    consolidator.consolidate_home(h.home, h.route, policy_path=h.policy_path, runner=lambda *a, **k: result)
                self.assertEqual(target.read_bytes(), b"prior output")

    def test_scanner_warning_and_dry_run_do_not_bypass_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            h = Harness(Path(directory))
            h.seed("Keep a durable machine-local seed.")
            with mock.patch.object(consolidator.memory, "scan", return_value=([{"severity": "WARN"}], False)):
                report = h.run(dry_run=True)
            self.assertEqual(report["scanner_warnings"], 1)
            self.assertFalse((h.home / "AGENTS.md").exists())


class MemoryTests(unittest.TestCase):
    def test_capture_stops_at_non_bullet_prose(self) -> None:
        text = (
            "## Learned Workspace Facts\n\n"
            "- Machine fact.\n"
            "Curated prose ends the machine block.\n"
            "- Curated bullet.\n"
        )
        self.assertEqual(
            consolidator.memory.learned_bullets(text),
            [("Learned Workspace Facts", "Machine fact.")],
        )

    def test_near_duplicate_fails_toward_keep(self) -> None:
        left = "Alpha beta gamma delta epsilon unique."
        right = "Alpha beta unrelated theta iota kappa."
        self.assertFalse(consolidator.memory.near_duplicate(left, right))
        self.assertEqual(
            len(
                consolidator.memory.consolidate(
                    [
                        ("Learned Workspace Facts", left),
                        ("Learned Workspace Facts", right),
                    ]
                )
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
