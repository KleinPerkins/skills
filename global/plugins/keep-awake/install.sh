#!/usr/bin/env bash
# install.sh — lifecycle dispatcher for the Cursor keep-awake plugin.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
MANAGER="$DIR/scripts/manage.py"

usage() {
  cat <<'EOF'
usage: install.sh --apply|--doctor|--repair|--uninstall

  --apply      Reconcile Cursor heartbeat hooks and the bounded maintenance timer.
  --doctor     Inspect hooks, timer, leases, backend, and assertions without changing them.
  --repair     Reconcile hooks/timer, repair owned state, then re-check.
  --uninstall Fence runtime work, then remove the timer, hooks, and owned state.
EOF
}

case "${1:-}" in
  --apply) action="apply" ;;
  --doctor) action="doctor" ;;
  --repair) action="repair" ;;
  --uninstall) action="uninstall" ;;
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
  *) printf 'unknown arg: %s\n' "$1" >&2; usage >&2; exit 2 ;;
esac

[ "$#" -eq 1 ] || { usage >&2; exit 2; }

# meta.yml `expose: none` is the tracked local-install authority (ADR 0007): apply/repair install
# nothing and doctor reports OFF. Uninstall stays available to remove any earlier runtime.
expose="$(awk -F'expose:[[:space:]]*' '/^expose:/{print $2; exit}' "$DIR/meta.yml" | tr -d '[]' | tr ',' ' ')"
case " $expose " in
  *" none "*)
    case "$action" in
      apply|repair) echo "keep-awake: expose: none — not installed locally (nothing applied)"; exit 0 ;;
      doctor) echo "ok   keep-awake: expose: none — not installed locally"; exit 0 ;;
    esac ;;
esac

exec python3 "$MANAGER" "$action"
