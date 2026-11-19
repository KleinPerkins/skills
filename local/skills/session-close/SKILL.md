---
name: session-close
description: "Run before closing a session to verify changes are saved, synced to Git, learnings are captured, feedback is logged, and docs are updated. Trigger: session close, wrap up, done for now, closing out, end session."
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Session Close Checklist

Run this before ending a productive session to ensure nothing is lost and everything is in sync.

## When to Use

- Before closing a session where you made changes
- When the user says "let's wrap up", "done for now", "closing out"
- Proactively at the end of any session with substantive work

## The Seven Checks

| # | Check | Purpose |
|---|-------|---------|
| 1 | **Changes Saved** | Verify file modifications are persisted |
| 2 | **File Sync** | Compare local agent/KB files against Git repo |
| 3 | **Learnings Captured** | Identify and write critical learnings to CLAUDE.md |
| 4 | **Feedback Logged** | Record issues, bugs, or suggestions about Claude's performance |
| 5 | **Docs Updated** | Ensure documentation reflects changes made |
| 6 | **Git Sync** | Commit, push, and contribute back changes |
| 7 | **Memory Updated** | Update MEMORY.md with session-spanning insights |

---

## Step 1: Verify Changes Are Saved

**Identify what was modified this session:**

1. Review the conversation to identify files that were edited/created
2. For each file, verify it exists and contains the expected changes

**Verification approach:**
```
For each modified file:
1. Read the file (or relevant section)
2. Confirm the changes are present
3. If using git, optionally check `git status` to see uncommitted changes
```

**Report format:**
```
## 1. Changes Saved

| File | Status |
|------|--------|
| `/path/to/file.md` | Verified |
| `/path/to/other.md` | Verified |

Uncommitted changes: [list if any, or "None - working directory clean"]
```

**If a change appears missing:**
- Alert the user immediately
- Offer to re-apply the change

---

## Step 2: File Sync (Local vs Git)

**Purpose:** Ensure local agent and KB files match what's in the Git repo.

**Check process:**

1. Count local files:
   - Core agents: Count `.md` files in `~/.claude/agents/` (excluding archive/ and `*-context.md` files) that do NOT have `status: experimental` in frontmatter
   - Experimental agents: Count `.md` files in `~/.claude/agents/` (excluding archive/ and `*-context.md` files) that HAVE `status: experimental` in frontmatter
   - Context files: Count `*-context.md` files in `~/.claude/agents/`
   - KBs: Count `.md` files in `~/.claude/knowledge-bases/`

2. Check if the ai-product repo exists locally:
   ```bash
   ls ~/Documents/code/ai-product/shared-team/product-management/product-council/agents/ 2>/dev/null
   ```

3. If repo exists, compare:
   - Count agents in repo: `ls ~/Documents/code/ai-product/shared-team/product-management/product-council/agents/*.md | wc -l`
   - Count KBs in repo: `ls ~/Documents/code/ai-product/shared-team/product-management/product-council/knowledge-bases/*.md | wc -l`
   - Diff local vs repo to detect modifications:
     ```bash
     diff ~/.claude/agents/ ~/Documents/code/ai-product/shared-team/product-management/product-council/agents/ --brief 2>/dev/null
     diff ~/.claude/knowledge-bases/ ~/Documents/code/ai-product/shared-team/product-management/product-council/knowledge-bases/ --brief 2>/dev/null
     ```

4. If repo does NOT exist: report "ai-product repo not found locally. Run `/update-skills` to clone and sync."

**Report format:**
```
## 2. File Sync

| Item | Local | Git Repo | Status |
|------|-------|----------|--------|
| Core Agents | 19 | 19 | In sync |
| Experimental Agents | 3 | — | Local only |
| Context Files | 2 | — | Local only |
| KBs | 8 | 8 | In sync |

[Or if discrepancy found:]
| Core Agents | 20 | 19 | Local has extra: new-agent.md |

**Note:** Experimental agents and their context files are local-only unless contributed back via Step 6b.
```

**If local files were modified this session:**
Flag them for the contribute-back flow in Step 6.

