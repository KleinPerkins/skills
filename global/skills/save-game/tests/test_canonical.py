import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import canonical  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CURRENT_V1_VALID = SKILL_DIR / "tests" / "fixtures" / "current.v1" / "valid.json"


class TestCanonicalBytes(unittest.TestCase):
    def test_key_order_does_not_affect_bytes(self):
        a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
        b = {"a": 2, "c": {"y": 2, "z": 1}, "b": 1}
        self.assertEqual(canonical.canonical_bytes(a), canonical.canonical_bytes(b))

    def test_bytes_have_no_insignificant_whitespace(self):
        data = canonical.canonical_bytes({"a": 1, "b": [1, 2]})
        self.assertNotIn(b" ", data)

    def test_sha256_hex_is_deterministic_and_correct_length(self):
        digest = canonical.sha256_hex(b"hello")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, canonical.sha256_hex(b"hello"))
        self.assertNotEqual(digest, canonical.sha256_hex(b"hello!"))


class TestDigestActiveStateInvariance(unittest.TestCase):
    """The plan's required proof: two documents differing ONLY in volatile
    observation metadata (created_at/updated_at/observed_at/freshness) and the
    digest field itself must produce the SAME semantic digest."""

    def setUp(self):
        self.base_doc = json.loads(CURRENT_V1_VALID.read_text())

    def test_volatile_only_changes_yield_same_digest(self):
        doc1 = copy.deepcopy(self.base_doc)
        doc2 = copy.deepcopy(self.base_doc)

        doc2["created_at"] = "2099-01-01T00:00:00Z"
        doc2["updated_at"] = "2099-01-01T00:00:01Z"
        doc2["live_refs"][0]["authority"]["observed_at"] = "2099-01-01T00:00:02Z"
        doc2["live_refs"][0]["freshness"] = "stale"
        doc2["decisions"][0]["authority"]["observed_at"] = "2099-06-06T00:00:00Z"
        doc2["current_digest"] = "9" * 64  # the digest field itself must also be excluded

        digest1 = canonical.digest_active_state(doc1)
        digest2 = canonical.digest_active_state(doc2)
        self.assertEqual(digest1, digest2)

    def test_semantic_change_does_change_digest(self):
        doc1 = copy.deepcopy(self.base_doc)
        doc2 = copy.deepcopy(self.base_doc)
        doc2["objective"] = "A materially different objective statement."

        self.assertNotEqual(
            canonical.digest_active_state(doc1),
            canonical.digest_active_state(doc2),
        )

    def test_revision_change_on_a_pointer_does_change_digest(self):
        doc1 = copy.deepcopy(self.base_doc)
        doc2 = copy.deepcopy(self.base_doc)
        doc2["decisions"][0]["authority"]["revision"] = "v3"

        self.assertNotEqual(
            canonical.digest_active_state(doc1),
            canonical.digest_active_state(doc2),
        )

    def test_digest_is_64_char_hex(self):
        digest = canonical.digest_active_state(self.base_doc)
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # raises if not valid hex


if __name__ == "__main__":
    unittest.main()
