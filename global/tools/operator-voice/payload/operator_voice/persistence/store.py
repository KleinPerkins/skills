"""Typed repository layer over the schema-v1 tables — the ONLY place SQL statements exist above
``migrations.py``. Every sensitive column is encrypted here (never in ``application.service``)
using the active key generation from :mod:`operator_voice.persistence.crypto`; every function
takes an already-open ``sqlite3.Connection`` and (where needed) a :class:`CryptoContext` and does
no transaction management of its own — callers wrap multi-step sequences in
``operator_voice.persistence.sqlite.transaction`` or the higher-level
``operator_voice.application.transactions`` staging pattern.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
import sqlite3
from dataclasses import asdict
from typing import Any, Optional

from operator_voice.domain.models import (
    BackendMode,
    CancellationState,
    ContextScope,
    CurationRun,
    CurationRunStatus,
    CurationTrigger,
    ExportManifest,
    FactState,
    FeedbackAction,
    FeedbackEvent,
    GatewayConfig,
    ModelCallRecord,
    ObservationCandidate,
    OperationChallenge,
    ConsequenceDescriptor,
    ProfileBackendConfig,
    ProfileFact,
    ProfileGeneration,
    ProfileSyncState,
    ReviewItem,
    ReviewReason,
    ReviewStatus,
    SignalObservation,
    SourceCurationState,
    SourceDocument,
    SourceRegistration,
    SubjectAlias,
    SubjectKind,
    SubjectRegistration,
    SyncStatus,
    ValidationOutcome,
    ValidationRun,
    now_ts,
)
from operator_voice.domain.models import AdapterType, AuthorshipState
from operator_voice.persistence.crypto import CryptoContext, aead_decrypt, aead_encrypt, new_generation_id

STORE_VERSION = "store/v1"
DOCUMENT_AAD = b"document_content"
SUBJECT_ALIAS_NATIVE_AAD = b"subject_alias_source_native_id"
OBSERVATION_VALUE_AAD = b"observation_value"
OBSERVATION_DIST_AAD = b"observation_distribution"
FACT_VALUE_AAD = b"fact_value"
FEEDBACK_PRIOR_AAD = b"feedback_prior_value"
FEEDBACK_NEW_AAD = b"feedback_new_value"
FEEDBACK_REASON_AAD = b"feedback_reason"
SOURCE_ROOT_AAD = b"source_canonical_root"
DOCUMENT_LOCATOR_AAD = b"document_locator"
_REDACTED_PLACEHOLDER = ""


class StoreError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------
# Key generations
# --------------------------------------------------------------------------------------


CONTENT_KEY_PURPOSE = "content"
PROFILE_PACK_KEY_PURPOSE = "profile_pack"


def ensure_active_key_generation(
    conn: sqlite3.Connection, crypto: CryptoContext, purpose: str = CONTENT_KEY_PURPOSE
) -> tuple[str, bytes]:
    """``purpose`` partitions the 'most recent non-destroyed generation' query — §5.1: 'Profile
    objects use independent data keys [under] a profile-pack wrapping-key generation', kept
    strictly separate from the local-content generation so a call with the wrong
    :class:`CryptoContext` fails to decrypt loudly rather than silently sharing a row."""
    row = conn.execute(
        "SELECT generation_id, wrapped_dek FROM key_generations WHERE destroyed_at IS NULL "
        "AND purpose = ? ORDER BY created_at DESC LIMIT 1",
        (purpose,),
    ).fetchone()
    if row:
        return row["generation_id"], crypto.unwrap_dek(row["wrapped_dek"])
    dek, wrapped = crypto.wrap_new_dek()
    generation_id = new_generation_id()
    conn.execute(
        "INSERT INTO key_generations(generation_id, wrapped_dek, created_at, purpose) VALUES (?,?,?,?)",
        (generation_id, wrapped, now_ts(), purpose),
    )
    return generation_id, dek


def dek_for_generation(conn: sqlite3.Connection, crypto: CryptoContext, key_generation_id: str) -> bytes:
    row = conn.execute(
        "SELECT wrapped_dek FROM key_generations WHERE generation_id = ? AND destroyed_at IS NULL",
        (key_generation_id,),
    ).fetchone()
    if not row:
        raise StoreError(f"key generation {key_generation_id!r} is missing or destroyed")
    return crypto.unwrap_dek(row["wrapped_dek"])


def list_key_generations(conn: sqlite3.Connection, purpose: str) -> list[tuple[str, float]]:
    """Return ``(generation_id, created_at)`` for every non-destroyed generation of ``purpose``,
    oldest first. Used by portability export to enumerate the profile-pack key generations whose
    raw DEKs must travel (encrypted under the operator passphrase) so a second machine can decrypt
    the ENCRYPTED_GIT profile pack and reconcile it (§13 M4 worklist 4/5)."""
    rows = conn.execute(
        "SELECT generation_id, created_at FROM key_generations WHERE destroyed_at IS NULL "
        "AND purpose = ? ORDER BY created_at",
        (purpose,),
    ).fetchall()
    return [(r["generation_id"], r["created_at"]) for r in rows]


def import_key_generation(
    conn: sqlite3.Connection, crypto: CryptoContext, generation_id: str, dek: bytes,
    *, purpose: str, created_at: Optional[float] = None,
) -> bool:
    """Insert a key generation carried in from another machine: the raw ``dek`` is (re)wrapped
    under THIS machine's KEK via ``crypto`` and stored under the SAME ``generation_id`` so a pack
    published on the origin machine (whose objects reference that id) decrypts here. Idempotent —
    an existing id is left untouched (returns False). Never widens local authority: it only makes
    an already-encrypted remote pack readable on the importing machine."""
    existing = conn.execute(
        "SELECT 1 FROM key_generations WHERE generation_id = ?", (generation_id,)
    ).fetchone()
    if existing is not None:
        return False
    wrapped = aead_encrypt(crypto.kek, dek, aad=b"dek-wrap")
    conn.execute(
        "INSERT INTO key_generations(generation_id, wrapped_dek, created_at, purpose) VALUES (?,?,?,?)",
        (generation_id, wrapped, created_at if created_at is not None else now_ts(), purpose),
    )
    return True


def rotate_key_generation(conn: sqlite3.Connection, crypto: CryptoContext, purpose: str = CONTENT_KEY_PURPOSE) -> str:
    """Destroys every current (non-destroyed) generation of ``purpose``'s usability going forward
    by minting a fresh one; callers that must retain existing ciphertext are responsible for
    re-encrypting it under the new DEK before the old row's ``destroyed_at`` is set (§5.1 'rotates/
    rewraps profile-pack keys as needed')."""
    conn.execute(
        "UPDATE key_generations SET destroyed_at = ? WHERE destroyed_at IS NULL AND purpose = ?",
        (now_ts(), purpose),
    )
    _, _ = ensure_active_key_generation(conn, crypto, purpose)
    row = conn.execute(
        "SELECT generation_id FROM key_generations WHERE destroyed_at IS NULL AND purpose = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (purpose,),
    ).fetchone()
    return row["generation_id"]


# --------------------------------------------------------------------------------------
# Subjects
# --------------------------------------------------------------------------------------


def insert_subject(conn: sqlite3.Connection, subject: SubjectRegistration) -> None:
    conn.execute(
        "INSERT INTO subjects(subject_id, kind, display_label, approved_purposes_json, "
        "consent_basis, generation_permission, retention_policy, active, created_at, reviewed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            subject.subject_id, subject.kind.value, subject.display_label,
            json.dumps(subject.approved_purposes), subject.consent_basis,
            int(subject.generation_permission), subject.retention_policy,
            int(subject.active), subject.created_at, subject.reviewed_at,
        ),
    )


def _row_to_subject(r: sqlite3.Row) -> SubjectRegistration:
    return SubjectRegistration(
        subject_id=r["subject_id"], kind=SubjectKind(r["kind"]), display_label=r["display_label"],
        approved_purposes=json.loads(r["approved_purposes_json"]), consent_basis=r["consent_basis"],
        generation_permission=bool(r["generation_permission"]), retention_policy=r["retention_policy"],
        active=bool(r["active"]), created_at=r["created_at"], reviewed_at=r["reviewed_at"],
    )


