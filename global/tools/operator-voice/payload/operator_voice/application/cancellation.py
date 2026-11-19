"""Cooperative cancellation — build plan v3 §8 "off persists disabled mode ... cancels active
operations at checkpoints" and §10.10 quality gate. The persisted
:class:`~operator_voice.domain.models.CancellationState` "off" flag is checked before every unit
of work; a long-running operation (e.g. ``ingest`` over a large export) additionally checks it at
declared checkpoints between records so a mid-run ``off`` takes effect promptly without an
in-process kill signal.
"""

from __future__ import annotations

import sqlite3

from operator_voice.domain.models import CancellationState, now_ts
from operator_voice.persistence import store

CANCELLATION_VERSION = "cancellation/v1"


class OperationCancelled(RuntimeError):
    """Raised at a checkpoint when the toolkit is off. The staging-transaction wrapper catches
    this, rolls back the in-flight DB transaction, and records a content-free audit event with
    ``result='cancelled'`` — never a partial commit."""


def is_off(conn: sqlite3.Connection) -> bool:
    return store.get_cancellation_state(conn).off


def checkpoint(conn: sqlite3.Connection, checkpoint_name: str) -> None:
    """Call between units of work inside a long-running operation. Raises
    :class:`OperationCancelled` if the toolkit has been turned off since the operation started."""
    state = store.get_cancellation_state(conn)
    if state.off:
        raise OperationCancelled(f"cancelled at checkpoint '{checkpoint_name}': {state.reason or 'operator disabled'}")


def set_off(conn: sqlite3.Connection, reason: str) -> CancellationState:
    state = CancellationState(off=True, reason=reason or "operator requested", set_at=now_ts(), checkpoints={})
    store.set_cancellation_state(conn, state)
    return state


def set_on(conn: sqlite3.Connection) -> CancellationState:
    """§8: 're-enable never restores previously erased data' — this only clears the off flag; it
    never touches facts/documents/observations."""
    state = CancellationState(off=False, reason=None, set_at=now_ts(), checkpoints={})
    store.set_cancellation_state(conn, state)
    return state
