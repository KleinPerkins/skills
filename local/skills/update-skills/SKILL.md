---
name: update-skills
description: Use when a user wants to install or update their AI skills, rules, agents, and knowledge bases from the ai-product repo. Pulls latest from GitHub, installs skills to Claude Code and Cursor globally, installs Cursor rules, and installs Product Council agents and knowledge bases.
allowed-tools: Bash, Read, Glob, AskUserQuestion
argument-hint: '[optional: "skills only" or "rules only"]'
---

# Update Skills

This skill pulls the latest skills, rules, agents, and knowledge bases from the [ai-product](https://github.com/Affirm/ai-product) repository and installs them globally for both **Claude Code** and **Cursor**.

---

## Sources

| Content | Source in Repo | Installed To |
|---------|---------------|-------------|
| Skills | `shared-global/starter-kit/skills/` | `~/.claude/skills/` + `~/.cursor/skills/` |
| Rules | `shared-global/starter-kit/rules/` | `~/.cursor/rules/` |
| Agents | `shared-team/product-management/product-council/agents/` | `~/.claude/agents/` |
| Knowledge Bases | `shared-team/product-management/product-council/knowledge-bases/` | `~/.claude/knowledge-bases/` |

---

## Step 1: Ensure the ai-product repo is available

Check if the repo exists at `$HOME/Documents/code/ai-product`:

```bash
ls $HOME/Documents/code/ai-product/.git
```

If it exists, pull latest main:

```bash
cd $HOME/Documents/code/ai-product && git checkout main && git pull origin main
```

If it does NOT exist, clone it:

```bash
git clone https://github.com/Affirm/ai-product.git $HOME/Documents/code/ai-product
```

---

## Step 2: Discover what's available

List all skills in the starter kit:

```bash
ls $HOME/Documents/code/ai-product/shared-global/starter-kit/skills/
```

List all rules in the starter kit:

```bash
ls $HOME/Documents/code/ai-product/shared-global/starter-kit/rules/*.mdc
```

Check if Product Council exists:

```bash
ls $HOME/Documents/code/ai-product/shared-team/product-management/product-council/agents/
```

Show the user what will be installed. If `$ARGUMENTS` specifies "skills only" or "rules only", respect that and skip the other.

---

## Step 3: Install skills

### 3.1 Claude Code (global)

For each skill directory in `shared-global/starter-kit/skills/`, copy the entire directory to `~/.claude/skills/`:

```bash
mkdir -p ~/.claude/skills
```

Then for each skill:

```bash
cp -r $HOME/Documents/code/ai-product/shared-global/starter-kit/skills/{skill-name} ~/.claude/skills/{skill-name}
```

### 3.2 Cursor (global)

For each skill directory, copy to `~/.cursor/skills/`:

```bash
mkdir -p ~/.cursor/skills
```

Then for each skill:

```bash
cp -r $HOME/Documents/code/ai-product/shared-global/starter-kit/skills/{skill-name} ~/.cursor/skills/{skill-name}
```

---

## Step 4: Install rules (Cursor only)

Copy all `.mdc` rule files to `~/.cursor/rules/`:

```bash
mkdir -p ~/.cursor/rules
cp $HOME/Documents/code/ai-product/shared-global/starter-kit/rules/*.mdc ~/.cursor/rules/
```

Skip this step if the user specified "skills only".

---

## Step 5: Install Product Council

**Purpose:** Install the Product Council agents and knowledge bases that power the `/council` skill.

Check if the Product Council directory exists:

```bash
ls $HOME/Documents/code/ai-product/shared-team/product-management/product-council/agents/ 2>/dev/null
```

If it does NOT exist, skip this step and report: "Product Council not found in repo — skipping agent/KB installation."

If it exists:

### 5.1 Install agents

```bash
mkdir -p ~/.claude/agents
```

**Core agents** (no `status: experimental` in frontmatter): simple overwrite — these are centrally managed.

```bash
# Copy all core agent files from repo
for f in $HOME/Documents/code/ai-product/shared-team/product-management/product-council/agents/*.md; do
  # Skip context files
  [[ "$f" == *"-context.md" ]] && continue
  # Check if it's experimental
  if grep -q '^status: experimental' "$f" 2>/dev/null; then
    continue  # Handle experimental separately below
  fi
  cp "$f" ~/.claude/agents/
done
```

**Experimental agents** (`status: experimental` in frontmatter): protect local edits.

```bash
for f in $HOME/Documents/code/ai-product/shared-team/product-management/product-council/agents/*.md; do
  [[ "$f" == *"-context.md" ]] && continue
  if ! grep -q '^status: experimental' "$f" 2>/dev/null; then
    continue  # Already handled as core above
  fi
  name=$(basename "$f")
  local_file=~/.claude/agents/$name
  if [ ! -f "$local_file" ]; then
    # New team agent — pull it
    cp "$f" "$local_file"
    echo "NEW: $name"
  elif [ "$f" -nt "$local_file" ]; then
    # Git is newer — update
    cp "$f" "$local_file"
    echo "UPDATED: $name"
  elif [ "$local_file" -nt "$f" ]; then
    # Local is newer — protect
    echo "KEPT LOCAL: $name (local changes newer than Git)"
  else
    echo "UNCHANGED: $name"
  fi
done
```

**Companion context files** (`*-context.md`): same merge strategy as experimental agents.

```bash
for f in $HOME/Documents/code/ai-product/shared-team/product-management/product-council/agents/*-context.md; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  local_file=~/.claude/agents/$name
  if [ ! -f "$local_file" ]; then
    cp "$f" "$local_file"
  elif [ "$f" -nt "$local_file" ]; then
    cp "$f" "$local_file"
  fi
  # If local is newer, keep local
done
```

Count and report how many agents were installed (core + experimental).

### 5.2 Install knowledge bases

```bash
mkdir -p ~/.claude/knowledge-bases
cp $HOME/Documents/code/ai-product/shared-team/product-management/product-council/knowledge-bases/*.md ~/.claude/knowledge-bases/
```

Count and report how many knowledge bases were installed.

---

## Step 6: Check for plugin conflicts

Check if the Affirm builders plugin also has council skills:

```bash
ls ~/.claude/plugins/cache/affirm-builders/*/skills/council/SKILL.md 2>/dev/null
```

If found, warn the user:

```
Note: Council skills also exist from the Affirm builders plugin.
Both versions will work, but you may see duplicate skill names.
The Git-installed versions at ~/.claude/skills/ are the primary path.
To avoid duplicates, you can remove the plugin copies at:
  ~/.claude/plugins/cache/affirm-builders/*/skills/council/
  ~/.claude/plugins/cache/affirm-builders/*/skills/session-close/
```

---

## Step 7: Also install this skill (self-install)

The update-skills skill itself lives in `shared-global/skills/update-skills/`, NOT in the starter-kit. Install it so the user can run `/update-skills` in the future:

```bash
mkdir -p ~/.claude/skills/update-skills
cp -r $HOME/Documents/code/ai-product/shared-global/skills/update-skills/SKILL.md ~/.claude/skills/update-skills/SKILL.md
mkdir -p ~/.cursor/skills/update-skills
cp -r $HOME/Documents/code/ai-product/shared-global/skills/update-skills/SKILL.md ~/.cursor/skills/update-skills/SKILL.md
```

---

## Step 8: Report results

Show the user a summary of what was installed. Example:

```
# Update Skills Report

## Skills (Claude Code + Cursor)
| Skill | Status |
|-------|--------|
| council | Installed |
| session-close | Installed |
| create-mlops-page | Installed |
| deploy-mlops-page | Installed |
| update-skills | Self-installed |

## Rules (Cursor)
| Rule | Status |
|------|--------|
| analytics-query.mdc | Installed |
| snowflake-mcp-safety.mdc | Installed |

## Product Council
| Component | Count | Status |
|-----------|-------|--------|
| Core Agents | 20 | Installed to ~/.claude/agents/ |
| Experimental Agents | N | Merged (see details below) |
| Context Files | N | Merged |
| Knowledge Bases | 9 | Installed to ~/.claude/knowledge-bases/ |

## Experimental Agent Sync
| Agent | Action |
|-------|--------|
| risk-scoring.md | NEW — pulled from team |
| canada-market.md | KEPT LOCAL — your edits preserved |
| merchant-success.md | UNCHANGED |

## Locations
- Claude Code skills: ~/.claude/skills/
- Cursor skills: ~/.cursor/skills/
- Cursor rules: ~/.cursor/rules/
- Agents: ~/.claude/agents/
- Knowledge bases: ~/.claude/knowledge-bases/

Run /council to verify the Product Council is working.
To update again later, run /update-skills
```

---

## Important rules

- Install skills and rules from `shared-global/starter-kit/` only.
- Install agents and KBs from `shared-team/product-management/product-council/` only.
- Never install from `community-playground/`, `examples/`, or other directories.
- Always pull latest main before installing to ensure everything is up to date.
- Overwriting existing files is expected and correct — that's how updates work.
- Do NOT modify any files during installation. Copy them exactly as they are.
- If the repo cannot be cloned (no access), tell the user to request access to https://github.com/Affirm/ai-product.
