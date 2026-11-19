#!/usr/bin/env bash
# install.sh - Flavor-1 install for the local-jobs global skill.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"

log() { printf '[install:%s] %s
' "$NAME" "$*"; }

need_python() {
  local py="${LOCAL_JOBS_PYTHON:-python3}"
  command -v "$py" >/dev/null 2>&1 || { log "ERROR: python3 is required for local-jobs (set LOCAL_JOBS_PYTHON to override)"; exit 2; }
  "$py" -c 'import yaml' >/dev/null 2>&1 || {
    log "ERROR: PyYAML is required for local-jobs under $py. Install PyYAML, then retry."
    exit 2
  }
}

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

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

need_python
expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[],' )"
[ -n "$expose" ] || expose="cursor"
for tool in $expose; do link_tool "$tool"; done
chmod +x "$SRC/scripts/local-jobs.sh" "$SRC/bin"/*.sh "$SRC/handlers"/*.sh "$SRC/backends/incremental-git-fetch"/*.sh 2>/dev/null || true
chmod +x "$SRC/lib/canvas_emit.py" 2>/dev/null || true
log "done"
