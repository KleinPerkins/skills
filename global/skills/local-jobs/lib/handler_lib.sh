#!/usr/bin/env bash
# Shared handler chassis for store-backed local-jobs types.
#
# A handler sources this file, declares a few knobs + hooks, and calls
# `handler_main "$@"`. Every generic verb (list-instances, view, add, update,
# delete, enable, disable, repair, logs, doctor, migrate) is implemented HERE
# over the Python chassis (store.py / launchd.py / schedule.py / contract.py /
# events.py). Handlers shrink to: describe (their schema), the launchd env +
# working dir for an instance, and run. New plist/schedule/CRUD bugs are fixed
# once, here, for all types.
#
# Required knobs (set before handler_main):
#   HANDLER_TYPE HANDLER_CARDINALITY(singleton|multi) HANDLER_LABEL_TOKEN
#   HANDLER_SCHEMA_VERSION HANDLER_STORE_FILE HANDLER_ADD_SCHEMA(json)
# Optional knobs:
#   HANDLER_FIELD_DEFAULTS(json={}) HANDLER_REQUIRED_FIELDS(json=[])
#   HANDLER_LOG_DIR(~/Library/Logs/local-jobs) HANDLER_SINGLETON_ID(=token)
# Required hooks (bash functions): handler_describe, handler_do_run
# Optional hooks: handler_launchd_env <id>, handler_working_dir <id>,
#   handler_doctor_extra
set -euo pipefail

_HL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_JOBS_HOME="${LOCAL_JOBS_HOME:-$(cd -- "$_HL_DIR/.." && pwd)}"
LOCAL_JOBS_PYTHON="${LOCAL_JOBS_PYTHON:-python3}"
LOCAL_JOBS_STATE="${LOCAL_JOBS_STATE:-$HOME/.local-jobs}"

hl_die() { printf '%s: %s\n' "${HANDLER_TYPE:-handler}" "$*" >&2; exit 2; }

_hl_defaults() {
  # NB: avoid ${VAR:-{}} — the brace default collides with the expansion's own
  # closing brace and appends a stray '}'.
  [[ -n "${HANDLER_FIELD_DEFAULTS:-}" ]] || HANDLER_FIELD_DEFAULTS='{}'
  [[ -n "${HANDLER_REQUIRED_FIELDS:-}" ]] || HANDLER_REQUIRED_FIELDS='[]'
  HANDLER_LOG_DIR="${HANDLER_LOG_DIR:-$HOME/Library/Logs/local-jobs}"
  HANDLER_SINGLETON_ID="${HANDLER_SINGLETON_ID:-$HANDLER_LABEL_TOKEN}"
  HANDLER_CARDINALITY="${HANDLER_CARDINALITY:-multi}"
}

_hl_py() { "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/$1" "${@:2}"; }
_hl_label_root() { LOCAL_JOBS_STATE="$LOCAL_JOBS_STATE" _hl_py registry.py label-root; }
_hl_label_template() {
  local root; root="$(_hl_label_root)"
  if [[ "${HANDLER_CARDINALITY:-multi}" == "singleton" ]]; then
    printf '%s.%s' "$root" "$HANDLER_LABEL_TOKEN"
  else
    printf '%s.%s.<id>' "$root" "$HANDLER_LABEL_TOKEN"
  fi
}

_hl_store() {
  _hl_py store.py --file "$HANDLER_STORE_FILE" --schema-version "$HANDLER_SCHEMA_VERSION" \
    --defaults "$HANDLER_FIELD_DEFAULTS" --required "$HANDLER_REQUIRED_FIELDS" "$@"
}

_hl_runtime() {
  LOCAL_JOBS_LABEL_ROOT="$(_hl_label_root)" _hl_py handler_runtime.py "$1" \
    --type "$HANDLER_TYPE" --token "$HANDLER_LABEL_TOKEN" --cardinality "$HANDLER_CARDINALITY" \
    --file "$HANDLER_STORE_FILE" --schema-version "$HANDLER_SCHEMA_VERSION" \
    --defaults "$HANDLER_FIELD_DEFAULTS" --required "$HANDLER_REQUIRED_FIELDS" \
    --log-dir "$HANDLER_LOG_DIR" --home "$LOCAL_JOBS_HOME" "${@:2}"
}

_hl_emit() { # kind verb id  (best-effort; never fails the verb)
  _hl_py events.py emit --kind "$1" --id "$3" --type "$HANDLER_TYPE" \
    --actor "${LOCAL_JOBS_ACTOR:-cli}" --payload "{\"verb\":\"$2\"}" >/dev/null 2>&1 || true
}

