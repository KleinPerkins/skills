"""Loads `engine/schemas/<name>.schema.json` files and validates documents against
them via Phase 1's `schemas_validate` validator. Every persisted JSON document in
this engine must go through `validate_as` before being treated as durably written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import schemas_validate as sv

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

_cache: dict[str, dict] = {}


def load_schema(name: str) -> dict:
    """`name` is the schema id without `.schema.json`, e.g. `current.v1`."""
    if name not in _cache:
        path = SCHEMA_DIR / f"{name}.schema.json"
        _cache[name] = json.loads(path.read_text())
    return _cache[name]


def validate_as(instance: Any, name: str) -> None:
    """Raises `schemas_validate.SchemaValidationError` (all violations, not just
    the first) if `instance` does not conform to schema `name`."""
    sv.validate(instance, load_schema(name))
