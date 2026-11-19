#!/usr/bin/env bash
# install.sh — Global Capability Binding (GCB) for AWA (Flavor-2, standalone-release).
#
# AWA is a Standalone System Package (SSP): a self-contained product that lives in its own repo
# (provenance_source) and installs itself from a fresh clone via its own install.sh. This shelf
# entry is the GLOBAL CAPABILITY BINDING to that SSP: it reads the pin from meta.yml
# (provenance_source @ provenance_ref), clones/updates KleinPerkins/awa at that exact commit into a
# per-user checkout, then hands off to the checkout's OWN install.sh to place the runtime. The shelf
# carries a pinned release pointer — never the runtime bytes. Idempotent; backup-before-write is
# owned by the standalone installer; honors HOME / XDG_* overrides; degrades with an honest message
# when git or the network is unavailable.
#
#   install.sh              clone-at-pin + run the standalone install (default; idempotent)
#   install.sh --repair     force update the checkout to the pin + standalone --repair
#   install.sh --doctor     read-only health check of the binding + standalone doctor
#   install.sh --check      CI-safe static preflight (no writes, no network)
#   install.sh --print      print the resolved (source, ref, checkout) without writing
#   install.sh --uninstall [--keep-state]  delegate the standalone uninstall + drop the gcb pointer
#
# Layout (all HOME / XDG-relative):
#   checkout  ${XDG_DATA_HOME:-$HOME/.local/share}/awa/checkout          pinned KleinPerkins/awa clone
#   binding   ${XDG_DATA_HOME:-$HOME/.local/share}/awa/gcb-pointer.json  awa-gcb-pointer/v1 record
#   runtime   ${XDG_DATA_HOME:-$HOME/.local/share}/awa/current           written by the SSP installer
#   pointer   ${XDG_DATA_HOME:-$HOME/.local/share}/awa/release-pointer.json  written by the SSP installer
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"
log()     { printf '[install:%s] %s\n' "$NAME" "$*"; }
degrade() { printf '[install:%s] DEGRADED: %s\n' "$NAME" "$*" >&2; }

# Flat `key: value` reader; require a space before an inline # so values keep a literal '#'.
meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

SRC_URL="$(meta_get "$SRC/meta.yml" provenance_source)"
REF="$(meta_get "$SRC/meta.yml" provenance_ref)"
: "${SRC_URL:?provenance_source missing from meta.yml}"
: "${REF:?provenance_ref missing from meta.yml}"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CHECKOUT="${AWA_CHECKOUT:-$DATA_HOME/awa/checkout}"
GCB_PTR="$DATA_HOME/awa/gcb-pointer.json"
REL_PTR="$DATA_HOME/awa/release-pointer.json"
SHORT_REF="$(printf '%s' "$REF" | cut -c1-12)"

# Derive clone remotes from `provenance_source` (host/owner/repo). SSH first (private repo),
# HTTPS as a non-interactive fallback; an explicit AWA_CLONE_URL overrides both.
HOST="${SRC_URL%%/*}"
REPO_SLUG="${SRC_URL#*/}"
SSH_URL="git@${HOST}:${REPO_SLUG}.git"
HTTPS_URL="https://${HOST}/${REPO_SLUG}.git"
RESOLVED_URL="${AWA_CLONE_URL:-$SSH_URL}"
export GIT_TERMINAL_PROMPT=0   # never block on an interactive credential prompt

need_git() {
  command -v git >/dev/null 2>&1 || { degrade "git is required for the clone-at-pin binding"; return 2; }
}

clone_at_pin() {
  mkdir -p "$(dirname "$CHECKOUT")"
  local urls u
  if [ -n "${AWA_CLONE_URL:-}" ]; then urls="$AWA_CLONE_URL"; else urls="$SSH_URL
$HTTPS_URL"; fi
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    log "cloning $u -> $CHECKOUT"
    rm -rf "$CHECKOUT" 2>/dev/null || true
    if git clone --quiet "$u" "$CHECKOUT" 2>/dev/null; then
      if git -C "$CHECKOUT" checkout --quiet --detach "$REF" 2>/dev/null; then
        RESOLVED_URL="$u"; return 0
      fi
      log "WARN cloned via $u but pin $SHORT_REF is absent; trying next remote"
    else
      log "WARN clone via $u failed; trying next remote"
    fi
  done <<EOF
$urls
EOF
  degrade "unable to clone $SRC_URL at pin $SHORT_REF (network / auth?)."
  return 3
}

