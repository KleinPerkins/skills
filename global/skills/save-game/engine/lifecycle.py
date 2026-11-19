"""Private adoption, retention, GC, archive, remove, and uninstall (plan:
"Adoption" and "Retention, archive, GC, rollback, and removal").

Layering note: this module owns a SEPARATE on-disk journal namespace
(`gc-journal/`, distinct from `transaction.py`'s `journal/`) for its own
delete-only transactions. Flush's recovery (`transaction.recover_workstream`)
only ever inspects `journal/` and validates strictly against the
`journal-prepared/aborted/finalized.v1` schemas; writing deletion evidence into
that same tree under those same filenames would corrupt Flush's own recovery
classification (an unrelated deletion phase file would look like "unexpected
evidence" -> RECOVERY_BLOCKED for a live workstream). Deletion instead reuses
`transaction.py`'s SIBLING primitives directly -- `durability` (O_EXCL,
containment, no-follow), `lock` (per-workstream flock), `ids`/`canonical`
(id + digest generation) -- and mirrors its exact prepared -> complete
idempotent-crash-recovery *pattern* in its own namespace, per the plan's v2
hardening: both automatic GC and the explicit `remove` operation share ONE
deletion transaction (`run_deletion` / `recover_pending_deletions`) rather than
each inventing their own.

The other v2 hardening point implemented precisely here: every age check below
is measured from an item's own CREATION moment (a journal operation's own
`created_at`, or a temp file's filesystem `st_mtime` -- see `_creation_ts` for
why mtime, not birthtime, is the deliberate signal) and never from a later
"discovery"/"consumption" timestamp such as when GC happened to run.
"""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import canonical, durability, ids, lock, paths, schemas, transaction

GC_RETENTION_DAYS = 7.0

# Matches the exact temp-file naming `durability.atomic_replace_durable` uses:
# `.{path.name}.tmp.{pid}.{6-byte-hex}`. This is the ONLY call site in this
# engine that leaves a hard-crash-orphanable temp file on disk (O_EXCL writers
# such as checkpoints/receipts/journal phases write directly to their final
# name and fail closed as malformed-evidence instead -- already handled by
# `transaction.recover_workstream`, not this module's concern).
_TEMP_FILE_RE = re.compile(r"^\.(?P<base>.+)\.tmp\.\d+\.[0-9a-f]+$")

_HEX64_ERROR = "value {value!r} is not a 64-hex-char key"
_SAFE_ID_ERROR = "value {value!r} is not a safe identifier"


def _hex64(value: str) -> str:
    if not isinstance(value, str) or not paths.HEX64.match(value):
        raise ValueError(_HEX64_ERROR.format(value=value))
    return value


def _safe_id(value: str) -> str:
    if not isinstance(value, str) or not paths.SAFE_ID.match(value):
        raise ValueError(_SAFE_ID_ERROR.format(value=value))
    return value


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts[:-1] + "+00:00" if ts.endswith("Z") else ts)


def _age_days(created_at: datetime, now: datetime) -> float:
    return (now - created_at).total_seconds() / 86400.0


# --------------------------------------------------------------------------
# 1. Adoption (plan: "Adoption")
# --------------------------------------------------------------------------


def is_adopted(repo_key: str, clone_key: str) -> bool:
    """Same one-line check `flush.py` uses privately -- duplicated here (not
    imported) since that function is private to Flush's own module and this
    module owns adoption's write side; both sides agree because both reduce to
    the same public `paths.registration_path(...).is_file()` fact."""
    return paths.registration_path(repo_key, clone_key).is_file()


def read_registration(repo_key: str, clone_key: str) -> Optional[dict]:
    """Read-only. Returns None for an unconfigured (never-adopted) clone."""
    path = paths.registration_path(repo_key, clone_key)
    try:
        raw = durability.read_file_bytes(path)
    except FileNotFoundError:
        return None
    doc = json.loads(raw)
    schemas.validate_as(doc, "registration.v1")
    return doc


def adoption_status(repo_key: str, clone_key: str) -> dict:
    """Read-only report distinguishing the plan's two explicit adoption cases:
    'configured' (a registration record already exists) vs 'unconfigured'
    (none yet -- Flush still works, privately, returning
    SAVED_PRIVATE_UNADOPTED)."""
    doc = read_registration(repo_key, clone_key)
    return {
        "repo_key": repo_key,
        "clone_key": clone_key,
        "adopted": doc is not None,
        "case": "configured" if doc is not None else "unconfigured",
        "registration": doc,
    }


def _build_registration_doc(
    repo_key: str,
    clone_key: str,
    *,
    existing: Optional[dict],
    canonical_pointers: Optional[list],
    retention_policy: Optional[dict],
    notes: Optional[str],
    enabled: bool,
) -> dict:
    now = ids.now_iso()
    doc: dict = {
        "schema": "save-game-registration/v1",
        "repo_key": repo_key,
        "clone_key": clone_key,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
        "enabled": enabled,
    }
    if canonical_pointers:
        doc["canonical_pointers"] = canonical_pointers[:10]
    if retention_policy:
        doc["retention_policy"] = retention_policy
    if notes:
        doc["notes"] = notes[:200]
    return doc


