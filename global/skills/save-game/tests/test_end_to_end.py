"""Genuine end-to-end test spanning all four contracts: Flush -> Index ->
simulate a crash mid-transaction (prepared.json written, current.json replaced,
but the process dies before checkpoint/receipt/finalized.json exist) ->
recovery (via the next Flush's own internal recovery pass) -> Reconcile,
asserting the final state is correct at every step."""

from __future__ import annotations

import unittest

import _support

from engine import flush, identity as identity_mod, index, paths, reconcile, transaction

TASK_ID = "task-e2e"


def _builder(identity, workstream_key, objective):
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
            "next_actions": [{"description": f"continue: {objective}"}],
            "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
            "status": "active",
        }

    return build


class TestFlushIndexCrashRecoverReconcile(unittest.TestCase):
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

    def test_full_round_trip(self):
        # 1. Flush #1: a normal, complete save.
        receipt1 = flush.run_flush(
            self.repo_key, self.clone_key, self.workstream_key,
            identity=self.identity, build_candidate_fn=_builder(self.identity, self.workstream_key, "Phase A: lay the foundation."),
        )
        self.assertEqual(receipt1["status"], "SAVED_PRIVATE_UNADOPTED")
        current1 = transaction.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current1["generation"], 1)

        # 2. Index: the checkpoint Flush #1 created resolves cleanly.
        checkpoint1, ambiguous1 = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous1)
        self.assertEqual(checkpoint1["checkpoint_id"], receipt1["checkpoint_id"])
        self.assertEqual(checkpoint1["active_state_generation"], 1)

        # 3. Simulate a crash mid-transaction for Flush #2: begin_transaction
        # completes through the atomic replace of current.json (steps 1-6) but
        # the process dies before Index/finalize (steps 7-9) ever run — the
        # exact gap this test's brief calls "crash mid-transaction".
        begin2 = transaction.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            build_candidate_fn=_builder(self.identity, self.workstream_key, "Phase B: never finalized."),
            identity=self.identity,
        )
        self.assertEqual(begin2.status, "proceed")
        current_mid_crash = transaction.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current_mid_crash["generation"], 2)
        self.assertEqual(current_mid_crash["objective"], "Phase B: never finalized.")
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        crashed_op_dir = journal_dir / begin2.operation_id
        self.assertTrue((crashed_op_dir / "prepared.json").is_file())
        self.assertFalse((crashed_op_dir / "finalized.json").exists())

        # 4. Recovery: the NEXT Flush call's own internal recovery pass finds
        # the crashed operation (current digest == new_digest, i.e. the replace
        # DID succeed) and reconstructs the missing checkpoint/receipt/finalized
        # records before reporting RECOVERY_REQUIRED — it must not silently
        # layer a fresh mutation on top of unreconciled crash evidence.
        receipt_recovery = flush.run_flush(
            self.repo_key, self.clone_key, self.workstream_key,
            identity=self.identity, build_candidate_fn=_builder(self.identity, self.workstream_key, "Phase C: the retry."),
        )
        self.assertEqual(receipt_recovery["status"], "RECOVERY_REQUIRED")
        self.assertTrue((crashed_op_dir / "finalized.json").is_file())
        # Recovery must never touch current.json itself.
        current_after_recovery = transaction.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current_after_recovery, current_mid_crash)

        # 5. Reconcile right after recovery: root/ref/HEAD still matches (git
        # never moved), and the reconstructed checkpoint now matches current.
        reconcile_receipt = reconcile.run_reconcile(
            self.repo_key, self.clone_key, self.workstream_key, identity=self.identity, triggers=["incomplete_transaction"],
        )
        by_claim = {c["claim"]: c["result"] for c in reconcile_receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "MATCH")
        self.assertEqual(by_claim["active_state_vs_checkpoint_digest"], "MATCH")
        self.assertEqual(reconcile_receipt["goal"], "Phase B: never finalized.")
        self.assertNotIn({"claim": "checkpoint_resolution", "result": "CONFLICT"}, reconcile_receipt["classifications"])

        # 6. Now that recovery is settled, retrying the SAME save succeeds for real.
        receipt3 = flush.run_flush(
            self.repo_key, self.clone_key, self.workstream_key,
            identity=self.identity, build_candidate_fn=_builder(self.identity, self.workstream_key, "Phase C: the retry."),
        )
        self.assertEqual(receipt3["status"], "SAVED_PRIVATE_UNADOPTED")
        current3 = transaction.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current3["generation"], 3)
        self.assertEqual(current3["objective"], "Phase C: the retry.")

        # 7. Index resolves to the newest checkpoint; a final Reconcile is clean.
        checkpoint3, ambiguous3 = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous3)
        self.assertEqual(checkpoint3["active_state_generation"], 3)
        self.assertEqual(checkpoint3["checkpoint_id"], receipt3["checkpoint_id"])

        final_reconcile = reconcile.run_reconcile(
            self.repo_key, self.clone_key, self.workstream_key, identity=self.identity, triggers=["resume"],
        )
        final_by_claim = {c["claim"]: c["result"] for c in final_reconcile["classifications"]}
        self.assertEqual(final_by_claim["root_ref_head"], "MATCH")
        self.assertEqual(final_by_claim["active_state_vs_checkpoint_digest"], "MATCH")
        self.assertEqual(final_reconcile["goal"], "Phase C: the retry.")
        self.assertFalse(final_reconcile["blockers"])


if __name__ == "__main__":
    unittest.main()
