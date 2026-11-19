import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _support import isolated_xdg_roots  # noqa: E402

from engine import canonical, paths, snapshot  # noqa: E402

REPO_KEY = "a" * 64
CLONE_KEY = "b" * 64
WS_KEY = "c" * 64

DOC = {"schema": "save-game-current/v1", "objective": "test"}


class TestWriteSnapshot(unittest.TestCase):
    def test_write_returns_sha256_of_canonical_bytes(self):
        with isolated_xdg_roots():
            digest = snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, DOC)
            expected = canonical.sha256_hex(canonical.canonical_bytes(DOC))
            self.assertEqual(digest, expected)

    def test_file_created_at_content_addressed_path(self):
        with isolated_xdg_roots():
            digest = snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, DOC)
            p = paths.snapshot_path(REPO_KEY, CLONE_KEY, WS_KEY, digest)
            self.assertTrue(p.is_file())

    def test_identical_content_reused_on_second_write(self):
        with isolated_xdg_roots():
            d1 = snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, DOC)
            d2 = snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, dict(DOC))  # equal but distinct dict
            self.assertEqual(d1, d2)

    def test_read_snapshot_round_trips(self):
        with isolated_xdg_roots():
            digest = snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, DOC)
            loaded = snapshot.read_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, digest)
            self.assertEqual(loaded, DOC)

    def test_eexist_with_mismatched_bytes_fails_closed_as_corrupt(self):
        with isolated_xdg_roots():
            digest = canonical.sha256_hex(canonical.canonical_bytes(DOC))
            p = paths.snapshot_path(REPO_KEY, CLONE_KEY, WS_KEY, digest)
            p.parent.mkdir(parents=True, exist_ok=True)
            # Simulate corrupt/colliding evidence: bytes at the content-addressed
            # path do not match what recomputing the hash of DOC would produce.
            p.write_bytes(b'{"tampered": true}')
            with self.assertRaises(snapshot.CorruptEvidenceError):
                snapshot.write_snapshot(REPO_KEY, CLONE_KEY, WS_KEY, DOC)


if __name__ == "__main__":
    unittest.main()
