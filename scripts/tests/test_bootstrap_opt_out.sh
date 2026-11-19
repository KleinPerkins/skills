#!/usr/bin/env bash
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
pass() { printf '  PASS %s\n' "$1"; }
fail_case() { printf '  FAIL %s\n' "$1"; fail=1; }

HOME_ROOT="$TMP/home"
REGISTRY="$TMP/capability-local.yml"
PLUGIN_DIR="$REPO/global/plugins/keep-awake"
PROJECTION="$TMP/repo"
mkdir -p "$PROJECTION/global/plugins" "$PROJECTION/scripts" "$HOME_ROOT/.cursor/skills"
cp "$REPO/bootstrap.sh" "$PROJECTION/bootstrap.sh"
cp "$REPO/scripts/capability-local.py" "$PROJECTION/scripts/capability-local.py"
cp "$REPO/scripts/capability_meta.py" "$PROJECTION/scripts/capability_meta.py"
mkdir -p "$PROJECTION/scripts/tests"
cp -R "$PLUGIN_DIR" "$PROJECTION/global/plugins/keep-awake"
# Exercise the opt-out gate on an installable plugin, independent of keep-awake's live expose value.
meta="$(awk '/^expose:/ { print "expose: cursor"; next } { print }' "$PROJECTION/global/plugins/keep-awake/meta.yml")"
printf '%s\n' "$meta" > "$PROJECTION/global/plugins/keep-awake/meta.yml"
: > "$PROJECTION/.git"

printf 'schema: kp-capability-local/v1\nopt_out:\n  - keep-awake\n' > "$REGISTRY"

output="$(
  HOME="$HOME_ROOT" \
  CAPABILITY_LOCAL_REGISTRY="$REGISTRY" \
  bash "$PROJECTION/bootstrap.sh" --reconcile --dry-run 2>&1
)"
if printf '%s\n' "$output" | grep -q 'SKIP   keep-awake (plugin opt-out)'; then
  pass "reconcile dry-run skips opted-out keep-awake"
else
  fail_case "reconcile dry-run skips opted-out keep-awake"
  printf '%s\n' "$output"
fi
if printf '%s\n' "$output" | grep -q 'APPLY  keep-awake'; then
  fail_case "reconcile dry-run must not apply opted-out keep-awake"
else
  pass "reconcile dry-run does not apply opted-out keep-awake"
fi

reset_output="$(
  HOME="$HOME_ROOT" \
  CAPABILITY_LOCAL_REGISTRY="$REGISTRY" \
  bash "$PROJECTION/bootstrap.sh" --reconcile --reset-local-config --dry-run 2>&1
)"
if printf '%s\n' "$reset_output" | grep -q 'reset  machine-local capability opt-out registry'; then
  pass "reset-local-config logs registry reset"
else
  fail_case "reset-local-config logs registry reset"
fi
if [ -f "$REGISTRY" ]; then
  pass "reset-local-config dry-run preserves registry file until apply"
else
  fail_case "reset-local-config dry-run preserves registry file until apply"
fi
if printf '%s\n' "$reset_output" | grep -q 'APPLY  keep-awake'; then
  pass "reset-local-config allows plugin apply"
else
  fail_case "reset-local-config allows plugin apply"
  printf '%s\n' "$reset_output"
fi

exit "$fail"
