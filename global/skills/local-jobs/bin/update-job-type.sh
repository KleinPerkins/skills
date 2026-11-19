#!/usr/bin/env bash
# Evolve an existing job type safely (schema_version bump / field add / field
# remove already expressed in the handler), by migrating its instances forward
# and proving nothing regressed:
#   snapshot the type's store -> run its `migrate` (re-merge defaults, stamp
#   schema_version) -> VERIFY the type -> cross-type REGRESSION (every type still
#   loads+validates) -> DRY-RUN the type -> on ANY failure, ROLL BACK the store.
#
# Usage: update-job-type.sh --type <type> [--no-dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

type=""; do_dry=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type) shift; type="${1:-}" ;;
    --no-dry-run) do_dry=0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done
[[ -n "$type" ]] || die "update-job-type requires --type"

handler="$(require_handler "$type")"
authoring() { "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/authoring.py" "$@"; }

# Discover this type's store file (if any) from its describe, to snapshot it.
store_file="$("$handler" describe | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print((json.load(sys.stdin).get("config_file") or ""))')"
backup=""
if [[ -n "$store_file" && -f "$store_file" ]]; then
  backup="${store_file}.preupdate.bak"
  cp -p "$store_file" "$backup"
  log "snapshotted store: $store_file -> $backup"
fi

rollback() {
  log_err "update-job-type: verification failed — rolling back $type"
  [[ -n "$backup" && -f "$backup" ]] && mv -f "$backup" "$store_file"
  die "update-job-type: $type rolled back (instances restored)"
}

# 1) Forward-migrate this type's instances (idempotent re-merge + version stamp).
log "migrating ${type} instances forward..."
"$handler" migrate >/dev/null 2>&1 || true   # store-backed types implement migrate; others no-op

# 2) Verify the changed type still conforms.
log "verifying ${type}..."
if ! authoring verify --type "$type"; then rollback; fi

# 3) Cross-type regression: every registered type still loads + validates.
log "cross-type regression (all types)..."
if ! authoring regression >/dev/null; then rollback; fi

# 4) Dry-run the changed type end-to-end (proves run still works post-migration).
if (( do_dry == 1 )); then
  log "dry-run ${type}..."
  ids="$("$handler" list-instances | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(" ".join(i["id"] for i in json.load(sys.stdin) if i.get("role")=="instance" and i.get("enabled",True)))')"
  if [[ -n "$ids" ]]; then
    first_id="${ids%% *}"
    if ! "$SCRIPT_DIR/dispatch-run.sh" --type "$type" --id "$first_id" --dry-run >/dev/null 2>&1; then rollback; fi
  fi
fi

# Success: discard the snapshot.
[[ -n "$backup" && -f "$backup" ]] && rm -f "$backup"
log "update-job-type: $type migrated + verified + regression-clean"
