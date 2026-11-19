import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _support import isolated_xdg_roots  # noqa: E402

from engine import lock  # noqa: E402

WS_KEY = "d" * 64


class TestWorkstreamLock(unittest.TestCase):
    def test_acquire_and_release(self):
        with isolated_xdg_roots():
            with lock.workstream_lock(WS_KEY, timeout=1.0):
                pass  # no exception == acquired and released cleanly

    def test_second_acquirer_times_out_while_first_holds(self):
        with isolated_xdg_roots():
            with lock.workstream_lock(WS_KEY, timeout=1.0):
                with self.assertRaises(lock.LockTimeoutError):
                    with lock.workstream_lock(WS_KEY, timeout=0.2):
                        pass  # pragma: no cover - should never acquire

    def test_lock_is_reacquirable_after_release(self):
        with isolated_xdg_roots():
            with lock.workstream_lock(WS_KEY, timeout=1.0):
                pass
            with lock.workstream_lock(WS_KEY, timeout=1.0):
                pass  # proves release actually happened

    def test_different_workstreams_do_not_contend(self):
        with isolated_xdg_roots():
            with lock.workstream_lock("e" * 64, timeout=1.0):
                with lock.workstream_lock("f" * 64, timeout=0.2):
                    pass  # different key: must not raise LockTimeoutError

    def test_lock_file_is_private_permissions(self):
        with isolated_xdg_roots():
            from engine import durability, paths

            with lock.workstream_lock(WS_KEY, timeout=1.0):
                pass
            mode = paths.lock_path(WS_KEY).stat().st_mode & 0o777
            self.assertEqual(mode, durability.FILE_MODE)


if __name__ == "__main__":
    unittest.main()
