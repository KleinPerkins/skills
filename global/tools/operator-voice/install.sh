#!/usr/bin/env bash
# install.sh — Global Capability Binding (GCB) for Operator Voice Toolkit (OVT), Flavor-2
# `shape: snapshot` (see meta.yml). Unlike `global/tools/awa`, this binding never clones the
# private `KleinPerkins/operator-voice` SSP repo: the runtime bytes are the committed `payload/`
# directory beside this script, a deterministic, personal-data-free snapshot at
# `meta.yml`'s `provenance_ref` — this is exactly what lets a FUTURE downstream-governed-repository
# generic `kind: tool` reconciler install OVT with no KleinPerkins/private-repo access at all
# (build plan §8.1). This script performs a completely ordinary HOME-relative "home" install using
# that same embedded payload; it is not itself a write into any downstream repository's control
# plane — that enrollment happens only through the standard WF1/WF2 ecosystem lifecycle
# (eco-orchestrator sync), never through this file.
#
#   install.sh              install (or no-op if already current; default)
#   install.sh --repair      verify/replace the runtime payload only (never config/state/keys)
#   install.sh --doctor      read-only health check
#   install.sh --check       CI-safe static preflight (no writes, no network) — verifies the
#                            embedded payload's digest matches meta.yml's payload_digest
#   install.sh --uninstall   remove the venv/runtime/wrapper/skill; profile data+keys untouched
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="operator-voice"
log()     { printf '[install:%s] %s\n' "$NAME" "$*"; }
degrade() { printf '[install:%s] DEGRADED: %s\n' "$NAME" "$*" >&2; }

PAYLOAD_ROOT="$SRC/payload"
SOURCE_ROOT="$PAYLOAD_ROOT/operator_voice"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
APP_DIR="$DATA_HOME/$NAME"
VENV="$APP_DIR/venv"
RUNTIME_ROOT="$APP_DIR/runtime"
RECEIPT="$STATE_HOME/$NAME/install-receipt.json"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/$NAME"

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

need_python312() {
  for cand in python3.12 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        echo "$cand"; return 0
      fi
    fi
  done
  return 1
}

runtime_requirements() {
  # Single source of truth: the embedded payload's own operator_voice/runtime/requirements.json
  # (operator_voice.runtime.requirements) — never a second hardcoded pin list here. This is exactly
  # the drift the requirements.json file was added to prevent (M5-B, docs/m5b-evidence-ledger.md):
  # this shelf's own copy had fallen behind a cryptography floor bump made only in pyproject.toml.
  "$1" -c '
import sys
sys.path.insert(0, "'"$PAYLOAD_ROOT"'")
from operator_voice.runtime.requirements import load_install_requires
from pathlib import Path
print("\n".join(load_install_requires(Path("'"$SOURCE_ROOT"'"))))
'
}

# Anchors one requirement-spec line (e.g. "cryptography>=48.0.1,<49.0") to bare PEP 440
# name[extras]<comma-separated-version-clauses> syntax (no '@', no '/', no whitespace, no leading
# '-'). Deliberately the SAME pattern a downstream generic kind:tool reconciler independently uses
# for its own runtime-requirements/v1 gate (M5-B swarm finding install-sh-unvalidated-pip-specs)
# rather than a fresh one: a pip-FLAG-shaped entry (--index-url=…) or a URL/VCS install (-e, git+…)
# must never reach pip's argv, even though today's only source is this shelf's own governed-PR-
# reviewed requirements.json — this is defense-in-depth against a future regeneration path that
# stops being a byte-for-byte human diff.
_req_spec_safe() {
  local spec="$1" name='[A-Za-z0-9][A-Za-z0-9._-]*' extras='(\[[A-Za-z0-9,._-]+\])?' clause='[<>=!~]=?[A-Za-z0-9._*]+'
  [[ "$spec" =~ ^${name}${extras}(${clause}(,${clause})*)?$ ]]
}

ensure_venv() {
  local py; py="$(need_python312)" || { degrade "python >= 3.12 not found on PATH"; return 2; }
  if [ ! -x "$VENV/bin/python" ]; then
    log "creating venv -> $VENV"
    if command -v uv >/dev/null 2>&1; then uv venv --python "$py" "$VENV" >/dev/null
    else "$py" -m venv "$VENV"; fi
  fi
  local reqs_raw specs=() line
  reqs_raw="$(runtime_requirements "$py")"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    _req_spec_safe "$line" \
      || { degrade "requirements.json entry '$line' is not a plain name/version dependency spec — refusing to install (this shelf's own embedded payload should never produce this; treat as a defect, not a transient error)."; return 2; }
    specs+=("$line")
  done <<<"$reqs_raw"
  [ "${#specs[@]}" -gt 0 ] || { degrade "no runtime dependencies resolved from requirements.json"; return 2; }
  log "installing runtime dependencies (${specs[*]}) into the venv"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$VENV/bin/python" --quiet "${specs[@]}"
  else
    "$VENV/bin/pip" install --quiet "${specs[@]}"
  fi
}

