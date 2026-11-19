#!/usr/bin/env python3
"""Tests for admission, fail-closed output, idempotence, and process boundaries."""

from __future__ import annotations

import importlib.util
import json
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
        self.home = root / "home"
        self.home.mkdir()
        self.route = root / "agent-route.sh"
        self.route.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        self.roots: list[dict[str, object]] = []
        self.commands: list[list[str]] = []

    def seed(self, *bullets: str) -> None:
        (self.home / "agent-learnings.md").write_text(
            learned(*bullets), encoding="utf-8"
        )

    def source(
        self,
        relative: str,
        origin: str,
        *bullets: str,
    ) -> Path:
        root = self.home / relative
        root.mkdir(parents=True)
        (root / "agent-learnings.md").write_text(
            learned(*bullets), encoding="utf-8"
        )
        self.roots.append(
            {
                "abs_path": str(root),
                "exists": True,
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

    def run(self, *, dry_run: bool = False) -> dict[str, object]:
        return consolidator.consolidate_home(
            self.home,
            self.route,
            dry_run=dry_run,
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
            )
            harness.source(
                "dev/affirm/work-b",
                "Affirm/work-b",
                work_only,
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
