#!/usr/bin/env bash
# .github/scripts/eco-lock.sh — generate/verify .eco-registry.lock (eco-lock/v1) for a capability repo
# (WF1/B2, Decision D1=keep). Self-contained (no ~/dev dependency).
#
# The lock is a fast-feedback METADATA LOCK over the NORMALIZED meta.yml fields of every capability in
# the repo. It is not a payload-integrity/content lock; payload byte equality is covered separately by
# orchestrator consistency. CI/local checks assert on-disk meta == lock ("did you forget to regenerate
# the lock after editing a meta.yml?"). The shared pre-commit registration-guard regenerates it by
# calling THIS script, so there is exactly ONE normalization algorithm per repo. The orchestrator-side
# reconcile READS the committed lock (never recomputes) and treats registry.yml as the authority on a
# conflict.
#
#   eco-lock.sh write              (re)write .eco-registry.lock from the current metas
#   eco-lock.sh check              recompute + compare; exit 1 on drift (the CI gate)
#   eco-lock.sh digest <meta.yml>  print one capability's normalized sha256 (debug)
#
# Layout auto-detect: a global/+local/ hub (KleinPerkins/skills) requires
# global|local/{skills,rules,sub-agents,tools,plugins}/<id>. A flat repo-root (kp-mcp)
# scans */meta.yml that declare schema: kp-capability/v1.
set -uo pipefail
set -o pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
LOCK=".eco-registry.lock"
ALLOWED_SHELVES="skills rules sub-agents tools plugins"
REPAIR_CMD="bash .github/scripts/eco-lock.sh write && git add .eco-registry.lock"

_sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 | awk '{print $1}'
  else openssl dgst -sha256 | awk '{print $NF}'; fi
}

# _field <key> <meta.yml> — value of a flat `key: value` (quotes + trailing space stripped).
_field() {
  awk -v k="$1" '
    $0 ~ ("^" k ":") { sub(/^[^:]*:[[:space:]]*/,""); sub(/[[:space:]]*$/,""); gsub(/^"|"$/,""); print; exit }
  ' "$2"
}

_expose_norm() {
  local raw
  raw="$(_field expose "$1" | tr -d '[]' | tr ',' ' ')"
  [ -n "$(printf '%s' "$raw" | tr -d '[:space:]')" ] || raw="cursor claude codex"
  printf '%s' "$raw" | tr ' ' '\n' | grep -v '^$' | LC_ALL=C sort -u | paste -sd' ' -
}

_kind_shelf() {
  case "$1" in
    skill)     printf 'skills\n' ;;
    rule)      printf 'rules\n' ;;
    sub-agent) printf 'sub-agents\n' ;;
    tool)      printf 'tools\n' ;;
    plugin)    printf 'plugins\n' ;;
    mcp)       printf 'mcp\n' ;;
    workflow)  printf 'workflows\n' ;;
    asset|doc) printf 'tools\n' ;;
    *)         printf '' ;;
  esac
}

