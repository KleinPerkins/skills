#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
cd "$REPO"

fail=0
pass() { printf 'PASS  %s\n' "$1"; }
fail_case() { printf 'FAIL  %s\n' "$1"; fail=1; }

expect_digest_ok() {
  local meta="$1" expected="$2" label="$3" output rc
  if output="$(bash .github/scripts/eco-lock.sh digest "$meta")"; then
    rc=0
  else
    rc=$?
  fi
  if [ "$rc" -ne 0 ]; then
    fail_case "$label returned rc=$rc"
    return
  fi
  if [ "$output" = "$expected" ]; then
    pass "$label"
  else
    fail_case "$label produced $output (expected $expected)"
  fi
}

expect_digest_ok \
  "global/skills/plan-refine/meta.yml" \
  "fe719f1315ce5d82ac6b57d48179ae7353b872cf675083d416b6356fdd227c36" \
  "digest succeeds without descriptor_ref"

expect_digest_ok \
  "global/plugins/keep-awake/meta.yml" \
  "b19301cc19ab8d6779aaf9823fd9f58740faf2b3967cdb642959fa7dd35229d4" \
  "digest succeeds with descriptor_ref"

[ "$fail" -eq 0 ]