ensure_checkout() {
  local force="$1"
  need_git || return 2
  if [ -d "$CHECKOUT/.git" ]; then
    local head; head="$(git -C "$CHECKOUT" rev-parse HEAD 2>/dev/null || echo none)"
    if [ "$head" = "$REF" ] && [ "$force" != "1" ]; then
      log "checkout already at pin $SHORT_REF — $CHECKOUT"
      return 0
    fi
    log "updating checkout -> pin $SHORT_REF"
    if ! git -C "$CHECKOUT" fetch --quiet origin 2>/dev/null; then
      if ! git -C "$CHECKOUT" rev-parse --verify --quiet "${REF}^{commit}" >/dev/null 2>&1; then
        degrade "cannot fetch origin and pin $SHORT_REF is not present locally (offline?)."
        return 3
      fi
      log "WARN offline fetch failed; pin present locally, continuing"
    fi
    git -C "$CHECKOUT" checkout --quiet --detach "$REF" 2>/dev/null || { degrade "cannot checkout pin $SHORT_REF"; return 3; }
  else
    if [ -e "$CHECKOUT" ] && [ -n "$(ls -A "$CHECKOUT" 2>/dev/null || true)" ]; then
      degrade "$CHECKOUT exists and is not an AWA git checkout (refusing to clobber)."
      return 3
    fi
    clone_at_pin || return 3
  fi
  local head2; head2="$(git -C "$CHECKOUT" rev-parse HEAD 2>/dev/null || echo none)"
  [ "$head2" = "$REF" ] || { degrade "checkout HEAD ($head2) != pin $REF"; return 3; }
  return 0
}

# Hand off to the standalone SSP installer inside the pinned checkout. The SSP owns the runtime, the
# config env, the Cursor hooks, the add-only MCP server, and release-pointer.json; it honors the same
# HOME / XDG overrides. We invoke it with bash (no dependency on its executable bit).
run_standalone() {
  local verb="$1"
  local inst="$CHECKOUT/install.sh"
  [ -f "$inst" ] || { degrade "checkout has no install.sh (pin predates the standalone installer?)"; return 3; }
  log "handing off to the standalone installer: install.sh ${verb:-install}"
  if [ -n "$verb" ]; then bash "$inst" "$verb"; else bash "$inst"; fi
}

write_gcb_pointer() {
  command -v python3 >/dev/null 2>&1 || { log "WARN python3 absent; skipping gcb pointer bookkeeping"; return 0; }
  local resolved; resolved="$(git -C "$CHECKOUT" remote get-url origin 2>/dev/null || echo "$RESOLVED_URL")"
  mkdir -p "$(dirname "$GCB_PTR")"
  GCB_PTR="$GCB_PTR" REL_PTR="$REL_PTR" SRC_URL="$SRC_URL" REF="$REF" CHECKOUT="$CHECKOUT" \
  SHELF="$SRC" CLONE_URL="$resolved" python3 - <<'PY'
import json, os, tempfile
ptr = os.environ["GCB_PTR"]
data = {
    "schema": "awa-gcb-pointer/v1",
    "id": "awa",
    "kind": "global-capability-binding",
    "source": os.environ["SRC_URL"],
    "ref": os.environ["REF"],
    "clone_url": os.environ["CLONE_URL"],
    "checkout": os.environ["CHECKOUT"],
    "shelf": os.environ["SHELF"],
    "release_pointer": os.environ["REL_PTR"],
}
try:
    with open(ptr) as fh:
        current = json.load(fh)
except Exception:
    current = None
if current == data:
    print(f"present: {ptr}")
    raise SystemExit(0)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ptr), prefix=".gcb-pointer.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, ptr)
print(f"wrote: {ptr}")
PY
}

