#!/usr/bin/env bash
#
# bootstrap.sh — KleinPerkins/skills (skills hub: global + local scope)
#
# Idempotent. Safe to re-run. On a fresh machine it:
#   1. clones KleinPerkins/skills to ~/dev/capabilities/skills (if missing), and
#   2. (re)creates ABSOLUTE symlinks from each tool's skills dir INTO this repo's
#      durable primary checkout, following the per-tool exposure rule.
#
# Skills under global/skills/ are eligible for orchestrator->cpp vendoring; capabilities under
# local/ are installed locally only (never shared to cpp). They are exposed to the
# agent tools per each skill's `meta.yml` `expose:` field — the SOLE exposure SoT.
#
# Per-tool exposure is no longer hardcoded here: this script iterates every
# global|local/{skills,rules,sub-agents,tools,plugins}/<id> with a meta.yml and links it into each tool named in its
#   expose: cursor claude codex        (space- or comma-separated subset)
# An ABSENT expose: defaults to all three tools (Decision D4, Phase 1). `expose: none` keeps the
# capability in the repo but never installs it locally: no links, no installer run, and doctor reports
# it as OFF (ADR 0007). cpp distribution is decided separately by the orchestrator registry.
# To change a skill's exposure, edit its meta.yml — never this file.
#
# It keeps correct links, creates missing ones, and never overwrites real paths.
# The two required Codex skill projections preserve conflicting symlinks; other
# capabilities retain their existing relink/journaled replacement contracts.
#
set -euo pipefail

REPO_SLUG="KleinPerkins/skills"
REPO_SSH="git@github.com:${REPO_SLUG}.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"

