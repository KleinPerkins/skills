# Agent route

Codex-only instructions for entering the correct project/workspace and reporting
the actual permission and writer state. An explicit known repository is verified
directly. Optional ecosystem search helps only when ownership is unknown.

The skill has no routing CLI, miner, scorer, cache, private registry, hook or job.
Native entry follows the current tool contract and the repository owner's rules.
Attachment establishes placement; it does not grant access or cleanup authority.

## Source-backed dependency

The optional index lives at `global/tools/ecosystem-index/ecosystem_index.py`
within the same `KleinPerkins/skills` source root as this skill. Resolve the
installed skill directory physically, verify its repository identity, and use
that exact source-relative tool path. Do not assume a primary checkout or PATH
command. A copied/relocated skill, missing tool, or mismatched source refuses the
optional search dependency; known-repository entry remains available.

```text
bash <physical-skill-directory>/install.sh --doctor
```

This command checks physical layout, the declared local Git remote and tracked
payloads. It reports `ready` with the verified tool path or `unavailable` (exit 3).
It does not execute the index or read a cache. It uses bounded local Git commands
for source identity; it is separate from the index's process-free query runtime.
Git identity is a source observation, not authentication or permission proof.

`install.sh` performs only this read-only source check (also when called without
arguments). The existing generic capability installer owns managed skill links.
There is no dependency installation, virtualenv, command link or new installer
channel. Native installation must use a durable merged source and its own gates.

## Compatibility and delivery

The previous CLI and three-client movement behavior are deliberately retired in
source. `meta.yml` now exposes this skill only to Codex; the separate
`ecosystem-search` skill is exposed to all three supported clients. Publishing
source does not remove existing client links, hooks, jobs or cached state.
Their exact ownership, preimages, shared-consumer disposition and rollback belong
to the later installation/retirement operation. Do not import old private state.

The source scenario matrix covers correct placement, wrong project, unsupported
transition, unknown/denied permission, stale/partial attachment, foreign writer
and unavailable index. Independent review evaluates the instructions against
those cases. Synthetic source/layout tests establish package behavior; they do
not establish that a native chat moved or that a permission was granted.

The approved architecture, specification and execution plan are linked from
`docs/plans/agent-route-client-parity-primary-routing-v2.md` in the source root.
Installation, native qualification and downstream delivery remain separate.