def get_subject(conn: sqlite3.Connection, subject_id: str) -> Optional[SubjectRegistration]:
    row = conn.execute("SELECT * FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone()
    return _row_to_subject(row) if row else None


def list_subjects(conn: sqlite3.Connection) -> list[SubjectRegistration]:
    rows = conn.execute("SELECT * FROM subjects ORDER BY created_at").fetchall()
    return [_row_to_subject(r) for r in rows]


def set_subject_active(conn: sqlite3.Connection, subject_id: str, active: bool) -> None:
    conn.execute("UPDATE subjects SET active = ? WHERE subject_id = ?", (int(active), subject_id))


def update_subject_enrollment(
    conn: sqlite3.Connection, subject_id: str, *, approved_purposes: list[str],
    consent_basis: str, reviewed_at: float,
) -> None:
    """Persist the operator-attested EXTERNAL enrollment fields (§4.3 subject-kind table): the
    approved analysis purposes, the consent basis, and when the operator reviewed/attested it.
    ``generation_permission`` is intentionally NOT writable here — EXTERNAL subjects never gain it."""
    conn.execute(
        "UPDATE subjects SET approved_purposes_json = ?, consent_basis = ?, reviewed_at = ? "
        "WHERE subject_id = ?",
        (json.dumps(approved_purposes), consent_basis, reviewed_at, subject_id),
    )


# --------------------------------------------------------------------------------------
# Subject aliases (§5 SubjectAlias) — source_native_id is sensitive → encrypted at rest
# --------------------------------------------------------------------------------------


def _row_to_alias(conn: sqlite3.Connection, crypto: CryptoContext, r: sqlite3.Row) -> SubjectAlias:
    dek = dek_for_generation(conn, crypto, r["key_generation_id"])
    native = aead_decrypt(dek, r["source_native_id_enc"], aad=SUBJECT_ALIAS_NATIVE_AAD).decode("utf-8")
    return SubjectAlias(
        alias_id=r["alias_id"], subject_id=r["subject_id"], source_type=r["source_type"],
        source_native_id=native, confidence=r["confidence"], verification_state=r["verification_state"],
        valid_from=r["valid_from"], valid_to=r["valid_to"], collision_review=r["collision_review"],
    )


def insert_subject_alias(conn: sqlite3.Connection, crypto: CryptoContext, alias: SubjectAlias) -> None:
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    native_enc = aead_encrypt(dek, alias.source_native_id.encode("utf-8"), aad=SUBJECT_ALIAS_NATIVE_AAD)
    conn.execute(
        "INSERT INTO subject_aliases(alias_id, subject_id, source_type, source_native_id_enc, "
        "key_generation_id, confidence, verification_state, valid_from, valid_to, collision_review) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            alias.alias_id, alias.subject_id, alias.source_type, native_enc, key_generation_id,
            alias.confidence, alias.verification_state, alias.valid_from, alias.valid_to,
            alias.collision_review,
        ),
    )


def list_subject_aliases(
    conn: sqlite3.Connection, crypto: CryptoContext, subject_id: Optional[str] = None
) -> list[SubjectAlias]:
    if subject_id:
        rows = conn.execute(
            "SELECT * FROM subject_aliases WHERE subject_id = ? AND valid_to IS NULL ORDER BY valid_from",
            (subject_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM subject_aliases WHERE valid_to IS NULL ORDER BY valid_from"
        ).fetchall()
    return [_row_to_alias(conn, crypto, r) for r in rows]


def find_alias_owner(
    conn: sqlite3.Connection, crypto: CryptoContext, source_type: str, source_native_id: str
) -> Optional[str]:
    """Return the subject_id currently owning ``(source_type, source_native_id)``, or None. The
    native id is stored under a RANDOM-nonce AEAD (equal plaintext → different ciphertext), so
    collision detection decrypts and compares in Python rather than matching ciphertext. Alias
    volume is tiny (a handful per subject), so this is cheap and avoids leaking a searchable index
    of source-native identifiers (§4.3: a display name alone is never authoritative)."""
    for alias in list_subject_aliases(conn, crypto):
        if alias.source_type == source_type and alias.source_native_id == source_native_id:
            return alias.subject_id
    return None


# --------------------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------------------


def insert_source(conn: sqlite3.Connection, crypto: CryptoContext, source: SourceRegistration) -> None:
    """``canonical_root`` is a real filesystem path (security review P1-3) — encrypted with the
    active content DEK, never stored in the clear. The legacy plaintext column is kept NOT NULL
    for schema stability but always written as an empty placeholder for new rows."""
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    root_enc = aead_encrypt(dek, source.canonical_root.encode("utf-8"), aad=SOURCE_ROOT_AAD)
    conn.execute(
        "INSERT INTO sources(source_id, subject_id, adapter_type, canonical_root, canonical_root_enc, "
        "key_generation_id, opted_in_at, approved_purpose, active, paused, retention_policy, limits_json, "
        "role_identity_json, cursor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            source.source_id, source.subject_id, source.adapter_type.value, _REDACTED_PLACEHOLDER, root_enc,
            key_generation_id, source.opted_in_at, source.approved_purpose, int(source.active), int(source.paused),
            source.retention_policy, json.dumps(source.limits), json.dumps(source.role_identity),
            source.cursor,
        ),
    )


def _row_to_source(conn: sqlite3.Connection, crypto: CryptoContext, r: sqlite3.Row) -> SourceRegistration:
    if r["canonical_root_enc"] is not None and r["key_generation_id"]:
        dek = dek_for_generation(conn, crypto, r["key_generation_id"])
        canonical_root = aead_decrypt(dek, r["canonical_root_enc"], aad=SOURCE_ROOT_AAD).decode("utf-8")
    else:
        canonical_root = r["canonical_root"]  # pre-migration row fallback only; never written to anymore
    return SourceRegistration(
        source_id=r["source_id"], subject_id=r["subject_id"], adapter_type=AdapterType(r["adapter_type"]),
        canonical_root=canonical_root, opted_in_at=r["opted_in_at"], approved_purpose=r["approved_purpose"],
        active=bool(r["active"]), paused=bool(r["paused"]), retention_policy=r["retention_policy"],
        limits=json.loads(r["limits_json"]), role_identity=json.loads(r["role_identity_json"]),
        cursor=r["cursor"],
    )


def get_source(conn: sqlite3.Connection, crypto: CryptoContext, source_id: str) -> Optional[SourceRegistration]:
    row = conn.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
    return _row_to_source(conn, crypto, row) if row else None


