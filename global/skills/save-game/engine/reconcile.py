"""The Reconcile contract (plan: "4. Reconcile").

Bounded live-source reads, conflict classification (MATCH/ADVANCED/STALE/
CONFLICT/UNKNOWN plus CHECKPOINT_AMBIGUOUS), and the v2-hardened persistence
rule: ADVANCED/STALE refresh the cache and auto-repair marginal drift but
create no new checkpoint and change no operator-owned durable field without
explicit save intent — a purely read-only resume never triggers a Flush.

This module implements the MECHANICAL contract (bounded reads, checkpoint
resolution, root/ref/HEAD-based classification, receipt rendering). The
richer scope/marginality/blocker/hygiene/autonomy BEHAVIOR rules that decide
exactly which marginal drift is auto-repairable, and how next actions are
derived, are Phase 3a's domain — deliberately out of scope here.
"""

from __future__ import annotations

from typing import Optional

from . import identity as identity_mod, ids, index, schemas, transaction

_VALID_TRIGGERS = {
    "post_compaction_evidence", "expected_compaction_command", "new_chat", "resume",
    "agent_replacement", "root_change", "branch_change", "worktree_change", "head_change",
    "git_operation_marker_change", "active_state_digest_change", "multiple_checkpoints",
    "stale_volatile_reference", "incomplete_transaction", "missing_recent_receipt",
    "pre_first_mutation_after_resume",
}

_NEVER_REPLAYS_HISTORY = "Never replays completed journal history to reconstruct current truth."


def _truncated(text: str, limit: int) -> str:
    text = (text or "").strip() or "(none)"
    return text[:limit]


def _classify_root(current: Optional[dict], fresh_identity: identity_mod.RootIdentity) -> str:
    if current is None:
        return "UNKNOWN"
    root = current.get("root", {})
    if fresh_identity.operation_marker != "none":
        # Mid-merge/rebase/cherry-pick/revert/bisect: branch/HEAD-sensitive
        # verification is always stale and is never auto-repaired.
        return "STALE"
    if root.get("branch") != fresh_identity.branch:
        return "STALE"
    if root.get("observed_head") == fresh_identity.observed_head[:64]:
        return "MATCH"
    return "ADVANCED"  # same branch, HEAD moved forward: accept the newer live revision


def run_reconcile(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    identity: identity_mod.RootIdentity,
    triggers: list[str],
) -> dict:
    """Caller should hold the workstream lock only long enough to read; this
    contract itself never mutates `current.json` or creates a checkpoint."""
    triggers = [t for t in triggers if t in _VALID_TRIGGERS] or ["resume"]

    classifications: list[dict] = []
    blockers: list[dict] = []
    repairs: list[str] = []
    sources_read: list[dict] = []

    # Step 1: resolve one checkpoint by the Index enumeration rule.
    checkpoint, ambiguous = index.resolve_checkpoint(repo_key, clone_key, workstream_key)
    if ambiguous:
        classifications.append({"claim": "checkpoint_resolution", "result": "CONFLICT"})
        blockers.append({"summary": "Multiple checkpoints tie at the same generation (CHECKPOINT_AMBIGUOUS); choose by objective, ref, or time."})

    # Step 2: recover only incomplete operation directories for this workstream.
    recovery_records = transaction.recover_workstream(repo_key, clone_key, workstream_key)
    for record in recovery_records:
        if record.outcome == transaction.RecoveryOutcome.BLOCKED:
            classifications.append({"claim": f"operation:{record.operation_id}", "result": "CONFLICT"})
            blockers.append({"summary": _truncated(f"Operation {record.operation_id} evidence is unsafe; needs explicit quarantine.", 150)})
        elif record.outcome == transaction.RecoveryOutcome.CONFLICT:
            classifications.append({"claim": f"operation:{record.operation_id}", "result": "CONFLICT"})
            blockers.append({"summary": _truncated(f"Operation {record.operation_id} digest matches neither prior state; needs review.", 150)})
        elif record.outcome in (transaction.RecoveryOutcome.ABORTED, transaction.RecoveryOutcome.RECONSTRUCTED):
            repairs.append(_truncated(f"Recovered operation {record.operation_id} ({record.outcome}).", 150))

    # Step 3: read current active state and only named plan/decision/task sections/IDs.
    current = transaction.read_current(repo_key, clone_key, workstream_key)
    if current is not None:
        sources_read.append({"kind": "code", "locator": f"save-game-current/{workstream_key}", "observed_at": ids.now_iso()})

    # Step 5: inspect live root/common-dir/git-dir/ref/HEAD/status/operation markers.
    fresh_identity = identity_mod.resolve_root_identity(identity.physical_root)
    sources_read.append({"kind": "git_ref", "locator": f"HEAD@{fresh_identity.physical_root}", "observed_at": ids.now_iso()})

    # Step 8: classify each claim.
    root_result = _classify_root(current, fresh_identity)
    classifications.append({"claim": "root_ref_head", "result": root_result})
    if root_result in ("ADVANCED", "STALE") and current is not None:
        repairs.append("Refreshed the observed root/ref/HEAD cache; no new checkpoint was created and no durable field changed.")

    # Under correct operation these always match: every Flush creates its
    # checkpoint from the SAME transaction that replaces current.json, and
    # step 2 above already recovered any interrupted operation. A mismatch here
    # is therefore always an anomaly worth a bounded evidence pass (UNKNOWN),
    # never a guessed ADVANCED/STALE direction.
    if current is not None and checkpoint is not None:
        digest_result = "MATCH" if current.get("current_digest") == checkpoint.get("active_state_digest") else "UNKNOWN"
        classifications.append({"claim": "active_state_vs_checkpoint_digest", "result": digest_result})

    goal = _truncated((current or {}).get("objective") or (checkpoint or {}).get("objective") or "(no active state recorded yet)", 200)
    hygiene = (current or {}).get("hygiene", {})
    hygiene_text = index.hygiene_summary(hygiene) if current is not None else "no active state recorded"
    next_actions = [{"description": _truncated(a["description"], 150)} for a in (current or {}).get("next_actions", [])[:3]]

    any_conflict = any(c["result"] == "CONFLICT" for c in classifications)
    if any_conflict and not blockers:
        blockers.append({"summary": "A classification conflict was found; stop before mutation and request the smallest operator-owned decision."})

    doc = {
        "schema": "save-game-reconcile-receipt/v1",
        "receipt_id": ids.new_receipt_id(),
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "triggers": triggers,
        "sources_read": sources_read,
        "classifications": classifications,
        "goal": goal,
        "hygiene_summary": _truncated(hygiene_text, 150),
        "blockers": blockers[:5],
        "next_actions": next_actions,
        "negative_claims": [
            "Refreshing this cache is not a save: it never means a new checkpoint was created or that a durable field changed without explicit save intent.",
            _NEVER_REPLAYS_HISTORY,
        ],
    }
    if repairs:
        doc["repairs"] = repairs[:10]
    schemas.validate_as(doc, "reconcile-receipt.v1")
    return doc
