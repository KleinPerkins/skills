#!/usr/bin/env bash
# Hermetic installer smoke test. No network or scheduler mutation.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME="$TMP/runtime"
export CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR="$TMP/bin"
mkdir -p "$HOME"

bash "$SKILL_DIR/install.sh" --no-schedule >/dev/null
BIN="$CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR/continual-learning-consolidate"
[ -x "$BIN" ]
"$BIN" --help >/dev/null
[ -L "$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME/current" ]

# A second install is byte-addressed and must reuse the same release.
bash "$SKILL_DIR/install.sh" --no-schedule >/dev/null
releases=("$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME"/releases/*)
[ "${#releases[@]}" = 1 ]

# An UPDATE (changed source bytes) must publish a new release AND actually
# repoint current to it. 'current' is a symlink to a directory, so a naive
# "mv tmp current" descends into the old release instead of replacing the link,
# stranding the update. This asserts the repoint really happens.
WORK="$TMP/work-skill"
cp -R "$SKILL_DIR" "$WORK"
export CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME="$TMP/runtime2"
export CONTINUAL_LEARNING_CONSOLIDATE_BIN_DIR="$TMP/bin2"
bash "$WORK/install.sh" --no-schedule >/dev/null
before="$(readlink "$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME/current")"
printf '\n# update marker\n' >> "$WORK/scripts/lib/memory.py"
bash "$WORK/install.sh" --no-schedule >/dev/null
after="$(readlink "$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME/current")"
[ "$before" != "$after" ] || { printf 'FAIL: current did not repoint on update\n' >&2; exit 1; }
updated=("$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME"/releases/*)
[ "${#updated[@]}" = 2 ] || { printf 'FAIL: expected 2 releases after update\n' >&2; exit 1; }
[ -f "$CONTINUAL_LEARNING_CONSOLIDATE_RUNTIME/current/scripts/continual_learning_consolidate.py" ] \
  || { printf 'FAIL: current does not resolve to a valid release\n' >&2; exit 1; }

printf 'integration_install: PASS\n'
