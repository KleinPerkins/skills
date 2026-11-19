"""Read-only curation of a workstream's promotion candidates (plan:
"Curation into preferences / ecosystem policy / product requirements /
live-system documentation").

Promotion candidates recorded on active state are READ-ONLY PROPOSALS. This
module never writes to any actual preference file, ecosystem-policy document,
product-requirement tracker, or live-system doc -- promotion always happens
through each destination's own governed workflow, never here. `curate()`
performs ZERO filesystem writes of any kind (not merely "none outside
save-game private state" -- literally none: it only ever reads `current.json`
and returns an in-memory report), which is the strongest and simplest way to
satisfy that constraint, and is asserted directly by a dedicated test.
"""

from __future__ import annotations

from . import ids, schemas, transaction

DESTINATION_CLASSES = ("preference", "ecosystem_policy", "product_requirement", "live_system_doc", "other")


def _enrich_candidate(compact: dict, *, workstream_key: str, current_doc: dict) -> dict:
    """`current.v1`'s embedded `promotion_candidates` entries are a COMPACT
    projection (`candidate_id`/`destination_class`/`summary`/`status`, plus an
    optional `authority`) -- missing the `rationale`/`owner`/`target_authority`
    that the standalone `promotion-candidate.v1` record requires. This maps
    compact -> full for DISPLAY and schema-validation purposes only, with
    reasonable ship-don't-perfect substitutions for fields the compact shape
    never carried in the first place (each documented inline below); the
    result is never persisted anywhere."""
    authority = compact.get("authority")
    target_authority = authority or {
        "kind": "other",
        "locator": f"workstream:{workstream_key}",
        "observed_at": current_doc["updated_at"],
    }
    doc = {
        "schema": "save-game-promotion-candidate/v1",
        "candidate_id": compact["candidate_id"],
        "workstream_key": workstream_key,
        # Compact shape carries no per-candidate timestamp; the active-state
        # document's own updated_at is the closest honest proxy available.
        "created_at": current_doc["updated_at"],
        "destination_class": compact["destination_class"],
        "target_authority": target_authority,
        # Compact shape has no separate rationale field; its summary IS the
        # short rationale for promotion.
        "rationale": compact["summary"],
        # Compact shape carries no owner, and curation must never assign one
        # on the operator's behalf -- "unassigned" is an explicit placeholder.
        "owner": "unassigned",
        "status": compact["status"],
    }
    if authority:
        doc["evidence"] = [authority]
    schemas.validate_as(doc, "promotion-candidate.v1")
    return doc


def curate(repo_key: str, clone_key: str, workstream_key: str) -> dict:
    """Read-only report of one workstream's promotion candidates, grouped by
    destination class, enriched to `promotion-candidate.v1` shape and
    schema-validated for display. Every group key is always present (even
    empty) for a predictable report shape. Returns an all-empty report if
    there is no active state yet for this workstream.

    NEVER writes to preferences, ecosystem policy, product requirements, or
    live-system docs -- promotion out of "proposed" always happens through
    each destination's own governed workflow, never through this function."""
    groups: dict[str, list[dict]] = {cls: [] for cls in DESTINATION_CLASSES}
    current_doc = transaction.read_current(repo_key, clone_key, workstream_key)
    if current_doc is None:
        return {"workstream_key": workstream_key, "generated_at": ids.now_iso(), "groups": groups, "count": 0}

    compacts = current_doc.get("promotion_candidates", [])
    for compact in compacts:
        enriched = _enrich_candidate(compact, workstream_key=workstream_key, current_doc=current_doc)
        groups[enriched["destination_class"]].append(enriched)

    return {
        "workstream_key": workstream_key,
        "generated_at": ids.now_iso(),
        "groups": groups,
        "count": len(compacts),
    }
