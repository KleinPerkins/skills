#!/usr/bin/env bash
# Hermetic generic conformance harness for the global local-jobs payload.
set -uo pipefail

REAL_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${LOCAL_JOBS_PYTHON:-python3}"
pass=0; fail=0
ok() { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail+1)); }
is_json() { "$PY" -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1; }

SB=""
cleanup() { [[ -n "$SB" && -d "$SB" ]] && rm -rf "$SB"; }
trap cleanup EXIT

setup_sandbox() {
  SB="$(mktemp -d "${TMPDIR:-/tmp}/lj-global.XXXXXX")"
  export LOCAL_JOBS_HOME="$SB"
  export LOCAL_JOBS_STATE="$SB/state"
  export LOCAL_JOBS_PYTHON="$PY"
  export LOCAL_JOBS_LAUNCHD_DISABLE=1
  export LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/agents"
  export LOCAL_JOBS_REGISTRY="$SB/config/registry.yml"
  export LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml"
  export LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml"
  export LOCAL_JOBS_IGF_DEV_ROOT="$SB/repos"
  export LOCAL_JOBS_IGF_LOG_DIR="$SB/logs"
  export HANDLER_LOG_DIR="$SB/logs"
  export LOCAL_JOBS_ACTOR="harness"

  # Missing-agent checks must stay hermetic on macOS as well as Linux. They
  # temporarily enable query logic, but must never inspect the operator's
  # launchd domain or install a real agent.
  mkdir -p "$SB/test-bin"
  cat > "$SB/test-bin/launchctl" <<'EOF'
#!/bin/sh
case "${1:-}" in
  print|list) exit 1 ;; # Synthetic absent agent.
  *) printf 'unexpected launchctl mutation in test fixture\n' >&2; exit 97 ;;