def list_sources(conn: sqlite3.Connection, crypto: CryptoContext, subject_id: Optional[str] = None) -> list[SourceRegistration]:
    if subject_id:
        rows = conn.execute("SELECT * FROM sources WHERE subject_id = ?", (subject_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sources").fetchall()
    return [_row_to_source(conn, crypto, r) for r in rows]


def list_active_sources(conn: sqlite3.Connection, crypto: CryptoContext) -> list[SourceRegistration]:
    """§13 M3: every source that is opted-in AND not paused, in a deterministic order
    (``source_id``). This is the exact set the continual-curation tick sweeps; a paused or
    inactive source is skipped, and with zero active sources the tick is a safe no-op (inert)."""
    rows = conn.execute(
        "SELECT * FROM sources WHERE active = 1 AND paused = 0 ORDER BY source_id"
    ).fetchall()
    return [_row_to_source(conn, crypto, r) for r in rows]


def set_source_cursor(conn: sqlite3.Connection, source_id: str, cursor: Optional[str]) -> None:
    conn.execute("UPDATE sources SET cursor = ? WHERE source_id = ?", (cursor, source_id))


def set_source_role_identity(conn: sqlite3.Connection, source_id: str, role_identity: dict) -> None:
    conn.execute("UPDATE sources SET role_identity_json = ? WHERE source_id = ?",
                 (json.dumps(role_identity, sort_keys=True), source_id))


def set_source_paused(conn: sqlite3.Connection, source_id: str, paused: bool) -> None:
    conn.execute("UPDATE sources SET paused = ? WHERE source_id = ?", (int(paused), source_id))




def _modified_time_is_strictly_newer(stored: str, incoming: str) -> bool:
    """Return True iff ``incoming`` is chronologically after ``stored``.

    Drive ``native_revision`` carries ISO-8601 ``modified_time`` values (RFC 3339).
    Lexical string order is not reliable for all valid ISO forms (e.g. unpadded hours);
    fail-closed on any parse error."""
    if not stored or not incoming:
        return False
    try:
        stored_ts = datetime.fromisoformat(str(stored).replace("Z", "+00:00")).timestamp()
        incoming_ts = datetime.fromisoformat(str(incoming).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return incoming_ts > stored_ts

# --------------------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------------------


def upsert_document(
    conn: sqlite3.Connection, crypto: CryptoContext, doc: SourceDocument, *,
    keep_content: bool, supersede_if_newer: bool = False, legacy_revision: Optional[str] = None,
) -> tuple[str, bool]:
    """Dedup by ``(source_id, source_native_id)`` (unique index, §10.3). Returns
    ``(document_id, is_new)``. When ``keep_content`` is False the content column is never
    populated at all (zero-day retention default, §5.1) — callers extract features from the
    in-memory ``doc.content`` BEFORE calling this.

    ``supersede_if_newer`` (Drive adapter M1, ADR 0002 Decision 2) is the ONE update path in this
    otherwise append-only store. It is reachable only for a document carrying a ``native_revision``
    (only the Drive adapter sets one — Drive's persisted identity is ``file_id`` ALONE, with the
    revision kept as PROVENANCE, not part of the dedup key). When an existing row for the same
    ``(source_id, source_native_id)`` is found AND the incoming ``doc.native_revision`` is STRICTLY
    GREATER than the stored one — a chronological ISO-8601 ``modified_time`` compare; ``revision_id`` is
    opaque/non-ordinal and is never used to order — the row is replaced IN PLACE: its old
    observations are deleted (so a superseded revision's stylometric signals never linger and
    inflate confidence; the caller re-extracts from the newer content under this SAME document_id,
    and ``observation_key`` is document_id-scoped so stale keys must be cleared first or the
    ``INSERT OR IGNORE`` in :func:`upsert_observations` would silently keep the old values) and the
    content/locator/digest/authorship/context/native_revision columns are rewritten. It returns
    ``(existing_document_id, True)`` so the caller's ordinary "is_new -> (re)extract" path runs.
    Anything not strictly newer — equal, older, or a missing comparator on EITHER side — is a
    fail-closed no-op returning ``(existing_document_id, False)``; good content is never downgraded
    or overwritten on an unorderable pair. With ``supersede_if_newer`` False (every non-Drive
    adapter) the historical insert-only behavior is preserved exactly."""
    existing = conn.execute(
        "SELECT document_id, native_revision FROM documents WHERE source_id = ? AND source_native_id = ?",
        (doc.source_id, doc.source_native_id),
    ).fetchone()
    if existing:
        if not supersede_if_newer:
            return existing["document_id"], False
        stored_rev, incoming_rev = existing["native_revision"] or legacy_revision, doc.native_revision
        if not _modified_time_is_strictly_newer(stored_rev, incoming_rev):
            return existing["document_id"], False  # strictly-greater-else-no-op; fail-closed
        document_id = existing["document_id"]
        key_generation_id, dek = ensure_active_key_generation(conn, crypto)
        content_enc = aead_encrypt(dek, doc.content.encode("utf-8"), aad=DOCUMENT_AAD) if keep_content else None
        locator_enc = aead_encrypt(dek, doc.locator.encode("utf-8"), aad=DOCUMENT_LOCATOR_AAD)
        conn.execute("DELETE FROM observations WHERE document_id = ?", (document_id,))
        conn.execute(
            "UPDATE documents SET digest = ?, locator = ?, locator_enc = ?, content_enc = ?, "
            "key_generation_id = ?, content_cleared_at = ?, context_json = ?, sensitivity = ?, "
            "authorship_state = ?, quarantine_reason = ?, expires_at = ?, native_revision = ? "
            "WHERE document_id = ?",
            (
                doc.digest, _REDACTED_PLACEHOLDER, locator_enc, content_enc, key_generation_id,
                None if keep_content else now_ts(), json.dumps({**doc.context.as_dict(), "words": doc.words, "text_key": doc.text_key}), doc.sensitivity,
                doc.authorship_state.value, doc.quarantine_reason, doc.expires_at, doc.native_revision,
                document_id,
            ),
        )
        return document_id, True

    # A key generation is always established, even with keep_content=False (M1's default), because
    # ``locator`` is a real filesystem/native-id path and must be encrypted regardless of whether
    # content itself is retained (security review P1-3).
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    content_enc = aead_encrypt(dek, doc.content.encode("utf-8"), aad=DOCUMENT_AAD) if keep_content else None
    locator_enc = aead_encrypt(dek, doc.locator.encode("utf-8"), aad=DOCUMENT_LOCATOR_AAD)

    conn.execute(
        "INSERT INTO documents(document_id, subject_id, source_id, source_native_id, digest, "
        "locator, locator_enc, content_enc, key_generation_id, content_cleared_at, created_at, context_json, "
        "sensitivity, authorship_state, quarantine_reason, expires_at, native_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            doc.document_id, doc.subject_id, doc.source_id, doc.source_native_id, doc.digest,
            _REDACTED_PLACEHOLDER, locator_enc, content_enc, key_generation_id, None if keep_content else now_ts(),
            doc.created_at, json.dumps({**doc.context.as_dict(), "words": doc.words, "text_key": doc.text_key}), doc.sensitivity,
            doc.authorship_state.value, doc.quarantine_reason, doc.expires_at, doc.native_revision,
        ),
    )
    return doc.document_id, True


def document_ids_for_source(conn: sqlite3.Connection, source_id: str) -> dict[str, str]:
    return {r["source_native_id"]: r["document_id"] for r in conn.execute(
        "SELECT source_native_id, document_id FROM documents WHERE source_id = ?", (source_id,))}


def delete_document_evidence(conn: sqlite3.Connection, document_id: str) -> None:
    conn.execute("DELETE FROM observations WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))


def update_document_classification(conn: sqlite3.Connection, crypto: CryptoContext, doc: SourceDocument) -> None:
    """Replace derived evidence from a fresh candidate, including non-Drive documents."""
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    locator_enc = aead_encrypt(dek, doc.locator.encode("utf-8"), aad=DOCUMENT_LOCATOR_AAD)
    conn.execute("DELETE FROM observations WHERE document_id = ?", (doc.document_id,))
    conn.execute(
        "UPDATE documents SET digest=?, authorship_state=?, quarantine_reason=?, context_json=?, "
        "locator=?, locator_enc=?, key_generation_id=?, content_enc=NULL, content_cleared_at=?, "
        "native_revision=? WHERE document_id=?",
        (doc.digest, doc.authorship_state.value, doc.quarantine_reason, json.dumps({**doc.context.as_dict(), "words": doc.words, "text_key": doc.text_key}),
         _REDACTED_PLACEHOLDER, locator_enc, key_generation_id, now_ts(), doc.native_revision, doc.document_id))


def observation_method_versions(conn: sqlite3.Connection, document_id: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT method_version FROM observations WHERE document_id=?",
                                     (document_id,))}


def retire_fact(conn: sqlite3.Connection, fact_id: str) -> None:
    conn.execute("UPDATE facts SET state=?, valid_to=?, superseded_by=NULL WHERE fact_id=?",
                 (FactState.DEPRECATED.value, now_ts(), fact_id))


def get_document(conn: sqlite3.Connection, crypto: CryptoContext, document_id: str) -> Optional[SourceDocument]:
    row = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
    if not row:
        return None
    content = ""
    if row["content_enc"] is not None and row["key_generation_id"]:
        dek = dek_for_generation(conn, crypto, row["key_generation_id"])
        content = aead_decrypt(dek, row["content_enc"], aad=DOCUMENT_AAD).decode("utf-8")
    if row["locator_enc"] is not None and row["key_generation_id"]:
        dek = dek_for_generation(conn, crypto, row["key_generation_id"])
        locator = aead_decrypt(dek, row["locator_enc"], aad=DOCUMENT_LOCATOR_AAD).decode("utf-8")
    else:
        locator = row["locator"]  # pre-migration row fallback only; never written to anymore
    return SourceDocument(
        document_id=row["document_id"], subject_id=row["subject_id"], source_id=row["source_id"],
        source_native_id=row["source_native_id"], digest=row["digest"], locator=locator,
        content=content, created_at=row["created_at"], context=ContextScope.from_dict(json.loads(row["context_json"])),
        sensitivity=row["sensitivity"], authorship_state=AuthorshipState(row["authorship_state"]),
        quarantine_reason=row["quarantine_reason"], expires_at=row["expires_at"],
        native_revision=row["native_revision"], words=json.loads(row["context_json"]).get("words"),
        text_key=json.loads(row["context_json"]).get("text_key"),
    )


def clear_document_content(conn: sqlite3.Connection, document_id: str) -> None:
    from operator_voice.persistence.retention import clear_document_content as _clear

    _clear(conn, document_id)


def list_document_ids_for_source(conn: sqlite3.Connection, source_id: str) -> list[str]:
    rows = conn.execute("SELECT document_id FROM documents WHERE source_id = ?", (source_id,)).fetchall()
    return [r["document_id"] for r in rows]


def document_source_map(conn: sqlite3.Connection, document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    placeholders = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"SELECT document_id, source_id FROM documents WHERE document_id IN ({placeholders})",
        document_ids,
    ).fetchall()
    return {r["document_id"]: r["source_id"] for r in rows}


# --------------------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------------------


def upsert_observations(conn: sqlite3.Connection, crypto: CryptoContext, observations: list[SignalObservation]) -> int:
    """INSERT OR IGNORE keyed by the unique ``observation_key`` HMAC (§10.3 exactly-once).
    Returns the count of NEWLY inserted rows."""
    if not observations:
        return 0
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    inserted = 0
    for obs in observations:
        value_enc = aead_encrypt(dek, json.dumps(obs.value).encode("utf-8"), aad=OBSERVATION_VALUE_AAD)
        distribution_enc = (
            aead_encrypt(dek, json.dumps(obs.distribution).encode("utf-8"), aad=OBSERVATION_DIST_AAD)
            if obs.distribution is not None
            else None
        )
        cur = conn.execute(
            "INSERT OR IGNORE INTO observations(observation_id, observation_key, subject_id, "
            "document_id, segment_id, facet, value_enc, distribution_enc, key_generation_id, "
            "context_json, sensitivity, method_version, created_at, quality_flags_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                obs.observation_id, obs.observation_key, obs.subject_id, obs.document_id,
                obs.segment_id, obs.facet, value_enc, distribution_enc, key_generation_id,
                json.dumps(obs.context.as_dict()), obs.sensitivity, obs.method_version,
                obs.created_at, json.dumps(obs.quality_flags),
            ),
        )
        inserted += cur.rowcount or 0
    return inserted


def _row_to_observation(conn: sqlite3.Connection, crypto: CryptoContext, r: sqlite3.Row) -> SignalObservation:
    dek = dek_for_generation(conn, crypto, r["key_generation_id"])
    value = json.loads(aead_decrypt(dek, r["value_enc"], aad=OBSERVATION_VALUE_AAD).decode("utf-8"))
    distribution = (
        json.loads(aead_decrypt(dek, r["distribution_enc"], aad=OBSERVATION_DIST_AAD).decode("utf-8"))
        if r["distribution_enc"] is not None
        else None
    )
    return SignalObservation(
        observation_id=r["observation_id"], observation_key=r["observation_key"], subject_id=r["subject_id"],
        document_id=r["document_id"], segment_id=r["segment_id"], facet=r["facet"], value=value,
        distribution=distribution, context=ContextScope.from_dict(json.loads(r["context_json"])),
        sensitivity=r["sensitivity"], method_version=r["method_version"], created_at=r["created_at"],
        quality_flags=json.loads(r["quality_flags_json"]),
    )


def get_observations_for_facet(conn: sqlite3.Connection, crypto: CryptoContext, subject_id: str, facet: str) -> list[SignalObservation]:
    rows = conn.execute(
        "SELECT * FROM observations WHERE subject_id = ? AND facet = ? ORDER BY created_at", (subject_id, facet)
    ).fetchall()
    return [_row_to_observation(conn, crypto, r) for r in rows]


def list_facets_for_subject(conn: sqlite3.Connection, subject_id: str) -> list[str]:
    rows = conn.execute("SELECT DISTINCT facet FROM observations WHERE subject_id = ?", (subject_id,)).fetchall()
    return [r["facet"] for r in rows]


# --------------------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------------------


def get_fact_by_facet_scope(conn: sqlite3.Connection, crypto: CryptoContext, subject_id: str, facet: str, scope_key: str) -> Optional[ProfileFact]:
    row = conn.execute(
        "SELECT * FROM facts WHERE subject_id = ? AND facet = ? AND scope_key = ? "
        "AND valid_to IS NULL ORDER BY CASE state WHEN 'CORRECTED' THEN 0 WHEN 'CONFIRMED' THEN 1 ELSE 2 END, "
        "valid_from DESC LIMIT 1",
        (subject_id, facet, scope_key),
    ).fetchone()
    return _row_to_fact(conn, crypto, row) if row else None


def get_fact(conn: sqlite3.Connection, crypto: CryptoContext, fact_id: str) -> Optional[ProfileFact]:
    row = conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
    return _row_to_fact(conn, crypto, row) if row else None


def _row_to_fact(conn: sqlite3.Connection, crypto: CryptoContext, r: sqlite3.Row) -> ProfileFact:
    dek = dek_for_generation(conn, crypto, r["key_generation_id"])
    value = json.loads(aead_decrypt(dek, r["value_enc"], aad=FACT_VALUE_AAD).decode("utf-8"))
    ci = json.loads(r["confidence_interval_json"]) if r["confidence_interval_json"] else None
    return ProfileFact(
        fact_id=r["fact_id"], subject_id=r["subject_id"], facet=r["facet"], value=value,
        scope=ContextScope.from_dict(json.loads(r["scope_json"])), state=FactState(r["state"]),
        confidence=r["confidence"], confidence_interval=tuple(ci) if ci else None,
        document_count=r["document_count"], source_count=r["source_count"],
        provenance_ids=json.loads(r["provenance_ids_json"]), synthesis_version=r["synthesis_version"],
        valid_from=r["valid_from"], valid_to=r["valid_to"], superseded_by=r["superseded_by"],
    )


def upsert_fact(conn: sqlite3.Connection, crypto: CryptoContext, fact: ProfileFact) -> None:
    """INSERT OR REPLACE by ``fact_id`` — the kernel (:mod:`operator_voice.kernel.synthesis`)
    decides whether a call site reuses an existing ``fact_id`` (update-in-place) or mints a new
    one; this function never makes that decision itself."""
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    value_enc = aead_encrypt(dek, json.dumps(fact.value).encode("utf-8"), aad=FACT_VALUE_AAD)
    conn.execute(
        "INSERT INTO facts(fact_id, subject_id, facet, value_enc, key_generation_id, scope_json, "
        "scope_key, state, confidence, confidence_interval_json, document_count, source_count, "
        "provenance_ids_json, synthesis_version, valid_from, valid_to, superseded_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(fact_id) DO UPDATE SET value_enc=excluded.value_enc, "
        "key_generation_id=excluded.key_generation_id, state=excluded.state, "
        "confidence=excluded.confidence, confidence_interval_json=excluded.confidence_interval_json, "
        "document_count=excluded.document_count, source_count=excluded.source_count, "
        "provenance_ids_json=excluded.provenance_ids_json, valid_to=excluded.valid_to, "
        "superseded_by=excluded.superseded_by",
        (
            fact.fact_id, fact.subject_id, fact.facet, value_enc, key_generation_id,
            json.dumps(fact.scope.as_dict()), fact.scope.key(), fact.state.value, fact.confidence,
            json.dumps(list(fact.confidence_interval)) if fact.confidence_interval else None,
            fact.document_count, fact.source_count, json.dumps(fact.provenance_ids),
            fact.synthesis_version, fact.valid_from, fact.valid_to, fact.superseded_by,
        ),
    )


def list_facts(conn: sqlite3.Connection, crypto: CryptoContext, subject_id: str, states: Optional[set[str]] = None) -> list[ProfileFact]:
    rows = conn.execute(
        "SELECT * FROM facts WHERE subject_id = ? AND valid_to IS NULL ORDER BY facet, scope_key", (subject_id,)
    ).fetchall()
    facts = [_row_to_fact(conn, crypto, r) for r in rows]
    if states is not None:
        facts = [f for f in facts if f.state.value in states]
    return facts


def deprecate_fact(conn: sqlite3.Connection, fact_id: str) -> None:
    conn.execute(
        "UPDATE facts SET state = ?, valid_to = ? WHERE fact_id = ?",
        (FactState.DEPRECATED.value, now_ts(), fact_id),
    )


def supersede_fact(conn: sqlite3.Connection, old_fact_id: str, new_fact_id: str) -> None:
    """Temporal-validity supersede (§13 M2 worklist 3): close out a drifted fact by marking it
    DEPRECATED with ``valid_to`` set and ``superseded_by`` pointing at its replacement, preserving
    the history rather than overwriting it in place."""
    conn.execute(
        "UPDATE facts SET state = ?, valid_to = ?, superseded_by = ? WHERE fact_id = ?",
        (FactState.DEPRECATED.value, now_ts(), new_fact_id, old_fact_id),
    )


# --------------------------------------------------------------------------------------
# Feedback events
# --------------------------------------------------------------------------------------


def insert_feedback_event(conn: sqlite3.Connection, crypto: CryptoContext, event: FeedbackEvent) -> None:
    """``reason`` carries the raw operator utterance or correction rationale (security review
    P1-1) — encrypted with the active content DEK, same as ``prior_value``/``new_value``. The
    legacy plaintext column is kept NOT NULL for schema stability but always written as an empty
    placeholder for new rows."""
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    prior_enc = aead_encrypt(dek, json.dumps(event.prior_value).encode("utf-8"), aad=FEEDBACK_PRIOR_AAD) if event.prior_value is not None else None
    new_enc = aead_encrypt(dek, json.dumps(event.new_value).encode("utf-8"), aad=FEEDBACK_NEW_AAD) if event.new_value is not None else None
    reason_enc = aead_encrypt(dek, event.reason.encode("utf-8"), aad=FEEDBACK_REASON_AAD)
    conn.execute(
        "INSERT INTO feedback_events(feedback_id, subject_id, utterance_digest, action, reason, reason_enc, "
        "target_fact_id, target_facet, prior_value_enc, new_value_enc, key_generation_id, actor, "
        "resulting_generation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            event.feedback_id, event.subject_id, event.utterance_digest, event.action.value, _REDACTED_PLACEHOLDER,
            reason_enc, event.target_fact_id, event.target_facet, prior_enc, new_enc, key_generation_id, event.actor,
            event.resulting_generation_id, event.created_at,
        ),
    )


