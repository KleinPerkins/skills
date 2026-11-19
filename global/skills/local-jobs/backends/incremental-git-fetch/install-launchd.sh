#!/usr/bin/env bash
# Install the incremental-git-fetch launchd agent(s) via the single chassis
# plist writer (lib/launchd.py) — no more hand-rolled plist heredoc. Builds a
# uniform spec (label, run-scheduled wrapper, WorkingDirectory, env, schedule,
# logs) and hands it to launchd.py install, which writes + (re)loads + verifies.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./common.sh
. "$SCRIPT_DIR/common.sh"

REPO_FILTER="${LOCAL_JOBS_IGF_INSTALL_REPO:-}"
RUN_SCHEDULED="$LOCAL_JOBS_HOME/bin/run-scheduled.sh"

usage() {
  cat <<USAGE
Usage: install-launchd.sh [--repo <id>]

Installs the user-level launchd agent for incremental-git-fetch.
  --repo <id>   Install a per-repo agent using that repo's schedule hour/minute
                (default: global agent at window_start_hour[:minute] + jitter)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) shift; REPO_FILTER="${1:-}"; [[ -n "$REPO_FILTER" ]] || die "--repo requires an id" ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

global_json="$(config_py global)"
default_label="${LOCAL_JOBS_IGF_LABEL:-$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/registry.py" label-root).git-fetch}"
log_dir_raw="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; print(json.load(sys.stdin).get("logging",{}).get("dir","~/Library/Logs/local-jobs"))' <<<"$global_json")"
LOG_DIR="$(expand_path "$log_dir_raw")"
OUT_LOG="$LOG_DIR/git-fetch.out.log"
ERR_LOG="$LOG_DIR/git-fetch.err.log"
mkdir -p "$LOG_DIR"

if [[ -n "$REPO_FILTER" ]]; then
  repo_json="$(config_py repo "$REPO_FILTER")"
  LABEL="${default_label}.${REPO_FILTER}"
  HOUR="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; s=json.load(sys.stdin).get("schedule") or {}; print(s.get("hour",""))' <<<"$repo_json")"
  MINUTE="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; s=json.load(sys.stdin).get("schedule") or {}; print(s.get("minute",0))' <<<"$repo_json")"
  [[ -n "$HOUR" ]] || die "repo $REPO_FILTER has no schedule.hour for per-repo install"
  PROGRAM_JSON="[\"$RUN_SCHEDULED\",\"--type\",\"incremental-git-fetch\",\"--id\",\"$REPO_FILTER\"]"
else
  LABEL="$default_label"
  HOUR="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; print(json.load(sys.stdin).get("launchd",{}).get("window_start_hour",18))' <<<"$global_json")"
  MINUTE="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; print(json.load(sys.stdin).get("launchd",{}).get("window_start_minute",0))' <<<"$global_json")"
  PROGRAM_JSON="[\"$RUN_SCHEDULED\",\"--type\",\"incremental-git-fetch\"]"
fi

[[ "$HOUR" =~ ^[0-9]+$ ]] || die "schedule hour must be numeric"
(( HOUR >= 0 && HOUR <= 23 )) || die "schedule hour must be 0-23"
[[ "$MINUTE" =~ ^[0-9]+$ ]] || die "schedule minute must be numeric"
(( MINUTE >= 0 && MINUTE <= 59 )) || die "schedule minute must be 0-59"

spec="$(LABEL="$LABEL" PROGRAM_JSON="$PROGRAM_JSON" WORKDIR="$LOCAL_JOBS_HOME" \
  IGF_CONFIG="$LOCAL_JOBS_IGF_CONFIG" HOME_DIR="$LOCAL_JOBS_HOME" HOUR="$HOUR" MINUTE="$MINUTE" \
  OUT_LOG="$OUT_LOG" ERR_LOG="$ERR_LOG" "$LOCAL_JOBS_PYTHON" - <<'PY'
import json, os
print(json.dumps({
    "label": os.environ["LABEL"],
    "program_args": json.loads(os.environ["PROGRAM_JSON"]),
    "working_directory": os.environ["WORKDIR"],
    "env": {"LOCAL_JOBS_IGF_CONFIG": os.environ["IGF_CONFIG"], "LOCAL_JOBS_HOME": os.environ["HOME_DIR"]},
    "schedule": {"hour": int(os.environ["HOUR"]), "minute": int(os.environ["MINUTE"])},
    "stdout": os.environ["OUT_LOG"],
    "stderr": os.environ["ERR_LOG"],
}))
PY
)"

result="$("$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/launchd.py" install --spec "$spec")"
ok="$("$LOCAL_JOBS_PYTHON" -c 'import json,os,sys; print(json.load(sys.stdin).get("ok"))' <<<"$result")"
log "Installed launch agent: $LABEL (schedule $(printf '%02d:%02d' "$HOUR" "$MINUTE") local, ok=$ok)"
[[ "$ok" == "True" ]] || log_err "launchd verify failed for $LABEL: $result"