_hl_resolve_id() { # echoes the effective id (singleton -> fixed id)
  local id="$1"
  if [[ "$HANDLER_CARDINALITY" == "singleton" ]]; then printf '%s' "$HANDLER_SINGLETON_ID"; return; fi
  [[ -n "$id" ]] || hl_die "this verb requires --id"
  printf '%s' "$id"
}

_hl_extra_env() { if declare -F handler_launchd_env >/dev/null; then handler_launchd_env "$1"; else printf '{}'; fi; }
_hl_working_dir() { if declare -F handler_working_dir >/dev/null; then handler_working_dir "$1"; else printf ''; fi; }

_hl_install() {
  local id="$1" extra wd
  extra="$(_hl_extra_env "$id")"
  wd="$(_hl_working_dir "$id")"
  local args=(install --id "$id" --extra-env "$extra")
  [[ -n "$wd" ]] && args+=(--working-dir "$wd")
  _hl_runtime "${args[@]}"
}

_hl_enabled() { # echoes true/false for an instance
  _hl_store get --id "$1" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("true" if json.load(sys.stdin).get("enabled",True) else "false")'
}

_hl_execution_mode() { # echoes scheduled|on_demand for a stored instance
  _hl_store get --id "$1" 2>/dev/null | "$LOCAL_JOBS_PYTHON" -c 'import json,sys
try:
    entry = json.load(sys.stdin)
except Exception:
    entry = {}
print(entry.get("execution_mode") or "scheduled")'
}

# Converge the launchd agent for an instance to its correct state.
#   on_demand -> NEVER carries an agent (runs only via run-job); boot out any
#                lingering one so "no loaded agent" is the correct, drift-free
#                state.
#   scheduled -> agent present iff the instance is enabled.
_hl_apply_agent() {
  local id="$1"
  if [[ "$(_hl_execution_mode "$id")" == "on_demand" ]]; then
    _hl_runtime uninstall --id "$id" >/dev/null 2>&1 || true
    return 0
  fi
  if [[ "$(_hl_enabled "$id")" == "true" ]]; then
    _hl_install "$id" >/dev/null
  else
    _hl_runtime uninstall --id "$id" >/dev/null 2>&1 || true
  fi
}

_hl_validate_schedule() { # value -> die on invalid
  local v="$1"
  [[ -n "$v" ]] || return 0
  local err
  if ! err="$(_hl_py schedule.py validate --schedule "$v" 2>&1)"; then
    hl_die "invalid schedule: $err"
  fi
}

# ---- generic verbs ---------------------------------------------------------

_hl_cmd_add() {
  local dry=0 rest=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry=1 ;;
      *) rest+=("$1") ;;
    esac
    shift
  done
  local schema="$HANDLER_ADD_SCHEMA" entry
  entry="$(_hl_py contract.py build-entry --schema "$schema" -- "${rest[@]}")" \
    || hl_die "invalid add flags"
  if [[ "$HANDLER_CARDINALITY" == "singleton" ]]; then
    entry="$(SID="$HANDLER_SINGLETON_ID" printf '%s' "$entry" | SID="$HANDLER_SINGLETON_ID" "$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; e=json.load(sys.stdin); e["id"]=os.environ["SID"]; print(json.dumps(e))')"
  fi
  local sched; sched="$(printf '%s' "$entry" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys
v=json.load(sys.stdin).get("schedule","")
print(json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v)')"
  _hl_validate_schedule "$sched"
  local iid; iid="$(printf '%s' "$entry" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  local store_args=()
  (( dry == 1 )) && store_args+=(--dry-run)
  local would_upsert=0
  if [[ "$HANDLER_CARDINALITY" == "singleton" ]] && _hl_store get --id "$iid" >/dev/null 2>&1; then
    would_upsert=1
    if (( dry == 1 )); then
      _hl_store set --id "$iid" --patch "$entry" "${store_args[@]}" >/dev/null
    else
      _hl_store set --id "$iid" --patch "$entry" >/dev/null
    fi
  else
    if (( dry == 1 )); then
      _hl_store add --entry "$entry" "${store_args[@]}" >/dev/null
    else
      _hl_store add --entry "$entry" >/dev/null
    fi
  fi
  if (( dry == 1 )); then
    local enabled mode would_install=0
    enabled="$(printf '%s' "$entry" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("true" if json.load(sys.stdin).get("enabled",True) else "false")')"
    mode="$(printf '%s' "$entry" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("execution_mode") or "scheduled")')"
    [[ "$enabled" == "true" && "$mode" != "on_demand" ]] && would_install=1
    ENTRY="$entry" IID="$iid" TOKEN="$HANDLER_LABEL_TOKEN" CARD="$HANDLER_CARDINALITY" \
      WOULD_INSTALL="$would_install" WOULD_UPSERT="$would_upsert" HANDLER_TYPE="$HANDLER_TYPE" \
      LOCAL_JOBS_HOME="$LOCAL_JOBS_HOME" \
      "$LOCAL_JOBS_PYTHON" - <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ.get("LOCAL_JOBS_HOME", ".")) / "lib"))
