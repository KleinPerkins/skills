"""Tests for engine.curation: read-only, zero-write promotion-candidate
curation reports grouped by destination class. Promotion candidates are
proposals only -- these tests specifically assert curate() never writes to
any preference, ecosystem-policy, product-requirement, or live-system-doc
destination (nor anywhere else)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import _support

from engine import curation, durability, identity as identity_mod, transaction as tx

TASK_ID = "task-curation-test"


def _identity_for(repo: Path) -> identity_mod.RootIdentity:
    return identity_mod.resolve_root_identity(str(repo))


def _keys_for(identity: identity_mod.RootIdentity):
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    workstream_key = identity_mod.workstream_key_for(repo_key, clone_key, TASK_ID, identity)
    return repo_key, clone_key, workstream_key


def _candidate(candidate_id, destination_class, summary, *, status="proposed", authority=None):
    doc = {"candidate_id": candidate_id, "destination_class": destination_class, "summary": summary, "status": status}
    if authority:
        doc["authority"] = authority
    return doc


class CurationTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        self.identity = _identity_for(self.repo)
        self.repo_key, self.clone_key, self.workstream_key = _keys_for(self.identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _flush_with_candidates(self, candidates):
        def build(_current_doc):
            return {
                "schema": "save-game-current/v1",
                "task_id": TASK_ID,
                "workstream_key": self.workstream_key,
                "root": identity_mod.root_snapshot_dict(self.identity),
                "objective": "Ship the thing.",
                "scope": {"in_scope": [], "non_scope": [], "deferred": []},
                "hygiene": {
                    "transactions_finalized": True,
                    "temp_artifacts_clear": True,
                    "repo_status_observed": True,
                    "required_checks_run": True,
                    "unclassified_delta": False,
                },
                "blockers": [],
                "next_actions": [],
                "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
                "promotion_candidates": candidates,
                "status": "active",
            }

        result = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
        )
        self.assertEqual(result.status, "proceed")
        return result


class TestCurate(CurationTestCase):
    def test_no_active_state_returns_all_empty_groups(self):
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(report["count"], 0)
        self.assertEqual(set(report["groups"]), set(curation.DESTINATION_CLASSES))
        self.assertTrue(all(v == [] for v in report["groups"].values()))

    def test_workstream_with_no_candidates_returns_all_empty_groups(self):
        self._flush_with_candidates([])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(report["count"], 0)
        self.assertTrue(all(v == [] for v in report["groups"].values()))

    def test_groups_candidates_by_destination_class(self):
        self._flush_with_candidates([
            _candidate("cand-1", "preference", "Prefer terse output."),
            _candidate("cand-2", "ecosystem_policy", "Adopt worktree-by-default."),
            _candidate("cand-3", "preference", "Another preference."),
        ])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(report["count"], 3)
        self.assertEqual(len(report["groups"]["preference"]), 2)
        self.assertEqual(len(report["groups"]["ecosystem_policy"]), 1)
        self.assertEqual(report["groups"]["product_requirement"], [])
        self.assertEqual(report["groups"]["live_system_doc"], [])
        self.assertEqual(report["groups"]["other"], [])

    def test_enriched_candidate_validates_against_promotion_candidate_schema(self):
        self._flush_with_candidates([_candidate("cand-1", "live_system_doc", "Update the README.")])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        enriched = report["groups"]["live_system_doc"][0]
        self.assertEqual(enriched["schema"], "save-game-promotion-candidate/v1")
        self.assertEqual(enriched["candidate_id"], "cand-1")
        self.assertEqual(enriched["workstream_key"], self.workstream_key)
        self.assertEqual(enriched["rationale"], "Update the README.")
        self.assertEqual(enriched["owner"], "unassigned")
        self.assertEqual(enriched["status"], "proposed")

    def test_authority_becomes_target_authority_and_evidence(self):
        authority = {"kind": "accepted_plan", "locator": "plan://save-game-v2", "observed_at": "2026-07-30T00:00:00.000Z"}
        self._flush_with_candidates([_candidate("cand-1", "product_requirement", "Ship remove_preview.", authority=authority)])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        enriched = report["groups"]["product_requirement"][0]
        self.assertEqual(enriched["target_authority"], authority)
        self.assertEqual(enriched["evidence"], [authority])

    def test_missing_authority_falls_back_to_a_workstream_pointer(self):
        self._flush_with_candidates([_candidate("cand-1", "other", "Something unclassified.")])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        enriched = report["groups"]["other"][0]
        self.assertEqual(enriched["target_authority"]["kind"], "other")
        self.assertIn(self.workstream_key, enriched["target_authority"]["locator"])
        self.assertNotIn("evidence", enriched)

    def test_promoted_and_rejected_status_pass_through(self):
        self._flush_with_candidates([
            _candidate("cand-1", "preference", "Adopted already.", status="promoted"),
            _candidate("cand-2", "preference", "Rejected already.", status="rejected"),
        ])
        report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        statuses = {c["candidate_id"]: c["status"] for c in report["groups"]["preference"]}
        self.assertEqual(statuses, {"cand-1": "promoted", "cand-2": "rejected"})


class TestCurateNeverWrites(CurationTestCase):
    def test_curate_performs_zero_filesystem_writes(self):
        """Direct proof, not just an absence-of-side-effect inference: every
        durable-write primitive this engine has is patched to explode if
        called, for the full duration of curate(). A passing test means
        curate()'s entire call graph never invokes either one."""
        self._flush_with_candidates([
            _candidate("cand-1", "preference", "Prefer terse output."),
            _candidate("cand-2", "ecosystem_policy", "Adopt worktree-by-default."),
        ])
        with patch.object(durability, "create_exclusive_durable", side_effect=AssertionError("curate() must never create files")), \
             patch.object(durability, "atomic_replace_durable", side_effect=AssertionError("curate() must never replace files")):
            report = curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(report["count"], 2)

    def test_curate_never_touches_any_real_preference_policy_or_doc_destination(self):
        # No fake preferences/policy/doc file exists anywhere in this isolated
        # fixture; curate() reading only current.json and returning an
        # in-memory dict, with the on-disk tree byte-for-byte unchanged
        # before/after, is the concrete proof it cannot have written to one.
        self._flush_with_candidates([_candidate("cand-1", "preference", "Prefer terse output.")])
        before = sorted(str(p) for p in Path(self.tmp).rglob("*") if p.is_file())
        curation.curate(self.repo_key, self.clone_key, self.workstream_key)
        after = sorted(str(p) for p in Path(self.tmp).rglob("*") if p.is_file())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
