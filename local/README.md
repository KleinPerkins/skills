# `local/` — local-scope capability subtree (reorg-v2 directory paradigm)

Artifacts created **here** are **local** scope (per `meta.yml scope: local`): installed locally but
**NOT** vendored downstream by the orchestrator. This is the sibling of `global/` — the operator chooses
scope by **which directory they work in** (D-2/D-3). The agent then infers + performs the correct local
+ remote plumbing via `_ops/eco/manifest.sh plan <dir>` (see `~/dev/_ops/eco/MANIFEST-CONTRACT.md`).

Contrast: `global/<id>/` artifacts are shared to the downstream consumer workspace (ld-agnostic
vendored copy) via the orchestrator — the only place that cross-workspace relationship is defined.

`local/plugins/` is the shelf for local IDE or marketplace plugin governors. These are first-class
capabilities with `kind: plugin`, `flavor: 2`, `scope: local`, a descriptor, and an installer with
`--apply`, `--doctor`, and `--repair`. They can activate bounded machine-local behavior, but they do
not get registry enrollment or downstream vendoring.
