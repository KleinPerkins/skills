"""SQLite/WAL connection management — build plan v3 §4: "encrypted local SQLite/WAL for every
operator." WAL mode is enabled on every connection; ``foreign_keys`` and a busy timeout are set
so concurrent CLI+MCP access from the same install fails safely rather than corrupting state.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """§11: 'Commit schema version last... never half-upgrade in place.' A plain BEGIN
    IMMEDIATE/COMMIT/ROLLBACK wrapper; the application layer's staging-transaction pattern
    (``application/transactions.py``) builds multi-step durability on top of this primitive."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
