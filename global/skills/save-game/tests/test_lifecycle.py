"""Tests for engine.lifecycle: adoption, read-only retention status, safe GC
(crash-resumable, tombstoned, deletions gated at >= 7 days from CREATION),
archive, remove preview/execute, and uninstall preview/execute."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _support

from engine import canonical, durability, ids, identity as identity_mod, lifecycle, paths, transaction as tx

TASK_ID = "task-lifecycle-test"


def _identity_for(repo: Path) -> identity_mod.RootIdentity:
    return identity_mod.resolve_root_identity(str(repo))


def _keys_for(identity: identity_mod.RootIdentity):
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    workstream_key = identity_mod.workstream_key_for(repo_key, clone_key, TASK_ID, identity)
    return repo_key, clone_key, workstream_key


def _snapshot_tree(root: Path, *, exclude_top_dirs: tuple = ()) -> dict:
    """Content-hash of every file under `root`, for asserting a call made ZERO
    durable changes (additions, deletions, or in-place edits). `exclude_top_dirs`
    excludes e.g. `locks/` -- `lock.workstream_lock`'s PID bookkeeping file is
    diagnostics-only (per lock.py's own docstring: "never the identity/authority
    boundary") and is expected to appear the first time any call acquires a
    workstream's lock, independent of whether that call did anything else."""
    if not root.is_dir():
        return {}
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] in exclude_top_dirs:
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _minimal_candidate(workstream_key, identity, *, objective="Ship the thing.", status="active", promotion_candidates=None, hygiene=None):
    doc = {
        "schema": "save-game-current/v1",
        "task_id": TASK_ID,
        "workstream_key": workstream_key,
        "root": identity_mod.root_snapshot_dict(identity),
        "objective": objective,
        "scope": {"in_scope": [], "non_scope": [], "deferred": []},
        "hygiene": hygiene or {
            "transactions_finalized": True,
            "temp_artifacts_clear": True,
            "repo_status_observed": True,
            "required_checks_run": True,
            "unclassified_delta": False,
        },
        "blockers": [],
        "next_actions": [],
        "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
        "status": status,
    }
    if promotion_candidates is not None:
        doc["promotion_candidates"] = promotion_candidates
    return doc


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        self.identity = _identity_for(self.repo)
        self.repo_key, self.clone_key, self.workstream_key = _keys_for(self.identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _flush(self, **overrides):
        """One real, finalized Flush -- the minimum fixture a retention/GC/
        archive test needs for a real journal + checkpoint + current.json."""
        def build(_current_doc):
            return _minimal_candidate(self.workstream_key, self.identity, **overrides)

        result = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            build_candidate_fn=build, identity=self.identity,
        )
        self.assertIn(result.status, ("proceed", "no_durable_delta"))
        if result.status == "no_durable_delta":
            return result
        checkpoint_id = ids.new_checkpoint_id()
        checkpoint_doc = {
            "schema": "save-game-checkpoint/v1",
            "checkpoint_id": checkpoint_id,
            "workstream_key": self.workstream_key,
            "client_id": "unknown",
            "created_at": ids.now_iso(),
            "expiry_class": "unresolved",
            "active_state_generation": result.generation,
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
        tx.finalize_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            operation_id=result.operation_id, checkpoint_id=checkpoint_id, receipt_id=ids.new_receipt_id(),
            new_digest=result.new_digest, identity_at_start=self.identity,
        )
        return result

    def _make_abandoned_temp_file(self, *, age_days: float) -> Path:
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        durability.ensure_private_dir(current_path.parent)
        temp_path = current_path.parent / f".{current_path.name}.tmp.{os.getpid()}.{os.urandom(6).hex()}"
        temp_path.write_bytes(b'{"leftover": true}')
        os.chmod(temp_path, 0o600)
        old_time = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
        os.utime(temp_path, (old_time, old_time))
        return temp_path


