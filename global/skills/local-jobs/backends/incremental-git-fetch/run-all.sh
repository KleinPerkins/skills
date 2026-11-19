#!/usr/bin/env bash
# Run all enabled repos (optionally one repo) with schedule jitter.
# Each repo fetch is serialized behind a per-repo flock so overlapping launchd
# agents (global + per-repo + an in-flight migration) never collide.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

TARGET_REPO="${1:-}"
DRY_RUN="${LOCAL_JOBS_IGF_DRY_RUN:-0}"
FAILURES=0

# Per-repo outcome ledger (id<TAB>status<TAB>reason), one line per repo. When
# the handler sets LOCAL_JOBS_IGF_OUTCOME_FILE it reads this to build a truthful
# per-instance runlog; a bare `run-all.sh` invocation (no env) writes nothing.
OUTCOME_FILE="${LOCAL_JOBS_IGF_OUTCOME_FILE:-}"
# Multi-repo sweep behavior on a per-repo failure; resolved from config in main().
FAILURE_POLICY="continue"

LOCK_DIR="${LOCAL_JOBS_STATE:-$HOME/.local-jobs}/locks"
FLOCK="$LOCAL_JOBS_HOME/lib/flock.py"

record_outcome() {
  # id status reason → one TSV line (ids/status/reason never contain tabs).
  [[ -n "$OUTCOME_FILE" ]] || return 0
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$OUTCOME_FILE"
}

classify_failure_reason() {
  # Map fetch-repo.sh output to ONE coarse, PM-readable reason. Order matters:
  # the most specific signal wins.
  local out="$1"
  case "$out" in
    *"fast-forward merge failed"*|*"Not possible to fast-forward"*|*"not something we can merge"*)
      printf 'merge not fast-forward' ;;
    *"Repository not found"*|*"repository not found"*|*"does not appear to be a git repository"*)
      printf 'remote not found' ;;
    *"Could not resolve host"*|*"Connection refused"*|*"Connection timed out"*|*"Operation timed out"*|*"Permission denied"*|*"kex_exchange"*|*"Could not read from remote"*|*"ssh: connect"*)
      printf 'network/SSH error' ;;
    *"repo path does not exist"*|*"not a git work tree"*)
      printf 'local repo missing' ;;
    *"index.lock is held"*)
      printf 'repo busy (lock held)' ;;
    *)
      printf 'fetch failed' ;;
  esac
}

apply_jitter() {
  local global_json window_start window_end use_jitter window_seconds jitter

  if [[ "${LOCAL_JOBS_IGF_SKIP_JITTER:-0}" == "1" ]]; then
    log "Skipping schedule jitter (LOCAL_JOBS_IGF_SKIP_JITTER=1)"
    return 0
  fi

  global_json="$(config_py global)"
  window_start="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; g=json.load(sys.stdin); print(g.get("launchd",{}).get("window_start_hour",18))' <<<"$global_json")"
  window_end="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; g=json.load(sys.stdin); print(g.get("launchd",{}).get("window_end_hour",24))' <<<"$global_json")"
  use_jitter="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; g=json.load(sys.stdin); print("1" if g.get("launchd",{}).get("use_jitter", True) else "0")' <<<"$global_json")"

  [[ "$use_jitter" == "1" ]] || {
    log "Schedule jitter disabled in config"
    return 0
  }

  window_seconds=$(( (window_end - window_start) * 3600 ))
  (( window_seconds > 0 )) || die "invalid schedule window: ${window_start}-${window_end}"

  # Use the shared scheduler for jitter so the full window is covered
  # (bash $RANDOM caps at 32767s ~9.1h and truncates longer windows — P2-8).
  jitter="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/schedule.py" jitter \
    --schedule "{\"window_start_hour\":$window_start,\"window_end_hour\":$window_end,\"use_jitter\":true}" 2>/dev/null)"
  [[ "$jitter" =~ ^[0-9]+$ ]] || jitter=$(( RANDOM % window_seconds ))
  log "Schedule window ${window_start}:00-${window_end}:00; sleeping ${jitter}s (~$(( jitter / 60 )) min)"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] would sleep ${jitter}s"
  else
    sleep "$jitter"
  fi
}

