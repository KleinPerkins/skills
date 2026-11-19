"""Append-only, content-free metadata audit journal — build plan v3 §5 ``AuditEvent`` / §5.1:
"A separate append-only metadata audit journal contains opaque IDs, operation type,
actor/consumer, timestamp, versions, result, and deletion counts — never prose, feature values,
prompts, paths, or PII."

This module never accepts a free-text ``detail`` field precisely so a future call site cannot
accidentally leak content into the journal — the type signature itself is the enforcement.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from operator_voice.domain.models import AuditEvent, new_id, now_ts


def record(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    operation_type: str,
    actor: str,
    consumer: Optional[str],
    result: str,
    versions: dict[str, str] | None = None,
    deletion_counts: dict[str, int] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_id=new_id("audit"),
        operation_id=operation_id,
        operation_type=operation_type,
        actor=actor,
        consumer=consumer,
        result=result,
        versions=versions or {},
        deletion_counts=deletion_counts,
        created_at=now_ts(),
    )
    conn.execute(
        "INSERT INTO audit_events(event_id, operation_id, operation_type, actor, consumer, "
        "result, versions_json, deletion_counts_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            event.event_id,
            event.operation_id,
            event.operation_type,
            event.actor,
            event.consumer,
            event.result,
            json.dumps(event.versions),
            json.dumps(event.deletion_counts) if event.deletion_counts is not None else None,
            event.created_at,
        ),
    )
    return event


def read(conn: sqlite3.Connection, limit: int = 50) -> list[AuditEvent]:
    rows = conn.execute(
        "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        AuditEvent(
            event_id=r["event_id"],
            operation_id=r["operation_id"],
            operation_type=r["operation_type"],
            actor=r["actor"],
            consumer=r["consumer"],
            result=r["result"],
            versions=json.loads(r["versions_json"]),
            deletion_counts=json.loads(r["deletion_counts_json"]) if r["deletion_counts_json"] else None,
            created_at=r["created_at"],
        )
        for r in rows
    ]


def latest(conn: sqlite3.Connection, operation_type: str, *, result: str | None = None) -> AuditEvent | None:
    row = conn.execute(
        "SELECT * FROM audit_events WHERE operation_type=? AND (? IS NULL OR result=?) "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (operation_type, result, result)).fetchone()
    if row is None:
        return None
    return AuditEvent(event_id=row["event_id"], operation_id=row["operation_id"],
                      operation_type=row["operation_type"], actor=row["actor"], consumer=row["consumer"],
                      result=row["result"], versions=json.loads(row["versions_json"]),
                      deletion_counts=json.loads(row["deletion_counts_json"]) if row["deletion_counts_json"] else None,
                      created_at=row["created_at"])


def latest_success(conn: sqlite3.Connection, operation_type: str) -> AuditEvent | None:
    return latest(conn, operation_type, result="success")