run_install_cli() {
  PYTHONPATH="$PAYLOAD_ROOT" "$VENV/bin/python" -m operator_voice.runtime.install_cli "$@"
}

write_wrapper() {
  mkdir -p "$BIN_DIR"
  local tmp; tmp="$(mktemp "$BIN_DIR/.${NAME}.XXXXXX")"
  cat > "$tmp" <<WRAP
#!/usr/bin/env bash
export PYTHONPATH="$RUNTIME_ROOT/current\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV/bin/python" -m operator_voice.interfaces.cli "\$@"
WRAP
  chmod +x "$tmp"
  mv -f "$tmp" "$WRAPPER"
  log "wrapper installed -> $WRAPPER (ensure $BIN_DIR is on PATH)"
}

install_skill_files() {
  PYTHONPATH="$RUNTIME_ROOT/current" "$VENV/bin/python" -c '
from operator_voice.interfaces.skill import install_skill
import json
print(json.dumps(install_skill()))
' 2>/dev/null || degrade "skill install step failed (non-fatal; CLI/MCP remain usable)"
}

do_install() {
  local force="${1:-}"
  ensure_venv || return $?
  local args=(install --source-root "$SOURCE_ROOT" --runtime-root "$RUNTIME_ROOT" --receipt "$RECEIPT" --source home-via-gcb)
  [ "$force" = "1" ] && args+=(--force)
  run_install_cli "${args[@]}"
  write_wrapper
  install_skill_files
}

do_repair() {
  ensure_venv || return $?
  run_install_cli repair --source-root "$SOURCE_ROOT" --runtime-root "$RUNTIME_ROOT" --receipt "$RECEIPT"
  write_wrapper
  install_skill_files
}

# CI-safe static preflight: no writes, no network. Verifies the embedded payload's own recorded
# digest matches meta.yml's payload_digest, AND that the digest re-derived from the files on disk
# right now still matches — i.e. this shelf has not drifted from its own manifest.
do_check() {
  local py; py="$(need_python312)" || { degrade "python >= 3.12 not found on PATH"; return 2; }
  local expected; expected="$(meta_get "$SRC/meta.yml" payload_digest)"
  : "${expected:?payload_digest missing from meta.yml}"
  PYTHONPATH="$PAYLOAD_ROOT" "$py" -c '
import json, sys
from operator_voice.runtime.payload import compute_digest, load_manifest
from pathlib import Path

payload_root = Path("'"$PAYLOAD_ROOT"'")
expected = "'"$expected"'"
manifest = load_manifest(payload_root)
on_disk_digest, _ = compute_digest(payload_root / "operator_voice")
problems = []
if manifest.digest != expected:
    problems.append(f"payload-manifest.json digest ({manifest.digest}) != meta.yml payload_digest ({expected})")
if on_disk_digest != expected:
    problems.append(f"on-disk payload digest ({on_disk_digest}) != meta.yml payload_digest ({expected}) — shelf has drifted")
print(json.dumps({"status": "ok" if not problems else "failed", "problems": problems}, indent=2))
sys.exit(0 if not problems else 1)
'
}

do_doctor() {
  [ -x "$VENV/bin/python" ] || { degrade "no venv yet — run install.sh first"; return 3; }
  run_install_cli doctor --runtime-root "$RUNTIME_ROOT" --receipt "$RECEIPT"
  local rc=$?
  if [ -x "$WRAPPER" ]; then log "wrapper present -> $WRAPPER"; else degrade "wrapper missing"; rc=1; fi
  return $rc
}

do_uninstall() {
  log "removing venv, runtime, wrapper, and skill files (profile data/config/keys are untouched by this step)"
  if [ -x "$VENV/bin/python" ]; then
    PYTHONPATH="$RUNTIME_ROOT/current" "$VENV/bin/python" -c '
from operator_voice.interfaces.skill import uninstall_skill
uninstall_skill()
' 2>/dev/null || true
  fi
  rm -rf "$VENV" "$RUNTIME_ROOT"
  rm -f "$WRAPPER"
  log "uninstalled runtime + wrapper + skill files. Receipt left at $RECEIPT for audit."
}

case "${1:-install}" in
  install|"")   do_install 0 ;;
  --repair)     do_repair ;;
  --doctor)     do_doctor ;;
  --check)      do_check ;;
  --uninstall)  do_uninstall ;;
  -h|--help)    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) log "WARN unknown arg '$1' (ignored); running default install"; do_install 0 ;;
esac
