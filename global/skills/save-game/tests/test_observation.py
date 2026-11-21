"""Read-only owner CLI observations against disposable, byte-read-back state."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import _support
from engine import canonical, durability, identity as identity_mod, ids, lifecycle, observation, paths, schemas, transaction
from engine.schemas_validate import SchemaValidationError
from engine.lock import workstream_lock
from test_reconcile import ReconcileTestCase, TASK_ID, _candidate_builder


class ObservationTests(ReconcileTestCase):
    def snapshot(self):
        return {
            path.relative_to(self.tmp).as_posix(): (path.stat().st_mode, path.read_bytes() if path.is_file() else None)
            for root in (self.tmp / "state", self.tmp / "config", self.repo / ".git")
            for path in root.rglob("*")
        }

    def adopt(self, *, enabled=True):
        lifecycle.adopt(self.repo_key, self.clone_key, enabled=enabled)

    def observe(self, status, *, task_id=TASK_ID):
        before = self.snapshot()
        output = subprocess.run(
            [str(_support.SKILL_DIR / "scripts/save-game.sh"), "--root", str(self.repo),
             "reconcile", "--task-id", task_id, "--observe"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(output.stderr, "")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(output.returncode, 0 if status == "MATCH" else 1, output.stdout)
        record = json.loads(output.stdout)
        self.assertEqual(record["status"], status)
        self.assertEqual(set(record) - {"checkpoint"}, {"schema", "status", "repo_key", "clone_key", "workstream_key"})
        self.assertEqual(record["schema"], "save-game-reconcile-observation/v1")
        self.assertEqual("checkpoint" in record, status == "MATCH")
        return record

    def test_validation_requires_checkpoint_exactly_for_match(self):
        fixture = _support.SKILL_DIR / "tests/fixtures/reconcile-observation.v1/valid.json"
        matched = json.loads(fixture.read_bytes())
        observation.validate_observation(matched)
        without_checkpoint = {key: value for key, value in matched.items() if key != "checkpoint"}
        with self.assertRaises(SchemaValidationError):
            observation.validate_observation(without_checkpoint)
        statuses = schemas.load_schema("reconcile-observation.v1")["properties"]["status"]["enum"]
        for status in statuses:
            if status == "MATCH":
                continue
            with self.subTest(status=status):
                observation.validate_observation(without_checkpoint | {"status": status})
                with self.assertRaises(SchemaValidationError):
                    observation.validate_observation(matched | {"status": status})

    def test_closed_match_binds_the_exact_current_index_checkpoint(self):
        self.adopt()
        self.assertEqual(self._flush()["status"], "SAVED")
        reply = self.observe("MATCH")
        checkpoint = paths.checkpoint_path(self.repo_key, self.clone_key, self.workstream_key, reply["checkpoint"]["id"])
        self.assertEqual(reply["checkpoint"]["digest"], "sha256:" + canonical.sha256_hex(checkpoint.read_bytes()))
        self.assertEqual(reply["checkpoint"]["generation"], 1)
        self.assertEqual(reply["workstream_key"], self.workstream_key)
        self.observe("WORKSTREAM_UNAVAILABLE", task_id="different-workstream")

    def test_absent_disabled_and_late_adoption_are_distinct(self):
        self.observe("UNADOPTED")
        self.adopt(enabled=False)
        self.observe("ADOPTION_DISABLED")
        paths.registration_path(self.repo_key, self.clone_key).unlink()
        self.assertEqual(self._flush()["status"], "SAVED_PRIVATE_UNADOPTED")
        self.adopt()
        self.observe("CHECKPOINT_UNADOPTED")

    def test_concurrent_writer_refuses_without_rewriting_the_lock(self):
        self.adopt()
        self._flush()
        with workstream_lock(self.workstream_key):
            self.observe("LOCK_BUSY")
        self.observe("MATCH")

    def test_interruptions_leave_both_journal_phases_untouched_until_owner_recovery(self):
        self.adopt()
        self._flush()
        build = _candidate_builder(self.identity, self.workstream_key, objective="Interrupted fixture")
        with workstream_lock(self.workstream_key), patch.object(
            durability, "atomic_replace_durable", side_effect=OSError("fixture stop before replace"),
        ):
            with self.assertRaises(OSError):
                transaction.begin_transaction(
                    self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
                )
        self.observe("INCOMPLETE_TRANSACTION")
        self.assertIn("aborted", self._reconcile()["repairs"][0])
        self.observe("MATCH")
        with workstream_lock(self.workstream_key):
            pending = transaction.begin_transaction(
                self.repo_key, self.clone_key, self.workstream_key, build_candidate_fn=build, identity=self.identity,
            )
        self.assertEqual(pending.status, "proceed")
        self.observe("INCOMPLETE_TRANSACTION")
        self.assertIn("reconstructed", self._reconcile()["repairs"][0])
        self.observe("MATCH")

    def test_existing_identical_workstream_rejects_changed_head_and_git_conflict(self):
        self.adopt()
        self._flush()
        git_dir = Path(self.identity.git_dir)
        marker = git_dir / "MERGE_HEAD"
        marker.write_text(self.identity.observed_head + "\n")
        self.observe("GIT_CONFLICT")
        marker.unlink()
        _support._git(self.repo, "commit", "--allow-empty", "-qm", "changed head")
        self.observe("LIVE_STATE_CHANGED")

    def test_final_git_conflict_check_refuses_late_conflict_or_unavailable_read(self):
        self.adopt()
        self._flush()
        run_git = identity_mod._run_git
        for final_read, expected in (("", "MATCH"), ("unmerged index entry", "GIT_CONFLICT"),
                                     (None, "WORKSTREAM_UNAVAILABLE")):
            with self.subTest(final_read=final_read):
                reads = []
                def observed_git(root, *args):
                    if args == ("--no-optional-locks", "ls-files", "--unmerged"):
                        reads.append(args)
                        return "" if len(reads) == 1 else final_read
                    return run_git(root, *args)
                before = self.snapshot()
                with patch.object(identity_mod, "_run_git", side_effect=observed_git):
                    reply = observation.observe_reconcile(
                        self.repo_key, self.clone_key, self.workstream_key,
                        task_id=TASK_ID, identity=self.identity,
                    )
                self.assertEqual(reply["status"], expected)
                self.assertEqual("checkpoint" in reply, expected == "MATCH")
                self.assertEqual(self.snapshot(), before)

    def test_missing_finalized_evidence_cannot_be_skipped(self):
        self.adopt()
        receipt = self._flush()
        paths.receipt_path(self.repo_key, self.clone_key, self.workstream_key, receipt["receipt_id"]).unlink()
        self.observe("INVALID_EVIDENCE")

    def test_enabling_adoption_after_legacy_disabled_save_cannot_qualify_it(self):
        self.adopt(enabled=False)
        self.assertEqual(self._flush()["status"], "SAVED")
        with patch.object(ids, "now_iso", return_value="2099-01-01T00:00:00Z"):
            self.adopt()
        self.observe("CHECKPOINT_UNADOPTED")

    def test_adoption_after_recovery_cannot_qualify_an_unadopted_write(self):
        with workstream_lock(self.workstream_key):
            pending = transaction.begin_transaction(
                self.repo_key, self.clone_key, self.workstream_key,
                build_candidate_fn=_candidate_builder(self.identity, self.workstream_key), identity=self.identity,
            )
        self.assertEqual(pending.status, "proceed")
        self.assertIn("reconstructed", self._reconcile()["repairs"][0])
        with patch.object(ids, "now_iso", return_value="2099-01-01T00:00:00Z"):
            self.adopt()
        self.observe("CHECKPOINT_UNADOPTED")

    def test_schema_valid_drift_in_prepared_lineage_cannot_qualify(self):
        self.adopt()
        self._flush()
        journal = paths.journal_workstream_dir(self.repo_key, self.clone_key, self.workstream_key)
        prepared = next(journal.iterdir()) / "prepared.json"
        raw = prepared.read_bytes()
        document = json.loads(raw)
        for key, changed in (
            ("old_digest", "a" * 64),
            ("observed_root", document["observed_root"] | {"observed_head": "a" * 40}),
            ("snapshot_digest", "b" * 64),
        ):
            with self.subTest(key=key):
                prepared.write_bytes(canonical.canonical_bytes(document | {key: changed}))
                self.observe("INVALID_EVIDENCE")
        prepared.write_bytes(raw)
        self.observe("MATCH")

    def test_incomparable_current_checkpoints_do_not_select_a_pointer(self):
        self.adopt()
        receipt = self._flush()
        scope = self.repo_key, self.clone_key, self.workstream_key
        journal = paths.journal_workstream_dir(*scope)
        old_operation = next(journal.iterdir())
        prepared = json.loads((old_operation / "prepared.json").read_bytes())
        finalized = json.loads((old_operation / "finalized.json").read_bytes())
        checkpoint = json.loads(paths.checkpoint_path(*scope, receipt["checkpoint_id"]).read_bytes())
        operation = journal / "op-competing"
        operation.mkdir()
        (operation / "prepared.json").write_bytes(canonical.canonical_bytes(prepared | {
            "operation_id": operation.name,
        }))
        (operation / "finalized.json").write_bytes(canonical.canonical_bytes(finalized | {
            "operation_id": operation.name, "checkpoint_id": "chk-competing", "receipt_id": "rcpt-competing",
        }))
        paths.checkpoint_path(*scope, "chk-competing").write_bytes(canonical.canonical_bytes(checkpoint | {
            "checkpoint_id": "chk-competing",
        }))
        paths.receipt_path(*scope, "rcpt-competing").write_bytes(canonical.canonical_bytes(receipt | {
            "checkpoint_id": "chk-competing", "receipt_id": "rcpt-competing",
        }))
        self.observe("CHECKPOINT_AMBIGUOUS")