fetch_one() {
  local repo_id="$1"
  local lock="$LOCK_DIR/igf-${repo_id}.lock"
  LOCAL_JOBS_IGF_DRY_RUN="$DRY_RUN" "$LOCAL_JOBS_PYTHON" "$FLOCK" "$lock" "$SCRIPT_DIR/fetch-repo.sh" "$repo_id"
}

attempt_one() {
  # Fetch one repo, record its own truthful outcome, and return its rc so the
  # caller can honor failure_policy. Combined output is re-emitted so launchd
  # logs still capture everything.
  local repo_id="$1" out rc=0
  out="$(fetch_one "$repo_id" 2>&1)" && rc=0 || rc=$?
  printf '%s\n' "$out"
  if (( rc == 0 )); then
    # `up to date` is the neutral default; the handler upgrades it to
    # `fast-forwarded` from the HEAD snapshot delta when it moved.
    record_outcome "$repo_id" success "up to date"
  else
    FAILURES=$((FAILURES + 1))
    log_err "[$repo_id] fetch failed"
    record_outcome "$repo_id" failure "$(classify_failure_reason "$out")"
  fi
  return "$rc"
}

run_all() {
  local repo_id

  if [[ -n "$TARGET_REPO" ]]; then
    attempt_one "$TARGET_REPO" || true
    return 0
  fi

  # The global scheduled window fetches only inherit repos; a repo with its own
  # per-repo agent is fetched by that agent, never twice (P0-1). A manual
  # `run-job --all` (INHERIT_ONLY unset) still fetches every enabled repo.
  local id_source="enabled-ids"
  if [[ "${LOCAL_JOBS_IGF_INHERIT_ONLY:-0}" == "1" ]]; then
    id_source="inherit-ids"
  fi

  # Capture the id list with an explicit exit check. A bare `< <(config_py ...)`
  # process substitution hides a config-read crash (set -e/pipefail can't see a
  # failure inside process substitution), which would silently yield zero repos
  # and let the sweep exit 0 — reported downstream as "success". Fail loud: a
  # crash dies here, while a genuinely empty enabled/inherit set (exit 0, no
  # output) still legitimately runs zero repos.
  local ids_raw ids=()
  ids_raw="$(config_py "$id_source")" || die "run-all: failed to read $id_source from config"
  while IFS= read -r repo_id; do
    [[ -n "$repo_id" ]] && ids+=("$repo_id")
  done <<<"$ids_raw"

  # failure_policy=stop halts the sweep after the first failure; the remaining
  # enabled repos are recorded as `skipped` in the ledger only (no per-child run
  # events downstream), so a repo's real prior streak is never reset by a skip.
  local stopped=0 arc
  for repo_id in ${ids[@]+"${ids[@]}"}; do
    if (( stopped )); then
      record_outcome "$repo_id" skipped "skipped after earlier failure"
      log "[$repo_id] skipped (failure_policy=stop after earlier failure)"
      continue
    fi
    arc=0
    attempt_one "$repo_id" || arc=$?
    if (( arc != 0 )) && [[ "$FAILURE_POLICY" == "stop" ]]; then
      stopped=1
      log_err "failure_policy=stop: halting sweep; remaining enabled repos skipped"
    fi
  done
}

main() {
  require_cmd git
  require_cmd "$LOCAL_JOBS_PYTHON"

  mkdir -p "$LOCAL_JOBS_IGF_LOG_DIR" "$LOCK_DIR"

  # config.py validates + normalizes global.failure_policy, so this is always
  # `continue` or `stop`; fall back to continue if the read ever fails.
  FAILURE_POLICY="$(config_py global | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print((json.load(sys.stdin) or {}).get("failure_policy","continue"))' 2>/dev/null || printf 'continue')"
  [[ "$FAILURE_POLICY" == "stop" ]] || FAILURE_POLICY="continue"

  log "incremental-git-fetch run starting (dry_run=$DRY_RUN target=${TARGET_REPO:-all} failure_policy=$FAILURE_POLICY)"

  apply_jitter
  run_all

  if (( FAILURES > 0 )); then
    log_err "incremental-git-fetch completed with $FAILURES failure(s)"
    exit 1
  fi

  log "incremental-git-fetch run completed successfully"
}

main "$@"
