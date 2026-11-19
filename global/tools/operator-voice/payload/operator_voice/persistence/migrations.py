"""Schema migrations — build plan v3 §5 "Schema v1, contract fixtures, migrations, validators,
and the sink registry ship in M1. There is no loose-JSON phase." and §11 "ships migration
metadata, encrypted backup/restore, schema compatibility checks, and downgrade refusal where a
safe reverse migration does not exist."

Every sensitive column is named with an ``_enc`` suffix and holds an AEAD ciphertext blob
(nonce||ct) produced by :mod:`operator_voice.persistence.crypto`; every other column is
non-sensitive (opaque IDs, enums, timestamps, counts) and stays in the clear so it can be
indexed/queried.
"""

from __future__ import annotations

import sqlite3

from operator_voice.persistence.sqlite import transaction

CURRENT_SCHEMA_VERSION = 6

_MIGRATION_1_SQL = """
CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE key_generations (
    generation_id TEXT PRIMARY KEY,
    wrapped_dek BLOB NOT NULL,
    created_at REAL NOT NULL,
    destroyed_at REAL
);

CREATE TABLE subjects (
    subject_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    display_label TEXT NOT NULL,
    approved_purposes_json TEXT NOT NULL,
    consent_basis TEXT NOT NULL,
    generation_permission INTEGER NOT NULL,
    retention_policy TEXT NOT NULL,
    active INTEGER NOT NULL,
    created_at REAL NOT NULL,
    reviewed_at REAL
);

CREATE TABLE subject_aliases (
    alias_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    source_type TEXT NOT NULL,
    source_native_id_enc BLOB NOT NULL,
    key_generation_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    verification_state TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_to REAL,
    collision_review TEXT
);

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    adapter_type TEXT NOT NULL,
    canonical_root TEXT NOT NULL,
    opted_in_at REAL NOT NULL,
    approved_purpose TEXT NOT NULL,
    active INTEGER NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    retention_policy TEXT NOT NULL,
    limits_json TEXT NOT NULL,
    role_identity_json TEXT NOT NULL,
    cursor TEXT
);

CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_native_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    locator TEXT NOT NULL,
    content_enc BLOB,
    key_generation_id TEXT,
    content_cleared_at REAL,
    created_at REAL NOT NULL,
    context_json TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    authorship_state TEXT NOT NULL,
    quarantine_reason TEXT,
    expires_at REAL
);
CREATE INDEX idx_documents_subject ON documents(subject_id);
CREATE INDEX idx_documents_source ON documents(source_id);
CREATE UNIQUE INDEX idx_documents_source_native ON documents(source_id, source_native_id);

CREATE TABLE observations (
    observation_id TEXT PRIMARY KEY,
    observation_key TEXT NOT NULL UNIQUE,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    segment_id TEXT NOT NULL,
    facet TEXT NOT NULL,
    value_enc BLOB NOT NULL,
    distribution_enc BLOB,
    key_generation_id TEXT NOT NULL,
    context_json TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    method_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    quality_flags_json TEXT NOT NULL
);
CREATE INDEX idx_observations_subject_facet ON observations(subject_id, facet);
CREATE INDEX idx_observations_document ON observations(document_id);

CREATE TABLE evidence_records (
    evidence_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    facet TEXT NOT NULL,
    context_json TEXT NOT NULL,
    observation_ids_json TEXT NOT NULL,
    document_diversity INTEGER NOT NULL,
    source_diversity INTEGER NOT NULL,
    contradiction INTEGER NOT NULL,
    outlier INTEGER NOT NULL,
    confidence_inputs_json TEXT NOT NULL,
    method_versions_json TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_to REAL,
    provenance_json TEXT NOT NULL
);
CREATE INDEX idx_evidence_subject_facet ON evidence_records(subject_id, facet);

CREATE TABLE facts (
    fact_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    facet TEXT NOT NULL,
    value_enc BLOB NOT NULL,
    key_generation_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    state TEXT NOT NULL,
    confidence REAL NOT NULL,
    confidence_interval_json TEXT,
    document_count INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    provenance_ids_json TEXT NOT NULL,
    synthesis_version TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_to REAL,
    superseded_by TEXT
);
CREATE INDEX idx_facts_subject_facet_scope ON facts(subject_id, facet, scope_key);
CREATE INDEX idx_facts_subject_state ON facts(subject_id, state);

CREATE TABLE feedback_events (
    feedback_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    utterance_digest TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    target_fact_id TEXT,
    target_facet TEXT,
    prior_value_enc BLOB,
    new_value_enc BLOB,
    key_generation_id TEXT,
    actor TEXT NOT NULL,
    resulting_generation_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX idx_feedback_subject ON feedback_events(subject_id);

CREATE TABLE generations (
    generation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    schema_version TEXT NOT NULL,
    normalization_version TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    synthesis_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    tokenizer_version TEXT NOT NULL,
    feature_registry_version TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    creation_reason TEXT NOT NULL,
    parent_generation_id TEXT,
    diff_summary_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX idx_generations_subject ON generations(subject_id, created_at);

CREATE TABLE backend_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL,
    active INTEGER NOT NULL,
    remote_reference_token TEXT,
    key_generation_ref TEXT,
    last_verified_durability_json TEXT,
    health TEXT NOT NULL
);

CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    local_generation_id TEXT,
    remote_generation_id TEXT,
    exact_parent_sha TEXT,
    publish_status TEXT NOT NULL,
    conflict_set_json TEXT NOT NULL,
    last_verified_clean_room REAL
);

CREATE TABLE model_call_records (
    call_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    data_class TEXT NOT NULL,
    purpose TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    cancelled INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    consumer TEXT,
    result TEXT NOT NULL,
    versions_json TEXT NOT NULL,
    deletion_counts_json TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX idx_audit_created ON audit_events(created_at);

CREATE TABLE challenges (
    challenge_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    targets_json TEXT NOT NULL,
    literal TEXT NOT NULL,
    consequence_json TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE cancellation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    off INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    set_at REAL,
    checkpoints_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE validation_runs (
    run_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    draft_digest TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    outcome TEXT NOT NULL,
    versions_json TEXT NOT NULL,
    gateway_metadata_json TEXT,
    created_at REAL NOT NULL,
    expires_at REAL
);

CREATE TABLE export_records (
    export_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    destination TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL
);
"""

