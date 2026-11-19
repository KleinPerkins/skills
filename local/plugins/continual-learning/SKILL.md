---
name: continual-learning
description: Govern Cursor’s local marketplace continual-learning plugin. Use to check or repair installation, activity, cadence, or tracked-memory safety. Retargets writes to git-ignored agent-learnings.md, protects tracked AGENTS.md, projects 50/1440 cadence, and handles compatibility and stop-hook containment.
---

# continual-learning

This is a local governor for Cursor's marketplace `continual-learning` plugin. It does not vendor the
plugin payload; it governs the machine-local cache projection: it **retargets** the plugin's write
target from the tracked `AGENTS.md` to the machine-local, git-ignored `agent-learnings.md`, projects
the 50-turn / 24-hour cadence, owns the global git excludes, and health-checks the result.

## Verbs

```bash
bash install.sh --doctor               # read-only health check
bash install.sh --repair               # bounded reapply of retarget + cadence + excludes
bash install.sh --apply                # install/reconcile behavior
bash install.sh --repair --cache-only  # reapply only the cache projection + global excludes
```

## What It Guarantees

- The live marketplace cache is discovered from `.cursor-plugin/plugin.json`, not from cache sentinels,
  so a freshly installed cache revision is found and re-classified on the very next run.
- The plugin's three writer files (`agents/agents-memory-updater.md` ×7,
  `skills/continual-learning/SKILL.md` ×3, `hooks/continual-learning-stop.ts` ×1) are retargeted from
  `AGENTS.md` to `agent-learnings.md` under an exact-count guard, with validate-all-before-write,
  content-addressed backups, atomic writes, post-write verify, and restore-on-fail.
- The stop-hook command is projected to `50` turns and `24` hours by a typed env-prefix patch.
- The global git excludes (`agent-learnings.md`, `.cursor/hooks/state/`) are ensured under
  `core.excludesFile`, so the retargeted learnings file is git-ignored everywhere.
- A Cursor `sessionStart` hook re-applies the projection without stealing focus.

## Compatibility State Machine (fail-closed)

The behavior fingerprint (`meta.provenance_ref`) is the safety-bearing signal; plugin version and
cache revision are advisory provenance.

- **BLESSED** — retarget targets carry the exact 7/3/1 counts, cadence is locatable, and the
  projection-invariant fingerprint matches `meta.provenance_ref`. The governor retargets + projects.
- **CONTAINABLE** — targets/counts still identifiable but the fingerprint drifted. The governor still
  retargets + projects (so the plugin cannot write a tracked `AGENTS.md`) and demands a re-bless:
  run `behavior-hash` and pin `meta.provenance_ref` in a `KleinPerkins/skills` PR.
- **INCOMPATIBLE** — the writer targets/counts or the cadence entry are no longer identifiable. The
  governor cannot trust the retarget, so it **neutralizes** the stop hook (contained no-op, else empty
  `stop[]`) to fail closed — mining pauses and no `AGENTS.md` is written — and demands a descriptor
  update or disabling the plugin in Cursor.

## Residual Runtime Limit

Closure now comes from retargeting the plugin's own writers plus fail-closed neutralization on any
unrecognized cache, rather than from a publish allowlist. If a future cache revision changes the
writer files or counts, the governor fails closed (INCOMPATIBLE → neutralized) until the descriptor
and `meta.provenance_ref` are updated in a `KleinPerkins/skills` PR, or the plugin is disabled in the
affected workspace.

Upstream retirement path: https://github.com/cursor/plugins/issues/141 asks the marketplace plugin to
honor user-owned cadence config and a repo denylist so cache projection can be removed.