def feedback_event_exists(conn: sqlite3.Connection, feedback_id: str) -> bool:
    return conn.execute("SELECT 1 FROM feedback_events WHERE feedback_id = ?", (feedback_id,)).fetchone() is not None


def list_feedback_events(conn: sqlite3.Connection, crypto: CryptoContext, subject_id: str) -> list[FeedbackEvent]:
    rows = conn.execute("SELECT * FROM feedback_events WHERE subject_id = ? ORDER BY created_at", (subject_id,)).fetchall()
    out = []
    for r in rows:
        prior = new = None
        if r["prior_value_enc"] is not None:
            dek = dek_for_generation(conn, crypto, r["key_generation_id"])
            prior = json.loads(aead_decrypt(dek, r["prior_value_enc"], aad=FEEDBACK_PRIOR_AAD).decode("utf-8"))
        if r["new_value_enc"] is not None:
            dek = dek_for_generation(conn, crypto, r["key_generation_id"])
            new = json.loads(aead_decrypt(dek, r["new_value_enc"], aad=FEEDBACK_NEW_AAD).decode("utf-8"))
        if r["reason_enc"] is not None and r["key_generation_id"]:
            dek = dek_for_generation(conn, crypto, r["key_generation_id"])
            reason = aead_decrypt(dek, r["reason_enc"], aad=FEEDBACK_REASON_AAD).decode("utf-8")
        else:
            reason = r["reason"]  # pre-migration row fallback only; never written to anymore
        out.append(
            FeedbackEvent(
                feedback_id=r["feedback_id"], subject_id=r["subject_id"], utterance_digest=r["utterance_digest"],
                action=FeedbackAction(r["action"]), reason=reason, target_fact_id=r["target_fact_id"],
                target_facet=r["target_facet"], prior_value=prior, new_value=new, actor=r["actor"],
                resulting_generation_id=r["resulting_generation_id"], created_at=r["created_at"],
            )
        )
    return out