---

## Step 3: Capture Learnings

**Purpose:** Mistakes, misunderstandings, and discoveries should be captured so future sessions benefit.

### 3a: Determine Target Location

Identify WHERE learnings should be written by reviewing which artifact(s) were worked on most.

**Scoping rules:**
- Write to the most specific (leaf-level) `{artifact}/CLAUDE.md` relevant to the artifact worked on
- NEVER write to root CLAUDE.md — it's for navigation only
- If the artifact is unclear or work spans multiple areas, ASK the user

### 3b: Bloat Prevention Check

If the target CLAUDE.md exists:
1. Read the file and count existing learning items
2. If more than 15 items exist, warn the user and ask how to proceed (add anyway, clean up first, or skip)

### 3c: Session Analysis

Review the conversation history for:
- **Mistakes made** — wrong assumptions, incorrect code, failed approaches
- **Misunderstandings** — incorrect mental models, misread documentation
- **Unexpected behaviors** — surprises in how code/tools/systems worked
- **Repeated corrections** — things that had to be fixed multiple times
- **Council system gaps** — patterns this session surfaced that should be fed back into agent instructions, KBs, or frameworks. If found, note them for the contribute-back flow in Step 6.

### 3d: Apply 3-Question Criticality Test

Each potential learning must pass ALL THREE questions:

| Question | Pass If... | Eliminate If... |
|----------|------------|-----------------|
| Would this apply to future sessions? | Learning is repeatable | One-off issue |
| Is this something Claude wouldn't already know? | Repo/team-specific or counter-intuitive | General programming knowledge |
| Would forgetting this cause significant problems? | High stakes — bugs, wasted time | Low stakes, easily rediscovered |

Eliminate any learning that fails even ONE question.

### 3e: Generalizability Filter

Eliminate learnings that are too specific:
- Only applies to one file/feature
- References specific variable names or line numbers
- Would not help on a different but similar task
- Tied to temporary state (current sprint, specific ticket)

Heuristic: "Would I tell every new engineer working in this codebase about this?"

### 3f: Present & Confirm

Present filtered learnings to the user for approval. **Mandatory — never write without explicit confirmation.**

**Format each learning as:**
```
- [Context trigger]: [What to do/remember]
```

**Examples:**
- "When using Buildkite MCP: Always check pipeline status before assuming build completion"
- "For Python tests in this repo: Use `pytest -k` for targeted runs instead of full suite"

Ask the user: Add all, select individually, or skip?

### 3g: Write to CLAUDE.md

Only after explicit user approval:

```markdown
<!-- Added: YYYY-MM-DD -->
- [Learning 1]
- [Learning 2]
```

Confirm to user what was added and where.

**Report format:**
```
## 3. Learnings

**Identified:** [N] potential learnings
**After filtering:** [M] critical learnings

Proposed additions to `{path}/CLAUDE.md`:
- [Learning 1]
- [Learning 2]

[Ask user to approve/modify/skip]
```

**Quick mode:** If session was straightforward, report "No critical learnings identified."

---

## Step 4: Log Feedback

**Purpose:** Track issues, bugs, or suggestions about Claude's performance for improvement.

**What to capture:**
- **Bugs:** Claude made an error that should be reported
- **Friction:** Something was harder than it should be
- **Feature requests:** "Claude should be able to..."
- **Praise:** Something worked particularly well (worth noting for patterns)

**Process:**
1. Ask the user if they have any feedback from this session
2. If yes, categorize it:

| Category | Where to Log | Action |
|----------|--------------|--------|
| Bug/Issue | GitHub issue or internal tracker | Create ticket |
| Skill improvement | Skill's own TODO or improvement section | Note in file |
| Claude Code feedback | https://github.com/anthropics/claude-code/issues | Link user |
| General suggestion | MEMORY.md or session notes | Capture locally |

**Report format:**
```
## 4. Feedback

Any feedback from this session?
- [ ] Bug or issue to report
- [ ] Friction or UX suggestion
- [ ] Feature request
- [ ] Something worked well (capture pattern)
- [ ] No feedback

[If feedback exists, help user log it appropriately]
```

