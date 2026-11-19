#!/usr/bin/env bash
# Shared helpers for the local-jobs framework.
set -euo pipefail

LOCAL_JOBS_HOME="${LOCAL_JOBS_HOME:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
LOCAL_JOBS_REGISTRY="${LOCAL_JOBS_REGISTRY:-$LOCAL_JOBS_HOME/config/registry.yml}"
LOCAL_JOBS_STATE="${LOCAL_JOBS_STATE:-$HOME/.local-jobs}"
LOCAL_JOBS_OVERLAY_DIR="${LOCAL_JOBS_OVERLAY_DIR:-$LOCAL_JOBS_STATE/registry.d}"
export LOCAL_JOBS_HOME LOCAL_JOBS_STATE LOCAL_JOBS_REGISTRY LOCAL_JOBS_OVERLAY_DIR
# Pin one interpreter for the whole framework (Phase 5). launchd plists export a
# PATH that puts the homebrew python3 (with PyYAML) first.
LOCAL_JOBS_PYTHON="${LOCAL_JOBS_PYTHON:-python3}"

log() {
  printf '[local-jobs] %s\n' "$*"
}

log_err() {
  printf '[local-jobs] ERROR: %s\n' "$*" >&2
}

die() {
  log_err "$*"
  exit "${LOCAL_JOBS_EXIT_CODE:-1}"
}

expand_path() {
  local raw="$1"
  case "$raw" in
    "~/"*) printf '%s\n' "${raw/#\~/$HOME}" ;;
    *) printf '%s\n' "$("$LOCAL_JOBS_PYTHON" -c 'import os,sys; print(os.path.expanduser(sys.argv[1]))' "$raw")" ;;
  esac
}

check_python_deps() {
  command -v "$LOCAL_JOBS_PYTHON" >/dev/null 2>&1 || die "python3 is required for local-jobs (set LOCAL_JOBS_PYTHON to override)"
  "$LOCAL_JOBS_PYTHON" -c 'import yaml' >/dev/null 2>&1 || die "PyYAML is required for local-jobs under $LOCAL_JOBS_PYTHON (install PyYAML, then retry)"
}

registry_py() {
  check_python_deps
  LOCAL_JOBS_REGISTRY="$LOCAL_JOBS_REGISTRY" \
  LOCAL_JOBS_HOME="$LOCAL_JOBS_HOME" \
  LOCAL_JOBS_STATE="$LOCAL_JOBS_STATE" \
  LOCAL_JOBS_OVERLAY_DIR="$LOCAL_JOBS_OVERLAY_DIR" \
    "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/registry.py" "$@"
}

local_jobs_label_root() {
  check_python_deps
  LOCAL_JOBS_STATE="$LOCAL_JOBS_STATE" "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/settings.py" label-root
}

local_jobs_label() {
  check_python_deps
  LOCAL_JOBS_STATE="$LOCAL_JOBS_STATE" "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/settings.py" label "$@"
}

handler_for_type() {
  local job_type="$1"
  registry_py handler-path --type "$job_type"
}

resolve_instance_type() {
  local instance_id="$1"
  registry_py instance-type --id "$instance_id"
}

require_handler() {
  local job_type="$1"
  local handler
  handler="$(handler_for_type "$job_type")"
  [[ -x "$handler" ]] || die "handler not executable for type $job_type: $handler"
  printf '%s\n' "$handler"
}

# Cursor only renders `.canvas.tsx` files under `~/.cursor/projects/<slug>/canvases/`.
# Map a workspace root to that slug. Cursor hyphenates dots in usernames
# (e.g. `/Users/sample.user/work/foo` → `Users-sample-user-work-foo`, not
# `Users-sample.user-work-foo`). Prefer an existing project dir when present.
cursor_project_slug() {
  local root="${1:-}"
  root="${root%/}"
  [[ -n "$root" && "$root" != "/" ]] || return 1
  local projects="${LOCAL_JOBS_CURSOR_PROJECTS_DIR:-$HOME/.cursor/projects}"
  local path_slug hyphen_slug
  path_slug="${root#/}"
  path_slug="${path_slug//\//-}"
  hyphen_slug="${path_slug//./-}"
  if [[ -d "$projects/$hyphen_slug" ]]; then
    printf '%s\n' "$hyphen_slug"
  elif [[ -d "$projects/$path_slug" ]]; then
    printf '%s\n' "$path_slug"
  else
    printf '%s\n' "$hyphen_slug"
  fi
}

# Print one workspace canvases dir when discoverable. Override with
# LOCAL_JOBS_CURSOR_CANVAS_DIR or LOCAL_JOBS_CURSOR_WORKSPACE.
cursor_workspace_canvas_dir() {
  if [[ -n "${LOCAL_JOBS_CURSOR_CANVAS_DIR:-}" ]]; then
    printf '%s\n' "$LOCAL_JOBS_CURSOR_CANVAS_DIR"
    return 0
  fi
  local root="${LOCAL_JOBS_CURSOR_WORKSPACE:-}"
  if [[ -z "$root" ]] && git rev-parse --show-toplevel &>/dev/null 2>&1; then
    root="$(git rev-parse --show-toplevel)"
  fi
  [[ -n "$root" ]] || return 1
  local slug dir
  slug="$(cursor_project_slug "$root")" || return 1
  local projects="${LOCAL_JOBS_CURSOR_PROJECTS_DIR:-$HOME/.cursor/projects}"
  dir="$projects/$slug/canvases"
  mkdir -p "$dir"
  printf '%s\n' "$dir"
}

# All Cursor workspace canvas dirs (for bridge WatchPaths / sidecar discovery).
cursor_workspace_canvas_dirs() {
  local projects="${LOCAL_JOBS_CURSOR_PROJECTS_DIR:-$HOME/.cursor/projects}" slug dir
  if [[ -n "${LOCAL_JOBS_CURSOR_CANVAS_DIR:-}" ]]; then
    printf '%s\n' "$LOCAL_JOBS_CURSOR_CANVAS_DIR"
  fi
  if [[ -d "$projects" ]]; then
    for dir in "$projects"/*/canvases; do
      [[ -d "$dir" ]] || continue
      printf '%s\n' "$dir"
    done
  fi
}
