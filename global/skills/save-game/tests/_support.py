"""Shared test helpers (not a test module itself — no `test_` prefix, so unittest
discover skips it while other test files can still `import _support`)."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


@contextlib.contextmanager
def isolated_xdg_roots():
    """Point XDG_STATE_HOME/XDG_CONFIG_HOME at a throwaway tempdir so tests never
    touch the operator's real save-game state."""
    with tempfile.TemporaryDirectory(prefix="save-game-test-") as tmp:
        state = Path(tmp) / "state"
        config = Path(tmp) / "config"
        state.mkdir()
        config.mkdir()
        keys = ("XDG_STATE_HOME", "XDG_CONFIG_HOME")
        old = {k: os.environ.get(k) for k in keys}
        os.environ["XDG_STATE_HOME"] = str(state)
        os.environ["XDG_CONFIG_HOME"] = str(config)
        try:
            yield Path(tmp)
        finally:
            for k in keys:
                if old[k] is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old[k]


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def make_git_repo(tmp_path: Path, *, branch: str = "main", remote_url: str | None = None) -> Path:
    repo = Path(tmp_path) / f"repo-{os.urandom(4).hex()}"
    repo.mkdir()
    _git(repo.parent, "init", "-q", "-b", branch, str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    if remote_url:
        _git(repo, "remote", "add", "origin", remote_url)
    return repo


def make_bare_git_repo(tmp_path: Path) -> Path:
    """A bare repo WITH history (cloned --bare from a throwaway seed repo) so
    `git rev-parse HEAD` resolves to a real commit rather than an empty ref."""
    seed = make_git_repo(tmp_path, branch="main")
    bare = Path(tmp_path) / f"bare-{os.urandom(4).hex()}.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True)
    return bare