esac
EOF
  chmod +x "$SB/test-bin/launchctl"
  export PATH="$SB/test-bin:$PATH"

  mkdir -p "$SB/config" "$SB/state/jobs" "$SB/state/registry.d" "$SB/state/handlers" "$SB/agents" "$SB/logs" "$SB/repos" "$SB/handlers"
  ln -s "$REAL_HOME/lib" "$SB/lib"
  ln -s "$REAL_HOME/bin" "$SB/bin"
  ln -s "$REAL_HOME/backends" "$SB/backends"
  for h in "$REAL_HOME/handlers"/*.sh; do ln -s "$h" "$SB/handlers/$(basename "$h")"; done

  git init -q "$SB/repos/reference"
  git -C "$SB/repos/reference" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  git -C "$SB/repos/reference" remote add origin "$SB/repos/reference/.git" 2>/dev/null || true
  git -C "$SB/repos/reference" config branch.master.remote origin 2>/dev/null || true

  cp "$REAL_HOME/config/registry.yml" "$SB/config/registry.yml"
  mkdir -p "$SB/canvases"
  cp "$REAL_HOME/canvases/local-jobs-dashboard.template.tsx" "$SB/canvases/"
  printf 'schema: jobs/v1\nversion: 1\ninstances: []\n' > "$SB/state/jobs/command.yml"
  cat > "$SB/state/jobs/incremental-git-fetch.yml" <<'EOF'
schema: jobs/v1
version: 1
defaults: {remote: origin, branch: master, enabled: true, filter_blobs: true, ff_only_merge: true, schedule: inherit}
global:
  launchd: {window_start_hour: 18, window_end_hour: 24, use_jitter: true}
  logging: {dir: __LOG_DIR__}
repos:
- {id: reference, path: reference, remote: origin, branch: master, enabled: true, schedule: inherit}
EOF
  "$PY" - "$SB/state/jobs/incremental-git-fetch.yml" "$SB/repos" "$SB/logs" <<'PY'
from pathlib import Path
import sys
p, repos, logs = map(Path, sys.argv[1:])
s = p.read_text().replace('__LOG_DIR__', str(logs))
s = s.replace('global:\n', f'global:\n  dev_root: {repos}\n')
p.write_text(s)
PY
}

CLI() { "$SB/bin/local-jobs.sh" "$@"; }
H() { "$SB/handlers/$1.sh" "${@:2}"; }
write_canvas_run_request() {
  local sidecar="$1" id="$2" nonce="$3" at="${4:-now}" snapshot="${5:-now}"
  "$PY" - "$sidecar" "$id" "$nonce" "$at" "$snapshot" <<'PY'
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sidecar, job_id, nonce, at_arg, snapshot_arg = sys.argv[1:]
at = int(time.time() * 1000) if at_arg == "now" else int(at_arg)
snapshot = (
    datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if snapshot_arg == "now"
    else snapshot_arg
)
Path(sidecar).write_text(json.dumps({
    "dash.runRequest": {
        "jobId": job_id,
        "type": "canvas-type-is-ignored",
        "nonce": nonce,
        "at": at,
        "snapshotGeneratedAt": snapshot,
    }
}))
PY
}

write_canvas_control_request() {
  local sidecar="$1" id="$2" action="$3" nonce="$4" at="${5:-now}" snapshot="${6:-now}"
  "$PY" - "$sidecar" "$id" "$action" "$nonce" "$at" "$snapshot" <<'PY'
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sidecar, job_id, action, nonce, at_arg, snapshot_arg = sys.argv[1:]
at = int(time.time() * 1000) if at_arg == "now" else int(at_arg)
snapshot = (
    datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if snapshot_arg == "now"
    else snapshot_arg
)
Path(sidecar).write_text(json.dumps({
    "dash.controlRequest": {
        "jobId": job_id,
        "action": action,
        "nonce": nonce,
        "at": at,
        "snapshotGeneratedAt": snapshot,
    }
}))
PY
}

write_canvas_view_request() {
  local sidecar="$1" nonce="$2" at="${3:-now}" snapshot="${4:-now}"
  "$PY" - "$sidecar" "$nonce" "$at" "$snapshot" <<'PY'
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sidecar, nonce, at_arg, snapshot_arg = sys.argv[1:]
at = int(time.time() * 1000) if at_arg == "now" else int(at_arg)
snapshot = (
    datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if snapshot_arg == "now"
    else snapshot_arg
)
Path(sidecar).write_text(json.dumps({
    "dash.viewRequest": {
        "nonce": nonce,
        "at": at,
        "snapshotGeneratedAt": snapshot,
    }
}))
PY
}

copy_tracked_payload() {
  local dest="$1" repo rel
  repo="$(git -C "$REAL_HOME" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$repo" ]] || { cp -R "$REAL_HOME" "$dest"; return; }
  rel="$("$PY" - "$repo" "$REAL_HOME" <<'PY'
import os, sys
print(os.path.relpath(sys.argv[2], sys.argv[1]))
PY
)"
  mkdir -p "$dest"
  "$PY" - "$repo" "$rel" "$dest" <<'PY'
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
rel = Path(sys.argv[2])
dest = Path(sys.argv[3])
proc = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--", str(rel)], check=True, capture_output=True)
for raw in proc.stdout.split(b"\0"):
    if not raw:
        continue
    src_rel = Path(raw.decode())
    try:
        out_rel = src_rel.relative_to(rel)
    except ValueError:
        continue
    src = repo / src_rel
    out = dest / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
PY
}

test_base_registry() {
  echo "== base registry =="
  types="$("$PY" "$SB/lib/registry.py" job-types | tr '\n' ' ')"
  [[ "$types" == *"command"* && "$types" == *"incremental-git-fetch"* ]] && ok "generic types present" || bad "generic types missing: $types"
  [[ "$types" != *"archive"* ]] && ok "local-only archive type absent" || bad "local-only type leaked"
  root="$("$PY" "$SB/lib/registry.py" label-root)"
  [[ "$root" == "com.local-jobs" ]] && ok "neutral label root" || bad "label root=$root"
}

test_conformance() {
  echo "== ABI conformance =="
  while IFS= read -r t; do
    [[ -n "$t" ]] || continue
    H "$t" describe | is_json && ok "$t describe JSON" || bad "$t describe"
    H "$t" describe | "$PY" "$SB/lib/contract.py" validate-describe >/dev/null 2>&1 && ok "$t describe valid" || bad "$t describe invalid"
    H "$t" list-instances | is_json && ok "$t instances JSON" || bad "$t instances"
    H "$t" list-instances | "$PY" "$SB/lib/contract.py" validate-instances >/dev/null 2>&1 && ok "$t instances valid" || bad "$t instances invalid"
    H "$t" doctor >/dev/null 2>&1 && ok "$t doctor PASS" || bad "$t doctor"
  done < <("$PY" "$SB/lib/registry.py" job-types)
}

test_unconfigured_fetch_scheduler() {
  echo "== fetch scheduler on a command-only installation =="
  local LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/unconfigured-fetch.yml"
  local LOCAL_JOBS_LAUNCHD_DISABLE=0
  local LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/empty-fetch-agents"
  export LOCAL_JOBS_IGF_CONFIG LOCAL_JOBS_LAUNCHD_DISABLE LOCAL_JOBS_LAUNCHAGENTS_DIR
  local out label
  mkdir -p "$LOCAL_JOBS_LAUNCHAGENTS_DIR"
  label="$("$PY" "$SB/lib/registry.py" label-root).git-fetch"
  H incremental-git-fetch list-instances | "$PY" -c '
import json, sys
row, = json.load(sys.stdin)
assert row["id"] == "__global__" and row["enabled"] is False and row["launchd_loaded"] is False
' && ok "unconfigured sweep is dormant" || bad "unconfigured sweep reported as enabled"
  if out="$(CLI doctor --plain 2>&1)" && [[ "$out" == *"doctor: PASS"* ]]; then
    ok "full doctor passes on a command-only host"
  else
    bad "unconfigured fetch failed full doctor: $out"
  fi
  [[ ! -e "$LOCAL_JOBS_IGF_CONFIG" && ! -e "$LOCAL_JOBS_LAUNCHAGENTS_DIR/$label.plist" ]] \
    && ok "readback preserved unconfigured fetch" || bad "fetch readback created configuration"

  # A retained plist or explicit configuration makes a missing agent real drift.
  touch "$LOCAL_JOBS_LAUNCHAGENTS_DIR/$label.plist"
  if H incremental-git-fetch doctor >/dev/null 2>&1; then bad "missing staged agent passed"; else ok "missing staged agent refused"; fi
  rm "$LOCAL_JOBS_LAUNCHAGENTS_DIR/$label.plist"
  cp "$SB/state/jobs/incremental-git-fetch.yml" "$LOCAL_JOBS_IGF_CONFIG"
  H incremental-git-fetch list-instances | "$PY" -c '
import json, sys
row = next(r for r in json.load(sys.stdin) if r["id"] == "__global__")
assert row["enabled"] is True and row["launchd_loaded"] is False
' && ok "configured missing sweep remains visible" || bad "configured sweep was hidden"
  if H incremental-git-fetch doctor >/dev/null 2>&1; then bad "missing configured agent passed"; else ok "missing configured agent refused"; fi
}

test_handler_log_override() {
  echo "== generic fetch handler preserves the scoped log-directory override =="
  local logs="$SB/explicit-fetch-logs"
  LOCAL_JOBS_IGF_LOG_DIR="$logs" H incremental-git-fetch list-instances | "$PY" -c '
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
rows = json.load(sys.stdin)
assert rows, "expected the synthetic global/reference instances"
for row in rows:
    for value in row.get("log_paths", {}).values():
        assert Path(value).parent == root, (row.get("id"), value, root)
assert any(row.get("log_paths") for row in rows), "no log-path assertion exercised"
' "$logs" && ok "fetch handler retains the explicit fixture log root" || bad "fetch handler overrides the requested log root"
}

test_command_lifecycle() {
  echo "== command lifecycle =="
  local id="cmdjob" plist="$SB/agents/com.local-jobs.command.cmdjob.plist"
  CLI add-job --type command --id "$id" --program /bin/echo --arg=hello --schedule 03:03 >/dev/null 2>&1 && ok "command add" || bad "command add"
  [[ -f "$plist" ]] && ok "command plist label root" || bad "command plist missing"
  CLI run-job --id "$id" --dry-run 2>/dev/null | "$PY" -c 'import sys; data=sys.stdin.read(); assert "@@RUNLOG@@" in data and "dry-run" in data' && ok "command dry-run runlog" || bad "command dry-run"
  CLI disable-job --id "$id" >/dev/null 2>&1 && [[ ! -f "$plist" ]] && ok "command disable removes plist" || bad "command disable"
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 && ok "command delete" || bad "command delete"
}

test_command_interval_lifecycle() {
  echo "== command interval lifecycle =="
  local id="intervalcmd" plist="$SB/agents/com.local-jobs.command.intervalcmd.plist" out rc=0 hash1 hash2
  out="$(CLI add-job --type command --id "$id" --program /usr/local/bin/pr-automation-controller \
    --arg=poll-once --interval-seconds 60 --dry-run 2>&1)" || rc=$?
  if [[ "$rc" == "0" ]] && printf '%s' "$out" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
assert d["dry_run"] is True
assert d["entry"]["schedule"] == {"kind": "interval", "seconds": 60}
assert d["entry"]["args"] == ["poll-once"]
assert d["would_install"] is True
'; then
    ok "60-second poll-once add dry-run"
  else
    bad "60-second poll-once add dry-run: $out"
  fi
  [[ ! -f "$plist" ]] && ! _hl_interval_store_has "$id" && ok "interval dry-run changes nothing" || bad "interval dry-run mutated state"

  CLI add-job --type command --id "$id" --program /usr/local/bin/pr-automation-controller \
    --arg=poll-once --interval-seconds 60 >/dev/null 2>&1 && ok "interval add" || bad "interval add"
  "$PY" - "$plist" <<'PY' && ok "interval plist renders StartInterval 60" || bad "interval plist wrong"
import sys
text = open(sys.argv[1]).read()
assert "<key>StartInterval</key>" in text
assert "<integer>60</integer>" in text
assert "StartCalendarInterval" not in text
PY

  CLI repair-job --id "$id" >/dev/null 2>&1 || bad "interval repair first pass"
  hash1="$("$PY" - "$plist" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  CLI repair-job --id "$id" >/dev/null 2>&1 || bad "interval repair second pass"
  hash2="$("$PY" - "$plist" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  [[ "$hash1" == "$hash2" ]] && ok "interval repair is idempotent" || bad "interval repair changed plist bytes"

  local update_rc=0
  CLI update-job --id "$id" --interval-seconds 120 >/dev/null 2>&1 || update_rc=$?
  if [[ "$update_rc" == "0" ]] && "$PY" - "$plist" <<'PY'
import sys
text = open(sys.argv[1]).read()
assert "<integer>120</integer>" in text
PY
  then ok "interval update"; else bad "interval update"; fi

  CLI update-job --id "$id" --schedule 04:05 >/dev/null 2>&1
  if "$PY" - "$plist" <<'PY'
import sys
text = open(sys.argv[1]).read()
assert "<key>StartCalendarInterval</key>" in text
assert "<key>Hour</key><integer>4</integer>" in text
assert "<key>Minute</key><integer>5</integer>" in text
assert "<key>StartInterval</key>" not in text
PY
  then ok "calendar schedule remains supported"; else bad "calendar schedule regression"; fi

  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 && ok "interval delete" || bad "interval delete"
}

_hl_interval_store_has() {
  local id="$1"
  "$PY" "$SB/lib/store.py" --file "$SB/state/jobs/command.yml" list | \
    ID="$id" "$PY" -c 'import json,os,sys; raise SystemExit(0 if any(x.get("id")==os.environ["ID"] for x in json.load(sys.stdin)) else 1)'
}

test_command_interval_validation() {
  echo "== command interval validation =="
  local n id i=0
  for n in -1 0 1 59 2147483648; do
    i=$((i+1)); id="badinterval$i"
    if CLI add-job --type command --id "$id" --program /bin/true --interval-seconds "$n" --dry-run >/dev/null 2>&1; then
      bad "unsafe interval accepted: $n"
    else
      ok "unsafe interval rejected: $n"
    fi
  done
  CLI add-job --type command --id badintervaltext --program /bin/true --interval-seconds nope --dry-run >/dev/null 2>&1 \
    && bad "non-integer interval accepted" || ok "non-integer interval rejected"
  CLI add-job --type command --id badintervalboth --program /bin/true --schedule 03:00 --interval-seconds 60 --dry-run >/dev/null 2>&1 \
    && bad "ambiguous schedule accepted" || ok "ambiguous schedule rejected"
  CLI add-job --type command --id badintervalmissing --program /bin/true --dry-run >/dev/null 2>&1 \
    && bad "missing schedule accepted" || ok "missing schedule rejected"
  CLI add-job --type command --id badintervalkind --program /bin/true \
    --schedule '{"kind":"unsupported","seconds":60}' --dry-run >/dev/null 2>&1 \
    && bad "unsupported interval kind accepted" || ok "unsupported interval kind rejected"
  CLI add-job --type command --id badintervalkeys --program /bin/true \
    --schedule '{"kind":"interval","seconds":60,"hour":1}' --dry-run >/dev/null 2>&1 \
    && bad "mixed interval fields accepted" || ok "mixed interval fields rejected"
  CLI add-job --type command --id legacyinterval --program /bin/true \
    --schedule '{"kind":"interval","seconds":60}' --dry-run >/dev/null 2>&1 \
    && ok "existing interval JSON remains supported" || bad "existing interval JSON regressed"
  local catalog
  catalog="$(CLI list-types --plain)"
  [[ "$catalog" == *"one of --schedule, --interval-seconds"* ]] \
    && ok "plain type help shows schedule alternatives" || bad "plain type help omits interval alternative"
  CLI describe-types --json | "$PY" -c '
import json, sys
command = next(x for x in json.load(sys.stdin) if x["slug"] == "command")
fields = {x["flag"]: x for x in command["update_fields"]}
assert fields["--schedule"]["required_one_of"] == "schedule"
assert fields["--interval-seconds"]["required_one_of"] == "schedule"
assert fields["--interval-seconds"]["kind"] == "interval_seconds"
' && ok "machine schema exposes interval schedule group" || bad "machine schema omits interval schedule group"
}

test_command_stored_schedule_doctor() {
  echo "== stored schedule doctor =="
  local out rc=0
  "$PY" - "$SB/state/jobs/command.yml" <<'PY'
import sys, yaml
path = sys.argv[1]
with open(path) as handle:
    data = yaml.safe_load(handle)
data["instances"].append({
    "id": "unsafe-stored",
    "program": "/bin/true",
    "schedule": {"kind": "interval", "seconds": 1},
    "enabled": False,
})
with open(path, "w") as handle:
    yaml.safe_dump(data, handle, sort_keys=False)
PY
  out="$(H command doctor 2>&1)" || rc=$?
  [[ "$rc" != "0" && "$out" == *"store: INVALID"* ]] \
    && ok "doctor rejects unsafe stored interval" || bad "doctor accepted unsafe stored interval: $out"
  "$PY" - "$SB/state/jobs/command.yml" <<'PY'
import sys, yaml
path = sys.argv[1]
with open(path) as handle:
    data = yaml.safe_load(handle)
data["instances"] = [x for x in data["instances"] if x.get("id") != "unsafe-stored"]
with open(path, "w") as handle:
    yaml.safe_dump(data, handle, sort_keys=False)
PY
}

test_fetch_dry_run() {
  echo "== incremental fetch dry-run =="
  CLI run-job --type incremental-git-fetch --id reference --dry-run >/dev/null 2>&1 && ok "fetch dry-run" || bad "fetch dry-run"
  env -u LOCAL_JOBS_PYTHON LOCAL_JOBS_IGF_DRY_RUN=1 LOCAL_JOBS_IGF_SKIP_JITTER=1 "$SB/backends/incremental-git-fetch/run-all.sh" reference >/dev/null 2>&1 && ok "fetch defaults python" || bad "fetch default python"
  LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/missing-fetch.yml" H incremental-git-fetch list-instances | "$PY" "$SB/lib/contract.py" validate-instances >/dev/null 2>&1 && ok "fetch missing store empty" || bad "fetch missing store"
  CLI run-job --type incremental-git-fetch --id __global__ --dry-run >/dev/null 2>&1 && ok "global fetch dry-run" || bad "global fetch dry-run"
  "$PY" "$SB/lib/run_log.py" recent --limit 5 --id reference | "$PY" -c 'import json,sys; assert len(json.load(sys.stdin)) >= 1' && ok "fetch run logged" || bad "fetch run log"
}

test_fetch_tags() {
  echo "== incremental fetch tags =="
  local remote="$SB/tag-remote.git" source="$SB/tag-source" off="$SB/tag-off" on="$SB/tag-on" detached="$SB/tag-detached"
  local config="$SB/state/jobs/incremental-git-fetch.yml"
  local out before after config_before config_after rc=0

  H incremental-git-fetch view --id reference | "$PY" -c '
import json,sys
assert json.load(sys.stdin)["fetch_tags"] is False
' 2>/dev/null && ok "legacy config defaults fetch_tags=false" || bad "legacy config did not default fetch_tags=false"

  out="$(LOCAL_JOBS_IGF_DRY_RUN=1 "$SB/backends/incremental-git-fetch/fetch-repo.sh" reference 2>&1)" || rc=$?
  [[ "$rc" == 0 && "$out" == *"--no-tags"* && "$out" != *" --tags"* ]] \
    && ok "default dry-run selects --no-tags" || bad "default dry-run tag selection: $out"

  git init -q --bare "$remote"
  git init -q "$source"
  git -C "$source" -c user.email=t@t -c user.name=t commit -q --allow-empty -m initial
  git -C "$source" branch -M master
  git -C "$source" remote add origin "$remote"
  git -C "$source" tag stable
  git -C "$source" push -q origin master --tags
  git clone -q --branch master "$remote" "$off"
  git clone -q --branch master "$remote" "$on"
  git clone -q --branch master "$remote" "$detached"
  git -C "$detached" checkout -q --detach HEAD
  before="$(git -C "$detached" rev-parse HEAD)"

  config_before="$("$PY" - "$config" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  rc=0; out="$(CLI add-job --type incremental-git-fetch --id tags-preview --path "$on" --branch master --fetch-tags true --dry-run 2>&1)" || rc=$?
  config_after="$("$PY" - "$config" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  if [[ "$rc" == 0 && "$config_before" == "$config_after" ]] && printf '%s' "$out" | "$PY" -c '
import json, sys
preview = json.load(sys.stdin)
assert preview["dry_run"] is True
assert preview["would_add"]["fetch_tags"] is True
' 2>/dev/null; then
    ok "tag-aware add dry-run exits zero and changes nothing"
  else
    bad "tag-aware add dry-run failed or changed config: $out"
  fi

  CLI add-job --type incremental-git-fetch --id tags-off --path "$off" --branch master --fetch-tags false >/dev/null 2>&1 \
    && ok "add fetch-tags=false" || bad "add fetch-tags=false"
  CLI add-job --type incremental-git-fetch --id tags-on --path "$on" --branch master --fetch-tags true >/dev/null 2>&1 \
    && ok "add fetch-tags=true" || bad "add fetch-tags=true"
  CLI add-job --type incremental-git-fetch --id tags-detached --path "$detached" --branch master --fetch-tags true >/dev/null 2>&1 \
    && ok "add detached fetch-tags=true" || bad "add detached fetch-tags=true"
  H incremental-git-fetch view --id tags-on | "$PY" -c '
import json,sys
assert json.load(sys.stdin)["fetch_tags"] is True
' 2>/dev/null && ok "add/view preserves fetch_tags=true" || bad "add/view lost fetch_tags=true"
  CLI update-job --id tags-on --fetch-tags false >/dev/null 2>&1 \
    && H incremental-git-fetch view --id tags-on | "$PY" -c 'import json,sys; assert json.load(sys.stdin)["fetch_tags"] is False' \
    && CLI update-job --id tags-on --fetch-tags true >/dev/null 2>&1 \
    && ok "update toggles fetch_tags true→false" || bad "update fetch_tags toggle failed"
  CLI update-job --id tags-on --fetch-tags maybe >/dev/null 2>&1 \
    && bad "invalid fetch_tags accepted" || ok "invalid fetch_tags rejected"

  git -C "$source" -c user.email=t@t -c user.name=t commit -q --allow-empty -m tagged
  git -C "$source" tag new-tag
  git -C "$source" push -q origin master refs/tags/new-tag

  rc=0; out="$(LOCAL_JOBS_IGF_DRY_RUN=1 "$SB/backends/incremental-git-fetch/fetch-repo.sh" tags-on 2>&1)" || rc=$?
  [[ "$rc" == 0 && "$out" == *"--tags"* && "$out" != *"--no-tags"* ]] \
    && ok "opted-in dry-run selects --tags" || bad "opted-in dry-run tag selection: $out"
  "$SB/backends/incremental-git-fetch/fetch-repo.sh" tags-on >/dev/null 2>&1 \
    && git -C "$on" rev-parse -q --verify refs/tags/new-tag >/dev/null 2>&1 \
    && ok "opted-in fetch obtains new tag" || bad "opted-in fetch missed new tag"
  "$SB/backends/incremental-git-fetch/fetch-repo.sh" tags-off >/dev/null 2>&1 \
    && ! git -C "$off" rev-parse -q --verify refs/tags/new-tag >/dev/null 2>&1 \
    && ok "non-opted fetch excludes new tag" || bad "non-opted fetch obtained new tag"

  "$SB/backends/incremental-git-fetch/fetch-repo.sh" tags-detached >/dev/null 2>&1
  after="$(git -C "$detached" rev-parse HEAD)"
  [[ "$before" == "$after" ]] && ! git -C "$detached" symbolic-ref -q HEAD >/dev/null 2>&1 \
    && ok "detached HEAD remains detached and unchanged" || bad "detached HEAD changed or attached"

  before="$(git -C "$on" rev-parse refs/tags/stable)"
  git -C "$source" tag -f stable
  git -C "$source" push -q --force origin refs/tags/stable
  rc=0; "$SB/backends/incremental-git-fetch/fetch-repo.sh" tags-on >/dev/null 2>&1 || rc=$?
  after="$(git -C "$on" rev-parse refs/tags/stable)"
  [[ "$rc" != 0 && "$before" == "$after" ]] \
    && ok "tag fetch never force-moves an existing local tag" || bad "existing local tag moved or fetch succeeded"
}

test_fetch_stable_head_telemetry() {
  echo "== incremental fetch stable head telemetry =="
  local fake_bin="$SB/fake-git/bin" fake_backend="$SB/fake-git/backend"
  local state="$SB/fake-git/head-state" out
  mkdir -p "$fake_bin" "$fake_backend"
  printf 'before\n' >"$state"
  cat >"$fake_bin/git" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"rev-parse --short HEAD" ]]; then
  [[ "$(<"$HEAD_STATE")" == "before" ]] && printf '68a04cc\n' || printf '68a04ccf\n'
elif [[ "$*" == *"rev-parse HEAD" ]]; then
  printf '68a04ccf8ef74803bdb651e12c3b85b218bbccdf\n'
elif [[ "$*" == *"rev-list --count"* ]]; then
  printf '5244\n'
else
  exit 1
fi
SH
  cat >"$fake_backend/run-all.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'after\n' >"$HEAD_STATE"
printf 'reference\tsuccess\tup to date\n' >"$LOCAL_JOBS_IGF_OUTCOME_FILE"
SH
  chmod +x "$fake_bin/git" "$fake_backend/run-all.sh"

  out="$(
    HANDLER="$SB/handlers/incremental-git-fetch.sh" \
    FAKE_BACKEND="$fake_backend" HEAD_STATE="$state" PATH="$fake_bin:$PATH" \
    LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_STATE="$SB/state" \
      bash -c '
        set -- describe
        source "$HANDLER" >/dev/null
        BACKEND="$FAKE_BACKEND"
        igf_config() {
          [[ "${1:-}" == "view" ]] || return 2
          printf "%s\n" '"'"'{"dev_root":"/tmp","repos":[{"id":"reference","path":"/tmp/reference","remote":"origin","branch":"main","enabled":true}]}'"'"'
        }
        cmd_run --id reference
      '
  )"
  if printf '%s\n' "$out" | "$PY" -c '
import json, sys
line = next((line for line in sys.stdin if line.startswith("@@RUNLOG@@ ")), "")
payload = json.loads(line.removeprefix("@@RUNLOG@@ "))
repo = payload["fields"]["repos"][0]
assert repo["head_before"] == "68a04cc"
assert repo["head_after"] == "68a04ccf"
assert repo["reason"] == "up to date"
'; then
    ok "short-hash length drift cannot masquerade as a fast-forward"
  else
    bad "stable full HEAD comparison"
  fi
}

test_fetch_update_atomicity() {
  echo "== incremental fetch update atomicity =="
  local config="$SB/state/jobs/incremental-git-fetch.yml" before after rc=0
  before="$("$PY" - "$config" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  CLI update-job --id __global__ --display-name "must not persist" --fetch-tags true >/dev/null 2>&1 || rc=$?
  after="$("$PY" - "$config" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
  [[ "$rc" != 0 && "$before" == "$after" ]] \
    && ok "rejected global mixed update leaves config bytes unchanged" \
    || bad "rejected global mixed update changed config"
}

test_fetch_conditional_retirement() {
  echo "== conditional retirement of an inherited fetch =="
  local rc=0
  "$PY" - "$SB" <<'PY' || rc=$?
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import yaml

home = Path(sys.argv[1])
config = home / "state/jobs/retirement.yml"
original = yaml.safe_load(Path(os.environ["LOCAL_JOBS_IGF_CONFIG"]).read_text())
original["repos"] = [row for row in original["repos"] if row["id"] == "reference"]
config.write_text(yaml.safe_dump(original))
env = dict(os.environ, LOCAL_JOBS_IGF_CONFIG=str(config))
cli = [str(home / "bin/local-jobs.sh")]
backend = [sys.executable, str(home / "backends/incremental-git-fetch/config.py")]

def call(program, *args, check=True):
    return subprocess.run([*program, *args], env=env, capture_output=True, text=True,
                          check=check, timeout=30)

def current():
    rows = json.loads(call(cli, "view-jobs", "--json").stdout)["instances"]
    return next(row for row in rows if row["id"] == "reference")

def delete(revision, *args, check=False):
    return call(cli, "delete-fetch-if-current", "--id", "reference",
                "--if-revision", revision, *args, check=check)

initial = current()["removal_revision"]
assert re.fullmatch("[0-9a-f]{64}", initial)
before = config.read_bytes()
for revision, extra in [(initial, []), ("wrong", ["--confirm"]),
                        (initial, ["--confirm", "--purge-launchd"])]:
    assert delete(revision, *extra).returncode and config.read_bytes() == before

call(cli, "update-job", "--type", "incremental-git-fetch", "--id", "reference",
     "--description", "reassigned")
reassigned = config.read_bytes()
assert current()["removal_revision"] != initial
assert delete(initial, "--confirm").returncode and config.read_bytes() == reassigned

# All writers to the shared YAML must serialize their read and replacement.
def add_peer(number):
    call(backend, "add", "--id", f"peer-{number}", "--path", "reference", "--branch", "main")
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(add_peer, range(12)))
revision = current()["removal_revision"]
peers = {f"peer-{number}" for number in range(12)}
assert {r["id"] for r in yaml.safe_load(config.read_text())["repos"]} == peers | {"reference"}
# A concurrent owner edit must either win and survive, or observe removal.
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    edit = pool.submit(call, backend, "set-fields", "--id", "reference", "--description",
                       "new assignment", check=False)
    retire = pool.submit(delete, revision, "--confirm")
    changed, removed = edit.result().returncode == 0, retire.result().returncode == 0
assert changed != removed
if changed:
    assert current()["description"] == "new assignment"
    delete(current()["removal_revision"], "--confirm", check=True)
assert {r["id"] for r in yaml.safe_load(config.read_text())["repos"]} == peers

# A duplicated row or a dedicated agent requires separate owner reconciliation.
data = yaml.safe_load(before)
data["repos"].append(dict(data["repos"][0]))
config.write_text(yaml.safe_dump(data))
duplicate = config.read_bytes()
assert delete(initial, "--confirm").returncode and config.read_bytes() == duplicate
data["repos"].pop()
data["repos"][0]["schedule"] = {"hour": 9, "minute": 30}
config.write_text(yaml.safe_dump(data))
custom = config.read_bytes()
assert "removal_revision" not in current()
assert delete(initial, "--confirm").returncode and config.read_bytes() == custom

# Read, execution lookup, and deletion all retain the version contract.
for version in (0, "invalid", 2):
    data = yaml.safe_load(before)
    data["version"] = version
    config.write_text(yaml.safe_dump(data))
    saved = config.read_bytes()
    for operation in [("view",), ("repo", "reference")]:
        result = call(backend, *operation, check=False)
        if version == 2:
            assert result.returncode == 0 and "loading forward-compatibly" in result.stderr
        else:
            assert result.returncode and "unsupported config version" in result.stderr
    if version != 2:
        assert delete(initial, "--confirm").returncode
    assert config.read_bytes() == saved
PY
  [[ "$rc" == 0 ]] && ok "conditional retirement and competing store writers" || bad "conditional fetch retirement"
}

test_configured_inventory() {
  "$PY" -B "$REAL_HOME/tests/test_configured.py" && ok "configuration-only inventory" || bad "configuration-only inventory"
}

test_overlay_authoring() {
  echo "== overlay authoring =="
  CLI add-job-type --type sample --cardinality multi >/dev/null 2>&1 && ok "scaffold overlay type" || bad "scaffold overlay type"
  [[ -x "$SB/state/handlers/sample.sh" && -f "$SB/state/registry.d/sample.yml" ]] && ok "authoring writes overlay" || bad "overlay files missing"
  ! [[ -e "$SB/handlers/sample.sh" ]] && ok "managed handlers untouched" || bad "managed handler was written"
  [[ "$(CLI handler-path --type sample)" == "$SB/state/handlers/sample.sh" ]] && ok "overlay handler path absolute" || bad "overlay handler path"
  CLI add-job --type sample --id s1 --schedule 01:00 >/dev/null 2>&1 && ok "overlay type add" || bad "overlay type add"
  "$SB/state/handlers/sample.sh" list-instances | "$PY" "$SB/lib/contract.py" validate-instances >/dev/null 2>&1 && ok "overlay type valid" || bad "overlay type invalid"
}

test_canvas_templates() {
  echo "== canvas templates =="
  for f in "$REAL_HOME"/canvases/*.template.tsx; do
    [[ -f "$f" ]] || { bad "missing canvas template"; return; }
    if "$PY" - "$f" <<'PY'
from pathlib import Path
import re, sys
s = Path(sys.argv[1]).read_text()
if re.search(r'\barchive\b', s, re.I):
    raise SystemExit('local-only archive token')
if "__DASHBOARD_JSON__" not in s and "local-jobs-dashboard" in sys.argv[1]:
    raise SystemExit('dashboard template missing embed marker')
PY
    then ok "template clean $(basename "$f")"; else bad "template dirty $(basename "$f")"; fi
  done
  for f in "$REAL_HOME"/canvases/*.canvas.tsx; do
    [[ -f "$f" ]] || { bad "missing canvas file"; return; }
    # The live render is a machine-specific, git-ignored artifact — not tracked.
    case "$(basename "$f")" in *.generated.canvas.tsx) continue ;; esac
    if "$PY" - "$f" <<'PY'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text()
name = Path(sys.argv[1]).name
if "export default" not in s:
    raise SystemExit("missing export default")
if name == "local-jobs-dashboard.canvas.tsx":
    for needle in ("INITIAL_RAW", "dashboard/v1"):
        if needle not in s:
            raise SystemExit(f"missing {needle!r}")
    # The tracked dashboard canvas is a data-free SEED: no machine specifics.
    if '"instances": []' not in s:
        raise SystemExit("tracked dashboard canvas must be the empty seed (instances: [])")
    for tok in ("com.kleinperkins", "Library/Logs", "head_after"):
        if tok in s:
            raise SystemExit(f"machine token leaked into seed: {tok}")
PY
    then ok "canvas structure $(basename "$f")"; else bad "canvas structure $(basename "$f")"; fi
  done
}

test_canvas_tsc_smoke() {
  echo "== canvas tsc smoke =="
  if ! command -v tsc >/dev/null 2>&1; then
    ok "tsc unavailable (static canvas checks covered)"
    return
  fi
  local td="$SB/tsc"
  mkdir -p "$td/cursor" "$td/react"
  cp "$REAL_HOME/canvases/local-jobs-dashboard.template.tsx" "$td/local-jobs-dashboard.template.tsx"
  # The stub must export EVERY member the template imports, or `tsc` (when
  # present) fails on a missing export rather than on a real type error. Keep
  # this list in lockstep with the template's `import { ... } from "cursor/canvas"`.
  cat > "$td/cursor/canvas.d.ts" <<'EOF'
declare module "cursor/canvas" {
  export const Stack: any; export const Row: any; export const Grid: any; export const Spacer: any;
  export const H1: any; export const H2: any; export const H3: any; export const Text: any;
  export const Code: any; export const Stat: any; export const Pill: any; export const Card: any;
  export const CardHeader: any; export const CardBody: any; export const Table: any;
  export const Callout: any; export const Button: any; export const Divider: any;
  export const CollapsibleSection: any; export const UsageBar: any; export const Swatch: any;
  export function useHostTheme(): any;
  export function useCanvasState<T>(key: string, initial: T): [T, (value: T) => void];
  export function useCanvasAction(): (action: any) => void;
}
declare namespace JSX { interface IntrinsicElements { [elemName: string]: any } }
declare const __DASHBOARD_JSON__: any;
EOF
  cat > "$td/react/jsx-runtime.d.ts" <<'EOF'
declare module "react/jsx-runtime" { export const jsx: any; export const jsxs: any; export const Fragment: any; }
EOF
  cat > "$td/react/index.d.ts" <<'EOF'
declare module "react" { export type ReactNode = unknown; }
EOF
  cat > "$td/tsconfig.json" <<'EOF'
{"compilerOptions":{"strict":true,"jsx":"react-jsx","module":"commonjs","target":"ES2020","moduleResolution":"node","baseUrl":".","skipLibCheck":true},"include":["*.tsx","cursor/*.d.ts","react/*.d.ts"]}
EOF
  (cd "$td" && tsc --noEmit >/dev/null 2>&1) && ok "dashboard template typechecks" || bad "dashboard template tsc"
}

test_dashboard_canvas_regen() {
  echo "== dashboard canvas regen =="
  local rc=0 seed="$SB/canvases/local-jobs-dashboard.canvas.tsx" live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx"
  local gen=(env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state"
    LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/agents"
    LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml"
    LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml"
    "$REAL_HOME/bin/generate-dashboard-canvas.sh")
  # 1) default writes the data-free tracked SEED
  "${gen[@]}" >/dev/null || rc=$?
  [[ "$rc" == "0" && -f "$seed" ]] && ok "generate seed canvas" || bad "generate seed canvas"
  grep -q '"instances": \[\]' "$seed" && ok "seed is empty payload" || bad "seed not empty payload"
  # 2) --check asserts byte parity of the fresh seed
  rc=0; "${gen[@]}" --check >/dev/null || rc=$?
  [[ "$rc" == "0" ]] && ok "seed check-seed parity" || bad "seed check-seed parity"
  # 3) --live writes a machine-specific render carrying real instances
  rc=0; "${gen[@]}" --live >/dev/null || rc=$?
  [[ "$rc" == "0" && -f "$live" ]] && ok "generate live canvas" || bad "generate live canvas"
  { ! grep -q '"instances": \[\]' "$live"; } && grep -q '__global__' "$live" && ok "live canvas embeds instances" || bad "live canvas empty"
}

test_dashboard_fixture_deterministic() {
  echo "== dashboard fixture (deterministic) =="
  local fstate="$SB/fixture-state" rc=0
  mkdir -p "$fstate/jobs" "$fstate/agents"
  cp "$REAL_HOME/tests/fixtures/runs.jsonl" "$fstate/runs.jsonl"
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" LOCAL_JOBS_STATE="$fstate" \
    LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml" \
    LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml" \
    LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$fstate/agents" \
    LOCAL_JOBS_NOW="2026-07-01T12:00:00-07:00" \
    "$SB/bin/local-jobs.sh" dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
assert d["generated_at"] == "2026-07-01T12:00:00-07:00", d["generated_at"]
assert d["run_bridge_enabled"] is False, d["run_bridge_enabled"]
ref = next(i for i in d["instances"] if i.get("id") == "reference")
rs = ref["run_stats"]
assert rs["last_run"]["status"] == "success", rs["last_run"]
assert rs["last_run"]["duration_s"] == 6, rs["last_run"]
assert rs["durations"]["last"] == 6, rs["durations"]
assert rs["durations"]["p50"] == 4, rs["durations"]
assert rs["durations"]["series"] == [3, 5, 4, 2, 6], rs["durations"]
assert rs["consecutive_failures"] == 0, rs["consecutive_failures"]
assert len(rs["recent"]) == 5 and rs["recent"][-1]["status"] == "success", rs["recent"]
assert rs["recent"][-1]["summary"], rs["recent"][-1]
' 2>/dev/null && ok "fixture → deterministic durations/recent/last" || { rc=1; bad "fixture dashboard assertions"; }
}

test_running_status() {
  echo "== running status marker =="
  "$PY" "$SB/lib/running.py" start --type incremental-git-fetch --id reference --pid $$ >/dev/null 2>&1 || true
  "$SB/bin/local-jobs.sh" dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
ref = next(i for i in d["instances"] if i.get("id") == "reference")
assert ref.get("running") is True, ref.get("running")
assert d["summary"].get("running", 0) >= 1, d["summary"]
' 2>/dev/null && ok "live marker → running=true" || bad "running marker not reflected"
  "$PY" "$SB/lib/running.py" stop --type incremental-git-fetch --id reference >/dev/null 2>&1 || true
  "$SB/bin/local-jobs.sh" dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
ref = next(i for i in d["instances"] if i.get("id") == "reference")
assert not ref.get("running"), ref.get("running")
' 2>/dev/null && ok "cleared marker → running=false" || bad "running marker not cleared"
  # A dead PID must never register as running (crash-safe).
  "$PY" "$SB/lib/running.py" start --type command --id ghost --pid 2147480000 >/dev/null 2>&1 || true
  "$PY" -c '
import sys; sys.path.insert(0, "'"$SB"'/lib")
import running
assert ("command", "ghost") not in running.active(), "dead pid registered as running"
' 2>/dev/null && ok "dead pid never running" || bad "dead pid registered as running"
  "$PY" "$SB/lib/running.py" stop --type command --id ghost >/dev/null 2>&1 || true
}

test_running_owner_aware_cleanup() {
  echo "== running marker owner cleanup =="
  local marker="$SB/state/running/command__owned.json"
  "$PY" "$SB/lib/running.py" start --type command --id owned --pid 111 >/dev/null 2>&1 || true
  "$PY" "$SB/lib/running.py" stop --type command --id owned --pid 222 >/dev/null 2>&1 || true
  [[ -f "$marker" ]] && ok "wrong pid cannot clear marker" || bad "wrong pid cleared marker"
  "$PY" "$SB/lib/running.py" stop --type command --id owned --pid 111 >/dev/null 2>&1 || true
  [[ ! -f "$marker" ]] && ok "owner pid clears marker" || bad "owner pid did not clear marker"
}

test_dispatch_run_flock() {
  echo "== dispatch run flock =="
  local h="$SB/state/handlers/slow-lock.sh" rc1=0 rc2=0
  cat > "$h" <<EOF
#!/usr/bin/env bash
case "\${1:-}" in
  describe) printf '{"type":"slow-lock","cardinality":"multi","label_token":"slow-lock","add_schema":[]}\n' ;;
  list-instances) printf '[{"id":"locky","type":"slow-lock","enabled":true,"role":"instance","launchd_label":"com.local-jobs.slow-lock.locky","launchd_loaded":false}]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  run)
    if [[ -f "$SB/state/slow-lock.active" ]]; then echo overlap > "$SB/state/slow-lock.overlap"; fi
    printf '%s\n' "\$\$" > "$SB/state/slow-lock.active"
    sleep 0.4
    rm -f "$SB/state/slow-lock.active"
    printf '@@RUNLOG@@ {"status":"success","fields":{}}\n'
    ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  cat > "$SB/state/registry.d/slow-lock.yml" <<EOF
id: slow-lock
handler: "$h"
EOF
  CLI run-job --type slow-lock --id locky >/dev/null 2>&1 & local p1=$!
  CLI run-job --type slow-lock --id locky >/dev/null 2>&1 & local p2=$!
  wait "$p1" || rc1=$?
  wait "$p2" || rc2=$?
  [[ "$rc1" == "0" && "$rc2" == "0" ]] && ok "double run both complete" || bad "double run rc $rc1/$rc2"
  [[ ! -f "$SB/state/slow-lock.overlap" ]] && ok "per-job flock prevents overlap" || bad "double run overlapped"
}

test_empty_state_seed() {
  echo "== empty-state seed =="
  local seed="$REAL_HOME/canvases/local-jobs-dashboard.canvas.tsx" tpl="$REAL_HOME/canvases/local-jobs-dashboard.template.tsx"
  [[ -f "$seed" ]] || { bad "tracked seed missing"; return; }
  "$PY" "$SB/lib/canvas_emit.py" check-seed "$tpl" "$seed" >/dev/null 2>&1 && ok "tracked seed == template ⊕ empty" || bad "tracked seed drifted from template⊕empty"
  "$PY" - "$seed" <<'PY' && ok "seed renders empty-state, no machine data" || bad "seed content wrong"
import sys
s = open(sys.argv[1]).read()
assert '"instances": []' in s, "instances not empty"
assert "No local job data on this machine" in s, "empty-state copy missing"
for tok in ("com.kleinperkins", "Library/Logs", "head_after"):
    assert tok not in s, tok
PY
}

test_view_verb_canvas() {
  echo "== view verb (canvas) =="
  local out rc=0 live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx"
  rm -f "$live"
  out="$(CLI view 2>&1)" || rc=$?
  [[ "$rc" == "0" ]] && ok "view verb exits 0" || bad "view verb rc=$rc: $out"
  [[ "$out" == *"local-jobs-dashboard.generated.canvas.tsx"* ]] && ok "view prints live canvas path" || bad "view path missing: $out"
  [[ -f "$live" ]] && ok "view wrote live canvas" || bad "view did not write live canvas"
  # Subtractive split preserved: view-jobs is still the plain text list.
  out="$(CLI view-jobs 2>&1)" && [[ "$out" == *"Managed instances"* ]] && ok "view-jobs still plain list" || bad "view-jobs broke: $out"
  # view rejects list-style flags with a helpful pointer.
  CLI view --json >/dev/null 2>&1 && bad "view --json should be rejected" || ok "view --json rejected (use dashboard --json)"
}

test_launchd_watchpaths_render() {
  echo "== launchd WatchPaths render =="
  local spec plist
  spec='{"label":"com.local-jobs.canvas-bridge","program_args":["/bin/true"],"watch_paths":["/tmp/local-jobs-canvas"],"schedule":{"seconds":15},"run_at_load":true}'
  plist="$("$PY" "$SB/lib/launchd.py" render --spec "$spec")"
  [[ "$plist" == *"<key>WatchPaths</key>"* && "$plist" == *"/tmp/local-jobs-canvas"* ]] && ok "WatchPaths rendered" || bad "WatchPaths missing"
  [[ "$plist" == *"<key>StartInterval</key>"* && "$plist" == *"<integer>15</integer>"* ]] && ok "bridge interval rendered" || bad "StartInterval missing"
}

test_launchd_schedule_validation_and_determinism() {
  echo "== launchd schedule validation + determinism =="
  local a b spec
  a='{"label":"com.local-jobs.det","program_args":["/bin/true"],"env":{"Z":"last","A":"first"},"schedule":{"seconds":60}}'
  b='{"program_args":["/bin/true"],"schedule":{"seconds":60},"env":{"A":"first","Z":"last"},"label":"com.local-jobs.det"}'
  [[ "$("$PY" "$SB/lib/launchd.py" render --spec "$a")" == "$("$PY" "$SB/lib/launchd.py" render --spec "$b")" ]] \
    && ok "plist render is deterministic" || bad "plist render depends on input key order"
  for spec in \
    '{"label":"x","program_args":["/bin/true"],"schedule":{"seconds":0}}' \
    '{"label":"x","program_args":["/bin/true"],"schedule":{"seconds":-1}}' \
    '{"label":"x","program_args":["/bin/true"],"schedule":{"seconds":"60"}}' \
    '{"label":"x","program_args":["/bin/true"],"schedule":{"seconds":60,"hour":1}}' \
    '{"label":"x","program_args":["/bin/true"],"schedule":{"minutes":1}}'
  do
    "$PY" "$SB/lib/launchd.py" render --spec "$spec" >/dev/null 2>&1 \
      && bad "invalid launchd schedule accepted: $spec" || ok "invalid launchd schedule rejected"
  done
}

test_canvas_run_bridge_lifecycle() {
  echo "== canvas run bridge lifecycle =="
  local label="com.local-jobs.canvas-bridge" plist out rc=0
  plist="$SB/agents/$label.plist"
  out="$(CLI enable-canvas-runs 2>&1)" || rc=$?
  [[ "$rc" == "0" && -f "$plist" ]] && ok "enable-canvas-runs writes plist" || bad "enable-canvas-runs: $out"
  [[ "$(<"$plist")" == *"<key>WatchPaths</key>"* && "$(<"$plist")" == *"$SB/canvases"* ]] && ok "bridge plist watches canvas dir" || bad "bridge WatchPaths missing"
  [[ "$(<"$plist")" == *"canvas-run-bridge.sh"* ]] && ok "bridge plist points at bridge script" || bad "bridge script missing from plist"
  rc=0; out="$(CLI enable-canvas-runs 2>&1)" || rc=$?
  [[ "$rc" == "0" && -f "$plist" ]] && ok "enable-canvas-runs idempotent" || bad "enable idempotency: $out"
  CLI disable-canvas-runs >/dev/null 2>&1 && [[ ! -f "$plist" ]] && ok "disable-canvas-runs removes plist" || bad "disable-canvas-runs"
}

test_canvas_run_bridge_requests() {
  echo "== canvas run bridge requests =="
  local id="bridgecmd" sidecar="$SB/canvases/local-jobs-dashboard.generated.canvas.data.json" ledger="$SB/state/canvas-bridge/seen-requests.json" last="$SB/state/canvas-bridge/last-request.json" live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx"
  CLI add-job --type command --id "$id" --program /bin/echo --arg=bridge-ok --schedule 03:04 >/dev/null 2>&1 || { bad "bridge command fixture add"; return; }
  write_canvas_run_request "$sidecar" "$id" "n1"
  local bridge_out rc=0
  bridge_out="$("$SB/bin/canvas-run-bridge.sh" 2>&1)" || rc=$?
  [[ "$rc" == "0" ]] && ok "bridge accepts registered request" || bad "bridge registered request: $bridge_out"
  [[ -f "$ledger" && -f "$live" ]] && ok "bridge writes ledger and refreshes view" || bad "bridge ledger/view missing"
  local count_before count_after mtime_before mtime_after
  count_before="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  mtime_before="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge duplicate wake exits 0" || bad "bridge duplicate wake"
  count_after="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  mtime_after="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  [[ "$count_before" == "$count_after" && "$mtime_before" == "$mtime_after" ]] && ok "duplicate nonce no run and no view loop" || bad "duplicate nonce reran or refreshed"

  write_canvas_run_request "$sidecar" "$id" "n2"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge accepts second nonce" || bad "bridge second nonce"
  count_before="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  write_canvas_run_request "$sidecar" "$id" "n1"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge remembers older nonce" || bad "bridge older nonce wake"
  count_after="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  [[ "$count_before" == "$count_after" ]] && ok "A-B-A nonce replay skipped" || bad "A-B-A nonce replay reran"

  write_canvas_run_request "$sidecar" "missing-job" "n3"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge rejects unknown id quietly" || bad "bridge unknown id"
  "$PY" - "$last" <<'PY' && ok "unknown request ledgered rejected" || bad "unknown request ledger missing"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
assert data["nonce"] == "n3", data
assert data["status"] == "rejected", data
assert data["reason"] == "unknown-or-ambiguous-job", data
PY

  "$PY" - "$sidecar" "$id" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
data["dash.runRequest"] = {"jobId": sys.argv[2], "at": int(__import__("time").time() * 1000), "snapshotGeneratedAt": "2026-07-01T00:00:00Z"}
Path(sys.argv[1]).write_text(json.dumps(data))
PY
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge rejects invalid request quietly" || bad "bridge invalid request"
  "$PY" - "$last" <<'PY' && ok "invalid request ledgered rejected" || bad "invalid request not ledgered"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
assert data["status"] == "rejected", data
assert data["reason"] == "invalid-request", data
PY

  count_before="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  write_canvas_run_request "$sidecar" "$id" "old-nonce" "1" "1970-01-01T00:00:00Z"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge skips stale request" || bad "bridge stale request"
  count_after="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  "$PY" - "$last" <<'PY' && [[ "$count_before" == "$count_after" ]] && ok "stale request ledgered without run" || bad "stale request ran or was not ledgered"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
assert data["nonce"] == "old-nonce", data
assert data["status"] == "skipped", data
assert data["reason"] == "stale-request", data
PY

  "$PY" "$SB/lib/running.py" start --type command --id "$id" --pid $$ >/dev/null 2>&1 || true
  count_before="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  write_canvas_run_request "$sidecar" "$id" "running-nonce"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge skips already-running job" || bad "bridge running request"
  "$PY" "$SB/lib/running.py" stop --type command --id "$id" --pid $$ >/dev/null 2>&1 || true
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "already-running request not replayed after stop" || bad "running request replay wake"
  count_after="$("$PY" "$SB/lib/run_log.py" recent --limit 20 --id "$id" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  "$PY" - "$last" <<'PY' && [[ "$count_before" == "$count_after" ]] && ok "already-running request ledgered without run" || bad "already-running request ran or was not ledgered"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
assert data["nonce"] == "running-nonce", data
assert data["status"] == "skipped", data
assert data["reason"] == "already-running", data
PY
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 || true
}

test_canvas_run_bridge_failure_refresh() {
  echo "== canvas run bridge failure refresh =="
  local id="bridgefail" sidecar="$SB/canvases/local-jobs-dashboard.generated.canvas.data.json" live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx" rc=0
  CLI add-job --type command --id "$id" --program /bin/sh --arg=-c --arg='printf "fail-visible\n"; exit 7' --schedule 03:05 >/dev/null 2>&1 || { bad "bridge failing fixture add"; return; }
  rm -f "$live"
  write_canvas_run_request "$sidecar" "$id" "fail-nonce"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" == "7" ]] && ok "bridge preserves failing run rc" || bad "bridge failure rc=$rc"
  [[ -f "$live" ]] && ok "bridge refreshes view after failure" || bad "bridge did not refresh view after failure"
  "$PY" "$SB/lib/run_log.py" recent --limit 5 --id "$id" | "$PY" -c '
import json, sys
rows = json.load(sys.stdin)
assert rows and rows[0]["status"] == "failure", rows
assert rows[0]["summary"] == "exit 7: fail-visible", rows[0]
' 2>/dev/null && ok "failed bridge run logged" || bad "failed bridge run log"
  "$PY" - "$live" <<'PY' && ok "failure visible in regenerated canvas" || bad "failure missing from live canvas"
import sys
from pathlib import Path
s = Path(sys.argv[1]).read_text()
assert "exit 7: fail-visible" in s, "failure summary missing"
PY
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 || true
}

test_wrapper_preflight() {
  echo "== wrapper preflight =="
  local path out rc=0
  path="$(LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state" LOCAL_JOBS_LAUNCHD_DISABLE=1 "$REAL_HOME/scripts/local-jobs.sh" handler-path --type command)"
  [[ "$path" == "$REAL_HOME/handlers/command.sh" ]] && ok "wrapper honors python override" || bad "wrapper handler path"
  out="$(LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/agents" LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml" "$REAL_HOME/scripts/local-jobs.sh" dashboard --brief 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"managed job(s)"* && "$out" != *"QUARANTINED"* ]] && ok "wrapper dashboard brief" || bad "wrapper dashboard brief: $out"
  rc=0
  out="$(LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/agents" LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml" "$REAL_HOME/scripts/local-jobs.sh" view-jobs 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"reference (incremental-git-fetch)"* && "$out" != *"QUARANTINED"* ]] && ok "wrapper view-jobs" || bad "wrapper view-jobs: $out"
  rc=0
  out="$(LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$SB/agents" LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$SB/state/jobs/incremental-git-fetch.yml" "$REAL_HOME/scripts/local-jobs.sh" doctor --plain 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"doctor: PASS"* && "$out" != *"QUARANTINED"* ]] && ok "wrapper doctor plain" || bad "wrapper doctor plain: $out"
}

test_fresh_state_dashboard() {
  echo "== fresh state dashboard =="
  local fresh="$SB/fresh-state" out
  mkdir -p "$fresh/jobs" "$fresh/agents"
  out="$(env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" LOCAL_JOBS_STATE="$fresh" LOCAL_JOBS_IGF_CONFIG="$fresh/jobs/incremental-git-fetch.yml" LOCAL_JOBS_COMMAND_CONFIG="$fresh/jobs/command.yml" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$fresh/agents" "$SB/bin/local-jobs.sh" dashboard --brief 2>&1)"
  [[ "$out" == *"All 1 managed job(s) healthy."* ]] && ok "fresh state healthy" || bad "fresh state dashboard: $out"
}

test_no_temp_status_paths() {
  echo "== no-temp status paths =="
  local no_tmp="$SB/no-tmp" out rc=0
  mkdir -p "$no_tmp"
  chmod 0555 "$no_tmp"

  out="$(env TMPDIR="$no_tmp" TMP="$no_tmp" TEMP="$no_tmp" "$SB/bin/local-jobs.sh" dashboard --brief 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"managed job(s)"* && "$out" != *"QUARANTINED"* && "$out" != *"cannot create temp file"* ]] && ok "no-temp dashboard brief" || bad "no-temp dashboard brief: $out"

  rc=0
  out="$(env TMPDIR="$no_tmp" TMP="$no_tmp" TEMP="$no_tmp" "$SB/bin/local-jobs.sh" view-jobs 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"reference (incremental-git-fetch)"* && "$out" != *"QUARANTINED"* && "$out" != *"cannot create temp file"* ]] && ok "no-temp view-jobs" || bad "no-temp view-jobs: $out"

  rc=0
  out="$(env TMPDIR="$no_tmp" TMP="$no_tmp" TEMP="$no_tmp" "$SB/bin/local-jobs.sh" doctor --plain 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"doctor: PASS"* && "$out" != *"QUARANTINED"* && "$out" != *"cannot create temp file"* ]] && ok "no-temp doctor plain" || bad "no-temp doctor plain: $out"

  chmod 0755 "$no_tmp"
}

test_consumer_payload_smoke_no_local_overlay() {
  echo "== consumer payload smoke =="
  local payload_dir="$SB/downstream/quiver/skills/local-jobs" state="$SB/consumer-state" out rc=0 live="$SB/downstream/quiver/skills/local-jobs/canvases/local-jobs-dashboard.generated.canvas.tsx"
  mkdir -p "$(dirname "$payload_dir")" "$state/jobs" "$state/registry.d" "$state/agents"
  copy_tracked_payload "$payload_dir"
  cp "$SB/state/jobs/command.yml" "$state/jobs/command.yml"
  cp "$SB/state/jobs/incremental-git-fetch.yml" "$state/jobs/incremental-git-fetch.yml"
  [[ -x "$payload_dir/bin/canvas-run-bridge.sh" && -f "$payload_dir/lib/launchd.py" && -f "$payload_dir/canvases/local-jobs-dashboard.template.tsx" ]] && ok "consumer payload includes bridge sources" || bad "consumer payload missing bridge sources"
  [[ ! -e "$payload_dir/canvases/local-jobs-dashboard.generated.canvas.tsx" && ! -e "$payload_dir/canvases/local-jobs-dashboard.generated.canvas.data.json" ]] && ok "consumer payload excludes generated canvas sidecars" || bad "consumer payload included generated canvas artifacts"
  "$PY" - "$payload_dir" <<'PY' && ok "consumer payload excludes all canvas data sidecars" || bad "consumer payload included canvas data sidecars"
import sys
from pathlib import Path
payload = Path(sys.argv[1])
assert not list((payload / "canvases").glob("*.canvas.data.json"))
PY

  out="$(env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/scripts/local-jobs.sh" list-types --plain 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"command"* && "$out" == *"incremental-git-fetch"* && "$out" != *"archive"* ]] && ok "consumer types exclude local overlay" || bad "consumer types: $out"

  rc=0
  out="$(env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/scripts/local-jobs.sh" dashboard --brief 2>&1)" || rc=$?
  [[ "$rc" == "0" && "$out" == *"managed job(s)"* && "$out" != *"archive"* && "$out" != *"QUARANTINED"* ]] && ok "consumer dashboard brief" || bad "consumer dashboard: $out"
  rc=0
  out="$(env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/scripts/local-jobs.sh" enable-canvas-runs 2>&1)" || rc=$?
  [[ "$rc" == "0" && -f "$state/agents/com.local-jobs.canvas-bridge.plist" ]] && ok "consumer enables bridge without install.sh" || bad "consumer enable bridge: $out"
  [[ "$(<"$state/agents/com.local-jobs.canvas-bridge.plist")" == *"<key>WatchPaths</key>"* ]] && ok "consumer bridge plist has WatchPaths" || bad "consumer bridge WatchPaths missing"
  rc=0
  out="$(env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/scripts/local-jobs.sh" view 2>&1)" || rc=$?
  [[ "$rc" == "0" && -f "$live" && "$out" == *"local-jobs-dashboard.generated.canvas.tsx"* ]] && ok "consumer view renders live canvas" || bad "consumer view: $out"
  rc=0
  out="$(env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$state" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/scripts/local-jobs.sh" view 2>&1)" || rc=$?
  [[ "$rc" == "0" && -f "$live" ]] && ok "consumer view idempotent" || bad "consumer view idempotency: $out"
  env LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_HOME="$payload_dir" LOCAL_JOBS_STATE="$state" LOCAL_JOBS_REGISTRY="$payload_dir/config/registry.yml" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" LOCAL_JOBS_COMMAND_CONFIG="$state/jobs/command.yml" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" "$payload_dir/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "consumer bridge reachable without sidecar" || bad "consumer bridge no-request"
}

test_stale_overlay_doctor_quarantine() {
  echo "== stale overlay quarantine =="
  local h="$SB/state/handlers/stale-overlay.sh" out rc=0
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
echo "raw stale runtime error" >&2
exit 9
EOF
  chmod +x "$h"
  cat > "$SB/state/registry.d/stale-overlay.yml" <<EOF
id: stale-overlay
handler: "$h"
EOF
  out="$(CLI doctor 2>&1)" || rc=$?
  [[ "$rc" != "0" ]] && ok "doctor fails on quarantined overlay" || bad "doctor unexpectedly passed on stale overlay"
  [[ "$out" == *"QUARANTINED: type is not runnable"* ]] && ok "doctor reports structured quarantine" || bad "doctor quarantine message missing: $out"
  [[ "$out" != *"raw stale runtime error"* ]] && ok "doctor suppresses raw stale handler stderr" || bad "doctor leaked raw handler stderr"
}

test_doctor_only_failure_structured() {
  echo "== doctor-only failure structure =="
  local h="$SB/state/handlers/doctor-only-fail.sh" out rc=0
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"doctor-only-fail","cardinality":"singleton","label_token":"doctor-only-fail","add_schema":[]}\n' ;;
  list-instances) printf '[]\n' ;;
  doctor) echo "raw doctor-only failure" >&2; exit 8 ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  cat > "$SB/state/registry.d/doctor-only-fail.yml" <<EOF
id: doctor-only-fail
handler: "$h"
EOF
  out="$(CLI doctor 2>&1)" || rc=$?
  [[ "$rc" != "0" ]] && ok "doctor fails on doctor-only handler failure" || bad "doctor unexpectedly passed doctor-only failure"
  [[ "$out" == *"FAIL: handler doctor failed (rc=8)"* ]] && ok "doctor reports structured handler failure" || bad "doctor structured failure missing: $out"
  [[ "$out" != *"raw doctor-only failure"* ]] && ok "doctor suppresses raw doctor stderr" || bad "doctor leaked raw doctor stderr"
}

test_partial_invalid_doctor_runs() {
  echo "== partial invalid instances =="
  local h="$SB/state/handlers/partial-invalid.sh" out rc=0
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"partial-invalid","cardinality":"multi","label_token":"partial-invalid","add_schema":[]}\n' ;;
  list-instances) printf '[{"id":"good","type":"partial-invalid","enabled":true,"launchd_label":"com.local-jobs.partial-invalid.good","launchd_loaded":false},{"bad":true}]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  cat > "$SB/state/registry.d/partial-invalid.yml" <<EOF
id: partial-invalid
handler: "$h"
EOF
  out="$(CLI doctor 2>&1)" || rc=$?
  [[ "$out" == *"== doctor: partial-invalid =="* ]] && ok "doctor runs for type with partial invalid instances" || bad "doctor skipped partial-invalid type: $out"
  if printf '%s\n' "$out" | grep -A2 '== doctor: partial-invalid ==' | grep -q 'QUARANTINED: type is not runnable'; then
    bad "partial invalid quarantined whole type"
  else
    ok "partial invalid does not skip doctor"
  fi
  out="$(CLI view-jobs 2>&1)" && [[ "$out" == *"good (partial-invalid)"* ]] && ok "valid instance still listed" || bad "valid instance missing after partial invalid"
}

test_inherit_disabled_no_drift() {
  echo "== inherit disabled no drift =="
  CLI disable-job --id reference >/dev/null 2>&1 && ok "disable inherit repo" || bad "disable inherit repo"
  local rc=0 live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx"
  "$PY" -c "
import json, subprocess, os
env = os.environ.copy()
env['LOCAL_JOBS_LAUNCHD_DISABLE'] = '0'
p = subprocess.run(['$SB/bin/local-jobs.sh', 'dashboard', '--json'], capture_output=True, text=True, env=env)
d = json.loads(p.stdout)
ref = next(i for i in d['instances'] if i.get('id') == 'reference')
assert not ref.get('drift'), ref
assert not ref.get('stale'), ref
assert ref['next_run']['basis'] == 'disabled', ref['next_run']
assert ref['next_run']['window_start'] is None, ref['next_run']
assert d['summary'].get('disabled', 0) >= 1, d['summary']
" 2>/dev/null && ok "disabled inherit repo has no drift" || { bad "inherit disabled drift"; rc=1; }
  CLI view >/dev/null 2>&1 || rc=$?
  "$PY" - "$live" <<'PY' && ok "disabled state visible in canvas" || { bad "disabled canvas state missing"; rc=1; }
import sys
from pathlib import Path
s = Path(sys.argv[1]).read_text()
assert '"enabled": false' in s, "disabled payload missing"
assert '"basis": "disabled"' in s, "disabled basis missing"
assert "schedule paused" in s, "disabled copy missing"
PY
  CLI enable-job --id reference >/dev/null 2>&1 && ok "re-enable inherit repo" || bad "re-enable inherit repo"
}

test_run_all_rc() {
  echo "== run --all exit code =="
  local h="$SB/state/handlers/run-fail.sh" rc=0
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"run-fail","cardinality":"singleton","label_token":"run-fail","add_schema":[]}\n' ;;
  list-instances) printf '[]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  run) exit 3 ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  cat > "$SB/state/registry.d/run-fail.yml" <<EOF
id: run-fail
handler: "$h"
EOF
  CLI run-job --all --dry-run >/dev/null 2>&1 || rc=$?
  [[ "$rc" != "0" ]] && ok "run --all propagates handler failure rc" || bad "run --all returned 0 on failure"
}

test_add_dry_run_id_unique() {
  echo "== add dry-run id uniqueness =="
  CLI add-job --type command --id cmdjob --program /bin/true --schedule 01:01 >/dev/null 2>&1 || true
  local rc=0
  CLI add-job --type command --id cmdjob --program /bin/true --schedule 02:02 --dry-run >/dev/null 2>&1 || rc=$?
  [[ "$rc" != "0" ]] && ok "add --dry-run rejects duplicate id" || bad "add --dry-run allowed duplicate id"
}

test_resolve_no_type_slug() {
  echo "== resolve-instance type slug =="
  local out rc=0
  out="$(CLI resolve-instance --query incremental-git-fetch 2>&1)" || rc=$?
  [[ "$rc" != "0" || "$out" != *$'\tincremental-git-fetch'* ]] && ok "resolve does not return bare type slug for multi type" || bad "resolve returned type slug as instance: $out"
}

test_store_flock() {
  echo "== store flock =="
  local store="$SB/state/jobs/flock-test.yml" rc=0
  printf 'schema: jobs/v1\nversion: 1\ninstances: []\n' > "$store"
  "$PY" - "$store" <<'PY' || rc=$?
import concurrent.futures, json, os, subprocess, sys
from pathlib import Path
store = Path(sys.argv[1])
py = os.environ["LOCAL_JOBS_PYTHON"]
lib = Path(os.environ["LOCAL_JOBS_HOME"]) / "lib" / "store.py"

def bump(n):
    entry = json.dumps({"id": f"id{n}", "program": "/bin/true", "schedule": "01:00", "enabled": True})
    subprocess.run([py, str(lib), "--file", str(store), "--schema-version", "1",
                    "--defaults", "{}", "--required", '["program","schedule"]',
                    "add", "--entry", entry], check=True, capture_output=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(bump, range(20)))

data = json.loads(subprocess.run([py, str(lib), "--file", str(store), "list"],
                                 capture_output=True, text=True, check=True).stdout)
ids = [e["id"] for e in data]
assert len(ids) == len(set(ids)) == 20, (len(ids), len(set(ids)))
PY
  [[ "$rc" == "0" ]] && ok "store flock serializes concurrent adds" || bad "store flock test failed"
}

test_cursor_project_slug() {
  echo "== cursor project slug =="
  local fake_home="$SB/fake-home" root="/Users/sample.user/work/foo"
  local dotted="Users-sample.user-work-foo" hyphen="Users-sample-user-work-foo" slug dir
  mkdir -p "$fake_home/.cursor/projects"

  slug="$(LOCAL_JOBS_CURSOR_PROJECTS_DIR="$fake_home/.cursor/projects" bash -c '. "$1/lib/common.sh"; cursor_project_slug "$2"' _ "$REAL_HOME" "$root")"
  [[ "$slug" == "$hyphen" ]] && ok "defaults to hyphen slug when neither dir exists" || bad "default slug=$slug want $hyphen"

  mkdir -p "$fake_home/.cursor/projects/$dotted"
  slug="$(LOCAL_JOBS_CURSOR_PROJECTS_DIR="$fake_home/.cursor/projects" bash -c '. "$1/lib/common.sh"; cursor_project_slug "$2"' _ "$REAL_HOME" "$root")"
  [[ "$slug" == "$dotted" ]] && ok "prefers dotted dir when only dotted exists" || bad "dotted-only slug=$slug"

  mkdir -p "$fake_home/.cursor/projects/$hyphen"
  slug="$(LOCAL_JOBS_CURSOR_PROJECTS_DIR="$fake_home/.cursor/projects" bash -c '. "$1/lib/common.sh"; cursor_project_slug "$2"' _ "$REAL_HOME" "$root")"
  [[ "$slug" == "$hyphen" ]] && ok "prefers hyphen dir when both exist" || bad "both-exist slug=$slug want $hyphen"

  rm -rf "$fake_home/.cursor/projects/$dotted"
  slug="$(LOCAL_JOBS_CURSOR_PROJECTS_DIR="$fake_home/.cursor/projects" bash -c '. "$1/lib/common.sh"; cursor_project_slug "$2"' _ "$REAL_HOME" "$root")"
  [[ "$slug" == "$hyphen" ]] && ok "prefers hyphen dir when only hyphen exists" || bad "hyphen-only slug=$slug"

  dir="$(LOCAL_JOBS_CURSOR_PROJECTS_DIR="$fake_home/.cursor/projects" LOCAL_JOBS_CURSOR_WORKSPACE="$root" bash -c '. "$1/lib/common.sh"; cursor_workspace_canvas_dir' _ "$REAL_HOME")"
  [[ "$dir" == "$fake_home/.cursor/projects/$hyphen/canvases" ]] && ok "canvas dir uses resolved slug" || bad "canvas dir=$dir"
}

test_wrapper_exports_env() {
  echo "== wrapper env exports =="
  local out
  out="$(LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_PRESERVE_HARNESS_ENV=1 LOCAL_JOBS_STATE="$SB/state" \
    "$REAL_HOME/scripts/local-jobs.sh" handler-path --type command 2>&1)"
  [[ "$out" == "$REAL_HOME/handlers/command.sh" ]] && ok "wrapper resolves handler with exports" || bad "wrapper handler: $out"
}

# --- Milestone 1: truthful per-repo outcomes --------------------------------
# Helpers build an isolated igf state so a sweep's parent/child records are fully
# controlled and never touch the shared `reference` history other tests rely on.

# m1_make_state <state-dir> <id:ok|fail> ...   (LJ_FAILPOLICY env → failure_policy)
#   ok repos are real git repos on `master` (fetch succeeds); fail repos point at
#   a missing path so fetch-repo.sh dies (a deterministic, network-free failure).
m1_make_state() {
  local state="$1"; shift
  local policy="${LJ_FAILPOLICY:-continue}"
  local repos="$state/repos" cfg="$state/jobs/incremental-git-fetch.yml"
  mkdir -p "$state/jobs" "$state/agents" "$state/logs" "$repos"
  {
    printf 'schema: jobs/v1\nversion: 1\n'
    printf 'defaults: {remote: origin, branch: master, enabled: true, filter_blobs: true, ff_only_merge: true, schedule: inherit}\n'
    printf 'global:\n  dev_root: %s\n  failure_policy: %s\n  launchd: {window_start_hour: 18, window_end_hour: 24, use_jitter: true}\n  logging: {dir: %s}\n' "$repos" "$policy" "$state/logs"
    printf 'repos:\n'
  } > "$cfg"
  local spec id kind
  for spec in "$@"; do
    id="${spec%%:*}"; kind="${spec##*:}"
    if [[ "$kind" == ok ]]; then
      git init -q "$repos/$id" 2>/dev/null
      git -C "$repos/$id" symbolic-ref HEAD refs/heads/master 2>/dev/null
      git -C "$repos/$id" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init 2>/dev/null
      git -C "$repos/$id" remote add origin "$repos/$id/.git" 2>/dev/null || true
      printf -- '- {id: %s, path: %s, remote: origin, branch: master, enabled: true, schedule: inherit}\n' "$id" "$id" >> "$cfg"
    else
      printf -- '- {id: %s, path: %s, remote: origin, branch: master, enabled: true, schedule: inherit}\n' "$id" "no-such-$id" >> "$cfg"
    fi
  done
}

m1_cli() {  # <state-dir> <local-jobs.sh args...>
  local state="$1"; shift
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" \
      LOCAL_JOBS_STATE="$state" LOCAL_JOBS_IGF_CONFIG="$state/jobs/incremental-git-fetch.yml" \
      LOCAL_JOBS_COMMAND_CONFIG="$SB/state/jobs/command.yml" LOCAL_JOBS_IGF_DEV_ROOT="$state/repos" \
      LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" \
      "$SB/bin/local-jobs.sh" "$@"
}

m1_dispatch() {  # <state-dir> <dispatch-run.sh args...>  (overlay types live in <state>/registry.d)
  local state="$1"; shift
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" \
      LOCAL_JOBS_STATE="$state" LOCAL_JOBS_PYTHON="$PY" \
      LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$state/agents" \
      "$SB/bin/dispatch-run.sh" "$@"
}

m1_records() {  # <state-dir> <job-id>  → JSON array of that id's run records
  local state="$1" id="$2"
  env LOCAL_JOBS_STATE="$state" LOCAL_JOBS_HOME="$SB" "$PY" "$SB/lib/run_log.py" recent --limit 50 --id "$id"
}

test_m1_mixed_sweep_truthful() {
  echo "== M1: mixed sweep (2 ok + 1 fail) truthful outcomes =="
  local st="$SB/m1-mixed"
  m1_make_state "$st" a:ok b:ok bad:fail
  m1_cli "$st" run-job --type incremental-git-fetch --id __global__ >/dev/null 2>&1 || true
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r, "no parent record"
assert r[-1]["status"]=="completed_with_failures", r[-1]["status"]
c=r[-1]["fields"].get("counts") or {}
assert c=={"total":3,"succeeded":2,"failed":1,"skipped":0}, c' 2>/dev/null \
    && ok "parent completed_with_failures + truthful counts" || bad "parent status/counts wrong"
  m1_records "$st" a | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="success" and r[-1]["rc"]==0, r[-1]' 2>/dev/null \
    && ok "successful child recorded success (rc 0)" || bad "successful child not clean success"
  m1_records "$st" bad | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="failure", r[-1]' 2>/dev/null \
    && ok "failed child recorded failure" || bad "failed child not failure"
  m1_cli "$st" dashboard --json 2>/dev/null | "$PY" -c '
import json,sys
d=json.load(sys.stdin)
insts={i.get("id"):i for i in d["instances"]}
assert d["summary"]["failing"]==1, d["summary"]
g=next(i for i in d["instances"] if i.get("role")=="global_scheduler")
assert g["run_stats"]["last_run"]["status"]=="completed_with_failures", g["run_stats"]["last_run"]
assert insts["a"]["run_stats"]["consecutive_failures"]==0, insts["a"]["run_stats"]' 2>/dev/null \
    && ok "dashboard: 1 failing (no false streak on ok child), sweep mixed" || bad "dashboard mixed wiring wrong"
}

test_m1_continue_attempts_all() {
  echo "== M1: failure_policy=continue attempts every repo =="
  local st="$SB/m1-continue"
  LJ_FAILPOLICY=continue m1_make_state "$st" ok1:ok bad1:fail ok2:ok
  m1_cli "$st" run-job --type incremental-git-fetch --id __global__ >/dev/null 2>&1 || true
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)[-1]
assert r["status"]=="completed_with_failures", r["status"]
c=r["fields"]["counts"]
assert c=={"total":3,"succeeded":2,"failed":1,"skipped":0}, c' 2>/dev/null \
    && ok "continue: parent completed_with_failures, nothing skipped" || bad "continue counts wrong"
  local miss=0 rr n
  for rr in ok1 bad1 ok2; do
    n="$(m1_records "$st" "$rr" | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
    [[ "$n" -ge 1 ]] || miss=1
  done
  [[ "$miss" == 0 ]] && ok "continue: every repo attempted (a child event each)" || bad "continue: a repo was skipped"
}

test_m1_stop_skips_later_preserves_streak() {
  echo "== M1: failure_policy=stop skips later repos, prior streak survives =="
  local st="$SB/m1-stop"
  LJ_FAILPOLICY=stop m1_make_state "$st" first:ok boom:fail later:ok
  # A real, pre-existing failing streak on `later` that a skip must not reset.
  printf '%s\n' \
    '{"schema":"runlog/v1","ts":"2026-07-01T00:00:00+00:00","job_id":"later","type":"incremental-git-fetch","status":"failure","duration_s":1,"rc":1,"summary":"real fail 1","fields":{}}' \
    '{"schema":"runlog/v1","ts":"2026-07-01T00:05:00+00:00","job_id":"later","type":"incremental-git-fetch","status":"failure","duration_s":1,"rc":1,"summary":"real fail 2","fields":{}}' \
    >> "$st/runs.jsonl"
  local before after
  before="$(m1_records "$st" later | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  m1_cli "$st" run-job --type incremental-git-fetch --id __global__ >/dev/null 2>&1 || true
  after="$(m1_records "$st" later | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  [[ "$before" == 2 && "$after" == 2 ]] \
    && ok "stop: skipped repo emits no child event (${before}->${after})" || bad "stop: later records ${before}->${after} (want 2->2)"
  m1_cli "$st" dashboard --json 2>/dev/null | "$PY" -c '
import json,sys
d=json.load(sys.stdin)
g=next(i for i in d["instances"] if i.get("role")=="global_scheduler")
lr=g["run_stats"]["last_run"]
assert lr["status"]=="completed_with_failures", lr["status"]
assert (lr["fields"].get("counts") or {}).get("skipped",0)>=1, lr["fields"].get("counts")
later=next(i for i in d["instances"] if i.get("id")=="later")
assert later["run_stats"]["consecutive_failures"]==2, later["run_stats"]["consecutive_failures"]' 2>/dev/null \
    && ok "stop: parent counts the skip; prior real streak survives" || bad "stop: skip/streak wiring wrong"
}

test_m1_reconcile_no_child_flip() {
  echo "== M1: reconcile — non-zero parent never flips a truthful success child =="
  local st="$SB/m1-recon"; mkdir -p "$st/registry.d" "$st/agents" "$st/jobs"
  local h="$st/m1recon.sh"
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"m1recon","cardinality":"singleton","label_token":"m1recon","add_schema":[]}\n' ;;
  list-instances) printf '[]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  run)
    printf '@@RUNLOG@@ {"status":"completed_with_failures","fields":{"target":"all","counts":{"total":2,"succeeded":1,"failed":1,"skipped":0}},"per_instance":[{"job_id":"kid_ok","status":"success","fields":{"reason":"up to date"}},{"job_id":"kid_bad","status":"failure","fields":{"reason":"boom"}}]}\n'
    exit 1 ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  printf 'id: m1recon\nhandler: "%s"\n' "$h" > "$st/registry.d/m1recon.yml"
  m1_dispatch "$st" --type m1recon >/dev/null 2>&1 || true
  m1_records "$st" kid_ok | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="success" and r[-1]["rc"]==0, r[-1]' 2>/dev/null \
    && ok "success child stays success despite non-zero parent rc" || bad "success child was flipped"
  m1_records "$st" kid_bad | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="failure" and r[-1]["rc"]!=0, r[-1]' 2>/dev/null \
    && ok "failure child recorded failure by its own rc" || bad "failure child wrong"
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="completed_with_failures", r[-1]["status"]' 2>/dev/null \
    && ok "parent stays completed_with_failures (rc=1 not overloaded)" || bad "parent status wrong"
}

test_m1_usage_exit2_is_failure() {
  echo "== M1: usage exit 2 records failure, never completed_with_failures =="
  local st="$SB/m1-usage"; mkdir -p "$st/registry.d" "$st/agents" "$st/jobs"
  local h="$st/m1usage.sh"
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"m1usage","cardinality":"singleton","label_token":"m1usage","add_schema":[]}\n' ;;
  list-instances) printf '[]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  run) printf 'm1usage: bad usage\n' >&2; exit 2 ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  printf 'id: m1usage\nhandler: "%s"\n' "$h" > "$st/registry.d/m1usage.yml"
  local rc=0
  m1_dispatch "$st" --type m1usage >/dev/null 2>&1 || rc=$?
  [[ "$rc" == 2 ]] && ok "usage exit 2 propagates as rc 2 (not overloaded)" || bad "usage rc was $rc (want 2)"
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r and r[-1]["status"]=="failure", r[-1]["status"]' 2>/dev/null \
    && ok "usage error recorded as failure, not completed_with_failures" || bad "usage error status wrong"
}

test_m1_clean_run_clears_bogus_streak() {
  echo "== M1: one clean run clears a bogus streak with no history rewrite =="
  local st="$SB/m1-clear"
  m1_make_state "$st" clearme:ok
  printf '%s\n' \
    '{"schema":"runlog/v1","ts":"2026-07-01T00:00:00+00:00","job_id":"clearme","type":"incremental-git-fetch","status":"failure","duration_s":1,"rc":1,"summary":"bogus1","fields":{}}' \
    '{"schema":"runlog/v1","ts":"2026-07-01T00:05:00+00:00","job_id":"clearme","type":"incremental-git-fetch","status":"failure","duration_s":1,"rc":1,"summary":"bogus2","fields":{}}' \
    >> "$st/runs.jsonl"
  local before
  before="$(m1_records "$st" clearme | "$PY" -c 'import json,sys; print("|".join(x.get("summary") or "" for x in json.load(sys.stdin)))')"
  m1_cli "$st" run-job --type incremental-git-fetch --id clearme >/dev/null 2>&1 || true
  m1_records "$st" clearme | BEFORE="$before" "$PY" -c '
import json,os,sys
r=json.load(sys.stdin)
assert len(r)==3, len(r)  # append-only: two bogus + one new
assert "|".join(x.get("summary") or "" for x in r[:2])==os.environ["BEFORE"], [x.get("summary") for x in r[:2]]
assert r[-1]["status"]=="success" and r[-1]["rc"]==0, r[-1]
cf=0
for x in reversed(r):
    if x["status"]=="failure": cf+=1
    else: break
assert cf==0, cf' 2>/dev/null \
    && ok "clean run: streak cleared, history appended not rewritten" || bad "streak/history wrong"
}

test_m2_display_fallback_precedence() {
  echo "== M2: display_name/description fallback + precedence =="
  local named="m2named" bare="m2bare"
  CLI add-job --type command --id "$named" --program /bin/echo --arg=hi --schedule 05:05 \
    --display-name "Nightly Echo" --description "Says hi every night." >/dev/null 2>&1 \
    && ok "add command with display_name/description" || bad "add named command"
  CLI add-job --type command --id "$bare" --program /bin/echo --arg=hi --schedule 05:06 >/dev/null 2>&1 \
    && ok "add command without identity" || bad "add bare command"
  H command view --id "$named" | "$PY" -c '
import json,sys
i=json.load(sys.stdin)
assert i.get("display_name")=="Nightly Echo", i
assert i.get("description")=="Says hi every night.", i
' 2>/dev/null && ok "store carries display_name/description" || bad "store dropped identity fields"
  # Omitted fields are simply absent -> display falls back to id at render time.
  H command view --id "$bare" | "$PY" -c '
import json,sys
i=json.load(sys.stdin)
assert "display_name" not in i, i
assert "description" not in i, i
' 2>/dev/null && ok "bare command stores no phantom identity fields" || bad "bare command got phantom fields"
  # Precedence: a user description wins over the derived overview; a bare job
  # still gets a non-empty derived overview (never blank).
  CLI dashboard --json 2>/dev/null | "$PY" -c '
import json,sys
d=json.load(sys.stdin)
named=next(i for i in d["instances"] if i.get("id")=="m2named")
assert named.get("overview")=="Says hi every night.", named.get("overview")
assert named.get("display_name")=="Nightly Echo", named
bare=next(i for i in d["instances"] if i.get("id")=="m2bare")
assert bare.get("overview"), bare
assert bare.get("overview")!="Says hi every night.", bare
' 2>/dev/null && ok "overview precedence: description > derived overview" || bad "overview precedence wrong"
  CLI delete-job --id "$named" --confirm >/dev/null 2>&1 && CLI delete-job --id "$bare" --confirm >/dev/null 2>&1 \
    && ok "cleanup named/bare commands" || bad "cleanup named/bare commands"
}

test_m2_execution_mode_on_demand() {
  echo "== M2: execution_mode on_demand (no timer, no drift, runnable) =="
  local id="m2ondemand" plist="$SB/agents/com.local-jobs.command.m2ondemand.plist"
  # No schedule is required for an on_demand job (required_unless waiver).
  CLI add-job --type command --id "$id" --program /bin/echo --arg=poke --execution-mode on_demand >/dev/null 2>&1 \
    && ok "add on_demand command with no schedule" || bad "on_demand add rejected"
  [[ ! -f "$plist" ]] && ok "on_demand installs no launchd agent" || bad "on_demand installed an agent"
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("execution_mode")=="on_demand"' 2>/dev/null \
    && ok "store records execution_mode on_demand" || bad "execution_mode not stored"
  # With launchd "live" (DISABLE=0) a scheduled+unloaded job would drift; on_demand must not.
  "$PY" -c "
import json, subprocess, os
env=os.environ.copy(); env['LOCAL_JOBS_LAUNCHD_DISABLE']='0'
p=subprocess.run(['$SB/bin/local-jobs.sh','dashboard','--json'],capture_output=True,text=True,env=env)
d=json.loads(p.stdout)
j=next(i for i in d['instances'] if i.get('id')=='$id')
assert not j.get('drift'), j
assert not j.get('stale'), j
assert j['next_run']['basis']=='on_demand', j['next_run']
assert d['summary'].get('on_demand',0)>=1, d['summary']
" 2>/dev/null && ok "on_demand: no drift/stale, on_demand basis, summary count" || bad "on_demand dashboard dishonest"
  CLI run-job --id "$id" --dry-run 2>/dev/null | "$PY" -c 'import sys; s=sys.stdin.read(); assert "@@RUNLOG@@" in s and "dry-run" in s' \
    && ok "on_demand job runnable via run-job" || bad "on_demand not runnable"
  # repair must keep it agent-free AND preserve the field (no drift, no data loss).
  CLI repair-job --id "$id" >/dev/null 2>&1 || bad "on_demand repair failed"
  [[ ! -f "$plist" ]] && ok "repair keeps on_demand agent-free" || bad "repair installed an agent for on_demand"
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("execution_mode")=="on_demand"' 2>/dev/null \
    && ok "repair preserves execution_mode" || bad "repair dropped execution_mode"
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 && ok "on_demand delete" || bad "on_demand delete"
}

test_m2_gitfetch_metadata_roundtrip() {
  echo "== M2: git-fetch display_name/description round-trip =="
  CLI update-job --type incremental-git-fetch --id reference \
    --display-name "Reference mirror" --description "Nightly filtered fetch of the reference clone." >/dev/null 2>&1 \
    && ok "set git-fetch repo identity via update-job" || bad "git-fetch set-fields failed"
  H incremental-git-fetch view --id reference | "$PY" -c '
import json,sys
i=json.load(sys.stdin)
assert i.get("display_name")=="Reference mirror", i
assert i.get("description")=="Nightly filtered fetch of the reference clone.", i
' 2>/dev/null && ok "git-fetch repo identity reads back" || bad "git-fetch identity not persisted"
  CLI update-job --type incremental-git-fetch --id __global__ --global \
    --display-name "Evening git-fetch sweep" >/dev/null 2>&1 \
    && ok "set git-fetch global identity" || bad "git-fetch global set-fields failed"
  H incremental-git-fetch view --id __global__ | "$PY" -c '
import json,sys
assert json.load(sys.stdin).get("display_name")=="Evening git-fetch sweep"
' 2>/dev/null && ok "git-fetch global identity reads back" || bad "git-fetch global identity missing"
  # An unrelated schedule/enabled update must not clobber the stored identity.
  CLI update-job --type incremental-git-fetch --id reference --enabled true >/dev/null 2>&1 || true
  H incremental-git-fetch view --id reference | "$PY" -c '
import json,sys
assert json.load(sys.stdin).get("display_name")=="Reference mirror"
' 2>/dev/null && ok "identity survives an unrelated update" || bad "identity clobbered by unrelated update"
  # failure_policy is global-only and settable through the same supported verb.
  CLI update-job --type incremental-git-fetch --id __global__ --global --failure-policy stop >/dev/null 2>&1 \
    && ok "set git-fetch failure_policy via update-job" || bad "failure_policy set-fields failed"
  H incremental-git-fetch view --id __global__ | "$PY" -c '
import json,sys
assert json.load(sys.stdin).get("failure_policy")=="stop"
' 2>/dev/null && ok "failure_policy reads back on global instance" || bad "failure_policy not persisted"
  CLI update-job --type incremental-git-fetch --id __global__ --global --failure-policy bogus >/dev/null 2>&1 \
    && bad "invalid failure_policy accepted" || ok "invalid failure_policy rejected"
  # Restore the default so we leave the sandbox global block clean.
  CLI update-job --type incremental-git-fetch --id __global__ --global --failure-policy continue >/dev/null 2>&1 || true
}

test_m2_migrate_fills_only_missing() {
  echo "== M2: migrate fills missing execution_mode, never overwrites =="
  "$PY" - "$SB/state/jobs/command.yml" <<'PY'
import sys, yaml
path=sys.argv[1]
data=yaml.safe_load(open(path)) or {"schema":"jobs/v1","version":1,"instances":[]}
data.setdefault("instances", [])
data["instances"].append({"id":"m2legacy","program":"/bin/true","schedule":"01:01","enabled":True,"display_name":"Legacy Name"})
data["instances"].append({"id":"m2already","program":"/bin/true","schedule":{"kind":"interval","seconds":2147483647},"enabled":True,"execution_mode":"on_demand"})
yaml.safe_dump(data, open(path,"w"), sort_keys=False)
PY
  H command migrate >/dev/null 2>&1 || bad "command migrate failed"
  H command view --id m2legacy | "$PY" -c '
import json,sys
i=json.load(sys.stdin)
assert i.get("execution_mode")=="scheduled", i  # backfilled default
assert i.get("display_name")=="Legacy Name", i  # pre-existing value untouched
' 2>/dev/null && ok "migrate backfills scheduled + keeps display_name" || bad "migrate mishandled legacy entry"
  H command view --id m2already | "$PY" -c '
import json,sys
assert json.load(sys.stdin).get("execution_mode")=="on_demand"
' 2>/dev/null && ok "migrate never overwrites explicit on_demand" || bad "migrate clobbered explicit on_demand"
  CLI delete-job --id m2legacy --confirm >/dev/null 2>&1
  CLI delete-job --id m2already --confirm >/dev/null 2>&1
  ok "migrate-fills-only-missing cleanup"
}

test_m2_shim_migration() {
  echo "== M2: action-shim migration to on_demand via supported verbs =="
  local id="m2shim" plist="$SB/agents/com.local-jobs.command.m2shim.plist"
  # Pre-M2 shim shape: sentinel interval, paused, triggered only on demand.
  CLI add-job --type command --id "$id" --program /bin/echo --arg=action \
    --interval-seconds 2147483647 --enabled false >/dev/null 2>&1 \
    && ok "add legacy sentinel shim (paused)" || bad "legacy shim add"
  [[ ! -f "$plist" ]] && ok "paused shim has no agent" || bad "paused shim installed agent"
  # Migrate through the supported update path (never hand-edit YAML).
  CLI update-job --id "$id" --execution-mode on_demand --enabled true >/dev/null 2>&1 \
    && ok "migrate shim to on_demand + enabled" || bad "shim migrate failed"
  [[ ! -f "$plist" ]] && ok "on_demand shim stays agent-free even when enabled" || bad "on_demand enabled installed agent"
  "$PY" -c "
import json, subprocess, os
env=os.environ.copy(); env['LOCAL_JOBS_LAUNCHD_DISABLE']='0'
p=subprocess.run(['$SB/bin/local-jobs.sh','dashboard','--json'],capture_output=True,text=True,env=env)
d=json.loads(p.stdout)
j=next(i for i in d['instances'] if i.get('id')=='$id')
assert j.get('execution_mode')=='on_demand', j
assert j.get('enabled') is True, j
assert not j.get('drift') and not j.get('stale'), j
assert j['next_run']['basis']=='on_demand', j['next_run']
" 2>/dev/null && ok "migrated shim: on_demand, enabled, no drift" || bad "shim migration dishonest"
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 && ok "shim delete" || bad "shim delete"
}

# --- Milestone 3: PM-operable dashboard ------------------------------------

test_running_long() {
  echo "== M3: running-long flag (observability only, no auto-kill) =="
  local st="$SB/m3-runlong"
  mkdir -p "$st/jobs" "$st/agents" "$st/running"
  cat > "$st/jobs/command.yml" <<'EOF'
schema: jobs/v1
version: 1
instances:
- {id: longrunner, program: /bin/true, schedule: "01:00", enabled: true}
- {id: quickrunner, program: /bin/true, schedule: "01:00", enabled: true}
EOF
  # Both jobs have a short typical duration (~60s) via the append-only run log.
  {
    printf '{"schema":"runlog/v1","ts":"2026-06-30T00:00:00+00:00","job_id":"longrunner","type":"command","status":"success","duration_s":60,"rc":0,"summary":"ok","fields":{}}\n'
    printf '{"schema":"runlog/v1","ts":"2026-06-30T00:00:00+00:00","job_id":"quickrunner","type":"command","status":"success","duration_s":60,"rc":0,"summary":"ok","fields":{}}\n'
  } >> "$st/runs.jsonl"
  # Live markers ($$ is alive): longrunner started 30 min before "now" (>> 3x
  # typical + 300s floor), quickrunner only 5s ago (well within typical).
  printf '{"pid":%s,"ts":"2026-07-01T11:30:00+00:00","type":"command","job_id":"longrunner"}\n' "$$" > "$st/running/command__longrunner.json"
  printf '{"pid":%s,"ts":"2026-07-01T11:59:55+00:00","type":"command","job_id":"quickrunner"}\n' "$$" > "$st/running/command__quickrunner.json"
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" LOCAL_JOBS_STATE="$st" \
      LOCAL_JOBS_IGF_CONFIG="$st/jobs/missing-igf.yml" LOCAL_JOBS_COMMAND_CONFIG="$st/jobs/command.yml" \
      LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$st/agents" \
      LOCAL_JOBS_NOW="2026-07-01T12:00:00+00:00" LOCAL_JOBS_PYTHON="$PY" \
      "$SB/bin/local-jobs.sh" dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
insts = {i.get("id"): i for i in d["instances"]}
lr, qr = insts["longrunner"], insts["quickrunner"]
assert lr.get("running") is True, lr.get("running")
assert lr.get("running_long") is True, lr
assert lr.get("running_since") == "2026-07-01T11:30:00+00:00", lr.get("running_since")
assert qr.get("running") is True, qr.get("running")
assert qr.get("running_long") is False, qr
' 2>/dev/null && ok "long run flagged running_long, quick run not" || bad "running_long wiring wrong"
  # A run with no duration history has no basis to flag (never running_long).
  rm -f "$st/runs.jsonl"
  printf '{"pid":%s,"ts":"2026-07-01T11:30:00+00:00","type":"command","job_id":"longrunner"}\n' "$$" > "$st/running/command__longrunner.json"
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml" LOCAL_JOBS_STATE="$st" \
      LOCAL_JOBS_IGF_CONFIG="$st/jobs/missing-igf.yml" LOCAL_JOBS_COMMAND_CONFIG="$st/jobs/command.yml" \
      LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$st/agents" \
      LOCAL_JOBS_NOW="2026-07-01T12:00:00+00:00" LOCAL_JOBS_PYTHON="$PY" \
      "$SB/bin/local-jobs.sh" dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
lr = next(i for i in d["instances"] if i.get("id") == "longrunner")
assert lr.get("running") is True, lr.get("running")
assert lr.get("running_long") is False, lr  # no history -> no basis to flag
' 2>/dev/null && ok "no duration history never flags running_long" || bad "running_long flagged without history"
}

test_pm_summary_buckets_reconcile() {
  echo "== M3: PM summary buckets reconcile (exhaustive + mutually exclusive) =="
  CLI dashboard --json 2>/dev/null | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
insts = d["instances"]
b = d["summary"]["buckets"]
# Exhaustive + mutually exclusive: every instance lands in exactly one bucket.
assert sum(b.values()) == len(insts), (b, len(insts))
# Independent recomputation with the same rules the canvas uses.
def needs_attention(i):
    rs = i.get("run_stats") or {}
    last = rs.get("last_run") or {}
    return bool(i.get("role") == "error" or rs.get("consecutive_failures", 0) > 0
                or i.get("drift") or i.get("stale") or last.get("status") == "completed_with_failures")
h = a = p = od = 0
for i in insts:
    if needs_attention(i): a += 1
    elif i.get("execution_mode") == "on_demand": od += 1
    elif i.get("enabled") is False: p += 1
    else: h += 1
assert b == {"healthy": h, "needs_attention": a, "paused": p, "on_demand": od}, (b, h, a, p, od)
' 2>/dev/null && ok "buckets sum to instance count and match canvas rules" || bad "PM buckets do not reconcile"
}

test_canvas_control_bridge() {
  echo "== M3: canvas control bridge (Pause/Resume operational toggle) =="
  local id="ctlcmd" sidecar="$SB/canvases/local-jobs-dashboard.generated.canvas.data.json"
  local last="$SB/state/canvas-bridge/last-control-request.json" ledger="$SB/state/canvas-bridge/seen-control-requests.json"
  local plist="$SB/agents/com.local-jobs.command.ctlcmd.plist"
  CLI add-job --type command --id "$id" --program /bin/echo --arg=ok --schedule 03:06 >/dev/null 2>&1 || { bad "control fixture add"; return; }
  [[ -f "$plist" ]] && ok "control fixture is scheduled (agent present)" || bad "control fixture missing agent"

  # 1) Pause -> runs the validated disable-job verb (single safe config-writer).
  write_canvas_control_request "$sidecar" "$id" pause "c1"
  local rc=0
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" == "0" ]] && ok "bridge accepts pause request" || bad "bridge pause rc=$rc"
  [[ ! -f "$plist" ]] && ok "pause removed the launchd agent (disable-job ran)" || bad "pause did not disable job"
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("enabled") is False' 2>/dev/null \
    && ok "pause set enabled=false via the verb" || bad "pause enabled state wrong"
  [[ -f "$ledger" ]] && ok "control ledger written" || bad "control ledger missing"
  "$PY" - "$last" <<'PY' && ok "pause ledgered accepted" || bad "pause ledger wrong"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["kind"] == "control", d
assert d["status"] == "accepted", d
assert d["reason"] == "pause", d
assert d["nonce"] == "c1", d
PY

  # 2) Duplicate nonce is a no-op (idempotent, ledger-deduped).
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "duplicate control nonce exits 0" || bad "duplicate control nonce"
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("enabled") is False' 2>/dev/null \
    && ok "duplicate nonce did not re-toggle" || bad "duplicate nonce re-toggled"

  # 3) Resume -> runs enable-job, agent restored.
  write_canvas_control_request "$sidecar" "$id" resume "c2"
  rc=0; "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" == "0" && -f "$plist" ]] && ok "resume restored the agent (enable-job ran)" || bad "resume did not enable job"
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("enabled") is True' 2>/dev/null \
    && ok "resume set enabled=true via the verb" || bad "resume enabled state wrong"

  # 4) Invalid action -> rejected, no state change.
  write_canvas_control_request "$sidecar" "$id" sabotage "c3"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge tolerates invalid control action" || bad "invalid control action rc"
  "$PY" - "$last" <<'PY' && ok "invalid action ledgered rejected" || bad "invalid action ledger wrong"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["status"] == "rejected", d
assert d["reason"] == "invalid-control-action", d
PY
  H command view --id "$id" | "$PY" -c 'import json,sys; assert json.load(sys.stdin).get("enabled") is True' 2>/dev/null \
    && ok "invalid action left job unchanged" || bad "invalid action changed job"

  # 5) Control on the global sweep row -> rejected (no schedule to pause as a whole).
  write_canvas_control_request "$sidecar" "__global__" pause "c4"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge rejects global-row pause" || bad "global pause rc"
  "$PY" - "$last" <<'PY' && ok "global control rejected (unsupported role)" || bad "global control ledger wrong"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["status"] == "rejected", d
assert d["reason"] == "unsupported-row-role", d
PY
  CLI delete-job --id "$id" --confirm >/dev/null 2>&1 || true
}

test_canvas_view_bridge() {
  echo "== canvas view bridge (Refresh -> local-jobs view) =="
  local sidecar="$SB/canvases/local-jobs-dashboard.generated.canvas.data.json"
  local last="$SB/state/canvas-bridge/last-view-request.json" ledger="$SB/state/canvas-bridge/seen-view-requests.json"
  local live="$SB/canvases/local-jobs-dashboard.generated.canvas.tsx"
  rm -f "$live"
  write_canvas_view_request "$sidecar" "v1"
  local rc=0
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" == "0" && -f "$live" ]] && ok "bridge accepts view request and regenerates canvas" || bad "view bridge rc=$rc live=$live"
  [[ -f "$ledger" ]] && ok "view ledger written" || bad "view ledger missing"
  "$PY" - "$last" <<'PY' && ok "view request ledgered accepted" || bad "view ledger wrong"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["kind"] == "view", d
assert d["status"] == "accepted", d
assert d["reason"] == "view", d
assert d["nonce"] == "v1", d
PY

  local mtime_before mtime_after
  mtime_before="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "duplicate view nonce exits 0" || bad "duplicate view nonce"
  mtime_after="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  [[ "$mtime_before" == "$mtime_after" ]] && ok "duplicate view nonce does not re-run view" || bad "duplicate view nonce refreshed again"

  write_canvas_view_request "$sidecar" "v2"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge accepts second view nonce" || bad "bridge second view nonce"

  write_canvas_view_request "$sidecar" "stale-view" "1" "1970-01-01T00:00:00Z"
  mtime_before="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 && ok "bridge skips stale view request" || bad "bridge stale view request"
  mtime_after="$("$PY" - "$live" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).stat().st_mtime_ns)
PY
)"
  "$PY" - "$last" <<'PY' && [[ "$mtime_before" == "$mtime_after" ]] && ok "stale view request ledgered without view" || bad "stale view request reran or was not ledgered"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
assert d["nonce"] == "stale-view", d
assert d["status"] == "skipped", d
assert d["reason"] == "stale-request", d
PY
}

test_canvas_view_bridge_targets_request_workspace() {
  echo "== canvas view bridge targets the requesting workspace (not the skill repo) =="
  # Regression: a Refresh from a Cursor workspace canvas must regenerate the
  # canvas back INTO that workspace's canvases/ dir. The bridge runs from the
  # skill's own worktree, so before this fix `view` inferred its publish target
  # from that repo and dropped the fresh canvas in the wrong project, leaving the
  # operator's open canvas stale (Refresh looked like a no-op).
  # Simulate a Cursor projects root with an override (never mutate $HOME — that
  # breaks user-site imports like PyYAML inside canvas_bridge.py).
  local proj="$SB/view-ws-projects"
  local ws_dir="$proj/Users-sample-user-dev/canvases"
  mkdir -p "$ws_dir"
  # The only pending request must be the workspace one, so drop any home-dir
  # sidecar an earlier test left behind (candidate_sidecars scans both).
  rm -f "$SB/canvases/local-jobs-dashboard.generated.canvas.data.json"
  local sidecar="$ws_dir/local-jobs-dashboard.canvas.data.json"
  local published="$ws_dir/local-jobs-dashboard.canvas.tsx"
  rm -f "$published"
  write_canvas_view_request "$sidecar" "ws-view-1"
  local rc=0
  LOCAL_JOBS_CURSOR_PROJECTS_DIR="$proj" "$SB/bin/canvas-run-bridge.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" == "0" ]] && ok "workspace view request accepted" || bad "workspace view rc=$rc"
  [[ -f "$published" ]] && ok "canvas published INTO the requesting workspace dir" || bad "canvas not published to workspace dir: $published"
}

test_builder_snapshot_retired() {
  echo "== M3: job-builder retired (subtractive cleanup, no residue) =="
  [[ ! -e "$REAL_HOME/canvases/local-jobs-job-builder.canvas.tsx" ]] && ok "static builder canvas removed" || bad "builder canvas still present"
  [[ ! -e "$REAL_HOME/bin/generate-job-builder-snapshot.sh" ]] && ok "builder snapshot generator removed" || bad "builder snapshot script present"
  "$PY" "$SB/lib/registry.py" builder-snapshot >/dev/null 2>&1 && bad "registry builder-snapshot still runs" || ok "registry builder-snapshot subcommand gone"
  local hits=""
  hits="$(grep -rInE 'job-builder|builder-snapshot|build_builder_snapshot|generate-job-builder-snapshot' "$REAL_HOME" \
      --include='*.sh' --include='*.py' --include='*.md' --include='*.tsx' \
      --exclude='test-local-jobs.sh' --exclude='*.generated.canvas.tsx' 2>/dev/null || true)"
  [[ -z "$hits" ]] && ok "no job-builder references remain in tracked sources" || bad "job-builder references remain: $hits"
}

# ---------------------------------------------------------------------------
# Swarm review regression tests (fail-before / pass-after for the fixes landed
# by the end-to-end local-jobs-overhaul review).
# ---------------------------------------------------------------------------

test_swarm_di_update_requires_schedule() {
  echo "== swarm/DI-1: store.set re-checks conditional-required fields on update =="
  local f="$SB/swarm-di1.yml"
  local req='[{"field":"schedule","unless":{"field":"execution_mode","equals":"on_demand"}}]'
  printf 'schema: jobs/v1\nversion: 1\ninstances: []\n' > "$f"
  "$PY" "$SB/lib/store.py" --file "$f" --required "$req" add \
    --entry '{"id":"di1","program":"/bin/echo","execution_mode":"on_demand"}' >/dev/null 2>&1 \
    || { bad "DI-1 seed on_demand add"; return; }
  # Flipping on_demand -> scheduled with NO schedule must be rejected (was silently written).
  local src=0
  "$PY" "$SB/lib/store.py" --file "$f" --required "$req" set \
    --id di1 --patch '{"execution_mode":"scheduled"}' >/dev/null 2>&1 || src=$?
  [[ "$src" != "0" ]] && ok "DI-1: timerless scheduled flip rejected" || bad "DI-1: timerless flip wrongly accepted"
  "$PY" - "$f" <<'PY' 2>/dev/null && ok "DI-1: config unchanged (still on_demand, no schedule)" || bad "DI-1: timerless scheduled instance persisted"
import sys, yaml
d = yaml.safe_load(open(sys.argv[1])) or {}
i = next((e for e in d.get("instances", []) if e.get("id") == "di1"), None)
assert i is not None and i.get("execution_mode") == "on_demand" and i.get("schedule") in (None, ""), i
PY
  # The check is conditional, not blanket: a flip WITH a schedule still succeeds.
  "$PY" "$SB/lib/store.py" --file "$f" --required "$req" set \
    --id di1 --patch '{"execution_mode":"scheduled","schedule":"03:15"}' >/dev/null 2>&1 \
    && ok "DI-1: flip with a schedule still succeeds" || bad "DI-1: valid flip wrongly rejected"
}

test_swarm_igf_config_crash_is_failure() {
  echo "== swarm/REL-2: run-all aborts (non-zero) when the id-read crashes =="
  local st="$SB/swarm-rel2"; mkdir -p "$st/jobs" "$st/logs" "$st/repos"
  local cfg="$st/jobs/incremental-git-fetch.yml"
  # Valid YAML + a valid global block, but a repo entry with no id -> config.py
  # load_config raises during enabled-ids enumeration (exit != 0). The guarded
  # FAILURE_POLICY read survives (falls back to continue); the id-read is the sole
  # unguarded consumer, so this isolates the process-substitution swallow: the old
  # `< <(config_py ...)` ran zero repos and exited 0 (a masked "success").
  cat > "$cfg" <<'EOF'
schema: jobs/v1
version: 1
defaults: {remote: origin, branch: master, enabled: true, schedule: inherit}
global:
  launchd: {window_start_hour: 18, window_end_hour: 24, use_jitter: true}
repos:
- {path: no-id-here, enabled: true}
EOF
  local rc=0
  env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_STATE="$st" LOCAL_JOBS_IGF_CONFIG="$cfg" \
      LOCAL_JOBS_IGF_DEV_ROOT="$st/repos" LOCAL_JOBS_IGF_LOG_DIR="$st/logs" \
      LOCAL_JOBS_PYTHON="$PY" LOCAL_JOBS_IGF_SKIP_JITTER=1 LOCAL_JOBS_LAUNCHD_DISABLE=1 \
      "$SB/backends/incremental-git-fetch/run-all.sh" >/dev/null 2>&1 || rc=$?
  [[ "$rc" != "0" ]] && ok "REL-2: id-read crash aborts the sweep (rc=$rc)" || bad "REL-2: id-read crash swallowed -> sweep exited 0"
}

test_swarm_igf_dry_run_surfaces_failure() {
  echo "== swarm/REL-1: --dry-run surfaces a real repo failure (not masked as dry-run) =="
  local st="$SB/swarm-rel1"
  m1_make_state "$st" good:ok bad:fail
  LOCAL_JOBS_IGF_SKIP_JITTER=1 m1_cli "$st" run-job --type incremental-git-fetch --id __global__ --dry-run >/dev/null 2>&1 || true
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)[-1]
assert r["status"] in ("failure","completed_with_failures"), r["status"]
repos={x["id"]:x for x in r["fields"].get("repos",[])}
assert repos.get("bad",{}).get("status")=="failure", repos.get("bad")' 2>/dev/null \
    && ok "REL-1: dry-run reports the real per-repo failure honestly" || bad "REL-1: dry-run masked a real failure"
}

test_swarm_repair_reports_failures() {
  echo "== swarm/REL-3: repair reports per-instance install failures (rc!=0) =="
  local st="$SB/swarm-rel3" agents="$SB/swarm-rel3/agents" cfg="$SB/swarm-rel3/command.yml"
  mkdir -p "$agents" "$st"
  printf 'schema: jobs/v1\nversion: 1\ninstances: []\n' > "$cfg"
  local -a RUN=(env LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_REGISTRY="$SB/config/registry.yml"
    LOCAL_JOBS_STATE="$st" LOCAL_JOBS_COMMAND_CONFIG="$cfg" LOCAL_JOBS_PYTHON="$PY"
    LOCAL_JOBS_LAUNCHD_DISABLE=1 LOCAL_JOBS_LAUNCHAGENTS_DIR="$agents" "$SB/bin/local-jobs.sh")
  "${RUN[@]}" add-job --type command --id r3 --program /bin/echo --schedule 03:03 >/dev/null 2>&1 \
    || { bad "REL-3 fixture add"; return; }
  # Make the agents dir unwritable so the plist (re)write fails during repair.
  chmod 000 "$agents"
  local rc=0 out
  out="$("${RUN[@]}" repair-job --id r3 2>&1)" || rc=$?
  chmod 755 "$agents"
  { [[ "$rc" != "0" ]] && printf '%s' "$out" | grep -qi "fail"; } \
    && ok "REL-3: repair returns non-zero + reports the failed install" \
    || bad "REL-3: repair swallowed install failure (rc=$rc): $out"
}

test_swarm_pid_reuse_guard() {
  echo "== swarm/CON-3: recycled PID (start-time mismatch) is not reported running =="
  local st="$SB/swarm-con3"; mkdir -p "$st"
  sleep 30 & local livepid=$!
  LOCAL_JOBS_STATE="$st" "$PY" "$SB/lib/running.py" start --type command --id real --pid "$livepid" >/dev/null 2>&1
  LOCAL_JOBS_STATE="$st" "$PY" -c '
import sys; sys.path.insert(0, sys.argv[1])
import running
assert ("command","real") in running.active(), "genuine live run not reported running"' "$SB/lib" 2>/dev/null \
    && ok "CON-3: genuine live run reported running" || bad "CON-3: genuine live run missing"
  # Corrupt only the recorded start-time token: pid is still alive, identity differs.
  "$PY" - "$st/running/command__real.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.loads(open(p).read())
d["pid_start"] = "Thu Jan  1 00:00:00 1970"
open(p, "w").write(json.dumps(d))
PY
  LOCAL_JOBS_STATE="$st" "$PY" -c '
import sys; sys.path.insert(0, sys.argv[1])
import running
assert ("command","real") not in running.active(), "recycled pid falsely reported running"' "$SB/lib" 2>/dev/null \
    && ok "CON-3: start-time mismatch treated as not-running" || bad "CON-3: recycled pid false-positive"
  kill "$livepid" 2>/dev/null || true
}

test_swarm_malformed_runlog_failure() {
  echo "== swarm/REL-4: malformed @@RUNLOG@@ line records a parse failure =="
  local st="$SB/swarm-rel4"; mkdir -p "$st/registry.d" "$st/agents" "$st/jobs"
  local h="$st/swarmrel4.sh"
  cat > "$h" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  describe) printf '{"type":"swarmrel4","cardinality":"singleton","label_token":"swarmrel4","add_schema":[]}\n' ;;
  list-instances) printf '[]\n' ;;
  doctor) printf 'doctor: PASS\n' ;;
  run) printf '@@RUNLOG@@ {this is not valid json\n'; exit 0 ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$h"
  printf 'id: swarmrel4\nhandler: "%s"\n' "$h" > "$st/registry.d/swarmrel4.yml"
  m1_dispatch "$st" --type swarmrel4 >/dev/null 2>&1 || true
  m1_records "$st" all | "$PY" -c '
import json,sys
r=json.load(sys.stdin)
assert r, "no record"
last=r[-1]
assert last["status"]=="failure", last["status"]
assert last["fields"].get("runlog_parse_error"), last["fields"]' 2>/dev/null \
    && ok "REL-4: malformed runlog -> failure + runlog_parse_error" || bad "REL-4: malformed runlog mishandled"
}

test_swarm_needs_attention_parity() {
  echo "== swarm/DI-2: dashboard needs_attention/buckets parity fixture =="
  LOCAL_JOBS_HOME="$SB" LOCAL_JOBS_STATE="$SB/state" "$PY" - "$SB/lib" <<'PY' 2>/dev/null \
    && ok "DI-2: buckets/needs_attention match the pinned fixture + streak invariant" \
    || bad "DI-2: bucket/attention semantics drifted"
import sys
sys.path.insert(0, sys.argv[1])
import dashboard as d

def inst(**kw):
    base = {"role": "job", "enabled": True, "execution_mode": "scheduled",
            "drift": False, "stale": False,
            "run_stats": {"consecutive_failures": 0, "last_run": {"status": "success"}}}
    base.update(kw)
    return base

rows = [
    inst(id="healthy"),
    inst(id="failing", run_stats={"consecutive_failures": 2, "last_run": {"status": "failure"}}),
    inst(id="drifted", drift=True),
    inst(id="stale", stale=True),
    inst(id="mixed", run_stats={"consecutive_failures": 0, "last_run": {"status": "completed_with_failures"}}),
    inst(id="quarantined", role="error"),
    inst(id="ondemand", execution_mode="on_demand"),
    inst(id="paused", enabled=False),
]
expected = {"healthy": 1, "needs_attention": 5, "paused": 1, "on_demand": 1}
got = d._pm_buckets(rows)
assert got == expected, f"buckets {got} != {expected}"
assert sum(got.values()) == len(rows), (got, len(rows))
attn = {r["id"] for r in rows if d._needs_attention(r)}
assert attn == {"failing", "drifted", "stale", "mixed", "quarantined"}, attn
# Load-bearing invariant the TS needsAttention() relies on: _run_stats can never
# yield last_run.status=="failure" with consecutive_failures==0 (its streak loop
# starts from the newest record). If this breaks, the canvas (which also checks
# last_run.status) desyncs from _needs_attention() here.
st = d._run_stats([{"status": "failure", "ts": "2026-07-01T00:00:00+00:00", "duration_s": 1}])
assert st["last_run"]["status"] == "failure" and st["consecutive_failures"] >= 1, st
PY
}

# Run one test function, failing loudly if it is undefined (a dangling name in
# the list below must never be swallowed by `set -uo pipefail`).
run_test() {
  local name="$1"
  if ! declare -F "$name" >/dev/null 2>&1; then
    bad "MISSING test function: $name"
    return
  fi
  "$name"
  echo
}

main() {
  setup_sandbox
  echo "sandbox: $SB (launchd disabled)"
  echo
  local tests=(
    test_base_registry
    test_conformance
    test_unconfigured_fetch_scheduler
    test_handler_log_override
    test_command_lifecycle
    test_command_interval_lifecycle
    test_command_interval_validation
    test_command_stored_schedule_doctor
    test_fetch_dry_run
    test_fetch_tags
    test_fetch_stable_head_telemetry
    test_fetch_update_atomicity
    test_fetch_conditional_retirement
    test_configured_inventory
    test_overlay_authoring
    test_canvas_templates
    test_canvas_tsc_smoke
    test_dashboard_canvas_regen
    test_dashboard_fixture_deterministic
    test_running_status
    test_running_owner_aware_cleanup
    test_dispatch_run_flock
    test_empty_state_seed
    test_view_verb_canvas
    test_launchd_watchpaths_render
    test_launchd_schedule_validation_and_determinism
    test_canvas_run_bridge_lifecycle
    test_canvas_run_bridge_requests
    test_canvas_run_bridge_failure_refresh
    test_wrapper_preflight
    test_fresh_state_dashboard
    test_no_temp_status_paths
    test_consumer_payload_smoke_no_local_overlay
    test_stale_overlay_doctor_quarantine
    test_doctor_only_failure_structured
    test_partial_invalid_doctor_runs
    test_inherit_disabled_no_drift
    test_run_all_rc
    test_add_dry_run_id_unique
    test_resolve_no_type_slug
    test_store_flock
    test_cursor_project_slug
    test_wrapper_exports_env
    test_m1_mixed_sweep_truthful
    test_m1_continue_attempts_all
    test_m1_stop_skips_later_preserves_streak
    test_m1_reconcile_no_child_flip
    test_m1_usage_exit2_is_failure
    test_m1_clean_run_clears_bogus_streak
    test_m2_display_fallback_precedence
    test_m2_execution_mode_on_demand
    test_m2_gitfetch_metadata_roundtrip
    test_m2_migrate_fills_only_missing
    test_m2_shim_migration
    test_running_long
    test_pm_summary_buckets_reconcile
    test_canvas_control_bridge
    test_canvas_view_bridge
    test_canvas_view_bridge_targets_request_workspace
    test_builder_snapshot_retired
    test_swarm_di_update_requires_schedule
    test_swarm_igf_config_crash_is_failure
    test_swarm_igf_dry_run_surfaces_failure
    test_swarm_repair_reports_failures
    test_swarm_pid_reuse_guard
    test_swarm_malformed_runlog_failure
    test_swarm_needs_attention_parity
  )
  local t
  for t in "${tests[@]}"; do run_test "$t"; done
  printf 'RESULT: %d passed, %d failed\n' "$pass" "$fail"
  (( fail == 0 ))
}

main "$@"
