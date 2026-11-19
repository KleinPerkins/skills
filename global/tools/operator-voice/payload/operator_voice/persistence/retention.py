"""Retention sweeps — build plan v3 §5.1: "Raw/verbatim, held-out, validation-draft, and model
payload retention defaults to zero days." A "zero day" default means: once a document's content
has been through feature extraction, its ciphertext content column is cleared in the SAME
transaction as the extraction commit — the row (and its digest/locator/metadata) survives for
provenance, but the raw text does not.
"""

from __future__ import annotations

import sqlite3

from operator_voice.domain.models import now_ts

DEFAULT_RETENTION_DAYS = 0


def clear_document_content(conn: sqlite3.Connection, document_id: str) -> None:
    """Zero-day sweep: null out the encrypted content column once it is no longer needed.
    Idempotent — clearing an already-cleared document is a no-op."""
    conn.execute(
        "UPDATE documents SET content_enc = NULL, key_generation_id = NULL, content_cleared_at = ? "
        "WHERE document_id = ? AND content_enc IS NOT NULL",
        (now_ts(), document_id),
    )


def sweep_expired(conn: sqlite3.Connection) -> dict[str, int]:
    """Sweep any row whose ``expires_at`` has passed. Returns per-table deletion counts for the
    (content-free) audit event the caller records."""
    now = now_ts()
    counts: dict[str, int] = {}

    cur = conn.execute(
        "UPDATE documents SET content_enc = NULL, key_generation_id = NULL, content_cleared_at = ? "
        "WHERE expires_at IS NOT NULL AND expires_at <= ? AND content_enc IS NOT NULL",
        (now, now),
    )
    counts["documents_content_cleared"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM export_records WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
    counts["export_records_deleted"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM challenges WHERE expires_at <= ?", (now,))
    counts["expired_challenges_deleted"] = cur.rowcount or 0

    return counts
