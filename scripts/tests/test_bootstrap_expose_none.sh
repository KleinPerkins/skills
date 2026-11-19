#!/usr/bin/env bash
# expose: none (ADR 0007): fresh install creates no links and runs no installer, reconcile prunes
# links left by an earlier install, doctor reports OFF and passes, and the capability's own
# install.sh creates nothing.
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
pass() { printf '  PASS %s\n' "$1"; }
fail_case() { printf '  FAIL %s\n' "$1"; fail=1; }

HOME_ROOT="$TMP/home"
PROJECTION="$TMP/repo"
mkdir -p "$PROJECTION/global/skills" "$PROJECTION/local/skills" "$PROJECTION/global/plugins" \
  "$PROJECTION/scripts" "$HOME_ROOT"
cp "$REPO/bootstrap.sh" "$PROJECTION/bootstrap.sh"
cp "$REPO/scripts/capability-local.py" "$PROJECTION/scripts/capability-local.py"
cp "$REPO/scripts/capability_meta.py" "$PROJECTION/scripts/capability_meta.py"
cp -R "$REPO/global/skills/algorithmic-art" "$PROJECTION/global/skills/off-flavor2"
cp -R "$REPO/local/skills/session-close" "$PROJECTION/local/skills/off-local"
cp -R "$REPO/global/plugins/keep-awake" "$PROJECTION/global/plugins/off-plugin"
cp -R "$REPO/local/skills/session-close" "$PROJECTION/local/skills/on-local"
rm -rf "$PROJECTION/global/plugins/off-plugin/tests"
: > "$PROJECTION/.git"

set_meta() {
  local dir="$1" id="$2" expose="$3" out
  out="$(awk -v id="$id" -v ex="$expose" '
    /^id:/ { print "id: " id; next }
    /^expose:/ { print "expose: " ex; next }
    { print }' "$dir/meta.yml")"
  printf '%s\n' "$out" > "$dir/meta.yml"
}
set_meta "$PROJECTION/global/skills/off-flavor2" off-flavor2 none
set_meta "$PROJECTION/local/skills/off-local" off-local none
set_meta "$PROJECTION/global/plugins/off-plugin" off-plugin none
set_meta "$PROJECTION/local/skills/on-local" on-local "cursor claude"
for d in global/skills/off-flavor2 local/skills/off-local local/skills/on-local; do
  id="$(basename "$d")"
  out="$(awk -v id="$id" 'NR<=5 && /^name:/ { print "name: " id; next } { print }' "$PROJECTION/$d/SKILL.md")"
  printf '%s\n' "$out" > "$PROJECTION/$d/SKILL.md"
done

run_bootstrap() {
  HOME="$HOME_ROOT" CAPABILITY_LOCAL_REGISTRY="$TMP/capability-local.yml" \
    bash "$PROJECTION/bootstrap.sh" "$@" 2>&1
}

no_links_for() {
  local id="$1" p found=0
  for p in "$HOME_ROOT/.cursor/skills/$id" "$HOME_ROOT/.claude/skills/$id" "$HOME_ROOT/.codex/skills/$id"; do
    { [ -L "$p" ] || [ -e "$p" ]; } && found=1
  done
  [ "$found" = 0 ]
}

# 1) Fresh HOME install: no links and no installer for expose: none; normal skill still links.
out="$(run_bootstrap --reconcile)"
for id in off-flavor2 off-local off-plugin; do
  if no_links_for "$id"; then pass "fresh install creates no links for $id"; else fail_case "fresh install creates no links for $id"; fi
  if printf '%s\n' "$out" | grep -q "OFF    $id (expose: none"; then pass "fresh install reports $id OFF"; else fail_case "fresh install reports $id OFF"; fi
done
if printf '%s\n' "$out" | grep -Eq 'INSTALL off-flavor2|APPLY  off-plugin'; then
  fail_case "fresh install must not run installers for expose: none"
  printf '%s\n' "$out"
else
  pass "fresh install runs no installer for expose: none"
fi
if [ -L "$HOME_ROOT/.cursor/skills/on-local" ] && [ -L "$HOME_ROOT/.claude/skills/on-local" ]; then
  pass "normal skill still links per expose"
else
  fail_case "normal skill still links per expose"
  printf '%s\n' "$out"
fi

# 2) Links left by an earlier install are pruned by reconcile.
mkdir -p "$HOME_ROOT/.cursor/skills" "$HOME_ROOT/.claude/skills" "$HOME_ROOT/.codex/skills"
ln -s "$PROJECTION/global/skills/off-flavor2" "$HOME_ROOT/.codex/skills/off-flavor2"
ln -s "$PROJECTION/local/skills/off-local/" "$HOME_ROOT/.claude/skills/off-local"
ln -s "$PROJECTION/global/plugins/off-plugin/" "$HOME_ROOT/.cursor/skills/off-plugin"
doctor_stale="$(run_bootstrap --doctor)"
if printf '%s\n' "$doctor_stale" | grep -q 'still links an OFF capability'; then
  pass "doctor warns about leftover links before reconcile"
else
  fail_case "doctor warns about leftover links before reconcile"
  printf '%s\n' "$doctor_stale"
fi
out="$(run_bootstrap --reconcile)"
for id in off-flavor2 off-local off-plugin; do
  if no_links_for "$id"; then pass "reconcile prunes earlier links for $id"; else fail_case "reconcile prunes earlier links for $id"; printf '%s\n' "$out"; fi
done
if [ -L "$HOME_ROOT/.cursor/skills/on-local" ]; then pass "reconcile keeps normal skill link"; else fail_case "reconcile keeps normal skill link"; fi

# 3) Doctor treats expose: none as correct.
doctor_out="$(run_bootstrap --doctor)"; doctor_rc=$?
if [ "$doctor_rc" = 0 ]; then pass "doctor passes with expose: none"; else fail_case "doctor passes with expose: none (rc=$doctor_rc)"; printf '%s\n' "$doctor_out"; fi
if printf '%s\n' "$doctor_out" | grep -q 'still links an OFF capability'; then
  fail_case "doctor reports no leftover links after reconcile"
else
  pass "doctor reports no leftover links after reconcile"
fi

# 4) Each capability's own install.sh honours expose: none.
for d in global/skills/off-flavor2 local/skills/off-local; do
  inst_out="$(HOME="$HOME_ROOT" bash "$PROJECTION/$d/install.sh" 2>&1)"; inst_rc=$?
  id="$(basename "$d")"
  if [ "$inst_rc" = 0 ] && no_links_for "$id" && printf '%s\n' "$inst_out" | grep -q 'not installed locally'; then
    pass "$id install.sh creates no links"
  else
    fail_case "$id install.sh creates no links (rc=$inst_rc)"
    printf '%s\n' "$inst_out"
  fi
done
for action in apply repair doctor; do
  inst_out="$(HOME="$HOME_ROOT" bash "$PROJECTION/global/plugins/off-plugin/install.sh" "--$action" 2>&1)"; inst_rc=$?
  if [ "$inst_rc" = 0 ] && printf '%s\n' "$inst_out" | grep -q 'not installed locally'; then
    pass "plugin install.sh --$action installs nothing"
  else
    fail_case "plugin install.sh --$action installs nothing (rc=$inst_rc)"
    printf '%s\n' "$inst_out"
  fi
done

exit "$fail"
