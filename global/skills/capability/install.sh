#!/usr/bin/env bash
# install.sh — generic Flavor-1 install for the `capability` playbook skill.
#
# Flavor-1 = homegrown master: this in-repo working copy is the source of truth. There is no
# upstream provenance to refresh against (unlike a Flavor-2 snapshot), so this installer only
# (re)asserts the per-tool symlink(s) into ~/.<tool>/skills, idempotently, for each tool listed in
# meta.yml `expose:` (space- or comma-separated cursor/claude/codex; falls back to cursor if unset).
# Conservative: never clobbers a real (non-symlink) path; relinks an existing wrong symlink.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"

log() { printf '[install:%s] %s\n' "$NAME" "$*"; }

# Flat `key: value` reader; require a space before an inline # so values keep a literal '#'.
meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) log "WARN: unknown arg '$arg' (ignored)" ;;
  esac
done

# Assert per-tool symlinks for each tool in `expose:` (fallback: cursor). Tolerate `[a, b]` or
# `a b` formatting by stripping brackets/commas.
expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[],' )"
[ -n "$expose" ] || expose="cursor"

link_tool() {
  local tool="$1" base link
  case "$tool" in
    cursor) base="$HOME/.cursor/skills" ;;
    claude) base="$HOME/.claude/skills" ;;
    codex)  base="$HOME/.codex/skills" ;;
    *) log "WARN: unknown expose tool '$tool' (skipped)"; return 0 ;;
  esac
  link="$base/$NAME"
  mkdir -p "$base"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$SRC" ]; then return 0; fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then log "skip $link (real path; not clobbering)"; return 0; fi
  rm -f "$link"
  ln -s "$SRC" "$link"
  log "linked $link -> $SRC"
}

for tool in $expose; do link_tool "$tool"; done