cursor_worktree_ancestor() {
  local physical_script_dir="$1" home_physical cursor_root relative
  local repo_component remainder slot_component descendant ancestor
  local git_marker="" git_root

  [ -d "$physical_script_dir" ] || return 1
  physical_script_dir="$(cd "$physical_script_dir" 2>/dev/null && pwd -P)" ||
    return 1
  [ -d "$HOME" ] || return 1
  home_physical="$(cd "$HOME" 2>/dev/null && pwd -P)" || return 1
  cursor_root="${home_physical}/.cursor/worktrees"
  [ -d "$cursor_root" ] || return 1
  cursor_root="$(cd "$cursor_root" 2>/dev/null && pwd -P)" || return 1

  # Require exact path components below ~/.cursor/worktrees/<repo>/<slot>.
  # Prefix lookalikes such as ~/.cursor/worktrees-backup never enter this case.
  case "$physical_script_dir" in
    "$cursor_root"/*/*/*) ;;
    *) return 1 ;;
  esac
  relative="${physical_script_dir#"$cursor_root"/}"
  repo_component="${relative%%/*}"
  remainder="${relative#*/}"
  [ "$remainder" != "$relative" ] || return 1
  slot_component="${remainder%%/*}"
  descendant="${remainder#*/}"
  [ "$descendant" != "$remainder" ] && [ -n "$descendant" ] || return 1

  ancestor="${cursor_root}/${repo_component}/${slot_component}"
  [ -d "$ancestor" ] || return 1
  ancestor="$(cd "$ancestor" 2>/dev/null && pwd -P)" || return 1
  case "$physical_script_dir" in
    "$ancestor"/*) ;;
    *) return 1 ;;
  esac

  # Path spelling is insufficient: the candidate ancestor must itself be a
  # real linked Git worktree rooted at exactly the two-component slot.
  [ -f "$ancestor/.git" ] || return 1
  IFS= read -r git_marker < "$ancestor/.git" || true
  case "$git_marker" in
    "gitdir: "*) ;;
    *) return 1 ;;
  esac
  [ "$(git -C "$ancestor" rev-parse --is-inside-work-tree 2>/dev/null || true)" = "true" ] ||
    return 1
  git_root="$(git -C "$ancestor" rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$git_root" ] || return 1
  git_root="$(cd "$git_root" 2>/dev/null && pwd -P)" || return 1
  [ "$git_root" = "$ancestor" ] || return 1

  printf '%s\n' "$ancestor"
}

validate_established_primary() {
  local candidate="$1" physical="" disposable="" git_root="" origin="" reason=""
  ESTABLISHED_PRIMARY_PHYSICAL=""

  if [ ! -d "$candidate" ]; then
    reason="path is missing"
  elif ! physical="$(cd "$candidate" 2>/dev/null && pwd -P)"; then
    reason="path does not resolve physically"
  elif disposable="$(cursor_worktree_ancestor "$physical" 2>/dev/null)"; then
    reason="resolves below disposable Cursor worktree $disposable"
  elif [ ! -e "$physical/.git" ]; then
    reason=".git is missing"
  elif [ ! -d "$physical/.git" ]; then
    reason=".git is not a primary checkout"
  elif [ ! -d "$physical/global" ]; then
    reason="global/ is missing"
  elif [ ! -f "$physical/bootstrap.sh" ]; then
    reason="bootstrap.sh is missing"
  else
    git_root="$(git -C "$physical" rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -z "$git_root" ]; then
      reason="Git top level is unavailable"
    elif ! git_root="$(cd "$git_root" 2>/dev/null && pwd -P)"; then
      reason="Git top level does not resolve physically"
    elif [ "$git_root" != "$physical" ]; then
      reason="Git top level does not match the candidate"
    else
      origin="$(git -C "$physical" remote get-url origin 2>/dev/null || true)"
      case "$origin" in
        git@github.com:KleinPerkins/skills|\
        git@github.com:KleinPerkins/skills.git|\
        https://github.com/KleinPerkins/skills|\
        https://github.com/KleinPerkins/skills.git|\
        ssh://git@github.com/KleinPerkins/skills|\
        ssh://git@github.com/KleinPerkins/skills.git) ;;
        *) reason="origin is not KleinPerkins/skills" ;;
      esac
    fi
  fi

  if [ -n "$reason" ]; then
    printf 'ERROR: rejected nested Skills source %s below disposable Cursor worktree %s; expected durable primary %s failed check: %s\n' \
      "${NESTED_SOURCE:-<unknown>}" \
      "${DISPOSABLE_ANCESTOR:-<unknown>}" \
      "$candidate" \
      "$reason" >&2
    return 1
  fi

  ESTABLISHED_PRIMARY_PHYSICAL="$physical"
  return 0
}

resolve_repo_dir() {
  local script_dir="$1" git_marker="" git_root primary reason ancestor expected_primary
  if [ ! -e "${script_dir}/.git" ] || [ ! -d "${script_dir}/global" ]; then
    printf '%s\n' "${HOME}/dev/capabilities/skills"
    return 0
  fi

  # A linked worktree's .git is a `gitdir:` file. Git lists the durable primary
  # worktree first in porcelain output; never make local installs depend on the
  # disposable linked checkout that happened to launch bootstrap.
  if [ -f "${script_dir}/.git" ]; then
    IFS= read -r git_marker < "${script_dir}/.git" || true
  fi
  case "$git_marker" in
    "gitdir: "*)
      git_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null || true)"
      primary="$(git -C "$script_dir" worktree list --porcelain 2>/dev/null |
        awk '/^worktree /{sub(/^worktree /, ""); print; exit}')"
      if [ -z "$git_root" ] || [ -z "$primary" ]; then
        printf 'ERROR: unable to resolve the durable primary worktree for %s; refusing to install from linked worktree\n' \
          "$script_dir" >&2
        return 1
      fi
      if [ "$git_root" != "$primary" ]; then
        reason=""
        if [ ! -d "$primary" ]; then
          reason="path is missing"
        elif [ ! -e "$primary/.git" ]; then
          reason=".git is missing"
        elif [ ! -d "$primary/global" ]; then
          reason="missing global/"
        fi
        if [ -n "$reason" ]; then
          printf 'ERROR: durable primary worktree unavailable: %s (%s); refusing to install from linked worktree %s\n' \
            "$primary" "$reason" "$git_root" >&2
          return 1
        fi
      fi
      printf '%s\n' "$primary"
      ;;
    *)
      if [ -d "${script_dir}/.git" ] &&
        ancestor="$(cursor_worktree_ancestor "$script_dir")"; then
        NESTED_SOURCE="$(cd "$script_dir" && pwd -P)"
        DISPOSABLE_ANCESTOR="$ancestor"
        expected_primary="${HOME}/dev/capabilities/skills"
        validate_established_primary "$expected_primary" || return 1
        printf '%s\n' "$ESTABLISHED_PRIMARY_PHYSICAL"
      else
        printf '%s\n' "$script_dir"
      fi
      ;;
  esac
}

if ! REPO_DIR="$(resolve_repo_dir "$SCRIPT_DIR")"; then
  exit 1
fi
REJECTED_REPO_DIR=""
if [ "$SCRIPT_DIR" != "$REPO_DIR" ] &&
  [ -d "$SCRIPT_DIR/.git" ] &&
  cursor_worktree_ancestor "$SCRIPT_DIR" >/dev/null; then
  REJECTED_REPO_DIR="$SCRIPT_DIR"
fi
GLOBAL_DIR="${REPO_DIR}/global"
LOCAL_DIR="${REPO_DIR}/local"
META_VALIDATOR="${REPO_DIR}/scripts/capability_meta.py"
CAPABILITY_LOCAL="${REPO_DIR}/scripts/capability-local.py"

CURSOR_DIR="${HOME}/.cursor/skills"
CLAUDE_DIR="${HOME}/.claude/skills"
CODEX_DIR="${HOME}/.codex/skills"
CURSOR_RULES_DIR="${HOME}/.cursor/rules"
CURSOR_AGENTS_DIR="${HOME}/.cursor/agents"
CLAUDE_AGENTS_DIR="${HOME}/.claude/agents"
CODEX_AGENTS_DIR="${HOME}/.codex/agents"
DESIRED_LINKS="$(mktemp)"
PLAN_STREAM="$(mktemp)"
trap 'rm -f "$DESIRED_LINKS" "$PLAN_STREAM"' EXIT

# Bash 3.2-compatible immutable action plan. The shared Python parser emits one
# deterministic NUL-delimited stream; bootstrap decodes and validates the whole
# stream before any installer, doctor, registry, link, or prune operation.
PLAN_COUNT=0
PLAN_READY=0
PLAN_BUILD_FAILED=0
MUTATION_STARTED=0
STRICT_RUNTIME_FAILURE=0
PLAN_DIRS=()
PLAN_IDS=()
PLAN_KINDS=()
PLAN_FLAVORS=()
PLAN_POST_MGMT=()
PLAN_RUNTIME_CONTRACTS=()
PLAN_INSTALLERS=()
PLAN_OFF=()
PLAN_PLUGIN_OPTED_OUT=()
PLAN_LINK_STARTS=()
PLAN_LINK_COUNTS=()
# Index zero is an inert sentinel: Bash 3.2 + `set -u` rejects expansion of a
# declared-but-empty array. Real link records therefore begin at index one.
PLAN_LINK_SRCS=("")
PLAN_LINK_DSTS=("")
PLAN_LINK_PRIOR_STATES=("")
PLAN_LINK_PRIOR_TARGETS=("")

log() { printf '%s\n' "$*"; }

plan_fail() {
  log "  FAIL   $*"
  log "  FAIL   capability action-plan preflight made no changes"
  return 1
}

plan_read() {
  local variable="$1"
  IFS= read -r -d '' "$variable" <&3
}

plan_unsigned() {
  case "$1" in
    ""|*[!0-9]*) return 1 ;;
    *) [ "$1" -le 10000 ] ;;
  esac
}

plan_add_link() {
  local src="$1" dst="$2" link_index
  if ! printf '%s\n' "$dst" >> "$DESIRED_LINKS"; then
    PLAN_BUILD_FAILED=1
    return 1
  fi
  link_index="${#PLAN_LINK_DSTS[@]}"
  PLAN_LINK_SRCS[link_index]="$src"
  PLAN_LINK_DSTS[link_index]="$dst"
}

preflight_destination_ancestors() {
  local dst="$1" parent next
  parent="${dst%/*}"
  [ -n "$parent" ] || parent="/"
  while :; do
    if [ -L "$parent" ]; then
      if [ ! -d "$parent" ]; then
        log "  FAIL   $parent is a symlink that does not resolve to a directory (activation preflight)"
        return 1
      fi
    elif [ -e "$parent" ] && [ ! -d "$parent" ]; then
      log "  FAIL   $parent exists and is NOT a directory (activation preflight)"
      return 1
    fi
    [ "$parent" = "/" ] && break
    next="${parent%/*}"
    [ -n "$next" ] || next="/"
    [ "$next" != "$parent" ] || break
    parent="$next"
  done
}

journal_runtime_destination() {
  local link_index="$1" dst="${PLAN_LINK_DSTS[$1]}" target
  preflight_destination_ancestors "$dst" || return 1
  if [ -L "$dst" ]; then
    if ! target="$(readlink "$dst")"; then
      log "  FAIL   could not read prior symlink target for $dst"
      return 1
    fi
    PLAN_LINK_PRIOR_STATES[link_index]="symlink"
    PLAN_LINK_PRIOR_TARGETS[link_index]="$target"
  elif [ -e "$dst" ]; then
    log "  FAIL   $dst exists and is NOT a symlink (activation preflight)"
    return 1
  else
    PLAN_LINK_PRIOR_STATES[link_index]="absent"
    PLAN_LINK_PRIOR_TARGETS[link_index]=""
  fi
}

build_action_plan() {
  local magic count unit_index asset_count asset_index extra
  local dir id kind flavor post runtime_contract install
  local expose_cursor expose_claude expose_codex off asset
  local src start link_index plugin_opted_out=0 seen_ids=""
  local -a unit_assets

  [ "$MUTATION_STARTED" = 0 ] ||
    { plan_fail "refusing to build an action plan after mutation started"; return 1; }
  command -v python3 >/dev/null 2>&1 ||
    { plan_fail "python3 is required for capability action-plan validation"; return 1; }
  [ -f "$META_VALIDATOR" ] ||
    { plan_fail "capability metadata validator is missing: $META_VALIDATOR"; return 1; }
  if [ -f "$CAPABILITY_LOCAL" ] &&
    ! python3 "$CAPABILITY_LOCAL" path >/dev/null 2>&1; then
    plan_fail "capability-local helper failed validation"
    return 1
  fi

  : > "$PLAN_STREAM"
  : > "$DESIRED_LINKS"
  if ! PYTHONDONTWRITEBYTECODE=1 python3 "$META_VALIDATOR" action-plan "$REPO_DIR" > "$PLAN_STREAM"; then
    plan_fail "capability action-plan parser failed"
    return 1
  fi

  exec 3< "$PLAN_STREAM"
  if ! plan_read magic || [ "$magic" != "kp-capability-plan/v1" ] ||
    ! plan_read count || ! plan_unsigned "$count" || [ "$count" -eq 0 ]; then
    exec 3<&-
    plan_fail "capability parser emitted a malformed action-plan header"
    return 1
  fi
  PLAN_COUNT="$count"

  for ((unit_index=0; unit_index<PLAN_COUNT; unit_index++)); do
    if ! plan_read dir || ! plan_read id || ! plan_read kind ||
      ! plan_read flavor || ! plan_read post || ! plan_read runtime_contract ||
      ! plan_read install || ! plan_read expose_cursor ||
      ! plan_read expose_claude || ! plan_read expose_codex ||
      ! plan_read off || ! plan_read asset_count ||
      ! plan_unsigned "$asset_count"; then
      exec 3<&-
      plan_fail "capability parser emitted a truncated action plan"
      return 1
    fi
    case "$dir" in
      "${GLOBAL_DIR}"/*|"${LOCAL_DIR}"/*) ;;
      *)
        exec 3<&-
        plan_fail "action-plan path escapes the repository: $dir"
        return 1 ;;
    esac
    case "${dir}${id}${kind}${flavor}${post}${runtime_contract}${install}" in
      *$'\n'*|*$'\r'*|*$'\t'*)
        exec 3<&-
        plan_fail "action-plan identity fields contain control characters"
        return 1 ;;
    esac
    case "$id" in
      ""|*[!A-Za-z0-9_-]*)
        exec 3<&-
        plan_fail "action-plan contains malformed capability id '$id'"
        return 1 ;;
    esac
    if [ "${dir##*/}" != "$id" ] || [ ! -d "$dir" ] || [ -L "$dir" ]; then
      exec 3<&-
      plan_fail "action-plan directory does not match capability id '$id'"
      return 1
    fi
    case " $seen_ids " in
      *" $id "*)
        exec 3<&-
        plan_fail "action-plan contains duplicate capability id '$id'"
        return 1 ;;
      *) seen_ids="$seen_ids $id" ;;
    esac
    case "$install" in
      ""|*..*|*/*|*\\*)
        exec 3<&-
        plan_fail "$id has an unsafe installer name in the action plan"
        return 1 ;;
    esac
    if [ ! -f "$dir/$install" ] || [ ! -x "$dir/$install" ]; then
      exec 3<&-
      plan_fail "$id installer is missing or not executable"
      return 1
    fi
    case "$runtime_contract" in
      ""|installer-doctor/v1) ;;
      *)
        exec 3<&-
        plan_fail "$id has unsupported runtime_contract '$runtime_contract'"
        return 1 ;;
    esac
    case "${expose_cursor}${expose_claude}${expose_codex}${off}" in
      [01][01][01][01]) ;;
      *)
        exec 3<&-
        plan_fail "$id has malformed exposure flags in the action plan"
        return 1 ;;
    esac
    if { [ "$off" = 1 ] &&
      [ "${expose_cursor}${expose_claude}${expose_codex}" != 000 ]; } ||
      { [ "$off" = 0 ] &&
        [ "${expose_cursor}${expose_claude}${expose_codex}" = 000 ]; }; then
      exec 3<&-
      plan_fail "$id has inconsistent exposure flags in the action plan"
      return 1
    fi

    unit_assets=()
    for ((asset_index=0; asset_index<asset_count; asset_index++)); do
      if ! plan_read asset; then
        exec 3<&-
        plan_fail "capability parser truncated the asset plan for $id"
        return 1
      fi
      case "$asset" in
        ""|*..*|*/*|*\\*|*$'\n'*|*$'\r'*|*$'\t'*)
          exec 3<&-
          plan_fail "$id has an unsafe asset in the action plan"
          return 1 ;;
      esac
      if [ ! -f "$dir/$asset" ]; then
        exec 3<&-
        plan_fail "$id action-plan asset is missing: $asset"
        return 1
      fi
      unit_assets[asset_index]="$asset"
    done

    PLAN_DIRS[unit_index]="$dir"
    PLAN_IDS[unit_index]="$id"
    PLAN_KINDS[unit_index]="$kind"
    PLAN_FLAVORS[unit_index]="$flavor"
    PLAN_POST_MGMT[unit_index]="$post"
    PLAN_RUNTIME_CONTRACTS[unit_index]="$runtime_contract"
    PLAN_INSTALLERS[unit_index]="$dir/$install"
    PLAN_OFF[unit_index]="$off"
    PLAN_PLUGIN_OPTED_OUT[unit_index]=0

    if [ "$kind" = plugin ] && [ "$off" = 0 ] &&
      [ "${RESET_LOCAL_CONFIG:-0}" != 1 ] && [ -f "$CAPABILITY_LOCAL" ]; then
      if python3 "$CAPABILITY_LOCAL" is-opted-out "$id" >/dev/null 2>&1; then
        plugin_opted_out=1
      else
        plugin_opted_out=0
      fi
      PLAN_PLUGIN_OPTED_OUT[unit_index]="$plugin_opted_out"
    fi

    start="${#PLAN_LINK_DSTS[@]}"
    PLAN_LINK_STARTS[unit_index]="$start"
    src="$dir"
    case "$kind" in
      skill)
        [ -f "$src/SKILL.md" ] || {
          exec 3<&-
          plan_fail "$id skill payload is missing"
          return 1
        }
        [ "$expose_cursor" = 1 ] && plan_add_link "$src" "$CURSOR_DIR/$id"
        [ "$expose_claude" = 1 ] && plan_add_link "$src" "$CLAUDE_DIR/$id"
        [ "$expose_codex" = 1 ] && plan_add_link "$src" "$CODEX_DIR/$id"
        ;;
      rule)
        [ -f "$src/$id.mdc" ] || {
          exec 3<&-
          plan_fail "$id rule payload is missing"
          return 1
        }
        if [ "$expose_cursor" = 1 ]; then
          plan_add_link "$src/$id.mdc" "$CURSOR_RULES_DIR/$id.mdc"
          for ((asset_index=0; asset_index<asset_count; asset_index++)); do
            plan_add_link "$src/${unit_assets[$asset_index]}" \
              "$CURSOR_RULES_DIR/${unit_assets[$asset_index]}"
          done
        fi
        ;;
      sub-agent)
        [ -f "$src/$id.md" ] || {
          exec 3<&-
          plan_fail "$id sub-agent payload is missing"
          return 1
        }
        [ "$expose_cursor" = 1 ] && plan_add_link "$src/$id.md" "$CURSOR_AGENTS_DIR/$id.md"
        [ "$expose_claude" = 1 ] && plan_add_link "$src/$id.md" "$CLAUDE_AGENTS_DIR/$id.md"
        [ "$expose_codex" = 1 ] && plan_add_link "$src/$id.md" "$CODEX_AGENTS_DIR/$id.md"
        ;;
      tool)
        [ -f "$src/tool.yml" ] || {
          exec 3<&-
          plan_fail "$id tool descriptor is missing"
          return 1
        } ;;
      plugin)
        { [ -f "$src/SKILL.md" ] && [ -f "$src/plugin.json" ]; } || {
          exec 3<&-
          plan_fail "$id plugin payload is incomplete"
          return 1
        }
        [ "$expose_cursor" = 1 ] && plan_add_link "$src" "$CURSOR_DIR/$id"
        ;;
      *)
        exec 3<&-
        plan_fail "$id has unsupported planned kind '$kind'"
        return 1 ;;
    esac
    PLAN_LINK_COUNTS[unit_index]=$((${#PLAN_LINK_DSTS[@]} - start))
  done

  extra=""
  if IFS= read -r -d '' extra <&3 || [ -n "$extra" ]; then
    exec 3<&-
    plan_fail "capability parser emitted trailing action-plan data"
    return 1
  fi
  exec 3<&-
  if [ "$PLAN_BUILD_FAILED" = 1 ]; then
    plan_fail "could not materialize the decoded action plan"
    return 1
  fi

  # Preflight and journal every activation-critical destination globally. A
  # collision in a later manifest therefore blocks all installers and links.
  for ((unit_index=0; unit_index<PLAN_COUNT; unit_index++)); do
    [ "${PLAN_OFF[$unit_index]}" = 0 ] || continue
    [ "${PLAN_RUNTIME_CONTRACTS[$unit_index]}" = installer-doctor/v1 ] || continue
    start="${PLAN_LINK_STARTS[$unit_index]}"
    count="${PLAN_LINK_COUNTS[$unit_index]}"
    for ((link_index=start; link_index<start+count; link_index++)); do
      if ! journal_runtime_destination "$link_index"; then
        plan_fail "activation destination preflight failed for ${PLAN_IDS[$unit_index]}"
        return 1
      fi
    done
  done

  readonly PLAN_COUNT
  readonly -a PLAN_DIRS PLAN_IDS PLAN_KINDS PLAN_FLAVORS PLAN_POST_MGMT \
    PLAN_RUNTIME_CONTRACTS PLAN_INSTALLERS PLAN_OFF PLAN_PLUGIN_OPTED_OUT \
    PLAN_LINK_STARTS PLAN_LINK_COUNTS PLAN_LINK_SRCS PLAN_LINK_DSTS \
    PLAN_LINK_PRIOR_STATES PLAN_LINK_PRIOR_TARGETS
  chmod 400 "$DESIRED_LINKS" "$PLAN_STREAM" 2>/dev/null || {
    plan_fail "could not freeze the validated capability action plan"
    return 1
  }
  PLAN_READY=1
}

reset_capability_local_registry() {
  local registry="${CAPABILITY_LOCAL_REGISTRY:-$HOME/.local/share/kleinperkins/capability-local.yml}"
  local parent
  case "$registry" in
    \~/*) registry="$HOME/${registry#\~/}" ;;
  esac
  rm -f "$registry"
  parent="${registry%/*}"
  [ -n "$parent" ] && [ "$parent" != "$registry" ] && rmdir "$parent" 2>/dev/null || true
}

# report_stale_links <id> — warn about leftover links for an OFF capability (reconcile prunes them).
report_stale_links() {
  local id="$1" p target canonical_target
  for p in "$CURSOR_DIR/$id" "$CLAUDE_DIR/$id" "$CODEX_DIR/$id" "$CURSOR_RULES_DIR/$id.mdc" \
    "$CURSOR_AGENTS_DIR/$id.md" "$CLAUDE_AGENTS_DIR/$id.md" "$CODEX_AGENTS_DIR/$id.md"; do
    [ -L "$p" ] || continue
    target="$(readlink "$p")"
    canonical_target="$(canonicalize_target_path "$target" 2>/dev/null || true)"
    case "$canonical_target" in
      "${REPO_DIR}"/*) log "  WARN   $p still links an OFF capability (run bootstrap.sh --reconcile)" ;;
    esac
  done
}

clone_if_missing() {
  if [ -e "${REPO_DIR}/.git" ]; then
    log "repo present: ${REPO_DIR}"
    return 0
  fi
  if [ -e "${REPO_DIR}" ] && [ -n "$(ls -A "${REPO_DIR}" 2>/dev/null || true)" ]; then
    log "ERROR: ${REPO_DIR} exists, is non-empty, and is not a git repo; aborting."
    exit 1
  fi
  log "cloning ${REPO_SLUG} -> ${REPO_DIR}"
  mkdir -p "$(dirname "${REPO_DIR}")"
  if command -v gh >/dev/null 2>&1; then
    gh repo clone "${REPO_SLUG}" "${REPO_DIR}"
  else
    git clone "${REPO_SSH}" "${REPO_DIR}"
  fi
}

link_path() {
  local src="$1" dst="$2" dry="${3:-0}" strict="${4:-0}" target
  if [ -L "$dst" ]; then
    target="$(readlink "$dst")"
    if [ "$target" = "$src" ]; then
      log "  OK     ${dst} -> ${src}"
      return 0
    fi
    # INT-005/006 do not authorize adopting another owner's discovery target.
    # Keep this migration boundary scoped to the two required skills; existing
    # capability upgrades and activation-critical journals keep their contracts.
    if [ "$strict" != 1 ]; then
      case "$src" in
        "$GLOBAL_DIR/skills/prompt-architect"|"$GLOBAL_DIR/skills/verification-before-completion")
          log "  SKIP   ${dst} (symlink ownership conflict; preserving target)"
          return 0 ;;
      esac
    fi
  fi
  if [ "$dry" != 1 ] && ! mkdir -p "$(dirname "$dst")"; then
    log "  FAIL   could not create parent for ${dst}"
    return 1
  fi
  if [ -L "${dst}" ]; then
    if [ "$dry" != 1 ] && ! ln -sfn "${src}" "${dst}"; then
      log "  FAIL   could not relink ${dst} -> ${src}"
      return 1
    fi
    log "  RELINK ${dst} -> ${src}"
  elif [ -e "${dst}" ]; then
    if [ "$strict" = 1 ]; then
      log "  FAIL   ${dst} exists and is NOT a symlink (refusing activation)"
      return 1
    fi
    log "  SKIP   ${dst} exists and is NOT a symlink (refusing to overwrite real path)"
  else
    if [ "$dry" != 1 ] && ! ln -s "${src}" "${dst}"; then
      log "  FAIL   could not link ${dst} -> ${src}"
      return 1
    fi
    log "  LINK   ${dst} -> ${src}"
  fi
}

restore_runtime_links() {
  local unit_index="$1" start count link_index dst prior_state prior_target current rc=0
  start="${PLAN_LINK_STARTS[$unit_index]}"
  count="${PLAN_LINK_COUNTS[$unit_index]}"
  for ((link_index=start; link_index<start+count; link_index++)); do
    dst="${PLAN_LINK_DSTS[$link_index]}"
    prior_state="${PLAN_LINK_PRIOR_STATES[$link_index]:-}"
    prior_target="${PLAN_LINK_PRIOR_TARGETS[$link_index]:-}"
    case "$prior_state" in
      absent)
        if [ -L "$dst" ]; then
          if rm -f "$dst"; then
            log "  ROLLBACK $dst (remove new activation link)"
          else
            log "  FAIL   could not remove new activation link $dst"
            rc=1
          fi
        elif [ -e "$dst" ]; then
          log "  FAIL   refusing to remove real path created at $dst during rollback"
          rc=1
        fi
        ;;
      symlink)
        if [ -L "$dst" ]; then
          current="$(readlink "$dst" 2>/dev/null || true)"
          if [ "$current" != "$prior_target" ]; then
            if ln -sfn "$prior_target" "$dst"; then
              log "  ROLLBACK $dst -> $prior_target"
            else
              log "  FAIL   could not restore prior symlink $dst -> $prior_target"
              rc=1
            fi
          fi
        elif [ -e "$dst" ]; then
          log "  FAIL   refusing to overwrite real path created at $dst during rollback"
          rc=1
        elif ln -s "$prior_target" "$dst"; then
          log "  ROLLBACK $dst -> $prior_target"
        else
          log "  FAIL   could not recreate prior symlink $dst -> $prior_target"
          rc=1
        fi
        ;;
      *)
        log "  FAIL   missing activation journal for $dst"
        rc=1 ;;
    esac
  done
  return "$rc"
}

maybe_run_install() {
  local unit_index="$1" dry="$2" mode="$3"
  local id="${PLAN_IDS[$1]}" flavor="${PLAN_FLAVORS[$1]}"
  local post="${PLAN_POST_MGMT[$1]}" kind="${PLAN_KINDS[$1]}"
  local runtime_contract="${PLAN_RUNTIME_CONTRACTS[$1]}"
  local installer="${PLAN_INSTALLERS[$1]}"
  if [ "$kind" = "plugin" ]; then
    if [ "${PLAN_PLUGIN_OPTED_OUT[$unit_index]}" = 1 ]; then
      log "  SKIP   ${id} (plugin opt-out)"
      return 0
    fi
    case "$mode" in
      install|reconcile)
        log "  APPLY  ${id} (plugin)"
        if [ "$dry" = 1 ]; then
          return 0
        elif [ "$runtime_contract" = installer-doctor/v1 ]; then
          KP_BOOTSTRAP_MANAGES_EXPOSURE=1 bash "$installer" --apply
        else
          bash "$installer" --apply
        fi
        return $? ;;
      repair)
        log "  REPAIR ${id} (plugin)"
        if [ "$dry" = 1 ]; then
          return 0
        elif [ "$runtime_contract" = installer-doctor/v1 ]; then
          KP_BOOTSTRAP_MANAGES_EXPOSURE=1 bash "$installer" --repair
        else
          bash "$installer" --repair
        fi
        return $? ;;
    esac
  fi
  if [ "$runtime_contract" = "installer-doctor/v1" ] ||
    [ "$flavor" = "2" ] || { [ -n "$post" ] && [ "$post" != "none" ]; }; then
    log "  INSTALL ${id} (flavor=${flavor:-?} post_mgmt=${post:-none})"
    [ "$dry" = 1 ] && return 0
    if [ "$runtime_contract" = "installer-doctor/v1" ]; then
      if KP_BOOTSTRAP_MANAGES_EXPOSURE=1 bash "$installer"; then
        return 0
      fi
      log "  FAIL   install.sh non-zero for activation-critical runtime $id"
      return 1
    fi
    bash "$installer" >/dev/null 2>&1 ||
      log "  WARN   install.sh non-zero for $id (continuing)"
  fi
}

expose_unit() {
  local unit_index="$1" dry="$2" strict="${3:-0}"
  local id="${PLAN_IDS[$1]}" kind="${PLAN_KINDS[$1]}"
  local start="${PLAN_LINK_STARTS[$1]}" count="${PLAN_LINK_COUNTS[$1]}"
  local link_index unit_rc=0
  if [ "$kind" = tool ]; then
    log "  RECORD ${id} (tool; no PATH install)"
    return 0
  fi
  for ((link_index=start; link_index<start+count; link_index++)); do
    link_path "${PLAN_LINK_SRCS[$link_index]}" "${PLAN_LINK_DSTS[$link_index]}" \
      "$dry" "$strict" || unit_rc=1
  done
  return "$unit_rc"
}

install_unit() {
  local unit_index="$1" dry="$2" mode="${3:-install}"
  local id="${PLAN_IDS[$1]}" runtime_contract="${PLAN_RUNTIME_CONTRACTS[$1]}"
  local unit_rc=0
  if [ "${PLAN_OFF[$unit_index]}" = 1 ]; then
    log "  OFF    ${id} (expose: none; not installed locally)"
    return 0
  fi
  case "$runtime_contract" in
    installer-doctor/v1)
      if ! maybe_run_install "$unit_index" "$dry" "$mode"; then
        STRICT_RUNTIME_FAILURE=1
        [ "$dry" = 1 ] || restore_runtime_links "$unit_index" || true
        return 1
      fi
      if ! expose_unit "$unit_index" "$dry" 1; then
        STRICT_RUNTIME_FAILURE=1
        [ "$dry" = 1 ] || restore_runtime_links "$unit_index" || true
        return 1
      fi
      return 0 ;;
    "")
      expose_unit "$unit_index" "$dry" || unit_rc=1
      maybe_run_install "$unit_index" "$dry" "$mode" || unit_rc=1
      return "$unit_rc" ;;
  esac
}

doctor_unit() {
  local unit_index="$1" id="${PLAN_IDS[$1]}" kind="${PLAN_KINDS[$1]}"
  local d="${PLAN_DIRS[$1]}" runtime_contract="${PLAN_RUNTIME_CONTRACTS[$1]}"
  local installer="${PLAN_INSTALLERS[$1]}" off="${PLAN_OFF[$1]}" err=0
  if [ "$off" = 1 ]; then
    log "  OFF    ${id} (expose: none; not installed locally)"
    report_stale_links "$id"
  fi
  case "$kind" in
    skill) [ -f "$d/SKILL.md" ] || { log "  FAIL   $d missing SKILL.md"; err=1; } ;;
    rule)
      [ -f "$d/$id.mdc" ] || { log "  FAIL   $d missing $id.mdc"; err=1; }
      if [ "$off" = 0 ]; then
        if [ "$runtime_contract" = "installer-doctor/v1" ]; then
          if [ ! -x "$installer" ]; then
            log "  FAIL   $d activation-critical runtime installer is not executable"
            err=1
          elif ! bash "$installer" --doctor; then
            log "  FAIL   $d activation-critical runtime doctor failed"
            err=1
          fi
        elif [ -x "$installer" ]; then
          bash "$installer" --doctor >/dev/null ||
            { log "  FAIL   $d rule/assets not installed (install.sh --doctor)"; err=1; }
        fi
      fi ;;
    sub-agent) [ -f "$d/$id.md" ] || { log "  FAIL   $d missing $id.md"; err=1; } ;;
    tool) [ -f "$d/tool.yml" ] || { log "  FAIL   $d missing tool.yml"; err=1; } ;;
    plugin)
      [ -f "$d/SKILL.md" ] || { log "  FAIL   $d missing SKILL.md"; err=1; }
      [ -f "$d/plugin.json" ] || { log "  FAIL   $d missing plugin.json"; err=1; }
      if [ ! -x "$installer" ]; then
        log "  FAIL   $d install.sh not executable"; err=1
      elif [ "$off" = 0 ]; then
        bash "$installer" --doctor || err=1
      fi ;;
  esac
  if [ "$off" = 0 ] && [ "$runtime_contract" = "installer-doctor/v1" ]; then
    case "$kind" in
      rule|plugin) : ;; # Their existing kind contracts already run --doctor above.
      *)
        if [ ! -x "$installer" ]; then
          log "  FAIL   $d activation-critical runtime installer is not executable"
          err=1
        elif ! bash "$installer" --doctor; then
          log "  FAIL   $d activation-critical runtime doctor failed"
          err=1
        fi ;;
    esac
  fi
  return "$err"
}

canonicalize_target_path() {
  local path="$1" probe suffix="" part physical
  case "$path" in
    /*) ;;
    *) return 1 ;;
  esac
  case "$path" in
    */../*|*/..|*/./*|*/.) return 1 ;;
  esac
  while [ "$path" != "/" ] && [ "${path%/}" != "$path" ]; do
    path="${path%/}"
  done
  probe="$path"
  while [ ! -d "$probe" ]; do
    [ "$probe" != "/" ] || return 1
    part="${probe##*/}"
    [ -n "$part" ] || return 1
    suffix="/${part}${suffix}"
    probe="${probe%/*}"
    [ -n "$probe" ] || probe="/"
  done
  physical="$(cd "$probe" 2>/dev/null && pwd -P)" || return 1
  printf '%s%s\n' "$physical" "$suffix"
}

prune_dir() {
  local dir="$1" dry="$2" p target canonical_target managed
  [ -d "$dir" ] || return 0
  for p in "$dir"/*; do
    [ -L "$p" ] || continue
    target="$(readlink "$p")"
    canonical_target="$(canonicalize_target_path "$target" 2>/dev/null || true)"
    managed=0
    case "$canonical_target" in
      "${REPO_DIR}"/*)
        managed=1 ;;
    esac
    if [ -n "$REJECTED_REPO_DIR" ]; then
      case "$canonical_target" in
        "${REJECTED_REPO_DIR}"/*)
          managed=1 ;;
      esac
    fi
    if [ "$managed" = 1 ] &&
      { [ ! -e "$target" ] || ! grep -qxF "$p" "$DESIRED_LINKS" 2>/dev/null; }; then
      log "  PRUNE  $p -> $target"
      [ "$dry" = 1 ] || rm -f "$p"
    fi
  done
}

run_install() {
  local dry="$1" mode="${2:-install}" unit_index rc=0
  for ((unit_index=0; unit_index<PLAN_COUNT; unit_index++)); do
    install_unit "$unit_index" "$dry" "$mode" || rc=1
  done
  return "$rc"
}

run_doctor() {
  local unit_index rc=0
  for ((unit_index=0; unit_index<PLAN_COUNT; unit_index++)); do
    doctor_unit "$unit_index" || rc=1
  done
  return "$rc"
}

run_prune() {
  local dry="$1"
  prune_dir "$CURSOR_DIR" "$dry"
  prune_dir "$CLAUDE_DIR" "$dry"
  prune_dir "$CODEX_DIR" "$dry"
  prune_dir "$CURSOR_RULES_DIR" "$dry"
  prune_dir "$CURSOR_AGENTS_DIR" "$dry"
  prune_dir "$CLAUDE_AGENTS_DIR" "$dry"
  prune_dir "$CODEX_AGENTS_DIR" "$dry"
}

main() {
  local mode="install" dry=0
  RESET_LOCAL_CONFIG=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --install) mode="install" ;;
      --reconcile) mode="reconcile" ;;
      --prune) mode="prune" ;;
      --doctor) mode="doctor" ;;
      --repair) mode="repair" ;;
      --reset-local-config) RESET_LOCAL_CONFIG=1 ;;
      --dry-run) dry=1 ;;
      -h|--help) log "usage: bootstrap.sh [--install|--reconcile|--prune|--doctor|--repair] [--reset-local-config] [--dry-run]"; return 0 ;;
      *) log "ERROR: unknown flag $1"; return 2 ;;
    esac
    shift
  done
  if [ "$REPO_DIR" != "$SCRIPT_DIR" ]; then
    if [ -d "$SCRIPT_DIR/.git" ]; then
      log "nested standalone checkout detected: using durable capability source ${REPO_DIR}"
    else
      log "linked worktree detected: using durable capability source ${REPO_DIR}"
    fi
  fi
  clone_if_missing
  build_action_plan || return 1
  [ "$PLAN_READY" = 1 ] || return 1
  MUTATION_STARTED=1
  if [ "$RESET_LOCAL_CONFIG" = "1" ] && [ -f "$CAPABILITY_LOCAL" ]; then
    log "reset  machine-local capability opt-out registry"
    [ "$dry" = 1 ] || reset_capability_local_registry
  fi
  # Capture the action's status instead of letting `set -e` abort the case: reconcile/prune must
  # still run run_prune (DESIRED_LINKS is fully populated even when a unit fails), and the failure
  # is surfaced via the final return rather than a silent early exit.
  local rc=0
  case "$mode" in
    install) run_install "$dry" install || rc=$? ;;
    reconcile)
      run_install "$dry" reconcile || rc=$?
      if [ "$STRICT_RUNTIME_FAILURE" = 1 ]; then
        log "  SKIP   stale-link pruning after activation-critical runtime failure"
      else
        run_prune "$dry"
      fi ;;
    prune) run_install 1 >/dev/null || rc=$?; run_prune "$dry" ;;
    doctor) run_doctor || rc=$? ;;
    repair) run_install "$dry" repair || rc=$? ;;
  esac
  log "Done."
  return "$rc"
}

main "$@"
