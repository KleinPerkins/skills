#!/usr/bin/env bash
# install.sh — generic Flavor-2 SNAPSHOT install (KleinPerkins/skills global tier).
#
# This skill is a verbatim, provenance-pinned snapshot of an upstream skill
# (github.com/anthropics/skills @ the SHA in meta.yml:provenance_ref). The in-repo
# working copy is the source of truth for what bootstrap exposes locally and what the
# ecosystem orchestrator vendors downstream.
#
# Default mode: idempotently (re)assert the per-tool symlink(s) into ~/.<tool>/skills,
# for each tool listed in meta.yml `expose:` (space-separated cursor/claude/codex;
# falls back to cursor if unset). Conservative: never clobbers a real (non-symlink) path.
#
# --refresh: SHA-safe, read-only drift report. Fetches the pinned commit from upstream
# and diffs it against the tracked snapshot, EXCLUDING our local-only files
# (meta.yml, install.sh). It does NOT mutate the snapshot — reconciliation is manual
# when upstream advances. Uses fetch-by-SHA (NOT `clone --branch <sha>`, which fails on a
# commit, and NOT a plain `--depth 1` clone + `checkout <sha>`, which breaks once the
# upstream default-branch tip moves past the pinned commit).
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

REFRESH=0
for arg in "$@"; do
  case "$arg" in
    --refresh) REFRESH=1 ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) log "WARN: unknown arg '$arg' (ignored)" ;;
  esac
done

if [ "$REFRESH" -eq 1 ]; then
  src_url="$(meta_get "$SRC/meta.yml" provenance_source)"
  ref="$(meta_get "$SRC/meta.yml" provenance_ref)"
  : "${src_url:?provenance_source missing from meta.yml}"
  : "${ref:?provenance_ref missing from meta.yml}"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  log "fetching $src_url @ $ref (read-only drift report)"
  git init -q "$tmp/up"
  git -C "$tmp/up" remote add origin "https://$src_url.git"
  if ! git -C "$tmp/up" fetch -q --depth 1 origin "$ref" 2>/dev/null; then
    log "ERROR: could not fetch $src_url @ $ref (no network or commit gone?)"; exit 2
  fi
  git -C "$tmp/up" checkout -q FETCH_HEAD
  up_skill="$tmp/up/skills/$NAME"
  [ -d "$up_skill" ] || { log "ERROR: upstream layout changed; skills/$NAME not found at $ref"; exit 2; }
  log "drift vs upstream/skills/$NAME (excluding meta.yml, install.sh):"
  drift_lines="$(diff -r --brief "$up_skill" "$SRC" 2>/dev/null \
    | grep -Ev '(meta\.yml|install\.sh)$' || true)"
  if [ -z "$drift_lines" ]; then
    log "(in sync with upstream modulo local files)"
    exit 0
  fi
  printf '%s\n' "$drift_lines"
  log "drift detected. To reconcile: review the diffs above and update the snapshot manually."
  exit 0
fi

# Default mode: assert per-tool symlinks for each tool in `expose:` (fallback: cursor).
expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[]' | tr ',' ' ')"
[ -n "$expose" ] || expose="cursor"
case " $expose " in
  *" none "*) log "expose: none — not installed locally (no links created)"; exit 0 ;;
esac

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
