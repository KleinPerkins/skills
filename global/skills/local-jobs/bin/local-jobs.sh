#!/usr/bin/env bash
# Unified, type-agnostic CLI for locally scheduled launchd jobs.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

usage() {
  cat <<USAGE
Usage: local-jobs.sh <command> [options]

Commands (aliases in parentheses):
  view                   Open the Cursor dashboard canvas (regenerated from live state)
  view-jobs              List managed instances + discovered launchd agents (--json)
                         Use --config-only for saved declarations without inspecting targets
  dashboard              Rich status payload (--json, --brief for plain-English summary)
  explain-job            Narrative troubleshooting for one job (--id <id> [--type])
  resolve-instance       Fuzzy job discovery (--query <text> [--json])
  list-types (types)     Job type catalog (--plain human, --json schemas)
  handler-path           Print the resolved handler path for a type (--type <job-type>)
  describe-types         Machine-readable type+schema superset as JSON (grounds agent-guided job creation)
  add-job (add)          Add/preview a job (--dry-run; command: --schedule HH:MM | --interval-seconds N)
  update-job (update)    Update schedule and/or enabled state (same typed schedule flags)
  delete-fetch-if-current Remove one fetch record matching its previewed revision
  delete-job (delete)    Remove a job instance (requires --confirm)
  run-job (run)          Run a job now (--id <id> | --all) [--dry-run]
  enable-canvas-runs     Opt in to the silent dashboard "Run now" bridge
  disable-canvas-runs    Uninstall the dashboard "Run now" bridge
  logs-job (logs)        Show log paths + tails (--id <id> [--tail N])
  repair-job (repair)    Idempotent repair for one or all managed jobs
  enable-job (enable)    Enable a job instance
  disable-job (disable)  Disable a job instance (keeps config)
  pause-job (pause)      Alias for disable-job
  resume-job (resume)    Alias for enable-job
  adopt-job (adopt)      Import an installed LaunchAgent as a managed command job
  add-job-type           Scaffold + register + verify a new ABI-conformant type
  update-job-type        Migrate a type's instances forward (verify + regression)
  doctor                 Run health checks (--plain for operator narrative)

Global options:
  --json                 JSON output (view-jobs, dashboard, resolve-instance, explain-job)
  --type <job-type>      Required for add-job; optional hint elsewhere

Run 'list-types --plain' or 'add-job --type <t>' flags via registry add_schema (see ABI.md).
USAGE
}

normalize_cmd() {
  case "${1:-}" in
    view) printf 'view' ;;
    view-jobs) printf 'view-jobs' ;;
    dashboard) printf 'dashboard' ;;
    explain-job|explain) printf 'explain-job' ;;
    resolve-instance|resolve-job|resolve) printf 'resolve-instance' ;;
    list-types|types|job-types) printf 'list-types' ;;
    handler-path) printf 'handler-path' ;;
    describe-types) printf 'describe-types' ;;
    add|add-job) printf 'add' ;;
    update|update-job) printf 'update' ;;
    delete|delete-job) printf 'delete' ;;
    run|run-job) printf 'run' ;;
    enable-canvas-runs|enable-canvas-run-bridge) printf 'enable-canvas-runs' ;;
    disable-canvas-runs|disable-canvas-run-bridge) printf 'disable-canvas-runs' ;;
    logs|logs-job) printf 'logs' ;;
    repair|repair-job) printf 'repair' ;;
    enable|enable-job|resume|resume-job) printf 'enable' ;;
    disable|disable-job|pause|pause-job) printf 'disable' ;;
    adopt|adopt-job) printf 'adopt' ;;
    add-job-type) printf 'add-job-type' ;;
    update-job-type) printf 'update-job-type' ;;
    doctor) printf 'doctor' ;;
    ""|-h|--help|help) printf 'help' ;;
    *) printf '%s' "$1" ;;
  esac
}

dispatch_handler() {
  local job_type="$1"; shift
  local handler
  handler="$(require_handler "$job_type")"
  "$handler" "$@"
}

