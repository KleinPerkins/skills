#!/usr/bin/env python3
"""Embed a dashboard/v1 payload into the local-jobs dashboard canvas.

Two products come out of one template:

* the **seed** — ``local-jobs-dashboard.canvas.tsx``, tracked in git, embeds a
  canonical *empty* payload so the committed canvas carries no machine-specific
  data and renders the "no local job data" state on a fresh checkout;
* the **live** canvas — ``local-jobs-dashboard.generated.canvas.tsx``, git-ignored,
  written by the ``view`` verb from the current machine's ``dashboard --json``.

``check-seed`` is the CI/maintainer gate: it asserts the tracked seed is byte-for-
byte ``template ⊕ EMPTY_DASHBOARD`` — so nobody committed live data and the seed
tracks template edits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MARKER = "__DASHBOARD_JSON__"

# The committed seed: a valid dashboard/v1 with no jobs and no history, so the
# tracked canvas is byte-stable across machines and renders the empty state.
EMPTY_DASHBOARD: dict[str, Any] = {
    "schema": "dashboard/v1",
    "generated_at": "1970-01-01T00:00:00+00:00",
    "run_bridge_enabled": False,
    # Mirrors the live summary shape emitted by lib/dashboard.py — the engineering
    # facets plus the PM-facing reconciled buckets (all zero on a fresh machine).
    "summary": {
        "total": 0,
        "failing": 0,
        "drifted": 0,
        "quarantined": 0,
        "disabled": 0,
        "on_demand": 0,
        "running": 0,
        "unmanaged": 0,
        "buckets": {"healthy": 0, "needs_attention": 0, "paused": 0, "on_demand": 0},
    },
    "instances": [],
    "discovered_unmanaged": [],
    "recent_events": [],
    "recent_runs": [],
    "type_catalog": [],
    "health_verdict": "No local jobs configured on this machine.",
    "next_actions": [],
}


def _load_dashboard(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"dashboard --json returned invalid JSON: {exc}") from exc
    if payload.get("schema") != "dashboard/v1":
        raise SystemExit(f"unexpected dashboard schema: {payload.get('schema')!r}")
    return payload


def _render(template_path: Path, payload: dict[str, Any]) -> str:
    template = template_path.read_text()
    if MARKER not in template:
        raise SystemExit(f"template missing {MARKER!r}: {template_path}")
    return template.replace(MARKER, json.dumps(payload, indent=2, ensure_ascii=True), 1)


def cmd_write(template_path: Path, output_path: Path) -> int:
    """Embed live ``dashboard --json`` (stdin) into the generated canvas."""
    output_path.write_text(_render(template_path, _load_dashboard(sys.stdin.read())))
    print(output_path)
    return 0


def cmd_seed(template_path: Path, output_path: Path) -> int:
    """Embed the canonical empty payload into the tracked seed canvas."""
    output_path.write_text(_render(template_path, EMPTY_DASHBOARD))
    print(output_path)
    return 0


def cmd_check_seed(template_path: Path, output_path: Path) -> int:
    """Assert the tracked seed is exactly ``template ⊕ EMPTY_DASHBOARD``."""
    expected = _render(template_path, EMPTY_DASHBOARD)
    if output_path.read_text() != expected:
        raise SystemExit(
            "canvas seed is stale or carries data — regenerate the data-free seed "
            "with bin/generate-dashboard-canvas.sh"
        )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: canvas_emit.py write <template> <output> "
            "| seed <template> <output> | check-seed <template> <output>"
        )
    cmd = sys.argv[1]
    if cmd in ("write", "seed", "check-seed"):
        if len(sys.argv) != 4:
            raise SystemExit(f"usage: canvas_emit.py {cmd} <template> <output>")
        handler = {"write": cmd_write, "seed": cmd_seed, "check-seed": cmd_check_seed}[cmd]
        return handler(Path(sys.argv[2]), Path(sys.argv[3]))
    raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
