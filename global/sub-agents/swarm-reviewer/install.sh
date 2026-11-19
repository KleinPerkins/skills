#!/usr/bin/env bash
# install.sh — idempotently expose one read-only swarm sub-agent.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"
PAYLOAD="$SRC/$NAME.md"
[ -f "$PAYLOAD" ] || { printf '[install:%s] missing %s\n' "$NAME" "$PAYLOAD" >&2; exit 2; }
DOCTOR=0
for arg in "$@"; do
  case "$arg" in
    --doctor) DOCTOR=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) printf '[install:%s] WARN: unknown arg %s\n' "$NAME" "$arg" ;;
  esac
done

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {line=$0; sub(/[[:space:]]+#.*$/,"",line);
     if (match(line,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=line; sub(/:.*$/,"",key);
       if (key==k) { value=line; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",value);
         gsub(/^"|"$/,"",value); print value; exit }
     }}' "$1"
}

expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[],' )"
[ -n "$expose" ] || expose="cursor"

for tool in $expose; do
  case "$tool" in
    cursor) base="$HOME/.cursor/agents" ;;
    claude) base="$HOME/.claude/agents" ;;
    codex) base="$HOME/.codex/agents" ;;
    *) printf '[install:%s] WARN: unknown tool %s\n' "$NAME" "$tool"; continue ;;
  esac
  link="$base/$NAME.md"
  if [ "$DOCTOR" -eq 1 ]; then
    if [ -L "$link" ] && [ "$link" -ef "$PAYLOAD" ]; then
      printf '[install:%s] ok %s\n' "$NAME" "$link"
      continue
    fi
    printf '[install:%s] FAIL expected link %s -> %s\n' "$NAME" "$link" "$PAYLOAD" >&2
    exit 1
  fi
  mkdir -p "$base"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$PAYLOAD" ]; then continue; fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    printf '[install:%s] skip %s (real path)\n' "$NAME" "$link"
    continue
  fi
  rm -f "$link"
  ln -s "$PAYLOAD" "$link"
  printf '[install:%s] linked %s -> %s\n' "$NAME" "$link" "$PAYLOAD"
done
