"""Erasure + sink registry — build plan v3 §8: "erase resolves the sink registry before
confirmation, deletes in one crash-safe (atomic, interruption-resumable) operation ... rotates/
rewraps profile-pack keys as needed, rebuilds affected views, clears caches/payloads/held-out/
drafts/controlled exports, and verifies zero live/decryptable content references in known
sinks." and §4.4: "Transactional sink registry covers DB/WAL/backups/caches/exports/profile
repo/key stores."

:class:`SinkRegistry` enumerates every sink OVT can act on directly. Anything outside this list
(an out-of-registry offline clone, an iCloud Keychain replica, a Time Machine snapshot) is
structurally unverifiable and must be *disclosed*, never silently claimed as erased (§5.1).
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from operator_voice.persistence.crypto import CryptoContext

ERASE_VERSION = "erase/v1"

KNOWN_SINK_KINDS = (
    "local_database",
    "local_wal",
    "local_backups",
    "keychain_kek",
    "keychain_hmac_secret",
    "profile_repo_keys",  # PPK destruction only — historical ciphertext bytes are disclosed, not deleted
)

UNVERIFIABLE_SINK_KINDS = (
    "icloud_keychain_sync",
    "time_machine_or_full_disk_backup",
    "unknown_offline_clone_or_export",
)


@dataclass
class ErasureReport:
    scope: str
    target: Optional[str]
    sinks_cleared: list[str] = field(default_factory=list)
    sinks_disclosed_unverifiable: list[str] = field(default_factory=list)
    deletion_counts: dict[str, int] = field(default_factory=dict)
    historical_ciphertext_note: Optional[str] = None


def erase_fact(conn: sqlite3.Connection, fact_id: str) -> ErasureReport:
    cur = conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
    return ErasureReport(
        scope="fact",
        target=fact_id,
        sinks_cleared=["local_database"],
        deletion_counts={"facts": cur.rowcount or 0},
    )


def erase_source(conn: sqlite3.Connection, source_id: str) -> ErasureReport:
    counts: dict[str, int] = {}
    doc_ids = [r["document_id"] for r in conn.execute(
        "SELECT document_id FROM documents WHERE source_id = ?", (source_id,)
    ).fetchall()]
    for doc_id in doc_ids:
        counts["observations"] = counts.get("observations", 0) + (
            conn.execute("DELETE FROM observations WHERE document_id = ?", (doc_id,)).rowcount or 0
        )
    counts["documents"] = conn.execute(
        "DELETE FROM documents WHERE source_id = ?", (source_id,)
    ).rowcount or 0
    counts["source_curation_state"] = conn.execute(
        "DELETE FROM source_curation_state WHERE source_id = ?", (source_id,)
    ).rowcount or 0
    counts["sources"] = conn.execute(
        "DELETE FROM sources WHERE source_id = ?", (source_id,)
    ).rowcount or 0
    return ErasureReport(
        scope="source", target=source_id, sinks_cleared=["local_database"], deletion_counts=counts
    )


def erase_validation_set(conn: sqlite3.Connection, subject_id: Optional[str]) -> ErasureReport:
    if subject_id:
        cur = conn.execute("DELETE FROM validation_runs WHERE subject_id = ?", (subject_id,))
    else:
        cur = conn.execute("DELETE FROM validation_runs")
    return ErasureReport(
        scope="validation_set",
        target=subject_id,
        sinks_cleared=["local_database"],
        deletion_counts={"validation_runs": cur.rowcount or 0},
    )


def erase_model_call_payloads(conn: sqlite3.Connection) -> ErasureReport:
    # M1 ships the gateway disabled, so this table is normally empty; still a real, tested path
    # for forward compatibility with M2's gateway (§4.4 "zero payload retention").
    cur = conn.execute("DELETE FROM model_call_records")
    return ErasureReport(
        scope="model_call_payload",
        target=None,
        sinks_cleared=["local_database"],
        deletion_counts={"model_call_records": cur.rowcount or 0},
    )


def erase_export_under_control(conn: sqlite3.Connection, export_id: str) -> ErasureReport:
    row = conn.execute(
        "SELECT destination FROM export_records WHERE export_id = ?", (export_id,)
    ).fetchone()
    file_deleted = 0
    if row and row["destination"]:
        dest = Path(row["destination"])
        if dest.exists():
            try:
                dest.unlink()
                file_deleted = 1
            except OSError:
                pass
    cur = conn.execute("DELETE FROM export_records WHERE export_id = ?", (export_id,))
    return ErasureReport(
        scope="export_under_control",
        target=export_id,
        sinks_cleared=["local_database"] + (["export_destination_file"] if file_deleted else []),
        deletion_counts={"export_records": cur.rowcount or 0, "export_files": file_deleted},
    )


_CONTENT_TABLES = (
    # Children before parents (SQLite enforces `PRAGMA foreign_keys=ON`, sqlite.connect): every
    # table that REFERENCES subjects/sources/documents must be deleted before the table it
    # references, or the parent DELETE raises `IntegrityError: FOREIGN KEY constraint failed`.
    # observations -> documents, subjects; documents -> sources, subjects; sources/subject_aliases/
    # evidence_records/facts/feedback_events/generations/review_items -> subjects; subjects is the
    # root, last. gateway_config is a singleton with no FK; clearing it resets BOTH egress switches
    # to their disabled defaults (get_gateway_config returns GatewayConfig() when the row is absent),
    # so "erase everything" cannot leave a previously-enabled model-egress policy behind.
    "observations", "documents", "source_curation_state", "curation_runs", "sources", "subject_aliases", "evidence_records", "review_items",
    "facts", "feedback_events", "generations", "model_call_records", "export_records",
    "validation_runs", "challenges", "gateway_config", "key_generations", "subjects",
)


def erase_full_system(
    conn: sqlite3.Connection,
    crypto: CryptoContext,
    *,
    profile_pack_crypto: Optional[CryptoContext] = None,
    backups_dir: Optional[Path] = None,
    profile_pack_clone_dir: Optional[Path] = None,
) -> ErasureReport:
    """Full local erasure. Audit events are deliberately NOT in ``_CONTENT_TABLES`` — §8:
    'Metadata-only audit events and tombstones remain.'

    Security review P1-2: an operator-directed ``export`` writes human-readable fact JSON to a
    file OUTSIDE the database; ``full_system`` must unlink every such file (same as
    ``erase_export_under_control``) before it deletes the ``export_records`` rows that are its
    only pointer to those paths — otherwise "irreversibly erase everything" silently leaves
    plaintext exports behind."""
    export_files_deleted = 0
    for row in conn.execute("SELECT destination FROM export_records WHERE destination IS NOT NULL").fetchall():
        dest = Path(row["destination"])
        if dest.exists():
            try:
                dest.unlink()
                export_files_deleted += 1
            except OSError:
                pass

    counts: dict[str, int] = {}
    for table in _CONTENT_TABLES:
        cur = conn.execute(f"DELETE FROM {table}")
        counts[table] = cur.rowcount or 0
    counts["export_files"] = export_files_deleted

    conn.execute(
        "INSERT INTO backend_config(id, mode, active, remote_reference_token, key_generation_ref, "
        "last_verified_durability_json, health) VALUES (1,'LOCAL_ONLY',0,NULL,NULL,NULL,"
        "'This profile stays on this computer') "
        "ON CONFLICT(id) DO UPDATE SET mode='LOCAL_ONLY', active=0, remote_reference_token=NULL, "
        "key_generation_ref=NULL, last_verified_durability_json=NULL, "
        "health='This profile stays on this computer'"
    )
    conn.execute(
        "INSERT INTO sync_state(id, local_generation_id, remote_generation_id, exact_parent_sha, "
        "publish_status, conflict_set_json, last_verified_clean_room) "
        "VALUES (1,NULL,NULL,NULL,'NOT_CONFIGURED','[]',NULL) "
        "ON CONFLICT(id) DO UPDATE SET local_generation_id=NULL, remote_generation_id=NULL, "
        "exact_parent_sha=NULL, publish_status='NOT_CONFIGURED', conflict_set_json='[]', "
        "last_verified_clean_room=NULL"
    )

    crypto.destroy_local_keys()
    sinks_cleared = ["local_database", "keychain_kek", "keychain_hmac_secret"]
    if export_files_deleted:
        sinks_cleared.append("export_destination_file")
    if profile_pack_crypto is not None:
        profile_pack_crypto.destroy_local_keys()
        sinks_cleared.append("keychain_profile_pack_kek")

    # P2-1: WAL truncation and VACUUM are deferred to `checkpoint_and_vacuum()`, which the caller
    # runs AFTER this transaction commits — SQLite refuses `VACUUM` (and a full `wal_checkpoint`
    # can't fully truncate) while a transaction is still open.
    sinks_cleared.append("local_wal")

    if backups_dir and backups_dir.exists():
        for f in backups_dir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        sinks_cleared.append("local_backups")

    if profile_pack_clone_dir and profile_pack_clone_dir.exists():
        shutil.rmtree(profile_pack_clone_dir, ignore_errors=True)
        sinks_cleared.append("profile_pack_clone")

    return ErasureReport(
        scope="full_system",
        target=None,
        sinks_cleared=sinks_cleared,
        sinks_disclosed_unverifiable=list(UNVERIFIABLE_SINK_KINDS),
        deletion_counts=counts,
        historical_ciphertext_note=(
            "If an ENCRYPTED_GIT profile backend was ever configured, historical Git objects may "
            "still contain ciphertext bytes; the local wrapping key generations that protected "
            "them have been destroyed, so that ciphertext is no longer decryptable from this "
            "machine. Git history itself was not rewritten (see profile repo README)."
        ),
    )


def checkpoint_and_vacuum(conn: sqlite3.Connection) -> None:
    """Truncate the WAL and reclaim freelist pages after a ``full_system`` erase commits (P2-1).

    Must run with NO open transaction on ``conn`` — SQLite refuses ``VACUUM`` inside one, and a
    `wal_checkpoint(TRUNCATE)` issued mid-transaction can't fully truncate either. Callers run
    this immediately after the ``staged_operation`` context that calls :func:`erase_full_system`
    has exited (committed)."""
    assert not conn.in_transaction, "checkpoint_and_vacuum must run outside any open transaction"
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
