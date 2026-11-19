#!/usr/bin/env python3
"""Run history for local-jobs — the thin ``kind:"run"`` slice of the event stream.

A run record is written as a ``run`` event via :mod:`events` (no field is ever
dropped, flock-serialized, rotation-safe). Readers get the flat ``runlog/v1``
projection the dashboard consumes, merged with any legacy ``~/.local-jobs/runs.jsonl``
history so older runs are never lost after the event-stream cutover.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import events


def state_dir() -> Path:
    return events.state_dir()


def runs_path() -> Path:
    return state_dir() / "runs.jsonl"


def append(record: dict[str, Any]) -> int:
    """Persist one run record (full fidelity) as a ``kind:"run"`` event."""
    record.setdefault("ts", events.now_iso())
    return events.emit(
        "run",
        job_id=record.get("job_id"),
        job_type=record.get("type"),
        payload={
            "status": record.get("status"),
            "duration_s": record.get("duration_s"),
            "rc": record.get("rc"),
            "summary": record.get("summary"),
            "fields": record.get("fields") or {},
        },
        ts=record.get("ts"),
    )


def _project_run_event(ev: dict[str, Any]) -> dict[str, Any]:
    payload = ev.get("payload") or {}
    return {
        "schema": "runlog/v1",
        "ts": ev.get("ts"),
        "job_id": ev.get("job_id"),
        "type": ev.get("type"),
        "status": payload.get("status"),
        "duration_s": payload.get("duration_s"),
        "rc": payload.get("rc"),
        "summary": payload.get("summary"),
        "fields": payload.get("fields") or {},
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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
                continue  # tolerate malformed (e.g. crash-truncated) lines
    return out


def _record_key(rec: dict[str, Any]) -> tuple[str, str, str]:
    return (str(rec.get("job_id") or ""), str(rec.get("ts") or ""), str(rec.get("type") or ""))


def read_records() -> list[dict[str, Any]]:
    """Flat run records, oldest→newest, merging legacy file + event stream.

    Dedupes on (job_id, ts, type) so a run present in both ``runs.jsonl`` (legacy
    mirror) and ``events.jsonl`` is counted once.
    """
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(rec: dict[str, Any]) -> None:
        key = _record_key(rec)
        if key in seen:
            return
        seen.add(key)
        records.append(rec)

    for r in _read_jsonl(runs_path()):
        if r.get("schema") == events.EVENT_SCHEMA:
            if r.get("kind") == "run":
                add(_project_run_event(r))
        else:
            add(r)
    for ev in events.read_events():
        if ev.get("kind") == "run":
            add(_project_run_event(ev))
    records.sort(key=lambda r: r.get("ts") or "")
    return records


def recent(limit: int, job_id: str | None = None) -> list[dict[str, Any]]:
    records = read_records()
    if job_id:
        records = [r for r in records if r.get("job_id") == job_id]
    return records[-limit:]


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("append")  # reads record JSON from stdin
    r = sub.add_parser("recent"); r.add_argument("--limit", type=int, default=20); r.add_argument("--id", default=None)
    args = ap.parse_args()
    if args.cmd == "append":
        data = json.loads(sys.stdin.read() or "{}")
        return append(data)
    if args.cmd == "recent":
        print(json.dumps(recent(args.limit, args.id), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