def adopt_preview(
    repo_key: str,
    clone_key: str,
    *,
    canonical_pointers: Optional[list] = None,
    retention_policy: Optional[dict] = None,
    notes: Optional[str] = None,
    enabled: bool = True,
) -> dict:
    """Dry-run: the exact schema-valid shape `adopt()` would persist, without
    writing it (plan: "`save-game adopt` previews a private registration...
    Operator confirmation writes it under XDG config"). No side effects."""
    existing = read_registration(repo_key, clone_key)
    doc = _build_registration_doc(
        repo_key, clone_key, existing=existing, canonical_pointers=canonical_pointers,
        retention_policy=retention_policy, notes=notes, enabled=enabled,
    )
    schemas.validate_as(doc, "registration.v1")
    return doc


def adopt(
    repo_key: str,
    clone_key: str,
    *,
    canonical_pointers: Optional[list] = None,
    retention_policy: Optional[dict] = None,
    notes: Optional[str] = None,
    enabled: bool = True,
) -> dict:
    """Operator-confirmed write of the private registration. Idempotent/mutable
    (unlike checkpoints/tombstones): registration is private CONFIG, so a
    second `adopt()` call updates `updated_at` and any changed fields in place
    via the same atomic-replace path `current.json` uses, rather than erroring
    -- disabling save-game or changing retention policy later is exactly this
    same call, not a distinct one. Never authorizes repository writes or
    weakens repo policy; it only ever touches this private XDG record."""
    existing = read_registration(repo_key, clone_key)
    doc = _build_registration_doc(
        repo_key, clone_key, existing=existing, canonical_pointers=canonical_pointers,
        retention_policy=retention_policy, notes=notes, enabled=enabled,
    )
    schemas.validate_as(doc, "registration.v1")
    durability.atomic_replace_durable(paths.registration_path(repo_key, clone_key), canonical.canonical_bytes(doc))
    return doc


# --------------------------------------------------------------------------
# Shared deletion transaction (GC + remove + uninstall all call this)
# --------------------------------------------------------------------------


def _gc_journal_workstream_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return paths.state_root() / "gc-journal" / _hex64(repo_key) / _hex64(clone_key) / _hex64(workstream_key)


def _gc_journal_operation_dir(repo_key: str, clone_key: str, workstream_key: str, operation_id: str) -> Path:
    return _gc_journal_workstream_dir(repo_key, clone_key, workstream_key) / _safe_id(operation_id)


def _tombstones_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return paths.state_root() / "tombstones" / _hex64(repo_key) / _hex64(clone_key) / _hex64(workstream_key)


def _tombstone_path(repo_key: str, clone_key: str, workstream_key: str, tombstone_id: str) -> Path:
    return _tombstones_dir(repo_key, clone_key, workstream_key) / f"{_safe_id(tombstone_id)}.json"


def _tombstone_id_for(operation_id: str) -> str:
    # Deterministic 1:1 derivation, same idiom as transaction._checkpoint_id_for,
    # so recovery can detect/reuse a tombstone written before a mid-transaction
    # crash without any extra bookkeeping.
    suffix = operation_id.split("-", 1)[1] if "-" in operation_id else operation_id
    return f"tomb-{suffix}"


def prepare_deletion(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    target_path: Path,
    target_kind: str,
    target_digest: str,
    reason: str,
) -> dict:
    """Phase 1 (durably, O_EXCL, before touching the target): records deletion
    INTENT. Caller MUST hold the workstream lock, matching
    `transaction.begin_transaction`'s own contract."""
    operation_id = ids.new_id("gcop")
    doc = {
        "operation_id": operation_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "target_path": str(target_path),
        "target_kind": target_kind,
        "target_digest": target_digest,
        "reason": reason,
    }
    op_dir = _gc_journal_operation_dir(repo_key, clone_key, workstream_key, operation_id)
    durability.create_exclusive_durable(op_dir / "prepared.json", canonical.canonical_bytes(doc))
    return doc


def _write_tombstone(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    tombstone_id: str,
    target_kind: str,
    target_digest: str,
    reason: str,
) -> dict:
    doc = {
        "schema": "save-game-tombstone/v1",
        "tombstone_id": tombstone_id,
        "workstream_key": workstream_key,
        "created_at": ids.now_iso(),
        "target_kind": target_kind,
        "target_digest": target_digest,
        "reason": reason,
        "completed": True,
    }
    schemas.validate_as(doc, "tombstone.v1")
    path = _tombstone_path(repo_key, clone_key, workstream_key, tombstone_id)
    try:
        durability.create_exclusive_durable(path, canonical.canonical_bytes(doc))
    except FileExistsError:
        pass  # idempotent: a previous recovery pass may already have completed this
    return doc


