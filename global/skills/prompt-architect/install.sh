#!/usr/bin/env bash
# install.sh — Flavor-2 SNAPSHOT install for prompt-architect.
#
# This skill is a tracked snapshot of github.com/ckelsoe/prompt-architect @ v3.2.2 with
# local modifications: chaos-labs subscription frontmatter in SKILL.md, and a locally-
# authored MAP.md. The in-repo working copy is the source of truth for what bootstrap
# exposes locally and what the ecosystem orchestrator vendors downstream.
#
# Default mode: expose the snapshot according to meta.yml (~/dev/capabilities/bootstrap.sh
# already does this in pass-1; install.sh re-asserts it so the artifact is meaningful as a
# standalone install). Cursor and Codex are the declared hosts.
#
# --refresh: clone upstream at the pinned ref into a tmpdir and diff against the tracked
# snapshot, EXCLUDING our local-only files (meta.yml, install.sh, MAP.md). This is a
# read-only drift report — it does NOT mutate the snapshot, because that would clobber
# the chaos-labs frontmatter. Reconciliation is manual when upstream advances.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"

log() { printf '[install:%s] %s\n' "$NAME" "$*"; }

REFRESH=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --refresh) REFRESH=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) log "WARN: unknown arg '$arg' (ignored)" ;;
  esac
done

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

if [ "$REFRESH" -eq 1 ]; then
  [ "$DRY" -eq 0 ] || { log "ERROR: --refresh and --dry-run cannot be combined"; exit 2; }
  src_url="$(meta_get "$SRC/meta.yml" provenance_source)"
  ref="$(meta_get "$SRC/meta.yml" provenance_ref)"
  : "${src_url:?provenance_source missing from meta.yml}"
  : "${ref:?provenance_ref missing from meta.yml}"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  log "fetching $src_url @ $ref (read-only drift report)"
  if ! git clone --quiet --depth 1 --branch "$ref" "https://$src_url.git" "$tmp/up" 2>/dev/null; then
    log "ERROR: could not fetch $src_url@$ref (no network or ref gone?)"; exit 2
  fi
  up_skill="$tmp/up/skills/$NAME"
  [ -d "$up_skill" ] || { log "ERROR: upstream layout changed; $up_skill not found"; exit 2; }
  log "drift vs upstream/skills/$NAME (excluding meta.yml, install.sh, MAP.md):"
  # diff returns non-zero when differences are found; capture+filter without pipefail
  # short-circuiting so we can distinguish "drift after filtering" from "in sync."
  drift_lines="$(diff -r --brief "$up_skill" "$SRC" 2>/dev/null \
    | grep -Ev '(meta\.yml|install\.sh|MAP\.md)$' || true)"
  if [ -z "$drift_lines" ]; then
    log "(in sync with upstream modulo local files)"
    exit 0
  fi
  printf '%s\n' "$drift_lines"
  log "drift detected. To reconcile: review the diffs above and update SRC manually."
  exit 0
fi

# Metadata is the same exposure authority used by bootstrap.
expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[]' | tr ',' ' ')"
[ -n "$expose" ] || expose="cursor claude codex"
if [ "$expose" = none ]; then
  log "OFF (expose: none; not installed locally)"
  exit 0
fi
# Validate every token before creating any destination.
for tool in $expose; do
  case "$tool" in
    cursor|claude|codex) ;;
    *) log "ERROR: invalid exposure $tool"; exit 2 ;;
  esac
done

for tool in $expose; do
  link="$HOME/.$tool/skills/$NAME"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$SRC" ]; then continue; fi
  if [ -L "$link" ] || [ -e "$link" ]; then
    log "skip $link (existing path; ownership conflict)"
    continue
  fi
  if [ "$DRY" -eq 1 ]; then
    log "would link $link -> $SRC"
    continue
  fi
  mkdir -p "$(dirname "$link")"
  ln -s "$SRC" "$link"
  log "linked $link -> $SRC"
done
