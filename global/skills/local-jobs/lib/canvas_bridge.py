#!/usr/bin/env python3
"""Pick and validate Cursor canvas sidecar requests for the launchd bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_REQUEST_AGE_SECONDS = int(os.environ.get("LOCAL_JOBS_CANVAS_REQUEST_MAX_AGE_SECONDS", "120"))
MAX_FUTURE_SKEW_SECONDS = 30
LEDGER_LIMIT = 200


def state_value(data: object, key: str) -> object | None:
    if not isinstance(data, dict):
        return None
    if key in data:
        return data.get(key)
    state = data.get("state")
    if isinstance(state, dict) and key in state:
        return state.get(key)
    cur: object = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur.get(part)
    return cur


def candidate_sidecars(home: Path) -> list[Path]:
    files: list[Path] = []
    canvas_dir = home / "canvases"
    if canvas_dir.is_dir():
        files.extend(canvas_dir.glob("local-jobs-dashboard*.canvas.data.json"))
    # Honor the same Cursor-projects override the publish side (common.sh) uses,
    # so discovery and republish stay consistent and the bridge is testable
    # without mutating $HOME (which would break user-site imports like PyYAML).
    projects_override = os.environ.get("LOCAL_JOBS_CURSOR_PROJECTS_DIR")
    projects = Path(projects_override) if projects_override else Path.home() / ".cursor" / "projects"
    if projects.is_dir():
        for ws_canvas in projects.glob("*/canvases"):
            if ws_canvas.is_dir():
                files.extend(ws_canvas.glob("local-jobs-dashboard*.canvas.data.json"))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return sorted(unique, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def key_for(request: object) -> tuple[str, str | None, str | None]:
    if not isinstance(request, dict):
        sig = hashlib.sha256(canonical(request).encode()).hexdigest()
        return f"signature:{sig}", None, None
    job_id = request.get("jobId")
    nonce = request.get("nonce")
    if isinstance(job_id, str) and job_id and isinstance(nonce, str) and nonce:
        return f"job-nonce:{job_id}\0{nonce}", job_id, nonce
    if isinstance(nonce, str) and nonce and "jobId" not in request:
        return f"view-nonce:{nonce}", None, nonce
    sig = hashlib.sha256(canonical(request).encode()).hexdigest()
    return f"signature:{sig}", job_id if isinstance(job_id, str) else None, nonce if isinstance(nonce, str) else None


def parse_ms(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value) / 1000.0
    if seconds <= 0:
        return None
    return seconds


def parse_iso(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Ledger:
    def __init__(self, bridge_dir: Path, schema: str, ledger_name: str, last_name: str) -> None:
        self.bridge_dir = bridge_dir
        self.schema = schema
        self.ledger_path = bridge_dir / ledger_name
        self.last_path = bridge_dir / last_name
        self.entries = self._load()

    def _load(self) -> list[dict[str, object]]:
        try:
            data = json.loads(self.ledger_path.read_text())
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            data = {}
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict)]
        return []

    def seen(self, request_key: str) -> bool:
        return any(e.get("key") == request_key for e in self.entries)

    def write(self, entry: dict[str, object]) -> None:
        self.entries.append(entry)
        self.entries = self.entries[-LEDGER_LIMIT:]
        payload = {"schema": self.schema, "limit": LEDGER_LIMIT, "entries": self.entries}
        tmp = self.ledger_path.with_name(f"{self.ledger_path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tmp.replace(self.ledger_path)
        last_tmp = self.last_path.with_name(f"{self.last_path.name}.{os.getpid()}.tmp")
        last_tmp.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n")
        last_tmp.replace(self.last_path)


def _validate_request_timing(request: dict[str, Any]) -> str | None:
    request_ts = parse_ms(request.get("at"))
    if request_ts is None:
        return "invalid-request-time"
    age = time.time() - request_ts
    if age > MAX_REQUEST_AGE_SECONDS:
        return "stale-request"
    if age < -MAX_FUTURE_SKEW_SECONDS:
        return "future-request"
    snapshot_ts = parse_iso(request.get("snapshotGeneratedAt"))
    if snapshot_ts is None:
        return "invalid-snapshot"
    if request_ts + 5 < snapshot_ts:
        return "request-before-snapshot"
    return None


def _validate_request(request: dict[str, Any]) -> tuple[str | None, str | None]:
    job_id = request.get("jobId")
    nonce = request.get("nonce")
    if not isinstance(job_id, str) or not job_id or not isinstance(nonce, str) or not nonce:
        return None, "invalid-request"
    err = _validate_request_timing(request)
    if err:
        return None, err
    return job_id, None


def _validate_view_request(request: dict[str, Any]) -> str | None:
    nonce = request.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return "invalid-request"
    return _validate_request_timing(request)


def pick_request(home: Path, bridge_dir: Path) -> dict[str, Any] | None:
    sys.path.insert(0, str(home / "lib"))
    import registry  # noqa: E402
    import running  # noqa: E402

    explain_ledger = Ledger(
        bridge_dir,
        "canvas-explain-bridge-ledger/v1",
        "seen-explain-requests.json",
        "last-explain-request.json",
    )
    run_ledger = Ledger(
        bridge_dir,
        "canvas-run-bridge-ledger/v1",
        "seen-requests.json",
        "last-request.json",
    )
    control_ledger = Ledger(
        bridge_dir,
        "canvas-control-bridge-ledger/v1",
        "seen-control-requests.json",
        "last-control-request.json",
    )
    view_ledger = Ledger(
        bridge_dir,
        "canvas-view-bridge-ledger/v1",
        "seen-view-requests.json",
        "last-view-request.json",
    )

    for state_key, kind, ledger in (
        ("dash.explainRequest", "explain", explain_ledger),
        ("dash.runRequest", "run", run_ledger),
        ("dash.controlRequest", "control", control_ledger),
        ("dash.viewRequest", "view", view_ledger),
    ):
        request = None
        sidecar = None
        for path in candidate_sidecars(home):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            raw = state_value(data, state_key)
            if isinstance(raw, dict):
                request = raw
                sidecar = path
                break
        if not request:
            continue

        request_key, request_job_id, request_nonce = key_for(request)
        if ledger.seen(request_key):
            continue

        def handled(status: str, reason: str, **extra: object) -> None:
            entry: dict[str, object] = {
                "key": request_key,
                "job_id": request_job_id,
                "nonce": request_nonce,
                "status": status,
                "reason": reason,
                "handled_at": now_iso(),
                "sidecar": str(sidecar) if sidecar else None,
                "kind": kind,
            }
            entry.update(extra)
            ledger.write(entry)

        if kind == "view":
            err = _validate_view_request(request)
            if err:
                status = "skipped" if err == "stale-request" else "rejected"
                handled(status, err)
                continue
            handled("accepted", "view")
            return {
                "kind": "view",
                "nonce": request_nonce,
                "sidecar": str(sidecar) if sidecar else None,
            }

        job_id, err = _validate_request(request)
        if err:
            status = "skipped" if err == "stale-request" else "rejected"
            handled(status, err)
            continue

        assert job_id is not None
        matches = [
            inst
            for inst in registry.collect_instances(registry.load_registry())
            if isinstance(inst, dict) and inst.get("role") != "error" and inst.get("id") == job_id
        ]
        if len(matches) != 1:
            handled("rejected", "unknown-or-ambiguous-job")
            continue

        inst = matches[0]
        if kind == "run":
            if job_id == "__global__" and inst.get("role") != "global_scheduler":
                handled("rejected", "invalid-global-row")
                continue
            if job_id != "__global__" and inst.get("role") != "instance":
                handled("rejected", "unsupported-row-role")
                continue
            effective_id = "all" if inst.get("role") == "global_scheduler" else job_id
            job_type = inst.get("type")
            if not isinstance(job_type, str) or not job_type:
                handled("rejected", "invalid-job-type")
                continue
            if (job_type, effective_id) in running.active():
                handled("skipped", "already-running", effective_id=effective_id, job_type=job_type)
                continue
            handled("accepted", "dispatch", effective_id=effective_id, job_type=job_type)
            return {
                "kind": "run",
                "job_id": job_id,
                "job_type": job_type,
                "nonce": request_nonce,
                "sidecar": str(sidecar) if sidecar else None,
            }

        if kind == "control":
            action = request.get("action")
            if action not in ("pause", "resume"):
                handled("rejected", "invalid-control-action")
                continue
            # Pause/Resume is a scheduled-instance operational toggle that runs
            # the validated enable/disable-job verb (the single safe config
            # writer). The global scheduler and on_demand jobs have no schedule
            # to pause; the verb rejects those, so we gate on role here too.
            if inst.get("role") != "instance":
                handled("rejected", "unsupported-row-role")
                continue
            handled("accepted", action, control_action=action)
            return {
                "kind": "control",
                "job_id": job_id,
                "action": action,
                "nonce": request_nonce,
                "sidecar": str(sidecar) if sidecar else None,
            }

        # explain — any managed row including global scheduler
        handled("accepted", "inspect")
        return {
            "kind": "explain",
            "job_id": job_id,
            "nonce": request_nonce,
            "sidecar": str(sidecar) if sidecar else None,
        }

    return None


def main() -> int:
    ap = argparse.ArgumentParser(prog="canvas_bridge.py")
    ap.add_argument("home")
    ap.add_argument("bridge_dir")
    args = ap.parse_args()
    picked = pick_request(Path(args.home), Path(args.bridge_dir))
    if picked:
        print(json.dumps(picked, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
