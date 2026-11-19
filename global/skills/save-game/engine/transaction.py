"""The append-only recovery transaction (plan: "Append-only recovery transaction").

Every Flush runs this under one workstream lock: recover/classify any incomplete
prior operation, CAS-check the caller's expectation against the live current
digest, privacy-scan and schema-validate the candidate, write a content-addressed
snapshot, durably create `prepared.json`, atomically replace `current.json`, then
(after the caller runs Index) durably create `finalized.json`. v2 removed the
redundant `committed.json` phase: recovery decides purely from `prepared.json`
plus the observed current digest.

Phase files are immutable and exclusive-created (`O_EXCL`). Recovery is
idempotent and deterministic:

- `prepared` exists, current digest == old: the replace never happened ->
  append `aborted.json`; leave `current.json` untouched.
- `prepared` exists, current digest == new: the replace succeeded but
  finalize did not run -> synthesize the missing checkpoint/finalized records.
- current digest matches neither: `RECOVERY_CONFLICT`, never overwrite.
- malformed/escaping/symlinked/special-file/permission-unsafe/unknown evidence:
  `RECOVERY_BLOCKED`, fails closed, artifacts are preserved untouched (recovery
  itself never quarantines — quarantine is a separate, explicit operator action;
  see `quarantine_operation`).

This module intentionally does not depend on the real Index contract (Phase 2
slice 3): a crash-recovery reconstruction that is missing its checkpoint
synthesizes a MINIMAL schema-valid one directly from the active-state document
so recovery stays self-contained and testable on its own. The normal (non-crash)
path always uses the real Index contract instead.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import canonical, durability, ids, identity as identity_mod, paths, privacy, schemas, snapshot
from .schemas_validate import SchemaValidationError

_ALLOWED_OP_FILES = {"prepared.json", "aborted.json", "finalized.json"}


class CurrentStateCorruptError(RuntimeError):
    """`current.json` exists but is unreadable/invalid. Never guess its content;
    callers must treat this the same as RECOVERY_BLOCKED evidence."""


class RecoveryOutcome:
    NONE = "none"
    ABORTED = "aborted"
    RECONSTRUCTED = "reconstructed"
    ALREADY_FINALIZED = "already_finalized"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


@dataclass
class RecoveryRecord:
    operation_id: str
    outcome: str
    detail: str = ""


@dataclass
class BeginResult:
    status: str  # "proceed" | "no_durable_delta" | "privacy_block" | "recovery_required" | "recovery_conflict"
    operation_id: Optional[str] = None
    old_digest: str = "none"
    new_digest: Optional[str] = None
    generation: Optional[int] = None
    validated_candidate: Optional[dict] = None
    privacy_findings: list = field(default_factory=list)
    recovery_records: list = field(default_factory=list)


def read_current(repo_key: str, clone_key: str, workstream_key: str) -> Optional[dict]:
    """Returns None if no active state exists yet for this workstream."""
    path = paths.current_path(repo_key, clone_key, workstream_key)
    try:
        data = durability.read_file_bytes(path)
    except FileNotFoundError:
        return None
    try:
        doc = json.loads(data)
        schemas.validate_as(doc, "current.v1")
    except (json.JSONDecodeError, SchemaValidationError, UnicodeDecodeError) as exc:
        raise CurrentStateCorruptError(f"{path}: {exc}") from exc
    return doc


def _read_json_strict(path) -> dict:
    """No-follow read + JSON parse. Raises on any anomaly; callers classify."""
    data = durability.read_file_bytes(path)
    return json.loads(data)


def _checkpoint_id_for(operation_id: str) -> str:
    # Deterministic 1:1 derivation so idempotent recovery can detect/reuse a
    # checkpoint written before a mid-transaction crash without extra journal
    # state: operations and checkpoints are exactly 1:1 in this transaction.
    suffix = operation_id.split("-", 1)[1] if "-" in operation_id else operation_id
    return f"chk-{suffix}"


def _receipt_id_for(operation_id: str) -> str:
    suffix = operation_id.split("-", 1)[1] if "-" in operation_id else operation_id
    return f"rcpt-{suffix}"


def _minimal_checkpoint_from_active_state(active_state: dict, checkpoint_id: str) -> dict:
    """Last-resort, recovery-only checkpoint synthesis directly from active-state
    fields (no Index dependency). Deliberately minimal: the normal path always
    uses the real Index contract, which is richer (authority pointers, working
    hypothesis projection, real compaction inputs)."""
    scope = active_state.get("scope", {})
    in_scope = scope.get("in_scope", [])
    scope_summary = "; ".join(item.get("summary", "") for item in in_scope[:3])[:200] or "(no active scope recorded)"
    blockers = [{"summary": b["description"][:150]} for b in active_state.get("blockers", [])[:3]]
    next_actions = [{"description": a["description"][:150]} for a in active_state.get("next_actions", [])[:3]]
    return {
        "schema": "save-game-checkpoint/v1",
        "checkpoint_id": checkpoint_id,
        "workstream_key": active_state["workstream_key"],
        "client_id": "unknown",
        "created_at": ids.now_iso(),
        "expiry_class": "unresolved",
        "active_state_generation": active_state["generation"],
        "active_state_digest": active_state["current_digest"],
        "objective": active_state.get("objective", "(recovered)")[:200],
        "scope_summary": scope_summary,
        "done": [],
        "blockers": blockers,
        "next_actions": next_actions,
        "compaction": {"status": "unknown", "pressure_source": "unknown"},
        "canonical_precedence_notice": "Live canonical sources override this checkpoint; it is an index, never authority.",
    }


def _minimal_receipt_for_recovery(workstream_key: str, receipt_id: str, checkpoint_id: str) -> dict:
    return {
        "schema": "save-game-flush-receipt/v1",
        "receipt_id": receipt_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "status": "SAVED",
        "saved": ["active state (recovered after an interrupted transaction)"],
        "omitted": [],
        "refused": [],
        "stale": [],
        "reconciliation_required": True,
        "checkpoint_id": checkpoint_id,
        "negative_claims": [
            "SAVED means private bytes were durability-certified; it never means Git-delivered, cross-machine, compacted, or worktree-retained."
        ],
    }


def write_prepared(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    operation_id: str,
    old_digest: str,
    new_digest: str,
    expected_generation: int,
    identity: identity_mod.RootIdentity,
    snapshot_digest: str,
) -> dict:
    doc = {
        "schema": "save-game-journal-prepared/v1",
        "operation_id": operation_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "old_digest": old_digest,
        "new_digest": new_digest,
        "expected_generation": expected_generation,
        "observed_root": identity_mod.root_snapshot_dict(identity, include_remote=False),
        "snapshot_digest": snapshot_digest,
    }
    schemas.validate_as(doc, "journal-prepared.v1")
    path = paths.journal_operation_dir(repo_key, clone_key, workstream_key, operation_id) / "prepared.json"
    durability.create_exclusive_durable(path, canonical.canonical_bytes(doc))
    return doc


def write_aborted(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    operation_id: str,
    reason: str,
    old_digest: str,
    attempted_new_digest: str,
) -> dict:
    doc = {
        "schema": "save-game-journal-aborted/v1",
        "operation_id": operation_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "reason": reason,
        "old_digest": old_digest,
        "attempted_new_digest": attempted_new_digest,
    }
    schemas.validate_as(doc, "journal-aborted.v1")
    path = paths.journal_operation_dir(repo_key, clone_key, workstream_key, operation_id) / "aborted.json"
    try:
        durability.create_exclusive_durable(path, canonical.canonical_bytes(doc))
    except FileExistsError:
        pass  # idempotent: a previous recovery pass may have already aborted this operation
    return doc


def write_finalized(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    operation_id: str,
    checkpoint_id: str,
    receipt_id: str,
    new_digest: str,
    reconcile_required: bool,
) -> dict:
    doc = {
        "schema": "save-game-journal-finalized/v1",
        "operation_id": operation_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "checkpoint_id": checkpoint_id,
        "receipt_id": receipt_id,
        "new_digest": new_digest,
        "reconcile_required": reconcile_required,
    }
    schemas.validate_as(doc, "journal-finalized.v1")
    path = paths.journal_operation_dir(repo_key, clone_key, workstream_key, operation_id) / "finalized.json"
    try:
        durability.create_exclusive_durable(path, canonical.canonical_bytes(doc))
    except FileExistsError:
        pass  # idempotent: a previous recovery pass may have already finalized this operation
    return doc


def quarantine_operation(repo_key: str, clone_key: str, workstream_key: str, operation_id: str) -> str:
    """Explicit operator action for RECOVERY_BLOCKED evidence — never called
    automatically by `recover_workstream`. Moves the operation directory under
    the workstream's `quarantine/` dir, preserving it as evidence rather than
    deleting it. Returns the new path as a string."""
    src = paths.journal_operation_dir(repo_key, clone_key, workstream_key, operation_id)
    dst_dir = paths.journal_quarantine_dir(repo_key, clone_key, workstream_key)
    durability.ensure_private_dir(dst_dir)
    dst = dst_dir / f"{operation_id}.{ids.now_iso().replace(':', '').replace('.', '')}"
    os.rename(src, dst)
    durability.sync_directory(dst_dir)
    durability.sync_directory(src.parent)
    return str(dst)


def recover_workstream(repo_key: str, clone_key: str, workstream_key: str) -> list[RecoveryRecord]:
    """Caller MUST hold the workstream lock. Classifies and, where safe,
    auto-resolves every incomplete operation directory for this workstream.
    BLOCKED/CONFLICT evidence is reported but left completely untouched."""
    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    records: list[RecoveryRecord] = []
    if not journal_dir.is_dir():
        return records

    for entry in sorted(journal_dir.iterdir()):
        if entry.name == "quarantine":
            continue
        op_id = entry.name
        st = durability.lstat_safe(entry)
        if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, "operation entry is not a real directory"))
            continue
        if not paths.SAFE_ID.match(op_id):
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, "unsafe operation directory name"))
            continue
        try:
            names = {p.name for p in entry.iterdir()}
        except OSError as exc:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, f"cannot list operation dir: {exc}"))
            continue
        if not names <= _ALLOWED_OP_FILES or "prepared.json" not in names:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, f"unexpected evidence: {sorted(names)}"))
            continue
        bad_file = None
        for fname in names:
            fst = durability.lstat_safe(entry / fname)
            if fst is None or stat.S_ISLNK(fst.st_mode) or not stat.S_ISREG(fst.st_mode):
                bad_file = fname
                break
        if bad_file is not None:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, f"{bad_file} is not a regular file"))
            continue
        if "aborted.json" in names and "finalized.json" in names:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, "both aborted.json and finalized.json present"))
            continue
        if "finalized.json" in names:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.ALREADY_FINALIZED))
            continue
        if "aborted.json" in names:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.NONE, "already aborted"))
            continue

        try:
            prepared = _read_json_strict(entry / "prepared.json")
            schemas.validate_as(prepared, "journal-prepared.v1")
        except Exception as exc:  # noqa: BLE001 - any parse/validate anomaly is unsafe evidence
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, f"malformed prepared.json: {exc}"))
            continue
        if prepared.get("operation_id") != op_id:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, "operation_id mismatch vs directory name"))
            continue

        try:
            current_doc = read_current(repo_key, clone_key, workstream_key)
        except CurrentStateCorruptError as exc:
            records.append(RecoveryRecord(op_id, RecoveryOutcome.BLOCKED, f"current.json unreadable: {exc}"))
            continue
        current_digest = current_doc["current_digest"] if current_doc else "none"
        old_digest = prepared["old_digest"]
        new_digest = prepared["new_digest"]

        if current_digest == old_digest:
            write_aborted(
                repo_key, clone_key, workstream_key,
                operation_id=op_id, reason="stale_current_digest",
                old_digest=old_digest, attempted_new_digest=new_digest,
            )
            records.append(RecoveryRecord(op_id, RecoveryOutcome.ABORTED))
        elif current_digest == new_digest:
            _reconstruct_finalized(repo_key, clone_key, workstream_key, op_id, current_doc, new_digest)
            records.append(RecoveryRecord(op_id, RecoveryOutcome.RECONSTRUCTED))
        else:
            records.append(
                RecoveryRecord(
                    op_id, RecoveryOutcome.CONFLICT,
                    f"current digest {current_digest!r} matches neither old {old_digest!r} nor new {new_digest!r}",
                )
            )

    return records


def _reconstruct_finalized(repo_key, clone_key, workstream_key, operation_id, current_doc, new_digest) -> None:
    checkpoint_id = _checkpoint_id_for(operation_id)
    checkpoint_path = paths.checkpoint_path(repo_key, clone_key, workstream_key, checkpoint_id)
    if not checkpoint_path.exists():
        checkpoint_doc = _minimal_checkpoint_from_active_state(current_doc, checkpoint_id)
        schemas.validate_as(checkpoint_doc, "checkpoint.v1")
        try:
            durability.create_exclusive_durable(checkpoint_path, canonical.canonical_bytes(checkpoint_doc))
        except FileExistsError:
            pass

    receipt_id = _receipt_id_for(operation_id)
    receipt_path = paths.receipt_path(repo_key, clone_key, workstream_key, receipt_id)
    if not receipt_path.exists():
        receipt_doc = _minimal_receipt_for_recovery(workstream_key, receipt_id, checkpoint_id)
        schemas.validate_as(receipt_doc, "flush-receipt.v1")
        try:
            durability.create_exclusive_durable(receipt_path, canonical.canonical_bytes(receipt_doc))
        except FileExistsError:
            pass

    write_finalized(
        repo_key, clone_key, workstream_key,
        operation_id=operation_id, checkpoint_id=checkpoint_id, receipt_id=receipt_id,
        new_digest=new_digest, reconcile_required=True,
    )


def begin_transaction(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    build_candidate_fn: Callable[[Optional[dict]], dict],
    identity: identity_mod.RootIdentity,
    expected_current_digest: Optional[str] = None,
) -> BeginResult:
    """Steps 1-6 of the append-only recovery transaction. Caller MUST hold the
    workstream lock for the entire begin_transaction/.../finalize_transaction
    span (CAS generation/digest checks and all phase writes occur inside one
    lock, per the plan's crash-consistency section).

    `build_candidate_fn(current_doc_or_None)` returns a raw candidate dict with
    the SEMANTIC fields only (no generation/current_digest/timestamps/privacy —
    this function fills those in)."""
    recovery_records = recover_workstream(repo_key, clone_key, workstream_key)
    if any(r.outcome == RecoveryOutcome.BLOCKED for r in recovery_records):
        return BeginResult(status="recovery_blocked", recovery_records=recovery_records)
    if any(r.outcome == RecoveryOutcome.CONFLICT for r in recovery_records):
        return BeginResult(status="recovery_conflict", recovery_records=recovery_records)
    if any(r.outcome in (RecoveryOutcome.ABORTED, RecoveryOutcome.RECONSTRUCTED) for r in recovery_records):
        # Recovery did real work this call: stop here and let the caller re-invoke
        # Flush now that state is clean, rather than compounding a fresh mutation
        # with a just-recovered one in the same breath.
        return BeginResult(status="recovery_required", recovery_records=recovery_records)

    current_doc = read_current(repo_key, clone_key, workstream_key)
    current_digest = current_doc["current_digest"] if current_doc else "none"
    generation = current_doc["generation"] if current_doc else 0
    if expected_current_digest is not None and expected_current_digest != current_digest:
        return BeginResult(status="recovery_required", old_digest=current_digest, recovery_records=recovery_records)

    raw_candidate = build_candidate_fn(current_doc)
    candidate = dict(raw_candidate)
    now = ids.now_iso()
    candidate["created_at"] = current_doc["created_at"] if current_doc else now
    candidate["updated_at"] = now
    candidate.pop("current_digest", None)
    candidate.pop("generation", None)
    candidate.pop("previous_digest", None)
    # A caller that echoes a stale `current_doc` back through unchanged (e.g. a
    # naive `dict(current_doc)` copy) could otherwise reintroduce the PRIOR
    # round's privacy classification as if it were new semantic content, which
    # corrupts both the NO_DURABLE_DELTA digest comparison and this round's own
    # (about to be freshly computed) classification.
    candidate.pop("privacy", None)

    try:
        redacted, findings = privacy.scan_and_redact_document(candidate)
    except privacy.PrivacyGateError:
        # Scanner failure, not a scanner FINDING: fail closed before any durable
        # write. A found-and-redacted document still saves fine (classification
        # "redacted" is a valid terminal state) — PRIVACY_BLOCK is reserved for
        # "the gate itself could not run", per the plan's fail-closed rule.
        return BeginResult(status="privacy_block", old_digest=current_digest, recovery_records=recovery_records)
    redacted["privacy"] = {
        "classification": privacy.classification_for(findings),
        "scanner_ruleset_version": privacy.SCANNER_RULESET_VERSION,
    }

    # `generation`/`previous_digest` are NOT volatile for digest purposes (Phase
    # 1 decision) — so the delta check must hold both EXACTLY as already
    # persisted first, or every call would look like a delta merely because
    # generation/previous_digest would already have moved. Only advance them
    # once a real semantic change is confirmed below.
    tentative = dict(redacted)
    tentative["generation"] = generation
    if current_doc and "previous_digest" in current_doc:
        tentative["previous_digest"] = current_doc["previous_digest"]
    tentative_digest = canonical.digest_active_state(tentative)

    if tentative_digest == current_digest:
        tentative["current_digest"] = tentative_digest
        schemas.validate_as(tentative, "current.v1")
        return BeginResult(
            status="no_durable_delta", old_digest=current_digest, new_digest=tentative_digest,
            generation=generation, validated_candidate=tentative, privacy_findings=findings,
            recovery_records=recovery_records,
        )

    redacted["generation"] = generation + 1
    if current_digest != "none":
        redacted["previous_digest"] = current_digest
    new_digest = canonical.digest_active_state(redacted)
    redacted["current_digest"] = new_digest
    schemas.validate_as(redacted, "current.v1")

    operation_id = ids.new_operation_id()
    snapshot_digest = snapshot.write_snapshot(repo_key, clone_key, workstream_key, redacted)
    write_prepared(
        repo_key, clone_key, workstream_key,
        operation_id=operation_id, old_digest=current_digest, new_digest=new_digest,
        expected_generation=generation, identity=identity, snapshot_digest=snapshot_digest,
    )
    durability.atomic_replace_durable(
        paths.current_path(repo_key, clone_key, workstream_key),
        canonical.canonical_bytes(redacted),
    )

    return BeginResult(
        status="proceed", operation_id=operation_id, old_digest=current_digest, new_digest=new_digest,
        generation=generation + 1, validated_candidate=redacted, privacy_findings=findings,
        recovery_records=recovery_records,
    )


def check_reconcile_required(identity_at_start: identity_mod.RootIdentity) -> bool:
    """Step 8: re-read branch/HEAD/operation markers. True means live Git moved
    during the transaction, so the caller must never claim a stable continuation."""
    fresh = identity_mod.resolve_root_identity(identity_at_start.physical_root)
    return (
        fresh.observed_head != identity_at_start.observed_head
        or fresh.branch != identity_at_start.branch
        or fresh.operation_marker != identity_at_start.operation_marker
    )


def finalize_transaction(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    operation_id: str,
    checkpoint_id: str,
    receipt_id: str,
    new_digest: str,
    identity_at_start: identity_mod.RootIdentity,
    reconcile_required: Optional[bool] = None,
) -> dict:
    """Step 9. Caller must already have run Index (step 7), durably created the
    checkpoint, and durably created the receipt (step 8's `finalized.json` points
    to both, so both must already exist on disk before this call) — and must
    still hold the workstream lock acquired before `begin_transaction`.

    `reconcile_required` defaults to a fresh step-8 check here; pass an already
    -computed value (e.g. from `check_reconcile_required`) when the caller needs
    that same boolean to build the receipt before calling this."""
    if reconcile_required is None:
        reconcile_required = check_reconcile_required(identity_at_start)
    return write_finalized(
        repo_key, clone_key, workstream_key,
        operation_id=operation_id, checkpoint_id=checkpoint_id, receipt_id=receipt_id,
        new_digest=new_digest, reconcile_required=reconcile_required,
    )