# --------------------------------------------------------------------------------------
# Generations
# --------------------------------------------------------------------------------------


def insert_generation(conn: sqlite3.Connection, generation: ProfileGeneration) -> None:
    conn.execute(
        "INSERT INTO generations(generation_id, subject_id, schema_version, normalization_version, "
        "extraction_version, synthesis_version, taxonomy_version, policy_version, tokenizer_version, "
        "feature_registry_version, content_digest, creation_reason, parent_generation_id, "
        "diff_summary_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            generation.generation_id, generation.subject_id, generation.schema_version,
            generation.normalization_version, generation.extraction_version, generation.synthesis_version,
            generation.taxonomy_version, generation.policy_version, generation.tokenizer_version,
            generation.feature_registry_version, generation.content_digest, generation.creation_reason,
            generation.parent_generation_id, json.dumps(generation.diff_summary), generation.created_at,
        ),
    )


def _row_to_generation(r: sqlite3.Row) -> ProfileGeneration:
    return ProfileGeneration(
        generation_id=r["generation_id"], subject_id=r["subject_id"], schema_version=r["schema_version"],
        normalization_version=r["normalization_version"], extraction_version=r["extraction_version"],
        synthesis_version=r["synthesis_version"], taxonomy_version=r["taxonomy_version"],
        policy_version=r["policy_version"], tokenizer_version=r["tokenizer_version"],
        feature_registry_version=r["feature_registry_version"], content_digest=r["content_digest"],
        creation_reason=r["creation_reason"], parent_generation_id=r["parent_generation_id"],
        diff_summary=json.loads(r["diff_summary_json"]), created_at=r["created_at"],
    )


def get_latest_generation(conn: sqlite3.Connection, subject_id: str) -> Optional[ProfileGeneration]:
    row = conn.execute(
        "SELECT * FROM generations WHERE subject_id = ? ORDER BY created_at DESC LIMIT 1", (subject_id,)
    ).fetchone()
    return _row_to_generation(row) if row else None


def get_generation(conn: sqlite3.Connection, generation_id: str) -> Optional[ProfileGeneration]:
    row = conn.execute("SELECT * FROM generations WHERE generation_id = ?", (generation_id,)).fetchone()
    return _row_to_generation(row) if row else None


def list_generations(conn: sqlite3.Connection, subject_id: str) -> list[ProfileGeneration]:
    rows = conn.execute("SELECT * FROM generations WHERE subject_id = ? ORDER BY created_at", (subject_id,)).fetchall()
    return [_row_to_generation(r) for r in rows]


# --------------------------------------------------------------------------------------
# Backend config / sync state (§5 ProfileBackendConfig / ProfileSyncState)
# --------------------------------------------------------------------------------------


