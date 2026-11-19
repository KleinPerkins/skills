# Update Skills

A meta-skill that pulls the latest skills and rules from the ai-product starter kit and installs them globally for both Claude Code and Cursor.

## What This Does

When invoked, this skill:
- Pulls the latest `main` from the ai-product repo (or clones it if missing)
- Copies all skills from `shared-global/starter-kit/skills/` to `~/.claude/skills/` and `~/.cursor/skills/`
- Copies all Cursor rules from `shared-global/starter-kit/rules/` to `~/.cursor/rules/`
- Installs itself so `/update-skills` keeps working

## Prerequisites

- **Cursor** or **Claude Code**
- Access to the [ai-product repo](https://github.com/Affirm/ai-product)
- Git configured with GitHub access

## First-Time Installation

Since you need the skill to install skills, bootstrap it manually:

```bash
# Clone the repo if you haven't already
git clone https://github.com/Affirm/ai-product.git ~/Documents/code/ai-product

# Install for Claude Code
mkdir -p ~/.claude/skills/update-skills
cp ~/Documents/code/ai-product/shared-global/skills/update-skills/SKILL.md ~/.claude/skills/update-skills/SKILL.md

# Install for Cursor
mkdir -p ~/.cursor/skills/update-skills
cp ~/Documents/code/ai-product/shared-global/skills/update-skills/SKILL.md ~/.cursor/skills/update-skills/SKILL.md
```

Then run `/update-skills` to install everything else.

## Usage

- `/update-skills` — install/update all skills and rules
- `/update-skills skills only` — only install skills, skip rules
- `/update-skills rules only` — only install Cursor rules, skip skills

## Author

Created by Miki Ovshievich