---

## Step 5: Update Documentation

**Purpose:** If the session changed how something works, documentation should reflect that.

**What to check:**
- Did we change a skill? → Update the skill's description or examples
- Did we change a workflow? → Update relevant docs
- Did we create something new? → Does it need a README or doc?
- Did we discover something undocumented? → Add documentation

**Process:**
1. List artifacts created or modified this session
2. For each, ask: "Does documentation need to be created or updated?"
3. Flag any gaps

**Report format:**
```
## 5. Documentation

| Artifact | Doc Status |
|----------|------------|
| `council/SKILL.md` | Self-documenting |
| `session-close/SKILL.md` | Created with docs |
| New workflow discovered | Needs documentation |

**Action needed:** [list any doc tasks]
```

**Common doc locations:**
- Skill behavior → SKILL.md itself
- Workflow/process → relevant CLAUDE.md or README
- Architecture decision → ADR if significant
- User-facing → Flag for README update or PR

---

## Step 6: Git Sync

**Purpose:** Ensure changes made this session are committed and pushed to the appropriate Git repos. Also detect local council changes that should be contributed back.

### 6a: Commit and Push Session Changes

**Process:**

1. Identify repos with uncommitted changes by checking working directories touched this session
2. Run `git status` in each repo
3. If changes exist:
   - Show the user what would be committed (file list + brief diff summary)
   - Ask: Commit and push? (Yes / Skip)
   - If yes: stage relevant files, commit with a descriptive message, push to current branch
4. If no changes: report "No uncommitted changes"

**Rules:**
- Never force push
- Never commit secrets or `.env` files
- Ask before pushing to main/master
- Use descriptive commit messages summarizing session changes
- If changes span multiple repos, handle each independently

### 6b: Contribute Back Council Changes

**Purpose:** If the user modified agents, KBs, or skills locally, offer to contribute those changes back to the ai-product repo via PR.

**Check process:**

1. Verify the ai-product repo exists:
   ```bash
   ls ~/Documents/code/ai-product/.git 2>/dev/null
   ```
   If not found: skip ("ai-product repo not found locally — run `/update-skills` to set up")

2. Pull latest main:
   ```bash
   cd ~/Documents/code/ai-product && git fetch origin main
   ```

3. Diff local installed files against repo:
   ```bash
   # Check core agents
   diff ~/.claude/agents/ ~/Documents/code/ai-product/shared-team/product-management/product-council/agents/ --brief 2>/dev/null

   # Check knowledge bases
   diff ~/.claude/knowledge-bases/ ~/Documents/code/ai-product/shared-team/product-management/product-council/knowledge-bases/ --brief 2>/dev/null

   # Check skills
   diff ~/.claude/skills/council/SKILL.md ~/Documents/code/ai-product/shared-global/starter-kit/skills/council/SKILL.md 2>/dev/null
   diff ~/.claude/skills/session-close/SKILL.md ~/Documents/code/ai-product/shared-global/starter-kit/skills/session-close/SKILL.md 2>/dev/null
   ```

4. Check for new/changed experimental agents:
   ```bash
   # Find experimental agents (have status: experimental in frontmatter)
   # Compare against repo's agents directory — any experimental agents not in the repo are new
   # Also check for companion context files (*-context.md)
   ```

   Categorize experimental agent changes:
   - **New** (local only, not in repo): candidate for contribute-back
   - **Modified** (exists in both, local differs): candidate for contribute-back
   - **Unchanged** (matches repo): skip

5. If no diffs: report "Local files match repo — no contributions needed"

6. If diffs found:
   - Show the user a summary of what changed, separating core and experimental:
     ```
     Core agent changes: [list or "none"]
     Experimental agent changes:
       - NEW: canada-market.md + canada-market-context.md
       - MODIFIED: risk-scoring.md
     KB changes: [list or "none"]
     ```
   - Ask: "Create a PR to contribute these changes back?" (Yes / Skip)