class TestAdoption(LifecycleTestCase):
    def test_unconfigured_before_first_adopt(self):
        status = lifecycle.adoption_status(self.repo_key, self.clone_key)
        self.assertEqual(status["case"], "unconfigured")
        self.assertFalse(status["adopted"])
        self.assertFalse(lifecycle.is_adopted(self.repo_key, self.clone_key))
        self.assertIsNone(lifecycle.read_registration(self.repo_key, self.clone_key))

    def test_adopt_preview_is_schema_valid_and_has_no_side_effects(self):
        preview = lifecycle.adopt_preview(self.repo_key, self.clone_key, notes="dry run")
        self.assertEqual(preview["schema"], "save-game-registration/v1")
        self.assertFalse(paths.registration_path(self.repo_key, self.clone_key).exists())

    def test_adopt_creates_schema_valid_registration_and_flips_to_configured(self):
        doc = lifecycle.adopt(self.repo_key, self.clone_key, notes="first adoption")
        self.assertEqual(doc["schema"], "save-game-registration/v1")
        self.assertTrue(paths.registration_path(self.repo_key, self.clone_key).is_file())
        status = lifecycle.adoption_status(self.repo_key, self.clone_key)
        self.assertEqual(status["case"], "configured")
        self.assertTrue(status["adopted"])
        self.assertEqual(status["registration"], doc)

    def test_second_adopt_updates_in_place_and_preserves_created_at(self):
        first = lifecycle.adopt(self.repo_key, self.clone_key, enabled=True)
        second = lifecycle.adopt(self.repo_key, self.clone_key, enabled=False, notes="disabled by operator")
        self.assertEqual(second["created_at"], first["created_at"])
        self.assertFalse(second["enabled"])
        self.assertEqual(lifecycle.read_registration(self.repo_key, self.clone_key)["enabled"], False)

    def test_adopt_never_touches_the_repo_working_tree(self):
        before = sorted(p.name for p in self.repo.iterdir())
        lifecycle.adopt(self.repo_key, self.clone_key)
        after = sorted(p.name for p in self.repo.iterdir())
        self.assertEqual(before, after)


class TestRetentionStatus(LifecycleTestCase):
    def test_empty_workstream_reports_nothing(self):
        status = lifecycle.retention_status(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(status["counts"], {"eligible": 0, "pinned": 0, "ambiguous": 0})

    def test_current_checkpoint_and_finalized_journal_entry_are_pinned(self):
        self._flush()
        status = lifecycle.retention_status(self.repo_key, self.clone_key, self.workstream_key)
        kinds = [i["kind"] for i in status["pinned"]]
        self.assertIn("checkpoint", kinds)
        self.assertIn("journal_operation", kinds)
        self.assertEqual(status["counts"]["eligible"], 0)

    def test_pending_operation_is_ambiguous(self):
        def build(_current_doc):
            return _minimal_candidate(self.workstream_key, self.identity)

        result = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
        )
        self.assertEqual(result.status, "proceed")  # prepared+replaced, never finalized

        status = lifecycle.retention_status(self.repo_key, self.clone_key, self.workstream_key)
        pending = [i for i in status["ambiguous"] if i["kind"] == "journal_operation"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["operation_id"], result.operation_id)

    def test_has_zero_side_effects(self):
        self._flush()
        before = _snapshot_tree(paths.state_root())
        lifecycle.retention_status(self.repo_key, self.clone_key, self.workstream_key)
        after = _snapshot_tree(paths.state_root())
        self.assertEqual(before, after)


class TestGCTempFiles(LifecycleTestCase):
    def test_six_day_old_temp_file_is_not_collected(self):
        temp_path = self._make_abandoned_temp_file(age_days=6)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["deleted_count"], 0)
        self.assertTrue(temp_path.exists())

    def test_eight_day_old_temp_file_is_collected_and_tombstoned(self):
        temp_path = self._make_abandoned_temp_file(age_days=8)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(temp_path.exists())

        tombstone = result["tombstones"][0]
        self.assertEqual(tombstone["schema"], "save-game-tombstone/v1")
        self.assertEqual(tombstone["target_kind"], "temp_file")
        self.assertEqual(tombstone["reason"], "gc_abandoned_temp")

        on_disk_path = (
            paths.state_root() / "tombstones" / self.repo_key / self.clone_key
            / self.workstream_key / f"{tombstone['tombstone_id']}.json"
        )
        self.assertEqual(json.loads(on_disk_path.read_bytes()), tombstone)

    def test_boundary_just_over_seven_days_is_collected(self):
        temp_path = self._make_abandoned_temp_file(age_days=7.01)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(temp_path.exists())

    def test_sibling_workstreams_temp_files_are_not_collected_by_this_ones_gc(self):
        other_workstream_key = identity_mod.workstream_key_for(self.repo_key, self.clone_key, "task-other", self.identity)
        current_path = paths.current_path(self.repo_key, self.clone_key, other_workstream_key)
        durability.ensure_private_dir(current_path.parent)
        other_temp = current_path.parent / f".{current_path.name}.tmp.{os.getpid()}.{os.urandom(6).hex()}"
        other_temp.write_bytes(b"{}")
        old_time = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
        os.utime(other_temp, (old_time, old_time))

        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["deleted_count"], 0)
        self.assertTrue(other_temp.exists())


