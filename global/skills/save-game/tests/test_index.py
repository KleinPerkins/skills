"""Tests for the Index contract: building a schema-valid checkpoint from active
state, and resolving the current checkpoint by the enumeration rule (max
embedded active_state_generation; an unresolved tie is CHECKPOINT_AMBIGUOUS)."""

from __future__ import annotations

import unittest

import _support

from engine import canonical, durability, identity as identity_mod, ids, index, paths, transaction

TASK_ID = "task-index-test"


def _active_state(*, generation=1, digest="a" * 64, objective="Ship the thing.", workstream_key="b" * 64):
    return {
        "schema": "save-game-current/v1",
        "task_id": TASK_ID,
        "workstream_key": workstream_key,
        "root": {"ref_kind": "branch", "observed_head": "c" * 40, "operation_marker": "none", "branch": "main"},
        "generation": generation,
        "current_digest": digest,
        "created_at": ids.now_iso(),
        "updated_at": ids.now_iso(),
        "objective": objective,
        "scope": {"in_scope": [{"summary": "Build the storage core."}], "non_scope": [], "deferred": []},
        "hygiene": {
            "transactions_finalized": True,
            "temp_artifacts_clear": False,
            "repo_status_observed": True,
            "required_checks_run": True,
            "unclassified_delta": False,
        },
        "blockers": [{"description": "Waiting on operator sign-off.", "kind": "operator_decision"}],
        "next_actions": [{"description": "Write tests"}],
        "marginal_scope_budget": {"consumed_minutes": 5, "estimate_source": "agent_estimated"},
        "privacy": {"classification": "clean", "scanner_ruleset_version": "v1"},
        "status": "active",
    }


