#!/usr/bin/env bash
# Install the git-free consolidator into a durable machine-local runtime.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
MAIN="$SKILL_DIR/scripts/continual_learning_consolidate.py"
MEMORY="$SKILL_DIR/scripts/lib/memory.py"
RUNTIME_ROOT="${CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME:-$HOME/.local/share/continual-learning-consolidate}"
BIN_DIR="${CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR:-$HOME/.local/bin}"
BIN="$BIN_DIR/continual-learning-consolidate"
JOB_ID="continual-learning-consolidate"
LOCAL_JOBS="${LOCAL_JOBS_CLI:-$HOME/.cursor/skills/local-jobs/scripts/local-jobs.sh}"
SCHEDULE=1

usage() {
  printf 'usage: install.sh [--no-schedule]\n'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-schedule) SCHEDULE=0 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for source in "$MAIN" "$MEMORY"; do
  [ -f "$source" ] || {
    printf 'continual-learning-consolidate: missing runtime source %s\n' "$source" >&2
    exit 1
  }
done

release_id="$(
  python3 - "$MAIN" "$MEMORY" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
for name in sys.argv[1:]:
    with open(name, "rb") as handle:
        digest.update(handle.read())
print(digest.hexdigest())
PY
)"
release="$RUNTIME_ROOT/releases/$release_id"
mkdir -p "$RUNTIME_ROOT/releases" "$BIN_DIR"

if [ ! -d "$release" ]; then
  stage="$(mktemp -d "$RUNTIME_ROOT/.stage.XXXXXX")"
  trap 'rm -rf "${stage:-}"' EXIT
  mkdir -p "$stage/scripts/lib"
  install -m 0755 "$MAIN" "$stage/scripts/continual_learning_consolidate.py"
  install -m 0644 "$MEMORY" "$stage/scripts/lib/memory.py"
  mv "$stage" "$release"
  stage=""
  trap - EXIT
fi

atomic_link() {
  local target="$1" destination="$2"
  if [ -e "$destination" ] && [ ! -L "$destination" ]; then
    printf 'continual-learning-consolidate: refusing to replace real path %s\n' "$destination" >&2
    return 1
  fi
  # -f -n: force-replace the symlink in place without dereferencing it. A plain
  # "mv tmp current" follows an existing current -> <dir> symlink and drops the
  # temp link INSIDE the old release dir, so updates never repoint and the job
  # keeps running stale code. -n (BSD -h alias / GNU --no-dereference) is
  # portable across macOS and Linux.
  ln -sfn "$target" "$destination"
}

atomic_link "$release" "$RUNTIME_ROOT/current"
atomic_link \
  "$RUNTIME_ROOT/current/scripts/continual_learning_consolidate.py" \
  "$BIN"
printf 'installed continual-learning-consolidate -> %s\n' "$release"

if [ "$SCHEDULE" = 0 ]; then
  exit 0
fi
if [ ! -x "$LOCAL_JOBS" ]; then
  printf 'continual-learning-consolidate: local-jobs unavailable at %s\n' "$LOCAL_JOBS" >&2
  exit 1
fi

if "$LOCAL_JOBS" explain-job --id "$JOB_ID" >/dev/null 2>&1; then
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
