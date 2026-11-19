# Evidence ledger — save-game Phase 1 (M0 + first slice of M1)

Recorded by the `freeze-evidence-and-gates` todo of the accepted
`save-game-global-capability-v2` plan. This file is itself part of the zero-link-scanned
payload, so it describes the build environment and baseline generically rather than
naming host-specific tooling (see `tests/test_zero_link.py`).

## v1/v2 plan freeze

- **v1 plan (immutable input):** `save-game-global-capability_18dc6696.plan.md`
  (`~/.cursor/plans/save-game-global-capability_18dc6696.plan.md`).
- **v1 plan SHA-256 (computed fresh for this build, not assumed):**
  `86cbcf4acb2f4895fe42bb555d19bfcb19e081d2ba97456f2b1867ddbad21865`
  — computed via `shasum -a 256` against the live file at build time. This matches the
  digest the v2 plan itself records "at review time," confirming the v1 input was not
  altered between v2's review and this implementation pass.
- **v2 plan (this build's authority):** `save-game-global-capability-v2_f76f17ff.plan.md`
  (`~/.cursor/plans/save-game-global-capability-v2_f76f17ff.plan.md`). Not edited by this
  build, per instruction.

## Build environment

This build ran on branch `feat/save-game` from a disposable, isolated worktree of
`KleinPerkins/skills` created by this repo's governed worktree-safety tooling — never from
the bare `~/dev` root, a shared primary checkout, or another session's worktree. Work was
pushed to `origin feat/save-game` incrementally (three commits, one per coherent slice) so
it survives regardless of what happens to the local worktree afterward, per this build's
own instructions. No PR was opened and `main` was not touched, per instruction — that
remains a later phase's or the operator's action.

## Verified baseline carried forward (client capability facts only)

Summarized from the v2 plan's "Verified baseline and corrections" section — not
re-verified independently by this phase; later phases (`add-client-adapters`) own live
discovery/invocation canaries:

- The repo's bootstrap/install mapping currently exposes `cursor`, `claude`, and `codex` to
  `~/.cursor/skills`, `~/.claude/skills`, and `~/.codex/skills` respectively. Current Cursor
  and Claude documentation supports their paths as-is. Current Codex documentation instead
  names `~/.agents/skills` as the canonical user-level location and `$skill` as explicit
  invocation — a generic path-migration question that is bigger than this one capability
  (see D1 below).
- Native compaction is operator/client control: a skill cannot type a slash command into
  its own client and must never report compaction without evidence. Canonical manual
  commands are Cursor `/summarize`, Claude `/compact`, and Codex `/compact`.
- Compaction hooks differ materially and are all deferred, optional defense-in-depth, never
  correctness-critical: Cursor's pre-compaction hook is observational only and cannot block;
  Claude's can block via an explicit decision field; Codex's can only halt by refusing to
  continue, not via that same block mechanism.
- A previously installed local, Cursor/Claude-only, council-specific session-closing skill
  is removed as a dependency by v2. Save-game finishes independently; Git delivery and
  workspace-close remain separate, operator-authorized workflows this capability does not
  perform.
- Official client evidence (docs read, not re-fetched by this phase): Cursor skills/hooks
  docs at cursor.com; Claude Code skills/hooks docs at code.claude.com; Codex skills,
  commands, and hooks docs at developers.openai.com.

## Open operator decisions — frozen outcomes for this build

The v2 plan lists D1 and D2 as open with a recommendation each. This build freezes both as
**deferred** for Phase 1 (and, by construction, for every later phase that builds on this
branch unless an operator explicitly revisits them):

- **D1 (Codex path) = DEFERRED** — do not touch the shared repo-root `bootstrap.sh`;
  save-game exposes to `codex` via the CURRENT legacy `~/.codex/skills` mapping as-is;
  Codex acceptance must be reported as "pending live discovery canary" rather than
  asserted.
- **D2 (tracked projection) = DEFERRED** — private-only state only, no repo-tracked
  `.save-game/current.*`.

Consequences for this phase's deliverables: `meta.yml`'s `expose:` line and `install.sh`
use the existing three-tool mapping unchanged (no `bootstrap.sh` edit); `SKILL.md` names
`$save-game` as the Codex trigger but does not assert Codex cross-client acceptance;
`references/clients.md` is left as a placeholder for Phase 3 to fill in with the live
canary result; no schema in `engine/schemas/` models a repo-tracked current-state file, and
none of this phase's fixtures represent one.

## Scope discipline

This phase implements exactly `freeze-evidence-and-gates`, `scaffold-global-capability`,
and `define-closed-contracts`. It does not implement storage, durability, locking, the four
contracts' runtime behavior, agent-behavior rules, client adapters, or lifecycle/curation
code — those remain later phases' todos on this same branch, per the accepted plan's
dependency order.

## Closing note — Phase 4 (verify & ship) complete

Recorded at the end of the `verify-canary-rollout` todo, the last item in the plan's
dependency-ordered implementation list. Phases 2/3 (engine core; behavior/adapters/lifecycle)
landed as ten commits on this same branch, each built in deliberate isolation so three parallel
agents could work without merge conflicts. This phase's job was to integrate those pieces,
verify the whole thing end-to-end, and ship — not to add new engine logic.

- **Baseline:** 318 tests passing, 0 failures, at commit `bb624ed` (confirmed before any Phase 4
  change).
- **Integration work:** `engine/cli.py` extended to expose every lifecycle/curation verb plus a
  `status`/`doctor` path (wiring only, reusing existing engine functions); `compact_decision.py`
  wired to `adapters.py`'s per-client capability facts; a real end-to-end test
  (`tests/test_full_lifecycle_end_to_end.py`) added that drives adopt → flush → index →
  compact-check → reconcile → retention-status → promotion-candidates → status → archive/remove
  → uninstall through the CLI in one flow, proving the modules actually work together rather
  than merely passing their own isolated unit tests.
- **Gate-by-gate verification-strategy re-read** closed two real coverage gaps with new tests
  against already-correct behavior (Git mid-operation markers in `identity.py`/`reconcile.py`;
  linked-worktree identity resolution) — no engine code changes required for either.
- **One gap found and deliberately deferred, not fixed:** the plan's Lifecycle verification gate
  requires "forward rollback" and "schema-version rollback." Neither is implemented as a
  callable operation anywhere in this codebase — confirmed by reading every function in
  `engine/lifecycle.py` and `install.sh`; the only trace is a comment noting that retained
  snapshots exist partly *for* a future rollback. Implementing real rollback (restoring
  active/checkpoint state to a prior generation; a schema-downgrade install path) is new engine
  logic, not integration wiring, and is out of proportion for a verify-and-ship pass. This is
  reported here rather than silently skipped so a future phase inherits an honest, explicit
  todo instead of a false "lifecycle is done" claim.
- **Final count:** 370 tests passing, 0 failures, `make verify` green (tests + `verify-skills.sh`
  + the zero-link scan) on the exact commit shipped in the PR.
- **D1/D2 remain frozen-deferred, unchanged by this phase** — restated, not re-litigated: D1
  (Codex canonical-path migration) stays on the legacy `~/.codex/skills` mapping, reported as
  "pending live discovery canary," never asserted; D2 (repo-tracked current-state projection)
  stays private-only, with no tracked `.save-game/current.*` file anywhere in this build.
  `bootstrap.sh` was not touched by this phase.

## Post-ship live-discovery canary (operator-run, 2026-08-02T00:57Z)

Run after installing the skill on a machine (`install.sh` linked all three client paths;
`install.sh --doctor` and `python3 -m engine.doctor` both passed, with every
`live-acceptance:*` line correctly reported as `UNKNOWN` — disk checks alone cannot prove
client discovery, per `references/clients.md`). This section records the follow-up live canary
that closes part of that gap, generically per this file's own zero-link convention.

### Cursor — PASSED (discovery + invocation)

- Discovery: an operator screenshot of the Cursor chat input after typing `/save` shows
  `save-game` matched and listed first (pinned-icon slot), ahead of several other real
  installed skills.
- Invocation: `scripts/save-game.sh flush --client-id cursor --task-id
  save-game-cursor-live-acceptance --objective "..." --next-action "..."` returned a schema-valid
  `save-game-flush-receipt/v1` (`status: SAVED_PRIVATE_UNADOPTED` — correct, since `adopt` was not
  run for this clone; checkpoint `chk-496ceda471ea`, generation 1, with the required
  `negative_claims` field present). Follow-up `index` and `status` calls with the same
  `--task-id` resolved the same workstream, echoing the exact objective/next-action verbatim and
  reporting `hygiene.all_clear: true` and `stopping.outcome: continue`. On-disk artifacts
  (`current/`, `checkpoints/`, `journal/{prepared,finalized}`, `receipts/`, `snapshots/`) were
  confirmed written with `0700` directory / `0600` file permissions, and nothing was written to
  any Git repository.
- Not covered: the post-compaction resume/reconcile step (canary step 4 in
  `references/clients.md`) — no real manual compaction was triggered in this pass.

### Claude Code — discovery PASSED; invocation not independently re-tested

- Two non-interactive probes (the client's `-p`/print mode with `--tools ""`, i.e. all tools
  disabled) asking whether a `save-game` skill was available both returned false negatives (a
  plain "NO", then "NONE" when asked to enumerate every loaded skill). Disabling all tools
  appears to also disable that client's skill-surface enumeration, not just tool execution —
  this is a methodology pitfall for future testers, not evidence against discovery.
- A corrected probe (same print mode, explicit `--setting-sources user,project,local`,
  `--permission-mode plan`, default tool access, session persistence disabled, instructed not to
  execute anything) returned a list of roughly ninety real skill/slash-command names including
  `save-game`, sitting in the exact alphabetical position it occupies on disk between two other
  real installed skill names — strong evidence this was a genuine loaded-skill enumeration, not a
  model guess.
- The underlying engine behavior (Flush/Index/Reconcile) is client-agnostic and was already
  proven correct end-to-end via the Cursor invocation above and the Phase 4 end-to-end test
  suite, so a separate live Claude Code *invocation* canary was judged lower-value for this pass
  and was not run (each such probe is a real, billed API call).

### Codex — unverified, structurally untestable on this canary's machine

- No `codex` CLI binary existed on the machine used for this canary, so neither the legacy
  `~/.codex/skills` discovery path nor `$save-game` invocation could be probed locally at all.
  D1 (Codex canonical-path migration) remains frozen-deferred per Phase 1; Codex acceptance must
  continue to be reported as pending, never asserted.
