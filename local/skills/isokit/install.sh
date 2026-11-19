#!/usr/bin/env bash
# install.sh — expose isokit and provision its bounded browser-check dependency.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="$(basename "$SRC")"
PLAYWRIGHT_VERSION="1.64.1"

log() { printf '[install:%s] %s\n' "$NAME" "$*"; }

meta_get() {
  awk -v k="$2" '/^[[:space:]]*#/{next}
    {l=$0; sub(/[[:space:]]+#.*$/,"",l);
     if (match(l,/^[A-Za-z0-9_]+:[[:space:]]*/)) {
       key=l; sub(/:.*$/,"",key);
       if (key==k) { v=l; sub(/^[A-Za-z0-9_]+:[[:space:]]*/,"",v); gsub(/^"|"$/,"",v); print v; exit }
     }}' "$1"
}

exposed_tools() {
  local expose
  expose="$(meta_get "$SRC/meta.yml" expose | tr -d '[]' | tr ',' ' ')"
  [ -n "$expose" ] || expose="cursor"
  printf '%s\n' "$expose"
}

tool_dir() {
  case "$1" in
    cursor) printf '%s/.cursor/skills\n' "$HOME" ;;
    claude) printf '%s/.claude/skills\n' "$HOME" ;;
    codex)  printf '%s/.codex/skills\n' "$HOME" ;;
    *) return 1 ;;
  esac
}

installed_playwright_version() {
  local package="$SRC/node_modules/playwright-core/package.json"
  [ -f "$package" ] || return 1
  node -e 'process.stdout.write(require(process.argv[1]).version)' "$package" 2>/dev/null
}

runtime_healthy() {
  command -v node >/dev/null 2>&1 || return 1
  [ -f "$SRC/node_modules/playwright-core/package.json" ] || return 1
  (
    cd "$SRC"
    node --input-type=module -e '
      import { readFileSync } from "node:fs";
      const metadata = JSON.parse(
        readFileSync("./node_modules/playwright-core/package.json", "utf8"),
      );
      const runtime = await import("playwright-core");
      const healthy =
        metadata.version === process.argv[1] &&
        typeof runtime.chromium?.launch === "function";
      process.exit(healthy ? 0 : 1);
    ' "$PLAYWRIGHT_VERSION"
  ) >/dev/null 2>&1
}

provision_runtime() {
  local installed=""
  if runtime_healthy; then
    log "playwright-core@$PLAYWRIGHT_VERSION already provisioned"
    return 0
  fi

  command -v node >/dev/null 2>&1 || { log "ERROR: node is required"; return 1; }
  command -v npm >/dev/null 2>&1 || { log "ERROR: npm is required"; return 1; }
  [ -f "$SRC/package-lock.json" ] || { log "ERROR: package-lock.json is missing"; return 1; }

  log "provisioning playwright-core@$PLAYWRIGHT_VERSION (lifecycle scripts disabled)"
  (
    cd "$SRC"
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm_config_ignore_scripts=true \
      npm ci --ignore-scripts --no-audit --no-fund
  )

  if ! runtime_healthy; then
    installed="$(installed_playwright_version || true)"
    log "ERROR: playwright-core@$PLAYWRIGHT_VERSION runtime is incomplete or invalid (metadata version: ${installed:-missing})"
    return 1
  fi
}

preflight_links() {
  local tool base link failed=0
  for tool in $(exposed_tools); do
    [ "$tool" != "none" ] || return 0
    base="$(tool_dir "$tool")" || { log "ERROR: unknown expose tool '$tool'"; failed=1; continue; }
    link="$base/$NAME"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      log "ERROR: refusing activation because $link is a real path"
      failed=1
    fi
  done
  return "$failed"
}

link_tools() {
  local tool base link
  for tool in $(exposed_tools); do
    [ "$tool" != "none" ] || return 0
    base="$(tool_dir "$tool")" || { log "WARN: unknown expose tool '$tool' (skipped)"; continue; }
    link="$base/$NAME"
    mkdir -p "$base"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$SRC" ]; then
      continue
    fi
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      log "ERROR: refusing activation because $link is a real path"
      return 1
    fi
    rm -f "$link"
    ln -s "$SRC" "$link"
    log "linked $link -> $SRC"
  done
}

doctor() {
  local failed=0 tool base link
  if ! runtime_healthy; then
    log "FAIL: playwright-core@$PLAYWRIGHT_VERSION cannot import with chromium.launch"
    failed=1
  fi
  for tool in $(exposed_tools); do
    [ "$tool" != "none" ] || continue
    base="$(tool_dir "$tool")" || { log "FAIL: unknown expose tool '$tool'"; failed=1; continue; }
    link="$base/$NAME"
    if [ ! -L "$link" ] || [ "$(readlink "$link")" != "$SRC" ]; then
      log "FAIL: $link does not resolve to $SRC"
      failed=1
    fi
  done
  [ "$failed" -eq 0 ] && log "OK: runtime and tool links are ready"
  return "$failed"
}

case "${1:-}" in
  --doctor) doctor ;;
  ""|--apply|--repair)
    if [ "${KP_BOOTSTRAP_MANAGES_EXPOSURE:-0}" != 1 ]; then
      preflight_links
    fi
    provision_runtime
    if [ "${KP_BOOTSTRAP_MANAGES_EXPOSURE:-0}" != 1 ]; then
      link_tools
    fi
    ;;
  *)
    log "ERROR: unknown argument '$1'"
    exit 2
    ;;
esac