def get_backend_config(conn: sqlite3.Connection) -> ProfileBackendConfig:
    row = conn.execute("SELECT * FROM backend_config WHERE id = 1").fetchone()
    if not row:
        return ProfileBackendConfig()
    return ProfileBackendConfig(
        mode=BackendMode(row["mode"]), active=bool(row["active"]), remote_reference_token=row["remote_reference_token"],
        key_generation_ref=row["key_generation_ref"],
        last_verified_durability=json.loads(row["last_verified_durability_json"]) if row["last_verified_durability_json"] else None,
        health=row["health"],
    )


def set_backend_config(conn: sqlite3.Connection, cfg: ProfileBackendConfig) -> None:
    conn.execute(
        "INSERT INTO backend_config(id, mode, active, remote_reference_token, key_generation_ref, "
        "last_verified_durability_json, health) VALUES (1,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET mode=excluded.mode, active=excluded.active, "
        "remote_reference_token=excluded.remote_reference_token, key_generation_ref=excluded.key_generation_ref, "
        "last_verified_durability_json=excluded.last_verified_durability_json, health=excluded.health",
        (
            cfg.mode.value, int(cfg.active), cfg.remote_reference_token, cfg.key_generation_ref,
            json.dumps(cfg.last_verified_durability) if cfg.last_verified_durability else None, cfg.health,
        ),
    )


def get_sync_state(conn: sqlite3.Connection) -> ProfileSyncState:
    row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
    if not row:
        return ProfileSyncState()
    return ProfileSyncState(
        local_generation_id=row["local_generation_id"], remote_generation_id=row["remote_generation_id"],
        exact_parent_sha=row["exact_parent_sha"], publish_status=SyncStatus(row["publish_status"]),
        conflict_set=json.loads(row["conflict_set_json"]), last_verified_clean_room=row["last_verified_clean_room"],
    )


def set_sync_state(conn: sqlite3.Connection, state: ProfileSyncState) -> None:
    conn.execute(
        "INSERT INTO sync_state(id, local_generation_id, remote_generation_id, exact_parent_sha, "
        "publish_status, conflict_set_json, last_verified_clean_room) VALUES (1,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET local_generation_id=excluded.local_generation_id, "
        "remote_generation_id=excluded.remote_generation_id, exact_parent_sha=excluded.exact_parent_sha, "
        "publish_status=excluded.publish_status, conflict_set_json=excluded.conflict_set_json, "
        "last_verified_clean_room=excluded.last_verified_clean_room",
        (
            state.local_generation_id, state.remote_generation_id, state.exact_parent_sha,
            state.publish_status.value, json.dumps(state.conflict_set), state.last_verified_clean_room,
        ),
    )


# --------------------------------------------------------------------------------------
# Challenges (§5 OperationChallenge)
# --------------------------------------------------------------------------------------


def insert_challenge(conn: sqlite3.Connection, challenge: OperationChallenge) -> None:
    conn.execute(
        "INSERT INTO challenges(challenge_id, operation, targets_json, literal, consequence_json, "
        "issued_at, expires_at, used) VALUES (?,?,?,?,?,?,?,?)",
        (
            challenge.challenge_id, challenge.operation, json.dumps(challenge.targets), challenge.literal,
            json.dumps(asdict(challenge.consequence)), challenge.issued_at, challenge.expires_at,
            int(challenge.used),
        ),
    )


def get_challenge(conn: sqlite3.Connection, challenge_id: str) -> Optional[OperationChallenge]:
    row = conn.execute("SELECT * FROM challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
    if not row:
        return None
    c = json.loads(row["consequence_json"])
    return OperationChallenge(
        challenge_id=row["challenge_id"], operation=row["operation"], targets=json.loads(row["targets_json"]),
        literal=row["literal"], consequence=ConsequenceDescriptor(**c), issued_at=row["issued_at"],
        expires_at=row["expires_at"], used=bool(row["used"]),
    )


def mark_challenge_used(conn: sqlite3.Connection, challenge_id: str) -> None:
    conn.execute("UPDATE challenges SET used = 1 WHERE challenge_id = ?", (challenge_id,))


def find_pending_challenge(conn: sqlite3.Connection, operation: str, targets: list[str]) -> Optional[OperationChallenge]:
    """Finds an unused, unexpired challenge previously issued for this exact operation+targets
    (§6: 'a one-use operation/target/generation-bound challenge'). Used so a caller need only
    resupply the literal, never the opaque ``challenge_id``, on the confirming call."""
    now = now_ts()
    rows = conn.execute(
        "SELECT * FROM challenges WHERE operation = ? AND used = 0 AND expires_at > ? ORDER BY issued_at DESC",
        (operation, now),
    ).fetchall()
    target_set = set(targets)
    for row in rows:
        row_targets = set(json.loads(row["targets_json"]))
        if target_set.issubset(row_targets):
            c = json.loads(row["consequence_json"])
            return OperationChallenge(
                challenge_id=row["challenge_id"], operation=row["operation"], targets=json.loads(row["targets_json"]),
                literal=row["literal"], consequence=ConsequenceDescriptor(**c), issued_at=row["issued_at"],
                expires_at=row["expires_at"], used=bool(row["used"]),
            )
    return None


# --------------------------------------------------------------------------------------
# Cancellation (§8, §10.10)
# --------------------------------------------------------------------------------------


def get_cancellation_state(conn: sqlite3.Connection) -> CancellationState:
    row = conn.execute("SELECT * FROM cancellation_state WHERE id = 1").fetchone()
    if not row:
        return CancellationState()
    return CancellationState(
        off=bool(row["off"]), reason=row["reason"], set_at=row["set_at"],
        checkpoints=json.loads(row["checkpoints_json"]),
    )


def set_cancellation_state(conn: sqlite3.Connection, state: CancellationState) -> None:
    conn.execute(
        "INSERT INTO cancellation_state(id, off, reason, set_at, checkpoints_json) VALUES (1,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET off=excluded.off, reason=excluded.reason, set_at=excluded.set_at, "
        "checkpoints_json=excluded.checkpoints_json",
        (int(state.off), state.reason, state.set_at, json.dumps(state.checkpoints)),
    )


# --------------------------------------------------------------------------------------
# Validation runs / export records / model call records (content-free where required)
# --------------------------------------------------------------------------------------


def insert_validation_run(conn: sqlite3.Connection, run: ValidationRun) -> None:
    conn.execute(
        "INSERT INTO validation_runs(run_id, subject_id, draft_digest, checks_json, outcome, "
        "versions_json, gateway_metadata_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            run.run_id, run.subject_id, run.draft_digest, json.dumps(run.checks), run.outcome.value,
            json.dumps(run.versions), json.dumps(run.gateway_metadata) if run.gateway_metadata else None,
            run.created_at, run.expires_at,
        ),
    )


def insert_export_record(conn: sqlite3.Connection, manifest: ExportManifest) -> None:
    # Content-free by schema (§5.1): only scope/destination/timestamps, never the facts themselves
    # — the human-readable ExportManifest.facts payload lives ONLY in the destination file.
    conn.execute(
        "INSERT INTO export_records(export_id, subject_id, scope, destination, created_at, expires_at) "
        "VALUES (?,?,?,?,?,?)",
        (manifest.export_id, manifest.subject_id, manifest.scope, manifest.destination, manifest.created_at, manifest.expires_at),
    )


def insert_model_call_record(conn: sqlite3.Connection, record: ModelCallRecord) -> None:
    conn.execute(
        "INSERT INTO model_call_records(call_id, provider, model, data_class, purpose, outcome, "
        "duration_ms, cancelled, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            record.call_id, record.provider, record.model, record.data_class, record.purpose,
            record.outcome, record.duration_ms, int(record.cancelled), record.created_at,
        ),
    )


def list_model_call_records(conn: sqlite3.Connection, limit: int = 50) -> list[ModelCallRecord]:
    rows = conn.execute(
        "SELECT * FROM model_call_records ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        ModelCallRecord(
            call_id=r["call_id"], provider=r["provider"], model=r["model"], data_class=r["data_class"],
            purpose=r["purpose"], outcome=r["outcome"], duration_ms=r["duration_ms"],
            cancelled=bool(r["cancelled"]), created_at=r["created_at"],
        )
        for r in rows
    ]


