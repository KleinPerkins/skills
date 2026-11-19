#!/bin/bash
set -euo pipefail
umask 077

PRACTICAL_ONLY=0
if [[ "${1:-}" == "--practical-only" ]]; then
  PRACTICAL_ONLY=1
  shift
fi
if [[ "$#" -ne 0 ]]; then
  printf 'usage: %s [--practical-only]\n' "$0" >&2
  exit 64
fi

CAPABILITY="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
. "$CAPABILITY/scripts/owned-cleanup.sh"
cd "$CAPABILITY"
SCRATCH="$(mktemp -d /private/tmp/dev-main-sync-core-tests.XXXXXX)"

cleanup() {
  local status="$1"
  trap - EXIT INT TERM
  if ! dms_reap_owned_root_helpers "$SCRATCH" m1-core-tests; then
    printf 'm1-core-tests: fixture child leaked before cleanup\n' >&2
    status=1
  fi
  dms_remove_owned_root "$SCRATCH" m1-core-tests || status=1
  exit "$status"
}
trap 'cleanup "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

BUILD_ARGS=(
  --package-path "$CAPABILITY"
  --scratch-path "$SCRATCH"
  --disable-index-store
  -Xswiftc -DSHADOW_SYNC_TESTING
)

swift build "${BUILD_ARGS[@]}" --product ShadowSync
swift build "${BUILD_ARGS[@]}" --product ShadowSyncSelfTest
BIN_DIR="$(swift build "${BUILD_ARGS[@]}" --show-bin-path)"
TEST_EXECUTABLE="$BIN_DIR/ShadowSync"
SELF_TEST_EXECUTABLE="$BIN_DIR/ShadowSyncSelfTest"
[ -x "$TEST_EXECUTABLE" ] || {
  printf 'm1-core-tests: testing executable is missing\n' >&2
  exit 1
}
[ -x "$SELF_TEST_EXECUTABLE" ] || {
  printf 'm1-core-tests: self-test executable is missing\n' >&2
  exit 1
}

printf 'm1-core-tests: running executable safety tests\n'
if [[ "$PRACTICAL_ONLY" -eq 1 ]]; then
  "$SELF_TEST_EXECUTABLE" \
    --app-executable "$TEST_EXECUTABLE" \
    --practical-only
  printf 'm1-core-tests: projecting live read-only inventory\n'
  "$SELF_TEST_EXECUTABLE" \
    --app-executable "$TEST_EXECUTABLE" \
    --live-diagnostic >"$SCRATCH/live-inventory.json"
  cat "$SCRATCH/live-inventory.json"
  python3 - "$SCRATCH/live-inventory.json" <<'PY'
import collections
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    rows = json.load(handle)
eligible = sum(row["eligible"] for row in rows)
blocked = len(rows) - eligible
reasons = collections.Counter(
    row.get("blockedReason", "eligible") for row in rows
)
print(
    "m1-core-tests: live inventory "
    f"{len(rows)} total, {eligible} eligible, {blocked} blocked; "
    + ", ".join(f"{key}={reasons[key]}" for key in sorted(reasons))
)
PY
else
  "$SELF_TEST_EXECUTABLE" --app-executable "$TEST_EXECUTABLE"
fi
printf 'm1-core-tests: executable safety tests passed\n'

# The selected Command Line Tools expose neither XCTest nor Swift Testing on Swift's default
# import path. Keep this target as an explicit compile gate with both runners disabled; the
# executable above is the no-dependency runtime test harness.
printf 'm1-core-tests: compiling SwiftPM test target without a runtime runner\n'
swift build "${BUILD_ARGS[@]}" --target ShadowSyncCompileTests
printf 'm1-core-tests: SwiftPM compile gate completed (zero registered runtime tests)\n'
