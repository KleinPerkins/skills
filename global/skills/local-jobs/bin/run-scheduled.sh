#!/usr/bin/env bash
# launchd entrypoint for managed agents. Adds schedule jitter for the
# incremental-git-fetch *global* agent (no --id) and otherwise just dispatches
# the run so every scheduled execution lands in runs.jsonl.
#
# Usage: run-scheduled.sh --type <type> [--id <id>]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

job_type=""; has_id=0
forward=("$@")
i=0; argv=("$@")
while [[ $i -lt ${#argv[@]} ]]; do
  case "${argv[$i]}" in
    --type) i=$((i+1)); job_type="${argv[$i]}" ;;
    --id) has_id=1 ;;
  esac
  i=$((i+1))
done

# Global incremental-git-fetch agent applies runtime jitter across its window.
if [[ "$job_type" == "incremental-git-fetch" && "$has_id" -eq 0 ]]; then
  forward+=(--jitter)
fi

exec "$SCRIPT_DIR/dispatch-run.sh" "${forward[@]}"
