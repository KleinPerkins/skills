"""The Index contract (plan: "2. Index").

Builds the immutable `save-game-checkpoint/v1` from an already-persisted
active-state document, and resolves the correct checkpoint for a workstream
when several exist (enumerate `finalized.json` records, sort by embedded
active-state generation, select the maximum; an unresolved tie is
`CHECKPOINT_AMBIGUOUS`, per v2 hardening).
"""

from __future__ import annotations

import json
from typing import Optional

from . import durability, ids, paths, schemas

_VALID_CLIENT_IDS = {"cursor", "claude", "codex", "unknown"}
_PRECEDENCE_NOTICE = "Live canonical sources override this checkpoint; it is an index, never authority."


def _truncated(text: str, limit: int) -> str:
    text = (text or "").strip() or "(none)"
    return text[:limit]


def _scope_summary(active_state: dict) -> str:
    items = active_state.get("scope", {}).get("in_scope", [])
    joined = "; ".join(item.get("summary", "") for item in items if item.get("summary"))
    return _truncated(joined or "(no active scope recorded)", 200)


def hygiene_summary(hygiene: dict) -> str:
    # unclassified_delta is inverted (True is the BAD state); the other four flags are bad when False.
    bad = [k for k in ("transactions_finalized", "temp_artifacts_clear", "repo_status_observed", "required_checks_run") if not hygiene.get(k, False)]
    if hygiene.get("unclassified_delta", False):
        bad.append("unclassified_delta")
    if not bad:
        return "hygiene clear"
    return _truncated("pending: " + ", ".join(bad), 150)


def _collect_authority_pointers(active_state: dict) -> list[dict]:
    pointers: list[dict] = []
    plan_pointer = active_state.get("plan_pointer")
    if plan_pointer and "authority" in plan_pointer:
        pointers.append(plan_pointer["authority"])
    for decision in active_state.get("decisions", []):
        if decision.get("status") == "accepted" and "authority" in decision:
            pointers.append(decision["authority"])
    for blocker in active_state.get("blockers", []):
        if "authority" in blocker:
            pointers.append(blocker["authority"])
    return pointers[:10]


def build_checkpoint(
    active_state: dict,
    *,
    checkpoint_id: str,
    compaction: dict,
    client_id: str = "unknown",
) -> dict:
    """Builds and schema-validates one immutable checkpoint. Does not persist
    it — callers durably create it (O_EXCL) via `paths.checkpoint_path`."""
    if client_id not in _VALID_CLIENT_IDS:
        client_id = "unknown"

    doc: dict = {
        "schema": "save-game-checkpoint/v1",
        "checkpoint_id": checkpoint_id,
        "workstream_key": active_state["workstream_key"],
        "client_id": client_id,
        "created_at": ids.now_iso(),
        "expiry_class": "unresolved",
        "active_state_generation": active_state["generation"],
        "active_state_digest": active_state["current_digest"],
        "objective": _truncated(active_state.get("objective"), 200),
        "scope_summary": _scope_summary(active_state),
        "done": [],  # behavior-rule "done" tracking is Phase 3a's domain; left empty here, never invented
        "blockers": [{"summary": _truncated(b["description"], 150)} for b in active_state.get("blockers", [])[:3]],
        "next_actions": [{"description": _truncated(a["description"], 150)} for a in active_state.get("next_actions", [])[:3]],
        "compaction": compaction,
        "canonical_precedence_notice": _PRECEDENCE_NOTICE,
    }
    authority_pointers = _collect_authority_pointers(active_state)
    if authority_pointers:
        doc["authority_pointers"] = authority_pointers
    if "current_action" in active_state:
        doc["active_action"] = {"description": _truncated(active_state["current_action"]["description"], 150)}
    hygiene_text = hygiene_summary(active_state.get("hygiene", {}))
    if hygiene_text:
        doc["hygiene_summary"] = hygiene_text
    if "working_hypothesis" in active_state:
        doc["working_hypothesis"] = {"statement": _truncated(active_state["working_hypothesis"]["statement"], 150)}

    schemas.validate_as(doc, "checkpoint.v1")
    return doc


def resolve_checkpoint(repo_key: str, clone_key: str, workstream_key: str) -> tuple[Optional[dict], bool]:
    """Returns (checkpoint_or_None, ambiguous). `ambiguous=True` means more than
    one incomparable maximum-generation checkpoint was found (ties at the same
    embedded active_state_generation) — callers must surface CHECKPOINT_AMBIGUOUS
    rather than silently pick one; the returned checkpoint is then only a
    bounded example for the operator choice, not the resolved answer."""
    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    if not journal_dir.is_dir():
        return None, False

    candidates: list[tuple[int, dict]] = []
    for entry in sorted(journal_dir.iterdir()):
        if entry.name == "quarantine":
            continue
        finalized_path = entry / "finalized.json"
        if not finalized_path.is_file():
            continue
        try:
            finalized = json.loads(durability.read_file_bytes(finalized_path))
            schemas.validate_as(finalized, "journal-finalized.v1")
            checkpoint_doc = json.loads(
                durability.read_file_bytes(
                    paths.checkpoint_path(repo_key, clone_key, workstream_key, finalized["checkpoint_id"])
                )
            )
            schemas.validate_as(checkpoint_doc, "checkpoint.v1")
        except Exception:
            # Malformed finalized/checkpoint evidence here doesn't block Reconcile —
            # Flush/recovery already gate what gets written; a bad record just
            # drops out of the enumeration rather than crashing resolution.
            continue
        candidates.append((checkpoint_doc["active_state_generation"], checkpoint_doc))

    if not candidates:
        return None, False
    max_generation = max(generation for generation, _ in candidates)
    at_max = [doc for generation, doc in candidates if generation == max_generation]
    if len(at_max) > 1:
        return at_max[0], True
    return at_max[0], False
