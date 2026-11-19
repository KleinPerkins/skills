#!/usr/bin/env python3
"""Run-progress markers for local-jobs — the crash-safe source of the ``running`` status.

``dispatch-run.sh`` writes a marker just before it runs a handler and removes it
when the run ends (via a shell ``trap``). The dashboard treats a job as running
only when its marker's PID is still alive AND the marker is recent, so a crashed
run (marker left behind but the process gone) never sticks as a phantom
"running". No daemon, no TTL heartbeat — the live PID is the source of truth and
the age bound only guards against PID reuse if a marker is ever orphaned.

Marker file: ``<state>/running/<type>__<job_id>.json`` = ``{pid, ts, type, job_id}``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import events  # single source of truth for state_dir() + now_iso()

# Backstop against PID reuse: a marker whose process is alive but that is older
# than this is treated as orphaned (a real run should never outlive it).
MAX_AGE_SECONDS = 12 * 3600


def _pid_start(pid: int) -> str | None:
    """Opaque process start-time token for ``pid``, for PID-reuse detection.

    Portable across macOS + Linux via ``ps -o lstart=``. Returns None when the
    pid is dead or the token is unknowable — callers treat None as "cannot
    prove identity" and fall back to the liveness + age backstop.
    """
    if pid <= 0:
        return None
    try:
        proc = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    token = proc.stdout.strip()
    return token or None


def marker_dir() -> Path:
    return events.state_dir() / "running"


def _slug(value: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in (value or "_"))


def marker_path(job_type: str, job_id: str) -> Path:
    return marker_dir() / f"{_slug(job_type)}__{_slug(job_id)}.json"


def _alive(pid: int) -> bool:
    """True when ``pid`` names a live process (portable across macOS + Linux)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user — still alive
    except OSError:
        return False
    return True


def start(job_type: str, job_id: str, pid: int) -> int:
    directory = marker_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = marker_path(job_type, job_id)
    tmp = path.with_name(path.name + ".tmp")
    marker = {"pid": pid, "ts": events.now_iso(), "type": job_type, "job_id": job_id}
    start_token = _pid_start(pid)
    if start_token is not None:
        marker["pid_start"] = start_token
    tmp.write_text(json.dumps(marker))
    tmp.replace(path)  # atomic vs. lock-free readers
    return 0


def stop(job_type: str, job_id: str, pid: int | None = None) -> int:
    path = marker_path(job_type, job_id)
    if pid is not None:
        try:
            data = json.loads(path.read_text())
            marker_pid = int(data.get("pid") or 0)
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return 0
        if marker_pid != pid:
            return 0
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return 1
    return 0


def _age_seconds(ts: str, now: datetime) -> float | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()


def active_map(now: datetime | None = None) -> dict[tuple[str, str], str]:
    """Map each live ``(type, job_id)`` to its marker start ts (ISO 8601).

    Same liveness + age filters as :func:`active`, but it also surfaces the run
    start time so the dashboard can flag a run that has been going far longer
    than its historical typical duration ("running long" — observability only,
    never an auto-kill/timeout).
    """
    now = now or datetime.now(timezone.utc)
    directory = marker_dir()
    out: dict[tuple[str, str], str] = {}
    if not directory.is_dir():
        return out
    for marker in directory.glob("*.json"):
        try:
            data = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            continue
        if not _alive(pid):
            continue
        # PID-reuse guard: if the marker recorded the process start time, the live
        # pid must still have that same start time, else it is a recycled pid for
        # an unrelated process (not our run). Legacy markers without the token
        # fall back to the age backstop below.
        recorded_start = data.get("pid_start")
        if recorded_start is not None and _pid_start(pid) != recorded_start:
            continue
        ts = data.get("ts") or ""
        age = _age_seconds(ts, now)
        if age is not None and age > MAX_AGE_SECONDS:
            continue
        job_type, job_id = data.get("type"), data.get("job_id")
        if job_type is not None and job_id is not None:
            out[(job_type, job_id)] = ts
    return out


def active(now: datetime | None = None) -> set[tuple[str, str]]:
    """Set of ``(type, job_id)`` currently running (live PID, recent marker)."""
    return set(active_map(now).keys())


def main() -> int:
    ap = argparse.ArgumentParser(prog="running.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "stop"):
        p = sub.add_parser(name)
        p.add_argument("--type", required=True)
        p.add_argument("--id", required=True)
        if name == "start":
            p.add_argument("--pid", type=int, required=True)
        else:
            p.add_argument("--pid", type=int, default=None)
    a = sub.add_parser("active")
    a.add_argument("--now", default=None)
    args = ap.parse_args()
    if args.cmd == "start":
        return start(args.type, args.id, args.pid)
    if args.cmd == "stop":
        return stop(args.type, args.id, args.pid)
    if args.cmd == "active":
        now = datetime.fromisoformat(args.now) if args.now else None
        print(json.dumps(sorted(list(active(now)))))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
