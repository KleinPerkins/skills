#!/usr/bin/env python3
"""Contract tests for the shared subagent model-tier catalog checker.

Every assertion about specific names uses synthetic fixtures. The real
model-tiers.json is only checked for structure and against its own candidates,
so refreshing the catalog from the live list never requires a test edit.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_model_tiers", ROOT / "verify_model_tiers.py"
)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

TIERS = ("deep", "critical", "standard", "economy")


def fixture_catalog() -> dict:
    return {
        "schema": "cursor-model-tiers/v2",
        "verified_against": "cursor-subagent-model-enum/2026-01-01",
        "tiers": {
            "deep": {"candidates": ["alpha-big-9-max", "alpha-big-9-high", "beta-pro-2-max"]},
            "critical": {"candidates": ["beta-pro-2-max", "alpha-big-9-max"]},
            "standard": {"candidates": ["alpha-mid-9-high", "beta-pro-2-max"]},
            "economy": {"candidates": ["gamma-1.5-fast", "alpha-mid-9-high"]},
        },
    }


def run_main(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = checker.main(list(argv))
    return code, out.getvalue()


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = checker.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def kinds(plan: dict) -> list[str]:
    return [warning["kind"] for warning in plan["warnings"]]


ALL_LIVE = sorted(
    {name for spec in fixture_catalog()["tiers"].values() for name in spec["candidates"]}
)


class StructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = fixture_catalog()

    def assert_invalid(self, catalog: dict, pattern: str) -> None:
        with self.assertRaisesRegex(checker.CatalogError, pattern):
            checker.validate_catalog(catalog)

    def test_fixture_is_valid(self) -> None:
        checked = checker.validate_catalog(self.catalog)
        self.assertEqual(set(checked["tiers"]), set(TIERS))

    def test_real_catalog_is_structurally_valid(self) -> None:
        checked = checker.validate_catalog(
            checker.load_catalog(ROOT / "model-tiers.json")
        )
        self.assertEqual(set(checked["tiers"]), set(TIERS))

    def test_exactly_four_tiers(self) -> None:
        missing = copy.deepcopy(self.catalog)
        del missing["tiers"]["economy"]
        self.assert_invalid(missing, "exactly")
        extra = copy.deepcopy(self.catalog)
        extra["tiers"]["bonus"] = {"candidates": ["alpha-x-1", "beta-x-1"]}
        self.assert_invalid(extra, "exactly")

    def test_closed_keys(self) -> None:
        root = copy.deepcopy(self.catalog)
        root["extra"] = 1
        self.assert_invalid(root, "unknown keys")
        tier = copy.deepcopy(self.catalog)
        tier["tiers"]["deep"]["effort"] = "deep"
        self.assert_invalid(tier, "unknown keys")

    def test_schema_is_required(self) -> None:
        broken = copy.deepcopy(self.catalog)
        broken["schema"] = "cursor-model-tiers/v1"
        self.assert_invalid(broken, "schema")

    def test_candidates_must_be_non_empty_list(self) -> None:
        for bad in ([], "alpha-big-9-max", None):
            with self.subTest(bad=bad):
                broken = copy.deepcopy(self.catalog)
                broken["tiers"]["deep"]["candidates"] = bad
                self.assert_invalid(broken, "non-empty list")

    def test_duplicates_are_rejected(self) -> None:
        broken = copy.deepcopy(self.catalog)
        broken["tiers"]["critical"]["candidates"].append("beta-pro-2-max")
        self.assert_invalid(broken, "duplicate")

    def test_malformed_names_are_rejected(self) -> None:
        for bad in ("inherit", "Alpha-big-9", "alpha big-9", "alpha-", "-alpha", "", 7):
            with self.subTest(bad=bad):
                broken = copy.deepcopy(self.catalog)
                broken["tiers"]["standard"]["candidates"][0] = bad
                self.assert_invalid(broken, "malformed")

    def test_every_tier_needs_two_providers(self) -> None:
        broken = copy.deepcopy(self.catalog)
        broken["tiers"]["deep"]["candidates"] = ["alpha-big-9-max", "alpha-big-9-high"]
        self.assert_invalid(broken, "two providers")

    def test_verified_against_is_informational_with_no_age_limit(self) -> None:
        ancient = copy.deepcopy(self.catalog)
        ancient["verified_against"] = "cursor-subagent-model-enum/2000-01-01"
        checker.validate_catalog(ancient)
        for bad in ("2026-01-01", "cursor-subagent-model-enum/not-a-date", 5):
            with self.subTest(bad=bad):
                broken = copy.deepcopy(self.catalog)
                broken["verified_against"] = bad
                self.assert_invalid(broken, "verified_against")

    def test_real_catalog_accepts_any_well_formed_replacement(self) -> None:
        catalog = checker.load_catalog(ROOT / "model-tiers.json")
        for tier in TIERS:
            with self.subTest(tier=tier):
                swapped = copy.deepcopy(catalog)
                candidates = swapped["tiers"][tier]["candidates"]
                candidates.append(candidates[0])
                candidates[0] = "zeta-renamed-1-high"
                checker.validate_catalog(swapped)


class ResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = checker.validate_catalog(fixture_catalog())

    def test_first_listed_candidate_wins(self) -> None:
        live = {"alpha-big-9-max", "beta-pro-2-max", "alpha-mid-9-high", "gamma-1.5-fast"}
        routes = checker.resolve_tiers(self.catalog, live)
        self.assertEqual(routes["deep"]["model"], "alpha-big-9-max")
        self.assertEqual(routes["critical"]["model"], "beta-pro-2-max")
        self.assertFalse(any(route["fallback"] for route in routes.values()))

    def test_same_family_at_another_level_is_not_a_fallback(self) -> None:
        live = {"alpha-big-9-high", "beta-pro-2-max", "alpha-mid-9-high", "gamma-1.5-fast"}
        route = checker.resolve_tiers(self.catalog, live)["deep"]
        self.assertEqual(route["model"], "alpha-big-9-high")
        self.assertFalse(route["fallback"])

    def test_different_family_is_a_fallback(self) -> None:
        live = {"beta-pro-2-max", "alpha-mid-9-high", "gamma-1.5-fast"}
        route = checker.resolve_tiers(self.catalog, live)["deep"]
        self.assertEqual(route["model"], "beta-pro-2-max")
        self.assertTrue(route["fallback"])

    def test_no_match_resolves_to_nothing_and_is_a_fallback(self) -> None:
        live = {"beta-pro-2-max", "alpha-mid-9-high"}
        route = checker.resolve_tiers(self.catalog, live)["economy"]
        self.assertEqual(route["model"], "alpha-mid-9-high")
        route = checker.resolve_tiers(self.catalog, {"gamma-1.5-fast"})["critical"]
        self.assertIsNone(route["model"])
        self.assertTrue(route["fallback"])

    def test_runtime_list_validation(self) -> None:
        for bad in ([], "alpha-big-9-max", ["inherit"], [""], [3]):
            with self.subTest(bad=bad):
                with self.assertRaises(checker.CatalogError):
                    checker.parse_runtime_models(bad)


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "model-tiers.json"
        self.path.write_text(json.dumps(fixture_catalog()), encoding="utf-8")

    def test_no_arguments_validates_the_real_catalog(self) -> None:
        code, out = run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("model-tier-catalog: OK", out)

    def test_bad_catalog_fails(self) -> None:
        broken = fixture_catalog()
        del broken["tiers"]["deep"]
        self.path.write_text(json.dumps(broken), encoding="utf-8")
        code, out = run_main("--catalog", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_runtime_models_prints_each_tier(self) -> None:
        live = json.dumps(["alpha-big-9-max", "beta-pro-2-max", "alpha-mid-9-high", "gamma-1.5-fast"])
        code, out = run_main("--catalog", str(self.path), "--runtime-models", live)
        self.assertEqual(code, 0, out)
        for tier, model in (
            ("deep", "alpha-big-9-max"),
            ("critical", "beta-pro-2-max"),
            ("standard", "alpha-mid-9-high"),
            ("economy", "gamma-1.5-fast"),
        ):
            self.assertIn(f"{tier}: {model}", out)
        self.assertNotIn("WARN", out)

    def test_runtime_models_from_file(self) -> None:
        live = Path(self.tmp.name) / "live.json"
        live.write_text(json.dumps(["beta-pro-2-max", "gamma-1.5-fast"]), encoding="utf-8")
        code, out = run_main("--catalog", str(self.path), "--runtime-models", f"@{live}")
        self.assertEqual(code, 0, out)

    def test_fallback_warns_but_passes(self) -> None:
        live = json.dumps(["beta-pro-2-max", "gamma-1.5-fast"])
        code, out = run_main("--catalog", str(self.path), "--runtime-models", live)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN", out)
        self.assertIn("deep", out)
        self.assertIn("model-tiers.json", out)

    def test_tier_with_no_match_fails(self) -> None:
        live = json.dumps(["gamma-1.5-fast"])
        code, out = run_main("--catalog", str(self.path), "--runtime-models", live)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL", out)
        self.assertIn("critical", out)

    def test_real_catalog_resolves_against_its_own_first_candidates(self) -> None:
        catalog = checker.load_catalog(ROOT / "model-tiers.json")
        firsts = sorted({spec["candidates"][0] for spec in catalog["tiers"].values()})
        code, out = run_main("--runtime-models", json.dumps(firsts))
        self.assertEqual(code, 0, out)
        self.assertNotIn("WARN", out)


class NeverWeakerTests(unittest.TestCase):
    def test_backup_from_a_weaker_tier_fails(self) -> None:
        for tier, candidates in (
            ("critical", ["beta-pro-2-max", "gamma-1.5-fast"]),
            ("deep", ["alpha-big-9-max", "alpha-mid-9-high", "beta-pro-2-max"]),
        ):
            with self.subTest(tier=tier):
                broken = fixture_catalog()
                broken["tiers"][tier]["candidates"] = candidates
                with self.assertRaisesRegex(checker.CatalogError, "weaker"):
                    checker.validate_catalog(broken)

    def test_own_levels_and_equal_or_stronger_backups_pass(self) -> None:
        catalog = fixture_catalog()
        catalog["tiers"]["deep"]["candidates"].insert(2, "alpha-big-9-low")
        catalog["tiers"]["economy"]["candidates"].append("beta-pro-2-max")
        checker.validate_catalog(catalog)
        checker.validate_catalog(checker.load_catalog(ROOT / "model-tiers.json"))

    def test_family_that_leads_no_tier_is_not_ranked(self) -> None:
        catalog = fixture_catalog()
        catalog["tiers"]["critical"]["candidates"].append("delta-new-1-high")
        checker.validate_catalog(catalog)


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = checker.validate_catalog(fixture_catalog())

    def plan(self, kind: str, live=ALL_LIVE, **options) -> dict:
        return checker.plan_launch(self.catalog, live, kind, **options)

    def test_work_kinds_map_to_tiers(self) -> None:
        expected = {
            "find": "economy", "run": "economy", "build": "standard",
            "review": "standard", "design": "deep", "sign-off": "critical",
        }
        self.assertEqual({k: v[0] for k, v in checker.WORK_KINDS.items()}, expected)
        for kind, tier in expected.items():
            with self.subTest(kind=kind):
                plan = self.plan(kind, author_provider="none")
                self.assertEqual((plan["work_kind"], plan["tier"]), (kind, tier))
                self.assertEqual(plan["warnings"], [])

    def test_tier_only_rises_to_a_stronger_class_with_a_reason(self) -> None:
        for kind, tier in (
            ("design", "standard"), ("design", "critical"), ("sign-off", "deep"),
            ("build", "standard"), ("find", "economy"), ("review", "economy"),
        ):
            with self.subTest(kind=kind, tier=tier):
                with self.assertRaisesRegex(checker.PlanError, "only be raised"):
                    self.plan(kind, tier=tier, raise_reason="why", author_provider="none")
        for options in ({"tier": "deep"}, {"tier": "deep", "raise_reason": "  "}):
            with self.assertRaisesRegex(checker.PlanError, "needs --raise-reason"):
                self.plan("build", **options)
        with self.assertRaisesRegex(checker.PlanError, "needs --tier"):
            self.plan("build", raise_reason="why")
        plan = self.plan("find", tier="critical", raise_reason="decides the merge")
        self.assertEqual((plan["tier"], kinds(plan)), ("critical", ["raised"]))
        self.assertIn("decides the merge", plan["warnings"][0]["message"])

    def test_secondary_is_another_provider_never_another_level(self) -> None:
        plan = self.plan("design")
        self.assertEqual((plan["primary"], plan["secondary"]), ("alpha-big-9-max", "beta-pro-2-max"))
        plan = self.plan("design", live=["alpha-big-9-max", "alpha-big-9-high"])
        self.assertEqual((plan["primary"], plan["secondary"]), ("alpha-big-9-max", None))

    def test_attempt_order_with_and_without_a_secondary(self) -> None:
        def launch(role: str, model: str) -> dict:
            return {"action": "launch", "role": role, "model": model}

        wait, fatal = {"action": "wait", "seconds": 60}, {"action": "fatal"}
        both = [launch("primary", "alpha-big-9-max"), launch("secondary", "beta-pro-2-max")]
        self.assertEqual(self.plan("design")["attempts"], both + [wait] + both + [fatal])
        alone = [launch("primary", "alpha-big-9-max")]
        self.assertEqual(
            self.plan("design", live=["alpha-big-9-max"])["attempts"],
            alone + [wait] + alone + [fatal],
        )

    def test_nothing_offered_launches_nothing(self) -> None:
        with self.assertRaisesRegex(checker.PlanError, "launch nothing"):
            self.plan("find", live=["beta-pro-2-max", "alpha-big-9-max"])

    def test_step_down_and_fallback_warnings(self) -> None:
        plan = self.plan("design", live=["alpha-big-9-high", "beta-pro-2-max"])
        self.assertEqual((plan["primary"], kinds(plan)), ("alpha-big-9-high", ["step-down"]))
        self.assertIn("alpha-big-9-max", plan["warnings"][0]["message"])
        plan = self.plan("design", live=["beta-pro-2-max"])
        self.assertEqual((plan["primary"], plan["secondary"]), ("beta-pro-2-max", None))
        self.assertEqual(kinds(plan), ["fallback"])
        catalog = fixture_catalog()
        catalog["tiers"]["critical"]["candidates"].append("alpha-big-9-high")
        plan = checker.plan_launch(
            checker.validate_catalog(catalog), ["beta-pro-2-max", "alpha-big-9-high"],
            "sign-off", author_provider="none",
        )
        self.assertEqual((plan["secondary"], kinds(plan)), ("alpha-big-9-high", ["step-down"]))

    def test_review_prefers_a_provider_other_than_the_authors(self) -> None:
        plan = self.plan("review", author_provider="alpha")
        self.assertEqual((plan["primary"], plan["secondary"]), ("beta-pro-2-max", "alpha-mid-9-high"))
        self.assertEqual(kinds(plan), ["not-independent"])
        self.assertIn("alpha-mid-9-high", plan["warnings"][0]["message"])
        plan = self.plan("sign-off", author_provider="beta")
        self.assertEqual((plan["primary"], plan["secondary"]), ("alpha-big-9-max", "beta-pro-2-max"))
        self.assertEqual(kinds(plan), ["not-independent"])
        plan = self.plan("review", author_provider="none")
        self.assertEqual((plan["primary"], plan["warnings"]), ("alpha-mid-9-high", []))

    def test_only_the_authors_provider_offered(self) -> None:
        plan = self.plan("review", live=["beta-pro-2-max"], author_provider="beta")
        self.assertEqual((plan["primary"], plan["secondary"]), ("beta-pro-2-max", None))
        self.assertEqual(kinds(plan), ["fallback", "not-independent"])

    def test_author_provider_required_for_review_and_sign_off_only(self) -> None:
        for kind in ("review", "sign-off"):
            for bad in (None, "", "Alpha", "alpha-big"):
                with self.subTest(kind=kind, bad=bad):
                    with self.assertRaisesRegex(checker.PlanError, "--author-provider"):
                        self.plan(kind, author_provider=bad)
        for kind in ("find", "run", "build", "design"):
            with self.subTest(kind=kind):
                self.assertEqual(self.plan(kind, author_provider="alpha"), self.plan(kind))

    def test_pinned_type_names_its_limits_and_keeps_the_general_purpose_plan(self) -> None:
        plain = self.plan("review", author_provider="alpha")
        pinned = self.plan("review", author_provider="alpha", subagent_type="bugbot")
        self.assertEqual({**pinned, "pinned": None}, plain)
        self.assertEqual(pinned["pinned"]["subagent_type"], "bugbot")
        for phrase in ("Cursor chooses", "ignores --model", "different-provider", "generalPurpose"):
            self.assertIn(phrase, pinned["pinned"]["note"])
        self.assertEqual(
            self.plan("review", author_provider="alpha", subagent_type="explore"), plain
        )


class PlanCommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "model-tiers.json"
        self.path.write_text(json.dumps(fixture_catalog()), encoding="utf-8")

    def plan(self, *argv: str, live=ALL_LIVE) -> tuple[int, str, str]:
        return run_cli(
            "plan", "--catalog", str(self.path), "--runtime-models", json.dumps(live), *argv
        )

    def test_human_output(self) -> None:
        code, out, err = self.plan(
            "--work-kind", "design", live=["alpha-big-9-high", "beta-pro-2-max"]
        )
        self.assertEqual((code, err), (0, ""))
        for text in (
            "primary: alpha-big-9-high", "secondary: beta-pro-2-max", "is a fallback; report it",
            "3. wait 60 seconds", "6. FATAL", "WARN  step-down: alpha-big-9-high",
        ):
            self.assertIn(text, out)

    def test_json_shape_keeps_stdout_pure_and_warnings_on_stderr(self) -> None:
        code, out, err = self.plan(
            "--work-kind", "design", "--json", live=["alpha-big-9-high", "beta-pro-2-max"]
        )
        self.assertEqual(code, 0, err)
        plan = json.loads(out)
        self.assertEqual(
            list(plan),
            ["tier", "work_kind", "primary", "secondary", "attempts", "warnings", "pinned"],
        )
        self.assertEqual(
            [step["action"] for step in plan["attempts"]],
            ["launch", "launch", "wait", "launch", "launch", "fatal"],
        )
        self.assertEqual((kinds(plan), plan["pinned"]), (["step-down"], None))
        self.assertIn("WARN  step-down", err)

    def test_pinned_output(self) -> None:
        argv = ("--work-kind", "review", "--author-provider", "alpha", "--subagent-type", "bugbot")
        code, out, _ = self.plan(*argv)
        self.assertEqual(code, 0, out)
        for text in ("pinned: Cursor chooses bugbot", "generalPurpose", "primary: beta-pro-2-max"):
            self.assertIn(text, out)
        code, out, _ = self.plan(*argv, "--json")
        self.assertEqual(json.loads(out)["pinned"]["subagent_type"], "bugbot")

    def test_refusals_exit_non_zero_and_name_no_model(self) -> None:
        for argv, live in (
            (("--work-kind", "find"), ["beta-pro-2-max"]),
            (("--work-kind", "review"), ALL_LIVE),
            (("--work-kind", "design", "--tier", "standard", "--raise-reason", "x"), ALL_LIVE),
            (("--work-kind", "build", "--tier", "deep"), ALL_LIVE),
        ):
            with self.subTest(argv=argv):
                code, out, _ = self.plan(*argv, live=live)
                self.assertEqual(code, 1, out)
                self.assertIn("model-tier-plan: FAIL", out)
                self.assertNotIn("primary", out)
        code, out, err = self.plan("--work-kind", "find", "--json", live=["beta-pro-2-max"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("launch nothing", err)

    def test_usage_errors_exit_two(self) -> None:
        live = json.dumps(["alpha-big-9-max"])
        for argv in (
            ("plan", "--work-kind", "nap", "--runtime-models", live),
            ("plan", "--work-kind", "find"),
            ("plan", "--runtime-models", live),
        ):
            with self.subTest(argv=argv):
                code, _, err = run_cli(*argv)
                self.assertEqual(code, 2)
                self.assertIn("usage", err)

    def test_real_catalog_plans_every_work_kind(self) -> None:
        catalog = checker.load_catalog(ROOT / "model-tiers.json")
        live = json.dumps(sorted({m for s in catalog["tiers"].values() for m in s["candidates"]}))
        for kind, (tier, _) in checker.WORK_KINDS.items():
            with self.subTest(kind=kind):
                code, out, err = run_cli(
                    "plan", "--work-kind", kind, "--author-provider", "none",
                    "--runtime-models", live, "--json",
                )
                self.assertEqual(code, 0, err)
                plan = json.loads(out)
                self.assertEqual(plan["primary"], catalog["tiers"][tier]["candidates"][0])
                self.assertNotIn("fallback", kinds(plan))


class UnchangedLegacyOutputTests(unittest.TestCase):
    def test_no_arguments_output_is_unchanged(self) -> None:
        catalog = checker.load_catalog(ROOT / "model-tiers.json")
        slots = sum(len(spec["candidates"]) for spec in catalog["tiers"].values())
        checked_on = catalog["verified_against"].split("/", 1)[1]
        code, out, err = run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            out,
            f"model-tier-catalog: OK (4 tiers, {slots} candidate slots; "
            f"last checked against the live list {checked_on})\n",
        )

    def test_runtime_models_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-tiers.json"
            path.write_text(json.dumps(fixture_catalog()), encoding="utf-8")
            live = json.dumps(["beta-pro-2-max", "gamma-1.5-fast"])
            code, out, _ = run_cli("--catalog", str(path), "--runtime-models", live)
        self.assertEqual(code, 0)
        advice = "report it and update model-tiers.json from the live list"
        self.assertEqual(out.splitlines(), [
            "model-tier-catalog: OK (4 tiers, 9 candidate slots; "
            "last checked against the live list 2026-01-01)",
            "  deep: beta-pro-2-max",
            f"WARN  deep: fallback from alpha-big-9-max to beta-pro-2-max; {advice}",
            "  critical: beta-pro-2-max",
            "  standard: beta-pro-2-max",
            f"WARN  standard: fallback from alpha-mid-9-high to beta-pro-2-max; {advice}",
            "  economy: gamma-1.5-fast",
        ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
