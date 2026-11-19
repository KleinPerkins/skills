#!/usr/bin/env python3
"""Persisted deep job explanations for the local-jobs dashboard canvas.

Written by the canvas explain bridge (``explain_inspect.write``) after inspecting
program paths, handler config, and log tails — not recycled dashboard stats.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "job-explain/v1"


def cache_dir() -> Path:
    return Path(os.environ.get("LOCAL_JOBS_STATE", str(Path.home() / ".local-jobs"))) / "explain"


def cache_path(job_id: str) -> Path:
    safe = job_id.replace("/", "_")
    return cache_dir() / f"{safe}.json"


def fingerprint(inst: dict[str, Any]) -> str:
    keys = (
        "id",
        "type",
        "enabled",
        "schedule",
        "program",
        "args",
        "env",
        "path",
        "branch",
        "remote",
        "role",
    )
    payload = {k: inst.get(k) for k in keys if k in inst}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_for_instance(inst: dict[str, Any]) -> dict[str, Any] | None:
    path = cache_path(str(inst.get("id") or ""))
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema") != SCHEMA:
        return None
    if data.get("fingerprint") != fingerprint(inst):
        return None
    return data


def write(job_id: str, body: dict[str, Any]) -> Path:
    cache_dir().mkdir(parents=True, exist_ok=True)
    path = cache_path(job_id)
    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        **body,
    }
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path
