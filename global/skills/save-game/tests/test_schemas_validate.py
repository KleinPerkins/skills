"""Direct unit tests for the hand-rolled validator itself (engine/schemas_validate.py),
isolated from any concept schema. Covers exactly the closed keyword set it implements:
type, required, additionalProperties:false, enum, pattern, maxLength, minItems, maxItems.
"""

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))

from engine.schemas_validate import SchemaValidationError, is_valid, validate  # noqa: E402


class TestValidatorKeywords(unittest.TestCase):
    def test_type_rejects_wrong_type(self):
        self.assertFalse(is_valid("nope", {"type": "object"}))
        self.assertFalse(is_valid(1, {"type": "string"}))
        self.assertFalse(is_valid(True, {"type": "integer"}))  # bool is not an integer here

    def test_required_flags_missing_property(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
        self.assertTrue(is_valid({"a": "x"}, schema))
        self.assertFalse(is_valid({}, schema))

    def test_additional_properties_false_rejects_unknown_key(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        self.assertTrue(is_valid({"a": "x"}, schema))
        self.assertFalse(is_valid({"a": "x", "b": "y"}, schema))

    def test_enum_restricts_values(self):
        schema = {"type": "string", "enum": ["x", "y"]}
        self.assertTrue(is_valid("x", schema))
        self.assertFalse(is_valid("z", schema))

    def test_pattern_matches_substring(self):
        schema = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
        self.assertTrue(is_valid("a" * 64, schema))
        self.assertFalse(is_valid("not-a-digest", schema))

    def test_max_length_bounds_strings(self):
        schema = {"type": "string", "maxLength": 3}
        self.assertTrue(is_valid("abc", schema))
        self.assertFalse(is_valid("abcd", schema))

    def test_min_and_max_items_bound_arrays(self):
        schema = {"type": "array", "minItems": 1, "maxItems": 2}
        self.assertFalse(is_valid([], schema))
        self.assertTrue(is_valid([1], schema))
        self.assertTrue(is_valid([1, 2], schema))
        self.assertFalse(is_valid([1, 2, 3], schema))

    def test_nested_object_recursion_via_properties(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["inner"],
            "properties": {
                "inner": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["x"],
                    "properties": {"x": {"type": "integer"}},
                }
            },
        }
        self.assertTrue(is_valid({"inner": {"x": 1}}, schema))
        self.assertFalse(is_valid({"inner": {"x": "1"}}, schema))
        self.assertFalse(is_valid({"inner": {"x": 1, "y": 2}}, schema))

    def test_items_recursion_for_arrays(self):
        schema = {"type": "array", "items": {"type": "string", "maxLength": 2}}
        self.assertTrue(is_valid(["ab", "cd"], schema))
        self.assertFalse(is_valid(["ab", "cde"], schema))

    def test_validate_raises_with_all_errors_not_just_first(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["a", "b"],
            "properties": {"a": {"type": "string"}},
        }
        with self.assertRaises(SchemaValidationError) as ctx:
            validate({"c": 1}, schema)
        # missing a, missing b, and unexpected c: three distinct violations.
        self.assertEqual(len(ctx.exception.errors), 3)


if __name__ == "__main__":
    unittest.main()
