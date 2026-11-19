# Session Close (Claude Code Skill)

A Claude Code skill that runs a structured checklist before ending a session — verifying changes are saved, synced to Git, learnings are captured, feedback is logged, and documentation is updated.

## What It Does

- **Verifies all changes are saved** — Reads modified files to confirm edits persisted
- **Compares local vs Git** — Diffs local agent/KB files against the ai-product repo to detect drift
- **Captures learnings** — Identifies mistakes, surprises, and discoveries from the session, applies a criticality filter, and writes approved learnings to the appropriate CLAUDE.md
- **Logs feedback** — Prompts for bugs, friction, or feature requests about Claude's performance
- **Updates documentation** — Flags any artifacts that need new or updated docs
- **Syncs Git** — Commits, pushes, and optionally creates PRs to contribute local changes back
- **Updates memory** — Persists cross-session insights to MEMORY.md

## Who Is This For

- Anyone using Claude Code for substantive work sessions where changes should be tracked
- Product Council users who modify agents or knowledge bases locally

## How to Use

Trigger with any of these phrases:
```
/session-close
"let's wrap up"
"done for now"
"closing out"
"end session"
```

The skill runs all seven checks and presents a consolidated report.

## The Seven Checks

| # | Check | What It Does |
|---|-------|-------------|
| 1 | **Changes Saved** | Verifies file modifications are persisted |
| 2 | **File Sync** | Compares local agent/KB files against Git repo |
| 3 | **Learnings Captured** | Identifies and writes critical learnings to CLAUDE.md |
| 4 | **Feedback Logged** | Records issues, bugs, or suggestions |
| 5 | **Docs Updated** | Ensures documentation reflects changes made |
| 6 | **Git Sync** | Commits, pushes, and contributes back changes |
| 7 | **Memory Updated** | Updates MEMORY.md with session-spanning insights |

## Quick Mode

For a fast check, the skill can output a compact summary:

```
Quick session close:
- 3 files modified and saved
- Agent Council: 19 core + 2 experimental agents, 8 KBs in sync
- No critical learnings
- No feedback
- Docs current
- Git: committed and pushed
- No memory updates

Ready to close.
```

## Installation

This skill is installed automatically via the [`/update-skills`](../update-skills/) skill, which copies it to `~/.claude/skills/session-close/`.

**Manual installation:**
```bash
cp -r shared-global/starter-kit/skills/session-close/ ~/.claude/skills/session-close/
```

## File Structure

```
session-close/
├── SKILL.md      # Full skill definition with all 7 checks
└── README.md     # This file
```

## Learnings Criticality Filter

Not every observation gets written down. Each potential learning must pass a 3-question test:

1. **Would this apply to future sessions?** (eliminates one-off issues)
2. **Is this something Claude wouldn't already know?** (eliminates general knowledge)
3. **Would forgetting this cause significant problems?** (eliminates low-stakes items)

Learnings are always presented for user approval before writing.

## Contribute-Back Flow

If you modified agents, KBs, or skills locally during the session, the Git Sync step will:
1. Diff your local files against the ai-product repo
2. Show what changed (core agents, experimental agents, KBs, skills)
3. Offer to create a PR to contribute changes back

---

**Author:** Patrick (phobanaffirm)
**Version:** 1.0.0
**Last updated:** February 2026
