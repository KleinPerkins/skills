#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
python3 "$DIR/test_consolidator.py"
bash "$DIR/integration_install.sh"
