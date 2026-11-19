#!/usr/bin/env bash
# install.sh — local governor for the Cursor marketplace continual-learning plugin.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY="$DIR/scripts/continual_learning_plugin.py"

usage() {
  cat <<'EOF'
usage: install.sh [--apply|--doctor|--repair] [--cache-only]

  --apply      Retarget the plugin cache to agent-learnings.md (BLESSED/CONTAINABLE) or
               fail-closed neutralize the stop hook (INCOMPATIBLE), project the 50/1440 cadence,
               own the global git excludes, and add the sessionStart reapply hook.
  --doctor     Read-only health check; exits non-zero on drift or an unblessed/incompatible cache.
  --repair     Bounded reapply of the cache retarget + cadence + global excludes.
  --cache-only Only touch the marketplace cache projection and global excludes (skip sessionStart).
EOF
}

mode="apply"
cache_only=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) mode="apply" ;;
    --doctor) mode="doctor" ;;
    --repair) mode="repair" ;;
    --cache-only) cache_only=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

chmod +x "$PY" 2>/dev/null || true

case "$mode" in
  apply)
    if [ "$cache_only" = 1 ]; then exec python3 "$PY" apply --cache-only
    else exec python3 "$PY" apply
    fi ;;
  doctor)
    exec python3 "$PY" doctor ;;
  repair)
    if [ "$cache_only" = 1 ]; then exec python3 "$PY" repair --cache-only
    else exec python3 "$PY" repair
    fi ;;
esac
