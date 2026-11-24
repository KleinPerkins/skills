"""Tests for the Reconcile contract: bounded live-source reads, MATCH/STALE/
CONFLICT classification, CHECKPOINT_AMBIGUOUS surfacing, and the v2-hardened
persistence rule — Reconcile itself never mutates current.json or creates a
checkpoint (a purely read-only resume never triggers a Flush)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import _support

from engine import canonical, durability, flush, identity as identity_mod, index, paths, reconcile, transaction

TASK_ID = "task-reconcile-test"


def _candidate_builder(identity, workstream_key, *, objective="Ship the thing."):
    def build(_current_doc):
        return {
            "schema": "save-game-current/v1",
            "task_id": TASK_ID,
            "workstream_key": workstream_key,
            "root": identity_mod.root_snapshot_dict(identity),
            "objective": objective,
            "scope": {"in_scope": [], "non_scope": [], "deferred": []},
            "hygiene": {
                "transactions_finalized": True,
                "temp_artifacts_clear": True,
                "repo_status_observed": True,
                "required_checks_run": True,
                "unclassified_delta": False,
            },
            "blockers": [],
            "next_actions": [{"description": "Write tests"}],
            "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
            "status": "active",
        }

    return build


class ReconcileTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        self.identity = identity_mod.resolve_root_identity(str(self.repo))
        self.repo_key = identity_mod.repo_key_for(self.identity)
        self.clone_key = identity_mod.clone_key_for(self.identity)
        self.workstream_key = identity_mod.workstream_key_for(self.repo_key, self.clone_key, TASK_ID, self.identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _flush(self, **kwargs):
        builder = kwargs.pop("build_candidate_fn", None) or _candidate_builder(self.identity, self.workstream_key)
        return flush.run_flush(
            self.repo_key, self.clone_key, self.workstream_key,
            identity=self.identity, build_candidate_fn=builder, **kwargs,
        )

    def _reconcile(self, identity=None, triggers=None):
        return reconcile.run_reconcile(
            self.repo_key, self.clone_key, self.workstream_key,
            identity=identity or self.identity, triggers=triggers or ["resume"],
        )


class TestBasicShapeAndTriggers(ReconcileTestCase):
    def test_fresh_workstream_reconcile_is_schema_valid_and_read_only(self):
        receipt = self._reconcile()
        self.assertEqual(receipt["schema"], "save-game-reconcile-receipt/v1")
        self.assertTrue(receipt["negative_claims"])
        self.assertIsNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(journal_dir.is_dir())  # no checkpoint/operation was created by a read-only Reconcile

    def test_invalid_trigger_falls_back_to_resume(self):
        receipt = self._reconcile(triggers=["not_a_real_trigger"])
        self.assertEqual(receipt["triggers"], ["resume"])

    def test_valid_triggers_are_preserved(self):
        receipt = self._reconcile(triggers=["new_chat", "root_change"])
        self.assertEqual(receipt["triggers"], ["new_chat", "root_change"])

    def test_reconcile_after_a_flush_never_creates_a_second_checkpoint(self):
        self._flush()
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        before = {p.name for p in journal_dir.iterdir()}
        self._reconcile()
        after = {p.name for p in journal_dir.iterdir()}
        self.assertEqual(before, after)


class TestClassification(ReconcileTestCase):
    def test_root_ref_head_is_unknown_before_any_flush(self):
        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "UNKNOWN")

    def test_root_ref_head_matches_right_after_a_flush(self):
        self._flush()
        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "MATCH")

    def test_digest_vs_checkpoint_matches_right_after_a_flush(self):
        self._flush()
        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["active_state_vs_checkpoint_digest"], "MATCH")

    def test_new_commit_on_same_branch_is_advanced(self):
        self._flush()
        (self.repo / "file2.txt").write_text("more\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "second"], check=True)
        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "ADVANCED")
        self.assertIn("Refreshed", receipt["repairs"][0])

    def test_same_branch_rewind_or_divergence_is_stale(self):
        git = ["git", "-C", str(self.repo)]
        parent = self.identity.observed_head
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "saved tip"], check=True)
        self.identity = identity_mod.resolve_root_identity(str(self.repo))
        self._flush()
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        original = current_path.read_bytes()

        subprocess.run([*git, "update-ref", "refs/heads/main", parent, self.identity.observed_head], check=True)
        rewind = self._reconcile()
        self.assertIn({"claim": "root_ref_head", "result": "STALE"}, rewind["classifications"])
        self.assertEqual(current_path.read_bytes(), original)

        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "other tip"], check=True)
        divergent = self._reconcile()
        self.assertIn({"claim": "root_ref_head", "result": "STALE"}, divergent["classifications"])
        self.assertEqual(current_path.read_bytes(), original)

    def test_missing_saved_commit_is_unknown(self):
        current = {"root": {"branch": self.identity.branch, "observed_head": "f" * 40}}
        self.assertEqual(reconcile._classify_root(current, self.identity), "UNKNOWN")

    def test_shallow_history_cannot_prove_a_negative_ancestry_result(self):
        upstream = ["git", "-C", str(self.repo)]
        saved = self.identity.observed_head
        subprocess.run([*upstream, "commit", "-q", "--allow-empty", "-m", "descendant"], check=True)
        clone = self.tmp / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth=1", self.repo.as_uri(), str(clone)], check=True)
        local = ["git", "-C", str(clone)]
        subprocess.run([*local, "fetch", "-q", self.repo.as_uri(), f"{saved}:refs/heads/saved"], check=True)
        subprocess.run([*local, "cat-file", "-e", f"{saved}^{{commit}}"], check=True)
        fresh = identity_mod.resolve_root_identity(str(clone))
        current = {"root": {"branch": fresh.branch, "observed_head": saved}}
        self.assertEqual(reconcile._classify_root(current, fresh), "UNKNOWN")

    def test_branch_change_is_stale_not_advanced(self):
        self._flush()
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", "-b", "other-branch"], check=True)
        # Reconcile always re-resolves identity LIVE from physical_root itself
        # (never trusts a caller-supplied snapshot), so passing the original,
        # now-stale `self.identity` in is enough to prove that.
        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "STALE")

    def test_mid_merge_operation_marker_forces_stale_even_with_head_unchanged(self):
        """Plan verification-strategy gate: "Git behavior ... mid-merge/rebase/
        cherry-pick/revert/bisect ... branch/HEAD/status revalidation." HEAD and
        branch are UNCHANGED from the flush above -- only a live MERGE_HEAD marker
        appears -- proving `_classify_root` checks the operation marker itself and
        does not just diff branch/HEAD."""
        self._flush()
        git_dir = Path(self.identity.git_dir)
        (git_dir / "MERGE_HEAD").write_text("a" * 40 + "\n")
        try:
            receipt = self._reconcile()
        finally:
            (git_dir / "MERGE_HEAD").unlink()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "STALE")

    def test_checkpoint_ambiguity_surfaces_as_conflict_and_blocker(self):
        self._flush()
        # Fabricate a second, competing finalized checkpoint tied at the same
        # generation as the real one, to force the enumeration-rule tie.
        current = transaction.read_current(self.repo_key, self.clone_key, self.workstream_key)
        op_id = "op-competing001"
        transaction.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=op_id, old_digest="0" * 64, new_digest=current["current_digest"],
            expected_generation=0, identity=self.identity, snapshot_digest="a" * 64,
        )
        checkpoint_id = "chk-competing001"
        checkpoint_doc = index.build_checkpoint(current, checkpoint_id=checkpoint_id, compaction={"status": "unknown", "pressure_source": "unknown"})
        durability.create_exclusive_durable(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id),
            canonical.canonical_bytes(checkpoint_doc),
        )
        transaction.write_finalized(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=op_id, checkpoint_id=checkpoint_id, receipt_id="rcpt-competing001",
            new_digest=current["current_digest"], reconcile_required=False,
        )

        receipt = self._reconcile()
        by_claim = {c["claim"]: c["result"] for c in receipt["classifications"]}
        self.assertEqual(by_claim["checkpoint_resolution"], "CONFLICT")
        self.assertTrue(receipt["blockers"])


class TestGoalAndHygieneProjection(ReconcileTestCase):
    def test_goal_and_next_actions_reflect_current_active_state(self):
        self._flush(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Reconcile should see this."))
        receipt = self._reconcile()
        self.assertEqual(receipt["goal"], "Reconcile should see this.")
        self.assertEqual(receipt["next_actions"], [{"description": "Write tests"}])

    def test_goal_falls_back_to_placeholder_before_any_flush(self):
        receipt = self._reconcile()
        self.assertTrue(receipt["goal"])


if __name__ == "__main__":
    unittest.main()
