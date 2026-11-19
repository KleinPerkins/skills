"""Tests for the Flush contract: status-code mapping for all ten plan-defined
statuses, receipt shape/negative_claims, and that a successful Flush durably
creates its checkpoint and receipt before finalized.json points to both."""

from __future__ import annotations

import fcntl
import json
import os
import unittest
from unittest.mock import patch

import _support

from engine import canonical, durability, flush, ids, identity as identity_mod, paths, privacy, transaction

TASK_ID = "task-flush-test"


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


class FlushTestCase(unittest.TestCase):
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

    def _register(self):
        doc = {
            "schema": "save-game-registration/v1",
            "repo_key": self.repo_key,
            "clone_key": self.clone_key,
            "created_at": ids.now_iso(),
            "updated_at": ids.now_iso(),
            "enabled": True,
        }
        durability.create_exclusive_durable(paths.registration_path(self.repo_key, self.clone_key), canonical.canonical_bytes(doc))


class TestHappyPath(FlushTestCase):
    def test_first_flush_is_saved_private_unadopted_by_default(self):
        receipt = self._flush()
        self.assertEqual(receipt["status"], "SAVED_PRIVATE_UNADOPTED")
        self.assertIn("checkpoint_id", receipt)
        self.assertTrue(receipt["saved"])
        self.assertFalse(receipt["omitted"])
        self.assertTrue(receipt["negative_claims"])

    def test_flush_is_saved_once_registration_file_exists(self):
        self._register()
        receipt = self._flush()
        self.assertEqual(receipt["status"], "SAVED")

    def test_checkpoint_and_receipt_files_exist_and_finalized_points_to_both(self):
        receipt = self._flush()
        checkpoint_path = paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, receipt["checkpoint_id"])
        receipt_path = paths.receipt_path(self.repo_key, self.clone_key, self.workstream_key, receipt["receipt_id"])
        self.assertTrue(checkpoint_path.is_file())
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(json.loads(receipt_path.read_bytes()), receipt)

        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        op_dirs = [p for p in journal_dir.iterdir() if p.name != "quarantine"]
        self.assertEqual(len(op_dirs), 1)
        finalized = json.loads((op_dirs[0] / "finalized.json").read_bytes())
        self.assertEqual(finalized["checkpoint_id"], receipt["checkpoint_id"])
        self.assertEqual(finalized["receipt_id"], receipt["receipt_id"])

    def test_second_identical_flush_is_no_durable_delta(self):
        first = self._flush()
        second = self._flush()
        self.assertEqual(second["status"], "NO_DURABLE_DELTA")
        self.assertNotIn("checkpoint_id", second)
        self.assertNotEqual(first["receipt_id"], second["receipt_id"])

    def test_changed_objective_produces_a_new_saved_generation(self):
        first = self._flush()
        second = self._flush(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="A different objective."))
        self.assertIn(second["status"], ("SAVED", "SAVED_PRIVATE_UNADOPTED"))
        self.assertNotEqual(first["checkpoint_id"], second["checkpoint_id"])

    def test_compact_inputs_are_projected_into_the_checkpoint_compaction_field(self):
        receipt = self._flush(compact_inputs=None)
        checkpoint = json.loads(paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, receipt["checkpoint_id"]).read_bytes())
        self.assertEqual(checkpoint["compaction"], {"status": "unknown", "pressure_source": "unknown"})


class TestStatusCodes(FlushTestCase):
    def test_authority_conflict_short_circuits_before_any_write(self):
        receipt = self._flush(authority_conflict=True)
        self.assertEqual(receipt["status"], "AUTHORITY_CONFLICT")
        self.assertIsNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(journal_dir.is_dir())

    def test_unsupported_environment_maps_correctly(self):
        with patch.object(durability, "assert_environment_safe", side_effect=durability.UnsupportedEnvironmentError("nope")):
            receipt = self._flush()
        self.assertEqual(receipt["status"], "UNSUPPORTED_ENVIRONMENT")

    def test_lock_busy_when_workstream_lock_already_held(self):
        lock_path = paths.lock_path(self.workstream_key)
        durability.ensure_private_dir(lock_path.parent)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, durability.FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            receipt = self._flush(lock_timeout=0.2)
            self.assertEqual(receipt["status"], "LOCK_BUSY")
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_privacy_block_maps_correctly_and_writes_nothing(self):
        with patch.object(privacy, "scan_and_redact_document", side_effect=privacy.PrivacyGateError("boom")):
            receipt = self._flush()
        self.assertEqual(receipt["status"], "PRIVACY_BLOCK")
        self.assertFalse(receipt["reconciliation_required"])
        self.assertIsNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))

    def test_stale_expected_digest_is_recovery_required(self):
        receipt = self._flush(expected_current_digest="0" * 64)
        self.assertEqual(receipt["status"], "RECOVERY_REQUIRED")
        self.assertTrue(receipt["reconciliation_required"])

    def test_recovery_conflict_maps_correctly(self):
        self._flush()
        bogus_op = "op-bogus00001"
        transaction.write_prepared(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=bogus_op, old_digest="e" * 64, new_digest="f" * 64,
            expected_generation=5, identity=self.identity, snapshot_digest="a" * 64,
        )
        receipt = self._flush(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Something else."))
        self.assertEqual(receipt["status"], "RECOVERY_CONFLICT")
        self.assertTrue(receipt["reconciliation_required"])

    def test_recovery_blocked_maps_correctly_and_preserves_evidence(self):
        self._flush()
        # The operation_id isn't in the receipt; fetch the one existing operation directly.
        journal_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        op_dirs = [p for p in journal_dir.iterdir() if p.name != "quarantine"]
        self.assertEqual(len(op_dirs), 1)
        (op_dirs[0] / "mystery.json").write_text("{}")

        receipt = self._flush(build_candidate_fn=_candidate_builder(self.identity, self.workstream_key, objective="Yet another objective."))
        self.assertEqual(receipt["status"], "RECOVERY_BLOCKED")
        self.assertTrue((op_dirs[0] / "mystery.json").is_file())  # evidence preserved untouched


class TestNegativeClaims(FlushTestCase):
    def test_every_status_carries_at_least_one_negative_claim(self):
        receipts = [
            self._flush(authority_conflict=True),
        ]
        with patch.object(durability, "assert_environment_safe", side_effect=durability.UnsupportedEnvironmentError("x")):
            receipts.append(self._flush())
        receipts.append(self._flush())  # SAVED_PRIVATE_UNADOPTED
        receipts.append(self._flush())  # NO_DURABLE_DELTA
        for receipt in receipts:
            self.assertTrue(receipt["negative_claims"])
            for claim in receipt["negative_claims"]:
                self.assertLessEqual(len(claim), 150)
                self.assertTrue(claim.strip())


if __name__ == "__main__":
    unittest.main()
