#!/usr/bin/env bash
# Import an installed LaunchAgent into the registry as a managed `command` job.
#
# Usage:
#   adopt-job.sh --label <launchd-label> [--id <id>] [--relabel --confirm] [--dry-run]
#
# Without --relabel the agent is registered in config only (the original label
# keeps running). With --relabel --confirm the original is booted out and a fresh
# <label_root>.command.<id> agent is installed in its place.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

label=""; id=""; relabel=0; confirm=0; dry=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label) shift; label="${1:-}" ;;
    --id) shift; id="${1:-}" ;;
    --relabel) relabel=1 ;;
    --confirm) confirm=1 ;;
    --dry-run) dry=1 ;;
    *) die "unknown adopt option: $1" ;;
  esac
  shift
done
[[ -n "$label" ]] || die "adopt-job requires --label <launchd-label>"

bridge_label="$(local_jobs_label --token canvas-bridge --cardinality singleton)"
if [[ "$label" == "$bridge_label" ]]; then
  if (( dry == 1 )); then
    printf 'would adopt %s via enable-canvas-runs (canvas Run now bridge)\n' "$label"
    exit 0
  fi
  "$SCRIPT_DIR/local-jobs.sh" enable-canvas-runs
  mkdir -p "$LOCAL_JOBS_STATE/canvas-bridge"
  ADOPTED="$LOCAL_JOBS_STATE/canvas-bridge/adopted.yml" LABEL="$label" \
    "$LOCAL_JOBS_PYTHON" - <<'PY'
import datetime, os, yaml
from pathlib import Path
path = Path(os.environ["ADOPTED"])
path.write_text(yaml.safe_dump({
    "label": os.environ["LABEL"],
    "adopted_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
}, sort_keys=False))
PY
  log "adopted canvas-bridge sidecar via enable-canvas-runs; $label is now managed"
  exit 0
fi

plist="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/launchd.py" plist-path --label "$label")"
[[ -f "$plist" ]] || die "no plist for label: $plist"

# Extract program/args/env/schedule from the plist.
parsed="$(PLIST="$plist" "$LOCAL_JOBS_PYTHON" - <<'PY'
import json, os, plistlib
with open(os.environ["PLIST"], "rb") as f:
    d = plistlib.load(f)
prog = d.get("ProgramArguments") or []
cal = d.get("StartCalendarInterval") or {}
interval = d.get("StartInterval")
schedule = None
if interval is not None:
    schedule = json.dumps({"kind": "interval", "seconds": int(interval)})
elif isinstance(cal, dict) and ("Hour" in cal or "Minute" in cal):
    schedule = "%02d:%02d" % (int(cal.get("Hour", 0)), int(cal.get("Minute", 0)))
print(json.dumps({
    "program": prog[0] if prog else "",
    "args": prog[1:] if len(prog) > 1 else [],
    "env": {k: str(v) for k, v in (d.get("EnvironmentVariables") or {}).items() if k != "PATH"},
    "schedule": schedule or "00:00",
}))
PY
)"

program="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["program"])' "$parsed")"
[[ -n "$program" ]] || die "plist has no ProgramArguments to adopt: $label"
[[ -n "$id" ]] || id="${label##*.}"
# Global-uniqueness invariant (same as add-job): ids are a cross-type namespace.
resolved_rc=0
resolved_out="$(registry_py instance-type --id "$id" 2>&1)" || resolved_rc=$?
if [[ $resolved_rc -eq 0 ]]; then
  die "id '$id' already exists under type '$resolved_out'; pick a new --id or delete the existing instance"
elif [[ "$resolved_out" == *"ambiguous id"* ]]; then
  die "id '$id' already exists ($resolved_out)"
fi
schedule="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["schedule"])' "$parsed")"

# Build the command-store entry through the chassis (contract + store), so the
# `command` handler's declared schema and the generic store stay the single
# source of truth (no bespoke command_store.py).
COMMAND_CONFIG="${LOCAL_JOBS_COMMAND_CONFIG:-$LOCAL_JOBS_STATE/jobs/command.yml}"
build_args=(--id "$id" --program "$program" --schedule "$schedule" --enabled true)
while IFS= read -r a; do [[ -n "$a" ]] && build_args+=("--arg=$a"); done < <("$LOCAL_JOBS_PYTHON" -c 'import json,sys; [print(x) for x in json.loads(sys.argv[1])["args"]]' "$parsed")
while IFS= read -r kv; do [[ -n "$kv" ]] && build_args+=("--env=$kv"); done < <("$LOCAL_JOBS_PYTHON" -c 'import json,sys; [print(f"{k}={v}") for k,v in json.loads(sys.argv[1])["env"].items()]' "$parsed")

schema="$(registry_py add-schema --type command)"
entry="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/contract.py" build-entry --schema "$schema" -- "${build_args[@]}")" \
  || die "could not build command entry from $label"

store_add() {
  "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/store.py" --file "$COMMAND_CONFIG" --schema-version 1 \
    --defaults '{"args":[],"env":{},"enabled":true}' --required '["program","schedule"]' \
    add --entry "$entry" "$@"
}

if (( dry == 1 )); then
  printf 'would adopt %s as command id=%s schedule=%s program=%s\n' "$label" "$id" "$schedule" "$program"
  store_add --dry-run
  exit 0
fi

store_add >/dev/null
log "adopted $label into command store as id=$id"

if (( relabel == 1 )); then
  (( confirm == 1 )) || die "--relabel requires --confirm (boots out the original agent)"
  new_label="$(local_jobs_label --token command --id "$id")"
  "$(require_handler command)" repair --id "$id"
  if [[ "$label" != "$new_label" ]]; then
    old_plist="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/launchd.py" plist-path --label "$label")"
    launchctl bootout "gui/$(id -u)/${label}" >/dev/null 2>&1 || true
    rm -f "$old_plist"
    log "relabeled $label -> $new_label (original booted out + removed)"
  fi
else
  log "registered in config only; original agent $label still runs. Use --relabel --confirm to migrate it."
fi
