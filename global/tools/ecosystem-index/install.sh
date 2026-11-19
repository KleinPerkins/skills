#!/usr/bin/env bash
# Flavor-1/post_mgmt-none lifecycle: read-only source/prerequisite check only.
set -euo pipefail
case "${1:---check}" in
  --check|--install|--uninstall) ;;
  *) printf '%s\n' 'Unsupported lifecycle option.' >&2; exit 2 ;;
esac
if [[ $# -gt 1 ]]; then printf '%s\n' 'Unsupported lifecycle arguments.' >&2; exit 2; fi
source_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null || { printf '%s\n' 'Python 3 unavailable.' >&2; exit 3; }
for file in ecosystem_index.py lib/contracts.py lib/engine.py lib/io_safe.py lib/adapters.py tool.yml requirements.txt; do
  [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || { printf '%s\n' 'Source prerequisite unavailable.' >&2; exit 3; }
done
python3 -B - <<'PY'
import importlib.util
import sys
if sys.version_info < (3, 10):
    print('Python 3.10 or later required.', file=sys.stderr)
    raise SystemExit(3)
print('Source checks passed. YAML parser available.' if importlib.util.find_spec('yaml') else
      'Source checks passed. YAML parser unavailable; YAML refresh will be partial.')
PY