def _assert_within_private_area(target: Path) -> None:
    """No-follow containment against WHICHEVER of the two XDG-private roots
    this engine ever writes under -- `state_root()` for every workstream
    artifact, `config_root()` for the clone-level registration record (the
    one deletion target this module handles that lives outside
    `state_root()`). Refuses anything that resolves under neither.

    `assert_contained` itself resolves `root` (Darwin exposes `/var` and
    `/tmp` as root-owned symlinks to `/private/...`) but leaves `target`
    untouched, so an unresolved target under one of those roots would
    otherwise mismatch a resolved root's prefix and be wrongly refused.
    `normalize_trusted_prefix` is the engine's own prescribed fix for exactly
    this: it resolves only ROOT-OWNED symlink PARENT components and leaves the
    final component's own symlink-ness untouched for `assert_contained`'s own
    no-follow walk to still catch -- the same composition `ensure_private_dir`
    uses internally. The original (unnormalized) `target` is still what every
    actual filesystem operation below uses; this normalization exists solely
    to make the containment STRING comparison consistent."""
    normalized = durability.normalize_trusted_prefix(target)
    for root in (paths.state_root(), paths.config_root()):
        try:
            durability.assert_contained(root, normalized)
            return
        except durability.UnsafePathError:
            continue
    raise durability.UnsafePathError(f"refusing to delete outside save-game private state/config roots: {target}")


def complete_deletion(repo_key: str, clone_key: str, workstream_key: str, prepared_doc: dict) -> dict:
    """Phase 2 (idempotent/crash-resumable): delete the target IF it is still
    present, then durably record the tombstone. Safe to call twice, and safe
    to call after a crash left `prepared.json` durable but the target/tombstone
    in an unknown state -- it re-derives truth from what is ACTUALLY on disk
    rather than assuming where the previous attempt got to, exactly like
    `transaction.recover_workstream`'s own old/new-digest re-derivation."""
    tombstone_id = _tombstone_id_for(prepared_doc["operation_id"])
    existing_tombstone = _tombstone_path(repo_key, clone_key, workstream_key, tombstone_id)
    if existing_tombstone.is_file():
        return json.loads(durability.read_file_bytes(existing_tombstone))

    target = Path(prepared_doc["target_path"])
    _assert_within_private_area(target)
    st = durability.lstat_safe(target)
    if st is not None:
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise durability.UnsafePathError(f"refusing to delete a non-regular target: {target}")
        os.unlink(target)
        durability.sync_directory(target.parent)

    return _write_tombstone(
        repo_key, clone_key, workstream_key,
        tombstone_id=tombstone_id, target_kind=prepared_doc["target_kind"],
        target_digest=prepared_doc["target_digest"], reason=prepared_doc["reason"],
    )


def run_deletion(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    target_path: Path,
    target_kind: str,
    target_digest: str,
    reason: str,
) -> dict:
    """The ONE deletion transaction automatic GC, `remove`, and `uninstall` all
    call -- prepare then complete. Caller MUST hold the workstream lock."""
    prepared = prepare_deletion(
        repo_key, clone_key, workstream_key,
        target_path=target_path, target_kind=target_kind, target_digest=target_digest, reason=reason,
    )
    return complete_deletion(repo_key, clone_key, workstream_key, prepared)


def recover_pending_deletions(repo_key: str, clone_key: str, workstream_key: str) -> list[dict]:
    """Caller MUST hold the workstream lock. Finds every `gc-journal` operation
    whose `prepared.json` exists but whose tombstone does not yet, and
    deterministically completes it. Malformed/unsafe evidence is left
    completely untouched and reported, never guessed at or force-deleted --
    the same fail-closed posture as `transaction.recover_workstream`'s
    RECOVERY_BLOCKED classification."""
    journal_dir = _gc_journal_workstream_dir(repo_key, clone_key, workstream_key)
    if not journal_dir.is_dir():
        return []
    results = []
    for entry in sorted(journal_dir.iterdir()):
        st = durability.lstat_safe(entry)
        if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            results.append({"operation_id": entry.name, "outcome": "blocked", "detail": "not a real directory"})
            continue
        prepared_path = entry / "prepared.json"
        try:
            prepared = json.loads(durability.read_file_bytes(prepared_path))
        except Exception as exc:  # noqa: BLE001 - any anomaly is unsafe evidence, never guessed at
            results.append({"operation_id": entry.name, "outcome": "blocked", "detail": f"malformed prepared.json: {exc}"})
            continue
        if prepared.get("operation_id") != entry.name:
            results.append({"operation_id": entry.name, "outcome": "blocked", "detail": "operation_id mismatch vs directory name"})
            continue
        try:
            tombstone = complete_deletion(repo_key, clone_key, workstream_key, prepared)
        except durability.UnsafePathError as exc:
            results.append({"operation_id": entry.name, "outcome": "blocked", "detail": str(exc)})
            continue
        results.append({"operation_id": entry.name, "outcome": "completed", "tombstone_id": tombstone["tombstone_id"]})
    return results


# --------------------------------------------------------------------------
# 2. Retention status (read-only) + 3. Safe GC
# --------------------------------------------------------------------------


def _creation_ts(path: Path) -> datetime:
    """Deliberately `st_mtime`, not `st_birthtime`: every temp file this engine
    can leave behind is written exactly once (O_CREAT|O_EXCL, then either
    renamed away or abandoned) and never modified again, so mtime IS its
    creation moment for this file class -- and unlike birthtime, mtime is
    reliably adjustable with `os.utime` in tests, which is exactly the lever
    the plan's "created 6 days ago is NOT collected, 8 days ago IS collected"
    behavioral test needs."""
    st = os.lstat(path)
    return datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)


