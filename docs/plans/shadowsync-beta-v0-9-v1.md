# ShadowSync Beta v0.9 inspection corrective release execution plan

**Version:** v1
**Status:** ACCEPTED — 2026-10-06
**Date:** 2026-10-06
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Linked decision:** [ADR 0005 — Separate ShadowSync preview admission from mutation evidence and result ownership](../adr/0005-shadowsync-preview-admission-and-result-ownership.md)
**Inherited authority:** [ShadowSync Beta v0.8 corrective release plan](shadowsync-beta-v0-8-v1.md)
**Planning baseline:** clean linked worktree at exact `origin/main`
`3376dd35af3457ae97dd7d6ba6cab73cfbbb8201`
**Implementation branch:** `fix/shadowsync-beta-v0.9-build14`
**Release identity:** marketing version `0.9.0`, build `14`
**Stage:** Beta v0.9 bounded inspection corrective candidate; operator UAT remains open

> **Immutable authority:** the operator approved every requirement below before implementation.
> Preserve this accepted plan byte-identically. Record implementation and delivery receipts in the
> mutable runbook, commits, tests, PR, and release metadata. Automated success never closes UAT.

## 0. Goal and closed dependency order

Cut one bounded corrective beta that makes optional branch/worktree inspection responsive,
observable, and understandable at real repository scale. Preserve every cleanup/removal permission
gate, candidate identity proof, recovery requirement, mutation guard, saved selection, and accepted
selected-batch hierarchy.

```text
M0 freeze authority and release identity
  → M1 bound and accelerate read-only discovery
    → M2 retain single/all inspection progress
      → M3 apply coherent RLCC hierarchy and alignment
        → M4 close exact-head release verification
          → M5 open one ready PR and stop at controller merge
```

M1–M3 may share one branch but retain independently detecting tests. M5 cannot start until one
clean exact head has all required receipts.

## 1. Frozen scope, invariants, and non-goals

### 1.1 Requirements

- **SS-09-01 — Release authority.** Cut only `0.9.0 (14)` from the exact baseline and branch named
  above. Preserve ADR 0005 and accepted v0.6–v0.8 plan bytes; keep operator UAT open.
- **SS-09-02 — Bounded bulk local evidence.** Replace per-branch local Git subprocess fan-out with
  the smallest bounded bulk query or queries that prove the same branch identity, upstream, and
  relation facts. Any fact not proven in bulk remains unavailable; no gate weakens.
- **SS-09-03 — Dedicated read-only PR admission.** Admit at most four concurrent GitHub/PR lookup
  children for the current repository only. Repositories remain strictly sequential and
  top-to-bottom. Each child retains its 15-second bound. This dedicated adapter does not change
  global mutation, scheduler, or unrelated subprocess admission.
- **SS-09-04 — Adaptive bounded completion.** Derive an explicit repository/stage budget from
  admitted work with a documented hard ceiling. At deadline or cancellation, stop admission,
  cancel and drain owned read-only children, retain only fully proven evidence, and mark incomplete
  candidates unavailable/retain with neutral copy. Incomplete candidates never enter recommended
  bulk selection.
- **SS-09-05 — Bounded exact memoization and evidence.** In-session memoization is permitted only
  when keyed by exact repository/candidate identity and freshness evidence. Add aggregate,
  non-sensitive stage counts/durations, active/max child count, deadline/partial counts, and
  progress heartbeat without paths or branch names. No durable cache or append-only command event
  stream is introduced.
- **SS-09-06 — Retained inspection progress.** A single-repository inspection retains one progress
  bar with coalesced topology, worktree-evidence, branch-relation, PR-evidence, and candidate-
  assembly stages plus terminal Complete, Complete with issues, Cancelled, or Failed state.
  Inspect-all retains one overall bar and stable repository rows in displayed order; exactly one
  repository is active; completion/error rows remain through batch completion; cancellation marks
  untouched rows Not inspected.
