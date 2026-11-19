---
name: save-game
description: "Save or resume durable agent state across compaction, chats, or handoffs. ‘Save this,’ ‘save our progress,’ or ‘checkpoint’ persists; ‘resume,’ ‘where are we,’ or ‘check status’ is read-only. Never stores transcripts, source, secrets, or customer data, performs Git delivery, or closes worktrees."
---

# /save-game

Cross-client capability that preserves the smallest durable execution state for a task —
privately, outside the chat transcript — and rebuilds confidence from live canonical sources
before work continues. It is not a Git-delivery mechanism, a transcript backup, and not a
worktree/session-close tool; those remain separate, operator-authorized workflows.

## Build status

**Complete (Phases 1-4, all four merged onto `feat/save-game`).** This capability shipped in
phases on one shared branch, then a final integration pass wired every phase's module together
into one coherent CLI and proved the whole thing works end-to-end:

- **Phase 1** — skeleton, closed schemas/fixtures, evidence ledger.
- **Phase 2** — the engine core: private storage (XDG paths, identity/key hashing, canonical
  serialization + digest, Darwin durability, per-workstream locking, the privacy gate,
  content-addressed snapshots), the append-only recovery transaction (prepared / aborted /
  finalized, in-lock CAS, deterministic crash recovery including `RECOVERY_BLOCKED`), and the
  four contracts (Flush, Index, Compact Decision, Reconcile).
- **Phase 3** — client registry + engine doctor (`engine/adapters.py`, `engine/doctor.py`), the
  cross-client invocation canary docs (`references/clients.md`), agent-behavior rules (scope,
  marginal-scope budget, decision reversal, blockers, hygiene, next-action, natural stopping —
  `engine/behavior.py`), lifecycle/curation (adoption, retention, GC, archive, preview-bound
  remove, uninstall, promotion candidates — `engine/lifecycle.py` / `engine/curation.py`).
- **Phase 4 (verify & ship)** — integrated everything above, which was deliberately built in
  isolation across the prior phases, into one coherent surface and proved it end-to-end:
  - `engine/cli.py` now exposes the full capability: the four core contracts
    (`flush|index|compact-check|reconcile`), every lifecycle/curation verb
    (`adopt|retention-status|gc|archive|remove|uninstall|promotion-candidates`, with
    `remove`/`uninstall` requiring `--preview` first and an exact `--confirm-digest` to
    `--execute`), and a `status`/`doctor` path that surfaces Phase 3's behavior outputs
    (hygiene, blockers, next-actions, natural-stopping) against already-persisted state.
  - `compact-check` (and `flush --client-id`) now actually consult `engine/adapters.py`'s
    per-client capability facts — a Compact Decision result carries the resolved client's exact
    manual compaction command and pre-compaction hook-capability class
    (`observational_only`/`can_block`/`halt_only_no_block`) when a known `--client-id` is given;
    an absent or unrecognized client degrades to unresolved fields rather than raising, and
    capability enrichment never changes the decision's status outcome or leaks into the
    persisted checkpoint (`checkpoint.compaction` stays exactly the closed v1 schema shape).
  - `tests/test_full_lifecycle_end_to_end.py` drives the entire capability through the CLI in
    one flow — adopt → flush → index → compact-check (client-capability-aware) → flush (a real
    pressure-triggered compaction embedded in a checkpoint) → reconcile → retention-status →
    promotion-candidates → status (active, then terminal) → archive → remove — plus a second
    flow proving `uninstall`'s full-retirement path distinctly from `remove`'s workstream-only
    scope. This is what actually proves every module built in isolation works as one system.
  - A gate-by-gate re-read of the plan's verification-strategy section closed two real, findable
    coverage gaps (Git mid-operation markers; linked-worktree identity) with new tests against
    already-correct engine behavior — no engine changes needed for those two.
  - **Known deferred gap, found during this pass:** the plan's Lifecycle verification gate
    names "forward rollback" and "schema-version rollback" as required. Neither exists as a
    callable operation anywhere in `engine/lifecycle.py` or `install.sh` today — only a code
    comment justifying why finalized snapshots are retained for a rollback that could use them
    later. Building actual rollback (restore active/checkpoint state to a prior generation; a
    schema-downgrade install path) is new engine logic, not wiring, and out of proportion for
    this verify-and-ship pass. It is intentionally NOT implemented; do not claim it works.

### Post-ship live-discovery canary (2026-08-02)

