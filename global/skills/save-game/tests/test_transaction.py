"""Tests for the append-only recovery transaction: begin/finalize, in-lock CAS,
and deterministic crash-recovery classification (stdlib no-follow os-level
failure injection at each phase boundary — truncated/missing/corrupt/symlinked
evidence — per the plan's RECOVERY_BLOCKED/RECOVERY_CONFLICT rules)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import _support

from engine import canonical, durability, ids, identity as identity_mod, paths, transaction as tx
from engine.schemas_validate import SchemaValidationError

TASK_ID = "task-tx-test"


def _identity_for(repo: Path) -> identity_mod.RootIdentity:
    return identity_mod.resolve_root_identity(str(repo))


def _keys_for(identity: identity_mod.RootIdentity):
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    workstream_key = identity_mod.workstream_key_for(repo_key, clone_key, TASK_ID, identity)
    return repo_key, clone_key, workstream_key


def _candidate_builder(identity: identity_mod.RootIdentity, workstream_key: str, *, objective="Ship the thing.", next_desc="Write tests"):
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
            "next_actions": [{"description": next_desc}],
            "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
            "status": "active",
        }

    return build


class TransactionTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        self.identity = _identity_for(self.repo)
        self.repo_key, self.clone_key, self.workstream_key = _keys_for(self.identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _begin(self, **kwargs):
        builder = kwargs.pop("build_candidate_fn", None) or _candidate_builder(self.identity, self.workstream_key)
        return tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            build_candidate_fn=builder, identity=self.identity, **kwargs,
        )

    def _finalize_with_minimal_checkpoint(self, begin_result):
        checkpoint_id = ids.new_checkpoint_id()
        checkpoint_doc = {
            "schema": "save-game-checkpoint/v1",
            "checkpoint_id": checkpoint_id,
            "workstream_key": self.workstream_key,
            "client_id": "unknown",
            "created_at": ids.now_iso(),
            "expiry_class": "unresolved",
            "active_state_generation": begin_result.generation,
            "active_state_digest": begin_result.new_digest,
            "objective": "Ship the thing.",
            "scope_summary": "(none)",
            "done": [],
            "blockers": [],
            "next_actions": [],
            "compaction": {"status": "unknown", "pressure_source": "unknown"},
            "canonical_precedence_notice": "Live canonical sources override this checkpoint; it is an index, never authority.",
        }
        durability.create_exclusive_durable(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id),
            canonical.canonical_bytes(checkpoint_doc),
        )
        receipt_id = ids.new_receipt_id()
        return tx.finalize_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=begin_result.operation_id, checkpoint_id=checkpoint_id, receipt_id=receipt_id,
            new_digest=begin_result.new_digest, identity_at_start=self.identity,
        )


class TestBeginTransaction(TransactionTestCase):
    def test_first_flush_writes_prepared_and_replaces_current(self):
        result = self._begin()
        self.assertEqual(result.status, "proceed")
        self.assertEqual(result.old_digest, "none")
        self.assertIsNotNone(result.new_digest)
        self.assertEqual(result.generation, 1)

        prepared_path = paths.journal_operation_dir(
            self.repo_key, self.clone_key, self.workstream_key, result.operation_id
        ) / "prepared.json"
        self.assertTrue(prepared_path.is_file())

        current = tx.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current["current_digest"], result.new_digest)
        self.assertEqual(current["generation"], 1)

    def test_second_identical_flush_is_no_durable_delta(self):
        first = self._begin()
        self.assertEqual(first.status, "proceed")
        self._finalize_with_minimal_checkpoint(first)

        second = self._begin()
        self.assertEqual(second.status, "no_durable_delta")
        self.assertEqual(second.new_digest, first.new_digest)
        # No second prepared.json/operation should be created for a no-op flush.
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        op_dirs = [p for p in journal_dir.iterdir() if p.name != "quarantine"]
        self.assertEqual(len(op_dirs), 1)

    def test_changed_candidate_produces_new_generation_and_digest(self):
        first = self._begin()
        self._finalize_with_minimal_checkpoint(first)

        second = self._begin(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Ship a different thing."))
        self.assertEqual(second.status, "proceed")
        self.assertNotEqual(second.new_digest, first.new_digest)
        self.assertEqual(second.generation, 2)
        self.assertEqual(second.old_digest, first.new_digest)

    def test_stale_expected_digest_returns_recovery_required(self):
        result = self._begin(expected_current_digest="0" * 64)
        self.assertEqual(result.status, "recovery_required")

    def test_correct_expected_digest_after_a_save_proceeds(self):
        first = self._begin()
        self._finalize_with_minimal_checkpoint(first)
        second = self._begin(expected_current_digest=first.new_digest, build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Different."))
        self.assertEqual(second.status, "proceed")

    def test_privacy_gate_failure_blocks_before_any_durable_write(self):
        from unittest.mock import patch

        from engine import privacy

        with patch.object(privacy, "scan_and_redact_document", side_effect=privacy.PrivacyGateError("boom")):
            result = self._begin()
        self.assertEqual(result.status, "privacy_block")
        self.assertIsNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(journal_dir.is_dir())

    def test_invalid_candidate_raises_schema_validation_error(self):
        def bad_builder(_current_doc):
            doc = _candidate_builder(self.identity, self.workstream_key)(_current_doc)
            doc["objective"] = ""  # violates pattern "\S"
            return doc

        with self.assertRaises(SchemaValidationError):
            self._begin(build_candidate_fn=bad_builder)

    def test_a_builder_that_echoes_stale_volatile_fields_still_detects_no_delta(self):
        # Regression: a builder that naively does `dict(current_doc)` (copying
        # generation/current_digest/previous_digest/timestamps/privacy straight
        # through) must not corrupt NO_DURABLE_DELTA detection or reintroduce a
        # stale privacy classification as if it were new semantic content.
        first = self._begin()
        self.assertEqual(first.status, "proceed")
        self._finalize_with_minimal_checkpoint(first)

        def echoing_builder(current_doc):
            base = _candidate_builder(self.identity, self.workstream_key)(current_doc)
            return {**base, **current_doc}  # current_doc's stale fields win

        second = self._begin(build_candidate_fn=echoing_builder)
        self.assertEqual(second.status, "no_durable_delta")
        self.assertEqual(second.validated_candidate["privacy"]["classification"], "clean")


class TestCheckReconcileRequired(TransactionTestCase):
    def test_false_when_nothing_changed(self):
        self.assertFalse(tx.check_reconcile_required(self.identity))

    def test_true_after_a_new_commit_on_the_same_branch(self):
        (self.repo / "extra.txt").write_text("more\n")
        _support._git(self.repo, "add", ".")
        _support._git(self.repo, "commit", "-q", "-m", "second")
        self.assertTrue(tx.check_reconcile_required(self.identity))

    def test_true_after_a_branch_change(self):
        _support._git(self.repo, "checkout", "-q", "-b", "other-branch")
        self.assertTrue(tx.check_reconcile_required(self.identity))

    def test_finalize_transaction_accepts_a_precomputed_value_without_rechecking(self):
        result = self._begin()
        checkpoint_id = ids.new_checkpoint_id()
        checkpoint_doc = {
            "schema": "save-game-checkpoint/v1", "checkpoint_id": checkpoint_id, "workstream_key": self.workstream_key,
            "client_id": "unknown", "created_at": ids.now_iso(), "expiry_class": "unresolved",
            "active_state_generation": result.generation, "active_state_digest": result.new_digest,
            "objective": "Ship the thing.", "scope_summary": "(none)", "done": [], "blockers": [], "next_actions": [],
            "compaction": {"status": "unknown", "pressure_source": "unknown"},
            "canonical_precedence_notice": "Live canonical sources override this checkpoint; it is an index, never authority.",
        }
        durability.create_exclusive_durable(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id),
            canonical.canonical_bytes(checkpoint_doc),
        )
        finalized = tx.finalize_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=result.operation_id, checkpoint_id=checkpoint_id, receipt_id=ids.new_receipt_id(),
            new_digest=result.new_digest, identity_at_start=self.identity, reconcile_required=True,
        )
        # Live Git never actually moved; a precomputed True must still win over
        # finalize_transaction's own (otherwise-False) fresh recheck.
        self.assertTrue(finalized["reconcile_required"])


class TestPhaseFileWriters(TransactionTestCase):
    def test_write_prepared_validates_and_persists(self):
        doc = tx.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id="op-abc123", old_digest="none", new_digest="a" * 64,
            expected_generation=0, identity=self.identity, snapshot_digest="b" * 64,
        )
        self.assertEqual(doc["schema"], "save-game-journal-prepared/v1")
        path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, "op-abc123") / "prepared.json"
        self.assertEqual(json.loads(path.read_bytes()), doc)

    def test_write_aborted_is_idempotent(self):
        for _ in range(2):
            doc = tx.write_aborted(
                self.repo_key, self.clone_key, self.workstream_key,
                operation_id="op-def456", reason="stale_current_digest",
                old_digest="none", attempted_new_digest="c" * 64,
            )
        self.assertEqual(doc["reason"], "stale_current_digest")

    def test_write_finalized_is_idempotent(self):
        for _ in range(2):
            doc = tx.write_finalized(
                self.repo_key, self.clone_key, self.workstream_key,
                operation_id="op-ghi789", checkpoint_id="chk-ghi789", receipt_id="rcpt-ghi789",
                new_digest="d" * 64, reconcile_required=False,
            )
        self.assertEqual(doc["checkpoint_id"], "chk-ghi789")


class TestRecoveryClassification(TransactionTestCase):
    def _crash_after_prepared(self):
        """Simulate a crash between step 5 (prepared.json) and step 6 (atomic
        replace): current.json is never touched, so current digest == old_digest."""
        result = self._begin()
        self.assertEqual(result.status, "proceed")
        # Undo the atomic replace to reproduce the "prepared but current still
        # old" state a real mid-transaction crash would leave (begin_transaction
        # itself always completes the replace, so we roll it back by hand here
        # purely to construct the fixture for this test).
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        current_path.unlink()
        return result

    def test_prepared_with_stale_current_digest_is_aborted(self):
        result = self._crash_after_prepared()
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].operation_id, result.operation_id)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.ABORTED)
        aborted_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id) / "aborted.json"
        self.assertTrue(aborted_path.is_file())
        self.assertIsNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))

    def test_recovery_is_idempotent_on_already_aborted(self):
        self._crash_after_prepared()
        first = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        second = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(first[0].outcome, tx.RecoveryOutcome.ABORTED)
        self.assertEqual(second[0].outcome, tx.RecoveryOutcome.NONE)

    def test_prepared_with_new_current_digest_reconstructs_finalized(self):
        # Crash between step 6 (atomic replace succeeded) and step 9 (finalized.json):
        # current.json already reflects new_digest; nothing else to undo.
        result = self._begin()
        self.assertEqual(result.status, "proceed")

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.RECONSTRUCTED)

        finalized_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id) / "finalized.json"
        self.assertTrue(finalized_path.is_file())
        finalized = json.loads(finalized_path.read_bytes())
        self.assertEqual(finalized["new_digest"], result.new_digest)
        self.assertTrue(finalized["reconcile_required"])

        checkpoint_path = paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, finalized["checkpoint_id"])
        self.assertTrue(checkpoint_path.is_file())
        receipt_path = paths.receipt_path(self.repo_key, self.clone_key, self.workstream_key, finalized["receipt_id"])
        self.assertTrue(receipt_path.is_file())

        # Current state itself must be untouched by reconstruction.
        current = tx.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current["current_digest"], result.new_digest)

    def test_reconstruction_reuses_existing_checkpoint_if_already_present(self):
        result = self._begin()
        checkpoint_id = tx._checkpoint_id_for(result.operation_id)
        checkpoint_doc = {
            "schema": "save-game-checkpoint/v1",
            "checkpoint_id": checkpoint_id,
            "workstream_key": self.workstream_key,
            "client_id": "cursor",
            "created_at": ids.now_iso(),
            "expiry_class": "unresolved",
            "active_state_generation": 1,
            "active_state_digest": result.new_digest,
            "objective": "Ship the thing.",
            "scope_summary": "(none)",
            "done": [],
            "blockers": [],
            "next_actions": [],
            "compaction": {"status": "unknown", "pressure_source": "unknown"},
            "canonical_precedence_notice": "Live canonical sources override this checkpoint; it is an index, never authority.",
        }
        durability.create_exclusive_durable(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id),
            canonical.canonical_bytes(checkpoint_doc),
        )
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.RECONSTRUCTED)
        finalized_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id) / "finalized.json"
        finalized = json.loads(finalized_path.read_bytes())
        self.assertEqual(finalized["checkpoint_id"], checkpoint_id)
        # The pre-existing checkpoint's own client_id must survive untouched
        # (proves reconstruction reused it rather than overwriting).
        reused = json.loads(
            paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, checkpoint_id).read_bytes()
        )
        self.assertEqual(reused["client_id"], "cursor")

    def test_current_digest_matching_neither_old_nor_new_is_conflict(self):
        result = self._begin()
        # Simulate an impossible-to-reconcile state: hand-write a bogus prepared
        # record whose declared old/new digests match neither "none" nor the
        # live current digest, in a second fabricated operation directory.
        bogus_op = "op-bogus00001"
        tx.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=bogus_op, old_digest="e" * 64, new_digest="f" * 64,
            expected_generation=5, identity=self.identity, snapshot_digest="a" * 64,
        )
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        by_id = {r.operation_id: r for r in records}
        self.assertEqual(by_id[bogus_op].outcome, tx.RecoveryOutcome.CONFLICT)
        # Conflicting evidence must never be auto-resolved/overwritten.
        aborted = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, bogus_op) / "aborted.json"
        finalized = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, bogus_op) / "finalized.json"
        self.assertFalse(aborted.exists())
        self.assertFalse(finalized.exists())

    def test_truncated_prepared_json_is_recovery_blocked(self):
        result = self._begin()
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        current_path.unlink()
        prepared_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id) / "prepared.json"
        # Truncate in place (not through durability.* — this specifically
        # simulates disk corruption a crash could leave behind).
        os.chmod(prepared_path, 0o600)
        with open(prepared_path, "wb") as fh:
            fh.write(b'{"schema": "save-game-journal-prep')  # deliberately truncated JSON

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.BLOCKED)
        # Evidence must be preserved untouched, never auto-quarantined.
        self.assertTrue(prepared_path.is_file())
        self.assertEqual(prepared_path.read_bytes(), b'{"schema": "save-game-journal-prep')

    def test_missing_required_field_in_prepared_json_is_recovery_blocked(self):
        result = self._begin()
        prepared_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id) / "prepared.json"
        doc = json.loads(prepared_path.read_bytes())
        del doc["new_digest"]
        os.chmod(prepared_path, 0o600)
        prepared_path.write_bytes(canonical.canonical_bytes(doc))

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.BLOCKED)

    def test_unknown_extra_file_in_operation_dir_is_recovery_blocked(self):
        result = self._begin()
        op_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id)
        (op_dir / "mystery.json").write_text("{}")

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.BLOCKED)

    def test_symlinked_prepared_json_is_recovery_blocked(self):
        result = self._begin()
        op_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id)
        prepared_path = op_dir / "prepared.json"
        real_target = op_dir / "prepared.real.json"
        prepared_path.rename(real_target)
        os.symlink(real_target, prepared_path)

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.BLOCKED)

    def test_symlinked_operation_directory_is_recovery_blocked(self):
        result = self._begin()
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        op_dir = journal_dir / result.operation_id
        real_dir = journal_dir / f"{result.operation_id}-real"
        op_dir.rename(real_dir)
        os.symlink(real_dir, op_dir)

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        blocked = [r for r in records if r.operation_id == result.operation_id]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].outcome, tx.RecoveryOutcome.BLOCKED)

    def test_no_pending_operations_returns_empty_list(self):
        self.assertEqual(tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key), [])

    def test_already_finalized_operation_is_left_alone(self):
        result = self._begin()
        self._finalize_with_minimal_checkpoint(result)
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.ALREADY_FINALIZED)


class TestQuarantine(TransactionTestCase):
    def test_quarantine_moves_operation_dir_and_excludes_it_from_recovery(self):
        result = self._begin()
        op_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, result.operation_id)
        (op_dir / "mystery.json").write_text("{}")  # force BLOCKED first
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(records[0].outcome, tx.RecoveryOutcome.BLOCKED)

        dst = tx.quarantine_operation(self.repo_key, self.clone_key, self.workstream_key, result.operation_id)
        self.assertTrue(Path(dst).is_dir())
        self.assertFalse(op_dir.exists())
        self.assertEqual(tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key), [])


class TestBeginTransactionEndToEnd(TransactionTestCase):
    def test_flush_crash_recover_flush_again_round_trip(self):
        first = self._begin()
        self._finalize_with_minimal_checkpoint(first)

        second = self._begin(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Second save."))
        self.assertEqual(second.status, "proceed")
        # Crash: never finalize. Simulate process death right after the replace.

        third = self._begin(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Third save intent."))
        self.assertEqual(third.status, "recovery_required")

        # `third`'s call already ran recovery internally (and reconstructed the
        # missing finalized.json as a side effect) before reporting
        # recovery_required, so a fresh explicit call now sees the settled,
        # idempotent ALREADY_FINALIZED state rather than RECONSTRUCTED again.
        finalized_path = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, second.operation_id) / "finalized.json"
        self.assertTrue(finalized_path.is_file())
        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertTrue(all(r.outcome == tx.RecoveryOutcome.ALREADY_FINALIZED for r in records))

        fourth = self._begin(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Third save intent."))
        self.assertEqual(fourth.status, "proceed")
        self.assertEqual(fourth.old_digest, second.new_digest)


if __name__ == "__main__":
    unittest.main()
