#!/usr/bin/env python3
"""Free-text instance/type discovery for local-jobs.

The single source of truth for ``resolve-instance`` scoring. Extracted from
``registry.py`` so the growing discovery surface (the ``resolve-instance`` verb
and unknown-id suggestions in ``instance_type``) has one home and no copy-paste
duplication. Behavior is identical to the prior in-registry implementation —
this module owns the logic; ``registry.py`` imports+delegates.

Registry concerns (loading the registry, running handler verbs) stay in
``registry.py``; this module calls back into them at *call time* only, so the
``registry`` <-> ``resolver`` relationship is free of load-time cycles.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402  (call-time use only; no load-time cycle)


def _score_match(query: str, text: str) -> int:
    """Higher score = better match. 0 = no match."""
    if not query or not text:
        return 0
    q, t = query.lower(), text.lower()
    if q == t:
        return 100
    if t.startswith(q):
        return 80
    if q in t:
        return 50
    return 0


def resolve_instance(query: str, reg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Score instances and registry types against a free-text query."""
    reg = reg or registry.load_registry()
    hits: dict[str, dict[str, Any]] = {}

    def _add(iid: str, jtype: str, score: int, field: str) -> None:
        if score <= 0:
            return
        key = f"{jtype}:{iid}"
        prev = hits.get(key)
        if prev is None or score > prev["score"]:
            hits[key] = {"id": iid, "type": jtype, "score": score, "matched": field}

    for jtype, meta in registry.job_types(reg).items():
        desc = (meta or {}).get("description") or ""
        hdesc = registry.handler_describe(jtype, reg)
        for field, text in (("type", jtype), ("description", desc)):
            sc = _score_match(query, text)
            if sc >= 50 and hdesc.get("cardinality") == "singleton":
                sid = hdesc.get("label_token") or jtype
                _add(sid, jtype, sc, field)
        if hdesc.get("cardinality") == "singleton":
            sid = hdesc.get("label_token") or jtype
            sc = _score_match(query, sid)
            if sc >= 50:
                _add(sid, jtype, sc, "singleton_id")

    for jtype in registry.job_types(reg):
        for inst in registry.collect_for_type(jtype, reg):
            if not isinstance(inst, dict) or inst.get("role") == "error":
                continue
            iid = inst.get("id") or ""
            for field in ("id", "path", "program", "launchd_label"):
                val = inst.get(field)
                if isinstance(val, str):
                    sc = _score_match(query, val)
                    if sc > 0:
                        _add(iid, jtype, sc, field)

    ranked = sorted(hits.values(), key=lambda h: (-h["score"], h["id"]))
    return ranked