def _temp_scan_dirs(repo_key: str, clone_key: str, workstream_key: str) -> list[tuple[Path, Optional[str]]]:
    """(directory, required_base_or_None) pairs to scan for abandoned temp
    files. Only `atomic_replace_durable` ever leaves a `.tmp.` file behind on
    a crash; every other artifact this engine writes (checkpoints, receipts,
    archives, snapshots, journal phases) uses `create_exclusive_durable`,
    which unlinks its own half-written file on failure and never leaves a
    temp name -- so `current.json`'s parent is the ONLY directory a
    workstream-scoped GC pass needs to scan. That directory is SHARED by
    every workstream under one repo/clone, so the scan filters to this
    workstream's own base name. (The registration record also uses
    `atomic_replace_durable`, but it is clone-scoped, not workstream-scoped --
    out of scope for this per-workstream scan; see module docstring.)"""
    current_path = paths.current_path(repo_key, clone_key, workstream_key)
    return [(current_path.parent, current_path.name)]


def _classify_temp_files(repo_key: str, clone_key: str, workstream_key: str, *, now: datetime) -> list[dict]:
    items = []
    for directory, required_base in _temp_scan_dirs(repo_key, clone_key, workstream_key):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            st = durability.lstat_safe(entry)
            if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                continue
            match = _TEMP_FILE_RE.match(entry.name)
            if not match:
                continue
            if required_base is not None and match.group("base") != required_base:
                continue  # belongs to a sibling workstream sharing this directory
            created = _creation_ts(entry)
            age = _age_days(created, now)
            eligible = age >= GC_RETENTION_DAYS
            items.append({
                "kind": "temp_file",
                "path": entry,
                "created_at": created.isoformat(),
                "age_days": round(age, 3),
                "category": "eligible" if eligible else "pinned",
                "auto_deletable": eligible,
                "rationale": (
                    f"abandoned temp file, {age:.1f}d old (>= {GC_RETENTION_DAYS:.0f}d retention)"
                    if eligible else f"abandoned temp file, only {age:.1f}d old (< {GC_RETENTION_DAYS:.0f}d retention)"
                ),
            })
    return items


def _classify_aborted_snapshots(repo_key: str, clone_key: str, workstream_key: str, *, now: datetime) -> list[dict]:
    """A snapshot is `snapshot_bytes_for`'s content hash of a FULL candidate
    active-state doc (plain content hash, not the semantic `current_digest`)
    -- every FINALIZED operation's own `prepared.json` already carries that
    exact digest, so marking every finalized operation's `snapshot_digest` as
    referenced (below) is sufficient; there is no need to separately re-hash
    `current.json` itself, since the current generation IS one of the
    finalized operations in this same journal."""
    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    if not journal_dir.is_dir():
        return []

    referenced: set[str] = set()
    aborted_candidates: list[tuple[str, dict, str]] = []
    pending_digests: set[str] = set()
    for entry in sorted(journal_dir.iterdir()):
        if entry.name == "quarantine" or not entry.is_dir():
            continue
        prepared_path = entry / "prepared.json"
        if not prepared_path.is_file():
            continue
        try:
            prepared = json.loads(durability.read_file_bytes(prepared_path))
        except Exception:  # noqa: BLE001 - malformed evidence is Flush recovery's concern, not GC's; skip defensively
            continue
        snap_digest = prepared.get("snapshot_digest")
        if not snap_digest:
            continue
        if (entry / "finalized.json").is_file():
            referenced.add(snap_digest)  # forward rollback depends on every finalized generation's snapshot
        elif (entry / "aborted.json").is_file():
            aborted_candidates.append((entry.name, prepared, snap_digest))
        else:
            pending_digests.add(snap_digest)  # incomplete: Flush's recovery owns this, GC never touches it

    items = []
    for op_id, prepared, snap_digest in aborted_candidates:
        snap_path = paths.snapshot_path(repo_key, clone_key, workstream_key, snap_digest)
        if not snap_path.is_file():
            continue  # already gone (e.g. a previous GC pass)
        created = _parse_iso(prepared["created_at"])
        age = _age_days(created, now)
        if snap_digest in referenced:
            category, auto_deletable = "pinned", False
            rationale = "snapshot content is shared with a finalized/current generation; never GC-eligible"
        elif snap_digest in pending_digests:
            category, auto_deletable = "ambiguous", False
            rationale = "snapshot content is also referenced by a still-incomplete operation; requires Flush recovery first"
        elif age >= GC_RETENTION_DAYS:
            category, auto_deletable = "eligible", True
            rationale = f"unreferenced snapshot from aborted operation {op_id}, {age:.1f}d old (>= {GC_RETENTION_DAYS:.0f}d retention)"
        else:
            category, auto_deletable = "pinned", False
            rationale = f"unreferenced snapshot from aborted operation {op_id}, only {age:.1f}d old (< {GC_RETENTION_DAYS:.0f}d retention)"
        items.append({
            "kind": "snapshot",
            "path": snap_path,
            "digest": snap_digest,
            "operation_id": op_id,
            "created_at": prepared["created_at"],
            "age_days": round(age, 3),
            "category": category,
            "auto_deletable": auto_deletable,
            "rationale": rationale,
        })
    return items