_is_allowed_shelf() {
  case " $ALLOWED_SHELVES " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

_has_shelf_metas() {
  local scope="$1" shelf m
  for shelf in $ALLOWED_SHELVES; do
    for m in "$scope/$shelf"/*/meta.yml; do [ -f "$m" ] && return 0; done
  done
  return 1
}

_validate_meta() {
  local m="$1" id kind scope expected_shelf source_scope source_shelf source_id
  id="$(_field id "$m")"
  kind="$(_field kind "$m")"
  scope="$(_field scope "$m")"
  expected_shelf="$(_kind_shelf "$kind")"
  [ -n "$id" ] || { printf 'eco-lock: FAIL  %s missing id\n' "$m" >&2; return 1; }
  [ -n "$kind" ] || { printf 'eco-lock: FAIL  %s missing kind\n' "$m" >&2; return 1; }
  [ -n "$scope" ] || { printf 'eco-lock: FAIL  %s missing scope\n' "$m" >&2; return 1; }
  [ -n "$expected_shelf" ] || { printf 'eco-lock: FAIL  %s unknown kind %s\n' "$m" "$kind" >&2; return 1; }

  case "$m" in
    global/*/*/meta.yml|local/*/*/meta.yml)
      source_scope="${m%%/*}"
      source_shelf="${m#*/}"; source_shelf="${source_shelf%%/*}"
      source_id="$(basename "$(dirname "$m")")"
      _is_allowed_shelf "$source_shelf" || {
        printf 'eco-lock: FAIL  %s unknown shelf %s (allowed: %s)\n' "$m" "$source_shelf" "$ALLOWED_SHELVES" >&2
        return 1
      }
      [ "$scope" = "$source_scope" ] || {
        printf 'eco-lock: FAIL  %s scope=%s but path scope is %s\n' "$m" "$scope" "$source_scope" >&2
        return 1
      }
      [ "$source_shelf" = "$expected_shelf" ] || {
        printf 'eco-lock: FAIL  %s kind=%s belongs on shelf %s, not %s\n' "$m" "$kind" "$expected_shelf" "$source_shelf" >&2
        return 1
      }
      [ "$source_id" = "$id" ] || {
        printf 'eco-lock: FAIL  %s id=%s but directory is %s\n' "$m" "$id" "$source_id" >&2
        return 1
      }
      ;;
    global/*/meta.yml|local/*/meta.yml)
      printf 'eco-lock: FAIL  stale flat path %s (use global|local/{skills,rules,sub-agents,tools}/<id>/meta.yml)\n' "$m" >&2
      return 1 ;;
    */meta.yml)
      source_id="$(basename "$(dirname "$m")")"
      [ "$source_id" = "$id" ] || {
        printf 'eco-lock: FAIL  %s id=%s but directory is %s\n' "$m" "$id" "$source_id" >&2
        return 1
      }
      ;;
  esac
}

_source_shelf() {
  local m="$1" kind source_shelf
  case "$m" in
    global/*/*/meta.yml|local/*/*/meta.yml)
      source_shelf="${m#*/}"; printf '%s\n' "${source_shelf%%/*}" ;;
    *) kind="$(_field kind "$m")"; _kind_shelf "$kind" ;;
  esac
}

# _digest_meta <meta.yml> — sha256 over the canonical capability-contract fields. expose tokens are
# sorted so a pure reordering is not spurious drift.
_digest_meta() {
  local m="$1" expose shelf source_path shape sync_policy descriptor_ref
  expose="$(_expose_norm "$m")"
  shelf="$(_source_shelf "$m")"
  source_path="$m"; source_path="${source_path%/meta.yml}"
  shape="$(_field shape "$m")"
  sync_policy="$(_field sync_policy "$m")"
  descriptor_ref="$(_field descriptor_ref "$m")"
  {
    printf 'id=%s\n'                "$(_field id "$m")"
    printf 'kind=%s\n'              "$(_field kind "$m")"
    printf 'shelf=%s\n'             "$shelf"
    printf 'flavor=%s\n'            "$(_field flavor "$m")"
    printf 'scope=%s\n'             "$(_field scope "$m")"
    printf 'source_path=%s\n'       "$source_path"
    printf 'shape=%s\n'             "$shape"
    printf 'sync_policy=%s\n'       "$sync_policy"
    printf 'owner=%s\n'             "$(_field owner "$m")"
    printf 'install=%s\n'           "$(_field install "$m")"
    printf 'expose=%s\n'            "$expose"
    printf 'provenance_source=%s\n' "$(_field provenance_source "$m")"
    printf 'provenance_ref=%s\n'    "$(_field provenance_ref "$m")"
    if [ -n "$descriptor_ref" ]; then
      printf 'descriptor_ref=%s\n' "$descriptor_ref"
    fi
  } | _sha
}

