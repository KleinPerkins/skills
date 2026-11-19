"""Skill installer — build plan v3 §6: "The SSP installer registers CLI, read-only stdio MCP, and
`/operator-voice`." "The skill is a thin conversational veneer and documentation entrypoint. It
does not duplicate business logic or manipulate profile files" (§6).

This module does exactly one thing: place the packaged, version-controlled ``SKILL.md`` (never
generated per-machine, never containing operator data) into each supported agent's skills
directory, atomically and idempotently. It never talks to the application service, persistence, or
network.
"""

from __future__ import annotations

import os
import tempfile
from importlib import resources
from pathlib import Path

SKILL_DIR_NAME = "operator-voice"

# Host -> skills root, each XDG/HOME-relative per this workspace's existing convention (AWA/awa
# meta.yml `expose: cursor claude codex`). A missing HOME override degrades cleanly (skipped, not
# an error) so this never fails an otherwise-successful SSP install.
SUPPORTED_AGENT_SKILL_ROOTS: dict[str, str] = {
    "agents": ".agents/skills",
    "cursor": ".cursor/skills",
    "claude": ".claude/skills",
    "codex": ".codex/skills",
}


def skill_markdown() -> str:
    return resources.files("operator_voice.skill").joinpath("SKILL.md").read_text(encoding="utf-8")


def _atomic_write(dest: Path, content: str) -> bool:
    """Returns True if the file was written/changed, False if it already matched (no-op)."""
    if dest.exists() and dest.read_text(encoding="utf-8") == content:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".skill.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, dest)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return True


def install_skill(home: Path | None = None, agents: tuple[str, ...] | None = None) -> dict[str, bool]:
    """Writes ``SKILL.md`` into every supported, present agent's skills root under ``home``
    (defaults to ``Path.home()``; tests pass a disposable tmp_path). An agent whose root directory
    does not already exist is skipped (never creates a brand-new agent's config tree from
    scratch) — this mirrors the existing skills ecosystem convention that installers populate
    known roots, not invent them. Returns {agent: changed} for every agent actually written."""
    home = home or Path.home()
    agents = agents or tuple(SUPPORTED_AGENT_SKILL_ROOTS)
    content = skill_markdown()
    results: dict[str, bool] = {}
    for agent in agents:
        root = SUPPORTED_AGENT_SKILL_ROOTS.get(agent)
        if root is None:
            continue
        skills_root = home / root
        if not skills_root.exists():
            continue
        dest = skills_root / SKILL_DIR_NAME / "SKILL.md"
        results[agent] = _atomic_write(dest, content)
    return results


def uninstall_skill(home: Path | None = None, agents: tuple[str, ...] | None = None) -> dict[str, bool]:
    """Removes the installed ``SKILL.md`` (and its now-empty directory) for every present agent.
    Returns {agent: removed}."""
    home = home or Path.home()
    agents = agents or tuple(SUPPORTED_AGENT_SKILL_ROOTS)
    results: dict[str, bool] = {}
    for agent in agents:
        root = SUPPORTED_AGENT_SKILL_ROOTS.get(agent)
        if root is None:
            continue
        skill_dir = home / root / SKILL_DIR_NAME
        dest = skill_dir / "SKILL.md"
        removed = dest.exists()
        if removed:
            dest.unlink()
            try:
                skill_dir.rmdir()
            except OSError:
                pass  # not empty (unexpected extra files) — leave it, never force-delete
        results[agent] = removed
    return results


__all__ = ["install_skill", "uninstall_skill", "skill_markdown", "SUPPORTED_AGENT_SKILL_ROOTS"]