class TestGCSnapshots(LifecycleTestCase):
    def _create_aborted_operation_with_snapshot(self) -> Path:
        self._flush(objective="Generation one.")
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        gen1_bytes = current_path.read_bytes()

        def build_gen2(_current_doc):
            return _minimal_candidate(self.workstream_key, self.identity, objective="Generation two (about to be aborted).")

        second = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key,
            build_candidate_fn=build_gen2, identity=self.identity,
        )
        self.assertEqual(second.status, "proceed")

        # Simulate a crash where the atomic replace never actually reached
        # disk: restore current.json to generation one's exact bytes so
        # recovery sees current_digest == old_digest and classifies this
        # operation ABORTED (mirrors test_transaction.py's own
        # _crash_after_prepared -- a hand-rollback that exists purely to
        # construct the fixture, never something GC itself does).
        current_path.write_bytes(gen1_bytes)

        records = tx.recover_workstream(self.repo_key, self.clone_key, self.workstream_key)
        aborted = [r for r in records if r.operation_id == second.operation_id]
        self.assertEqual(len(aborted), 1)
        self.assertEqual(aborted[0].outcome, tx.RecoveryOutcome.ABORTED)

        prepared = json.loads(durability.read_file_bytes(
            paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, second.operation_id) / "prepared.json"
        ))
        snapshot_path = paths.snapshot_path(self.repo_key, self.clone_key, self.workstream_key, prepared["snapshot_digest"])
        self.assertTrue(snapshot_path.is_file())
        return snapshot_path

    def test_six_day_old_aborted_snapshot_is_not_collected(self):
        snapshot_path = self._create_aborted_operation_with_snapshot()
        soon = datetime.now(timezone.utc) + timedelta(days=6)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key, now=soon)
        self.assertEqual(result["deleted_count"], 0)
        self.assertTrue(snapshot_path.is_file())

    def test_eight_day_old_aborted_snapshot_is_collected_and_tombstoned(self):
        snapshot_path = self._create_aborted_operation_with_snapshot()
        later = datetime.now(timezone.utc) + timedelta(days=8)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key, now=later)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(snapshot_path.is_file())
        self.assertEqual(result["tombstones"][0]["target_kind"], "snapshot")
        self.assertEqual(result["tombstones"][0]["reason"], "gc_unreferenced_snapshot")

    def test_finalized_generation_snapshot_is_never_collected_even_far_in_the_future(self):
        self._flush()
        far_future = datetime.now(timezone.utc) + timedelta(days=365)
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key, now=far_future)
        self.assertEqual(result["deleted_count"], 0)
        self.assertIsNotNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))

    def test_retention_status_predicts_gc_eligibility_for_aborted_snapshot(self):
        snapshot_path = self._create_aborted_operation_with_snapshot()
        later = datetime.now(timezone.utc) + timedelta(days=8)
        status = lifecycle.retention_status(self.repo_key, self.clone_key, self.workstream_key, now=later)
        eligible_snaps = [i for i in status["eligible"] if i["kind"] == "snapshot"]
        self.assertEqual(len(eligible_snaps), 1)
        self.assertEqual(eligible_snaps[0]["path"], snapshot_path)