# _metas — every capability meta.yml, layout-aware.
_metas() {
  local scope shelf m flat
  if [ -d global ] || [ -d local ]; then
    for scope in global local; do
      [ -d "$scope" ] || continue
      for m in "$scope"/*/*/meta.yml; do
        [ -f "$m" ] || continue
        shelf="${m#*/}"; shelf="${shelf%%/*}"
        if ! _is_allowed_shelf "$shelf"; then
          printf 'eco-lock: FAIL  %s unknown shelf %s (allowed: %s)\n' "$m" "$shelf" "$ALLOWED_SHELVES" >&2
          return 1
        fi
      done
      if _has_shelf_metas "$scope"; then
        for flat in "$scope"/*/meta.yml; do
          [ -f "$flat" ] || continue
          printf 'eco-lock: FAIL  stale flat path %s after kind shelves are present under %s/\n' "$flat" "$scope" >&2
          return 1
        done
        for shelf in $ALLOWED_SHELVES; do
          for m in "$scope/$shelf"/*/meta.yml; do
            [ -f "$m" ] || continue
            _validate_meta "$m" || return 1
            printf '%s\n' "$m"
          done
        done
      else
        for m in "$scope"/*/meta.yml; do
          [ -f "$m" ] || continue
          _validate_meta "$m" || return 1
          printf '%s\n' "$m"
        done
      fi
    done
  else
    for m in */meta.yml; do
      [ -f "$m" ] || continue
      if grep -qE '^schema:[[:space:]]*kp-capability/v1' "$m"; then
        _validate_meta "$m" || return 1
        printf '%s\n' "$m"
      fi
    done
  fi
}

_gen() {
  local metas seen_ids="" id
  metas="$(_metas)" || return 1
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    id="$(_field id "$m")"; [ -n "$id" ] || id="$(basename "$(dirname "$m")")"
    case " $seen_ids " in
      *" $id "*) printf 'eco-lock: FAIL  duplicate id %s (ids are globally unique until tuple-key registry support lands)\n' "$id" >&2; return 1 ;;
      *) seen_ids="$seen_ids $id" ;;
    esac
  done <<EOF
$metas
EOF
  printf 'schema: eco-lock/v1\n'
  printf '# generated by .github/scripts/eco-lock.sh write — do NOT hand-edit. CI asserts parity.\n'
  printf '%s\n' "$metas" | while IFS= read -r m; do
    [ -n "$m" ] || continue
    local id kind shelf source_path shape sync_policy
    id="$(_field id "$m")"; [ -n "$id" ] || id="$(basename "$(dirname "$m")")"
    kind="$(_field kind "$m")"
    shelf="$(_source_shelf "$m")"
    source_path="${m%/meta.yml}"
    shape="$(_field shape "$m")"
    sync_policy="$(_field sync_policy "$m")"
    printf '%s  %s  scope=%s  shelf=%s  kind=%s  source_path=%s' \
      "$id" "$(_digest_meta "$m")" "$(_field scope "$m")" "$shelf" "$kind" "$source_path"
    [ -n "$shape" ] && printf '  shape=%s' "$shape"
    [ -n "$sync_policy" ] && printf '  sync_policy=%s' "$sync_policy"
    printf '\n'
  done | LC_ALL=C sort
}

case "${1:-}" in
  write)
    _gen > "$LOCK" || { rm -f "$LOCK"; exit 1; }
    printf 'eco-lock: wrote %s (%s entries)\n' "$LOCK" "$(grep -cvE '^(schema:|#)' "$LOCK" 2>/dev/null || echo 0)" ;;
  check)
    [ -f "$LOCK" ] || { printf 'eco-lock: FAIL  no %s present (run: %s)\n' "$LOCK" "$REPAIR_CMD"; exit 1; }
    tmp="$(mktemp)" || { printf 'eco-lock: FAIL  could not create temp file\n' >&2; exit 1; }
    _gen > "$tmp" || { rm -f "$tmp"; exit 1; }
    if cmp -s "$tmp" "$LOCK"; then printf 'eco-lock: OK (%s in parity)\n' "$LOCK"; rm -f "$tmp"
    else printf 'eco-lock: FAIL  %s out of date — regenerate with: %s\n' "$LOCK" "$REPAIR_CMD"; diff -u "$LOCK" "$tmp" | sed 's/^/    /'; rm -f "$tmp"; exit 1; fi ;;
  digest)
    [ -n "${2:-}" ] || { echo "usage: eco-lock.sh digest <meta.yml>"; exit 2; }
    _digest_meta "$2" ;;
  *) sed -n '2,18p' "$0"; exit 2 ;;
esac
