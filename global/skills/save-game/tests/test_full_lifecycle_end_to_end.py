"""Genuine end-to-end test proving the modules built across this build's three
prior phases actually work TOGETHER, driven entirely through `engine.cli.main`
(the same surface `scripts/save-game.sh` and every client adapter call into) —
not isolated per-module fixtures. This is a SIBLING to `test_end_to_end.py`
(which proves Flush -> crash -> recovery -> Reconcile at the engine-function
level) and to `test_lifecycle.py` (which proves each lifecycle verb in
isolation); this file's job is the one no other test file covers: one
continuous flow spanning adoption, the four core contracts (with a
client-capability-aware Compact Decision embedded in a real checkpoint),
Phase-3a's status/stopping projection, and both lifecycle exit paths
(archive+remove, and separately uninstall)."""

from __future__ import annotations

import contextlib
import io
import json
import unittest

import _support

from engine import identity as identity_mod, transaction

TASK_ID = "task-full-lifecycle"


def _run(argv) -> tuple:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        from engine import cli
        code = cli.main(argv)
    return code, json.loads(buf.getvalue())


class FullLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        identity = identity_mod.resolve_root_identity(str(self.repo))
        self.repo_key = identity_mod.repo_key_for(identity)
        self.clone_key = identity_mod.clone_key_for(identity)
        self.workstream_key = identity_mod.workstream_key_for(self.repo_key, self.clone_key, TASK_ID, identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def _run(self, *args):
        return _run(["--root", str(self.repo), *args])


class TestAdoptThroughArchiveAndRemove(FullLifecycleTestCase):
    def test_full_lifecycle_through_the_cli(self):
        # 1. Adopt: explicit operator confirmation writes the private
        # registration (plan: "Adoption"). Preview first proves it starts
        # unconfigured, matching the CLI's own --preview contract.
        code, preview = self._run("adopt", "--preview")
        self.assertEqual((code, preview["case"]), (0, "unconfigured"))

        code, registration = self._run("adopt", "--note", "full-lifecycle integration test")
        self.assertEqual(code, 0)
        self.assertEqual(registration["schema"], "save-game-registration/v1")
        self.assertTrue(registration["enabled"])

        # 2. Flush: now that this clone is adopted, the SAME flush that would
        # have been SAVED_PRIVATE_UNADOPTED before adopt() is just SAVED —
        # proving adopt() and flush() are actually wired to the same
        # registration record, not two modules that happen to coexist.
        code, receipt1 = self._run(
            "flush", "--task-id", TASK_ID, "--client-id", "claude",
            "--objective", "Ship the save-game v2 capability.", "--next-action", "Wire the CLI.",
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt1["status"], "SAVED")
        self.assertEqual(receipt1["workstream_key"], self.workstream_key)

        # 3. Index: the checkpoint Flush #1 created resolves cleanly and
        # carries the objective through.
        code, checkpoint1 = self._run("index", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(checkpoint1["schema"], "save-game-checkpoint/v1")
        self.assertEqual(checkpoint1["checkpoint_id"], receipt1["checkpoint_id"])
        self.assertEqual(checkpoint1["objective"], "Ship the save-game v2 capability.")

        # 4. Compact Decision, client-capability-aware: an explicit operator
        # compact request for Claude resolves Claude's EXACT manual command
        # and hook-capability class from adapters.py through compact_decision.
        code, compact = self._run("compact-check", "--operator-request", "compact", "--client-id", "claude")
        self.assertEqual(code, 0)
        self.assertEqual(compact["status"], "COMPACTION_REQUIRED")
        self.assertEqual(compact["manual_compaction_command"], "/compact")
        self.assertEqual(compact["pre_compaction_capability"], "can_block")
        self.assertTrue(compact["client_capability_known"])

        # 5. A second Flush with verified pressure actually EMBEDS a Compact
        # Decision result into a real checkpoint (a genuine durable delta is
        # required for a new checkpoint to be created at all -- pressure
        # alone on an unchanged candidate would be NO_DURABLE_DELTA and never
        # reach Index, so the next-action changes too).
        code, receipt2 = self._run(
            "flush", "--task-id", TASK_ID, "--client-id", "claude",
            "--objective", "Ship the save-game v2 capability.", "--next-action", "Trigger a compaction checkpoint.",
            "--pressure-percent", "85", "--continuation-count", "3",
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt2["status"], "SAVED")
        self.assertGreater(receipt2["checkpoint_id"], "")

        code, checkpoint2 = self._run("index", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(checkpoint2["checkpoint_id"], receipt2["checkpoint_id"])
        self.assertEqual(checkpoint2["compaction"]["status"], "compaction_required")
        self.assertEqual(checkpoint2["compaction"]["pressure_percent"], 85)

        # 6. Reconcile: root/ref/HEAD still matches (git never moved), the
        # checkpoint matches current, and the goal reflects the latest Flush.
        code, reconcile_receipt = self._run("reconcile", "--task-id", TASK_ID, "--trigger", "resume")
        self.assertEqual(code, 0)
        by_claim = {c["claim"]: c["result"] for c in reconcile_receipt["classifications"]}
        self.assertEqual(by_claim["root_ref_head"], "MATCH")
        self.assertEqual(by_claim["active_state_vs_checkpoint_digest"], "MATCH")
        self.assertEqual(reconcile_receipt["goal"], "Ship the save-game v2 capability.")
        self.assertFalse(reconcile_receipt["blockers"])

        # 7. Retention status: the current checkpoint and finalized journal
        # entries are pinned; nothing is eligible for GC yet.
        code, retention = self._run("retention-status", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(retention["counts"]["eligible"], 0)
        pinned_kinds = {i["kind"] for i in retention["pinned"]}
        self.assertIn("checkpoint", pinned_kinds)

        # 8. Promotion candidates: read-only, shape-valid, empty (nothing was
        # ever proposed) -- proving the surface wires through without error
        # even in the common empty case.
        code, promo = self._run("promotion-candidates", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(promo["count"], 0)

        # 9. Status before terminal: hygiene is clear, there's a pending next
        # action, and stopping correctly says "continue" -- Phase 3a's
        # behavior rules running against this exact persisted state.
        code, status_active = self._run("status", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(status_active["task_status"], "active")
        self.assertTrue(status_active["hygiene"]["all_clear"])
        self.assertEqual(status_active["blockers"], [])
        self.assertEqual(status_active["stopping"]["outcome"], "continue")

        # 10. Flip to terminal via the CLI's --status flag (the only CLI path
        # to a status archive_workstream can act on) -- hygiene carries over
        # clear, so status now reports acceptance+hygiene complete.
        code, receipt3 = self._run(
            "flush", "--task-id", TASK_ID, "--client-id", "claude",
            "--objective", "Ship the save-game v2 capability.", "--status", "terminal",
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt3["status"], "SAVED")

        code, status_terminal = self._run("status", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(status_terminal["task_status"], "terminal")
        self.assertEqual(status_terminal["stopping"]["outcome"], "acceptance_and_hygiene_complete")

        # 11. Archive: terminal + clear hygiene is exactly archive_workstream's
        # precondition -- writes an immutable hash manifest, never deletes.
        code, archive = self._run("archive", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertEqual(archive["status"], "ARCHIVED")
        self.assertEqual(archive["manifest"]["schema"], "save-game-archive-manifest/v1")
        self.assertIsNotNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))  # archive never deletes

        # 12. Remove: preview-first, confirmation bound to the exact preview
        # digest. This is the "or remove" half of the deliverable -- run in
        # the SAME flow as archive (a superset, not a substitute) so both
        # terminal exit paths get proven together.
        code, remove_preview = self._run("remove", "--task-id", TASK_ID)
        self.assertEqual(code, 0)
        self.assertGreater(remove_preview["item_count"], 0)

        code, remove_result = self._run("remove", "--task-id", TASK_ID, "--execute", "--confirm-digest", remove_preview["preview_digest"])
        self.assertEqual(code, 0)
        self.assertEqual(remove_result["status"], "REMOVED")
        self.assertIsNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))

        # 13. Remove is workstream-scoped only -- the clone-level registration
        # from step 1 must still be intact (distinct from uninstall, proven
        # separately below).
        code, adoption_after_remove = self._run("adopt", "--preview")
        self.assertEqual(code, 0)
        self.assertTrue(adoption_after_remove["adopted"])


class TestUninstallFullRetirement(FullLifecycleTestCase):
    """`uninstall` is the CLONE-level exit path (registration + every
    workstream), distinct from `remove`'s workstream-only scope -- proven
    end-to-end separately since the main flow above only exercises `remove`."""

    def test_adopt_flush_then_uninstall_via_cli(self):
        self._run("adopt")
        code, flush_receipt = self._run("flush", "--task-id", TASK_ID, "--client-id", "cursor", "--objective", "About to retire this clone.")
        self.assertEqual(code, 0)
        self.assertEqual(flush_receipt["status"], "SAVED")

        code, preview = self._run("uninstall")
        self.assertEqual(code, 0)
        self.assertIn(self.workstream_key, preview["workstream_keys"])
        self.assertGreater(preview["item_count"], 0)

        code, result = self._run("uninstall", "--execute", "--confirm-digest", preview["preview_digest"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "UNINSTALLED")

        self.assertIsNone(transaction.read_current(self.repo_key, self.clone_key, self.workstream_key))
        code, adoption_after = self._run("adopt", "--preview")
        self.assertFalse(adoption_after["adopted"])  # registration gone too, unlike remove


if __name__ == "__main__":
    unittest.main()