class TestCrashResumableDeletion(LifecycleTestCase):
    def test_crash_between_prepare_and_complete_recovers_deterministically(self):
        temp_path = self._make_abandoned_temp_file(age_days=8)
        digest = canonical.sha256_hex(temp_path.read_bytes())
        lifecycle.prepare_deletion(
            self.repo_key, self.clone_key, self.workstream_key,
            target_path=temp_path, target_kind="temp_file", target_digest=digest, reason="gc_abandoned_temp",
        )
        # "Crash": prepared.json is durable, but complete_deletion never ran.
        self.assertTrue(temp_path.exists())

        first = lifecycle.recover_pending_deletions(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["outcome"], "completed")
        self.assertFalse(temp_path.exists())

        # Idempotent: a second recovery pass over the same (now-tombstoned)
        # operation must not error or attempt a double delete.
        second = lifecycle.recover_pending_deletions(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(second[0]["outcome"], "completed")
        self.assertEqual(second[0]["tombstone_id"], first[0]["tombstone_id"])

    def test_recovery_after_target_already_unlinked_still_writes_tombstone(self):
        # A second crash point: unlink succeeded, but the process died before
        # the tombstone was durably written.
        temp_path = self._make_abandoned_temp_file(age_days=8)
        digest = canonical.sha256_hex(temp_path.read_bytes())
        lifecycle.prepare_deletion(
            self.repo_key, self.clone_key, self.workstream_key,
            target_path=temp_path, target_kind="temp_file", target_digest=digest, reason="gc_abandoned_temp",
        )
        os.unlink(temp_path)

        results = lifecycle.recover_pending_deletions(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(results[0]["outcome"], "completed")

    def test_gc_run_recovers_pending_deletions_before_scanning_for_new_ones(self):
        temp_path = self._make_abandoned_temp_file(age_days=8)
        digest = canonical.sha256_hex(temp_path.read_bytes())
        lifecycle.prepare_deletion(
            self.repo_key, self.clone_key, self.workstream_key,
            target_path=temp_path, target_kind="temp_file", target_digest=digest, reason="gc_abandoned_temp",
        )
        result = lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(len(result["recovered_pending"]), 1)
        self.assertEqual(result["recovered_pending"][0]["outcome"], "completed")
        self.assertFalse(temp_path.exists())

    def test_symlinked_target_is_blocked_never_deleted(self):
        current_path = paths.current_path(self.repo_key, self.clone_key, self.workstream_key)
        durability.ensure_private_dir(current_path.parent)
        real = current_path.parent / "real-target.json"
        real.write_bytes(b"{}")
        link = current_path.parent / "link-target.json"
        os.symlink(real, link)
        digest = canonical.sha256_hex(real.read_bytes())
        lifecycle.prepare_deletion(
            self.repo_key, self.clone_key, self.workstream_key,
            target_path=link, target_kind="temp_file", target_digest=digest, reason="gc_abandoned_temp",
        )

        results = lifecycle.recover_pending_deletions(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(results[0]["outcome"], "blocked")
        self.assertTrue(link.is_symlink())
        self.assertTrue(real.exists())

    def test_target_outside_private_roots_is_refused(self):
        outside = Path(self.tmp) / "definitely-not-private.json"
        outside.write_bytes(b"{}")
        prepared = lifecycle.prepare_deletion(
            self.repo_key, self.clone_key, self.workstream_key,
            target_path=outside, target_kind="temp_file", target_digest="0" * 64, reason="gc_abandoned_temp",
        )
        with self.assertRaises(durability.UnsafePathError):
            lifecycle.complete_deletion(self.repo_key, self.clone_key, self.workstream_key, prepared)
        self.assertTrue(outside.exists())


class TestGCScopeIsNarrow(LifecycleTestCase):
    def test_gc_never_deletes_checkpoints_or_current_state_even_far_in_the_future(self):
        self._flush()
        far_future = datetime.now(timezone.utc) + timedelta(days=365)
        lifecycle.gc_run(self.repo_key, self.clone_key, self.workstream_key, now=far_future)
        self.assertIsNotNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))
        checkpoints = list(paths.checkpoints_dir(self.repo_key, self.clone_key, self.workstream_key).iterdir())
        self.assertEqual(len(checkpoints), 1)


class TestArchive(LifecycleTestCase):
    def test_no_active_state_yet(self):
        result = lifecycle.archive_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["status"], "NO_ACTIVE_STATE")

    def test_requires_terminal_status(self):
        self._flush(status="active")
        result = lifecycle.archive_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["status"], "NOT_TERMINAL")

    def test_requires_clear_hygiene(self):
        self._flush(status="terminal", hygiene={
            "transactions_finalized": True, "temp_artifacts_clear": True,
            "repo_status_observed": True, "required_checks_run": False,
            "unclassified_delta": False,
        })
        result = lifecycle.archive_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["status"], "HYGIENE_INCOMPLETE")

    def test_writes_schema_valid_manifest_when_terminal_and_clean(self):
        self._flush(status="terminal")
        result = lifecycle.archive_workstream(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(result["status"], "ARCHIVED")
        manifest = result["manifest"]
        self.assertEqual(manifest["schema"], "save-game-archive-manifest/v1")
        current = tx.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(manifest["final_active_state_digest"], current["current_digest"])

        on_disk = [
            json.loads(p.read_bytes())
            for p in paths.archives_dir(self.repo_key, self.clone_key, self.workstream_key).iterdir()
        ]
        self.assertEqual(on_disk, [manifest])

    def test_archiving_never_flips_current_status_itself(self):
        self._flush(status="terminal")
        lifecycle.archive_workstream(self.repo_key, self.clone_key, self.workstream_key)
        current = tx.read_current(self.repo_key, self.clone_key, self.workstream_key)
        self.assertEqual(current["status"], "terminal")


class TestRemove(LifecycleTestCase):
    def test_preview_has_no_side_effects(self):
        self._flush()
        before = _snapshot_tree(paths.state_root())
        preview = lifecycle.remove_preview(self.repo_key, self.clone_key, self.workstream_key)
        after = _snapshot_tree(paths.state_root())
        self.assertEqual(before, after)
        self.assertGreater(preview["item_count"], 0)

    def test_execute_refuses_on_digest_mismatch_and_deletes_nothing(self):
        self._flush()
        before = _snapshot_tree(paths.state_root(), exclude_top_dirs=("locks",))
        result = lifecycle.remove_execute(self.repo_key, self.clone_key, self.workstream_key, confirm_preview_digest="0" * 64)
        self.assertEqual(result["status"], "PREVIEW_DIGEST_MISMATCH")
        after = _snapshot_tree(paths.state_root(), exclude_top_dirs=("locks",))
        self.assertEqual(before, after)
        self.assertIsNotNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))

    def test_execute_with_correct_digest_deletes_everything_and_tombstones_it(self):
        self._flush()
        preview = lifecycle.remove_preview(self.repo_key, self.clone_key, self.workstream_key)
        result = lifecycle.remove_execute(self.repo_key, self.clone_key, self.workstream_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "REMOVED")
        self.assertEqual(result["deleted_count"], preview["item_count"])
        self.assertIsNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))
        for tombstone in result["tombstones"]:
            self.assertEqual(tombstone["schema"], "save-game-tombstone/v1")
            self.assertEqual(tombstone["reason"], "explicit_remove")

    def test_uses_the_same_run_deletion_transaction_as_gc(self):
        self._flush()
        preview = lifecycle.remove_preview(self.repo_key, self.clone_key, self.workstream_key)
        lifecycle.remove_execute(self.repo_key, self.clone_key, self.workstream_key, confirm_preview_digest=preview["preview_digest"])
        tombstones_dir = paths.state_root() / "tombstones" / self.repo_key / self.clone_key / self.workstream_key
        gc_journal_dir = paths.state_root() / "gc-journal" / self.repo_key / self.clone_key / self.workstream_key
        self.assertEqual(len(list(tombstones_dir.iterdir())), preview["item_count"])
        self.assertEqual(len(list(gc_journal_dir.iterdir())), preview["item_count"])

    def test_pending_journal_operation_is_preserved_not_deleted(self):
        # Plan: "[remove] preserves unresolved or malformed evidence." A
        # pending (never finalized/aborted) operation must survive both the
        # preview's plan and an execute against that preview.
        self._flush()

        def build(_current_doc):
            return _minimal_candidate(self.workstream_key, self.identity, objective="Generation two, never finalized.")

        pending = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
        )
        self.assertEqual(pending.status, "proceed")
        pending_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, pending.operation_id)
        self.assertTrue(pending_dir.is_dir())

        preview = lifecycle.remove_preview(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(any(pending.operation_id in item["path"] for item in preview["items"]))

        result = lifecycle.remove_execute(self.repo_key, self.clone_key, self.workstream_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "REMOVED")
        self.assertTrue((pending_dir / "prepared.json").is_file())

    def test_quarantined_operation_is_preserved_not_deleted(self):
        # Plan: "[remove] preserves unresolved or malformed evidence." A
        # quarantined (malformed/unsafe) operation directory must survive too.
        self._flush()
        quarantine_dir = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key) / "quarantine" / "op-bogus"
        durability.ensure_private_dir(quarantine_dir)
        (quarantine_dir / "prepared.json").write_bytes(b'{"not": "valid evidence"}')

        preview = lifecycle.remove_preview(self.repo_key, self.clone_key, self.workstream_key)
        self.assertFalse(any("quarantine" in item["path"] for item in preview["items"]))

        result = lifecycle.remove_execute(self.repo_key, self.clone_key, self.workstream_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "REMOVED")
        self.assertTrue((quarantine_dir / "prepared.json").is_file())


