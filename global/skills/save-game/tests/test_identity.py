import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _support import make_bare_git_repo, make_git_repo  # noqa: E402

from engine import identity  # noqa: E402


class TestResolveRootIdentityBranch(unittest.TestCase):
    def test_branch_checkout_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, branch="feat/x")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.ref_kind, "branch")
            self.assertEqual(ident.branch, "feat/x")
            self.assertEqual(len(ident.observed_head), 40)
            self.assertEqual(ident.operation_marker, "none")
            self.assertIsNotNone(ident.common_dir)
            self.assertIsNone(ident.remote_identity)

    def test_detached_head_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            head = ident.observed_head
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", head], check=True)
            detached = identity.resolve_root_identity(str(repo))
            self.assertEqual(detached.ref_kind, "detached")
            self.assertIsNone(detached.branch)
            self.assertEqual(detached.detached_commit, head)

    def test_non_git_root_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain"
            plain.mkdir()
            ident = identity.resolve_root_identity(str(plain))
            self.assertEqual(ident.ref_kind, "non_git")
            self.assertEqual(ident.observed_head, "")
            self.assertIsNone(ident.common_dir)

    def test_bare_repo_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = make_bare_git_repo(tmp)
            ident = identity.resolve_root_identity(str(bare))
            self.assertEqual(ident.ref_kind, "bare")
            self.assertEqual(len(ident.observed_head), 40)

    def test_github_ssh_remote_is_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, remote_url="git@github.com:Owner/Repo.git")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.remote_identity, "github:Owner/Repo")

    def test_github_https_remote_normalizes_to_same_identity_as_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            ssh_repo = make_git_repo(tmp, remote_url="git@github.com:Owner/Repo.git")
            https_repo = make_git_repo(tmp, remote_url="https://github.com/Owner/Repo")
            ssh_ident = identity.resolve_root_identity(str(ssh_repo))
            https_ident = identity.resolve_root_identity(str(https_repo))
            self.assertEqual(ssh_ident.remote_identity, https_ident.remote_identity)

    def test_non_github_remote_is_not_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, remote_url="https://example.com/owner/repo.git")
            ident = identity.resolve_root_identity(str(repo))
            self.assertIsNone(ident.remote_identity)

    def test_explicit_root_ignores_inherited_git_checkout_context(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as foreign:
            repo = make_git_repo(tmp, remote_url="git@github.com:Owner/Selected.git")
            other = make_git_repo(foreign, remote_url="git@github.com:Owner/Other.git")
            before = identity.resolve_root_identity(str(repo))
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "forward"],
                           check=True)
            selected = identity.resolve_root_identity(str(repo))
            with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(repo)}):
                self.assertEqual(identity.resolve_root_identity(str(repo)), selected)
                self.assertIs(identity.prove_ancestry(str(repo), before.observed_head, selected.observed_head), True)

    def test_linked_worktree_shares_common_dir_but_has_its_own_git_dir(self):
        """Plan verification-strategy gate: "Identity matrix ... linked
        worktrees." A linked worktree is a distinct physical_root/git_dir (its
        own per-worktree HEAD/branch/operation state) that shares the primary
        checkout's common_dir (one shared object store/refs) -- proving
        identity resolution keeps these two notions separate rather than
        conflating "this worktree" with "this repo clone"."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, branch="main")
            wt_path = Path(tmp) / "linked-worktree"
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-q", "-b", "wt-branch", str(wt_path)],
                check=True,
            )
            primary = identity.resolve_root_identity(str(repo))
            linked = identity.resolve_root_identity(str(wt_path))

            self.assertNotEqual(primary.git_dir, linked.git_dir)
            self.assertEqual(primary.common_dir, linked.common_dir)
            self.assertEqual(primary.branch, "main")
            self.assertEqual(linked.branch, "wt-branch")

    def test_linked_worktree_shares_clone_key_but_gets_its_own_workstream_key(self):
        """Same machine-local clone identity (shared common_dir -> shared
        clone_key) for both worktrees of one repo, but a DIFFERENT workstream
        for the same task_id because each worktree sits on its own branch --
        the same "branch affects workstream" rule already proven via in-place
        checkout, now proven via a real linked worktree."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, branch="main", remote_url="git@github.com:Owner/Repo.git")
            wt_path = Path(tmp) / "linked-worktree"
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-q", "-b", "wt-branch", str(wt_path)],
                check=True,
            )
            primary = identity.resolve_root_identity(str(repo))
            linked = identity.resolve_root_identity(str(wt_path))

            repo_key_primary = identity.repo_key_for(primary)
            repo_key_linked = identity.repo_key_for(linked)
            clone_key_primary = identity.clone_key_for(primary)
            clone_key_linked = identity.clone_key_for(linked)
            self.assertEqual(repo_key_primary, repo_key_linked)
            self.assertEqual(clone_key_primary, clone_key_linked)

            ws_primary = identity.workstream_key_for(repo_key_primary, clone_key_primary, "task-x", primary)
            ws_linked = identity.workstream_key_for(repo_key_linked, clone_key_linked, "task-x", linked)
            self.assertNotEqual(ws_primary, ws_linked)


