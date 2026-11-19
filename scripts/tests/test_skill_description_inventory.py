#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "skill-description-inventory.py"
FIXTURES = (
    REPO
    / "scripts"
    / "tests"
    / "fixtures"
    / "skill-description-normalization-v1"
    / "cases.json"
)

SPEC = importlib.util.spec_from_file_location(
    "skill_description_inventory", SCRIPT
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("inventory module could not be loaded")
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)


def skill_bytes(name: str, description: str) -> bytes:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "---\n"
        "# Body\n"
    ).encode("utf-8")


class GitFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "config",
                "user.email",
                "test@example.invalid",
            ],
            check=True,
        )

    def write(self, relative: str, raw: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def commit(self, message: str = "fixture") -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "add", "-A"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", message],
            check=True,
        )

    def close(self) -> None:
        self.temp.cleanup()


class TestConformanceFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_fixture = FIXTURES.read_bytes()
        cls.fixture = json.loads(cls.raw_fixture.decode("utf-8"))

    def test_fixture_schema_and_canonical_bytes(self):
        self.assertEqual(
            self.fixture["schema"],
            "skill-description-normalization-fixtures/v1",
        )
        expected = (
            json.dumps(
                self.fixture, indent=2, sort_keys=True, ensure_ascii=True
            )
            + "\n"
        ).encode("ascii")
        self.assertEqual(self.raw_fixture, expected)
        self.assertEqual(len(hashlib.sha256(self.raw_fixture).hexdigest()), 64)

    def test_valid_yaml_and_normalization_cases(self):
        valid = [case for case in self.fixture["cases"] if not case["blocked"]]
        self.assertGreaterEqual(len(valid), 15)
        for case in valid:
            with self.subTest(case=case["id"]):
                raw = base64.b64decode(case["raw_base64"], validate=True)
                parsed = inventory.parse_frontmatter(raw, case["id"])
                native = parsed["description"]
                normalized = inventory.normalize_description(native)
                self.assertEqual(native, case["expected_native"])
                self.assertEqual(normalized, case["expected_normalized"])
                self.assertEqual(len(normalized), case["expected_count"])

    def test_blocked_yaml_cases_fail_closed(self):
        blocked = [case for case in self.fixture["cases"] if case["blocked"]]
        self.assertGreaterEqual(len(blocked), 20)
        for case in blocked:
            with self.subTest(case=case["id"]):
                raw = base64.b64decode(case["raw_base64"], validate=True)
                with self.assertRaises(inventory.BlockedPrerequisite):
                    inventory.parse_frontmatter(raw, case["id"])

    def test_duplicate_fixture_pair_normalizes_identically(self):
        by_id = {case["id"]: case for case in self.fixture["cases"]}
        left_id, right_id = self.fixture["duplicate_case_ids"]
        normalized = []
        for case_id in (left_id, right_id):
            raw = base64.b64decode(
                by_id[case_id]["raw_base64"], validate=True
            )
            parsed = inventory.parse_frontmatter(raw, case_id)
            normalized.append(
                inventory.normalize_description(parsed["description"])
            )
        self.assertEqual(normalized[0], normalized[1])


class TestCandidateDiscovery(unittest.TestCase):
    def setUp(self):
        self.git = GitFixture()

    def tearDown(self):
        self.git.close()

    def test_discovers_all_tracked_candidates_in_byte_order(self):
        self.git.write(
            "local/skills/zeta/SKILL.md", skill_bytes("zeta", "zeta")
        )
        self.git.write(
            "global/plugins/alpha/SKILL.md", skill_bytes("alpha", "alpha")
        )
        self.git.write("other/SKILL.md", skill_bytes("other", "other"))
        self.git.commit()
        candidates = inventory.discover_candidates(self.git.root)
        relative = [
            path.relative_to(self.git.root.resolve()).as_posix()
            for path in candidates
        ]
        self.assertEqual(
            relative,
            [
                "global/plugins/alpha/SKILL.md",
                "local/skills/zeta/SKILL.md",
            ],
        )

    def test_empty_candidate_set_blocks(self):
        self.git.write("README.md", b"empty\n")
        self.git.commit()
        with self.assertRaises(inventory.BlockedPrerequisite):
            inventory.discover_candidates(self.git.root)

    def test_untracked_descriptor_blocks(self):
        self.git.write(
            "global/skills/tracked/SKILL.md",
            skill_bytes("tracked", "tracked"),
        )
        self.git.commit()
        self.git.write(
            "local/skills/untracked/SKILL.md",
            skill_bytes("untracked", "untracked"),
        )
        with self.assertRaises(inventory.BlockedPrerequisite):
            inventory.discover_candidates(self.git.root)

    def test_node_modules_descriptors_are_not_candidates(self):
        self.git.write(
            "global/skills/tracked/SKILL.md",
            skill_bytes("tracked", "tracked"),
        )
        self.git.write(".gitignore", b"node_modules/\n")
        self.git.commit()
        self.git.write(
            "local/skills/runtime/node_modules/dependency/SKILL.md",
            skill_bytes("dependency", "dependency"),
        )
        candidates = inventory.discover_candidates(self.git.root)
        relative = [
            path.relative_to(self.git.root.resolve()).as_posix()
            for path in candidates
        ]
        self.assertEqual(relative, ["global/skills/tracked/SKILL.md"])

    def test_tracked_but_missing_descriptor_blocks(self):
        path = self.git.write(
            "global/skills/missing/SKILL.md",
            skill_bytes("missing", "missing"),
        )
        self.git.commit()
        path.unlink()
        with self.assertRaises(inventory.BlockedPrerequisite):
            inventory.discover_candidates(self.git.root)

    def test_non_git_root_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(inventory.BlockedPrerequisite):
                inventory.discover_candidates(Path(directory))