_MIGRATION_2_SQL = """
ALTER TABLE key_generations ADD COLUMN purpose TEXT NOT NULL DEFAULT 'content';
CREATE INDEX idx_key_generations_purpose ON key_generations(purpose, destroyed_at);
"""

_MIGRATION_3_SQL = """
ALTER TABLE feedback_events ADD COLUMN reason_enc BLOB;
ALTER TABLE sources ADD COLUMN canonical_root_enc BLOB;
ALTER TABLE sources ADD COLUMN key_generation_id TEXT;
ALTER TABLE documents ADD COLUMN locator_enc BLOB;
"""

_MIGRATION_4_SQL = """
CREATE TABLE review_items (
    review_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
    reason TEXT NOT NULL,
    detail_enc BLOB,
    key_generation_id TEXT,
    facet TEXT,
    scope_json TEXT,
    scope_key TEXT,
    related_fact_id TEXT,
    related_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at REAL NOT NULL,
    resolved_at REAL,
    resolution TEXT
);
CREATE INDEX idx_review_subject_status ON review_items(subject_id, status);

CREATE TABLE gateway_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    operator_egress_enabled INTEGER NOT NULL DEFAULT 0,
    external_egress_enabled INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    model TEXT,
    allowed_data_classes_json TEXT NOT NULL DEFAULT '[]',
    timeout_ms INTEGER NOT NULL DEFAULT 20000,
    updated_at REAL
);
"""

_MIGRATION_5_SQL = """
CREATE TABLE curation_runs (
    run_id TEXT PRIMARY KEY,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    sources_total INTEGER NOT NULL DEFAULT 0,
    sources_processed INTEGER NOT NULL DEFAULT 0,
    sources_failed INTEGER NOT NULL DEFAULT 0,
    documents_new INTEGER NOT NULL DEFAULT 0,
    observations_new INTEGER NOT NULL DEFAULT 0,
    facets_touched INTEGER NOT NULL DEFAULT 0,
    contradictions INTEGER NOT NULL DEFAULT 0,
    catch_up_gap_seconds REAL,
    pending_continuation INTEGER NOT NULL DEFAULT 0,
    published INTEGER NOT NULL DEFAULT 0,
    publish_status TEXT,
    recovered_runs INTEGER NOT NULL DEFAULT 0,
    learning_summary_json TEXT,
    error_class TEXT,
    notes TEXT
);
CREATE INDEX idx_curation_runs_started ON curation_runs(started_at);
CREATE INDEX idx_curation_runs_status ON curation_runs(status);

CREATE TABLE source_curation_state (
    source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
    last_curated_at REAL,
    last_success_at REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error_class TEXT,
    last_run_id TEXT,
    pending_continuation INTEGER NOT NULL DEFAULT 0
);
"""