run_install() {
  local force="$1"
  ensure_checkout "$force" || return $?
  if [ "$force" = "1" ]; then run_standalone --repair || return $?; else run_standalone "" || return $?; fi
  write_gcb_pointer || true
  log "bound $SRC_URL @ $SHORT_REF -> standalone install complete."
  log "release pointer (written by the standalone installer): $REL_PTR"
}

do_doctor() {
  local rc=0
  echo "== awa global-capability-binding doctor =="
  echo "   source=$SRC_URL  ref=$SHORT_REF"
  echo "   checkout=$CHECKOUT"
  if [ -d "$CHECKOUT/.git" ]; then
    local head; head="$(git -C "$CHECKOUT" rev-parse HEAD 2>/dev/null || echo none)"
    if [ "$head" = "$REF" ]; then echo "  PASS  pinned checkout present at $SHORT_REF"
    else echo "  FAIL  checkout HEAD=$head != pin $REF"; rc=1; fi
  else echo "  FAIL  no checkout (run install.sh)"; rc=1; fi
  if [ -f "$GCB_PTR" ] && python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$GCB_PTR" 2>/dev/null; then
    echo "  PASS  gcb pointer present + valid"
  else echo "  WARN  gcb pointer missing/invalid (run install.sh)"; fi
  if [ -f "$CHECKOUT/install.sh" ]; then
    if bash "$CHECKOUT/install.sh" --doctor; then echo "  PASS  standalone install doctor OK"
    else echo "  FAIL  standalone install doctor reported problems"; rc=1; fi
  else echo "  FAIL  checkout missing install.sh"; rc=1; fi
  if [ "$rc" -eq 0 ]; then echo "awa binding doctor: OK"; else echo "awa binding doctor: FAILED"; fi
  return "$rc"
}

# CI-safe static preflight: validates the pin + host prerequisites. No network, no writes to $HOME.
do_check() {
  local rc=0
  echo "== awa global-capability-binding --check (static, no writes) =="
  if [ -n "$SRC_URL" ]; then echo "  PASS  provenance_source present ($SRC_URL)"; else echo "  FAIL  provenance_source missing"; rc=1; fi
  if printf '%s' "$REF" | grep -qE '^[0-9a-f]{40}$'; then echo "  PASS  provenance_ref is a full commit sha ($SHORT_REF)"
  else echo "  FAIL  provenance_ref must be a full 40-char commit sha (got '$REF')"; rc=1; fi
  if command -v git >/dev/null 2>&1; then echo "  PASS  git available"; else echo "  FAIL  git required for the clone-at-pin binding"; rc=1; fi
  if command -v python3 >/dev/null 2>&1; then echo "  PASS  python3 available"; else echo "  WARN  python3 absent (pointer bookkeeping degrades)"; fi
  if [ -d "$CHECKOUT/.git" ] && [ -f "$CHECKOUT/install.sh" ]; then
    echo "   checkout present; delegating the standalone static preflight"
    if bash "$CHECKOUT/install.sh" --check; then echo "  PASS  standalone --check OK"; else echo "  FAIL  standalone --check failed"; rc=1; fi
  else
    echo "   no checkout yet — install.sh will clone at the pin (static shelf preflight only)"
  fi
  if [ "$rc" -eq 0 ]; then echo "awa --check: OK"; else echo "awa --check: FAILED"; fi
  return "$rc"
}

do_print() { log "source=$SRC_URL ref=$REF checkout=$CHECKOUT clone_url=$RESOLVED_URL"; }

do_uninstall() {
  if [ -f "$CHECKOUT/install.sh" ]; then
    log "delegating uninstall to the standalone installer"
    bash "$CHECKOUT/install.sh" --uninstall "${1:-}" || true
  fi
  rm -f "$GCB_PTR" 2>/dev/null || true
  log "dropped gcb pointer; pinned checkout left in place at $CHECKOUT"
}

case "${1:-install}" in
  install|"")   run_install 0 ;;
  --repair)     run_install 1 ;;
  --doctor)     do_doctor ;;
  --check)      do_check ;;
  --print)      do_print ;;
  --uninstall)  shift; do_uninstall "${1:-}" ;;
  -h|--help)    sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) log "WARN unknown arg '$1' (ignored); running default install"; run_install 0 ;;
esac
