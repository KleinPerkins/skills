#!/usr/bin/env bash
# Shared helpers for the incremental-git-fetch backend.
set -euo pipefail

IGF_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Framework root is two levels up: backends/incremental-git-fetch/ -> local-jobs/
LOCAL_JOBS_HOME="${LOCAL_JOBS_HOME:-$(cd -- "$IGF_HOME/../.." && pwd)}"

LOCAL_JOBS_STATE="${LOCAL_JOBS_STATE:-$HOME/.local-jobs}"
LOCAL_JOBS_IGF_CONFIG="${LOCAL_JOBS_IGF_CONFIG:-$LOCAL_JOBS_STATE/jobs/incremental-git-fetch.yml}"

_igf_python_with_yaml() {
  local py="${1:-python3}" candidate=""
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import yaml' >/dev/null 2>&1; then
    printf '%s\n' "$py"
    return 0
  fi
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$candidate" ]] && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ -z "${LOCAL_JOBS_PYTHON:-}" ]]; then
  LOCAL_JOBS_PYTHON="$(_igf_python_with_yaml python3 || printf '%s' python3)"
elif ! "$LOCAL_JOBS_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
  LOCAL_JOBS_PYTHON="$(_igf_python_with_yaml "$LOCAL_JOBS_PYTHON" || printf '%s' "$LOCAL_JOBS_PYTHON")"
fi

LOCAL_JOBS_IGF_LABEL="${LOCAL_JOBS_IGF_LABEL:-$(LOCAL_JOBS_STATE="$LOCAL_JOBS_STATE" "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/registry.py" label-root).git-fetch}"
LOCAL_JOBS_IGF_LOG_DIR="${LOCAL_JOBS_IGF_LOG_DIR:-$HOME/Library/Logs/local-jobs}"
LOCAL_JOBS_IGF_OUT_LOG="$LOCAL_JOBS_IGF_LOG_DIR/git-fetch.out.log"
LOCAL_JOBS_IGF_ERR_LOG="$LOCAL_JOBS_IGF_LOG_DIR/git-fetch.err.log"
LOCAL_JOBS_IGF_DEV_ROOT="${LOCAL_JOBS_IGF_DEV_ROOT:-}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*"
}

log_err() {
  log "$*" >&2
}

die() {
  log_err "ERROR: $*"
  exit "${LOCAL_JOBS_IGF_EXIT_CODE:-1}"
}

expand_path() {
  local raw="$1"
  case "$raw" in
    "~/"*) printf '%s\n' "${raw/#\~/$HOME}" ;;
    /*) printf '%s\n' "$raw" ;;
    *) printf '%s\n' "$LOCAL_JOBS_IGF_DEV_ROOT/$raw" ;;
  esac
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "$cmd is not available on PATH"
}

config_py() {
  LOCAL_JOBS_IGF_CONFIG="$LOCAL_JOBS_IGF_CONFIG" "$LOCAL_JOBS_PYTHON" "$IGF_HOME/config.py" "$@"
}

escape_xml() {
  /usr/bin/python3 -c 'import html, sys; print(html.escape(sys.argv[1], quote=True))' "$1"
}

recent_log_lines() {
  local path="$1"
  local lines="${2:-30}"

  if [[ ! -f "$path" ]]; then
    printf '%s does not exist\n' "$path"
    return 0
  fi

  "$LOCAL_JOBS_PYTHON" - "$path" "$lines" <<'PY'
from collections import deque
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = int(sys.argv[2])
for line in deque(path.open(errors="replace"), maxlen=lines):
    print(line, end="")
PY
}

launchctl_loaded() {
  [[ "${LOCAL_JOBS_LAUNCHD_DISABLE:-0}" == "1" ]] && return 1
  command -v launchctl >/dev/null 2>&1 || return 1
  launchctl print "gui/$(id -u)/${LOCAL_JOBS_IGF_LABEL}" >/dev/null 2>&1
}
