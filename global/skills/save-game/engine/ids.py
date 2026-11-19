"""ID and timestamp generation shared by every persisted record.

IDs are collision-resistant (12 hex chars of `secrets.token_hex`) and always match
the closed schemas' `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$` identifier pattern because
they start with an alphabetic prefix. Timestamps always match the schemas'
`^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z$` pattern (millisecond precision, UTC).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def new_task_id() -> str:
    return new_id("task")


def new_operation_id() -> str:
    return new_id("op")


def new_checkpoint_id() -> str:
    return new_id("chk")


def new_receipt_id() -> str:
    return new_id("rcpt")


def new_candidate_id() -> str:
    return new_id("cand")


def new_tombstone_id() -> str:
    return new_id("tomb")
