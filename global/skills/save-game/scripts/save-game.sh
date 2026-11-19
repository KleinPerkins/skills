#!/usr/bin/env bash
# scripts/save-game.sh — thin wrapper around the engine.cli entrypoint.
# Style reference: global/skills/agent-route/scripts/agent-route.sh.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defend against a corrupted/partial install (missing engine/cli.py) with a
# clear, honest error instead of a raw ModuleNotFoundError/traceback.
if [ ! -f "$SKILL_DIR/engine/cli.py" ]; then
  printf 'save-game: engine.cli missing (expected %s/engine/cli.py) — reinstall this skill\n' "$SKILL_DIR" >&2
  exit 2
fi

export PYTHONPATH="${SKILL_DIR}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m engine.cli "$@"
