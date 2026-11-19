#!/usr/bin/env bash
# Incremental fetch + optional ff-only merge for one configured repo.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

REPO_ID="${1:-}"
DRY_RUN="${LOCAL_JOBS_IGF_DRY_RUN:-0}"

usage() {
  cat <<USAGE
Usage: fetch-repo.sh <repo-id>

Environment:
  LOCAL_JOBS_IGF_DRY_RUN=1   Print actions without mutating git state
USAGE
}

remove_stale_lock() {
  local repo_path="$1"
  local lock_path="$repo_path/.git/index.lock"

  [[ -f "$lock_path" ]] || return 0

  if lsof "$lock_path" >/dev/null 2>&1; then
    die "index.lock is held by another process: $lock_path"
  fi

  log "Removing stale index.lock at $lock_path"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] would remove $lock_path"
  else
    rm -f "$lock_path"
  fi
}

fetch_repo() {
  local repo_json="$1"
  local repo_id path remote branch filter_blobs full_fetch ff_only fetch_tags tag_option

  repo_id="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$repo_json")"
  path="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$repo_json")"
  remote="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("remote","origin"))' <<<"$repo_json")"
  branch="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("branch","main"))' <<<"$repo_json")"
  filter_blobs="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("1" if json.load(sys.stdin).get("filter_blobs", True) else "0")' <<<"$repo_json")"
  full_fetch="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("1" if json.load(sys.stdin).get("full_fetch_other_refs", False) else "0")' <<<"$repo_json")"
  ff_only="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("1" if json.load(sys.stdin).get("ff_only_merge", True) else "0")' <<<"$repo_json")"
  fetch_tags="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("1" if json.load(sys.stdin).get("fetch_tags", False) else "0")' <<<"$repo_json")"
  tag_option="--no-tags"
  [[ "$fetch_tags" == "1" ]] && tag_option="--tags"

  [[ -d "$path" ]] || die "repo path does not exist: $path ($repo_id)"
  git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "not a git work tree: $path ($repo_id)"

  local current_branch tracking_branch
  current_branch="$(git -C "$path" branch --show-current 2>/dev/null || true)"
  tracking_branch="$(git -C "$path" rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || true)"

  log "[$repo_id] path=$path remote=$remote branch=$branch"
  log "[$repo_id] current=$current_branch upstream=$tracking_branch"

  remove_stale_lock "$path"

  local fetch_args=(-c protocol.version=2 fetch "$remote" "refs/heads/${branch}:refs/remotes/${remote}/${branch}" "$tag_option")
  if [[ "$filter_blobs" == "1" ]]; then
    fetch_args+=(--filter=blob:none)
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] [$repo_id] git -C $path ${fetch_args[*]}"
  else
    git -C "$path" "${fetch_args[@]}"
  fi

  if [[ "$full_fetch" == "1" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "[dry-run] [$repo_id] git -C $path fetch $remote $tag_option"
    else
      git -C "$path" fetch "$remote" "$tag_option"
    fi
  fi

  if [[ "$ff_only" == "1" && "$current_branch" == "$branch" && "$tracking_branch" == "${remote}/${branch}" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "[dry-run] [$repo_id] git -C $path merge --ff-only ${remote}/${branch}"
    else
      if git -C "$path" merge --ff-only "${remote}/${branch}"; then
        log "[$repo_id] fast-forward merge completed"
      else
        die "[$repo_id] fast-forward merge failed"
      fi
    fi
  else
    log "[$repo_id] skipping merge (branch=$current_branch tracking=$tracking_branch)"
  fi

  local head
  head="$(git -C "$path" rev-parse --short HEAD 2>/dev/null || true)"
  [[ -n "$head" ]] && log "[$repo_id] HEAD now $head"
}

main() {
  export GIT_TERMINAL_PROMPT=0
  require_cmd git
  require_cmd "$LOCAL_JOBS_PYTHON"
  require_cmd lsof

  [[ -n "$REPO_ID" ]] || { usage >&2; exit 2; }

  local repo_json
  repo_json="$(config_py repo "$REPO_ID")"
  local enabled
  enabled="$("$LOCAL_JOBS_PYTHON" -c 'import json,sys; print("1" if json.load(sys.stdin).get("enabled", True) else "0")' <<<"$repo_json")"
  [[ "$enabled" == "1" ]] || {
    log "[$REPO_ID] disabled in config; skipping"
    exit 0
  }

  fetch_repo "$repo_json"
}

main "$@"
