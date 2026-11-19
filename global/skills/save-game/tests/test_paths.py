import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _support import isolated_xdg_roots  # noqa: E402

from engine import paths  # noqa: E402

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


class TestPaths(unittest.TestCase):
    def test_unsafe_hex_component_rejected(self):
        with self.assertRaises(paths.UnsafePathComponentError):
            paths.current_path("not-hex", HEX_B, HEX_C)

    def test_unsafe_id_component_rejected(self):
        with self.assertRaises(paths.UnsafePathComponentError):
            paths.checkpoint_path(HEX_A, HEX_B, HEX_C, "-leading-dash-not-allowed")

    def test_layout_nests_repo_clone_workstream(self):
        with isolated_xdg_roots():
            p = paths.current_path(HEX_A, HEX_B, HEX_C)
            self.assertIn("current", p.parts)
            self.assertIn(HEX_A, p.parts)
            self.assertIn(HEX_B, p.parts)
            self.assertTrue(p.name.startswith(HEX_C))

    def test_snapshot_and_checkpoint_and_journal_and_receipt_paths(self):
        with isolated_xdg_roots():
            snap = paths.snapshot_path(HEX_A, HEX_B, HEX_C, HEX_A)
            self.assertTrue(snap.name.endswith(".json"))
            self.assertIn("snapshots", snap.parts)

            chk = paths.checkpoint_path(HEX_A, HEX_B, HEX_C, "chk-abc123")
            self.assertIn("checkpoints", chk.parts)
            self.assertEqual(chk.name, "chk-abc123.json")

            op_dir = paths.journal_operation_dir(HEX_A, HEX_B, HEX_C, "op-abc123")
            self.assertIn("journal", op_dir.parts)
            self.assertEqual(op_dir.name, "op-abc123")

            rcpt = paths.receipt_path(HEX_A, HEX_B, HEX_C, "rcpt-abc123")
            self.assertIn("receipts", rcpt.parts)

    def test_lock_path_has_no_repo_or_clone_prefix(self):
        with isolated_xdg_roots():
            lp = paths.lock_path(HEX_C)
            self.assertEqual(lp.name, f"{HEX_C}.lock")
            self.assertNotIn(HEX_A, lp.parts)

    def test_registration_path_under_config_root_not_state_root(self):
        with isolated_xdg_roots():
            rp = paths.registration_path(HEX_A, HEX_B)
            self.assertTrue(str(rp).startswith(str(paths.config_root())))
            self.assertFalse(str(rp).startswith(str(paths.state_root())))


if __name__ == "__main__":
    unittest.main()
