#!/usr/bin/env python3
"""Portable exclusive file lock wrapper (macOS has no flock(1)).

Usage: flock.py <lockfile> <command> [args...]

Acquires an exclusive advisory lock on <lockfile> (created if needed), runs the
command while holding it, releases on exit. Used to serialize per-repo git
operations so overlapping launchd agents never collide on the same worktree.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: flock.py <lockfile> <command> [args...]", file=sys.stderr)
        return 2
    lockfile = sys.argv[1]
    cmd = sys.argv[2:]
    os.makedirs(os.path.dirname(lockfile) or ".", exist_ok=True)
    with open(lockfile, "w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return subprocess.run(cmd).returncode
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    raise SystemExit(main())