def _hygiene_clear(hygiene: dict) -> bool:
    required_true = ("transactions_finalized", "temp_artifacts_clear", "repo_status_observed", "required_checks_run")
    return all(hygiene.get(k) for k in required_true) and not hygiene.get("unclassified_delta", True)


def _classify_checkpoints(repo_key: str, clone_key: str, workstream_key: str, *, now: datetime) -> list[dict]:
    """Informational only: the plan's fuller retention model classifies
    non-newest ("consumed") checkpoints as conceptually GC-eligible once past
    the retention window, but MVP's automatic GC never deletes checkpoints
    (the plan's own narrower "Automatic GC may delete only..." sentence, and
    this build's deliverable scope, both exclude them) -- every entry here
    carries `auto_deletable: False` so a report reader never mistakes this for
    something `gc_run` will act on."""
    checkpoints_dir = paths.checkpoints_dir(repo_key, clone_key, workstream_key)
    if not checkpoints_dir.is_dir():
        return []
    docs = []
    for entry in sorted(checkpoints_dir.iterdir()):
        st = durability.lstat_safe(entry)
        if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            continue
        try:
            doc = json.loads(durability.read_file_bytes(entry))
            schemas.validate_as(doc, "checkpoint.v1")
        except Exception:  # noqa: BLE001 - malformed checkpoint evidence isn't this report's job to fix
            continue
        docs.append(doc)
    if not docs:
        return []

    max_generation = max(d["active_state_generation"] for d in docs)
    at_max = [d for d in docs if d["active_state_generation"] == max_generation]
    ambiguous_tie = len(at_max) > 1
    consumed = sorted((d for d in docs if d["active_state_generation"] != max_generation), key=lambda d: d["active_state_generation"])
    newest_consumed_id = consumed[-1]["checkpoint_id"] if consumed else None

    items = []
    for d in docs:
        created = _parse_iso(d["created_at"])
        age = _age_days(created, now)
        if d["active_state_generation"] == max_generation:
            if ambiguous_tie:
                category, rationale = "ambiguous", "tied maximum-generation checkpoint; resolution is ambiguous (matches Index's CHECKPOINT_AMBIGUOUS)"
            else:
                category, rationale = "pinned", "current resolved checkpoint (maximum generation)"
        elif d["checkpoint_id"] == newest_consumed_id:
            category, rationale = "pinned", "newest consumed checkpoint; always retained as the fallback resume point"
        elif age >= GC_RETENTION_DAYS:
            category, rationale = "eligible", f"consumed checkpoint, {age:.1f}d old (>= {GC_RETENTION_DAYS:.0f}d) -- informational only, not deleted by automatic GC in MVP"
        else:
            category, rationale = "pinned", f"consumed checkpoint, only {age:.1f}d old (< {GC_RETENTION_DAYS:.0f}d)"
        items.append({
            "kind": "checkpoint",
            "checkpoint_id": d["checkpoint_id"],
            "created_at": d["created_at"],
            "age_days": round(age, 3),
            "category": category,
            "auto_deletable": False,
            "rationale": rationale,
        })
    return items


def _classify_journal_entries(repo_key: str, clone_key: str, workstream_key: str) -> list[dict]:
    """Read-only (no `transaction.recover_workstream` call -- that mutates).
    Just reports each operation directory's terminal/pending state."""
    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    if not journal_dir.is_dir():
        return []
    items = []
    for entry in sorted(journal_dir.iterdir()):
        if entry.name == "quarantine" or not entry.is_dir():
            continue
        try:
            names = {p.name for p in entry.iterdir()}
        except OSError:
            names = set()
        if "finalized.json" in names:
            state, category, rationale = "finalized", "pinned", "completed journal metadata; not automatically deleted in MVP"
        elif "aborted.json" in names:
            state, category, rationale = "aborted", "pinned", "aborted operation's journal metadata is retained; only its unreferenced snapshot may be GC-eligible"
        else:
            state, category, rationale = "pending", "ambiguous", "incomplete operation; requires Flush recovery, never deleted by GC"
        items.append({
            "kind": "journal_operation",
            "operation_id": entry.name,
            "state": state,
            "category": category,
            "auto_deletable": False,
            "rationale": rationale,
        })
    return items


def retention_status(repo_key: str, clone_key: str, workstream_key: str, *, now: Optional[datetime] = None) -> dict:
    """Read-only, no side effects (verified by a dedicated zero-write test):
    reports every checkpoint/journal-operation/temp-file/snapshot item's
    retention classification -- eligible / pinned / ambiguous -- for the
    workstream. `gc status` in the plan's vocabulary."""
    now = now or datetime.now(timezone.utc)
    items = (
        _classify_temp_files(repo_key, clone_key, workstream_key, now=now)
        + _classify_aborted_snapshots(repo_key, clone_key, workstream_key, now=now)
        + _classify_checkpoints(repo_key, clone_key, workstream_key, now=now)
        + _classify_journal_entries(repo_key, clone_key, workstream_key)
    )
    buckets: dict[str, list[dict]] = {"eligible": [], "pinned": [], "ambiguous": []}
    for item in items:
        buckets[item["category"]].append(item)
    return {
        "workstream_key": workstream_key,
        "generated_at": ids.now_iso(),
        "eligible": buckets["eligible"],
        "pinned": buckets["pinned"],
        "ambiguous": buckets["ambiguous"],
        "counts": {k: len(v) for k, v in buckets.items()},
    }


