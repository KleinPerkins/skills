"""Loads every engine/schemas/*.schema.json and its tests/fixtures/<name>/ directory:
valid.json must be accepted; every other *.json fixture (invalid.json plus any
adversarial-*.json) must be rejected. Auto-discovers schemas so adding a new
schema+fixture pair in a later phase needs no test-file edit.
"""

import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

from engine import schemas_validate as sv  # noqa: E402

SCHEMA_DIR = SKILL_DIR / "engine" / "schemas"
FIXTURE_DIR = SKILL_DIR / "tests" / "fixtures"


def _load(path: Path):
    return json.loads(path.read_text())


class TestSchemas(unittest.TestCase):
    def test_every_schema_file_is_valid_json_schema_shape(self):
        schema_files = sorted(SCHEMA_DIR.glob("*.schema.json"))
        self.assertTrue(schema_files, "no schema files found under engine/schemas/")
        for schema_file in schema_files:
            with self.subTest(schema=schema_file.name):
                schema = _load(schema_file)
                self.assertEqual(schema.get("type"), "object")
                self.assertIs(schema.get("additionalProperties"), False)

    def test_valid_fixture_accepted_per_schema(self):
        schema_files = sorted(SCHEMA_DIR.glob("*.schema.json"))
        for schema_file in schema_files:
            name = schema_file.name[: -len(".schema.json")]
            valid_path = FIXTURE_DIR / name / "valid.json"
            with self.subTest(schema=name):
                self.assertTrue(valid_path.is_file(), f"missing {valid_path}")
                schema = _load(schema_file)
                instance = _load(valid_path)
                try:
                    sv.validate(instance, schema)
                except sv.SchemaValidationError as exc:
                    self.fail(f"{name}/valid.json rejected: {exc.errors}")

    def test_invalid_and_adversarial_fixtures_rejected_per_schema(self):
        schema_files = sorted(SCHEMA_DIR.glob("*.schema.json"))
        found_any_negative_fixture = False
        for schema_file in schema_files:
            name = schema_file.name[: -len(".schema.json")]
            fixture_dir = FIXTURE_DIR / name
            if not fixture_dir.is_dir():
                continue
            schema = _load(schema_file)
            for fixture_path in sorted(fixture_dir.glob("*.json")):
                if fixture_path.name == "valid.json":
                    continue
                found_any_negative_fixture = True
                with self.subTest(schema=name, fixture=fixture_path.name):
                    instance = _load(fixture_path)
                    self.assertFalse(
                        sv.is_valid(instance, schema),
                        f"{name}/{fixture_path.name} unexpectedly validated",
                    )
        self.assertTrue(found_any_negative_fixture, "no invalid/adversarial fixtures found at all")

    def test_every_schema_has_a_fixture_directory(self):
        schema_names = {f.name[: -len(".schema.json")] for f in SCHEMA_DIR.glob("*.schema.json")}
        fixture_names = {d.name for d in FIXTURE_DIR.iterdir() if d.is_dir()}
        missing = schema_names - fixture_names
        self.assertFalse(missing, f"schemas with no fixture directory: {sorted(missing)}")

    def test_current_v1_adversarial_fixtures_present_for_reuse(self):
        # Later phases' privacy-gate tests (Phase 2+) reuse these three fixtures; if any
        # goes missing here, that reuse would silently lose coverage.
        current_dir = FIXTURE_DIR / "current.v1"
        for stem in ("adversarial-oversized-field", "adversarial-extra-key", "adversarial-malformed-digest"):
            with self.subTest(fixture=stem):
                self.assertTrue((current_dir / f"{stem}.json").is_file())


if __name__ == "__main__":
    unittest.main()
