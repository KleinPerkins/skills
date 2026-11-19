#!/usr/bin/env bash
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL="$(cd "$SELF/.." && pwd)"
fail=0

run_case() {
  local name="$1"
  shift
  printf '\n[%s]\n' "$name"
  "$@" || fail=1
}

run_case "unit, contract, authority, acceptance, and fault tests" \
  python3 -m unittest discover -s "$SELF" -p 'test_*.py' -v
run_case "isolated bootstrap and installer tests" \
  bash "$SELF/test_bootstrap.sh"
run_case "offline deterministic marker fixture (not an agent benchmark)" \
  python3 "$SELF/test_benchmark.py"
run_case "helper command smoke" \
  python3 "$SKILL/scripts/swarm_cli.py" risk \
    --impact 4 --likelihood 4 --exposure 4 --irreversibility 4

if [ "$fail" -eq 0 ]; then
  printf '\nswarm tests: OK\n'
else
  printf '\nswarm tests: FAILED\n' >&2
  exit 1
fi
