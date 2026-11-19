#!/usr/bin/env python3
"""Lean behavioral suite for the proportional /swarm helper API.

Replaces the retired test_contract.py + test_acceptance.py. Exercises the real
public surface of scripts/swarm_helper.py (and the swarm_cli.py facade): band
selection at every boundary, the dispatch budget ceilings, concrete-slug routing
with no inheritance, finding/reviewer-return validation and caps, curated
rendering, and a capstone runaway-regression guard proving a default run cannot
become the ~20-agent, multi-hour spend the redesign removed.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import swarm_helper as helper  # noqa: E402
import swarm_cli  # noqa: E402


MODEL_CATALOG, OBLIGATION = helper._load_model_catalog()
ALL_SLUGS = {slug for slugs in MODEL_CATALOG.values() for slug in slugs}
RUNTIME_MODELS = frozenset(ALL_SLUGS)
RUNTIME_MODELS_JSON = json.dumps(sorted(RUNTIME_MODELS))
ACCOUNTING_SLUG = MODEL_CATALOG["critical"][0]
NON_CATALOG_SLUG = "fixture-not-in-catalog-1-high"
assert NON_CATALOG_SLUG not in ALL_SLUGS
TEST_CANDIDATE_ID = helper.build_candidate_identity(
    "test-revision",
    [
        {
            "path": "fixture.py",
            "sha256": hashlib.sha256(b"fixture").hexdigest(),
            "bytes": 7,
            "lines": 10,
        }
    ],
)["candidate_id"]


def make_probe(
    scores: dict | None = None,
    *,
    roots: int = 1,
    files: int = 1,
    lines: int = 10,
    impacted: list | None = None,
    territories: list | None = None,
    fix_character: str = "mixed",
    protected: dict | None = None,
    recommended_band: str | None = None,
    candidate_files: list[dict] | None = None,
    sections: list[dict] | None = None,
    integration_points: list[dict] | None = None,
    depth: str = "shallow",
) -> dict:
    """Build a schema-valid probe (all 16 dims present) with targeted overrides."""
    values = {dim: 5 for dim in helper.DIMENSIONS}
    if scores:
        values.update(scores)
    if candidate_files is None:
        remaining = max(lines, files)
        candidate_files = []
        for index in range(files):
            file_lines = remaining // (files - index)
            remaining -= file_lines
            path = f"file-{index + 1}.py"
            marker = f"{path}:{file_lines}".encode()
            candidate_files.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(marker).hexdigest(),
                    "bytes": len(marker),
                    "lines": file_lines,
                }
            )
    candidate = helper.build_candidate_identity("test-revision", candidate_files)
    surface: dict = {
        "roots": roots,
        "files_changed": files,
        "lines_changed": lines,
        "impacted_surfaces": impacted or [],
        "flows": [],
    }
    if sections is not None:
        surface["sections"] = sections
    if integration_points is not None:
        surface["integration_points"] = integration_points
    probe: dict = {
        "candidate": candidate,
        "scores": {
            dim: {"score": values[dim], "confidence": 80, "hotspot": False}
            for dim in helper.DIMENSIONS
        },
        "surface": surface,
        "complexity": {
            "size_band": "large" if lines > 2000 else "small",
            "depth": depth,
            "novelty": "familiar",
        },
        "fix_character": fix_character,
    }
    if territories is not None:
        probe["territories"] = territories
    if protected is not None:
        probe["protected_axes"] = protected
    if recommended_band is not None:
        probe["recommended_band"] = recommended_band
    return probe


def good_finding(**overrides) -> dict:
    finding = {
        "finding_id": "authz-missing-owner-check",
        "focus_area": "security",
        "dimension": "D04",
        "root_cause": "missing owner check",
        "evidence": [{"ref": "auth.py:42", "lineage": "source-confirmed"}],
        "impact": {"priority": "P1", "risk_score": 75, "confidence": 82},
        "correction": "add the owner assertion",
        "status": "open",
    }
    finding.update(overrides)
    return finding


class RiskAndPriorityTests(unittest.TestCase):
    def test_weighted_risk_is_deterministic(self) -> None:
        self.assertEqual(helper.calculate_risk(5, 5, 5, 5), 100)
        self.assertEqual(helper.calculate_risk(4, 4, 4, 4), 80)
        self.assertEqual(helper.calculate_risk(1, 1, 1, 1), 20)

    def test_priority_bands(self) -> None:
        self.assertEqual(helper.priority_for(100), "P0")
        self.assertEqual(helper.priority_for(80), "P1")
        self.assertEqual(helper.priority_for(50), "P2")
        self.assertEqual(helper.priority_for(20), "P3")
        self.assertEqual(helper.priority_for(5), "P4")
        self.assertEqual(helper.priority_for(50, unsafe_to_ship=True), "P0")

    def test_risk_factor_bounds(self) -> None:
        with self.assertRaises(helper.ContractError):
            helper.calculate_risk(6, 1, 1, 1)


class BandSelectionTests(unittest.TestCase):
    def _band(self, probe: dict) -> str:
        return helper.select_band(probe)["band"]

    def test_trivial_fast_path(self) -> None:
        probe = make_probe(files=3, lines=50, fix_character="cosmetic")
        plan = helper.size_cohort(probe)
        self.assertEqual(plan["band"], "trivial")
        self.assertEqual(plan["reviewers"], 1)  # floor 1
        self.assertEqual(plan["verifier"], "no")
        self.assertEqual(plan["second_pass"], "no")
        self.assertEqual(plan["max_dispatches"], 2)

    def test_small_by_score_and_by_single_root_fallback(self) -> None:
        by_score = helper.size_cohort(make_probe({"D01": 50}, files=3))
        self.assertEqual(by_score["band"], "small")
        self.assertEqual(by_score["verifier"], "no")
        self.assertIn(by_score["reviewers"], (1, 2))
        fallback = helper.size_cohort(make_probe(files=10, fix_character="mixed"))
        self.assertEqual(fallback["band"], "small")

    def test_standard_by_score_and_by_focus_areas(self) -> None:
        by_score = helper.size_cohort(make_probe({"D01": 70}))
        self.assertEqual(by_score["band"], "standard")
        self.assertEqual(by_score["verifier"], "gated")
        self.assertEqual(by_score["second_pass"], "no")
        self.assertIn(by_score["reviewers"], (2, 3))
        by_focus = helper.size_cohort(
            make_probe(territories=[{"focus_area": "a"}, {"focus_area": "b"}])
        )
        self.assertEqual(by_focus["band"], "standard")

    def test_deep_by_max_score_and_by_protected_axis(self) -> None:
        by_max = helper.size_cohort(make_probe({"D01": 85}))
        self.assertEqual(by_max["band"], "deep")
        self.assertEqual(by_max["verifier"], "gated")
        self.assertEqual(by_max["second_pass"], "gated")
        self.assertIn(by_max["reviewers"], (3, 4))
        by_axis = self._band(make_probe({"D04": 70}))  # protected axis 60-79
        self.assertEqual(by_axis, "deep")

    def test_critical_by_score_and_by_protected_axis(self) -> None:
        by_max = helper.size_cohort(make_probe({"D01": 95}))
        self.assertEqual(by_max["band"], "critical")
        self.assertEqual(by_max["verifier"], "yes")
        self.assertIn(by_max["reviewers"], (4, 5))
        self.assertEqual(self._band(make_probe({"D04": 85})), "critical")
        self.assertEqual(self._band(make_probe({"D07": 90})), "critical")

    def test_floor_one_and_base_max_five(self) -> None:
        # Even a critical band flooded with territories is capped at the base max.
        flooded = make_probe(
            {"D01": 95},
            territories=[{"focus_area": f"t{i}"} for i in range(100)],
        )
        plan = helper.size_cohort(flooded)
        self.assertEqual(plan["band"], "critical")
        self.assertEqual(plan["reviewers"], helper.BASE_MAX_REVIEWERS)
        self.assertLessEqual(plan["reviewers"], helper.BASE_MAX_REVIEWERS)
        # No band ever plans more than the base max.
        for band in helper.BANDS:
            self.assertLessEqual(helper.BAND_SPEC[band]["reviewers"][1], helper.BASE_MAX_REVIEWERS)

    def test_probe_recommendation_is_advice_only(self) -> None:
        # A wrong probe recommendation never overrides the recomputed band.
        plan = helper.size_cohort(make_probe({"D01": 95}, recommended_band="trivial"))
        self.assertEqual(plan["band"], "critical")
        self.assertEqual(plan["probe_recommended_band"], "trivial")
        self.assertFalse(plan["matches_probe_recommendation"])


class BudgetCounterTests(unittest.TestCase):
    def _spread(self, band: str, kinds: list[str]) -> list[dict]:
        counter = helper.BudgetCounter(band)
        snap = counter.snapshot()
        for i, kind in enumerate(kinds):
            snap = counter.record(kind, batch=i)  # unique batch avoids concurrency trips
        return snap

    def test_per_band_base_ceilings(self) -> None:
        ceilings = {"trivial": 2, "small": 3, "standard": 4, "deep": 6, "critical": 8}
        for band, ceiling in ceilings.items():
            self.assertEqual(helper.BAND_SPEC[band]["max_dispatches"], ceiling)
            # Fill exactly to the ceiling with base kinds, then overflow by one.
            base = ["probe"] + ["reviewer"] * (ceiling - 1)
            self._spread(band, base)  # ok
            with self.assertRaises(helper.ContractError):
                self._spread(band, base + ["reviewer"])

    def test_absolute_ceiling_of_nine(self) -> None:
        nine = ["probe"] + ["reviewer"] * 6 + ["verifier", "escalation"]
        snap = helper.evaluate_budget(
            "critical", [{"kind": k, "batch": i // 3} for i, k in enumerate(nine)]
        )
        self.assertEqual(snap["dispatches"], 9)
        self.assertEqual(snap["base_dispatches"], 8)
        ten = nine + ["escalation"]
        with self.assertRaisesRegex(helper.ContractError, "absolute ceiling"):
            helper.evaluate_budget(
                "critical", [{"kind": k, "batch": i // 3} for i, k in enumerate(ten)]
            )

    def test_per_batch_concurrency(self) -> None:
        counter = helper.BudgetCounter("standard")  # concurrency 2
        counter.record("probe", batch=0)
        counter.record("reviewer", batch=0)
        with self.assertRaisesRegex(helper.ContractError, "concurrency"):
            counter.record("reviewer", batch=0)

    def test_singleton_probe_verifier_and_bounded_charter_retry(self) -> None:
        with self.assertRaisesRegex(helper.ContractError, "more than one accepted probe"):
            self._spread("critical", ["probe", "probe"])
        with self.assertRaisesRegex(helper.ContractError, "more than one accepted verifier"):
            self._spread("critical", ["verifier", "verifier"])
        counter = helper.BudgetCounter("critical")
        counter.record("reviewer", attempt_index=1)
        with self.assertRaises(helper.ContractError):
            counter.record("reviewer", batch=1, attempt_index=2)

    def test_no_third_pass(self) -> None:
        counter = helper.BudgetCounter("deep")
        counter.record("probe", pass_index=1)
        counter.record("reviewer", pass_index=2)
        with self.assertRaisesRegex(helper.ContractError, "third pass"):
            counter.record("reviewer", batch=2, pass_index=3)

    def test_start_cutoff_is_separate_from_completion_allowance(self) -> None:
        counter = helper.BudgetCounter("standard")
        with self.assertRaisesRegex(helper.ContractError, "no new accepted worker"):
            counter.record("reviewer", at_seconds=helper.NO_NEW_DISPATCH_SECONDS + 1)
        small = helper.execution_window(
            band="small", lines_changed=100, territory_count=1, depth="shallow"
        )
        large = helper.execution_window(
            band="critical",
            lines_changed=9396,
            territory_count=4,
            depth="deep",
        )
        self.assertEqual(
            small["start_new_work_cutoff_seconds"],
            large["start_new_work_cutoff_seconds"],
        )
        self.assertGreater(
            large["healthy_completion_allowance_seconds"],
            small["healthy_completion_allowance_seconds"],
        )

    def test_evidence_kind_is_rejected(self) -> None:
        counter = helper.BudgetCounter("trivial")
        with self.assertRaisesRegex(helper.ContractError, "accepted workers"):
            counter.record("evidence")


class RunAccountingTests(unittest.TestCase):
    def _window(self) -> dict:
        return helper.execution_window(
            band="critical",
            lines_changed=9396,
            territory_count=4,
            depth="deep",
        )

    def test_preflight_rejection_does_not_consume_worker_capacity(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        before = accounting.snapshot()["budget"]["remaining_band"]
        snapshot = accounting.record_preflight_rejection(
            "security-review", "stale-model", "not in runtime enum"
        )
        self.assertEqual(snapshot["accepted_workers"], 0)
        self.assertEqual(snapshot["budget"]["remaining_band"], before)
        self.assertIn("security-review", snapshot["routing_rejections"])

    def test_routing_and_transport_fallback_attempts_are_separately_bounded(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        accounting.record_preflight_rejection(
            "security-review", "stale-model", "not supported"
        )
        accounting.record_transport_rejection(
            "security-review", "runtime-model", "transport unavailable"
        )
        with self.assertRaisesRegex(helper.ContractError, "preflight model resolution"):
            accounting.record_preflight_rejection(
                "security-review", "other-model", "still not supported"
            )
        with self.assertRaisesRegex(helper.ContractError, "transport"):
            accounting.record_transport_rejection(
                "security-review", "fallback-model", "transport unavailable"
            )

    def test_accepted_worker_is_counted_once(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        kwargs = {
            "worker_id": "worker-one",
            "kind": "reviewer",
            "assignment_id": "security-review",
            "territory_id": "security",
            "model_slug": ACCOUNTING_SLUG,
        }
        accounting.accept_worker(**kwargs)
        snapshot = accounting.accept_worker(**kwargs)
        self.assertEqual(snapshot["accepted_workers"], 1)
        self.assertEqual(snapshot["budget"]["dispatches"], 1)
        accounting.complete_worker(
            "worker-one", outcome="valid", completed_at_seconds=600
        )
        snapshot = accounting.accept_worker(**kwargs)
        self.assertEqual(snapshot["accepted_workers"], 1)

    def test_assignment_allows_base_launch_and_one_retry(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        for attempt_index in (0, 1):
            snapshot = accounting.accept_worker(
                worker_id=f"worker-{attempt_index}",
                kind="reviewer",
                assignment_id="security-review",
                territory_id="security",
                model_slug=ACCOUNTING_SLUG,
                batch=attempt_index,
                attempt_index=attempt_index,
            )
        self.assertEqual(snapshot["accepted_workers"], 2)
        self.assertEqual(snapshot["budget"]["dispatches"], 2)

    def test_assignment_refuses_third_accepted_launch_before_counting(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        for attempt_index in (0, 1):
            accounting.accept_worker(
                worker_id=f"worker-{attempt_index}",
                kind="reviewer",
                assignment_id="security-review",
                territory_id="security",
                model_slug=ACCOUNTING_SLUG,
                batch=attempt_index,
                attempt_index=attempt_index,
            )
        before = accounting.snapshot()
        with self.assertRaisesRegex(
            helper.ContractError,
            "base launch plus at most 1 retry allowed",
        ):
            accounting.accept_worker(
                worker_id="worker-third",
                kind="reviewer",
                assignment_id="security-review",
                territory_id="security",
                model_slug=ACCOUNTING_SLUG,
                batch=2,
                attempt_index=1,
            )
        after = accounting.snapshot()
        self.assertEqual(after["accepted_workers"], before["accepted_workers"])
        self.assertEqual(
            after["budget"]["dispatches"], before["budget"]["dispatches"]
        )

    def test_assignment_refuses_non_monotonic_attempt_index(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        with self.assertRaisesRegex(
            helper.ContractError, "expected attempt_index 0"
        ):
            accounting.accept_worker(
                worker_id="worker-retry-without-base",
                kind="reviewer",
                assignment_id="security-review",
                territory_id="security",
                model_slug=ACCOUNTING_SLUG,
                attempt_index=1,
            )
        self.assertEqual(accounting.snapshot()["accepted_workers"], 0)

    def test_malformed_and_stalled_returns_remain_failed_coverage(self) -> None:
        accounting = helper.RunAccounting("critical", self._window())
        for index, outcome in enumerate(
            ("malformed", "stalled", "errored"), start=1
        ):
            worker_id = f"worker-{index}"
            accounting.accept_worker(
                worker_id=worker_id,
                kind="reviewer",
                assignment_id=f"assignment-{index}",
                territory_id=f"territory-{index}",
                model_slug=ACCOUNTING_SLUG,
                batch=index,
            )
            snapshot = accounting.complete_worker(
                worker_id,
                outcome=outcome,
                completed_at_seconds=600,
            )
        self.assertEqual(
            {failure["outcome"] for failure in snapshot["failed_workers"]},
            {"malformed", "stalled", "errored"},
        )
        self.assertEqual(snapshot["completed_assignment_ids"], [])

    def test_healthy_large_review_may_finish_after_small_target(self) -> None:
        window = self._window()
        accounting = helper.RunAccounting("critical", window)
        accounting.accept_worker(
            worker_id="worker-large",
            kind="reviewer",
            assignment_id="large-review",
            territory_id="large-territory",
            model_slug=ACCOUNTING_SLUG,
        )
        completed_at = window["target_wall_clock_seconds"] + 600
        self.assertLess(
            completed_at, window["healthy_completion_allowance_seconds"]
        )
        snapshot = accounting.complete_worker(
            "worker-large",
            outcome="valid",
            completed_at_seconds=completed_at,
        )
        self.assertEqual(snapshot["completed_assignment_ids"], ["large-review"])


class RoutingTests(unittest.TestCase):
    def test_no_catalog_slug_is_inherit(self) -> None:
        self.assertNotIn("inherit", ALL_SLUGS)
        self.assertTrue(ALL_SLUGS)

    def test_probe_routes_off_pre_probe_facts_only(self) -> None:
        trivial = helper.route_probe(
            roots=1,
            files_changed=3,
            lines_changed=50,
            protected_paths=False,
            runtime_models=RUNTIME_MODELS,
        )
        self.assertEqual(trivial["model_class"], "economy")
        heavy = helper.route_probe(
            roots=2,
            files_changed=9,
            lines_changed=400,
            protected_paths=True,
            runtime_models=RUNTIME_MODELS,
        )
        self.assertEqual(heavy["model_class"], "deep")
        default = helper.route_probe(
            roots=1,
            files_changed=80,
            lines_changed=900,
            protected_paths=False,
            runtime_models=RUNTIME_MODELS,
        )
        self.assertEqual(default["model_class"], "standard")
        for route in (trivial, heavy, default):
            self.assertIn(route["slug"], ALL_SLUGS)
            self.assertNotEqual(route["slug"], "inherit")
            self.assertEqual(
                set(route)
                & {
                    "model_class",
                    "slug",
                    "rigor",
                    "fallbacks",
                    "filtered_out",
                },
                {
                    "model_class",
                    "slug",
                    "rigor",
                    "fallbacks",
                    "filtered_out",
                },
            )
        # Probe routing must not accept probe scores (no circular routing).
        with self.assertRaises(TypeError):
            helper.route_probe(
                roots=1,
                files_changed=1,
                lines_changed=1,
                protected_paths=False,
                runtime_models=RUNTIME_MODELS,
                score=95,
            )

    def test_reviewer_and_verifier_routes_scale_with_severity(self) -> None:
        self.assertEqual(
            helper.route_reviewer(
                score=95, runtime_models=RUNTIME_MODELS
            )["model_class"],
            "critical",
        )
        self.assertEqual(
            helper.route_reviewer(
                score=70, runtime_models=RUNTIME_MODELS
            )["model_class"],
            "deep",
        )
        self.assertEqual(
            helper.route_reviewer(
                score=50, runtime_models=RUNTIME_MODELS
            )["model_class"],
            "standard",
        )
        self.assertEqual(
            helper.route_reviewer(
                score=10, runtime_models=RUNTIME_MODELS
            )["model_class"],
            "economy",
        )
        self.assertEqual(
            helper.route_verifier(
                priority="P0", runtime_models=RUNTIME_MODELS
            )["model_class"],
            "critical",
        )
        self.assertEqual(
            helper.route_verifier(
                priority="P1", runtime_models=RUNTIME_MODELS
            )["model_class"],
            "deep",
        )
        with self.assertRaises(helper.ContractError):
            helper.route_verifier(priority="P9", runtime_models=RUNTIME_MODELS)

    def test_resolve_model_dispatch(self) -> None:
        probe = helper.resolve_model(
            "probe",
            roots=1,
            files_changed=1,
            lines_changed=1,
            protected_paths=False,
            runtime_models=RUNTIME_MODELS,
        )
        self.assertIn(probe["slug"], ALL_SLUGS)
        self.assertEqual(
            helper.resolve_model(
                "reviewer", score=95, runtime_models=RUNTIME_MODELS
            )["model_class"],
            "critical",
        )
        self.assertEqual(
            helper.resolve_model(
                "verify", priority="P0", runtime_models=RUNTIME_MODELS
            )["model_class"],
            "critical",
        )
        with self.assertRaises(helper.ContractError):
            helper.resolve_model(
                "bogus", score=1, runtime_models=RUNTIME_MODELS
            )

    def test_select_slug_primary_fallback_and_bounded_stop(self) -> None:
        standard = MODEL_CATALOG["standard"]
        self.assertEqual(helper.select_slug("standard", {standard[1]}), standard[1])
        # Unavailable primary with no listed alternative -> bounded stop (never inherit).
        with self.assertRaises(helper.ContractError):
            helper.select_slug("deep", {NON_CATALOG_SLUG})
        with self.assertRaises(helper.ContractError):
            helper.select_slug("critical", set())

    def test_all_tiers_preserve_primary_then_fallback_order(self) -> None:
        # Derives expected slugs from the live catalog rather than duplicating
        # a hardcoded snapshot here: catalog *structure* is
        # subagent-orchestration's job (tests/test_model_tiers.py) and its
        # *content* follows the live list; this suite only owns the *ordering*
        # invariant that select_slug preserves primary-then-fallback for
        # whatever the shared catalog currently declares.
        for tier, candidates in MODEL_CATALOG.items():
            self.assertEqual(
                helper.select_slug(tier, RUNTIME_MODELS), candidates[0]
            )
            self.assertEqual(helper.select_slug(tier, {candidates[1]}), candidates[1])

    def test_unavailable_preference_resolves_to_valid_configured_fallback(self) -> None:
        catalog = {"critical": ["stale-preference", "fixture-valid-2-max"]}
        obligations = {"critical": "max"}
        with mock.patch.object(
            helper, "_load_model_catalog", return_value=(catalog, obligations)
        ):
            route = helper.resolve_tier(
                "critical", {"fixture-valid-2-max", NON_CATALOG_SLUG}
            )
        self.assertEqual(route["slug"], "fixture-valid-2-max")
        self.assertEqual(route["filtered_out"], ["stale-preference"])
        self.assertEqual(route["fallbacks"], [])

    def test_no_runtime_valid_catalog_model_is_precise_preflight_failure(self) -> None:
        with self.assertRaisesRegex(
            helper.ContractError,
            "preflight model resolution.*zero launches",
        ):
            helper.resolve_tier("critical", {NON_CATALOG_SLUG})


class SharedModelCatalogTests(unittest.TestCase):
    def test_helper_matches_the_shared_catalog(self) -> None:
        raw = json.loads(helper.MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
        expected_models = {
            tier: spec["candidates"] for tier, spec in raw["tiers"].items()
        }
        self.assertEqual(MODEL_CATALOG, expected_models)
        self.assertEqual(OBLIGATION, helper.TIER_RIGOR)

    def test_missing_catalog_breaks_only_routing_verbs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "source" / "model-tiers.json"
            second = Path(tmp) / "installed" / "model-tiers.json"
            with mock.patch.object(helper, "_catalog_paths", return_value=(first, second)):
                self.assertEqual(helper.calculate_risk(4, 4, 4, 4), 80)
                self.assertEqual(
                    helper.size_cohort(
                        make_probe(files=3, lines=50, fix_character="cosmetic")
                    )["band"],
                    "trivial",
                )
                self.assertEqual(
                    helper.validate_finding(good_finding())["finding_id"],
                    "authz-missing-owner-check",
                )
                self.assertEqual(helper.evaluate_budget("trivial", [])["dispatches"], 0)
                self.assertFalse(helper.gate_verifier([])["run"])
                self.assertFalse(helper.gate_second_pass({})["allowed"])
                self.assertIn(
                    "### BLUF",
                    helper.render_report({"band": "trivial", "findings": []}),
                )
                with self.assertRaisesRegex(
                    helper.ContractError,
                    f"{first}.*{second}",
                ):
                    helper.route_reviewer(
                        score=50, runtime_models=RUNTIME_MODELS
                    )

    def test_deep_tier_routes_to_shared_primary(self) -> None:
        deep = MODEL_CATALOG["deep"][0]
        self.assertEqual(
            helper.route_reviewer(
                score=70, runtime_models=RUNTIME_MODELS
            )["slug"],
            deep,
        )
        self.assertEqual(
            helper.route_verifier(
                priority="P1", runtime_models=RUNTIME_MODELS
            )["slug"],
            deep,
        )
        self.assertEqual(
            helper.route_probe(
                roots=2,
                files_changed=9,
                lines_changed=400,
                protected_paths=True,
                runtime_models=RUNTIME_MODELS,
            )["slug"],
            deep,
        )


class CandidateIdentityTests(unittest.TestCase):
    def test_fingerprint_changes_when_one_byte_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "artifact.md"
            path.write_bytes(b"alpha\n")
            first = helper.fingerprint_candidate(
                str(root), "revision-one", ["artifact.md"]
            )
            path.write_bytes(b"alphb\n")
            second = helper.fingerprint_candidate(
                str(root), "revision-one", ["artifact.md"]
            )
        self.assertNotEqual(first["candidate_id"], second["candidate_id"])
        self.assertNotEqual(
            first["files"][0]["sha256"], second["files"][0]["sha256"]
        )

    def test_tampered_candidate_manifest_is_rejected(self) -> None:
        candidate = make_probe()["candidate"]
        candidate["files"][0]["lines"] += 1
        with self.assertRaisesRegex(helper.ContractError, "does not match"):
            helper.validate_candidate_identity(candidate)


class FindingValidationTests(unittest.TestCase):
    def test_valid_finding_round_trips(self) -> None:
        result = helper.validate_finding(good_finding())
        self.assertEqual(result["finding_id"], "authz-missing-owner-check")
        self.assertEqual(result["impact"]["priority"], "P1")

    def test_priority_must_match_risk(self) -> None:
        with self.assertRaisesRegex(helper.ContractError, "priority"):
            helper.validate_finding(good_finding(impact={"priority": "P0", "risk_score": 75, "confidence": 82}))

    def test_confirmed_lineage_requires_confidence(self) -> None:
        with self.assertRaisesRegex(helper.ContractError, "confidence"):
            helper.validate_finding(good_finding(impact={"priority": "P1", "risk_score": 75, "confidence": 65}))
        # An unverified low-confidence finding is allowed (it just cannot be "confirmed").
        low = helper.validate_finding(
            good_finding(
                evidence=[{"ref": "auth.py:42", "lineage": "unverified"}],
                impact={"priority": "P1", "risk_score": 75, "confidence": 50},
            )
        )
        self.assertEqual(low["impact"]["confidence"], 50)

    def test_verified_requires_parent_test_confirmed(self) -> None:
        with self.assertRaisesRegex(helper.ContractError, "verified"):
            helper.validate_finding(good_finding(status="verified"))
        ok = helper.validate_finding(
            good_finding(
                evidence=[{"ref": "auth.py:42", "lineage": "parent-test-confirmed"}],
                status="verified",
            )
        )
        self.assertEqual(ok["status"], "verified")

    def test_unknown_dimension_and_bad_id_rejected(self) -> None:
        with self.assertRaises(helper.ContractError):
            helper.validate_finding(good_finding(dimension="D99"))
        with self.assertRaises(helper.ContractError):
            helper.validate_finding(good_finding(finding_id="Bad_ID"))


class ReviewerReturnCapsTests(unittest.TestCase):
    def _return(self, findings: list, **overrides) -> dict:
        payload = {
            "role": "review",
            "charter_id": "security-authz",
            "candidate_id": TEST_CANDIDATE_ID,
            "assignment_id": "security-review",
            "territory_id": "security",
            "territory": "auth surface",
            "findings": findings,
            "no_finding_evidence": [],
            "residual_uncertainty": [],
        }
        payload.update(overrides)
        return payload

    def _checks(self, **overrides) -> dict:
        checks = {
            "critical_coverage_complete": True,
            "critical_probe_blind_review_complete": True,
            "revision_matches": True,
            "partial_rollout": False,
            "blockers": [],
        }
        checks.update(overrides)
        return checks

    def _verifier_return(
        self,
        findings: list,
        *,
        clearance: str = "failed",
        checks: dict | None = None,
    ) -> dict:
        return self._return(
            findings,
            role="verify",
            assignment_id="verifier",
            territory_id="verification",
            clearance_checks=checks or self._checks(),
            shipping_clearance=clearance,
        )

    def _coverage(self, **overrides) -> dict:
        coverage = {
            "candidate_id": TEST_CANDIDATE_ID,
            "current_candidate_id": TEST_CANDIDATE_ID,
            "required_territories": ["security-review"],
            "completed_territories": ["security-review"],
            "failed_territories": [],
            "partial_territories": [],
            "required_probe_blind_territories": [],
            "completed_probe_blind_territories": [],
        }
        coverage.update(overrides)
        return coverage

    def _validate_reviewer(self, payload: dict) -> dict:
        return helper.validate_reviewer_return(
            payload,
            expected_candidate_id=TEST_CANDIDATE_ID,
            expected_assignment_id=payload.get("assignment_id"),
        )

    def _validate_verifier(
        self,
        payload: dict,
        *,
        expected: list | None = None,
        authorized: list | None = None,
        coverage: dict | None = None,
    ) -> dict:
        if expected is None:
            expected = [finding["finding_id"] for finding in payload["findings"]]
        return helper.validate_reviewer_return(
            payload,
            expected_candidate_id=TEST_CANDIDATE_ID,
            expected_assignment_id="verifier",
            expected_candidate_ids=expected,
            authorized_accepted_risk_ids=[] if authorized is None else authorized,
            coverage_state=self._coverage() if coverage is None else coverage,
        )

    def test_valid_reviewer_return_round_trips(self) -> None:
        result = self._validate_reviewer(self._return([good_finding()]))
        self.assertEqual(result["role"], "review")
        self.assertEqual(len(result["findings"]), 1)

    def test_at_most_six_findings(self) -> None:
        findings = [good_finding(finding_id=f"issue-number-{i}") for i in range(7)]
        with self.assertRaisesRegex(helper.ContractError, "at most 6"):
            self._validate_reviewer(self._return(findings))

    def test_size_cap_16_kib(self) -> None:
        findings = [
            good_finding(finding_id=f"issue-number-{i}", correction="x" * 3000)
            for i in range(6)
        ]
        with self.assertRaisesRegex(helper.ContractError, "bytes"):
            self._validate_reviewer(self._return(findings))

    def test_role_must_be_review_or_verify(self) -> None:
        with self.assertRaises(helper.ContractError):
            self._validate_reviewer(
                self._return([good_finding()], role="probe")
            )

    def test_verifier_clearance_is_inside_the_single_json_object(self) -> None:
        adjudication = good_finding(status="verified")
        verified = self._validate_verifier(
            self._verifier_return(
                [adjudication],
                clearance="approved",
            )
        )
        self.assertEqual(verified["shipping_clearance"], "approved")
        self.assertNotIn("candidate_high_risk_ids", verified)
        self.assertEqual(verified["clearance_checks"], self._checks())
        with self.assertRaisesRegex(helper.ContractError, "shipping_clearance"):
            helper.validate_reviewer_return(
                self._return([good_finding()], role="verify"),
                expected_candidate_ids=["authz-missing-owner-check"],
                authorized_accepted_risk_ids=[],
            )
        with self.assertRaisesRegex(helper.ContractError, "unknown keys"):
            helper.validate_reviewer_return(
                self._return(
                    [good_finding()],
                    shipping_clearance="approved",
                )
            )
        with self.assertRaisesRegex(helper.ContractError, "approved.*failed"):
            self._validate_verifier(
                self._verifier_return(
                    [good_finding()],
                    clearance="not_evaluated",
                )
            )

    def test_verifier_requires_parent_binding_scope_authority_and_coverage(self) -> None:
        payload = self._verifier_return([good_finding(status="verified")])
        with self.assertRaisesRegex(helper.ContractError, "expected_candidate_id"):
            helper.validate_reviewer_return(payload)
        with self.assertRaisesRegex(helper.ContractError, "expected_candidate_ids"):
            helper.validate_reviewer_return(
                payload,
                expected_candidate_id=TEST_CANDIDATE_ID,
                expected_assignment_id="verifier",
            )
        with self.assertRaisesRegex(
            helper.ContractError, "authorized_accepted_risk_ids"
        ):
            helper.validate_reviewer_return(
                payload,
                expected_candidate_id=TEST_CANDIDATE_ID,
                expected_assignment_id="verifier",
                expected_candidate_ids=["authz-missing-owner-check"],
            )
        with self.assertRaisesRegex(helper.ContractError, "coverage_state"):
            helper.validate_reviewer_return(
                payload,
                expected_candidate_id=TEST_CANDIDATE_ID,
                expected_assignment_id="verifier",
                expected_candidate_ids=["authz-missing-owner-check"],
                authorized_accepted_risk_ids=[],
            )
        echoed = dict(payload, candidate_high_risk_ids=["authz-missing-owner-check"])
        with self.assertRaisesRegex(helper.ContractError, "unknown keys"):
            self._validate_verifier(echoed)

    def test_verifier_requires_exact_unique_adjudication_scope(self) -> None:
        candidate = "authz-missing-owner-check"
        with self.assertRaisesRegex(helper.ContractError, "missing=.*authz"):
            self._validate_verifier(
                self._verifier_return(
                    [],
                ),
                expected=[candidate],
            )
        with self.assertRaisesRegex(helper.ContractError, "extra=.*authz"):
            self._validate_verifier(
                self._verifier_return([good_finding()]),
                expected=[],
            )
        with self.assertRaisesRegex(helper.ContractError, "duplicate adjudication"):
            self._validate_verifier(
                self._verifier_return(
                    [good_finding(), good_finding()],
                ),
                expected=[candidate],
            )
        with self.assertRaisesRegex(helper.ContractError, "duplicate finding id"):
            self._validate_verifier(
                self._verifier_return([good_finding()]),
                expected=[candidate, candidate],
            )

    def test_verifier_approved_requires_resolved_adjudication(self) -> None:
        with self.assertRaisesRegex(helper.ContractError, "unresolved="):
            self._validate_verifier(
                self._verifier_return(
                    [good_finding(status="open")],
                    clearance="approved",
                )
            )

    def test_verifier_clearance_resolutions_require_confirmed_evidence(self) -> None:
        for status in ("duplicate", "false-positive"):
            with self.subTest(status=status):
                unverified = good_finding(
                    status=status,
                    evidence=[{"ref": "auth.py:42", "lineage": "unverified"}],
                    impact={"priority": "P4", "risk_score": 1, "confidence": 1},
                )
                with self.assertRaisesRegex(
                    helper.ContractError,
                    rf"verifier {status} status requires confirmed evidence.*>= 70",
                ):
                    self._validate_verifier(
                        self._verifier_return([unverified], clearance="approved")
                    )
                confirmed = self._validate_verifier(
                    self._verifier_return(
                        [good_finding(status=status)],
                        clearance="approved",
                    )
                )
                self.assertEqual(confirmed["shipping_clearance"], "approved")
                reviewer = self._validate_reviewer(self._return([unverified]))
                self.assertEqual(reviewer["findings"][0]["status"], status)

        open_finding = good_finding(
            status="open",
            evidence=[{"ref": "auth.py:42", "lineage": "unverified"}],
            impact={"priority": "P4", "risk_score": 1, "confidence": 1},
        )
        unresolved = self._validate_verifier(
            self._verifier_return([open_finding], clearance="failed")
        )
        self.assertEqual(unresolved["findings"][0]["status"], "open")

    def test_verifier_approved_requires_clear_blocker_state(self) -> None:
        adjudication = good_finding(status="verified")
        with self.assertRaisesRegex(helper.ContractError, "failed_checks"):
            self._validate_verifier(
                self._verifier_return(
                    [adjudication],
                    clearance="approved",
                    checks=self._checks(revision_matches=False),
                )
            )
        with self.assertRaisesRegex(helper.ContractError, "remaining contradiction"):
            self._validate_verifier(
                self._verifier_return(
                    [adjudication],
                    clearance="approved",
                    checks=self._checks(blockers=["remaining contradiction"]),
                )
            )

    def test_failed_verifier_return_may_report_unresolved_blockers(self) -> None:
        result = self._validate_verifier(
            self._verifier_return(
                [good_finding(status="open")],
                clearance="failed",
                checks=self._checks(
                    revision_matches=False,
                    blockers=["candidate remains open"],
                ),
            )
        )
        self.assertEqual(result["shipping_clearance"], "failed")
        self.assertEqual(result["clearance_checks"]["blockers"], ["candidate remains open"])

    def test_accepted_risk_requires_parent_authority_and_confirmed_evidence(self) -> None:
        accepted = good_finding(status="accepted-risk")
        with self.assertRaisesRegex(helper.ContractError, "reviewers cannot accept risk"):
            helper.validate_finding(accepted)
        with self.assertRaisesRegex(helper.ContractError, "reviewers cannot accept risk"):
            self._validate_reviewer(self._return([accepted]))
        with self.assertRaisesRegex(helper.ContractError, "not authorized"):
            self._validate_verifier(self._verifier_return([accepted]))
        authorized = self._validate_verifier(
            self._verifier_return([accepted], clearance="approved"),
            authorized=["authz-missing-owner-check"],
        )
        self.assertEqual(authorized["shipping_clearance"], "approved")
        unconfirmed = good_finding(
            status="accepted-risk",
            evidence=[{"ref": "auth.py:42", "lineage": "unverified"}],
            impact={"priority": "P1", "risk_score": 75, "confidence": 82},
        )
        with self.assertRaisesRegex(
            helper.ContractError, "confirmed evidence.*confidence >= 70"
        ):
            self._validate_verifier(
                self._verifier_return([unconfirmed]),
                authorized=["authz-missing-owner-check"],
            )
        low_confidence = good_finding(
            status="accepted-risk",
            impact={"priority": "P1", "risk_score": 75, "confidence": 65},
        )
        with self.assertRaisesRegex(helper.ContractError, "confidence >= 70"):
            self._validate_verifier(
                self._verifier_return([low_confidence]),
                authorized=["authz-missing-owner-check"],
            )

    def test_parent_observed_coverage_blocks_false_clearance(self) -> None:
        adjudication = self._verifier_return(
            [good_finding(status="verified")],
            clearance="approved",
        )
        cases = (
            (
                self._coverage(completed_territories=[]),
                "parent_critical_coverage",
            ),
            (
                self._coverage(failed_territories=["security-review"]),
                "parent_failed_workers",
            ),
            (
                self._coverage(partial_territories=["security-review"]),
                "parent_partial_outputs",
            ),
            (
                self._coverage(current_candidate_id="sha256:" + "0" * 64),
                "parent_candidate_identity",
            ),
            (
                self._coverage(
                    required_probe_blind_territories=["blind-security"],
                    completed_probe_blind_territories=[],
                ),
                "parent_probe_blind_coverage",
            ),
        )
        for coverage, failure in cases:
            with self.subTest(failure=failure):
                with self.assertRaisesRegex(helper.ContractError, failure):
                    self._validate_verifier(
                        adjudication,
                        coverage=coverage,
                    )

    def test_invalid_return_is_not_a_no_finding_result(self) -> None:
        with self.assertRaises(helper.ContractError):
            helper.validate_reviewer_return(
                "INERT: charter was incomplete; no review performed"
            )
        report = helper.render_report(
            {
                "band": "deep",
                "findings": [],
                "coverage": {
                    "failed_dispatches": [
                        {
                            "failure_class": "charter",
                            "assignment_id": "security-review",
                            "territory": "security-authz",
                        }
                    ],
                    "uncovered": ["security-authz"],
                },
            }
        )
        self.assertIn(
            "Failed dispatch (charter): assignment=security-review; "
            "territory=security-authz",
            report,
        )
        self.assertIn("Uncovered: security-authz", report)


class CurationRenderTests(unittest.TestCase):
    def test_report_curates_to_ten_and_summarizes_minors(self) -> None:
        majors = [
            {
                "finding_id": f"major-finding-{i}",
                "dimension": "D01",
                "focus_area": "core",
                "root_cause": "rc",
                "correction": "fix",
                "status": "open",
                "impact": {"priority": "P1", "risk_score": 75, "confidence": 80},
            }
            for i in range(12)
        ]
        minors = [
            {"finding_id": f"minor-{i}", "impact": {"priority": "P3", "risk_score": 20, "confidence": 60}}
            for i in range(3)
        ] + [
            {"finding_id": f"trivial-{i}", "impact": {"priority": "P4", "risk_score": 5, "confidence": 60}}
            for i in range(2)
        ]
        report = helper.render_report(
            {
                "band": "critical",
                "findings": majors + minors,
                "shipping_clearance": "failed",
                "coverage": {"reviewers": 5, "waived": [{"dimension": "D13", "why": "cosmetic", "evidence": "probe"}]},
            }
        )
        self.assertIn(f"truncated at {helper.MAX_REPORT_FINDINGS}", report)
        self.assertIn("P3 x 3, P4 x 2", report)
        self.assertIn("Waived D13", report)
        shown_rows = report.count("| major-finding-")
        self.assertLessEqual(shown_rows, helper.MAX_REPORT_FINDINGS)


class RunawayRegressionTests(unittest.TestCase):
    """Capstone: a default run cannot become the removed ~20-agent runaway."""

    def _probe_for(self, band: str) -> dict:
        seeds = {
            "trivial": make_probe(files=3, lines=50, fix_character="cosmetic"),
            "small": make_probe({"D01": 50}, files=3),
            "standard": make_probe({"D01": 70}),
            "deep": make_probe({"D01": 85}),
            "critical": make_probe({"D01": 95}),
        }
        return seeds[band]

    def test_no_band_exceeds_five_reviewers_or_nine_dispatches(self) -> None:
        # Each natural seed lands in its band, within the reviewer/dispatch caps.
        for band in helper.BANDS:
            plan = helper.size_cohort(self._probe_for(band))
            self.assertEqual(plan["band"], band)
            self.assertLessEqual(plan["reviewers"], helper.BASE_MAX_REVIEWERS)
            self.assertLessEqual(plan["max_dispatches"], helper.ABSOLUTE_MAX_DISPATCHES)
        # Fan-out pressure (many focus areas / impacted surfaces) may legitimately
        # ESCALATE the band, but can never breach the 5-reviewer / 9-dispatch caps.
        for band in helper.BANDS:
            probe = self._probe_for(band)
            probe["territories"] = [{"focus_area": f"t{i}"} for i in range(50)]
            probe["surface"]["impacted_surfaces"] = [f"s{i}" for i in range(50)]
            plan = helper.size_cohort(probe)
            self.assertLessEqual(plan["reviewers"], helper.BASE_MAX_REVIEWERS)
            self.assertLessEqual(plan["max_dispatches"], helper.ABSOLUTE_MAX_DISPATCHES)

    def test_low_bands_never_schedule_a_verifier_or_second_pass(self) -> None:
        # Trivial/Small carry no verifier gate at all -> an ungated verifier is impossible.
        for band in ("trivial", "small"):
            self.assertEqual(helper.BAND_SPEC[band]["verifier"], "no")
        # No default band auto-starts a second pass; only deep/critical may, and only gated.
        for band in ("trivial", "small", "standard"):
            self.assertEqual(helper.BAND_SPEC[band]["second_pass"], "no")
        for band in ("deep", "critical"):
            self.assertEqual(helper.BAND_SPEC[band]["second_pass"], "gated")

    def test_counter_blocks_every_runaway_axis(self) -> None:
        # The sizer caps reviewers at 5; the counter caps critical's base cohort at 8.
        # probe + 5 reviewers + verifier = 7 base fits; base 9 (7 reviewers) is refused.
        ok = ["probe"] + ["reviewer"] * 5 + ["verifier"]
        helper.evaluate_budget(
            "critical", [{"kind": k, "batch": i // 3} for i, k in enumerate(ok)]
        )
        too_many = ["probe"] + ["reviewer"] * 7 + ["verifier"]  # base 9 > critical ceiling 8
        with self.assertRaises(helper.ContractError):
            helper.evaluate_budget(
                "critical", [{"kind": k, "batch": i // 3} for i, k in enumerate(too_many)]
            )
        # No second probe, no evidence subagent, no third pass — the three doctrine breaches.
        counter = helper.BudgetCounter("critical")
        counter.record("probe")
        with self.assertRaises(helper.ContractError):
            counter.record("probe", batch=1)
        with self.assertRaises(helper.ContractError):
            helper.BudgetCounter("critical").record("evidence")
        with self.assertRaises(helper.ContractError):
            helper.evaluate_budget("critical", [{"kind": "reviewer", "pass_index": 3}])


class CliContractTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = swarm_cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_risk_verb_success(self) -> None:
        code, out, _ = self._run(
            ["risk", "--impact", "4", "--likelihood", "4", "--exposure", "4", "--irreversibility", "4"]
        )
        self.assertEqual(code, 0)
        self.assertIn('"risk_score": 80', out)
        self.assertIn('"priority": "P1"', out)

    def test_failure_prints_swarm_prefix_and_exit_two(self) -> None:
        code, _, err = self._run(
            ["risk", "--impact", "9", "--likelihood", "1", "--exposure", "1", "--irreversibility", "1"]
        )
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("swarm: "), err)

    def test_bad_json_is_a_bounded_failure(self) -> None:
        code, _, err = self._run(["validate-finding", "{not json"])
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("swarm: "), err)

    def test_verifier_cli_requires_authoritative_scope_and_authority(self) -> None:
        finding = good_finding(status="verified")
        coverage = {
            "candidate_id": TEST_CANDIDATE_ID,
            "current_candidate_id": TEST_CANDIDATE_ID,
            "required_territories": ["security-review"],
            "completed_territories": ["security-review"],
            "failed_territories": [],
            "partial_territories": [],
            "required_probe_blind_territories": [],
            "completed_probe_blind_territories": [],
        }
        payload = json.dumps(
            {
                "role": "verify",
                "charter_id": "verifier",
                "candidate_id": TEST_CANDIDATE_ID,
                "assignment_id": "verifier",
                "territory_id": "verification",
                "territory": "verification",
                "findings": [finding],
                "no_finding_evidence": [],
                "residual_uncertainty": [],
                "clearance_checks": {
                    "critical_coverage_complete": True,
                    "critical_probe_blind_review_complete": True,
                    "revision_matches": True,
                    "partial_rollout": False,
                    "blockers": [],
                },
                "shipping_clearance": "approved",
            }
        )
        code, _, err = self._run(
            ["validate-finding", payload, "--reviewer-return"]
        )
        self.assertEqual(code, 2)
        self.assertIn("expected_candidate_id", err)
        code, out, _ = self._run(
            [
                "validate-finding",
                payload,
                "--reviewer-return",
                "--expected-candidate-id",
                TEST_CANDIDATE_ID,
                "--expected-assignment-id",
                "verifier",
                "--expected-candidate-ids",
                '["authz-missing-owner-check"]',
                "--authorized-accepted-risk-ids",
                "[]",
                "--coverage-state",
                json.dumps(coverage),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["shipping_clearance"], "approved")

    def test_verifier_cli_rejects_unverified_clearance_resolutions(self) -> None:
        coverage = {
            "candidate_id": TEST_CANDIDATE_ID,
            "current_candidate_id": TEST_CANDIDATE_ID,
            "required_territories": ["security-review"],
            "completed_territories": ["security-review"],
            "failed_territories": [],
            "partial_territories": [],
            "required_probe_blind_territories": [],
            "completed_probe_blind_territories": [],
        }

        def payload_for(finding: dict) -> str:
            return json.dumps(
                {
                    "role": "verify",
                    "charter_id": "verifier",
                    "candidate_id": TEST_CANDIDATE_ID,
                    "assignment_id": "verifier",
                    "territory_id": "verification",
                    "territory": "verification",
                    "findings": [finding],
                    "no_finding_evidence": [],
                    "residual_uncertainty": [],
                    "clearance_checks": {
                        "critical_coverage_complete": True,
                        "critical_probe_blind_review_complete": True,
                        "revision_matches": True,
                        "partial_rollout": False,
                        "blockers": [],
                    },
                    "shipping_clearance": "approved",
                }
            )

        def argv_for(finding: dict) -> list[str]:
            return [
                "validate-finding",
                payload_for(finding),
                "--reviewer-return",
                "--expected-candidate-id",
                TEST_CANDIDATE_ID,
                "--expected-assignment-id",
                "verifier",
                "--expected-candidate-ids",
                '["authz-missing-owner-check"]',
                "--authorized-accepted-risk-ids",
                "[]",
                "--coverage-state",
                json.dumps(coverage),
            ]

        for status in ("duplicate", "false-positive"):
            with self.subTest(status=status):
                unverified = good_finding(
                    status=status,
                    evidence=[{"ref": "auth.py:42", "lineage": "unverified"}],
                    impact={"priority": "P4", "risk_score": 1, "confidence": 1},
                )
                code, _, err = self._run(argv_for(unverified))
                self.assertEqual(code, 2)
                self.assertIn(
                    f"verifier {status} status requires confirmed evidence", err
                )
                code, out, _ = self._run(
                    argv_for(good_finding(status=status))
                )
                self.assertEqual(code, 0)
                self.assertEqual(
                    json.loads(out)["findings"][0]["status"], status
                )


# The 11 committed reviewer charters (references/charters/<id>.md, minus probe/verifier).
COMMITTED_REVIEWER_CHARTERS = {
    "generic-surface", "api-contract-compat", "data-integrity-migration",
    "security-authz", "privacy-secrets", "reliability-failure",
    "concurrency-ordering", "performance", "testing-evidence",
    "architecture-maintainability", "policy-governance",
}


class CharterMapTests(unittest.TestCase):
    def test_focus_area_maps_to_committed_charter(self) -> None:
        self.assertEqual(helper.charter_for("security"), "security-authz")
        self.assertEqual(helper.charter_for("generic-surface"), "generic-surface")
        self.assertEqual(helper.charter_for("policy"), "policy-governance")

    def test_already_resolved_charter_id_passes_through(self) -> None:
        self.assertEqual(helper.charter_for("data-integrity-migration"), "data-integrity-migration")

    def test_unknown_focus_falls_back_to_generic_surface(self) -> None:
        # A plan must never name a charter file that is not committed.
        self.assertEqual(helper.charter_for("made-up-focus"), "generic-surface")
        self.assertEqual(helper.charter_for(""), "generic-surface")

    def test_map_covers_exactly_the_committed_charters(self) -> None:
        self.assertEqual(set(helper.CHARTER_IDS), COMMITTED_REVIEWER_CHARTERS)


class PlanTests(unittest.TestCase):
    def _plan(self, probe: dict) -> dict:
        return helper.plan_run(probe, runtime_models=RUNTIME_MODELS)

    def test_trivial_plan_is_one_economy_reviewer(self) -> None:
        plan = self._plan(
            make_probe(files=3, lines=50, fix_character="cosmetic")
        )
        self.assertEqual(plan["band"], "trivial")
        self.assertEqual(len(plan["cohort"]), 1)  # floor 1
        entry = plan["cohort"][0]
        self.assertEqual(entry["slug"], MODEL_CATALOG["economy"][0])
        self.assertEqual(entry["rigor"], "light")
        self.assertEqual(entry["model_class"], "economy")
        self.assertEqual(entry["fallbacks"], MODEL_CATALOG["economy"][1:])
        self.assertIn(entry["charter_id"], helper.CHARTER_IDS)
        self.assertEqual(plan["budget"]["max_accepted_workers"], 2)
        self.assertEqual(plan["budget"]["concurrency"], 1)
        self.assertEqual(plan["budget"]["target_wall_clock_seconds"], 180)
        self.assertEqual(plan["preflight"]["reviewer_launches"], 0)
        self.assertEqual(
            entry["candidate_id"], plan["candidate"]["candidate_id"]
        )
        self.assertEqual(plan["charter_ids"], [entry["charter_id"]])

    def test_plan_routes_each_territory_off_its_driving_score(self) -> None:
        probe = make_probe(
            {"D04": 95, "D08": 70},
            territories=[
                {"focus_area": "security", "dimensions": ["D04"]},
                {"focus_area": "performance", "dimensions": ["D08"]},
            ],
        )
        plan = self._plan(probe)
        self.assertEqual(plan["band"], "critical")  # D04 >= 80 -> critical
        by_focus = {
            c["focus_area"]: c
            for c in plan["cohort"]
            if not c["blind_to_probe"]
        }
        self.assertEqual(by_focus["security"]["charter_id"], "security-authz")
        self.assertEqual(by_focus["security"]["slug"], MODEL_CATALOG["critical"][0])  # >=90
        self.assertEqual(by_focus["security"]["rigor"], "max")
        self.assertEqual(by_focus["performance"]["charter_id"], "performance")
        self.assertEqual(
            by_focus["performance"]["slug"],
            MODEL_CATALOG["deep"][0],
        )  # 60-89 deep
        self.assertEqual(by_focus["performance"]["model_class"], "deep")
        self.assertEqual(by_focus["performance"]["fallbacks"], MODEL_CATALOG["deep"][1:])
        # Cohort is capped at the base max and every charter id is committed.
        self.assertLessEqual(len(plan["cohort"]), helper.BASE_MAX_REVIEWERS)
        for cid in plan["charter_ids"]:
            self.assertIn(cid, helper.CHARTER_IDS)

    def test_plan_routes_long_form_probe_focus_areas_to_specialists(self) -> None:
        # Flag #1 (highest-risk reconciliation): the probe emits
        # territories[].focus_area in the LONG charter-name form (INDEX.md routing
        # keys), e.g. "security-authz" — NOT the short header label "security".
        # Each specialist territory must route to its own charter, never silently
        # fall back to generic-surface. Bites if the map/charter_for stops keying
        # on the form the probe actually emits.
        probe = make_probe(
            {"D04": 75, "D03": 72, "D07": 70},
            files=9,
            lines=240,
            territories=[
                {"focus_area": "security-authz", "dimensions": ["D04"]},
                {"focus_area": "data-integrity-migration", "dimensions": ["D03"]},
                {"focus_area": "concurrency-ordering", "dimensions": ["D07"]},
            ],
        )
        plan = self._plan(probe)
        self.assertEqual(plan["band"], "deep")  # D04/D03/D07 in 60-79 -> deep
        by_focus = {c["focus_area"]: c for c in plan["cohort"]}
        self.assertEqual(by_focus["security-authz"]["charter_id"], "security-authz")
        self.assertEqual(
            by_focus["data-integrity-migration"]["charter_id"], "data-integrity-migration"
        )
        self.assertEqual(
            by_focus["concurrency-ordering"]["charter_id"], "concurrency-ordering"
        )
        self.assertNotIn("generic-surface", plan["charter_ids"])
        self.assertEqual(
            set(plan["charter_ids"]),
            {"security-authz", "data-integrity-migration", "concurrency-ordering"},
        )

    def test_plan_pads_band_floor_with_generic_surface(self) -> None:
        # Standard band, no probe territories -> reviewer floor (2), padded generic.
        plan = self._plan(make_probe({"D01": 70}))
        self.assertEqual(plan["band"], "standard")
        self.assertEqual(len(plan["cohort"]), 2)
        self.assertTrue(all(c["focus_area"] == "generic-surface" for c in plan["cohort"]))
        self.assertTrue(
            all(c["slug"] == MODEL_CATALOG["deep"][0] for c in plan["cohort"])
        )  # 60-89 deep
        self.assertEqual(plan["charter_ids"], ["generic-surface"])
        self.assertEqual(plan["budget"]["max_accepted_workers"], 4)
        self.assertEqual(plan["budget"]["reviewer_capacity"], 3)
        self.assertEqual(plan["budget"]["concurrency"], 2)

    def test_standard_three_required_territories_do_not_reserve_gated_verifier(self) -> None:
        plan = self._plan(
            make_probe(
                {"D01": 70, "D02": 65, "D08": 60},
                territories=[
                    {"id": "logic", "focus_area": "generic-surface", "dimensions": ["D01"]},
                    {"id": "api", "focus_area": "api-contract", "dimensions": ["D02"]},
                    {"id": "performance", "focus_area": "performance", "dimensions": ["D08"]},
                ],
            )
        )
        self.assertEqual(plan["band"], "standard")
        self.assertEqual(len(plan["cohort"]), 3)
        self.assertEqual(plan["budget"]["reviewer_capacity"], 3)
        self.assertTrue(plan["verifier"]["conditional"])
        self.assertFalse(plan["verifier"]["required"])
        self.assertFalse(plan["verifier"]["reserved"])
        self.assertNotIn(["verifier"], plan["waves"])

    def test_capacity_pressure_refuses_before_reviewer_dispatch(self) -> None:
        probe = make_probe(
            {"D01": 95},
            territories=[
                {"focus_area": f"t{i}", "dimensions": ["D01"]}
                for i in range(50)
            ],
        )
        with self.assertRaisesRegex(
            helper.CapacityError,
            "coverage capacity.*zero reviewer launches",
        ):
            self._plan(probe)

    def test_9396_line_critical_scope_gets_bounded_evidence_packs(self) -> None:
        line_counts = [1342] * 6 + [1344]
        candidate_files = []
        sections = []
        for index, line_count in enumerate(line_counts, start=1):
            path = f"artifact-{index}.md"
            marker = f"{path}:{line_count}".encode()
            candidate_files.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(marker).hexdigest(),
                    "bytes": len(marker),
                    "lines": line_count,
                }
            )
            sections.append(
                {
                    "section_id": f"section-{index}",
                    "path": path,
                    "start_line": 1,
                    "end_line": line_count,
                    "flows": [f"flow-{index}"],
                }
            )
        probe = make_probe(
            {"D03": 82, "D04": 95, "D06": 84, "D15": 70},
            files=7,
            lines=9396,
            candidate_files=candidate_files,
            sections=sections,
            depth="deep",
            protected={
                "state_migration_D03": True,
                "security_privacy_D04_D05": True,
                "concurrency_D07": False,
                "reliability_release_D06_D16": True,
            },
            territories=[
                {
                    "id": "security",
                    "focus_area": "security-authz",
                    "dimensions": ["D04", "D05"],
                    "section_ids": ["section-1", "section-2"],
                },
                {
                    "id": "data-integrity",
                    "focus_area": "data-integrity-migration",
                    "dimensions": ["D03"],
                    "section_ids": ["section-3", "section-4"],
                },
                {
                    "id": "reliability",
                    "focus_area": "reliability-failure",
                    "dimensions": ["D06", "D16"],
                    "section_ids": ["section-5", "section-6"],
                },
                {
                    "id": "policy",
                    "focus_area": "policy-governance",
                    "dimensions": ["D15"],
                    "section_ids": ["section-7"],
                },
            ],
        )
        plan = self._plan(probe)
        self.assertEqual(plan["band"], "critical")
        self.assertEqual(len(plan["cohort"]), 5)
        self.assertTrue(plan["verifier"]["required"])
        self.assertTrue(plan["verifier"]["reserved"])
        self.assertEqual(plan["budget"]["reviewer_capacity"], 5)
        self.assertEqual(plan["waves"][-1], ["verifier"])
        self.assertLessEqual(
            1 + len(plan["cohort"]) + 1,
            plan["budget"]["max_accepted_workers"],
        )
        self.assertEqual(
            set(plan["coverage"]["required_critical_territory_ids"]),
            {"security", "data-integrity", "reliability"},
        )
        for assignment in plan["cohort"]:
            self.assertLessEqual(
                assignment["evidence_pack"]["line_count"],
                helper.MAX_EVIDENCE_PACK_LINES,
            )
            self.assertLess(
                assignment["evidence_pack"]["line_count"],
                9396,
            )
            self.assertEqual(
                assignment["candidate_id"],
                plan["candidate"]["candidate_id"],
            )
        blind = [
            assignment
            for assignment in plan["cohort"]
            if assignment["blind_to_probe"]
        ]
        self.assertEqual(len(blind), 1)
        self.assertTrue(blind[0]["overlap_section_ids"])

    def test_explicit_integration_review_is_not_a_catch_all(self) -> None:
        probe = make_probe(
            {"D04": 95, "D14": 70},
            territories=[
                {
                    "id": "security",
                    "focus_area": "security-authz",
                    "dimensions": ["D04"],
                },
                {
                    "id": "architecture",
                    "focus_area": "architecture-maintainability",
                    "dimensions": ["D14"],
                },
            ],
        )
        no_integration = self._plan(probe)
        self.assertFalse(
            any(
                assignment["purpose"]
                == "explicit-cross-territory-integration"
                for assignment in no_integration["cohort"]
            )
        )


class VerifierGateTests(unittest.TestCase):
    def test_empty_findings_runs_no_verifier(self) -> None:
        self.assertEqual(helper.gate_verifier([]), {"run": False, "reasons": []})

    def test_candidate_p0_forces_verifier(self) -> None:
        result = helper.gate_verifier(
            [{"finding_id": "boot-p0", "impact": {"priority": "P0"}, "status": "open"}]
        )
        self.assertTrue(result["run"])
        self.assertTrue(any("P0" in r for r in result["reasons"]), result["reasons"])

    def test_dismissed_p0_does_not_fire(self) -> None:
        result = helper.gate_verifier(
            [{"finding_id": "boot-p0", "impact": {"priority": "P0"}, "status": "false-positive"}]
        )
        self.assertFalse(result["run"])

    def test_blocking_protected_axis_p1_fires(self) -> None:
        result = helper.gate_verifier(
            [{"finding_id": "authz-gap", "priority": "P1", "dimension": "D04", "status": "open"}]
        )
        self.assertTrue(result["run"])
        self.assertTrue(any("block" in r for r in result["reasons"]), result["reasons"])

    def test_unresolved_p1_contradiction_fires(self) -> None:
        result = helper.gate_verifier(
            [{"finding_id": "contested", "priority": "P1", "dimension": "D01",
              "contradicts": ["other"], "status": "open"}]
        )
        self.assertTrue(result["run"])
        self.assertTrue(any("contradiction" in r for r in result["reasons"]), result["reasons"])

    def test_clearance_request_needs_a_critical_change(self) -> None:
        self.assertTrue(helper.gate_verifier([], critical_change=True, clearance_request=True)["run"])
        # A clearance request on a non-critical change does not force a verifier.
        self.assertFalse(helper.gate_verifier([], clearance_request=True)["run"])

    def test_non_blocking_minor_finding_does_not_fire(self) -> None:
        result = helper.gate_verifier(
            [{"finding_id": "nit", "priority": "P2", "dimension": "D08", "status": "open"}]
        )
        self.assertFalse(result["run"])


class SecondPassGateTests(unittest.TestCase):
    def _state(self, **overrides) -> dict:
        state = {
            "candidate_without_evidence": True,
            "unresolved_question": "does the migration preserve invariant X?",
            "territory": "data-integrity-migration",
            "reused_charter_ids": ["data-integrity-migration"],
            "dispatches_used": 4,
            "minutes_elapsed": 8,
        }
        state.update(overrides)
        return state

    def test_allowed_when_trigger_budget_and_discipline_all_hold(self) -> None:
        result = helper.gate_second_pass(self._state())
        self.assertTrue(result["allowed"], result["reason"])

    def test_denied_without_any_trigger(self) -> None:
        result = helper.gate_second_pass(
            self._state(
                candidate_without_evidence=False, contradiction=False,
                uncovered_critical_territory=False, fix_changed_critical_boundary=False,
            )
        )
        self.assertFalse(result["allowed"])
        self.assertIn("trigger", result["reason"])

    def test_denied_when_dispatch_budget_exhausted(self) -> None:
        result = helper.gate_second_pass(self._state(dispatches_used=9))
        self.assertFalse(result["allowed"])
        self.assertIn("budget", result["reason"])

    def test_denied_after_the_no_new_dispatch_line(self) -> None:
        result = helper.gate_second_pass(self._state(minutes_elapsed=21))
        self.assertFalse(result["allowed"])
        self.assertIn("start-new-work", result["reason"])

    def test_denied_without_a_stated_question_and_territory(self) -> None:
        self.assertFalse(helper.gate_second_pass(self._state(unresolved_question=""))["allowed"])
        self.assertFalse(helper.gate_second_pass(self._state(territory=""))["allowed"])

    def test_denied_when_reusing_more_than_two_charters(self) -> None:
        result = helper.gate_second_pass(self._state(reused_charter_ids=["a", "b", "c"]))
        self.assertFalse(result["allowed"])

    def test_optional_band_guard_refuses_single_pass_bands(self) -> None:
        self.assertFalse(helper.gate_second_pass(self._state(band="trivial"))["allowed"])
        self.assertTrue(helper.gate_second_pass(self._state(band="deep"))["allowed"])


class JitVerbCliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = swarm_cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_route_probe_trivial_and_heavy(self) -> None:
        code, out, _ = self._run(
            [
                "route-probe", "--roots", "1", "--files-changed", "3",
                "--lines-changed", "50", "--runtime-models",
                RUNTIME_MODELS_JSON,
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out),
            {
                "model_class": "economy",
                "slug": MODEL_CATALOG["economy"][0],
                "rigor": "light",
                "fallbacks": MODEL_CATALOG["economy"][1:],
                "filtered_models": [],
            },
        )
        code, out, _ = self._run(
            ["route-probe", "--roots", "2", "--files-changed", "9",
             "--lines-changed", "400", "--protected-paths",
             "--runtime-models", RUNTIME_MODELS_JSON]
        )
        self.assertEqual(
            json.loads(out),
            {
                "model_class": "deep",
                "slug": MODEL_CATALOG["deep"][0],
                "rigor": "deep",
                "fallbacks": MODEL_CATALOG["deep"][1:],
                "filtered_models": [],
            },
        )

    def test_route_reviewer_and_verifier(self) -> None:
        _, out, _ = self._run(
            [
                "route", "--role", "reviewer", "--score", "95",
                "--runtime-models", RUNTIME_MODELS_JSON,
            ]
        )
        self.assertEqual(
            json.loads(out),
            {
                "model_class": "critical",
                "slug": MODEL_CATALOG["critical"][0],
                "rigor": "max",
                "fallbacks": MODEL_CATALOG["critical"][1:],
                "filtered_models": [],
            },
        )
        _, out, _ = self._run(
            [
                "route", "--role", "verifier", "--priority", "P1",
                "--runtime-models", RUNTIME_MODELS_JSON,
            ]
        )
        self.assertEqual(
            json.loads(out),
            {
                "model_class": "deep",
                "slug": MODEL_CATALOG["deep"][0],
                "rigor": "deep",
                "fallbacks": MODEL_CATALOG["deep"][1:],
                "filtered_models": [],
            },
        )

    def test_route_missing_or_bad_severity_is_bounded_failure(self) -> None:
        code, _, err = self._run(
            [
                "route", "--role", "reviewer",
                "--runtime-models", RUNTIME_MODELS_JSON,
            ]
        )
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("swarm: "), err)
        code, _, err = self._run(
            [
                "route", "--role", "verifier", "--priority", "P9",
                "--runtime-models", RUNTIME_MODELS_JSON,
            ]
        )
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("swarm: "), err)

    def test_gate_verifier_cli(self) -> None:
        code, out, _ = self._run(
            ["gate-verifier", '[{"finding_id":"p0","priority":"P0","status":"open"}]']
        )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["run"])

    def test_gate_second_pass_cli(self) -> None:
        state = json.dumps(
            {
                "contradiction": True,
                "unresolved_question": "which finding is correct?",
                "territory": "auth surface",
                "reused_charter_ids": ["security-authz"],
                "dispatches_used": 5,
                "minutes_elapsed": 10,
            }
        )
        code, out, _ = self._run(["gate-second-pass", state])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["allowed"])

    def test_plan_cli_trivial(self) -> None:
        probe = json.dumps(make_probe(files=3, lines=50, fix_character="cosmetic"))
        code, out, _ = self._run(
            ["plan", probe, "--runtime-models", RUNTIME_MODELS_JSON]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["band"], "trivial")
        self.assertEqual(len(payload["cohort"]), 1)
        self.assertEqual(payload["cohort"][0]["slug"], MODEL_CATALOG["economy"][0])
        self.assertIn("max_accepted_workers", payload["budget"])
        self.assertEqual(payload["charter_ids"], [payload["cohort"][0]["charter_id"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