# --------------------------------------------------------------------------------------
# Review queue (§13 M2 worklist 3) — detail is encrypted (may quote a fact value)
# --------------------------------------------------------------------------------------

REVIEW_DETAIL_AAD = b"review_item_detail"


def insert_review_item(conn: sqlite3.Connection, crypto: CryptoContext, item: ReviewItem) -> None:
    key_generation_id, dek = ensure_active_key_generation(conn, crypto)
    detail_enc = aead_encrypt(dek, (item.detail or "").encode("utf-8"), aad=REVIEW_DETAIL_AAD)
    conn.execute(
        "INSERT INTO review_items(review_id, subject_id, reason, detail_enc, key_generation_id, "
        "facet, scope_json, scope_key, related_fact_id, related_ids_json, status, created_at, "
        "resolved_at, resolution) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            item.review_id, item.subject_id, item.reason.value, detail_enc, key_generation_id,
            item.facet, json.dumps(item.scope.as_dict()) if item.scope else None,
            item.scope.key() if item.scope else None, item.related_fact_id,
            json.dumps(item.related_ids), item.status.value, item.created_at,
            item.resolved_at, item.resolution,
        ),
    )


def _row_to_review_item(conn: sqlite3.Connection, crypto: CryptoContext, r: sqlite3.Row) -> ReviewItem:
    detail = ""
    if r["detail_enc"] is not None and r["key_generation_id"]:
        dek = dek_for_generation(conn, crypto, r["key_generation_id"])
        detail = aead_decrypt(dek, r["detail_enc"], aad=REVIEW_DETAIL_AAD).decode("utf-8")
    return ReviewItem(
        review_id=r["review_id"], subject_id=r["subject_id"], reason=ReviewReason(r["reason"]),
        detail=detail, facet=r["facet"],
        scope=ContextScope.from_dict(json.loads(r["scope_json"])) if r["scope_json"] else None,
        related_fact_id=r["related_fact_id"], related_ids=json.loads(r["related_ids_json"]),
        status=ReviewStatus(r["status"]), created_at=r["created_at"],
        resolved_at=r["resolved_at"], resolution=r["resolution"],
    )


def list_review_items(
    conn: sqlite3.Connection, crypto: CryptoContext, subject_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[ReviewItem]:
    clauses = []
    params: list[Any] = []
    if subject_id:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM review_items{where} ORDER BY created_at", params
    ).fetchall()
    return [_row_to_review_item(conn, crypto, r) for r in rows]


def get_review_item(conn: sqlite3.Connection, crypto: CryptoContext, review_id: str) -> Optional[ReviewItem]:
    row = conn.execute("SELECT * FROM review_items WHERE review_id = ?", (review_id,)).fetchone()
    return _row_to_review_item(conn, crypto, row) if row else None


def resolve_review_item(conn: sqlite3.Connection, review_id: str, status: str, resolution: str) -> bool:
    cur = conn.execute(
        "UPDATE review_items SET status = ?, resolution = ?, resolved_at = ? WHERE review_id = ? AND status = 'OPEN'",
        (status, resolution, now_ts(), review_id),
    )
    return (cur.rowcount or 0) > 0


def has_open_review(
    conn: sqlite3.Connection, subject_id: str, facet: Optional[str], scope_key: Optional[str], reason: str
) -> bool:
    """De-dup guard: is there already an OPEN review item for this exact (subject, facet, scope,
    reason)? Prevents a recurring condition (e.g. a persistently single-source fact) from spamming
    the queue with a new item on every ingest."""
    row = conn.execute(
        "SELECT 1 FROM review_items WHERE subject_id = ? AND status = 'OPEN' AND reason = ? "
        "AND facet IS ? AND scope_key IS ? LIMIT 1",
        (subject_id, reason, facet, scope_key),
    ).fetchone()
    return row is not None


def count_open_review_items(conn: sqlite3.Connection, subject_id: Optional[str] = None) -> int:
    if subject_id:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM review_items WHERE status = 'OPEN' AND subject_id = ?", (subject_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS n FROM review_items WHERE status = 'OPEN'").fetchone()
    return int(row["n"])


# --------------------------------------------------------------------------------------
# Gateway config (§13 M2 worklist 4) — both egress switches default disabled at the schema level
# --------------------------------------------------------------------------------------


def get_gateway_config(conn: sqlite3.Connection) -> GatewayConfig:
    row = conn.execute("SELECT * FROM gateway_config WHERE id = 1").fetchone()
    if not row:
        return GatewayConfig()
    return GatewayConfig(
        operator_egress_enabled=bool(row["operator_egress_enabled"]),
        external_egress_enabled=bool(row["external_egress_enabled"]),
        provider=row["provider"], model=row["model"],
        allowed_data_classes=json.loads(row["allowed_data_classes_json"]),
        timeout_ms=row["timeout_ms"], updated_at=row["updated_at"],
    )


def set_gateway_config(conn: sqlite3.Connection, cfg: GatewayConfig) -> None:
    conn.execute(
        "INSERT INTO gateway_config(id, operator_egress_enabled, external_egress_enabled, provider, "
        "model, allowed_data_classes_json, timeout_ms, updated_at) VALUES (1,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET operator_egress_enabled=excluded.operator_egress_enabled, "
        "external_egress_enabled=excluded.external_egress_enabled, provider=excluded.provider, "
        "model=excluded.model, allowed_data_classes_json=excluded.allowed_data_classes_json, "
        "timeout_ms=excluded.timeout_ms, updated_at=excluded.updated_at",
        (
            int(cfg.operator_egress_enabled), int(cfg.external_egress_enabled), cfg.provider,
            cfg.model, json.dumps(cfg.allowed_data_classes), cfg.timeout_ms, cfg.updated_at or now_ts(),
        ),
    )


# --------------------------------------------------------------------------------------
# Continual curation (§13 M3) — curation runs + per-source curation health. Content-free:
# only counts, enums, booleans, and timestamps are stored (§5.1 no-content rule).
# --------------------------------------------------------------------------------------

STALE_CURATION_RUN_SECONDS = 6 * 60 * 60  # a RUNNING row older than this is presumed interrupted


def insert_curation_run(conn: sqlite3.Connection, run: CurationRun) -> None:
    conn.execute(
        "INSERT INTO curation_runs(run_id, trigger, status, started_at, finished_at, sources_total, "
        "sources_processed, sources_failed, documents_new, observations_new, facets_touched, "
        "contradictions, catch_up_gap_seconds, pending_continuation, published, publish_status, "
        "recovered_runs, learning_summary_json, error_class, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run.run_id, run.trigger.value, run.status.value, run.started_at, run.finished_at,
            run.sources_total, run.sources_processed, run.sources_failed, run.documents_new,
            run.observations_new, run.facets_touched, run.contradictions, run.catch_up_gap_seconds,
            int(run.pending_continuation), int(run.published), run.publish_status, run.recovered_runs,
            json.dumps(run.learning_summary) if run.learning_summary else None, run.error_class, run.notes,
        ),
    )


def update_curation_run(conn: sqlite3.Connection, run: CurationRun) -> None:
    conn.execute(
        "UPDATE curation_runs SET trigger=?, status=?, started_at=?, finished_at=?, sources_total=?, "
        "sources_processed=?, sources_failed=?, documents_new=?, observations_new=?, facets_touched=?, "
        "contradictions=?, catch_up_gap_seconds=?, pending_continuation=?, published=?, publish_status=?, "
        "recovered_runs=?, learning_summary_json=?, error_class=?, notes=? WHERE run_id=?",
        (
            run.trigger.value, run.status.value, run.started_at, run.finished_at, run.sources_total,
            run.sources_processed, run.sources_failed, run.documents_new, run.observations_new,
            run.facets_touched, run.contradictions, run.catch_up_gap_seconds, int(run.pending_continuation),
            int(run.published), run.publish_status, run.recovered_runs,
            json.dumps(run.learning_summary) if run.learning_summary else None, run.error_class, run.notes,
            run.run_id,
        ),
    )


