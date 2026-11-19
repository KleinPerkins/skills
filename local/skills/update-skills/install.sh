#!/usr/bin/env bash
# install.sh — Flavor-1 LOCAL skill: tool-targeted symlink into ~/.cursor/skills + ~/.claude/skills.
#
# Local (not global) is the operative scope: this skill is NOT enrolled in the orchestrator's
# managed-items.txt and MUST stay machine-local. Tool exposure is intentionally narrow — only
# the tools where the skill is meaningful (matches the curated lists in
# ~/dev/capabilities/verify-capabilities.sh). Adding it to ~/.codex/skills would create a stale
# duplicate the per-tool bootstrap would refuse to re-link.
#
# Idempotent + conservative: never clobbers a real (non-symlink) path. WS-1 manifest contract.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"
for tool in .cursor .claude; do
  d="$HOME/$tool/skills"; link="$d/$NAME"
  mkdir -p "$d"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$SRC" ]; then continue; fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then echo "[install] skip $link (real path; not clobbering)"; continue; fi
  rm -f "$link"; ln -s "$SRC" "$link"; echo "[install] linked $link -> $SRC"
done
