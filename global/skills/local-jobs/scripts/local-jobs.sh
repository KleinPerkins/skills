#!/usr/bin/env bash
# Co-located wrapper for IDE agents. Keeps operator state/config overrides, but
# drops harness-only variables that could point the skill at a stale sandbox.
set -euo pipefail

WRAPPER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd -- "$WRAPPER_DIR/.." && pwd)"

if [[ "${LOCAL_JOBS_PRESERVE_HARNESS_ENV:-0}" != "1" ]]; then
  unset LOCAL_JOBS_HOME LOCAL_JOBS_REGISTRY LOCAL_JOBS_LAUNCHD_DISABLE LOCAL_JOBS_LAUNCHAGENTS_DIR
else
  unset LOCAL_JOBS_HOME LOCAL_JOBS_REGISTRY
fi

export LOCAL_JOBS_STATE="${LOCAL_JOBS_STATE:-$HOME/.local-jobs}"

_find_repo_venv_python() {
  local candidate="" dir="$SKILL_DIR" repo_root=""

  if git -C "$SKILL_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    repo_root="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$repo_root" ]]; then
      candidate="$repo_root/_ops/.venv/bin/python3"
      if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  fi

  if [[ "$SKILL_DIR" == */quiver/skills/local-jobs* ]]; then
    candidate="${SKILL_DIR%%/quiver/*}/_ops/.venv/bin/python3"
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  dir="$SKILL_DIR"
  while [[ "$dir" != "/" ]]; do
    candidate="$dir/_ops/.venv/bin/python3"
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

_resolve_python() {
  local py="${LOCAL_JOBS_PYTHON:-python3}" fallback=""
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import yaml' >/dev/null 2>&1; then
    LOCAL_JOBS_PYTHON="$py"
    return 0
  fi
  fallback="$(_find_repo_venv_python || true)"
  if [[ -n "$fallback" ]] && "$fallback" -c 'import yaml' >/dev/null 2>&1; then
    LOCAL_JOBS_PYTHON="$fallback"
    return 0
  fi
  printf 'ERROR: PyYAML is required for local-jobs under %s
' "${LOCAL_JOBS_PYTHON:-python3}" >&2
  if [[ -n "$fallback" ]]; then
    printf 'Hint: repo _ops venv fallback not usable: %s
' "$fallback" >&2
  fi
  exit 2
}

_resolve_python
export LOCAL_JOBS_PYTHON
export LOCAL_JOBS_HOME="$SKILL_DIR"
exec "$SKILL_DIR/bin/local-jobs.sh" "$@"
