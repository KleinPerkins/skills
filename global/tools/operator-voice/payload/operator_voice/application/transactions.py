"""Staging-transaction pattern — build plan v3 §8/§11: every operation handler runs inside
exactly one DB transaction (crash mid-operation never leaves a half-applied mutation, matching
the "commit ... last, never half-upgrade in place" guarantee already used for migrations) AND
always records exactly one content-free :class:`~operator_voice.domain.models.AuditEvent` for the
attempt, whether it succeeds, fails, or is cancelled at a checkpoint.

This is a thin composition of :func:`operator_voice.persistence.sqlite.transaction` (the DB
primitive) and :mod:`operator_voice.application.cancellation` (the off-flag check) — it holds no
persistence logic of its own.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from operator_voice.application.cancellation import OperationCancelled, is_off
from operator_voice.persistence import audit
from operator_voice.persistence.sqlite import transaction

TRANSACTIONS_VERSION = "transactions/v1"


class OperationRefused(RuntimeError):
    """Raised before the transaction opens (toolkit is off, or a precondition failed) — cheaper
    and clearer than opening a transaction just to cancel it immediately."""


@contextmanager
def staged_operation(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    operation_type: str,
    actor: str,
    consumer: Optional[str] = None,
    versions: Optional[dict[str, str]] = None,
    allow_while_off: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Usage::

        with staged_operation(conn, operation_id=..., operation_type="ingest", actor="operator") as c:
            ... mutate via persistence.store using ``c`` ...

    On a clean exit, commits and records ``result='success'``. On :class:`OperationCancelled`,
    rolls back and records ``result='cancelled'``. On any other exception, rolls back and records
    ``result='error'`` with no content (never the exception message, which could echo user text)
    beyond its class name.
    """
    if not allow_while_off and is_off(conn):
        raise OperationRefused(f"operation '{operation_type}' refused: toolkit is off")

    deletion_counts: dict[str, int] | None = None
    try:
        with transaction(conn):
            yield conn
        audit.record(
            conn, operation_id=operation_id, operation_type=operation_type, actor=actor,
            consumer=consumer, result="success", versions=versions, deletion_counts=deletion_counts,
        )
    except OperationCancelled:
        audit.record(
            conn, operation_id=operation_id, operation_type=operation_type, actor=actor,
            consumer=consumer, result="cancelled", versions=versions,
        )
        raise
    except Exception as exc:
        audit.record(
            conn, operation_id=operation_id, operation_type=operation_type, actor=actor,
            consumer=consumer, result=f"error:{type(exc).__name__}", versions=versions,
        )
        raise
