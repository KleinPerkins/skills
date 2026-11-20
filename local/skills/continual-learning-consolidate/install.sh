#!/usr/bin/env bash
# Install the git-free consolidator into a durable machine-local runtime.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RUNTIME_ROOT="${CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME:-$HOME/.local/share/continual-learning-consolidate}"
BIN_DIR="${CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR:-$HOME/.local/bin}"
BIN="$BIN_DIR/continual-learning-consolidate"
JOB_ID="continual-learning-consolidate"
LOCAL_JOBS="${LOCAL_JOBS_CLI:-$HOME/.cursor/skills/local-jobs/scripts/local-jobs.sh}"
SCHEDULE=1
INSTALL_ARGS=(--source "$SKILL_DIR" --runtime "$RUNTIME_ROOT" --bin-dir "$BIN_DIR")

usage() {
  printf 'usage: install.sh [--no-schedule] [--policy PATH --expected-policy-sha256 HASH|absent] [--expected-current HASH|absent] [--rollback-to HASH]\n'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-schedule) SCHEDULE=0 ;;
    --policy|--expected-policy-sha256|--expected-current|--rollback-to)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      [ "$1" != "--rollback-to" ] || SCHEDULE=0
      INSTALL_ARGS+=("$1" "$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 -B "$SKILL_DIR/scripts/install_runtime.py" "${INSTALL_ARGS[@]}"

if [ "$SCHEDULE" = 0 ]; then
  exit 0
fi
if [ ! -x "$LOCAL_JOBS" ]; then
  printf 'continual-learning-consolidate: local-jobs unavailable at %s\n' "$LOCAL_JOBS" >&2
  exit 1
fi

if "$LOCAL_JOBS" explain-job --type command --id "$JOB_ID" >/dev/null 2>&1; then
  printf 'local-jobs: %s already present\n' "$JOB_ID"
else
  "$LOCAL_JOBS" add-job \
    --type command \
    --id "$JOB_ID" \
    --program "$BIN" \
    --schedule 09:00 \
    --dry-run
  "$LOCAL_JOBS" add-job \
    --type command \
    --id "$JOB_ID" \
    --program "$BIN" \
    --schedule 09:00
fi
"$LOCAL_JOBS" doctor --plain
