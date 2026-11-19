#!/usr/bin/env bash
# Read-only source/dependency check. Managed exposure belongs to the generic bootstrap.
set -euo pipefail
case "${1:---doctor}" in
  --doctor) [ "$#" -le 1 ] || exit 2 ;;
  --help|-h) printf '%s\n' 'Read-only source check: install.sh [--doctor]'; exit 0 ;;
  *) printf '%s\n' 'Unsupported lifecycle argument.' >&2; exit 2 ;;
esac
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
python3 -I -B - "$SRC" <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys

def unavailable():
    print(json.dumps({'status': 'unavailable', 'reason': 'source-dependency-unverified'}))
    raise SystemExit(3)

try:
    if sys.version_info < (3, 10):
        unavailable()
    skill = Path(sys.argv[1]).resolve(strict=True)
    root = skill.parents[2]
    if skill.name not in ('agent-route', 'ecosystem-search') or skill != root / 'global' / 'skills' / skill.name:
        unavailable()
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS='0')
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], env=env, check=True,
                              capture_output=True, timeout=5).stdout.decode().strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != root:
        unavailable()
    remote = git('config', '--local', '--no-includes', '--get', 'remote.origin.url')
    if remote not in ('git@github.com:KleinPerkins/skills.git',
                       'https://github.com/KleinPerkins/skills.git',
                       'https://github.com/KleinPerkins/skills'):
        unavailable()
    relative = 'global/tools/ecosystem-index/ecosystem_index.py'
    tool = root / relative
    if not tool.is_file() or tool.is_symlink() or tool.resolve() != tool:
        unavailable()
    tool_directory = 'global/tools/ecosystem-index/'
    required = ('ecosystem_index.py', 'lib/__init__.py', 'lib/contracts.py',
                'lib/engine.py', 'lib/adapters.py', 'lib/io_safe.py', 'lib/deadline.py',
                'tool.yml', 'meta.yml', 'requirements.txt', 'schemas/config-v1.json',
                'schemas/metadata-v1.json', 'schemas/snapshot-v1.json', 'schemas/result-v1.json')
    payloads = [tool_directory + part for part in required]
    payloads.append(str(skill.relative_to(root) / 'SKILL.md'))
    for payload in payloads:
        path = root / payload
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            unavailable()
    git('ls-files', '--error-unmatch', '--', *payloads)
    print(json.dumps({'status': 'ready', 'source_root': str(root), 'tool': str(tool)}))
except (OSError, ValueError, IndexError, UnicodeError, subprocess.SubprocessError):
    unavailable()
PY
