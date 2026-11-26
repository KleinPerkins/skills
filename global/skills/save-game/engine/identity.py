"""Root/workstream identity resolution (plan: normative glossary — Root identity,
Workstream, and the repo_key/clone_key/workstream_key hashing rules).

`repo_key` hashes a proven remote identity (`github:owner/repo`, never a raw path
segment) or, when none is proven, the canonical root. `clone_key` hashes the Git
common-dir (or the canonical root path for non-Git roots) so two clones of one
remote never share storage. MVP binds exactly one anchor root per workstream —
multi-root binding is out of scope here by the plan's own deferral.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import canonical

_GITHUB_REMOTE_RE = re.compile(
    r"^(?:git@|ssh://git@|https://|git://)?github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$"
)
_COMMIT_ID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


@dataclass(frozen=True)
class RootIdentity:
    ref_kind: str  # branch | detached | bare | non_git
    physical_root: str
    branch: Optional[str]
    detached_commit: Optional[str]
    observed_head: str
    common_dir: Optional[str]  # absolute real path; None for non_git
    git_dir: Optional[str]  # per-worktree git dir; None for non_git
    remote_identity: Optional[str]  # "github:owner/repo" only when uniquely proven
    operation_marker: str  # none | merge | rebase | cherry_pick | revert | bisect


def _git_environment() -> dict[str, str]:
    # An explicit root must not inherit a caller's repository, worktree,
    # object store or Git configuration (for example, from a Git hook).
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", GIT_OPTIONAL_LOCKS="0")
    return env


def _run_git(root: str, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "--no-replace-objects", "-C", root, *args],
            env=_git_environment(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def prove_ancestry(root: str, saved_head: str, live_head: str) -> Optional[bool]:
    """Return whether the live commit descends from the saved commit, using local history."""
    if not _COMMIT_ID_RE.fullmatch(saved_head) or not _COMMIT_ID_RE.fullmatch(live_head):
        return None
    git = ["git", "--no-replace-objects", "-C", root]
    env = _git_environment()
    try:
        proof = subprocess.run(
            [*git, "merge-base", "--is-ancestor", saved_head, live_head],
            env=env, capture_output=True, text=True, timeout=5,
        )
        if proof.returncode == 0:
            return True
        if proof.returncode != 1:
            return None
        shallow = subprocess.run(
            [*git, "rev-parse", "--is-shallow-repository"],
            env=env, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if shallow.returncode == 0 and shallow.stdout.strip() == "false":
        return False
    return None


def _proven_remote_identity(root: str) -> Optional[str]:
    url = _run_git(root, "remote", "get-url", "origin")
    if not url:
        names = _run_git(root, "remote")
        first = (names or "").splitlines()
        if not first:
            return None
        url = _run_git(root, "remote", "get-url", first[0])
    if not url:
        return None
    match = _GITHUB_REMOTE_RE.match(url.strip())
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    return f"github:{owner}/{repo}"


def _operation_marker(git_dir: str) -> str:
    checks = [
        ("MERGE_HEAD", "merge"),
        ("CHERRY_PICK_HEAD", "cherry_pick"),
        ("REVERT_HEAD", "revert"),
        ("BISECT_LOG", "bisect"),
    ]
    for filename, marker in checks:
        if Path(git_dir, filename).exists():
            return marker
    if Path(git_dir, "rebase-merge").is_dir() or Path(git_dir, "rebase-apply").is_dir():
        return "rebase"
    return "none"


def resolve_root_identity(start_path: str) -> RootIdentity:
    start_path = str(Path(start_path).resolve())
    toplevel = _run_git(start_path, "rev-parse", "--show-toplevel")
    is_bare = _run_git(start_path, "rev-parse", "--is-bare-repository")

    if toplevel is None and is_bare is None:
        # Not a Git root at all (git itself couldn't even answer) -> non_git.
        return RootIdentity(
            ref_kind="non_git",
            physical_root=start_path,
            branch=None,
            detached_commit=None,
            observed_head="",
            common_dir=None,
            git_dir=None,
            remote_identity=None,
            operation_marker="none",
        )

    common_dir_raw = _run_git(start_path, "rev-parse", "--git-common-dir")
    git_dir_raw = _run_git(start_path, "rev-parse", "--git-dir")
    common_dir = str(Path(start_path, common_dir_raw).resolve()) if common_dir_raw else None
    git_dir = str(Path(start_path, git_dir_raw).resolve()) if git_dir_raw else common_dir
    remote_identity = _proven_remote_identity(start_path)
    operation_marker = _operation_marker(git_dir) if git_dir else "none"

    if is_bare == "true":
        observed_head = _run_git(start_path, "rev-parse", "HEAD") or ""
        return RootIdentity(
            ref_kind="bare",
            physical_root=str(Path(toplevel).resolve()) if toplevel else start_path,
            branch=None,
            detached_commit=None,
            observed_head=observed_head,
            common_dir=common_dir,
            git_dir=git_dir,
            remote_identity=remote_identity,
            operation_marker=operation_marker,
        )

    physical_root = str(Path(toplevel).resolve()) if toplevel else start_path
    observed_head = _run_git(start_path, "rev-parse", "HEAD") or ""
    symbolic = _run_git(start_path, "symbolic-ref", "-q", "--short", "HEAD")
    if symbolic:
        return RootIdentity(
            ref_kind="branch",
            physical_root=physical_root,
            branch=symbolic,
            detached_commit=None,
            observed_head=observed_head,
            common_dir=common_dir,
            git_dir=git_dir,
            remote_identity=remote_identity,
            operation_marker=operation_marker,
        )
    return RootIdentity(
        ref_kind="detached",
        physical_root=physical_root,
        branch=None,
        detached_commit=observed_head,
        observed_head=observed_head,
        common_dir=common_dir,
        git_dir=git_dir,
        remote_identity=remote_identity,
        operation_marker=operation_marker,
    )


def _canonical_root_for_repo_key(identity: RootIdentity) -> str:
    # No proven remote: repo_key falls back to a canonical root. For Git roots
    # that is the shared common-dir (unifies worktrees of one clone); for
    # non_git it is the physical root itself.
    return identity.common_dir or identity.physical_root


def repo_key_for(identity: RootIdentity) -> str:
    basis = identity.remote_identity or _canonical_root_for_repo_key(identity)
    return canonical.sha256_hex(basis.encode("utf-8"))


def clone_key_for(identity: RootIdentity) -> str:
    basis = identity.common_dir or identity.physical_root
    return canonical.sha256_hex(basis.encode("utf-8"))


def common_dir_key_for(identity: RootIdentity) -> Optional[str]:
    if not identity.common_dir:
        return None
    return canonical.sha256_hex(identity.common_dir.encode("utf-8"))


def remote_identity_key_for(identity: RootIdentity) -> Optional[str]:
    if not identity.remote_identity:
        return None
    return canonical.sha256_hex(identity.remote_identity.encode("utf-8"))


def _ref_identity_value(identity: RootIdentity) -> str:
    """The stable (non-volatile) portion of the Workstream tuple's ref_identity.

    A branch name is stable across ordinary commits on that branch (does not
    fragment the workstream); detached HEAD has no branch, so the exact commit
    IS the ref identity (matches "never invent a branch"); bare/non_git use a
    fixed sentinel since MVP makes no working-tree claim there.
    """
    if identity.ref_kind == "branch":
        return identity.branch or ""
    if identity.ref_kind == "detached":
        return identity.detached_commit or ""
    return identity.ref_kind  # "bare" or "non_git" sentinel


def workstream_key_for(repo_key: str, clone_key: str, task_id: str, identity: RootIdentity) -> str:
    basis = canonical.canonical_bytes(
        {
            "repo_key": repo_key,
            "clone_key": clone_key,
            "task_id": task_id,
            "ref_kind": identity.ref_kind,
            "ref_value": _ref_identity_value(identity),
        }
    )
    return canonical.sha256_hex(basis)


def root_snapshot_dict(identity: RootIdentity, *, include_remote: bool = True) -> dict:
    """The `root` object shape shared by current.v1 (full) and journal-prepared's
    slightly smaller `observed_root` (no remote_identity_key — see that schema)."""
    doc: dict = {
        "ref_kind": identity.ref_kind,
        "observed_head": identity.observed_head[:64],
        "operation_marker": identity.operation_marker,
    }
    if identity.branch:
        doc["branch"] = identity.branch[:200]
    common_key = common_dir_key_for(identity)
    if common_key:
        doc["common_dir_key"] = common_key
    if include_remote:
        remote_key = remote_identity_key_for(identity)
        if remote_key:
            doc["remote_identity_key"] = remote_key
    return doc


def default_start_path() -> str:
    return os.getcwd()
