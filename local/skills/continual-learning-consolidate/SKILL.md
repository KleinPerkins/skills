---
name: continual-learning-consolidate
description: Build the machine-local global learning projection in ~/AGENTS.md from ignored agent-learnings.md files. Use when the operator asks to consolidate continual learning, refresh global agent memory, verify that work-only memory stays local, or repair the daily consolidation job.
---

# continual-learning-consolidate

`~/AGENTS.md` is generated output. Never hand-edit it and never treat it as a
learning source. The durable machine-local home seed is
`~/agent-learnings.md`.

## Run

```bash
continual-learning-consolidate
continual-learning-consolidate --dry-run
continual-learning-consolidate --json
```

The consolidator reads candidate roots only from `agent-route map --json`, then
looks for `agent-learnings.md` at those exact roots. It never scans the home
directory and makes no git or GitHub calls.

## Admission and safety

- Home-seed bullets are always eligible.
- A workspace bullet is promoted only when it exactly matches the home seed, or
  recurs across at least two independent roots with at least one root outside
  `~/dev/affirm`.
- Multiple worktrees/clones of the same origin count as one independent source.
- Near-duplicate uncertainty keeps both bullets.
- The final projection is scanner-gated. Missing sources, malformed input,
  discovery failure, scanner failure, or a blocked finding leaves
  `~/AGENTS.md` unchanged.
- Successful writes are atomic and deterministic.

Install or repair the durable runtime with:

```bash
bash ~/.cursor/skills/continual-learning-consolidate/install.sh
```

The installer uses supported `local-jobs` verbs to ensure the daily 09:00
`continual-learning-consolidate` job.
