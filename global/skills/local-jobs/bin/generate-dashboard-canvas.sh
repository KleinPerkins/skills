#!/usr/bin/env bash
# Produce the local-jobs dashboard canvas from the shared template.
#
# Two artifacts, one template:
#   local-jobs-dashboard.canvas.tsx            tracked SEED (data-free; empty state)
#   local-jobs-dashboard.generated.canvas.tsx  git-ignored LIVE render (this machine)
#
# Usage:
#   bin/generate-dashboard-canvas.sh            # (re)write the tracked data-free seed
#   bin/generate-dashboard-canvas.sh --live     # write the live canvas from dashboard --json
#   bin/generate-dashboard-canvas.sh --live --open   # + print an "open this" hint
#   bin/generate-dashboard-canvas.sh --check    # assert the tracked seed is data-free + current
#   bin/generate-dashboard-canvas.sh --json     # emit dashboard/v1 JSON to stdout
#
# The `view` verb calls `--live`. The seed is what CI checks and what downstream
# vendoring copies, so it must never carry machine-specific data.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

CANVAS_DIR="$LOCAL_JOBS_HOME/canvases"
TEMPLATE="$CANVAS_DIR/local-jobs-dashboard.template.tsx"
SEED="$CANVAS_DIR/local-jobs-dashboard.canvas.tsx"
LIVE="$CANVAS_DIR/local-jobs-dashboard.generated.canvas.tsx"
PY_HELPER="$LOCAL_JOBS_HOME/lib/canvas_emit.py"

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
}

dashboard_json() {
  "$SCRIPT_DIR/local-jobs.sh" dashboard --json
}

mode="${1:-seed}"
case "$mode" in
  --json)
    dashboard_json
    ;;
  --check)
    [[ -f "$SEED" ]] || die "missing tracked seed: $SEED (run generate-dashboard-canvas.sh)"
    "$LOCAL_JOBS_PYTHON" "$PY_HELPER" check-seed "$TEMPLATE" "$SEED"
    log "canvas seed is data-free and current"
    ;;
  --live)
    [[ "${2:-}" == "--open" || -z "${2:-}" ]] || die "unknown flag: $2"
    dashboard_json | "$LOCAL_JOBS_PYTHON" "$PY_HELPER" write "$TEMPLATE" "$LIVE" >/dev/null
    log "wrote $(basename "$LIVE") ($(wc -c < "$LIVE" | tr -d ' ') bytes)"
    open_path="$LIVE"
    if ws_dir="$(cursor_workspace_canvas_dir 2>/dev/null || true)" && [[ -n "$ws_dir" ]]; then
      published="$ws_dir/local-jobs-dashboard.canvas.tsx"
      cp "$LIVE" "$published"
      log "published Cursor canvas UX copy → $(basename "$published")"
      open_path="$published"
    fi
    printf '%s\n' "$open_path"
    if [[ "${2:-}" == "--open" ]]; then
      if [[ "$open_path" == "$LIVE" ]]; then
        log "open from a Cursor workspace (cd into the repo first) or set LOCAL_JOBS_CURSOR_WORKSPACE"
      fi
      log "open this path as a Cursor canvas (Cmd+P → Open Canvas), not as a code tab"
    fi
    ;;
  -h|--help)
    usage
    ;;
  seed|"")
    "$LOCAL_JOBS_PYTHON" "$PY_HELPER" seed "$TEMPLATE" "$SEED" >/dev/null
    log "wrote data-free seed $(basename "$SEED") ($(wc -c < "$SEED" | tr -d ' ') bytes)"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