- **Cursor: PASSED.** Operator screenshot confirms `save-game` is listed and matched in Cursor's
  own slash-command autocomplete for `/save`. Separately, a live Cursor agent ran a real
  `flush → index → status` round trip through the installed skill, producing a schema-valid,
  durability-certified receipt and checkpoint with correct `0700`/`0600` on-disk permissions.
  Full evidence: `EVIDENCE.md`.
- **Claude Code: discovery PASSED**; invocation was not separately re-tested (the engine is
  client-agnostic and already proven correct via the Cursor round trip above). A first discovery
  probe method produced a false negative — see `EVIDENCE.md` for the pitfall and the corrected
  method that passed.
- **Codex: still unverified.** No `codex` CLI existed on the machine used for this canary, so
  discovery/invocation could not be probed at all. D1 stays frozen-deferred; continue to report
  Codex acceptance as pending, never asserted.

`save-game adopt` remains required before a Flush reports plain `SAVED` rather than
`SAVED_PRIVATE_UNADOPTED` — this is by design (plan: "Adoption"), not a gap.

## Triggers

- Explicit: `/save-game` in Cursor or Claude; `$save-game` in Codex via the current legacy
  `~/.codex/skills` discovery path (D1 froze the canonical-path migration as deferred — see
  `EVIDENCE.md`). Codex acceptance is a pending live-discovery canary, never asserted.
- Implicit save intent ("save this", "save our progress", "checkpoint this"): runs Flush then
  Index — persists a new immutable checkpoint.
- Implicit resume/status intent ("resume", "where are we", "check where we are"): read-only
  refresh only — may update the private cache but never creates a checkpoint or changes an
  operator-owned durable field.
- Ambiguous phrasing must never silently persist a checkpoint; when save-vs-resume intent is
  unclear, ask rather than assume save intent.

Exact per-client discovery paths, install/version detail, and the capability registry live in
`references/clients.md`.

## Authority boundaries (non-negotiable)

- Live canonical sources (repository policy, accepted plans, Git, CI, issue/PR systems) always
  outrank checkpoints and cached active state — a checkpoint is an index, never authority.
- Only sanitized, schema-valid execution facts and pointers to external authorities are ever
  persisted — never raw transcripts, prompts, source, diffs, logs, command output, secrets, or
  customer data.
- Every environment (standard repo, linked worktree, detached HEAD, bare repo, vendor/read-only
  root, governed repo, non-Git root) is private-only in MVP: state lives under XDG state/config,
  never tracked in the repository.
- Never commits, pushes, opens or merges a PR, or closes/removes a worktree.
- Never types or simulates a native compaction command on the operator's behalf, and never claims
  compaction occurred without client evidence.

## Four-phase routing

1. **Flush** — inspects live state, classifies each candidate fact as durable/ephemeral/derivable,
   applies scope and marginal-scope rules, then durably persists only the current delta under one
   workstream lock.
2. **Index** — builds the immutable, size-capped checkpoint (at most 2 KiB and 200 words of human
   text) that resumes work without replaying history.
3. **Compact Decision** — evaluates hard gates plus observable pressure/continuation signals,
   classifies the outcome (e.g. save-only, recommend, required, new-chat-recommended), and prints
   the active client's exact manual compaction command — it never types the command itself and
   never claims compaction ran without evidence.
4. **Reconcile** — after compaction, resume, or a root/branch/HEAD change, re-reads bounded live
   sources and classifies each claim (match/advanced/stale/conflict/unknown) before continuing.

## Progressive references

Detailed per-contract semantics, schemas, and exact client commands are kept out of this file so
they do not load into every session's startup context:

- `engine/schemas/` — closed JSON Schemas for every persisted record.
- `references/clients.md` — per-client discovery/invocation/manual-compaction detail, disk/engine
  doctor usage, and the manual live-discovery canary script for each client.
- Contract, behavior, and lifecycle/curation algorithms are documented in each engine module's own
  docstring (`engine/*.py`) rather than duplicated into a separate reference file.

## Related

- Source plan: `save-game-global-capability-v2` (this build's authority). Read the plan for any
  rule not summarized here rather than re-deriving behavior from memory.

## Client invocation

- Cursor: `/save-game`; manual compaction is `/summarize`.
- Claude Code: `/save-game`; manual compaction is `/compact`.
- Codex: `$save-game` through the current legacy exposure; manual compaction is `/compact`, and
  acceptance remains unverified pending a live discovery canary.
- Run `python3 -m engine.doctor` (disk/engine prerequisites) or `scripts/save-game.sh doctor`
  (the same checks through the installed CLI). Follow `references/clients.md` for exact paths,
  hook capability classes, and the manual live-client
  canary; neither doctor proves that a running client accepted the skill.
