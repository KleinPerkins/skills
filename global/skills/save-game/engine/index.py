"""The Index contract (plan: "2. Index").

Builds the immutable `save-game-checkpoint/v1` from an already-persisted
active-state document, and resolves the correct checkpoint for a workstream
when several exist (enumerate `finalized.json` records, sort by embedded
active-state generation, select the maximum; an unresolved tie is
`CHECKPOINT_AMBIGUOUS`, per v2 hardening).
"""

from __future__ import annotations

import json
import stat
from datetime import datetime
from itertools import islice
from typing import Optional

from . import canonical, durability, ids, paths, schemas

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


class IncompleteJournalError(ValueError):
    """An operation has no terminal record and needs owner recovery."""


class UnadoptedCheckpointError(ValueError):
    """The selected checkpoint predates enabled adoption."""


def _strict_journal_record(path, schema: str) -> dict:
    raw = durability.read_file_bytes(path)
    value = json.loads(raw)
    schemas.validate_as(value, schema)
    if raw != canonical.canonical_bytes(value):
        raise ValueError("noncanonical observation record")
    return value


def _strict_finalized(entry, workstream_key: str) -> tuple[dict, dict] | None:
    if not paths.SAFE_ID.fullmatch(entry.name) or not stat.S_ISDIR(entry.lstat().st_mode):
        raise ValueError("invalid journal operation")
    names = {name.name for name in entry.iterdir()}
    prepared = _strict_journal_record(entry / "prepared.json", "journal-prepared.v1")
    if prepared["operation_id"] != entry.name or prepared["workstream_key"] != workstream_key:
        raise ValueError("journal operation has the wrong identity")
    if names == {"prepared.json"}:
        raise IncompleteJournalError("operation needs recovery")
    if names == {"prepared.json", "aborted.json"}:
        aborted = _strict_journal_record(entry / "aborted.json", "journal-aborted.v1")
        if (aborted["operation_id"] != entry.name or aborted["workstream_key"] != workstream_key
                or aborted["old_digest"] != prepared["old_digest"]
                or aborted["attempted_new_digest"] != prepared["new_digest"]):
            raise ValueError("inconsistent aborted journal operation")
        return None
    if names != {"prepared.json", "finalized.json"}:
        raise ValueError("invalid journal operation phases")
    finalized = _strict_journal_record(entry / "finalized.json", "journal-finalized.v1")
    if (finalized["operation_id"] != entry.name or finalized["workstream_key"] != workstream_key
            or finalized["new_digest"] != prepared["new_digest"]):
        raise ValueError("inconsistent finalized journal operation")
    return finalized, prepared


def _check_prepared_snapshot(scope: tuple[str, str, str], prepared: dict, checkpoint: dict) -> None:
    document = _strict_journal_record(paths.snapshot_path(*scope, prepared["snapshot_digest"]), "current.v1")
    root = {key: value for key, value in document["root"].items() if key != "remote_identity_key"}
    if (canonical.sha256_hex(canonical.canonical_bytes(document)) != prepared["snapshot_digest"]
            or document["workstream_key"] != scope[2] or root != prepared["observed_root"]
            or document.get("previous_digest", "none") != prepared["old_digest"]
            or document["generation"] != checkpoint["active_state_generation"]
            or document["current_digest"] != checkpoint["active_state_digest"]
            or canonical.digest_active_state(document) != document["current_digest"]):
        raise ValueError("prepared operation disagrees with its snapshot")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve_checkpoint(repo_key: str, clone_key: str, workstream_key: str,
                       *, adopted_since: str | None = None) -> tuple[Optional[dict], bool]:
    """Returns (checkpoint_or_None, ambiguous). `ambiguous=True` means more than
    one incomparable maximum-generation checkpoint was found (ties at the same
    embedded active_state_generation) — callers must surface CHECKPOINT_AMBIGUOUS
    rather than silently pick one; the returned checkpoint is then only a
    bounded example for the operator choice, not the resolved answer."""
    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    if not journal_dir.is_dir():
        return None, False

    strict = adopted_since is not None
    candidates: list[tuple[int, dict, bool]] = []
    lineage: list[tuple[int, str, str]] = []
    if strict and not stat.S_ISDIR(journal_dir.lstat().st_mode):
        raise ValueError("invalid journal directory")
    if strict:
        operations = (entry for entry in journal_dir.iterdir() if entry.name != "quarantine")
        entries = list(islice(operations, 1025))
    else:
        entries = list(journal_dir.iterdir())
    if strict and len(entries) > 1024:
        raise ValueError("journal exceeds observation limit")
    for entry in sorted(entries):
        if entry.name == "quarantine":
            continue
        finalized_path = entry / "finalized.json"
        if strict:
            checked = _strict_finalized(entry, workstream_key)
            if checked is None:
                continue
            finalized, prepared = checked
            generation = prepared["expected_generation"] + 1
            checkpoint_doc = _strict_journal_record(
                paths.checkpoint_path(repo_key, clone_key, workstream_key, finalized["checkpoint_id"]),
                "checkpoint.v1",
            )
            if (checkpoint_doc["checkpoint_id"] != finalized["checkpoint_id"]
                    or checkpoint_doc["workstream_key"] != workstream_key
                    or checkpoint_doc["active_state_digest"] != finalized["new_digest"]
                    or checkpoint_doc["active_state_generation"] != generation):
                raise ValueError("inconsistent finalized checkpoint")
            _check_prepared_snapshot((repo_key, clone_key, workstream_key), prepared, checkpoint_doc)
            receipt = _strict_journal_record(
                paths.receipt_path(repo_key, clone_key, workstream_key, finalized["receipt_id"]),
                "flush-receipt.v1",
            )
            if (receipt["receipt_id"] != finalized["receipt_id"]
                    or receipt["workstream_key"] != workstream_key
                    or receipt.get("checkpoint_id") != finalized["checkpoint_id"]
                    or receipt["reconciliation_required"] != finalized["reconcile_required"]
                    or receipt["status"] not in {"SAVED", "SAVED_PRIVATE_UNADOPTED"}):
                raise ValueError("inconsistent finalized receipt")
            # A legacy SAVED receipt (including a reconstructed receipt) alone
            # cannot distinguish enabled adoption from a disabled registration.
            # Require today's enabled registration to predate even preparation.
            started = _timestamp(prepared["created_at"])
            if _timestamp(receipt["created_at"]) < started:
                raise ValueError("flush receipt predates its operation")
            adopted = receipt["status"] == "SAVED" and _timestamp(adopted_since) < started
            candidates.append((generation, checkpoint_doc, adopted))
            lineage.append((generation, checkpoint_doc["active_state_digest"], prepared["old_digest"]))
            continue
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
        candidates.append((checkpoint_doc["active_state_generation"], checkpoint_doc, True))

    if not candidates:
        return None, False
    max_generation = max(generation for generation, _, _ in candidates)
    at_max = [(doc, saved_adopted) for generation, doc, saved_adopted in candidates if generation == max_generation]
    if len(at_max) > 1:
        return at_max[0][0], True
    if strict:
        generations = {generation: digest for generation, digest, _ in lineage}
        if (len(generations) != len(lineage) or any(
            previous != ("none" if generation == 1 else generations.get(generation - 1))
            for generation, _, previous in lineage
        )):
            raise ValueError("inconsistent checkpoint generation lineage")
    checkpoint, saved_adopted = at_max[0]
    if not saved_adopted:
        raise UnadoptedCheckpointError("checkpoint predates adoption")
    return checkpoint, False
