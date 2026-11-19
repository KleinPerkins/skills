"""Private storage location layout (plan: "Private locations").

All roots live under `${XDG_STATE_HOME:-$HOME/.local/state}/save-game/v1` (durable
records) and `${XDG_CONFIG_HOME:-$HOME/.config}/save-game/v1` (private registration).
Every path segment derived from a hash or generated ID is validated against a safe
pattern before it is allowed to become a filesystem path component — this is the
"safe/contained key derivation" the plan requires, enforced once here so every
caller gets it for free.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HEX64 = re.compile(r"^[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class UnsafePathComponentError(ValueError):
    """Raised when a value that would become a path component fails safety validation."""


def _hex64(name: str, value: str) -> str:
    if not isinstance(value, str) or not HEX64.match(value):
        raise UnsafePathComponentError(f"{name}={value!r} is not a 64-hex-char key")
    return value


def _safe_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.match(value):
        raise UnsafePathComponentError(f"{name}={value!r} is not a safe identifier")
    return value


def _env_root(env_var: str, fallback: str) -> Path:
    raw = os.environ.get(env_var) or fallback
    return Path(raw).expanduser()


def state_root() -> Path:
    return _env_root("XDG_STATE_HOME", str(Path.home() / ".local" / "state")) / "save-game" / "v1"


def config_root() -> Path:
    return _env_root("XDG_CONFIG_HOME", str(Path.home() / ".config")) / "save-game" / "v1"


def _workstream_dir(kind: str, repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return (
        state_root()
        / kind
        / _hex64("repo_key", repo_key)
        / _hex64("clone_key", clone_key)
        / _hex64("workstream_key", workstream_key)
    )


def current_path(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    d = _workstream_dir("current", repo_key, clone_key, workstream_key)
    return d.parent / f"{_hex64('workstream_key', workstream_key)}.json"


def snapshots_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return _workstream_dir("snapshots", repo_key, clone_key, workstream_key)


def snapshot_path(repo_key: str, clone_key: str, workstream_key: str, sha256_hex: str) -> Path:
    return snapshots_dir(repo_key, clone_key, workstream_key) / f"{_hex64('sha256_hex', sha256_hex)}.json"


def checkpoints_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return _workstream_dir("checkpoints", repo_key, clone_key, workstream_key)


def checkpoint_path(repo_key: str, clone_key: str, workstream_key: str, checkpoint_id: str) -> Path:
    return checkpoints_dir(repo_key, clone_key, workstream_key) / f"{_safe_id('checkpoint_id', checkpoint_id)}.json"


def journal_workstream_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return _workstream_dir("journal", repo_key, clone_key, workstream_key)


def journal_operation_dir(repo_key: str, clone_key: str, workstream_key: str, operation_id: str) -> Path:
    return journal_workstream_dir(repo_key, clone_key, workstream_key) / _safe_id("operation_id", operation_id)


def journal_quarantine_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return journal_workstream_dir(repo_key, clone_key, workstream_key) / "quarantine"


def receipts_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return _workstream_dir("receipts", repo_key, clone_key, workstream_key)


def receipt_path(repo_key: str, clone_key: str, workstream_key: str, receipt_id: str) -> Path:
    return receipts_dir(repo_key, clone_key, workstream_key) / f"{_safe_id('receipt_id', receipt_id)}.json"


def archives_dir(repo_key: str, clone_key: str, workstream_key: str) -> Path:
    return _workstream_dir("archives", repo_key, clone_key, workstream_key)


def lock_path(workstream_key: str) -> Path:
    return state_root() / "locks" / f"{_hex64('workstream_key', workstream_key)}.lock"


def registration_path(repo_key: str, clone_key: str) -> Path:
    return (
        config_root()
        / "repos"
        / _hex64("repo_key", repo_key)
        / f"{_hex64('clone_key', clone_key)}.json"
    )