import handler_runtime as hr
import schedule as schedule_mod
from datetime import datetime
entry = json.loads(os.environ["ENTRY"])
iid = os.environ["IID"]
token = os.environ["TOKEN"]
card = os.environ["CARD"]
label = hr.label_for(token, card, iid)
nr = {"window_start": None, "window_end": None, "basis": "unknown"}
sched = entry.get("schedule")
if sched:
    try:
        nr = schedule_mod.Schedule.parse(sched).next_run(datetime.now().astimezone())
    except (ValueError, KeyError, TypeError):
        pass
print(json.dumps({
    "dry_run": True,
    "type": os.environ["HANDLER_TYPE"],
    "entry": entry,
    "launchd_label": label,
    "next_run": nr,
    "would_install": os.environ["WOULD_INSTALL"] == "1",
    "would_upsert": os.environ["WOULD_UPSERT"] == "1",
}, indent=2))
PY
    return 0
  fi
  _hl_apply_agent "$iid"
  _hl_emit lifecycle add "$iid"
  printf 'added %s instance %s\n' "$HANDLER_TYPE" "$iid"
}

_hl_cmd_update() {
  local id="" rest=()
  local a=("$@") i=0
  while [[ $i -lt ${#a[@]} ]]; do
    case "${a[$i]}" in
      --id) i=$((i+1)); id="${a[$i]}" ;;
      *) rest+=("${a[$i]}") ;;
    esac
    i=$((i+1))
  done
  id="$(_hl_resolve_id "$id")"
  [[ ${#rest[@]} -gt 0 ]] || hl_die "update requires fields to change (e.g. --schedule/--enabled)"
  local patch; patch="$(_hl_py contract.py build-patch --schema "$HANDLER_ADD_SCHEMA" -- "${rest[@]}")" \
    || hl_die "invalid update flags"
  local sched; sched="$(printf '%s' "$patch" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys
v=json.load(sys.stdin).get("schedule","")
print(json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v)')"
  _hl_validate_schedule "$sched"
  _hl_store set --id "$id" --patch "$patch" >/dev/null
  _hl_apply_agent "$id"
  _hl_emit lifecycle update "$id"
  printf 'updated %s instance %s\n' "$HANDLER_TYPE" "$id"
}

_hl_cmd_delete() {
  local id="" confirm=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id) shift; id="${1:-}" ;;
      --confirm) confirm=1 ;;
      --purge-launchd) : ;;
      *) hl_die "unknown delete option: $1" ;;
    esac
    shift
  done
  id="$(_hl_resolve_id "$id")"
  (( confirm == 1 )) || hl_die "delete requires --confirm (destructive)"
  _hl_runtime uninstall --id "$id" >/dev/null
  _hl_store remove --id "$id" >/dev/null
  _hl_emit lifecycle delete "$id"
  printf 'removed %s instance %s\n' "$HANDLER_TYPE" "$id"
}

