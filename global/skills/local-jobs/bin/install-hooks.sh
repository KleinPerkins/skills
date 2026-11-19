#!/usr/bin/env bash
# Install the local-jobs repo-local pre-commit hook into the active git hooks
# path so the managed pre-commit dispatcher chains it.
#
# Idempotent: symlinks hooks/pre-commit.local -> <hooksPath>/pre-commit.local.
# Re-runnable any time; safe to run after `make fix-hooks` reinstalls the
# managed guards. Honors core.hooksPath (husky/lefthook-aware).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

hooks_path="$(git config core.hooksPath || true)"
hooks_path="${hooks_path:-.git/hooks}"
mkdir -p "$hooks_path"

src="$root/hooks/pre-commit.local"
dst="$hooks_path/pre-commit.local"
[[ -f "$src" ]] || { echo "missing $src" >&2; exit 1; }
chmod +x "$src"
ln -sfn "$src" "$dst"
echo "installed: $dst -> $src"

if [[ -f "$hooks_path/pre-commit" ]] && ! grep -q 'pre-commit.local' "$hooks_path/pre-commit"; then
  echo "WARN: $hooks_path/pre-commit does not chain pre-commit.local." >&2
  echo "      Refresh the repository's managed hook dispatcher before relying on this hook." >&2
fi
