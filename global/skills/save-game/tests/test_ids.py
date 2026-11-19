import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import ids  # noqa: E402

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class TestIds(unittest.TestCase):
    def test_generated_ids_match_schema_pattern(self):
        for fn, prefix in (
            (ids.new_task_id, "task"),
            (ids.new_operation_id, "op"),
            (ids.new_checkpoint_id, "chk"),
            (ids.new_receipt_id, "rcpt"),
            (ids.new_candidate_id, "cand"),
            (ids.new_tombstone_id, "tomb"),
        ):
            value = fn()
            with self.subTest(fn=fn.__name__):
                self.assertTrue(SAFE_ID.match(value), value)
                self.assertTrue(value.startswith(prefix + "-"))

    def test_ids_are_collision_resistant_across_many_calls(self):
        generated = {ids.new_operation_id() for _ in range(1000)}
        self.assertEqual(len(generated), 1000)

    def test_now_iso_matches_timestamp_pattern(self):
        self.assertTrue(TIMESTAMP.match(ids.now_iso()))


if __name__ == "__main__":
    unittest.main()