cmd_view_jobs() {
  local json=0 config_only=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --json) json=1 ;;
      --config-only) config_only=1 ;;
      *) die "unknown view-jobs option: $1" ;;
    esac
    shift
  done
  if (( config_only )); then
    if (( json )); then
      "$LOCAL_JOBS_PYTHON" -B "$SCRIPT_DIR/../lib/configured.py" --json
    else
      "$LOCAL_JOBS_PYTHON" -B "$SCRIPT_DIR/../lib/configured.py"
    fi
    return
  fi
  if (( json == 1 )); then registry_py view --json; else registry_py view; fi
}

cmd_view() {
  # Operator `view` = the Cursor dashboard canvas. Always regenerate from live
  # state (never a stale snapshot), then print the file to open as a canvas.
  # Read-only: the canvas surfaces status; mutations stay in the other verbs.
  while [[ $# -gt 0 ]]; do
    case "$1" in
      *) die "unknown view option: $1 (for the plain text list use view-jobs; for JSON use dashboard --json)" ;;
    esac
  done
  "$SCRIPT_DIR/generate-dashboard-canvas.sh" --live --open
}

cmd_dashboard() {
  local json=0 brief=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --json) json=1 ;;
      --brief) brief=1 ;;
      *) die "unknown dashboard option: $1" ;;
    esac
    shift
  done
  if (( brief == 1 )); then registry_py dashboard --brief
  elif (( json == 1 )); then registry_py dashboard --json
  else registry_py dashboard; fi
}

cmd_explain_job() {
  local id="" job_type="" json=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --type) shift; job_type="${1:-}" ;;
      --json) json=1 ;;
      *) die "unknown explain-job option: $1" ;;
    esac
    shift
  done
  [[ -n "$id" ]] || die "explain-job requires --id"
  local args=(explain-job --id "$id")
  [[ -n "$job_type" ]] && args+=(--type "$job_type")
  (( json == 1 )) && args+=(--json)
  registry_py "${args[@]}"
}

cmd_resolve_instance() {
  local query="" json=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --query) shift; query="${1:-}" ;;
      --json) json=1 ;;
      *) die "unknown resolve-instance option: $1" ;;
    esac
    shift
  done
  [[ -n "$query" ]] || die "resolve-instance requires --query"
  local args=(resolve-instance --query "$query")
  (( json == 1 )) && args+=(--json)
  registry_py "${args[@]}"
}

cmd_list_types() {
  local plain=0 json=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --plain) plain=1 ;;
      --json) json=1 ;;
      *) die "unknown list-types option: $1" ;;
    esac
    shift
  done
  if (( json == 1 )); then registry_py list-types --json
  else registry_py list-types --plain; fi
}

cmd_handler_path() {
  local job_type=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type) shift; job_type="${1:-}" ;;
      *) die "unknown handler-path option: $1" ;;
    esac
    shift
  done
  [[ -n "$job_type" ]] || die "handler-path requires --type"
  registry_py handler-path --type "$job_type"
}

cmd_describe_types() {
  # Machine-readable superset (schema_version + update-field matrix); always JSON.
  while [[ $# -gt 0 ]]; do case "$1" in --json) ;; *) die "unknown describe-types option: $1" ;; esac; shift; done
  registry_py describe-types --json
}

cmd_add() {
  local job_type="" id="" dry=0 passthrough=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type) shift; job_type="${1:-}" ;;
      --id) shift; id="${1:-}"; passthrough+=(--id "$id") ;;
      --dry-run) dry=1; passthrough+=(--dry-run) ;;
      --*) # generic flag passthrough; consume an optional value
        local flag="$1"
        if [[ $# -ge 2 && "${2:-}" != --* ]]; then shift; passthrough+=("$flag" "$1"); else passthrough+=("$flag"); fi
        ;;
      *) die "unknown add token: $1" ;;
    esac
    shift
  done
  [[ -n "$job_type" ]] || die "add-job requires --type"
  if [[ -n "$id" ]]; then
    local resolved rc=0
    resolved="$(registry_py instance-type --id "$id" 2>&1)" || rc=$?
    if [[ $rc -eq 0 ]]; then
      die "id '$id' already exists under type '$resolved'; ids must be globally unique (use update-job to change it, or pick a new id)"
    elif [[ "$resolved" == *"ambiguous id"* ]]; then
      die "id '$id' already exists ($resolved)"
    fi
  fi
  local schema missing_json
  schema="$(registry_py add-schema --type "$job_type")"
  missing_json="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/contract.py" missing-required --schema "$schema" -- "${passthrough[@]}" 2>&1)" || {
    if [[ -n "$missing_json" && "$missing_json" == \[* ]]; then
      local msg
      msg="$("$LOCAL_JOBS_PYTHON" -c 'import json, sys
m = json.loads(sys.argv[1])
print("; ".join("{} ({})".format(x["flag"], x["help"]) for x in m))' "$missing_json")"
      die "add-job --type $job_type missing required flags: $msg"
    fi
    [[ -n "$missing_json" ]] && die "add-job --type $job_type missing required flags: $missing_json"
    die "add-job --type $job_type: invalid flags"
  }
  dispatch_handler "$job_type" add "${passthrough[@]}"
}

