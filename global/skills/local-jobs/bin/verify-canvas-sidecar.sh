#!/usr/bin/env bash
# Local-only probe for Cursor Canvas sidecar flush behavior.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

timeout_s=60
while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout) shift; timeout_s="${1:-60}" ;;
    -h|--help)
      printf 'usage: verify-canvas-sidecar.sh [--timeout seconds]\n'
      exit 0
      ;;
    *) die "unknown verify-canvas-sidecar option: $1" ;;
  esac
  shift
done

"$LOCAL_JOBS_PYTHON" - "$LOCAL_JOBS_HOME" "$timeout_s" <<'PY'
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

home = Path(sys.argv[1])
timeout_s = float(sys.argv[2])
deadline = time.time() + timeout_s
canvas_dir = home / "canvases"


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


def read_request() -> tuple[Path, object] | None:
    files = sorted(
        canvas_dir.glob("local-jobs-dashboard*.canvas.data.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for path in files:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        req = state_value(data, "dash.runRequest")
        if req:
            return path, req
    return None


while time.time() <= deadline:
    found = read_request()
    if found:
        path, req = found
        print(json.dumps({"sidecar": str(path), "dash.runRequest": req}, indent=2, sort_keys=True))
        raise SystemExit(0)
    time.sleep(0.5)

print(
    f"no dash.runRequest observed within {timeout_s:g}s; keep canvas runs disabled and use scripts/local-jobs.sh run-job --id <id>",
    file=sys.stderr,
)
raise SystemExit(1)
PY
