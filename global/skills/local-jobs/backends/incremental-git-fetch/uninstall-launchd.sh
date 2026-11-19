#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

REPO_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      shift
      REPO_FILTER="${1:-}"
      [[ -n "$REPO_FILTER" ]] || die "--repo requires an id"
      ;;
    -h|--help)
      printf 'Usage: uninstall-launchd.sh [--repo <id>]\n'
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
  shift
done

global_json="$(config_py global)"
default_label="${LOCAL_JOBS_IGF_LABEL:-$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/registry.py" label-root).git-fetch}"

if [[ -n "$REPO_FILTER" ]]; then
  LABEL="${default_label}.${REPO_FILTER}"
else
  LABEL="$default_label"
fi

PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ ! -f "$PLIST_PATH" ]]; then
  log "Launch agent not installed: $PLIST_PATH"
  exit 0
fi

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
log "Removed launch agent: $PLIST_PATH"
