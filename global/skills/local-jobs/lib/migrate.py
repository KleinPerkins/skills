#!/usr/bin/env python3
"""Load-time forward migration for local-jobs job-type data (P1-3).

ONE default-resolution policy for every type: **re-merge-at-load**. Whenever a
store is read, the type's declared optional-field defaults are merged into each
instance and the store's ``schema_version`` is stamped forward. This is what
lets a type evolve without bricking existing instances:

  - **add a field** → existing instances pick up its default at load;
  - **remove a field** → the now-unknown key is simply ignored (never orphans
    or hard-rejects the instance);
  - **bump schema_version** → recorded; instances keep loading (no hard reject
    like the old ``version != 1`` guard).

A type that needs a structural transform beyond defaults passes a small
``transforms`` map (``{from_version: callable}``); the generic path covers
add/remove-field + version bumps with no per-type code.
"""

from __future__ import annotations

from typing import Any, Callable


def forward_migrate(
    data: dict[str, Any],
    schema_version: int,
    field_defaults: dict[str, Any] | None = None,
    transforms: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return ``(data, changed)`` after re-merging defaults + stamping version.

    Idempotent: running it again on already-current data reports ``changed=False``.
    """
    field_defaults = field_defaults or {}
    transforms = transforms or {}
    changed = False

    current = data.get("schema_version", 1)
    instances = data.get("instances") or []
    for entry in instances:
        if not isinstance(entry, dict):
            continue
        # Run any structural transforms for versions strictly behind current.
        v = int(entry.get("_schema_version", current) or current)
        while v < schema_version and v in transforms:
            transforms[v](entry)
            v += 1
            changed = True
        if entry.get("_schema_version") not in (None, schema_version):
            entry["_schema_version"] = schema_version
            changed = True
        # Single policy: re-merge declared defaults for any missing optional field.
        for key, default in field_defaults.items():
            if key not in entry:
                entry[key] = default
                changed = True

    if current != schema_version:
        changed = True
    data["schema_version"] = schema_version
    data.setdefault("instances", instances)
    return data, changed