def gc_run(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    now: Optional[datetime] = None,
    lock_timeout: float = 10.0,
) -> dict:
    """Automatic GC. Deletes ONLY: (a) abandoned temp files, and (b)
    unreferenced snapshots from aborted operations -- both gated at >= 7 days
    old, measured from creation. Never touches current state, checkpoints,
    pending operations, or completed journal metadata (the plan's explicit
    narrowing). Every deletion goes through `run_deletion`'s
    containment-checked/journaled/tombstoned/crash-resumable transaction."""
    now = now or datetime.now(timezone.utc)
    with lock.workstream_lock(workstream_key, timeout=lock_timeout):
        recovered = recover_pending_deletions(repo_key, clone_key, workstream_key)

        eligible_temp = [i for i in _classify_temp_files(repo_key, clone_key, workstream_key, now=now) if i["auto_deletable"]]
        eligible_snap = [i for i in _classify_aborted_snapshots(repo_key, clone_key, workstream_key, now=now) if i["auto_deletable"]]

        tombstones = []
        for item in eligible_temp:
            digest = canonical.sha256_hex(durability.read_file_bytes(item["path"]))
            tombstones.append(run_deletion(
                repo_key, clone_key, workstream_key,
                target_path=item["path"], target_kind="temp_file", target_digest=digest, reason="gc_abandoned_temp",
            ))
        for item in eligible_snap:
            tombstones.append(run_deletion(
                repo_key, clone_key, workstream_key,
                target_path=item["path"], target_kind="snapshot", target_digest=item["digest"], reason="gc_unreferenced_snapshot",
            ))

    return {
        "workstream_key": workstream_key,
        "recovered_pending": recovered,
        "deleted_count": len(tombstones),
        "tombstones": tombstones,
    }


# --------------------------------------------------------------------------
# 4. Archive
# --------------------------------------------------------------------------


def archive_workstream(repo_key: str, clone_key: str, workstream_key: str) -> dict:
    """Requires `status == "terminal"` plus clear hygiene (plan: "archive
    requires terminal task plus hygiene"). Writes an immutable
    `archive-manifest.v1` hash manifest over the active-state/checkpoint/
    journal pointers; moves nothing into normal context; performs no packing/
    compression (deferred until volume warrants it, per plan). Does NOT itself
    flip `current.json`'s `status` to "archived" -- that is a normal Flush
    (`build_candidate_fn` setting `status="archived"`), keeping this function
    decoupled from Flush's own orchestration/receipt/checkpoint side effects."""
    current_doc = transaction.read_current(repo_key, clone_key, workstream_key)
    if current_doc is None:
        return {"status": "NO_ACTIVE_STATE"}
    if current_doc.get("status") != "terminal":
        return {"status": "NOT_TERMINAL", "actual_status": current_doc.get("status")}
    if not _hygiene_clear(current_doc.get("hygiene", {})):
        return {"status": "HYGIENE_INCOMPLETE", "hygiene": current_doc.get("hygiene", {})}

    checkpoints_dir = paths.checkpoints_dir(repo_key, clone_key, workstream_key)
    checkpoint_ids = []
    if checkpoints_dir.is_dir():
        for entry in sorted(checkpoints_dir.iterdir()):
            if entry.suffix == ".json":
                checkpoint_ids.append(entry.stem)
    if not checkpoint_ids:
        return {"status": "NO_CHECKPOINTS"}

    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    journal_operation_ids = []
    if journal_dir.is_dir():
        for entry in sorted(journal_dir.iterdir()):
            if entry.name != "quarantine" and entry.is_dir() and (entry / "finalized.json").is_file():
                journal_operation_ids.append(entry.name)

    final_digest = current_doc["current_digest"]
    # Schema caps checkpoint_ids/journal_operation_ids at 50/200 entries, so the
    # digest is computed over exactly the (possibly truncated) lists actually
    # stored below -- a manifest that is self-verifying over its OWN bytes,
    # never a hash of a longer list than what the document itself contains.
    stored_checkpoint_ids = sorted(checkpoint_ids)[:50]
    stored_journal_operation_ids = sorted(journal_operation_ids)[:200]
    manifest_digest = canonical.sha256_hex(canonical.canonical_bytes({
        "final_active_state_digest": final_digest,
        "checkpoint_ids": stored_checkpoint_ids,
        "journal_operation_ids": stored_journal_operation_ids,
    }))
    doc = {
        "schema": "save-game-archive-manifest/v1",
        "workstream_key": workstream_key,
        "archived_at": ids.now_iso(),
        "final_active_state_digest": final_digest,
        "checkpoint_ids": stored_checkpoint_ids,
        "manifest_digest": manifest_digest,
        "hygiene_confirmed": True,
    }
    if stored_journal_operation_ids:
        doc["journal_operation_ids"] = stored_journal_operation_ids
    schemas.validate_as(doc, "archive-manifest.v1")

    archive_id = ids.new_id("arch")
    path = paths.archives_dir(repo_key, clone_key, workstream_key) / f"{archive_id}.json"
    durability.create_exclusive_durable(path, canonical.canonical_bytes(doc))
    return {"status": "ARCHIVED", "manifest": doc}


