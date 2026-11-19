"""Minimal hand-rolled JSON Schema (draft-07 subset) validator.

Hand-rolled because `python3 -c "import jsonschema"` fails in this build's target
environment (verified before writing this file, per build brief) — the stdlib-only
constraint means we cannot depend on the third-party `jsonschema` package. This
implements ONLY the keywords the schemas in `engine/schemas/` actually use: `type`,
`required`, `additionalProperties: false`, `enum`, `pattern`, `maxLength`, `minItems`,
`maxItems` — plus `properties`/`items`, which are structural traversal, not
validating assertions. Deliberately excluded: `$ref`, `$defs`, `oneOf`/`anyOf`,
`format`, `minLength`, `minimum`/`maximum`, and any other keyword. Every schema file
in this skill sticks to the same closed keyword set so it would also validate
correctly under a real `jsonschema` install if one becomes available later.
"""

from __future__ import annotations

import re
from typing import Any


class SchemaValidationError(Exception):
    """Raised with every violation found, not just the first."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors) or "schema validation failed")


def _type_ok(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        # bool is a subclass of int in Python; a JSON boolean is never an integer.
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "null":
        return value is None
    return True  # unknown type name: nothing in our closed set asserts it, so pass


def _walk(instance: Any, schema: dict, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        return

    if "type" in schema:
        expected = schema["type"]
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(f"{path}: expected type {expected!r}, got {type(instance).__name__}")
            return  # wrong type makes further structural checks meaningless

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']!r}")

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match pattern {schema['pattern']!r}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: length {len(instance)} exceeds maxLength {schema['maxLength']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: {len(instance)} items below minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: {len(instance)} items above maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                _walk(item, item_schema, f"{path}[{i}]", errors)

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} not allowed")
        for key, sub_schema in properties.items():
            if key in instance:
                _walk(instance[key], sub_schema, f"{path}.{key}", errors)


def validate(instance: Any, schema: dict) -> None:
    """Raise SchemaValidationError (with every violation) if instance doesn't conform."""
    errors: list[str] = []
    _walk(instance, schema, "$", errors)
    if errors:
        raise SchemaValidationError(errors)


def is_valid(instance: Any, schema: dict) -> bool:
    try:
        validate(instance, schema)
        return True
    except SchemaValidationError:
        return False