class TestBuildCheckpoint(unittest.TestCase):
    def test_builds_schema_valid_minimal_checkpoint(self):
        doc = index.build_checkpoint(_active_state(), checkpoint_id="chk-abc123", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertEqual(doc["schema"], "save-game-checkpoint/v1")
        self.assertEqual(doc["checkpoint_id"], "chk-abc123")
        self.assertEqual(doc["expiry_class"], "unresolved")
        self.assertEqual(doc["active_state_generation"], 1)
        self.assertEqual(doc["active_state_digest"], "a" * 64)
        self.assertEqual(doc["canonical_precedence_notice"], "Live canonical sources override this checkpoint; it is an index, never authority.")
        self.assertEqual(doc["done"], [])

    def test_unknown_client_id_falls_back_to_unknown(self):
        doc = index.build_checkpoint(_active_state(), checkpoint_id="chk-x", compaction={"status": "unknown", "pressure_source": "unknown"}, client_id="not-a-real-client")
        self.assertEqual(doc["client_id"], "unknown")

    def test_valid_client_id_is_preserved(self):
        doc = index.build_checkpoint(_active_state(), checkpoint_id="chk-y", compaction={"status": "unknown", "pressure_source": "unknown"}, client_id="cursor")
        self.assertEqual(doc["client_id"], "cursor")

    def test_hygiene_summary_reports_only_bad_flags(self):
        doc = index.build_checkpoint(_active_state(), checkpoint_id="chk-z", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertIn("temp_artifacts_clear", doc["hygiene_summary"])
        self.assertNotIn("transactions_finalized", doc["hygiene_summary"])

    def test_all_hygiene_flags_clear_yields_clear_summary_or_no_field(self):
        state = _active_state()
        state["hygiene"] = {
            "transactions_finalized": True, "temp_artifacts_clear": True,
            "repo_status_observed": True, "required_checks_run": True, "unclassified_delta": False,
        }
        doc = index.build_checkpoint(state, checkpoint_id="chk-clear", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertEqual(doc.get("hygiene_summary"), "hygiene clear")

    def test_unclassified_delta_true_is_reported_as_bad(self):
        state = _active_state()
        state["hygiene"]["unclassified_delta"] = True
        doc = index.build_checkpoint(state, checkpoint_id="chk-delta", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertIn("unclassified_delta", doc["hygiene_summary"])

    def test_long_objective_is_truncated_to_200_chars(self):
        state = _active_state(objective="x" * 500)
        doc = index.build_checkpoint(state, checkpoint_id="chk-long", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertLessEqual(len(doc["objective"]), 200)

    def test_blockers_and_next_actions_are_capped_and_truncated(self):
        state = _active_state()
        state["blockers"] = [{"description": "d" * 300, "kind": "operator_decision"} for _ in range(10)]
        state["next_actions"] = [{"description": "n" * 300} for _ in range(10)]
        doc = index.build_checkpoint(state, checkpoint_id="chk-cap", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertLessEqual(len(doc["blockers"]), 3)
        self.assertLessEqual(len(doc["next_actions"]), 3)
        self.assertLessEqual(len(doc["blockers"][0]["summary"]), 150)
        self.assertLessEqual(len(doc["next_actions"][0]["description"]), 150)

    def test_authority_pointers_collected_from_plan_pointer_and_accepted_decisions(self):
        state = _active_state()
        authority = {"kind": "accepted_plan", "locator": "plans/foo.md", "observed_at": ids.now_iso()}
        state["plan_pointer"] = {"authority": authority}
        state["decisions"] = [
            {"decision_id": "dec-1", "statement": "Use SHA-256.", "status": "accepted", "authority": authority, "revision": "r1"},
            {"decision_id": "dec-2", "statement": "Rejected idea.", "status": "rejected", "authority": authority, "revision": "r1"},
        ]
        doc = index.build_checkpoint(state, checkpoint_id="chk-auth", compaction={"status": "unknown", "pressure_source": "unknown"})
        self.assertEqual(len(doc["authority_pointers"]), 2)  # plan_pointer + the one accepted decision, not the rejected one

    def test_compaction_field_is_passed_through(self):
        compaction = {"status": "recommend_compaction", "pressure_source": "client_metric", "pressure_percent": 65}
        doc = index.build_checkpoint(_active_state(), checkpoint_id="chk-comp", compaction=compaction)
        self.assertEqual(doc["compaction"], compaction)


class IndexResolutionTestCase(unittest.TestCase):
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

    def _finalize_checkpoint(self, generation: int, digest: str) -> str:
        """Fabricates one complete, schema-valid finalized operation (prepared +
        checkpoint + receipt + finalized) directly, without going through Flush,
        so resolution can be tested in isolation from the transaction layer."""
        operation_id = ids.new_operation_id()
        checkpoint_id = ids.new_checkpoint_id()
        receipt_id = ids.new_receipt_id()

        transaction.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=operation_id, old_digest="none", new_digest=digest,
            expected_generation=generation - 1, identity=self.identity, snapshot_digest="f" * 64,
        )
        checkpoint_doc = index.build_checkpoint(
            _active_state(generation=generation, digest=digest, workstream_key=self.workstream_key),
            checkpoint_id=checkpoint_id, compaction={"status": "unknown", "pressure_source": "unknown"},
        )
        durability.create_exclusive_durable(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id),
            canonical.canonical_bytes(checkpoint_doc),
        )
        transaction.write_finalized(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=operation_id, checkpoint_id=checkpoint_id, receipt_id=receipt_id,
            new_digest=digest, reconcile_required=False,
        )
        return checkpoint_id


class TestResolveCheckpoint(IndexResolutionTestCase):
    def test_no_journal_dir_returns_none_not_ambiguous(self):
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertIsNone(checkpoint)
        self.assertFalse(ambiguous)

    def test_single_finalized_checkpoint_resolves_cleanly(self):
        checkpoint_id = self._finalize_checkpoint(generation=1, digest="1" * 64)
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous)
        self.assertEqual(checkpoint["checkpoint_id"], checkpoint_id)

    def test_selects_maximum_generation_among_several(self):
        self._finalize_checkpoint(generation=1, digest="1" * 64)
        self._finalize_checkpoint(generation=3, digest="3" * 64)
        second_id = self._finalize_checkpoint(generation=2, digest="2" * 64)
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous)
        self.assertEqual(checkpoint["active_state_generation"], 3)
        self.assertNotEqual(checkpoint["checkpoint_id"], second_id)

    def test_tie_at_max_generation_is_ambiguous(self):
        self._finalize_checkpoint(generation=1, digest="1" * 64)
        # Two DIFFERENT operations both landing on generation 2 (e.g. two
        # divergent recoveries) is the pathological tie this test fabricates.
        self._finalize_checkpoint(generation=2, digest="2" * 64)
        self._finalize_checkpoint(generation=2, digest="9" * 64)
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertTrue(ambiguous)
        self.assertIsNotNone(checkpoint)  # a bounded example, not the resolved answer

    def test_malformed_finalized_record_is_skipped_not_fatal(self):
        self._finalize_checkpoint(generation=1, digest="1" * 64)
        bogus_op_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, "op-bogus000001")
        durability.ensure_private_dir(bogus_op_dir)
        durability.create_exclusive_durable(bogus_op_dir / "finalized.json", b'{"not": "valid"}')

        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous)
        self.assertEqual(checkpoint["active_state_generation"], 1)

    def test_finalized_pointing_to_missing_checkpoint_file_is_skipped(self):
        self._finalize_checkpoint(generation=1, digest="1" * 64)
        op_id = ids.new_operation_id()
        transaction.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=op_id, old_digest="1" * 64, new_digest="2" * 64,
            expected_generation=1, identity=self.identity, snapshot_digest="e" * 64,
        )
        transaction.write_finalized(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=op_id, checkpoint_id="chk-does-not-exist", receipt_id="rcpt-does-not-exist",
            new_digest="2" * 64, reconcile_required=False,
        )
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous)
        self.assertEqual(checkpoint["active_state_generation"], 1)

    def test_quarantine_subdir_is_never_enumerated(self):
        checkpoint_id = self._finalize_checkpoint(generation=1, digest="1" * 64)
        quarantine_dir = paths.journal_quarantine_dir(self.repo_key, self.clone_key, self.workstream_key)
        durability.ensure_private_dir(quarantine_dir)
        checkpoint, ambiguous = index.resolve_checkpoint(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(ambiguous)
        self.assertEqual(checkpoint["checkpoint_id"], checkpoint_id)


if __name__ == "__main__":
    unittest.main()
