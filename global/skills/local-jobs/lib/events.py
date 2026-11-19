#!/usr/bin/env python3
"""Uniform versioned event stream for local-jobs (event/v1).

One JSON envelope per line in ``~/.local-jobs/events.jsonl``::

    {"schema":"event/v1","ts":"...","kind":"run|lifecycle|status|drift",
     "job_id":"...","type":"...","actor":"cli|scheduler|agent","payload":{...}}

This is the audit/observability backbone: every mutating verb emits a
``lifecycle`` event, every execution a ``run`` event, ``doctor`` a ``status``
event, and detected drift a ``drift`` event. The sink is pluggable (jsonl now;
a broker/file-per-day later) behind :func:`sink_from_env` — no daemon.

The module also owns the durable, flock-serialized, rotation-safe jsonl writer
shared with :mod:`run_log`; records are written in full (no field is dropped).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EVENT_SCHEMA = "event/v1"
EVENT_KINDS = ("run", "lifecycle", "status", "drift")

MAX_BYTES = 5 * 1024 * 1024
MAX_AGE_DAYS = 90


def state_dir() -> Path:
    return Path(os.environ.get("LOCAL_JOBS_STATE", str(Path.home() / ".local-jobs"))).expanduser()


def events_path() -> Path:
    return state_dir() / "events.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lock_path(path: Path) -> Path:
    return path.parent / (path.name + ".lock")


def durable_append(path: Path, line: str, rotate: Callable[[Path], None] | None = None) -> int:
    """Append one line under an exclusive flock, optionally rotating first.

    The whole append happens while holding the lock, so concurrent writers can
    never interleave regardless of line length (the old ``PIPE_BUF`` cap is gone
    and no field is ever dropped). ``rotate`` runs inside the lock so it cannot
    race a writer; it is expected to be atomic vs. lock-free readers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    try:
        with open(lock, "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            try:
                if rotate is not None:
                    rotate(path)
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                try:
                    os.write(fd, (line + "\n").encode())
                finally:
                    os.close(fd)
            finally:
                fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        print(f"events: append failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _first_record_ts(path: Path) -> str | None:
    """Oldest timestamp, tolerant of leading malformed/crash-truncated lines."""
    try:
        with path.open(errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line).get("ts")
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return None


def rotate_by_size_age(path: Path, max_bytes: int = MAX_BYTES, max_age_days: int = MAX_AGE_DAYS) -> None:
    """Drop the oldest half when over size or age. Atomic vs. readers.

    Rotation writes a sibling temp file then ``os.replace``s it, so a reader
    that does not hold the lock only ever observes a complete file. A malformed
    first line never defeats age rotation (we scan for the first valid record).
    """
    try:
        if not path.is_file():
            return
        over_size = path.stat().st_size > max_bytes
        over_age = False
        if not over_size:
            ts = _first_record_ts(path)
            if not ts:
                return
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
                over_age = age > max_age_days
            except ValueError:
                return
        if not (over_size or over_age):
            return
        lines = path.read_text(errors="replace").splitlines()
        keep = lines[len(lines) // 2 :]
        tmp = path.parent / (path.name + ".rot")
        tmp.write_text("\n".join(keep) + ("\n" if keep else ""))
        tmp.replace(path)
    except OSError:
        pass


class JsonlSink:
    """Default sink: one event per line in a rotation-bounded jsonl file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, event: dict[str, Any]) -> int:
        return durable_append(
            self.path,
            json.dumps(event, separators=(",", ":")),
            rotate=rotate_by_size_age,
        )


def sink_from_env() -> JsonlSink:
    """Broker-ready seam. Today: a jsonl sink at ``events.jsonl``.

    A future broker/file-per-day sink can be selected here via
    ``LOCAL_JOBS_EVENT_SINK`` without touching any caller.
    """
    return JsonlSink(events_path())


def make_event(
    kind: str,
    job_id: str | None = None,
    job_type: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": EVENT_SCHEMA,
        "ts": ts or now_iso(),
        "kind": kind,
        "job_id": job_id,
        "type": job_type,
        "actor": actor or os.environ.get("LOCAL_JOBS_ACTOR", "cli"),
        "payload": payload or {},
    }


def emit(
    kind: str,
    job_id: str | None = None,
    job_type: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
    ts: str | None = None,
    sink: JsonlSink | None = None,
) -> int:
    event = make_event(kind, job_id, job_type, payload, actor, ts)
    return (sink or sink_from_env()).write(event)


def read_events() -> list[dict[str, Any]]:
    path = events_path()
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def recent(limit: int, kind: str | None = None, job_id: str | None = None) -> list[dict[str, Any]]:
    evs = read_events()
    if kind:
        evs = [e for e in evs if e.get("kind") == kind]
    if job_id:
        evs = [e for e in evs if e.get("job_id") == job_id]
    return evs[-limit:]


def main() -> int:
    ap = argparse.ArgumentParser(prog="events.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emit")
    e.add_argument("--kind", required=True, choices=EVENT_KINDS)
    e.add_argument("--id", dest="job_id", default=None)
    e.add_argument("--type", dest="job_type", default=None)
    e.add_argument("--actor", default=None)
    e.add_argument("--payload", default="{}", help="JSON object")
    r = sub.add_parser("recent")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--kind", default=None)
    r.add_argument("--id", dest="job_id", default=None)
    args = ap.parse_args()
    if args.cmd == "emit":
        try:
            payload = json.loads(args.payload or "{}")
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"events: bad --payload: {exc}", file=sys.stderr)
            return 2
        return emit(args.kind, args.job_id, args.job_type, payload, args.actor)
    if args.cmd == "recent":
        print(json.dumps(recent(args.limit, args.kind, args.job_id), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