- **SS-09-07 — Coherent RLCC hierarchy and alignment.** Make full-width containers explicit while
  headers, copy, actions, names, and inline text lead-align. Only compact status/count badges may
  trail. Replace whitespace indentation with 16–20-point constraints. Long identities use full
  available width, wrap to at most two lines, and move the status below on narrow layouts.
  Constrain optional-inspection panels and candidate lists to repository-card width.
- **SS-09-08 — Contained candidate subcards.** Present each branch/worktree candidate as a stable
  contained subsection with type/icon/name, provenance, actions or error, recommendation/rationale,
  relevant AWA/recovery/PR notes, and disclosed diagnostics. Preserve semantic colors, keyboard
  order, VoiceOver labels, stable selection identity, standard controls, muted cleanup treatment,
  and the accepted selected-batch hierarchy.
- **SS-09-09 — Governed verification and delivery.** Add focused v0.9 selectors and a self-cleaning
  verification wrapper; prove AWA-shaped and skills-shaped bounded fixtures, delayed/error/timeout
  adapters, concurrency and cancellation limits, fail-closed partial results, zero mutation,
  retained progress, deterministic instrumentation, native Aqua/Dark Aqua layout and accessibility,
  release/source identity, repository/doc/diff gates, and one normal ready PR. Controller
  automation alone reviews and merges; no candidate install.

### 1.2 Preserved invariants

- Inspection remains read-only and never authorizes mutation. Common-directory locks, exact
  Repair/removal sets, refs, hooks, identity, recovery, secrets, digests, preservation, postflight,
  and immediate pre-mutation checks remain authoritative.
- Candidate cleanup permission requires complete exact evidence. Deadline, cancellation, missing
  fields, PR failure, and ambiguous identity resolve to unavailable/retain.
- Repository ordering and execution remain one repository at a time. Only the dedicated read-only
  PR-evidence stage admits up to four children within that current repository.
- The immutable execution plan, append-only durable log, selected-batch worker count, operation
  cancellation, confirmations, report/history, and old-log compatibility do not change.
- Tests use isolated fixtures or owned temporary repositories. No live user repository operation
  may run and installed `0.8.0 (13)` plus preserved UAT evidence remain untouched.
- No feature-head install, direct/admin merge, agent-armed auto-merge, check bypass, workflow-policy
  change, paid runner, or mutation of unrelated branches/operator data is allowed.

### 1.3 Non-goals

- Cleanup/removal semantics, granular prune, detached-commit recovery, preservation-store changes,
  saved-selection changes, repository-wide GitHub batching, global concurrency changes, selected-
  batch redesign, or mutation scheduler changes.
- Durable inspection cache, unbounded process output, unbounded event/log growth, external
  telemetry, package dependency, permanent performance SLA, or live-repository benchmark.
- `NSOutlineView`, wholesale UI framework replacement, byte-for-byte imitation of operator low-fi,
  or unrelated RLCC/chooser/report cleanup.
- Declaring Fast-forward, Repair, pruning, inspection, or overall Beta UAT accepted.

## 2. Evidence and implementation seams

The installed v0.8 RLCC inspected `KleinPerkins/awa`, which has 21 total worktrees and 75 local
branches; after primary/default exclusions it displayed 20 worktrees and 74 branches. Read-only
profiling measured 4.506 seconds of worktree state, 230 serial Git children over 11.870 seconds, and
representative per-branch GitHub lookups averaging 625 milliseconds, projecting 46.3 seconds for
74 lookups and about 58 seconds overall against the fixed 20-second enrichment deadline. Five of
the 11 selected repositories exceed the practical current threshold: `skills` 84 branches/20
worktrees, `dev` 79/11, `awa` 75/21, `pr-automation-controller` 75/10, and
`ecosystem-orchestrator` 28/4.