cmd_update() {
  local id="" job_type="" rest=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}"; rest+=(--id "$id") ;;
      --type) shift; job_type="${1:-}" ;;
      --*) local flag="$1"; if [[ $# -ge 2 && "${2:-}" != --* ]]; then shift; rest+=("$flag" "$1"); else rest+=("$flag"); fi ;;
      *) die "unknown update token: $1" ;;
    esac
    shift
  done
  [[ -n "$id" ]] || die "update-job requires --id"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  dispatch_handler "$job_type" update "${rest[@]}"
}

cmd_delete() {
  local id="" job_type="" rest=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}"; rest+=(--id "$id") ;;
      --type) shift; job_type="${1:-}" ;;
      --confirm) rest+=(--confirm) ;;
      --purge-launchd) rest+=(--purge-launchd) ;;
      *) die "unknown delete option: $1" ;;
    esac
    shift
  done
  [[ -n "$id" ]] || die "delete-job requires --id"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  dispatch_handler "$job_type" delete "${rest[@]}"
}

cmd_run() {
  local id="" all=0 dry=0 job_type=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --type) shift; job_type="${1:-}" ;;
      --all) all=1 ;;
      --dry-run) dry=1 ;;
      *) die "unknown run option: $1" ;;
    esac
    shift
  done
  if (( all == 1 )); then
    local t failed=0
    while IFS= read -r t; do
      [[ -n "$t" ]] || continue
      printf '\n== run: %s ==\n' "$t"
      local args=(--type "$t")
      (( dry == 1 )) && args+=(--dry-run)
      "$SCRIPT_DIR/dispatch-run.sh" "${args[@]}" || failed=1
    done < <(registry_py job-types)
    return "$failed"
  fi
  [[ -n "$id" ]] || die "run-job requires --id or --all"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  local args=(--type "$job_type")
  [[ "$id" != "__global__" && "$id" != "all" ]] && args+=(--id "$id")
  (( dry == 1 )) && args+=(--dry-run)
  "$SCRIPT_DIR/dispatch-run.sh" "${args[@]}"
}

canvas_bridge_label() {
  local_jobs_label --token canvas-bridge --cardinality singleton
}

canvas_bridge_spec() {
  local label="$1" log_dir="$LOCAL_JOBS_STATE/logs" canvas_dir="$LOCAL_JOBS_HOME/canvases" ws_dirs
  mkdir -p "$log_dir"
  ws_dirs="$(cursor_workspace_canvas_dirs 2>/dev/null || true)"
  "$LOCAL_JOBS_PYTHON" - "$label" "$LOCAL_JOBS_HOME" "$LOCAL_JOBS_STATE" "$LOCAL_JOBS_REGISTRY" "$LOCAL_JOBS_OVERLAY_DIR" "$LOCAL_JOBS_PYTHON" "$canvas_dir" "$log_dir" "$ws_dirs" <<'PY'
import json
import sys
from pathlib import Path

label, home, state, registry, overlay, py, canvas_dir, log_dir, ws_dirs_raw = sys.argv[1:]
watch_paths: list[str] = [canvas_dir]
for line in ws_dirs_raw.splitlines():
    line = line.strip()
    if line and line not in watch_paths:
        watch_paths.append(line)
print(json.dumps({
    "label": label,
    "program_args": [str(Path(home) / "bin" / "canvas-run-bridge.sh")],
    "working_directory": home,
    "env": {
        "LOCAL_JOBS_HOME": home,
        "LOCAL_JOBS_STATE": state,
        "LOCAL_JOBS_REGISTRY": registry,
        "LOCAL_JOBS_OVERLAY_DIR": overlay,
        "LOCAL_JOBS_PYTHON": py,
    },
    "schedule": {"seconds": 15},
    "watch_paths": watch_paths,
    "run_at_load": True,
    "stdout": str(Path(log_dir) / "canvas-run-bridge.out.log"),
    "stderr": str(Path(log_dir) / "canvas-run-bridge.err.log"),
}, separators=(",", ":")))
PY
}