_hl_cmd_toggle() { # enable|disable
  local verb="$1"; shift
  local id=""
  while [[ $# -gt 0 ]]; do case "$1" in --id) shift; id="${1:-}" ;; *) hl_die "unknown $verb option: $1" ;; esac; shift; done
  id="$(_hl_resolve_id "$id")"
  if [[ "$verb" == "enable" ]]; then
    _hl_store set --id "$id" --patch '{"enabled":true}' >/dev/null
  else
    _hl_store set --id "$id" --patch '{"enabled":false}' >/dev/null
  fi
  # on_demand jobs install no agent even when enabled; _hl_apply_agent honors mode.
  _hl_apply_agent "$id"
  _hl_emit lifecycle "$verb" "$id"
  printf '%sd %s instance %s\n' "$verb" "$HANDLER_TYPE" "$id"
}

_hl_cmd_repair() {
  local id="" all=0
  while [[ $# -gt 0 ]]; do case "$1" in --id) shift; id="${1:-}" ;; --all) all=1 ;; *) hl_die "unknown repair option: $1" ;; esac; shift; done
  local ids=()
  if [[ -n "$id" && "$all" -eq 0 ]]; then
    ids=("$(_hl_resolve_id "$id")")
  else
    while IFS= read -r iid; do [[ -n "$iid" ]] && ids+=("$iid"); done \
      < <(_hl_store list | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; [print(e["id"]) for e in json.load(sys.stdin)]')
  fi
  local iid fails=0
  for iid in "${ids[@]}"; do
    if [[ "$(_hl_execution_mode "$iid")" == "on_demand" ]]; then
      # on_demand instances never carry an agent; "no loaded agent" is correct,
      # not drift. Boot out any lingering one and preserve the mode field.
      _hl_runtime uninstall --id "$iid" >/dev/null 2>&1 || true
    elif [[ "$(_hl_enabled "$iid")" == "true" ]]; then
      _hl_install "$iid" >/dev/null || { printf 'repair: install failed for %s\n' "$iid" >&2; fails=$((fails + 1)); }
    else
      # Converge disabled instances: boot out any lingering agent (fixes drift).
      _hl_runtime uninstall --id "$iid" >/dev/null 2>&1 || true
    fi
  done
  _hl_emit lifecycle repair "${id:-all}"
  # Honest convergence summary: a swallowed install failure must not report
  # "complete"/rc 0 (mirrors run()'s truthful-status principle).
  local total=${#ids[@]} converged
  converged=$(( total - fails ))
  if (( fails > 0 )); then
    printf 'repair: %d/%d converged, %d failed\n' "$converged" "$total" "$fails" >&2
    return 1
  fi
  printf 'repair: complete (%d/%d converged)\n' "$converged" "$total"
}

_hl_cmd_logs() {
  local id="" tail=40
  while [[ $# -gt 0 ]]; do case "$1" in --id) shift; id="${1:-}" ;; --tail) shift; tail="${1:-40}" ;; *) hl_die "unknown logs option: $1" ;; esac; shift; done
  id="$(_hl_resolve_id "$id")"
  local inst; inst="$(_hl_runtime view --id "$id")" || hl_die "unknown instance: $id"
  local o e
  o="$(printf '%s' "$inst" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["log_paths"]["stdout"])')"
  e="$(printf '%s' "$inst" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["log_paths"]["stderr"])')"
  printf 'stdout: %s\nstderr: %s\n' "$o" "$e"
  local f
  for f in "$o" "$e"; do
    printf '\n-- %s (tail %s) --\n' "$f" "$tail"
    if [[ -f "$f" ]]; then "$LOCAL_JOBS_PYTHON" - "$f" "$tail" <<'PY'; else printf '(no log yet)\n'; fi
from collections import deque
from pathlib import Path
import sys
for line in deque(Path(sys.argv[1]).open(errors="replace"), maxlen=int(sys.argv[2])):
    print(line, end="")
PY
  done
}

_hl_cmd_doctor() {
  local issues=0
  printf '== %s doctor ==\n' "$HANDLER_TYPE"
  if "$LOCAL_JOBS_PYTHON" -c 'import yaml' 2>/dev/null; then printf 'PyYAML: ok\n'; else printf 'PyYAML: missing\n'; issues=$((issues+1)); fi
  if _hl_store validate >/dev/null 2>&1; then printf 'store: ok (%s)\n' "$HANDLER_STORE_FILE"; else printf 'store: INVALID\n'; issues=$((issues+1)); fi
  local count; count="$(_hl_store list | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '?')"
  printf 'instances: %s\n' "$count"
  if declare -F handler_doctor_extra >/dev/null; then handler_doctor_extra || issues=$((issues+1)); fi
  local status=PASS; (( issues == 0 )) || status=FAIL
  _hl_py events.py emit --kind status --type "$HANDLER_TYPE" --actor "${LOCAL_JOBS_ACTOR:-cli}" \
    --payload "{\"check\":\"doctor\",\"status\":\"$status\",\"issues\":$issues}" >/dev/null 2>&1 || true
  if (( issues == 0 )); then printf 'doctor: PASS\n'; else printf 'doctor: FAIL (%s)\n' "$issues"; return 1; fi
}

handler_main() {
  _hl_defaults
  local verb="${1:-}"; shift || true
  case "$verb" in
    describe) handler_describe ;;
    list-instances) _hl_runtime list-instances ;;
    view)
      local id=""
      while [[ $# -gt 0 ]]; do case "$1" in --id) shift; id="${1:-}" ;; *) hl_die "unknown view option: $1" ;; esac; shift; done
      _hl_runtime view --id "$(_hl_resolve_id "$id")"
      ;;
    add) _hl_cmd_add "$@" ;;
    update) _hl_cmd_update "$@" ;;
    delete) _hl_cmd_delete "$@" ;;
    enable) _hl_cmd_toggle enable "$@" ;;
    disable) _hl_cmd_toggle disable "$@" ;;
    repair) _hl_cmd_repair "$@" ;;
    logs) _hl_cmd_logs "$@" ;;
    doctor) _hl_cmd_doctor ;;
    migrate) _hl_store migrate ;;
    run) handler_do_run "$@" ;;
    ""|-h|--help) printf '%s handler verbs: describe list-instances view run logs add update delete repair enable disable doctor migrate\n' "$HANDLER_TYPE"; exit 2 ;;
    *) hl_die "unknown verb: $verb" ;;
  esac
}