# --------------------------------------------------------------------------
# 5. Remove preview/execute (workstream-scoped)
# --------------------------------------------------------------------------


def _target_kind_for(path: Path, *, snapshots_dir: Path) -> str:
    if _TEMP_FILE_RE.match(path.name):
        return "temp_file"
    if path.parent == snapshots_dir:
        return "snapshot"
    return "checkpoint_evidence"  # catch-all: current state, checkpoints, journal phases, receipts, archives


def _enumerate_workstream_files(repo_key: str, clone_key: str, workstream_key: str) -> list[Path]:
    """Every file constituting one workstream's private state EXCEPT
    unresolved (pending) journal operations and quarantined evidence (plan,
    "Retention...removal": "[remove] preserves unresolved or malformed
    evidence") -- a pending operation might still be needed by a future Flush
    recovery pass, and `quarantine/` already holds evidence Flush itself
    decided was too unsafe/malformed to interpret, so an explicit remove must
    not silently destroy either. Only finalized/aborted journal operation
    directories -- i.e. evidence whose classification is already resolved --
    are in scope for deletion."""
    found: list[Path] = []
    current = paths.current_path(repo_key, clone_key, workstream_key)
    if current.is_file():
        found.append(current)
    for d in (
        paths.snapshots_dir(repo_key, clone_key, workstream_key),
        paths.checkpoints_dir(repo_key, clone_key, workstream_key),
        paths.receipts_dir(repo_key, clone_key, workstream_key),
        paths.archives_dir(repo_key, clone_key, workstream_key),
    ):
        if d.is_dir():
            found.extend(p for p in sorted(d.rglob("*")) if p.is_file())

    journal_dir = paths.journal_workstream_dir(repo_key, clone_key, workstream_key)
    if journal_dir.is_dir():
        for entry in sorted(journal_dir.iterdir()):
            if entry.name == "quarantine" or not entry.is_dir():
                continue  # malformed/unsafe evidence Flush already set aside -- preserved, not a remove target
            if not ((entry / "finalized.json").is_file() or (entry / "aborted.json").is_file()):
                continue  # unresolved (pending) operation -- preserved, not a remove target
            found.extend(p for p in sorted(entry.rglob("*")) if p.is_file())
    return found


def remove_preview(repo_key: str, clone_key: str, workstream_key: str) -> dict:
    """Dry-run, no side effects: exactly what `remove_execute` would delete for
    ONE workstream, plus the digest execute must be handed back verbatim to
    proceed (plan: "confirmation is bound to the exact preview digest")."""
    snapshots_dir = paths.snapshots_dir(repo_key, clone_key, workstream_key)
    files = _enumerate_workstream_files(repo_key, clone_key, workstream_key)
    items = []
    for f in files:
        raw = durability.read_file_bytes(f)
        items.append({
            "path": str(f),
            "target_kind": _target_kind_for(f, snapshots_dir=snapshots_dir),
            "content_digest": canonical.sha256_hex(raw),
            "size_bytes": len(raw),
        })
    items.sort(key=lambda i: i["path"])
    preview_digest = canonical.sha256_hex(canonical.canonical_bytes({
        "workstream_key": workstream_key,
        "items": [{"path": i["path"], "content_digest": i["content_digest"]} for i in items],
    }))
    return {
        "workstream_key": workstream_key,
        "preview_digest": preview_digest,
        "item_count": len(items),
        "total_bytes": sum(i["size_bytes"] for i in items),
        "items": items,
        "generated_at": ids.now_iso(),
    }


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if not filenames and not any((p / d).is_dir() for d in dirnames):
            try:
                p.rmdir()
            except OSError:
                pass  # best-effort tidiness only -- never load-bearing for correctness


def remove_execute(
    repo_key: str,
    clone_key: str,
    workstream_key: str,
    *,
    confirm_preview_digest: str,
    lock_timeout: float = 10.0,
) -> dict:
    """Deletes everything `remove_preview` planned for ONE workstream, using
    the SAME `run_deletion` transaction as automatic GC -- never a separate ad
    hoc path. Refuses (no deletion at all) if `confirm_preview_digest` does not
    match a freshly recomputed preview, e.g. because state changed since the
    operator saw the preview. Pending journal operations and quarantined
    evidence are never in `remove_preview`'s plan in the first place (see
    `_enumerate_workstream_files`), so this is a confirmed-total-but-safe wipe,
    not an absolute one."""
    with lock.workstream_lock(workstream_key, timeout=lock_timeout):
        recover_pending_deletions(repo_key, clone_key, workstream_key)
        fresh = remove_preview(repo_key, clone_key, workstream_key)
        if fresh["preview_digest"] != confirm_preview_digest:
            return {"status": "PREVIEW_DIGEST_MISMATCH", "expected_preview_digest": fresh["preview_digest"]}

        tombstones = []
        for item in fresh["items"]:
            tombstones.append(run_deletion(
                repo_key, clone_key, workstream_key,
                target_path=Path(item["path"]), target_kind=item["target_kind"],
                target_digest=item["content_digest"], reason="explicit_remove",
            ))
        _prune_empty_dirs(paths.journal_workstream_dir(repo_key, clone_key, workstream_key))

    return {"status": "REMOVED", "workstream_key": workstream_key, "deleted_count": len(tombstones), "tombstones": tombstones}