The timeout is structural: `RepositoryInventoryDiscovery` creates one fixed whole-enrichment
deadline, performs local relation/ancestry/upstream probes serially per branch, then performs one
single-flight `gh pr list` per branch. UI work is detached from the main actor and is not the
dominant cost. The current optional-inspection call site does not surface detailed lifecycle
progress to the RLCC.

The layout defects are similarly bounded: root/full-card vertical stacks use width alignment while
summary controls rely on intrinsic alignment; cleanup boxes lack an explicit card-width contract;
branch/detail nesting uses width alignment plus literal string whitespace; and horizontal identity
rows do not define narrow-width compression/status reflow.

Implement through existing seams:

- `RepositoryInventoryDiscovery`, its branch-enrichment models, process runner, lifecycle observer,
  and deterministic adapters;
- `ReadOnlyGitHubCLIAdapter` through a new bounded inspection-only admission seam, leaving the
  existing global singleton behavior intact elsewhere;
- `AppDelegate` optional-inspection state and sequential batch orchestration;
- `RepositoryCardsWindowController` root/card/cleanup/candidate layout primitives and stable
  progress presentation;
- release identity, package metadata, README/install/source assertions, focused selectors, and
  verification wrapper.

The four-child inspection-only adapter is a bounded implementation policy within the already
authorized read-only preview boundary. It does not revise ADR 0005's preview-versus-mutation
authority or establish cross-product concurrency architecture, so no new ADR is required.

## 3. Milestones and acceptance rows

### M0 — Freeze authority

- Create the named branch only from clean exact baseline `3376dd35…`.
- Add this accepted plan and index row; update the mutable runbook with `SS-09-01–09`, evidence,
  open-UAT state, candidate identity, and preserved v0.8 installed/UAT evidence.
- Do not edit this plan after M0.

**M0-AT-01:** plan/index/runbook name the exact baseline, branch, identity, closed scope, preserved
safety boundaries, and open UAT; doc and diff checks pass.

### M1 — Bound and accelerate read-only discovery

- Use bounded bulk Git output to construct exact local branch identity/upstream/relation evidence.
- Admit at most four current-repository PR children through the dedicated read-only path; preserve
  per-query timeout, exact branch/OID keys, output bounds, and safe response parsing.
- Derive a deterministic adaptive PR-stage budget from admitted waves, with an absolute hard
  ceiling, and expose the derivation in source/tests rather than encoding an AWA latency SLA.
- On timeout/cancellation, drain children and attach complete evidence only to complete candidates.
- Add aggregate stage receipts without repository paths or candidate names.

**M1-AT-01:** deterministic 21-worktree/75-branch and 20-worktree/84-branch fixtures complete
without per-branch local Git fan-out; maximum PR child count is four; repository concurrency is one;
timeout/error/cancellation leave incomplete candidates unavailable and unselectable; no mutation
command is admitted.

### M2 — Retain inspection progress

- Define bounded stage/count/terminal snapshots rather than append-only per-command events.
- Wire snapshots to the main actor at stage boundaries or a bounded cadence.
- Keep one single-repository bar or one inspect-all bar plus stable ordered rows until terminal
  presentation; preserve successful prior rows after a later warning/failure.
- Cancellation stops future repository admission and marks untouched rows Not inspected.

**M2-AT-01:** deterministic clocks prove ordered/coalesced progress, retained terminal rows, exact
single-repository-at-a-time behavior, drained cancellation, bounded snapshot count/memory, and UI
heartbeat while delayed adapters run.

### M3 — Apply coherent RLCC hierarchy and alignment

- Introduce small layout primitives for explicit full-width containment, leading content, real
  insets, identity wrapping, and compact trailing badges.
- Organize each repository as identity/status, default/current checkout, repository actions,
  optional inspection, then contained candidate subcards.
- Organize each candidate as identity/type, provenance, actions/error, recommendation/rationale,
  notes, and disclosed diagnostics.
- Reuse the accepted muted panel and selected-batch visual language without copying its mutation
  semantics or changing selected-batch code.

