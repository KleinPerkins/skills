---
name: continual-learning-consolidate
description: Build the machine-local global learning projection in ~/AGENTS.md from ignored agent-learnings.md files. Use when the operator asks to consolidate continual learning, refresh global agent memory, verify that work-only memory stays local, or repair the daily consolidation job.
---

# continual-learning-consolidate

`~/AGENTS.md` is generated output, never a learning source. The explicit home
seed is `~/agent-learnings.md`. Do not hand-edit or retrospectively clean memory
as part of runtime repair.

## Run

```bash
continual-learning-consolidate
continual-learning-consolidate --dry-run
continual-learning-consolidate --json
```

Candidate roots come only from `agent-route map --json`; no Git or network call
is made by the consolidator. A private `memory-source-classification/v1` policy
at `~/.local/share/continual-learning-consolidate/classifications.json` binds
accepted personal/work/unknown logical IDs to paired active primary/common-Git
aliases. See [README.md](README.md) for the closed schema and installation guards.
Never publish the host policy, private assignments or continuity evidence.

## Admission and safety

- The explicit home seed remains eligible.
- Workspace recurrence requires two distinct accepted logical repository IDs,
  including at least one personal source. Paths and remote ownership do not
  decide classification; equivalent worktrees/clones share one ID.
- Unknown, stale and excluded recovery/archive/retired roots are skipped before
  memory access. Identity continuity never grants active-memory admission.
- Missing/invalid/conflicting policy, discovery/parse failure, scanner failure
  or blocked findings leave the output unchanged.
- Deduplication remains conservative; successful writes are atomic/deterministic.

Install or update using `install.sh --no-schedule`, supplying an explicitly
validated private policy and exact preimage hash when replacing it. This form
preserves scheduler state and capture. Qualify with a synthetic child-only
`--home` and fake `--agent-route`; real-home dry runs still read memory.
Resume only the intended job through its owner tooling after qualification.
The installer's scheduling form retains existing jobs or creates a missing
09:00 command job. Keep a failed repair paused and preserve rollback evidence.