cmd_enable_canvas_runs() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      *) die "unknown enable-canvas-runs option: $1" ;;
    esac
  done
  local label spec
  label="$(canvas_bridge_label)"
  spec="$(canvas_bridge_spec "$label")"
  "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/launchd.py" install --spec "$spec"
}

cmd_disable_canvas_runs() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      *) die "unknown disable-canvas-runs option: $1" ;;
    esac
  done
  "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/launchd.py" uninstall --label "$(canvas_bridge_label)"
}

cmd_logs() {
  local id="" tail=40 job_type=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --type) shift; job_type="${1:-}" ;;
      --tail) shift; tail="${1:-40}" ;;
      *) die "unknown logs option: $1" ;;
    esac
    shift
  done
  [[ -n "$id" ]] || die "logs-job requires --id"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  dispatch_handler "$job_type" logs --id "$id" --tail "$tail"
}

cmd_repair() {
  local id="" all=0 job_type=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --type) shift; job_type="${1:-}" ;;
      --all) all=1 ;;
      *) die "unknown repair option: $1" ;;
    esac
    shift
  done
  if (( all == 1 )); then
    local t failed=0
    while IFS= read -r t; do
      [[ -n "$t" ]] || continue
      printf '\n== repair: %s ==\n' "$t"
      dispatch_handler "$t" repair || failed=1
    done < <(registry_py job-types)
    return "$failed"
  fi
  [[ -n "$id" ]] || die "repair-job requires --id or --all"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  dispatch_handler "$job_type" repair --id "$id"
}

cmd_simple() { # enable/disable
  local verb="$1"; shift
  local id="" job_type=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --type) shift; job_type="${1:-}" ;;
      *) die "unknown $verb option: $1" ;;
    esac
    shift
  done
  [[ -n "$id" ]] || die "$verb-job requires --id"
  [[ -n "$job_type" ]] || job_type="$(resolve_instance_type "$id")"
  dispatch_handler "$job_type" "$verb" --id "$id"
}

cmd_doctor() {
  local plain=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --plain) plain=1 ;;
      *) die "unknown doctor option: $1" ;;
    esac
    shift
  done
  local failed=0 t dash_json fully_quarantined_types overlay_errors dash_ok=1
  if dash_json="$(registry_py dashboard --json 2>/dev/null)"; then
    dash_ok=1
  else
    failed=1; dash_ok=0
    dash_json="$(registry_py view --json 2>/dev/null)" || dash_json='{"instances":[]}'
  fi
  # Skip handler doctor only when a type has ZERO healthy instances (all rows are
  # quarantine/error). A type with both error rows and healthy instances still runs.
  fully_quarantined_types="$(DASH_JSON="$dash_json" "$LOCAL_JOBS_PYTHON" -c 'import json, os
from collections import defaultdict
payload = json.loads(os.environ.get("DASH_JSON") or "{\"instances\":[]}")
counts = defaultdict(lambda: {"ok": 0, "err": 0})
for inst in payload.get("instances", []):
    t = inst.get("type")
    if not t:
        continue
    if inst.get("role") == "error":
        counts[t]["err"] += 1
    else:
        counts[t]["ok"] += 1
for t, c in counts.items():
    if c["ok"] == 0 and c["err"] > 0:
        print(t)')"
  overlay_errors="$(DASH_JSON="$dash_json" "$LOCAL_JOBS_PYTHON" -c 'import json, os
payload = json.loads(os.environ.get("DASH_JSON") or "{}")
for jid, msg in sorted((payload.get("overlay_errors") or {}).items()):
    print(f"{jid}\t{msg}")')"
  if [[ -n "$overlay_errors" ]]; then
    printf '\n== doctor: overlay errors ==\n'
    while IFS=$'\t' read -r jid msg; do
      [[ -n "$jid" ]] || continue
      printf '  OVERLAY: %s — %s\n' "$jid" "$msg"
      failed=1
    done <<< "$overlay_errors"
  fi
  while IFS= read -r t; do
    [[ -n "$t" ]] || continue
    printf '\n== doctor: %s ==\n' "$t"
    case "
