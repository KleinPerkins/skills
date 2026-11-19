#!/bin/bash
# Rollback-safe local-jobs entrypoint: old descriptors fail closed instead of invoking an old
# runtime that does not understand the maintenance event.
set -u

SCRIPT_DIR="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || exit 0
CAP_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)" || exit 0
DESCRIPTOR="${KEEP_AWAKE_DESCRIPTOR:-$CAP_DIR/plugin.json}"
RUNTIME="$CAP_DIR/scripts/hooks/keep-awake-refill.sh"
PYTHON="${KEEP_AWAKE_PYTHON:-/usr/bin/python3}"

[ -x "$RUNTIME" ] || exit 0
[ -x "$PYTHON" ] || exit 0

"$PYTHON" - "$DESCRIPTOR" >/dev/null 2>&1 <<'PY' || exit 0
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    descriptor = json.load(fh)

enabled = descriptor.get("maintenanceEnabled")
interval = descriptor.get("maintenanceIntervalSeconds")
window = descriptor.get("activityWindowSeconds")
if enabled is not True:
    raise SystemExit(1)
if not isinstance(interval, int) or isinstance(interval, bool) or interval < 60:
    raise SystemExit(1)
if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
    raise SystemExit(1)
PY

exec "$RUNTIME" maintenance </dev/null