# M6 (Drive adapter M1, ADR 0002 Decision 2): a nullable opaque native-revision comparator on the
# document row. It holds Drive's file ``modified_time`` (ISO-8601, lexically ordered) so the
# store's Drive-only supersede-if-newer path can decide "is this revision strictly newer than the
# one we already have for this file_id?". It is NOT content (a timestamp string, like ``created_at``),
# stays NULL for every pre-Drive source, and is additive — no existing row or column changes.
_MIGRATION_6_SQL = """
ALTER TABLE documents ADD COLUMN native_revision TEXT;
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial schema v1 (build plan §5)", _MIGRATION_1_SQL),
    (
        2,
        "key_generations.purpose discriminator (§5.1: profile-pack objects use an independent "
        "data-key generation from local content — without this column, "
        "ensure_active_key_generation(content) and ensure_active_key_generation(profile_pack) "
        "would silently share the same 'most recent non-destroyed' row)",
        _MIGRATION_2_SQL,
    ),
    (
        3,
        "encrypt free-text columns left in cleartext by mistake (security review P1-1/P1-3): "
        "feedback_events.reason carried the raw operator utterance, and sources.canonical_root / "
        "documents.locator carried real filesystem paths, in a store whose stated invariant is "
        "'every column that could carry raw text is encrypted'. The old plaintext columns stay "
        "NOT NULL for schema stability but are now written as an empty placeholder; the new "
        "*_enc columns hold the real AEAD ciphertext going forward. There is no production data "
        "yet (pre-GA), so no data-preserving backfill is attempted.",
        _MIGRATION_3_SQL,
    ),
    (
        4,
        "M2 (§13 worklist 3/4): operator review queue (review_items, with an encrypted detail_enc "
        "column because a review detail may quote a fact value) and the singleton gateway_config "
        "(operator/EXTERNAL egress switches DEFAULT 0 = disabled — the default-deny invariant is "
        "enforced at the schema default, not only in code, D7/D17).",
        _MIGRATION_4_SQL,
    ),
    (
        5,
        "M3 (§13 worklist 1-3): continual-curation bookkeeping. curation_runs is the durable, "
        "content-free (§5.1: counts/enums/timestamps only) record of each passive scheduled tick — "
        "a RUNNING row that outlives its process is reclaimed as RECOVERED on the next tick "
        "(stale-operation recovery). source_curation_state tracks per-source watermark health "
        "(last-curated/failure count) so a persistently-failing source is surfaced without "
        "blocking the others; the incremental cursor itself stays on sources.cursor.",
        _MIGRATION_5_SQL,
    ),
    (
        6,
        "Drive adapter M1 (ADR 0002 Decision 2): documents.native_revision — a nullable, opaque "
        "revision comparator (Drive's file modified_time, ISO-8601). Drive persists one document per "
        "file_id (dedup key = file_id alone), carrying the revision as PROVENANCE, not identity; this "
        "column lets the store's single, Drive-only supersede-if-newer path order revisions of the "
        "same file_id (strictly-greater-else-no-op). It is a timestamp string (not content, like "
        "created_at), stays NULL for every pre-Drive source, and no data-preserving backfill is "
        "needed (pre-GA, and NULL is the correct value for every existing non-revisioned row).",
        _MIGRATION_6_SQL,
    ),
]


class SchemaError(RuntimeError):
    pass


def _split_statements(sql: str) -> list[str]:
    """Split a DDL script into individual statements for ``conn.execute()``. NOT a general SQL
    parser (no semicolon-in-string-literal handling) — sufficient because every migration script
    in ``MIGRATIONS`` is plain DDL with no string literals containing ';'. Deliberately avoids
    ``sqlite3.Connection.executescript()``, which issues an implicit COMMIT before running and so
    silently breaks out of the surrounding ``transaction()`` context manager's explicit BEGIN,
    defeating the "commit schema version last... never half-upgrade in place" guarantee below."""
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def current_version(conn: sqlite3.Connection) -> int:
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchall()
    if not tables:
        return 0
    row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else 0


def migrate(conn: sqlite3.Connection, target_version: int | None = None) -> int:
    """Apply pending migrations in order. §11: 'Commit schema version last. On failure, restore
    automatically or leave both old data and an actionable recovery record; never half-upgrade
    in place.' Each migration runs in its own transaction with the version bump as the final
    statement, so a crash mid-migration leaves the previous fully-valid version, not a partial
    schema."""
    target = target_version if target_version is not None else MIGRATIONS[-1][0]
    have = current_version(conn)
    if have > target:
        raise SchemaError(
            f"refusing to downgrade from schema v{have} to v{target}: no safe reverse migration"
        )
    for version, _description, sql in MIGRATIONS:
        if version <= have or version > target:
            continue
        with transaction(conn):
            for statement in _split_statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),),
            )
    return current_version(conn)


def check_compatible(conn: sqlite3.Connection) -> tuple[bool, str]:
    have = current_version(conn)
    if have == 0:
        return False, "database is uninitialized (run setup)"
    if have > CURRENT_SCHEMA_VERSION:
        return False, (
            f"database schema v{have} is newer than this runtime supports (v{CURRENT_SCHEMA_VERSION}); "
            "upgrade the runtime, do not downgrade the database"
        )
    return True, "compatible"
