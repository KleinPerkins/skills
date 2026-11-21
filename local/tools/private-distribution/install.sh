#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
case "${1:-}" in
    --check)
        [ "$#" -eq 1 ] || exit 2
        exec node --test "$root"/tests/*.test.mjs
        ;;
    *)
        printf '%s\n' "Usage: $0 --check" >&2
        exit 2
        ;;
esac
