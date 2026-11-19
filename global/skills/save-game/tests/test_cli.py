"""Tests for engine/cli.py's argv dispatch — the surface scripts/save-game.sh
calls into. Exercises all subcommands end-to-end (through main(), not by
calling the contract modules directly) and captures/parses their JSON stdout."""

from __future__ import annotations

import contextlib
import io
import json
import os
import time
import unittest

import _support

from engine import cli, identity as identity_mod, paths

TASK_ID = "cli-test-task"


def _keys_for(repo, task_id):
    identity = identity_mod.resolve_root_identity(str(repo))
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    workstream_key = identity_mod.workstream_key_for(repo_key, clone_key, task_id, identity)
    return repo_key, clone_key, workstream_key


def _checkpoint_files_for(repo, task_id):
    """Resolve the same keys the CLI derives internally, then list any
    checkpoint files written for that workstream."""
    repo_key, clone_key, workstream_key = _keys_for(repo, task_id)
    checkpoints_dir = paths.checkpoints_dir(repo_key, clone_key, workstream_key)
    if not checkpoints_dir.is_dir():
        return []
    return sorted(checkpoints_dir.glob("*.json"))


def _make_abandoned_temp_file(repo, task_id, *, age_days):
    """Drop a `.tmp.` file next to `current.json` old enough (or not) to be
    GC-eligible, matching `lifecycle._TEMP_FILE_RE`'s expected shape."""
    repo_key, clone_key, workstream_key = _keys_for(repo, task_id)
    current_path = paths.current_path(repo_key, clone_key, workstream_key)
    temp_path = current_path.parent / f".{current_path.name}.tmp.999.deadbeef"
    temp_path.write_bytes(b"{}")
    stamp = time.time() - age_days * 86400
    os.utime(temp_path, (stamp, stamp))
    return temp_path


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _run(self, argv) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, json.loads(buf.getvalue())


class TestFlushCommand(CliTestCase):
    def test_flush_with_objective_and_next_action_succeeds(self):
        code, doc = self._run([
            "--root", str(self.repo), "flush",
            "--task-id", TASK_ID, "--objective", "Ship the CLI.", "--next-action", "Write the wiring.",
        ])
        self.assertEqual(code, 0)
        self.assertEqual(doc["schema"], "save-game-flush-receipt/v1")
        self.assertIn(doc["status"], ("SAVED", "SAVED_PRIVATE_UNADOPTED"))

    def test_flush_default_task_id_is_stable_across_calls(self):
        code1, first = self._run(["--root", str(self.repo), "flush", "--objective", "First call, no --task-id."])
        code2, second = self._run(["--root", str(self.repo), "flush", "--objective", "First call, no --task-id."])
        self.assertEqual(code1, 0)
        self.assertEqual(second["status"], "NO_DURABLE_DELTA")  # same default workstream, same content
        self.assertEqual(first["workstream_key"], second["workstream_key"])

    def test_flush_authority_conflict_flag_maps_to_authority_conflict_status(self):
        code, doc = self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--authority-conflict"])
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "AUTHORITY_CONFLICT")

    def test_flush_with_high_pressure_marks_compaction_required_in_checkpoint(self):
        code, doc = self._run([
            "--root", str(self.repo), "flush", "--task-id", TASK_ID,
            "--objective", "Trigger compaction.", "--pressure-percent", "85", "--continuation-count", "3",
        ])
        self.assertEqual(code, 0)
        checkpoint_files = _checkpoint_files_for(self.repo, TASK_ID)
        self.assertEqual(len(checkpoint_files), 1)
        checkpoint = json.loads(checkpoint_files[0].read_bytes())
        self.assertEqual(checkpoint["compaction"]["status"], "compaction_required")