class TestUninstall(LifecycleTestCase):
    def test_preview_includes_registration_and_all_workstreams(self):
        lifecycle.adopt(self.repo_key, self.clone_key)
        self._flush()
        preview = lifecycle.uninstall_preview(self.repo_key, self.clone_key)
        item_paths = {item["path"] for item in preview["items"]}
        self.assertIn(str(paths.registration_path(self.repo_key, self.clone_key)), item_paths)
        self.assertIn(self.workstream_key, preview["workstream_keys"])

    def test_execute_removes_workstream_state_and_registration(self):
        lifecycle.adopt(self.repo_key, self.clone_key)
        self._flush()
        preview = lifecycle.uninstall_preview(self.repo_key, self.clone_key)
        result = lifecycle.uninstall_execute(self.repo_key, self.clone_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "UNINSTALLED")
        self.assertFalse(paths.registration_path(self.repo_key, self.clone_key).exists())
        self.assertIsNone(tx.read_current(self.repo_key, self.clone_key, self.workstream_key))
        self.assertEqual(len(result["registration_tombstones"]), 1)
        self.assertEqual(result["registration_tombstones"][0]["target_kind"], "checkpoint_evidence")
        self.assertEqual(result["registration_tombstones"][0]["schema"], "save-game-tombstone/v1")

    def test_execute_refuses_on_digest_mismatch(self):
        lifecycle.adopt(self.repo_key, self.clone_key)
        result = lifecycle.uninstall_execute(self.repo_key, self.clone_key, confirm_preview_digest="0" * 64)
        self.assertEqual(result["status"], "PREVIEW_DIGEST_MISMATCH")
        self.assertTrue(paths.registration_path(self.repo_key, self.clone_key).exists())

    def test_uninstall_without_registration_still_removes_workstreams(self):
        self._flush()  # never adopted
        preview = lifecycle.uninstall_preview(self.repo_key, self.clone_key)
        result = lifecycle.uninstall_execute(self.repo_key, self.clone_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "UNINSTALLED")
        self.assertEqual(result["registration_tombstones"], [])

    def test_uninstall_inherits_removes_preservation_of_pending_evidence(self):
        # uninstall_execute delegates to remove_execute per workstream, so the
        # same plan guarantee ("preserves unresolved or malformed evidence")
        # must hold even though uninstall is otherwise a full retirement.
        lifecycle.adopt(self.repo_key, self.clone_key)
        self._flush()

        def build(_current_doc):
            return _minimal_candidate(self.workstream_key, self.identity, objective="Never finalized.")

        pending = tx.begin_transaction(
            self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
        )
        pending_dir = paths.journal_operation_dir(self.repo_key, self.clone_key, self.workstream_key, pending.operation_id)

        preview = lifecycle.uninstall_preview(self.repo_key, self.clone_key)
        result = lifecycle.uninstall_execute(self.repo_key, self.clone_key, confirm_preview_digest=preview["preview_digest"])
        self.assertEqual(result["status"], "UNINSTALLED")
        self.assertTrue((pending_dir / "prepared.json").is_file())

    def test_install_sh_client_symlinks_are_never_touched(self):
        # uninstall_execute must only ever reach into XDG state/config for
        # save-game's own private records -- it has no path derivation that
        # could resolve into a client's skills directory at all. Every item
        # path was built by paths.py's own helpers (never independently
        # resolved), so comparing unresolved strings is the apples-to-apples
        # check here.
        lifecycle.adopt(self.repo_key, self.clone_key)
        self._flush()
        preview = lifecycle.uninstall_preview(self.repo_key, self.clone_key)
        for item in preview["items"]:
            self.assertTrue(
                item["path"].startswith(str(paths.state_root())) or item["path"].startswith(str(paths.config_root()))
            )


if __name__ == "__main__":
    unittest.main()
