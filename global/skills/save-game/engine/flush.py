"""The Flush contract (plan: "1. Flush").

Wires together environment/lock preconditions, the append-only recovery
transaction, the Index contract, and Compact Decision into one call that
returns a schema-valid `save-game-flush-receipt/v1`. Scope/marginal-budget
CLASSIFICATION (which facts are durable/ephemeral/derivable, cumulative
marginal-scope accounting) is Phase 3a's behavior-rule domain; this contract
persists exactly the candidate `build_candidate_fn` hands it, already
schema-validated and privacy-scanned by the transaction layer.
"""

from __future__ import annotations

from typing import Callable, Optional

from . import canonical, compact_decision as cd, durability, identity as identity_mod, ids, index, lock, paths, schemas, transaction

_NEG_SAVED = (
    "SAVED means private bytes were durability-certified; it never means "
    "Git-delivered, cross-machine, compacted, or worktree-retained."
)
_NEG_NOT_SAVED = "This status means nothing new was durably saved this call; it never implies data loss of any prior save."
_NEG_NO_DELTA = "NO_DURABLE_DELTA means the observation was refreshed with no semantic change; nothing new was written this call."

_RECOVERY_STATUS_MAP = {
    "recovery_blocked": "RECOVERY_BLOCKED",
    "recovery_conflict": "RECOVERY_CONFLICT",
    "recovery_required": "RECOVERY_REQUIRED",
    "privacy_block": "PRIVACY_BLOCK",
}


def _is_adopted(repo_key: str, clone_key: str) -> bool:
    return paths.registration_path(repo_key, clone_key).is_file()


def _receipt(
    workstream_key: str,
    status: str,
    *,
    receipt_id: Optional[str] = None,
    saved=(),
    omitted=(),
    refused=(),
    stale=(),
    reconciliation_required: bool = False,
    checkpoint_id: Optional[str] = None,
    negative_claims: Optional[list] = None,
) -> dict:
    if negative_claims is None:
        negative_claims = [_NEG_NO_DELTA] if status == "NO_DURABLE_DELTA" else (
            [_NEG_SAVED] if status in ("SAVED", "SAVED_PRIVATE_UNADOPTED") else [_NEG_NOT_SAVED]
        )
    doc = {
        "schema": "save-game-flush-receipt/v1",
        "receipt_id": receipt_id or ids.new_receipt_id(),
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "status": status,
        "saved": list(saved)[:10],
        "omitted": list(omitted)[:10],
        "refused": list(refused)[:10],
        "stale": list(stale)[:10],
        "reconciliation_required": reconciliation_required,
        "negative_claims": negative_claims[:5],
    }
    if checkpoint_id:
        doc["checkpoint_id"] = checkpoint_id
    schemas.validate_as(doc, "flush-receipt.v1")
    return doc


def run_flush(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    identity: identity_mod.RootIdentity,
    build_candidate_fn: Callable[[Optional[dict]], dict],
    client_id: str = "unknown",
    expected_current_digest: Optional[str] = None,
    compact_inputs: Optional[cd.CompactDecisionInputs] = None,
    authority_conflict: bool = False,
    lock_timeout: float = 10.0,
) -> dict:
    """Entry point for `save-game flush`. Caller supplies `build_candidate_fn`
    (semantic-fields-only candidate builder — see `transaction.begin_transaction`)
    and, when known, the digest the caller believes is current (stale values are
    reported as `RECOVERY_REQUIRED`, never silently overwritten).

    `authority_conflict=True` is the caller's own pre-flight signal that a live
    authority (e.g. two roots claiming the same workstream) is unresolved —
    detecting THAT conflict is Phase 3a's scope/authority behavior-rule domain;
    Flush itself only refuses to proceed once told."""
    if authority_conflict:
        return _receipt(workstream_key, "AUTHORITY_CONFLICT")

    try:
        durability.assert_environment_safe(paths.state_root())
    except durability.UnsupportedEnvironmentError:
        return _receipt(workstream_key, "UNSUPPORTED_ENVIRONMENT")

    try:
        with lock.workstream_lock(workstream_key, timeout=lock_timeout):
            return _run_flush_locked(
                repo_key, clone_key, workstream_key,
                identity=identity, build_candidate_fn=build_candidate_fn, client_id=client_id,
                expected_current_digest=expected_current_digest, compact_inputs=compact_inputs,
            )
    except lock.LockTimeoutError:
        return _receipt(workstream_key, "LOCK_BUSY")


def _run_flush_locked(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    identity: identity_mod.RootIdentity,
    build_candidate_fn: Callable[[Optional[dict]], dict],
    client_id: str,
    expected_current_digest: Optional[str],
    compact_inputs: Optional[cd.CompactDecisionInputs],
) -> dict:
    begin = transaction.begin_transaction(
        repo_key, clone_key, workstream_key,
        build_candidate_fn=build_candidate_fn, identity=identity,
        expected_current_digest=expected_current_digest,
    )

    if begin.status in _RECOVERY_STATUS_MAP:
        return _receipt(
            workstream_key, _RECOVERY_STATUS_MAP[begin.status],
            reconciliation_required=begin.status != "privacy_block",
        )

    if begin.status == "no_durable_delta":
        return _receipt(workstream_key, "NO_DURABLE_DELTA")

    assert begin.status == "proceed"
    active_state = begin.validated_candidate

    if compact_inputs is not None:
        compaction = cd.evaluate(compact_inputs).as_checkpoint_compaction()
    else:
        compaction = {"status": "unknown", "pressure_source": "unknown"}

    checkpoint_id = ids.new_checkpoint_id()
    checkpoint_doc = index.build_checkpoint(active_state, checkpoint_id=checkpoint_id, compaction=compaction, client_id=client_id)
    durability.create_exclusive_durable(
        paths.checkpoint_path(repo_key, clone_key, workstream_key, checkpoint_id),
        canonical.canonical_bytes(checkpoint_doc),
    )

    # Step 8 (re-read branch/HEAD/operation markers) happens here, once, so the
    # SAME boolean both lands in the receipt below and is handed to
    # finalize_transaction — never two independent live-git reads that could
    # theoretically disagree with each other.
    reconcile_required = transaction.check_reconcile_required(identity)

    receipt_id = ids.new_receipt_id()
    status = "SAVED" if _is_adopted(repo_key, clone_key) else "SAVED_PRIVATE_UNADOPTED"
    receipt = _receipt(
        workstream_key, status, receipt_id=receipt_id,
        saved=[f"active state (generation {active_state['generation']})"],
        checkpoint_id=checkpoint_id, reconciliation_required=reconcile_required,
    )
    # Durably create the receipt BEFORE finalized.json, matching the plan's step
    # 9 ("finalized.json pointing to checkpoint AND RECEIPT") and the same order
    # crash-recovery reconstruction uses: `finalized.json` must never point to a
    # receipt that doesn't durably exist yet.
    durability.create_exclusive_durable(
        paths.receipt_path(repo_key, clone_key, workstream_key, receipt_id),
        canonical.canonical_bytes(receipt),
    )

    transaction.finalize_transaction(
        repo_key, clone_key, workstream_key,
        operation_id=begin.operation_id, checkpoint_id=checkpoint_id, receipt_id=receipt_id,
        new_digest=begin.new_digest, identity_at_start=identity, reconcile_required=reconcile_required,
    )
    return receipt
