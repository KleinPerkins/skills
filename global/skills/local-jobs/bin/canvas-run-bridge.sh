#!/usr/bin/env bash
# Silent Cursor Canvas bridge for Run now and Full explain-job.
#
# The dashboard canvas persists requests to its sidecar. This launchd watcher
# validates each request once, then either runs a job or inspects it on disk,
# writes a cached deep explain, and regenerates the live dashboard canvas.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

bridge_dir="$LOCAL_JOBS_STATE/canvas-bridge"
mkdir -p "$bridge_dir"

exec 9>"$bridge_dir/bridge.lock"
if ! "$LOCAL_JOBS_PYTHON" - 9 <<'PY'
import fcntl
import sys

try:
    fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(1)
PY
then
  exit 0
fi

request_json="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/canvas_bridge.py" "$LOCAL_JOBS_HOME" "$bridge_dir" 2>/dev/null || true)"
[[ -n "$request_json" ]] || exit 0

# The request is now durably ledgered (canvas_bridge.py wrote its nonce under the
# lock), so the next tick will not re-pick it. Release bridge.lock before the
# (possibly slow, flock-blocked) dispatch below so a single in-flight run never
# stalls other queued canvas requests until they age out of the freshness window.
exec 9>&-

# Attribute every bridge-triggered run/mutation to the bridge (not the default
# "cli") in the event stream, so an operator can distinguish a canvas action from
# a direct CLI verb.
export LOCAL_JOBS_ACTOR="canvas-bridge"

# Regenerate the refreshed canvas back into the SAME Cursor workspace that made
# the request. This bridge runs from the skill's own git worktree, so a plain
# `view` would infer its publish target from that repo (git rev-parse) and drop
# the fresh canvas in the wrong Cursor project — leaving the operator's open
# canvas stale (that mis-target is exactly what makes Refresh look like a no-op).
# The request's sidecar is the .canvas.data.json the canvas persisted its request
# to; its parent is the operator's workspace canvases/ dir. Never redirect to the
# skill's own canvases/ (that holds the tracked seed + live render, not a copy).
request_sidecar="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1]).get("sidecar") or "")' "$request_json")"
if [[ -n "$request_sidecar" ]]; then
  request_canvas_dir="$(dirname -- "$request_sidecar")"
  if [[ -d "$request_canvas_dir" && "$request_canvas_dir" != "$LOCAL_JOBS_HOME/canvases" ]]; then
    export LOCAL_JOBS_CURSOR_CANVAS_DIR="$request_canvas_dir"
  fi
fi

kind="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["kind"])' "$request_json")"

if [[ "$kind" == "view" ]]; then
  view_rc=0
  "$SCRIPT_DIR/local-jobs.sh" view >/dev/null || view_rc=$?
  exit "$view_rc"
fi

job_id="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["job_id"])' "$request_json")"

if [[ "$kind" == "explain" ]]; then
  inspect_rc=0
  "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/explain_inspect.py" write --id "$job_id" >/dev/null || inspect_rc=$?
  hook="$LOCAL_JOBS_STATE/hooks/explain-agent.sh"
  if [[ -x "$hook" ]]; then
    "$hook" --id "$job_id" >/dev/null 2>&1 || true
  fi
  view_rc=0
  "$SCRIPT_DIR/local-jobs.sh" view >/dev/null || view_rc=$?
  if (( inspect_rc != 0 )); then
    exit "$inspect_rc"
  fi
  exit "$view_rc"
fi

if [[ "$kind" == "control" ]]; then
  # Pause/Resume: an operational toggle symmetric with Run now. The canvas never
  # writes config; it queues a request and the trusted enable/disable-job verb
  # (the single safe config-writer) performs the change, then we regenerate.
  action="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1]).get("action",""))' "$request_json")"
  case "$action" in
    pause) verb="disable-job" ;;
    resume) verb="enable-job" ;;
    *) exit 0 ;;
  esac
  control_rc=0
  "$SCRIPT_DIR/local-jobs.sh" "$verb" --id "$job_id" >/dev/null || control_rc=$?
  view_rc=0
  "$SCRIPT_DIR/local-jobs.sh" view >/dev/null || view_rc=$?
  if (( control_rc != 0 )); then
    exit "$control_rc"
  fi
  exit "$view_rc"
fi

run_rc=0
"$SCRIPT_DIR/local-jobs.sh" run-job --id "$job_id" || run_rc=$?

view_rc=0
"$SCRIPT_DIR/local-jobs.sh" view >/dev/null || view_rc=$?

if (( run_rc != 0 )); then
  exit "$run_rc"
fi
exit "$view_rc"