class TestInventory(unittest.TestCase):
    def make_valid_repo(self) -> GitFixture:
        git = GitFixture()
        git.write(
            "global/skills/alpha/SKILL.md",
            skill_bytes("alpha", "alpha description"),
        )
        git.write(
            "local/plugins/zeta/SKILL.md",
            skill_bytes("zeta", "zeta description"),
        )
        git.commit()
        return git

    def test_build_inventory_is_deterministic_and_complete(self):
        git = self.make_valid_repo()
        self.addCleanup(git.close)
        first = inventory.build_inventory(git.root)
        second = inventory.build_inventory(git.root)
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "skill-description-inventory/v1")
        self.assertEqual(
            first["normalization_contract"],
            "skill-description-normalization/v1",
        )
        self.assertEqual(
            first["parser_profile"], "skills-yaml12-core-profile/v1"
        )
        self.assertEqual(first["candidate_count"], 2)
        self.assertEqual(first["normalized_duplicates"], [])
        self.assertEqual(
            [row["path"] for row in first["candidates"]],
            [
                "global/skills/alpha/SKILL.md",
                "local/plugins/zeta/SKILL.md",
            ],
        )

    def test_duplicate_normalized_descriptions_block(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/alpha/SKILL.md",
            skill_bytes("alpha", '"same   value"'),
        )
        git.write(
            "local/skills/beta/SKILL.md",
            skill_bytes("beta", "same value"),
        )
        git.commit()
        with self.assertRaises(inventory.BlockedPrerequisite):
            inventory.build_inventory(git.root)

    def test_source_mutation_changes_only_bound_row(self):
        git = self.make_valid_repo()
        self.addCleanup(git.close)
        before = inventory.build_inventory(git.root)
        git.write(
            "global/skills/alpha/SKILL.md",
            skill_bytes("alpha", "alpha description expanded"),
        )
        git.commit("mutate alpha")
        after = inventory.build_inventory(git.root)
        before_rows = {row["path"]: row for row in before["candidates"]}
        after_rows = {row["path"]: row for row in after["candidates"]}
        self.assertNotEqual(
            before_rows["global/skills/alpha/SKILL.md"],
            after_rows["global/skills/alpha/SKILL.md"],
        )
        self.assertEqual(
            before_rows["local/plugins/zeta/SKILL.md"],
            after_rows["local/plugins/zeta/SKILL.md"],
        )
        self.assertNotEqual(
            before["total_normalized_characters"],
            after["total_normalized_characters"],
        )

    def test_repository_inventory_is_eligible(self):
        result = inventory.build_inventory(REPO)
        tracked_count = int(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(REPO),
                    "ls-files",
                    "-z",
                    "--",
                    "global",
                    "local",
                ],
                check=True,
                capture_output=True,
            ).stdout.count(b"\0")
        )
        expected = len(
            [
                path
                for path in subprocess.run(
                    [
                        "git",
                        "-C",
                        str(REPO),
                        "ls-files",
                        "global/**/SKILL.md",
                        "local/**/SKILL.md",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.splitlines()
                if path
            ]
        )
        self.assertGreater(tracked_count, expected)
        self.assertEqual(result["candidate_count"], expected)
        self.assertEqual(result["normalized_duplicates"], [])


class TestDescriptionBudget(unittest.TestCase):
    def test_threshold_constants_are_pinned(self):
        self.assertEqual(inventory.DESCRIPTION_BUDGET_WARNING_LIMIT, 300)
        self.assertEqual(inventory.DESCRIPTION_BUDGET_FAILURE_LIMIT, 600)
        self.assertEqual(inventory.DESCRIPTION_MIGRATION_FAILURE_LIMIT, 1024)

    def test_exact_boundaries_and_precedence(self):
        cases = (
            (0, None),
            (300, None),
            (301, ("DESCRIPTION_BUDGET_WARNING", 300)),
            (600, ("DESCRIPTION_BUDGET_WARNING", 300)),
            (601, ("DESCRIPTION_BUDGET_FAILURE", 600)),
            (1024, ("DESCRIPTION_BUDGET_FAILURE", 600)),
            (1025, ("DESCRIPTION_MIGRATION_FAILURE", 1024)),
        )
        for character_count, expected in cases:
            with self.subTest(character_count=character_count):
                self.assertEqual(
                    inventory.classify_description_budget(character_count),
                    expected,
                )


class TestCli(unittest.TestCase):
    def run_cli(self, root: Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(root)],
            check=False,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_success_output_is_byte_identical(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/alpha/SKILL.md",
            skill_bytes("alpha", "deterministic"),
        )
        git.commit()
        first = self.run_cli(git.root)
        second = self.run_cli(git.root)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(first.stdout.endswith(b"\n"))
        json.loads(first.stdout.decode("utf-8"))

    def test_warning_only_keeps_complete_v1_json_and_sorted_stderr(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/warning/SKILL.md",
            skill_bytes("warning", "w" * 301),
        )
        git.commit()
        expected_stdout = (
            json.dumps(
                inventory.build_inventory(git.root),
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            + "\n"
        ).encode("utf-8")
        result = self.run_cli(git.root)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, expected_stdout)
        self.assertEqual(
            result.stderr,
            b"DESCRIPTION_BUDGET_WARNING "
            b"global/skills/warning/SKILL.md: characters=301 limit=300\n",
        )
        self.assertEqual(
            json.loads(result.stdout.decode("utf-8"))["schema"],
            "skill-description-inventory/v1",
        )

    def test_mixed_global_local_budgets_are_complete_and_path_sorted(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/warning/SKILL.md",
            skill_bytes("warning", "w" * 301),
        )
        git.write(
            "local/skills/failure/SKILL.md",
            skill_bytes("failure", "f" * 601),
        )
        git.write(
            "local/skills/migration/SKILL.md",
            skill_bytes("migration", "m" * 1025),
        )
        git.commit()
        result = self.run_cli(git.root)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr,
            b"DESCRIPTION_BUDGET_WARNING "
            b"global/skills/warning/SKILL.md: characters=301 limit=300\n"
            b"DESCRIPTION_BUDGET_FAILURE "
            b"local/skills/failure/SKILL.md: characters=601 limit=600\n"
            b"DESCRIPTION_MIGRATION_FAILURE "
            b"local/skills/migration/SKILL.md: characters=1025 limit=1024\n",
        )
        self.assertNotIn(b"w" * 20, result.stderr)
        self.assertNotIn(b"f" * 20, result.stderr)
        self.assertNotIn(b"m" * 20, result.stderr)

    def test_budget_failure_is_nonzero_for_verifier_invocation(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/failure/SKILL.md",
            skill_bytes("failure", "f" * 601),
        )
        git.commit()
        result = self.run_cli(git.root)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr,
            b"DESCRIPTION_BUDGET_FAILURE "
            b"global/skills/failure/SKILL.md: characters=601 limit=600\n",
        )

    def test_malformed_candidate_emits_no_partial_inventory(self):
        git = GitFixture()
        self.addCleanup(git.close)
        git.write(
            "global/skills/bad/SKILL.md",
            b"---\nname: bad\ndescription: [optional: bad]\n---\n",
        )
        git.commit()
        result = self.run_cli(git.root)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        diagnostic = result.stderr.decode("utf-8")
        self.assertIn(
            "BLOCKED_PREREQUISITE global/skills/bad/SKILL.md:",
            diagnostic,
        )
        self.assertNotIn("total_normalized_characters", diagnostic)
        self.assertNotIn('"candidates"', diagnostic)

    def test_every_blocked_fixture_class_emits_no_inventory(self):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            if not case["blocked"]:
                continue
            with self.subTest(case=case["id"]):
                git = GitFixture()
                try:
                    git.write(
                        "global/skills/bad/SKILL.md",
                        base64.b64decode(
                            case["raw_base64"], validate=True
                        ),
                    )
                    git.commit()
                    result = self.run_cli(git.root)
                    self.assertEqual(result.returncode, 3)
                    self.assertEqual(result.stdout, b"")
                    self.assertIn(
                        b"BLOCKED_PREREQUISITE "
                        b"global/skills/bad/SKILL.md:",
                        result.stderr,
                    )
                    self.assertNotIn(
                        b"total_normalized_characters", result.stderr
                    )
                finally:
                    git.close()

    def test_duplicate_fixture_pair_emits_no_inventory(self):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        by_id = {case["id"]: case for case in fixture["cases"]}
        left_id, right_id = fixture["duplicate_case_ids"]
        git = GitFixture()
        self.addCleanup(git.close)
        for name, case_id, scope in (
            ("left", left_id, "global"),
            ("right", right_id, "local"),
        ):
            raw = base64.b64decode(
                by_id[case_id]["raw_base64"], validate=True
            )
            parsed = inventory.parse_frontmatter(raw, case_id)
            git.write(
                f"{scope}/skills/{name}/SKILL.md",
                skill_bytes(
                    name,
                    json.dumps(parsed["description"], ensure_ascii=True),
                ),
            )
        git.commit()
        result = self.run_cli(git.root)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"duplicates another candidate", result.stderr)

    def test_invalid_cli_invocation_uses_exit_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--unknown"],
            check=False,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")