**M3-AT-01:** Aqua and Dark Aqua native captures at minimum, standard, and wide sizes show explicit
leading alignment, card-width containment, readable 59+ character identities, status reflow,
semantic control colors, stable selection state, keyboard order, and accessible labels with no
clipping or ambiguous indentation.

### M4 — Close one exact release head

- Set all release/catalog/installer/README expectations consistently to `0.9.0 (14)`.
- Register `--beta-v09-focused-only` and `scripts/verify-beta-v0.9.sh`.
- Run focused, core/transaction, AppKit/native visual, performance/resource, installer/source,
  signed release-build, repository, doc-warden, frozen-authority, and diff gates.
- Inspect every generated visual against the three operator-supplied v0.8/low-fi references.
- Prove any broad baseline failure from an untouched exact-main source rather than hiding it or
  expanding scope.

**M4-AT-01:** one clean `TESTED_HEAD` passes the complete mapped matrix and attests production
identity `0.9.0 (14)`, bounded read-only child counts/output/events, deterministic partial-result
safety, responsive progress/layout, unchanged mutation semantics, and no owned process/temp residue.

### M5 — Governed ready PR

- Perform a subtractive whole-body review and remove speculative code.
- Commit meaningful complete work, push the exact tested head, and open one normal ready PR.
- Resolve only in-scope exact-head findings with minimal pushes and refreshed evidence.
- Never install, arm/alter auto-merge, merge, bypass checks, or change workflow policy.

**M5-AT-01:** one ready PR names the exact clean tested head; installed v0.8 and preserved UAT
evidence are unchanged; the linked worktree is clean; and all owned helpers and temporary roots are
removed.

## 4. Verification matrix

| Requirement | Detecting evidence |
|---|---|
| `SS-09-01` | plan/index/runbook diff; exact baseline/branch/identity/frozen-authority assertions |
| `SS-09-02` | bulk relation fixtures; missing-field refusal; bounded-output and zero-mutation checks |
| `SS-09-03` | deterministic delayed adapters; maximum active PR children four; repository concurrency one |
| `SS-09-04` | deadline/cancel/drain matrix; retained complete evidence; incomplete candidates unavailable and excluded from bulk select |
| `SS-09-05` | exact-key memoization fixtures; aggregate count/timing/heartbeat receipts without path/name leakage |
| `SS-09-06` | single/all ordered progress, retention, coalescing, cancellation, terminal-state, heartbeat, and bounded-memory checks |
| `SS-09-07` | minimum/standard/wide Aqua/Dark Aqua geometry, leading alignment, real insets, wrapping/reflow, accessibility and keyboard checks |
| `SS-09-08` | contained branch/worktree subcard hierarchy; provenance/action/recommendation/note/diagnostic fixtures; stable identity/selection |
| `SS-09-09` | focused/core/AppKit/native/performance/install/source/signature/repository/doc/diff gates and exact ready PR |

Every row is release-blocking. Evidence lives outside this immutable plan.

## 5. Stop and rollback conditions

- Stop before implementation if the branch does not start from the exact clean baseline.
- Stop and return to the operator if the correction requires changing cleanup permission/removal
  semantics, mutation concurrency, recovery requirements, saved selections, selected-batch
  architecture, a new durable cache, or ADR 0005.
- Any identity/ref/claim/AWA/upstream/PR/recovery/policy/hook/digest drift remains a safe refusal.
- Before merge, abandon or correct the PR normally and do not install. Installation is a separate
  exact-merged-main task.

## 6. Definition of done

The implementation task is complete only when `M0-AT-01` through `M5-AT-01` have objective receipts
at one exact clean head, native visuals were inspected in both appearances and all required window
widths, AWA-shaped and skills-shaped fixtures prove bounded resource behavior without a latency SLA,
the complete corrective body passed subtractive review, one ready PR is at the controller gate,
installed v0.8 and preserved UAT evidence remain untouched, and all owned temporary resources are
removed. Engineering completion does not accept or close operator UAT.
