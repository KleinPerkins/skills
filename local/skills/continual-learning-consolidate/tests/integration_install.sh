#!/usr/bin/env bash
# Every installer invocation and entrypoint uses a child-only synthetic home.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
python3 -B "$SKILL_DIR/tests/test_install_runtime.py"