7. If user confirms:
   ```bash
   cd ~/Documents/code/ai-product
   git checkout -b council/contribute-$(date +%Y%m%d-%H%M%S)

   # Copy changed agents (core + experimental)
   cp ~/.claude/agents/*.md shared-team/product-management/product-council/agents/

   # Copy companion context files
   cp ~/.claude/agents/*-context.md shared-team/product-management/product-council/agents/ 2>/dev/null

   # Copy changed KBs
   cp ~/.claude/knowledge-bases/*.md shared-team/product-management/product-council/knowledge-bases/

   # Copy changed skills (if applicable)
   cp ~/.claude/skills/council/SKILL.md shared-global/starter-kit/skills/council/SKILL.md
   cp ~/.claude/skills/session-close/SKILL.md shared-global/starter-kit/skills/session-close/SKILL.md

   git add -A
   git commit -m "council: contribute local agent/KB/skill changes"
   git push -u origin HEAD
   gh pr create --title "Council: contribute local changes" --body "Auto-generated PR from session-close contribute-back flow."
   ```

7. Report the PR URL

**Note:** To contribute exemplars to the library, add files to `product-council/library/exemplars/` and submit a PR manually.

**Report format:**
```
## 6. Git Sync

### Session Changes
| Repo | Branch | Status |
|------|--------|--------|
| `Affirm/ai-product` | main | Committed and pushed |
| `/path/to/other` | feature-x | No changes |

### Council Contributions
| Type | Changed Files | Status |
|------|--------------|--------|
| Core Agents | 1 modified | PR created: #XX |
| Experimental Agents | 2 new | PR created: #XX |
| Context Files | 1 new | PR created: #XX |
| KBs | 0 | In sync |
| Skills | 1 modified | Included in PR |

[Or: "No local council changes to contribute"]
```

---

## Step 7: Update Memory

**Purpose:** MEMORY.md captures session-spanning insights that should persist.

**Location:** `~/.claude/projects/{project}/memory/MEMORY.md`

**What belongs in MEMORY.md:**
- Cross-session context (e.g., "User prefers X approach")
- Project-level patterns discovered
- Key decisions made that affect future work
- Links to important artifacts created

**What does NOT belong:**
- Task-specific details (use CLAUDE.md in artifact directory)
- Temporary state
- Anything already in a skill or KB

**Process:**
1. Review if any session insights are broadly applicable
2. If yes, propose additions to MEMORY.md
3. Keep MEMORY.md concise (<200 lines, as noted in system prompt)

**Report format:**
```
## 7. Memory

**Session insights for MEMORY.md:**
- [Insight 1 - if any]

[Or: "No memory updates needed"]
```

---

## Output Format

Present the full checklist as a consolidated report:

```
# Session Close Checklist

## 1. Changes Saved
[Table of verified files]

## 2. File Sync
[Local vs Git repo comparison]

## 3. Learnings
[Learnings identified or "None"]

## 4. Feedback
[Any feedback to log?]

## 5. Documentation
[Doc status for artifacts]

## 6. Git Sync
[Commit/push status + council contributions]

## 7. Memory
[Memory updates or "None needed"]

---
**Ready to close?** [Yes/No based on outstanding items]
```

---

## Quick Mode

If the user wants a fast check:

```
Quick session close:
- [N] files modified and saved
- Agent Council: 19 core + [N] experimental agents, 8 KBs [in sync / diffs found]
- No critical learnings
- Any feedback? [Yes/No]
- Docs current
- Git: [committed/no changes]
- Council contributions: [none / PR created]
- No memory updates

Ready to close.
```

---

## Reference

| Item | Location |
|------|----------|
| Knowledge bases | `~/.claude/knowledge-bases/` |
| Agents | `~/.claude/agents/` |
| Skills | `~/.claude/skills/` |
| ai-product repo | `~/Documents/code/ai-product` |
| Learnings | `{artifact}/CLAUDE.md` |
| Memory | `~/.claude/projects/{project}/memory/MEMORY.md` |
| Claude Code issues | https://github.com/anthropics/claude-code/issues |
