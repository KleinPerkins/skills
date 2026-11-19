#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SOURCE_REPO = SKILL.parents[2]


class RepositoryVerifierTests(unittest.TestCase):
    def test_dev_main_sync_preflight_uses_bash_for_noexec_workspaces(
        self,
    ) -> None:
        verifier = SOURCE_REPO / ".github" / "scripts" / "verify-skills.sh"
        if not verifier.is_file():
            self.skipTest(
                "source-repository verifier is unavailable in vendored payload"
            )
        source = verifier.read_text(encoding="utf-8")
        preflight = (
            "global/tools/dev-main-sync/scripts/"
            "v3-preflight-acceptance.sh"
        )
        self.assertEqual(source.count(f"bash {preflight}"), 2)
        self.assertNotIn(f"&& {preflight}", source)

    def test_duplicate_unknown_or_mutating_agent_frontmatter_is_rejected(self) -> None:
        verifier = SOURCE_REPO / ".github" / "scripts" / "verify-skills.sh"
        lock_writer = SOURCE_REPO / ".github" / "scripts" / "eco-lock.sh"
        if not verifier.is_file() or not lock_writer.is_file():
            self.skipTest(
                "source-repository verifier fixtures are unavailable in vendored payload"
            )
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            scripts = repo / ".github" / "scripts"
            shared_scripts = repo / "scripts"
            agent = repo / "global" / "sub-agents" / "bad-agent"
            scripts.mkdir(parents=True)
            shared_scripts.mkdir(parents=True)
            agent.mkdir(parents=True)
            shutil.copy2(
                verifier,
                scripts / "verify-skills.sh",
            )
            shutil.copy2(
                lock_writer,
                scripts / "eco-lock.sh",
            )
            shutil.copy2(
                SOURCE_REPO / "scripts" / "capability_meta.py",
                shared_scripts / "capability_meta.py",
            )
            (agent / "meta.yml").write_text(
                "\n".join(
                    [
                        "schema: kp-capability/v1",
                        "id: bad-agent",
                        "kind: sub-agent",
                        "flavor: 1",
                        "scope: global",
                        "owner: Fixture",
                        "install: install.sh",
                        "expose: cursor",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            installer = agent / "install.sh"
            installer.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            installer.chmod(0o755)
            (agent / "bad-agent.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: bad-agent",
                        "description: fixture",
                        "model: inherit",
                        "tools: Read, Glob, Grep",
                        "tools: Read, Write",
                        "surprise: enabled",
                        "---",
                        "fixture",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init", str(repo)], check=True, stdout=subprocess.PIPE)
            subprocess.run(
                ["bash", str(scripts / "eco-lock.sh"), "write"],
                cwd=repo,
                check=True,
                stdout=subprocess.PIPE,
            )
            result = subprocess.run(
                ["bash", str(scripts / "verify-skills.sh")],
                cwd=repo,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must appear exactly once", result.stdout)
            self.assertIn("unknown frontmatter key", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
