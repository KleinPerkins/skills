#!/usr/bin/env bash
# install.sh — idempotently expose the Flavor-1 save-game skill.
# Reference pattern: global/skills/plan-refine/install.sh (per-tool symlink + --doctor).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {line=$0; sub(/[[:space:]]+#.*$/,"",line);
     if (match(line,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=line; sub(/:.*$/,"",key);
       if (key==k) { value=line; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",value);
         gsub(/^"|"$/,"",value); print value; exit }
     }}' "$1"
}

DOCTOR=0
for arg in "$@"; do
  case "$arg" in
    --doctor) DOCTOR=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) printf '[install:%s] WARN: unknown arg %s (ignored)\n' "$NAME" "$arg" ;;
  esac
done

expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[],' )"
[ -n "$expose" ] || expose="cursor claude codex"

link_tool() {
  local tool="$1" base link
  case "$tool" in
    cursor) base="$HOME/.cursor/skills" ;;
    claude) base="$HOME/.claude/skills" ;;
    codex) base="$HOME/.codex/skills" ;;
    *) printf '[install:%s] WARN: unknown tool %s\n' "$NAME" "$tool"; return 0 ;;
  esac
  link="$base/$NAME"
  if [ "$DOCTOR" -eq 1 ]; then
    if [ -L "$link" ] && [ "$link" -ef "$SRC" ]; then
      printf '[install:%s] ok %s\n' "$NAME" "$link"
      return 0
    fi
    printf '[install:%s] FAIL expected link %s -> %s\n' "$NAME" "$link" "$SRC" >&2
    return 1
  fi
  mkdir -p "$base"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$SRC" ]; then return 0; fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    printf '[install:%s] skip %s (real path)\n' "$NAME" "$link"
    return 0
  fi
  rm -f "$link"
  ln -s "$SRC" "$link"
  printf '[install:%s] linked %s -> %s\n' "$NAME" "$link" "$SRC"
}

rc=0
for tool in $expose; do link_tool "$tool" || rc=1; done
exit "$rc"
