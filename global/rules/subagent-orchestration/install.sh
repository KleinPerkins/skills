#!/usr/bin/env bash
# install.sh — expose the global rule and its declared sibling assets to Cursor
# without clobbering a real file. Sibling assets are declared in meta.yml `assets:` (ADR 0002)
# and co-installed next to the rule payload in ~/.cursor/rules/.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RULES_DIR="$HOME/.cursor/rules"
PAYLOAD="$SRC/subagent-orchestration.mdc"
DOCTOR=0

for arg in "$@"; do
  case "$arg" in
    --doctor) DOCTOR=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) printf '[install:subagent-orchestration] WARN unknown arg %s\n' "$arg" ;;
  esac
done

[ -f "$PAYLOAD" ] || {
  printf '[install:subagent-orchestration] missing %s\n' "$PAYLOAD" >&2
  exit 2
}

# Build the src|dst install set: the rule payload plus each declared bare-filename asset
# (kp-capability/v1 optional `assets:`). The meta declaration is the single source of truth
# (quotes/brackets tolerated). A declared asset that is absent from source, or not a bare
# filename, is a HARD ERROR in BOTH install and doctor modes — matching bootstrap's doctor and
# the verify-skills source assertion, so a required sibling can never be silently skipped.
pairs="$PAYLOAD|$RULES_DIR/subagent-orchestration.mdc"
missing=0
assets="$(awk -F'assets:[[:space:]]*' '/^assets:/{print $2; exit}' "$SRC/meta.yml" 2>/dev/null | tr -d '[]' | tr -d '"' | tr -d "'" | tr ',' ' ')"
for asset in $assets; do
  [ -n "$asset" ] || continue
  case "$asset" in
    *..*|*/*) printf '[install:subagent-orchestration] FAIL asset must be a bare filename: %s\n' "$asset" >&2; missing=1; continue ;;
  esac
  if [ -f "$SRC/$asset" ]; then
    pairs="$pairs
$SRC/$asset|$RULES_DIR/$asset"
  else
    printf '[install:subagent-orchestration] FAIL declared asset missing in source: %s\n' "$SRC/$asset" >&2
    missing=1
  fi
done

if [ "$DOCTOR" -eq 1 ]; then
  err="$missing"
  while IFS='|' read -r src link; do
    [ -n "$src" ] || continue
    if [ -L "$link" ] && [ "$link" -ef "$src" ]; then
      printf '[install:subagent-orchestration] ok %s\n' "$link"
    else
      printf '[install:subagent-orchestration] FAIL expected %s -> %s\n' "$link" "$src" >&2
      err=1
    fi
  done <<EOF
$pairs
EOF
  exit "$err"
fi

mkdir -p "$RULES_DIR"
while IFS='|' read -r src link; do
  [ -n "$src" ] || continue
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then
    continue
  fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    printf '[install:subagent-orchestration] skip real path %s\n' "$link"
    continue
  fi
  rm -f "$link"
  ln -s "$src" "$link"
  printf '[install:subagent-orchestration] linked %s -> %s\n' "$link" "$src"
done <<EOF
$pairs
EOF
exit "$missing"