# --------------------------------------------------------------------------
# 6. Uninstall preview/execute (repo/clone-scoped: every workstream + registration)
# --------------------------------------------------------------------------


def _discover_workstream_keys(repo_key: str, clone_key: str) -> list[str]:
    """Read-only discovery via the `current/` directory's leaf files -- every
    adopted-or-not workstream gets a `current.json` on its first Flush, so this
    is a safe single enumeration source (never invents a workstream that never
    actually flushed)."""
    base = paths.state_root() / "current" / _hex64(repo_key) / _hex64(clone_key)
    if not base.is_dir():
        return []
    return sorted(p.stem for p in base.glob("*.json") if paths.HEX64.match(p.stem))


def uninstall_preview(repo_key: str, clone_key: str, *, workstream_keys: Optional[list] = None) -> dict:
    """Dry-run, no side effects: fully removing save-game's private state for
    a repo/clone -- every workstream's files plus the private registration.
    Distinct from `install.sh`'s symlink removal, which this never touches.
    Inherits `remove_preview`'s one safety exception per workstream (pending
    operations / quarantined evidence are preserved, not previewed for
    deletion -- see `_enumerate_workstream_files`); this is deliberate, not a
    gap, so a live/unrecovered workstream can never be silently destroyed by
    what is otherwise meant to be a full retirement."""
    keys = list(workstream_keys) if workstream_keys is not None else _discover_workstream_keys(repo_key, clone_key)
    items = []
    for wk in keys:
        items.extend(remove_preview(repo_key, clone_key, wk)["items"])

    registration_path = paths.registration_path(repo_key, clone_key)
    if registration_path.is_file():
        raw = durability.read_file_bytes(registration_path)
        items.append({
            "path": str(registration_path), "target_kind": "checkpoint_evidence",
            "content_digest": canonical.sha256_hex(raw), "size_bytes": len(raw),
        })

    items.sort(key=lambda i: i["path"])
    preview_digest = canonical.sha256_hex(canonical.canonical_bytes({
        "repo_key": repo_key, "clone_key": clone_key,
        "items": [{"path": i["path"], "content_digest": i["content_digest"]} for i in items],
    }))
    return {
        "repo_key": repo_key,
        "clone_key": clone_key,
        "workstream_keys": keys,
        "preview_digest": preview_digest,
        "item_count": len(items),
        "total_bytes": sum(i["size_bytes"] for i in items),
        "items": items,
        "generated_at": ids.now_iso(),
    }


def uninstall_execute(
    repo_key: str,
    clone_key: str,
    *,
    confirm_preview_digest: str,
    workstream_keys: Optional[list] = None,
) -> dict:
    """Full private-state retirement for a repo/clone: every workstream via
    `remove_execute`, then the registration record itself via the SAME
    `run_deletion` transaction (using `clone_key` as the tombstone's
    `workstream_key` field -- a deliberate, documented exception: registration
    is clone-scoped, not workstream-scoped, and `tombstone.v1` has no
    clone-level target kind, but `clone_key` is already a valid 64-hex value so
    this keeps registration deletion inside the one shared crash-safe
    primitive instead of a bespoke bare unlink). Never touches `install.sh`'s
    client-link removal."""
    keys = list(workstream_keys) if workstream_keys is not None else _discover_workstream_keys(repo_key, clone_key)
    fresh = uninstall_preview(repo_key, clone_key, workstream_keys=keys)
    if fresh["preview_digest"] != confirm_preview_digest:
        return {"status": "PREVIEW_DIGEST_MISMATCH", "expected_preview_digest": fresh["preview_digest"]}

    workstream_results = []
    for wk in keys:
        wk_preview = remove_preview(repo_key, clone_key, wk)
        workstream_results.append(remove_execute(
            repo_key, clone_key, wk, confirm_preview_digest=wk_preview["preview_digest"],
        ))

    tombstones = []
    registration_path = paths.registration_path(repo_key, clone_key)
    if registration_path.is_file():
        with lock.workstream_lock(clone_key):
            recover_pending_deletions(repo_key, clone_key, clone_key)
            raw = durability.read_file_bytes(registration_path)
            tombstones.append(run_deletion(
                repo_key, clone_key, clone_key,
                target_path=registration_path, target_kind="checkpoint_evidence",
                target_digest=canonical.sha256_hex(raw), reason="explicit_remove",
            ))

    return {
        "status": "UNINSTALLED",
        "repo_key": repo_key,
        "clone_key": clone_key,
        "workstream_results": workstream_results,
        "registration_tombstones": tombstones,
    }