class TestIndexCommand(CliTestCase):
    def test_index_before_any_flush_is_no_checkpoint(self):
        code, doc = self._run(["--root", str(self.repo), "index", "--task-id", TASK_ID])
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "NO_CHECKPOINT")

    def test_index_after_a_flush_returns_the_checkpoint(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "For index to find."])
        code, doc = self._run(["--root", str(self.repo), "index", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["schema"], "save-game-checkpoint/v1")
        self.assertEqual(doc["objective"], "For index to find.")


class TestCompactCheckCommand(CliTestCase):
    def test_explicit_compact_request(self):
        code, doc = self._run(["compact-check", "--operator-request", "compact"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["status"], "COMPACTION_REQUIRED")

    def test_default_is_save_only_with_no_signals(self):
        code, doc = self._run(["compact-check"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["status"], "SAVE_ONLY")

    def test_task_completed_flag(self):
        code, doc = self._run(["compact-check", "--task-completed"])
        self.assertEqual(doc["status"], "NEW_CHAT_RECOMMENDED")

    def test_client_id_resolves_exact_manual_command_and_capability_class(self):
        code, doc = self._run(["compact-check", "--operator-request", "compact", "--client-id", "claude"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["manual_compaction_command"], "/compact")
        self.assertEqual(doc["pre_compaction_capability"], "can_block")
        self.assertTrue(doc["client_capability_known"])

    def test_default_client_id_unknown_leaves_capability_unresolved(self):
        code, doc = self._run(["compact-check", "--operator-request", "compact"])
        self.assertEqual(code, 0)
        self.assertIsNone(doc["manual_compaction_command"])
        self.assertFalse(doc["client_capability_known"])


class TestReconcileCommand(CliTestCase):
    def test_reconcile_before_any_flush_is_schema_valid(self):
        code, doc = self._run(["--root", str(self.repo), "reconcile", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["schema"], "save-game-reconcile-receipt/v1")
        self.assertEqual(doc["triggers"], ["resume"])

    def test_reconcile_repeatable_trigger_flag(self):
        code, doc = self._run(["--root", str(self.repo), "reconcile", "--task-id", TASK_ID, "--trigger", "new_chat", "--trigger", "root_change"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["triggers"], ["new_chat", "root_change"])


class TestAdoptCommand(CliTestCase):
    def test_preview_before_any_adopt_is_unconfigured(self):
        code, doc = self._run(["--root", str(self.repo), "adopt", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["case"], "unconfigured")
        self.assertFalse(doc["adopted"])

    def test_adopt_writes_a_registration_and_flush_then_reports_saved(self):
        code, doc = self._run(["--root", str(self.repo), "adopt", "--note", "test adoption"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["schema"], "save-game-registration/v1")
        self.assertTrue(doc["enabled"])
        self.assertEqual(doc["notes"], "test adoption")

        _code, preview = self._run(["--root", str(self.repo), "adopt", "--preview"])
        self.assertTrue(preview["adopted"])
        self.assertEqual(preview["case"], "configured")

        _code, flush_doc = self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "After adoption."])
        self.assertEqual(flush_doc["status"], "SAVED")  # adopted -- not SAVED_PRIVATE_UNADOPTED

    def test_adopt_disable_flag_writes_enabled_false(self):
        code, doc = self._run(["--root", str(self.repo), "adopt", "--disable"])
        self.assertEqual(code, 0)
        self.assertFalse(doc["enabled"])

    def test_adopt_is_idempotent_and_updates_in_place(self):
        self._run(["--root", str(self.repo), "adopt", "--note", "first"])
        code, doc = self._run(["--root", str(self.repo), "adopt", "--note", "second"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["notes"], "second")


class TestRetentionStatusCommand(CliTestCase):
    def test_before_any_flush_is_all_empty(self):
        code, doc = self._run(["--root", str(self.repo), "retention-status", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["counts"], {"eligible": 0, "pinned": 0, "ambiguous": 0})

    def test_after_a_flush_pins_the_checkpoint_and_journal_entry(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "For retention."])
        code, doc = self._run(["--root", str(self.repo), "retention-status", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        kinds = {i["kind"] for i in doc["pinned"]}
        self.assertEqual(kinds, {"checkpoint", "journal_operation"})

    def test_an_old_abandoned_temp_file_is_json_serializable_and_eligible(self):
        # Regression test: lifecycle._classify_temp_files returns a real Path
        # object under "path" -- the CLI must still be able to print it (this
        # crashed with TypeError before _print()'s default=str fix, found by
        # wiring lifecycle into a JSON-emitting CLI for the first time).
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "For retention."])
        _make_abandoned_temp_file(self.repo, TASK_ID, age_days=8)
        code, doc = self._run(["--root", str(self.repo), "retention-status", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        temp_items = [i for i in doc["eligible"] if i["kind"] == "temp_file"]
        self.assertEqual(len(temp_items), 1)
        self.assertIsInstance(temp_items[0]["path"], str)


class TestGcCommand(CliTestCase):
    def test_gc_on_a_clean_workstream_deletes_nothing(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Nothing to collect."])
        code, doc = self._run(["--root", str(self.repo), "gc", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["deleted_count"], 0)

    def test_gc_collects_an_old_abandoned_temp_file(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Has an old temp file."])
        temp_path = _make_abandoned_temp_file(self.repo, TASK_ID, age_days=8)
        code, doc = self._run(["--root", str(self.repo), "gc", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["deleted_count"], 1)
        self.assertFalse(temp_path.is_file())


class TestArchiveCommand(CliTestCase):
    def test_archive_before_terminal_status_is_not_terminal(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Still active."])
        code, doc = self._run(["--root", str(self.repo), "archive", "--task-id", TASK_ID])
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "NOT_TERMINAL")

    def test_flush_status_terminal_then_archive_succeeds(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Wrapping up.", "--next-action", "Archive it."])
        code, doc = self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Wrapping up.", "--status", "terminal"])
        self.assertEqual(code, 0)
        self.assertIn(doc["status"], ("SAVED", "SAVED_PRIVATE_UNADOPTED"))
        code, doc = self._run(["--root", str(self.repo), "archive", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["status"], "ARCHIVED")
        self.assertEqual(doc["manifest"]["schema"], "save-game-archive-manifest/v1")


class TestRemoveCommand(CliTestCase):
    def test_preview_then_execute_round_trip(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "To be removed."])
        code, preview = self._run(["--root", str(self.repo), "remove", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertGreater(preview["item_count"], 0)

        code, doc = self._run(["--root", str(self.repo), "remove", "--task-id", TASK_ID, "--execute", "--confirm-digest", preview["preview_digest"]])
        self.assertEqual(code, 0)
        self.assertEqual(doc["status"], "REMOVED")

    def test_execute_without_confirm_digest_is_refused_before_touching_anything(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Do not remove yet."])
        code, doc = self._run(["--root", str(self.repo), "remove", "--task-id", TASK_ID, "--execute"])
        self.assertEqual(code, 2)
        self.assertEqual(doc["status"], "CONFIRM_DIGEST_REQUIRED")
        _code, index_doc = self._run(["--root", str(self.repo), "index", "--task-id", TASK_ID])
        self.assertEqual(index_doc["schema"], "save-game-checkpoint/v1")  # untouched

    def test_stale_confirm_digest_is_refused(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "First."])
        code, doc = self._run(["--root", str(self.repo), "remove", "--task-id", TASK_ID, "--execute", "--confirm-digest", "not-a-real-digest"])
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "PREVIEW_DIGEST_MISMATCH")


class TestUninstallCommand(CliTestCase):
    def test_preview_then_execute_removes_registration_and_workstreams(self):
        self._run(["--root", str(self.repo), "adopt"])
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "About to uninstall."])

        code, preview = self._run(["--root", str(self.repo), "uninstall"])
        self.assertEqual(code, 0)
        _repo_key, _clone_key, workstream_key = _keys_for(self.repo, TASK_ID)
        self.assertIn(workstream_key, preview["workstream_keys"])

        code, doc = self._run(["--root", str(self.repo), "uninstall", "--execute", "--confirm-digest", preview["preview_digest"]])
        self.assertEqual(code, 0)
        self.assertEqual(doc["status"], "UNINSTALLED")

        _code, status_after = self._run(["--root", str(self.repo), "adopt", "--preview"])
        self.assertFalse(status_after["adopted"])


class TestPromotionCandidatesCommand(CliTestCase):
    def test_before_any_flush_is_an_empty_report(self):
        code, doc = self._run(["--root", str(self.repo), "promotion-candidates", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["count"], 0)

    def test_after_a_flush_still_shape_valid_with_no_candidates_set(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "No candidates yet."])
        code, doc = self._run(["--root", str(self.repo), "promotion-candidates", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["count"], 0)
        self.assertIn("groups", doc)


class TestStatusCommand(CliTestCase):
    def test_before_any_flush_is_no_active_state(self):
        code, doc = self._run(["--root", str(self.repo), "status", "--task-id", TASK_ID])
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "NO_ACTIVE_STATE")

    def test_after_a_flush_reports_continue_with_the_next_action(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "In progress.", "--next-action", "Keep going."])
        code, doc = self._run(["--root", str(self.repo), "status", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["task_status"], "active")
        self.assertTrue(doc["hygiene"]["all_clear"])
        self.assertEqual(doc["blockers"], [])
        self.assertEqual(doc["stopping"]["outcome"], "continue")

    def test_operator_stop_flag_overrides_to_operator_stop_outcome(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "In progress.", "--next-action", "Keep going."])
        code, doc = self._run(["--root", str(self.repo), "status", "--task-id", TASK_ID, "--operator-stop"])
        self.assertEqual(code, 0)
        self.assertEqual(doc["stopping"]["outcome"], "operator_stop")

    def test_terminal_status_with_clear_hygiene_and_no_next_actions_is_acceptance_complete(self):
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Wrapping up."])
        self._run(["--root", str(self.repo), "flush", "--task-id", TASK_ID, "--objective", "Wrapping up.", "--status", "terminal"])
        code, doc = self._run(["--root", str(self.repo), "status", "--task-id", TASK_ID])
        self.assertEqual(code, 0)
        self.assertEqual(doc["task_status"], "terminal")
        self.assertEqual(doc["stopping"]["outcome"], "acceptance_and_hygiene_complete")


class TestDoctorCommand(CliTestCase):
    def test_doctor_json_skip_runtime_is_fast_and_schema_shaped(self):
        code, doc = self._run(["doctor", "--json", "--skip-runtime"])
        self.assertIn(code, (0, 1, 2))
        self.assertIn("disk_prerequisite_status", doc)
        self.assertIn("checks", doc)

    def test_doctor_plain_text_mode_does_not_crash(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["doctor", "--skip-runtime"])
        self.assertIn(code, (0, 1, 2))
        self.assertIn("save-game engine doctor", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