def _row_to_curation_run(r: sqlite3.Row) -> CurationRun:
    return CurationRun(
        run_id=r["run_id"], trigger=CurationTrigger(r["trigger"]), status=CurationRunStatus(r["status"]),
        started_at=r["started_at"], finished_at=r["finished_at"], sources_total=r["sources_total"],
        sources_processed=r["sources_processed"], sources_failed=r["sources_failed"],
        documents_new=r["documents_new"], observations_new=r["observations_new"],
        facets_touched=r["facets_touched"], contradictions=r["contradictions"],
        catch_up_gap_seconds=r["catch_up_gap_seconds"], pending_continuation=bool(r["pending_continuation"]),
        published=bool(r["published"]), publish_status=r["publish_status"], recovered_runs=r["recovered_runs"],
        learning_summary=json.loads(r["learning_summary_json"]) if r["learning_summary_json"] else {},
        error_class=r["error_class"], notes=r["notes"],
    )


def get_curation_run(conn: sqlite3.Connection, run_id: str) -> Optional[CurationRun]:
    row = conn.execute("SELECT * FROM curation_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_curation_run(row) if row else None


def list_curation_runs(conn: sqlite3.Connection, limit: int = 20) -> list[CurationRun]:
    rows = conn.execute(
        "SELECT * FROM curation_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_curation_run(r) for r in rows]


def get_last_completed_curation_run(conn: sqlite3.Connection) -> Optional[CurationRun]:
    row = conn.execute(
        "SELECT * FROM curation_runs WHERE status = 'COMPLETED' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return _row_to_curation_run(row) if row else None


def reclaim_stale_curation_runs(conn: sqlite3.Connection, *, exclude_run_id: Optional[str] = None) -> int:
    """§13 M3 stale-operation recovery: any ``RUNNING`` row (other than the caller's own current
    run) whose ``started_at`` predates :data:`STALE_CURATION_RUN_SECONDS` is presumed interrupted
    (crash / kill / long sleep). Marks it ``RECOVERED`` with a ``finished_at`` so a subsequent
    tick never treats it as live. Returns the count reclaimed. Because every per-source ingest is
    its own atomic transaction with cursor advancement, the reclaimed run's committed work is
    already durable and idempotent — recovery is pure bookkeeping, never a data repair."""
    cutoff = now_ts() - STALE_CURATION_RUN_SECONDS
    params: list[Any] = [now_ts(), cutoff]
    exclude_clause = ""
    if exclude_run_id is not None:
        exclude_clause = " AND run_id != ?"
        params.append(exclude_run_id)
    cur = conn.execute(
        "UPDATE curation_runs SET status = 'RECOVERED', finished_at = ? "
        "WHERE status = 'RUNNING' AND started_at <= ?" + exclude_clause,
        params,
    )
    return cur.rowcount or 0


def get_source_curation_state(conn: sqlite3.Connection, source_id: str) -> Optional[SourceCurationState]:
    row = conn.execute(
        "SELECT * FROM source_curation_state WHERE source_id = ?", (source_id,)
    ).fetchone()
    if not row:
        return None
    return SourceCurationState(
        source_id=row["source_id"], last_curated_at=row["last_curated_at"],
        last_success_at=row["last_success_at"], consecutive_failures=row["consecutive_failures"],
        last_error_class=row["last_error_class"], last_run_id=row["last_run_id"],
        pending_continuation=bool(row["pending_continuation"]),
    )


def upsert_source_curation_state(conn: sqlite3.Connection, state: SourceCurationState) -> None:
    conn.execute(
        "INSERT INTO source_curation_state(source_id, last_curated_at, last_success_at, "
        "consecutive_failures, last_error_class, last_run_id, pending_continuation) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(source_id) DO UPDATE SET last_curated_at=excluded.last_curated_at, "
        "last_success_at=excluded.last_success_at, consecutive_failures=excluded.consecutive_failures, "
        "last_error_class=excluded.last_error_class, last_run_id=excluded.last_run_id, "
        "pending_continuation=excluded.pending_continuation",
        (
            state.source_id, state.last_curated_at, state.last_success_at, state.consecutive_failures,
            state.last_error_class, state.last_run_id, int(state.pending_continuation),
        ),
    )


def list_source_curation_states(conn: sqlite3.Connection) -> list[SourceCurationState]:
    rows = conn.execute("SELECT * FROM source_curation_state ORDER BY source_id").fetchall()
    return [
        SourceCurationState(
            source_id=r["source_id"], last_curated_at=r["last_curated_at"],
            last_success_at=r["last_success_at"], consecutive_failures=r["consecutive_failures"],
            last_error_class=r["last_error_class"], last_run_id=r["last_run_id"],
            pending_continuation=bool(r["pending_continuation"]),
        )
        for r in rows
    ]


__all__ = [name for name in dir() if not name.startswith("_")]


def repeated_evidence_ids(records) -> frozenset:
    """Shared keeper rule for persisted documents and a read-only candidate preview."""
    groups = {}
    for record in records:
        adapter, key = record["adapter_type"], record["text_key"]
        if key and adapter in {"gmail_export", "slack_export", "drive_export"}:
            groups.setdefault((adapter, key), []).append(record)
    excluded = set()
    for (adapter, _), group in groups.items():
        if len(group) < 2:
            continue
        def order(record):
            native = record["source_native_id"]
            try:
                if adapter == "slack_export":
                    stamp = Decimal(native.rsplit(":", 1)[-1])
                    if not stamp.is_finite():
                        stamp = Decimal("Infinity")
                else:
                    stamp = datetime.fromisoformat(record["native_revision"].replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError, AttributeError, InvalidOperation):
                stamp = float("inf")
            return stamp, native, record["id"]
        excluded.update(r["id"] for r in (group if adapter == "gmail_export" else sorted(group, key=order)[1:]))
    return frozenset(excluded)


def repeated_document_ids(conn: sqlite3.Connection, subject_id: str) -> frozenset[str]:
    rows = conn.execute(
        "SELECT d.document_id,d.source_native_id,d.native_revision,d.context_json,s.adapter_type "
        "FROM documents d JOIN sources s ON s.source_id=d.source_id "
        "WHERE d.subject_id=? AND d.authorship_state=?", (subject_id, AuthorshipState.SUBJECT.value)).fetchall()
    return repeated_evidence_ids({"id": r["document_id"], "source_native_id": r["source_native_id"],
                                  "native_revision": r["native_revision"], "adapter_type": r["adapter_type"],
                                  "text_key": json.loads(r["context_json"]).get("text_key")} for r in rows)


def count_documents_for_source(conn: sqlite3.Connection, source_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents WHERE source_id=?", (source_id,)).fetchone()[0]


def learned_native_ids(conn: sqlite3.Connection, source_id: str) -> set[str]:
    """Records with actual persisted observations, not empty/quarantined registrations."""
    rows = conn.execute(
        "SELECT DISTINCT d.source_native_id FROM documents d JOIN observations o ON o.document_id=d.document_id "
        "WHERE d.source_id=? AND d.authorship_state='SUBJECT'", (source_id,)).fetchall()
    return {row[0] for row in rows}


def document_has_analysis_metadata(conn: sqlite3.Connection, document_id: str) -> bool:
    row = conn.execute("SELECT context_json FROM documents WHERE document_id=?", (document_id,)).fetchone()
    return row is not None and {"words", "text_key"}.issubset(json.loads(row[0]))


def supersede_inferred_facts_for_scope(conn: sqlite3.Connection, fact: ProfileFact) -> None:
    """Close all legacy inferred duplicates while retaining every operator-authoritative row."""
    conn.execute(
        "UPDATE facts SET state=?, valid_to=?, superseded_by=? WHERE subject_id=? AND facet=? "
        "AND scope_key=? AND valid_to IS NULL AND fact_id!=? AND state NOT IN (?,?)",
        (FactState.DEPRECATED.value, now_ts(), fact.fact_id, fact.subject_id, fact.facet, fact.scope.key(),
         fact.fact_id, FactState.CORRECTED.value, FactState.CONFIRMED.value))