class TestKeyHashing(unittest.TestCase):
    def test_repo_key_and_clone_key_are_hex64(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            repo_key = identity.repo_key_for(ident)
            clone_key = identity.clone_key_for(ident)
            self.assertEqual(len(repo_key), 64)
            self.assertEqual(len(clone_key), 64)
            int(repo_key, 16)
            int(clone_key, 16)

    def test_no_proven_remote_makes_repo_key_equal_clone_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            self.assertIsNone(ident.remote_identity)
            self.assertEqual(identity.repo_key_for(ident), identity.clone_key_for(ident))

    def test_proven_remote_makes_repo_key_independent_of_clone_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo1 = make_git_repo(tmp, remote_url="git@github.com:Owner/Repo.git")
            repo2 = make_git_repo(tmp, remote_url="git@github.com:Owner/Repo.git")
            ident1 = identity.resolve_root_identity(str(repo1))
            ident2 = identity.resolve_root_identity(str(repo2))
            # Same proven remote -> same repo_key even though these are two
            # independent clones (different common dirs) on disk.
            self.assertEqual(identity.repo_key_for(ident1), identity.repo_key_for(ident2))
            # But two distinct clones must never share clone_key/storage.
            self.assertNotEqual(identity.clone_key_for(ident1), identity.clone_key_for(ident2))

    def test_workstream_key_deterministic_and_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            repo_key = identity.repo_key_for(ident)
            clone_key = identity.clone_key_for(ident)
            k1 = identity.workstream_key_for(repo_key, clone_key, "task-abc", ident)
            k2 = identity.workstream_key_for(repo_key, clone_key, "task-abc", ident)
            self.assertEqual(k1, k2)
            self.assertEqual(len(k1), 64)

    def test_different_task_ids_yield_different_workstreams(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            repo_key = identity.repo_key_for(ident)
            clone_key = identity.clone_key_for(ident)
            k1 = identity.workstream_key_for(repo_key, clone_key, "task-a", ident)
            k2 = identity.workstream_key_for(repo_key, clone_key, "task-b", ident)
            self.assertNotEqual(k1, k2)

    def test_same_task_on_different_branch_yields_different_workstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, branch="main")
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "other"], check=True)
            ident_other = identity.resolve_root_identity(str(repo))
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
            ident_main = identity.resolve_root_identity(str(repo))

            repo_key = identity.repo_key_for(ident_main)
            clone_key = identity.clone_key_for(ident_main)
            k_main = identity.workstream_key_for(repo_key, clone_key, "task-x", ident_main)
            k_other = identity.workstream_key_for(repo_key, clone_key, "task-x", ident_other)
            self.assertNotEqual(k_main, k_other)

    def test_root_snapshot_dict_omits_remote_key_when_not_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp, remote_url="git@github.com:Owner/Repo.git")
            ident = identity.resolve_root_identity(str(repo))
            full = identity.root_snapshot_dict(ident, include_remote=True)
            observed = identity.root_snapshot_dict(ident, include_remote=False)
            self.assertIn("remote_identity_key", full)
            self.assertNotIn("remote_identity_key", observed)


class TestOperationMarker(unittest.TestCase):
    """Plan verification-strategy gate: "Git behavior ... mid-merge/rebase/
    cherry-pick/revert/bisect." `_operation_marker` reads real Git evidence
    files/dirs under `git_dir` -- planting the exact same markers Git itself
    creates mid-operation is a faithful, deterministic way to exercise this
    without actually driving a real conflicted merge/rebase."""

    def test_no_operation_in_progress_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "none")

    def test_merge_head_marks_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "MERGE_HEAD").write_text("a" * 40 + "\n")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "merge")

    def test_cherry_pick_head_marks_cherry_pick(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "CHERRY_PICK_HEAD").write_text("a" * 40 + "\n")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "cherry_pick")

    def test_revert_head_marks_revert(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "REVERT_HEAD").write_text("a" * 40 + "\n")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "revert")

    def test_bisect_log_marks_bisect(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "BISECT_LOG").write_text("git bisect start\n")
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "bisect")

    def test_rebase_merge_dir_marks_rebase(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "rebase-merge").mkdir()
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "rebase")

    def test_rebase_apply_dir_marks_rebase(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            (repo / ".git" / "rebase-apply").mkdir()
            ident = identity.resolve_root_identity(str(repo))
            self.assertEqual(ident.operation_marker, "rebase")

    def test_marker_clears_once_operation_directory_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_git_repo(tmp)
            marker = repo / ".git" / "MERGE_HEAD"
            marker.write_text("a" * 40 + "\n")
            mid_merge = identity.resolve_root_identity(str(repo))
            self.assertEqual(mid_merge.operation_marker, "merge")
            marker.unlink()
            after = identity.resolve_root_identity(str(repo))
            self.assertEqual(after.operation_marker, "none")


if __name__ == "__main__":
    unittest.main()
