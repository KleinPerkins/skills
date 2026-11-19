#!/usr/bin/env python3
"""Turn a handler's structured `@@RUNLOG@@` fields into a human headline.

Centralized so every job type produces a uniform run-log `summary` string; the
dashboard and `logs-job` read this rather than re-tailing raw logs.

Usage: summarize.py <type> <status>   # fields JSON on stdin
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _igf(status: str, fields: dict[str, Any]) -> str:
    repos = fields.get("repos") or []
    counts = fields.get("counts") or {}
    reason = fields.get("reason")
    total = counts.get("total") or len(repos)
    failed = counts.get("failed")
    if failed is None:
        failed = sum(1 for r in repos if r.get("status") == "failure")

    if status == "dry-run":
        return f"dry-run ({len(repos)} repo(s))"
    if status == "completed_with_failures":
        return f"Completed with issues · {failed} of {total} failed"
    if not repos:
        return "no repos run"
    if status == "failure" and total > 1:
        return f"FAILED · {failed} of {total} repos failed"
    if len(repos) == 1:
        r = repos[0]
        hb, ha = r.get("head_before"), r.get("head_after")
        bb = r.get("behind_before")
        if status == "failure":
            detail = reason or r.get("reason")
            return f"FAILED: {r.get('id')} — {detail}" if detail else f"FAILED: {r.get('id')}"
        if hb and ha and hb != ha:
            return f"{r.get('id')}: ff-merged {hb}→{ha}" + (f" ({bb} behind)" if bb else "")
        return f"{r.get('id')}: up-to-date"
    merged = sum(1 for r in repos if r.get("head_before") and r.get("head_after") and r["head_before"] != r["head_after"])
    uptodate = len(repos) - merged
    return f"{len(repos)} repos: {merged} ff-merged, {uptodate} up-to-date"


def _command(status: str, fields: dict[str, Any]) -> str:
    code = fields.get("exit_code")
    last = fields.get("last_line") or ""
    if status == "dry-run":
        return "dry-run"
    if status == "failure":
        return f"exit {code}: {last}" if last else f"exit {code}"
    return last or "exit 0"


def summarize(job_type: str, status: str, fields: dict[str, Any]) -> str:
    if job_type == "incremental-git-fetch":
        return _igf(status, fields)
    if job_type == "command":
        return _command(status, fields)
    return f"{status}"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: summarize.py <type> <status>  (fields JSON on stdin)", file=sys.stderr)
        return 2
    job_type, status = sys.argv[1], sys.argv[2]
    try:
        fields = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        fields = {}
    print(summarize(job_type, status, fields if isinstance(fields, dict) else {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