class TestBootstrapProjection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.candidate = self.root / "candidate"
        self.home = self.root / "home"
        self.old = self.root / "old" / "update-skills"
        self.candidate.mkdir()
        self.home.mkdir()
        self.old.mkdir(parents=True)
        shutil.copy2(REPO / "bootstrap.sh", self.candidate / "bootstrap.sh")
        (self.candidate / "scripts").mkdir()
        shutil.copy2(
            REPO / "scripts/capability_meta.py",
            self.candidate / "scripts" / "capability_meta.py",
        )
        (self.candidate / "global").mkdir()
        target = self.candidate / "local" / "skills" / "update-skills"
        target.parent.mkdir(parents=True)
        shutil.copytree(REPO / "local" / "skills" / "update-skills", target)
        subprocess.run(["git", "init", "-q", str(self.candidate)], check=True)
        (self.old / "SKILL.md").write_bytes(
            skill_bytes("update-skills", "old malformed source")
        )
        self.target = target

    def tearDown(self):
        self.temp.cleanup()

    def run_bootstrap(self, mode: str):
        return subprocess.run(
            ["bash", str(self.candidate / "bootstrap.sh"), mode],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home)},
        )

    def link(self, tool: str) -> Path:
        return self.home / f".{tool}" / "skills" / "update-skills"

    def assert_candidate_links(self):
        for tool in ("cursor", "claude"):
            link = self.link(tool)
            self.assertTrue(link.is_symlink())
            self.assertEqual(
                Path(os.readlink(link)), self.target.resolve()
            )
            self.assertEqual(
                (link / "SKILL.md").read_bytes(),
                (self.target / "SKILL.md").read_bytes(),
            )
        self.assertFalse(self.link("codex").exists())

    def home_state(self):
        state = []
        for path in sorted(self.home.glob("**/*")):
            relative = path.relative_to(self.home).as_posix()
            if path.is_symlink():
                state.append((relative, "link", os.readlink(path)))
            elif path.is_file():
                state.append(
                    (
                        relative,
                        "file",
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
            else:
                state.append((relative, "dir", ""))
        return state

    def test_clean_install_and_second_reconcile_are_idempotent(self):
        first = self.run_bootstrap("--reconcile")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assert_candidate_links()
        before = self.home_state()
        second = self.run_bootstrap("--reconcile")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.home_state(), before)
        self.assert_candidate_links()

    def test_upgrade_repair_and_rollback_preserve_exact_source(self):
        for tool in ("cursor", "claude"):
            link = self.link(tool)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(self.old)
        upgraded = self.run_bootstrap("--reconcile")
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assert_candidate_links()

        self.link("cursor").unlink()
        self.link("cursor").symlink_to(self.old)
        self.link("claude").unlink()
        repaired = self.run_bootstrap("--repair")
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assert_candidate_links()

        for tool in ("cursor", "claude"):
            link = self.link(tool)
            link.unlink()
            link.symlink_to(self.old)
            self.assertEqual(Path(os.readlink(link)), self.old)


if __name__ == "__main__":
    unittest.main()
