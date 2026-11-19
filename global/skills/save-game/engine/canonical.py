"""Canonical JSON serialization and digest computation.

The canonical digest is SHA-256 over canonical JSON of semantic fields only. Per
the plan's v2-hardened digest-invariance rule, it excludes the digest field itself
(`current_digest`) and volatile observation metadata: `created_at`, `updated_at`,
each authority pointer's `observed_at`, and each live-ref's `freshness` class —
wherever those keys appear, at any nesting depth. A refreshed observation with
unchanged revisions therefore yields an unchanged digest; changed revisions still
change it, because `revision`/`digest`/`locator` etc. are NOT in the excluded set.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

VOLATILE_KEYS = {"created_at", "updated_at", "observed_at", "freshness"}


def canonical_bytes(obj: Any) -> bytes:
    """Stable key ordering, no insignificant whitespace, ASCII-escaped."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def digest_active_state(doc: dict) -> str:
    """SHA-256 over the semantic-only projection of an active-state document.

    Excludes `current_digest` itself (the digest field) plus every volatile key
    anywhere in the structure. Callers must pass the document with `generation`
    and `previous_digest` already set to whatever value they want reflected —
    this function hashes exactly what it is given, per the plan's literal list of
    exclusions (no additional fields are treated as volatile beyond that list).
    """
    semantic = {k: v for k, v in doc.items() if k != "current_digest"}
    semantic = _strip_volatile(semantic)
    return sha256_hex(canonical_bytes(semantic))