$fully_quarantined_types
" in
      *"
$t
"*)
        printf 'QUARANTINED: type is not runnable; see drift scan for details\n'
        failed=1
        continue
        ;;
    esac
    local doctor_out doctor_rc=0
    doctor_out="$(dispatch_handler "$t" doctor 2>&1)" || doctor_rc=$?
    if (( doctor_rc == 0 )); then
      printf '%s\n' "$doctor_out"
    else
      printf 'FAIL: handler doctor failed (rc=%s)\n' "$doctor_rc"
      failed=1
    fi
  done < <(registry_py job-types)
  printf '\n== doctor: drift scan ==\n'
  if (( dash_ok == 0 )) && [[ "$(printf '%s' "$dash_json" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(len(json.load(sys.stdin).get("instances") or []))')" == "0" ]]; then
    printf '  FAIL: drift scan skipped (could not load instance payload)\n'
    failed=1
  else
  env DASH_JSON="$dash_json" LOCAL_JOBS_HOME="$LOCAL_JOBS_HOME" LOCAL_JOBS_PYTHON="$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_PYTHON" -c 'import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["LOCAL_JOBS_HOME"]) / "lib"))
import events  # noqa: E402
payload = json.loads(os.environ["DASH_JSON"])
issues = 0
for inst in payload.get("instances", []):
    if inst.get("role") == "error":
        issues += 1
        err = inst.get("error") or {}
        print("  QUARANTINED: {} — {}".format(inst.get("type"), err.get("reason")))
        events.emit("drift", job_type=inst.get("type"), payload={"kind": "quarantine", "reason": err.get("reason")})
        continue
    if inst.get("drift"):
        issues += 1
        print("  DRIFT: {} ({}) enabled={} loaded={}".format(
            inst.get("id"), inst.get("type"), inst.get("enabled"), inst.get("launchd_loaded")))
        events.emit("drift", job_id=inst.get("id"), job_type=inst.get("type"),
                    payload={"enabled": inst.get("enabled"), "loaded": inst.get("launchd_loaded")})
print("  no drift" if issues == 0 else f"  {issues} drift/quarantine issue(s)")
sys.exit(1 if issues else 0)' || failed=1
  fi
  if (( plain == 1 )); then
    printf '\n== operator summary ==\n'
    registry_py dashboard --brief || true
    for inst in $(printf '%s' "$dash_json" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print(" ".join(i["id"] for i in d["instances"] if i.get("drift")))'); do
      [[ -n "$inst" ]] || continue
      registry_py explain-job --id "$inst" 2>/dev/null || true
    done
  fi
  return "$failed"
}

main() {
  local verb
  verb="$(normalize_cmd "${1:-}")"
  shift || true
  case "$verb" in
    help) usage ;;
    view) cmd_view "$@" ;;
    view-jobs) cmd_view_jobs "$@" ;;
    dashboard) cmd_dashboard "$@" ;;
    explain-job) cmd_explain_job "$@" ;;
    resolve-instance) cmd_resolve_instance "$@" ;;
    list-types) cmd_list_types "$@" ;;
    handler-path) cmd_handler_path "$@" ;;
    describe-types) cmd_describe_types "$@" ;;
    add) cmd_add "$@" ;;
    update) cmd_update "$@" ;;
    delete) cmd_delete "$@" ;;
    delete-fetch-if-current) dispatch_handler incremental-git-fetch delete-if-current "$@" ;;
    run) cmd_run "$@" ;;
    enable-canvas-runs) cmd_enable_canvas_runs "$@" ;;
    disable-canvas-runs) cmd_disable_canvas_runs "$@" ;;
    logs) cmd_logs "$@" ;;
    repair) cmd_repair "$@" ;;
    enable) cmd_simple enable "$@" ;;
    disable) cmd_simple disable "$@" ;;
    adopt) "$SCRIPT_DIR/adopt-job.sh" "$@" ;;
    add-job-type) "$SCRIPT_DIR/add-job-type.sh" "$@" ;;
    update-job-type) "$SCRIPT_DIR/update-job-type.sh" "$@" ;;
    doctor) cmd_doctor "$@" ;;
    *) die "unknown command: $verb" ;;
  esac
}

main "$@"
