#!/usr/bin/env bash
# test_sibling_assets.sh — regression guard for kp-capability/v1 declared sibling assets (ADR 0002).
#
# Proves, in a hermetic sandbox HOME, that a declared `assets:` entry (model-tiers.json) is:
#   * co-installed beside the rule payload as a symlink resolving to source,
#   * idempotent on re-run and prune-safe under --reconcile,
#   * verified by both install.sh --doctor and bootstrap --doctor (fail when the link is missing),
#   * a HARD failure at install/doctor time when the declared asset is absent from source.
#
# The test is self-contained: it builds a fake DURABLE primary (a real non-worktree git repo, NOT
# under ~/.cursor/worktrees) so bootstrap.sh resolves REPO_DIR to it and reads OUR meta/install.sh.
# Removing the Task-2 co-install logic turns the first assertion RED.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
cd "$REPO"

fail=0
pass() { printf 'PASS  %s\n' "$1"; }
fail_case() { printf 'FAIL  %s\n' "$1"; fail=1; }

RULE_SRC="global/rules/subagent-orchestration"
ASSET="model-tiers.json"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# make_primary <dir> <with_asset:1|0> — scaffold a fake durable primary carrying the rule.
make_primary() {
  local dir="$1" with_asset="$2" cap
  cap="$dir/global/rules/subagent-orchestration"
  mkdir -p "$cap"
  git -C "$dir" init -q
  cp bootstrap.sh "$dir/bootstrap.sh"
  mkdir -p "$dir/scripts"
  cp scripts/capability_meta.py "$dir/scripts/capability_meta.py"
  cp "$RULE_SRC/meta.yml" "$RULE_SRC/subagent-orchestration.mdc" "$RULE_SRC/install.sh" "$cap/"
  chmod +x "$cap/install.sh"
  [ "$with_asset" = 1 ] && cp "$RULE_SRC/$ASSET" "$cap/"
  return 0
}

# rc_of <cmd...> — run a command with set -e disabled for the call and echo its exit code.
rc_of() {
  local rc=0
  "$@" >/dev/null 2>&1 || rc=$?
  printf '%s' "$rc"
}

# ---- Case A: declared asset present in source ----
PRIMARY="$WORK/primary"; SBOX="$WORK/home"
make_primary "$PRIMARY" 1
mkdir -p "$SBOX"
LINK="$SBOX/.cursor/rules/$ASSET"
SRC_ASSET="$PRIMARY/global/rules/subagent-orchestration/$ASSET"
CAP_INSTALL="$PRIMARY/global/rules/subagent-orchestration/install.sh"

if [ "$(rc_of env HOME="$SBOX" bash "$PRIMARY/bootstrap.sh" --install)" = 0 ]; then
  pass "bootstrap --install succeeds with the declared asset present"
else
  fail_case "bootstrap --install exited non-zero with the declared asset present"
fi

if [ -L "$LINK" ] && [ "$LINK" -ef "$SRC_ASSET" ]; then
  pass "bootstrap co-installs $ASSET as a symlink resolving to source"
else
  fail_case "bootstrap did NOT co-install $ASSET (regression: co-install logic missing)"
fi

if [ "$(rc_of env HOME="$SBOX" bash "$PRIMARY/bootstrap.sh" --install)" = 0 ] && [ -L "$LINK" ]; then
  pass "second --install run is idempotent (asset link intact)"
else
  fail_case "second --install run was not idempotent"
fi

if [ "$(rc_of env HOME="$SBOX" bash "$PRIMARY/bootstrap.sh" --reconcile)" = 0 ] && [ -L "$LINK" ]; then
  pass "--reconcile does not prune the co-installed asset"
else
  fail_case "--reconcile pruned the asset or exited non-zero"
fi

if [ "$(rc_of env HOME="$SBOX" bash "$CAP_INSTALL" --doctor)" = 0 ]; then
  pass "install.sh --doctor OK with the asset installed"
else
  fail_case "install.sh --doctor failed with the asset installed"
fi

if [ "$(rc_of env HOME="$SBOX" bash "$PRIMARY/bootstrap.sh" --doctor)" = 0 ]; then
  pass "bootstrap --doctor OK with the asset installed"
else
  fail_case "bootstrap --doctor failed with the asset installed"
fi

# Doctors must detect a MISSING installed sibling.
rm -f "$LINK"
if [ "$(rc_of env HOME="$SBOX" bash "$CAP_INSTALL" --doctor)" != 0 ]; then
  pass "install.sh --doctor fails when the installed asset link is missing"
else
  fail_case "install.sh --doctor passed with the installed asset link missing"
fi
if [ "$(rc_of env HOME="$SBOX" bash "$PRIMARY/bootstrap.sh" --doctor)" != 0 ]; then
  pass "bootstrap --doctor fails when the installed asset link is missing"
else
  fail_case "bootstrap --doctor passed with the installed asset link missing"
fi

# ---- Case B: declared asset absent from source -> hard failure ----
PRIMARY2="$WORK/primary2"; SBOX2="$WORK/home2"
make_primary "$PRIMARY2" 0
mkdir -p "$SBOX2"
CAP_INSTALL2="$PRIMARY2/global/rules/subagent-orchestration/install.sh"
if [ "$(rc_of env HOME="$SBOX2" bash "$PRIMARY2/bootstrap.sh" --install)" != 0 ]; then
  pass "bootstrap --install fails when a declared asset is missing from source"
else
  fail_case "bootstrap --install passed with a source-missing declared asset"
fi
if [ "$(rc_of env HOME="$SBOX2" bash "$CAP_INSTALL2" --doctor)" != 0 ]; then
  pass "install.sh --doctor fails when a declared asset is missing from source"
else
  fail_case "install.sh --doctor passed with a source-missing declared asset"
fi

[ "$fail" -eq 0 ]
