# ShadowSync Beta v0.6 corrective release execution plan

**Version:** v1
**Status:** DRAFT — 2026-10-04
**Date:** 2026-10-04
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Execution shape:** agentic-execution
**Linked decisions:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md);
[ADR 0005 — Separate ShadowSync preview admission from mutation evidence and result ownership](../adr/0005-shadowsync-preview-admission-and-result-ownership.md)
**Inherited authority:** [ShadowSync exact Lucide draft-pull-request glyph plan v7](dev-main-sync-global-capability-v7.md)
**Planning baseline:** clean detached worktree at exact `origin/main`
`7b9780f12e5e16f8de71b4692177fe51b7ecaa06`
**Source plan:** `/Users/laurence.duggan/.cursor/plans/shadowsync-beta-v06_ef83de21.plan.md`,
SHA-256 `819b6750274acfc69c794e8a7c17e52bbc593f817a123322489ebfe200102aec`
**Release identity:** marketing version `0.6.0`, build `11`
**Stage:** Beta v0.6 corrective candidate; operator UAT remains open

> **For zero-context implementers:** execute M0 through M5 in order. Every milestone is
> release-blocking. Never edit an accepted copy of this plan to record progress; preserve receipts
> separately. A checked box or passing automated test is not operator UAT acceptance.

## 0. Goal, authority, and dependency order

Cut one narrow corrective release that restores safe Fast-forward/Repair execution, separates
new-run and historical-report ownership, reuses unchanged same-session evidence, and presents
stable repository-grouped results without weakening the inherited Git, lifecycle, installation, or
delivery boundaries.

Execution order is closed:

```text
M0 freeze release authority and branch
  → M1 repair operation admission and topology evidence
  → M2 reconcile session/history/cleanup state
  → M3 stabilize result presentation and compatibility
  → M4 close exact-head verification
  → M5 ready PR, controller merge, exact-main install, UAT handoff
```

Do not start a milestone until every exit row for its predecessor has objective evidence. M1–M3 may
be implemented in one branch, but their tests and receipts remain separately attributable. M5
cannot begin until M4 freezes one clean exact tested head.

## 1. Frozen scope, safety, and non-goals

### 1.1 In scope

- `Start New Run`, `Show Last Report`, selected-scope reconciliation, optional cleanup bulk
  selection, Fast-forward/Repair availability and execution, and batch/report presentation.
- Checked-out default-target preview admission when the cached relation is unavailable.
- Fresh default claimant and linked-worktree evidence scoped to the executing operation.
- Same-session retention of unchanged card and cleanup inspection evidence.
- Stable repository/action result rows, historical metadata, bounded diagnostics, and v2 log
  decoding.
- Focused regression entrypoint, exact release identity `0.6.0 (11)`, governed ready PR,
  controller-owned merge, exact-merged-main installation, and renewed operator UAT.

### 1.2 Safety constraints inherited unchanged

- Preview evidence never authorizes mutation.
- Equal is a verified no-op; only Behind may advance by the inherited exact-OID fast-forward path.
  Ahead, Diverged, unknown execution relation, duplicate default claims, identity drift, policy
  drift, changed repair set, unsafe hooks, or incomplete topology refuse without mutation.
- Unknown ref-only Fast-forward and incompletely proven Repair remain unavailable.
- Preserve the existing common-directory lock, exact ref/OID capture, no-replace-object mode,
  hook/config/identity/digest validation, immediate pre-mutation reinspection, poststate proof, and
  no real-repository mutation in tests.
- Session-local inspection evidence cannot cross process restart and cannot serve as mutation
  authority. Action checkmarks and confirmations reset on selection reconciliation.
- Technical detail is optional, bounded, redacted, and never replaces plain operator-facing result
  text.
- Existing v2 logs remain decodable; no destructive state migration is introduced.
- No feature-branch install, dirty-source install, direct merge, agent-armed auto-merge, bypassed
  check, paid/self-hosted GitHub runner, new package dependency, or mutation of `chaos-scheduler`.
- The reviewer/controller automation owns approval and merge. The implementation agent may mark the
  verified PR ready but must never call `gh pr merge --auto` or alter auto-merge.
- UAT remains open until the operator explicitly accepts or defers every remaining workflow.

### 1.3 Non-goals

- General Git repair, divergence reconciliation, lock deletion, object repair, auth repair, policy
  repair, hook bypass, remote branch deletion, or cleanup automation.
- Ref-only unknown-relation admission.
- Cross-session cache reuse, a new report schema family, replacement of the durable Live Log, or
  unbounded command/error disclosure.
- Broad AppKit redesign, accessibility expansion, performance SLA work, package/runtime dependency,
  Xcode project, updater, controller/VPS change, or work outside the named v0.6 files.
- Declaring Beta v0.6 released or UAT complete from branch, PR, automated-test, or install evidence.

## 2. Current diagnosis and implementation invariants

The failed v0.5 run made no mutation. `LocalClone.worktrees` retained linked-worktree evidence while
the later `sourceSnapshot.linkedWorktrees` was empty. Fast-forward treated unrelated stale
non-default registrations as target ambiguity, and Repair could not reopen a preserved linked
worktree. Separately, a remote commit absent from the local cache produced `.unavailable` preview
relation and hid Fast-forward even for a clean checked-out default target, although execution
already fetches the exact advertised OID before resolving Equal/Behind/Ahead/Diverged.

The UI also conflates terminal report ownership with active-run routing, discards the whole selected
session when one repository changes, enables cleanup bulk selection before useful inspection
evidence exists, and rebuilds result rows instead of retaining stable repository/action identity.

Implement these corrections through existing seams:

- `RepositoryInventoryDiscovery.card`, `makePlannedOperation`, and
  `RepositoryInventoryGitInspector.cachedExactRelation`;
- `LocalRepositoryInspection.inspectDefaultBranchTarget` and
  `DefaultBranchTargetInspection.requireMutableTarget`;
- `RepositoryHandle.open`, linked-worktree claim verification, and a new operation-scoped opener
  in `GitSafety.swift`;
- maintenance admission in `RepositoryMaintenance.swift` and preservation in
  `FastForwardTransactionV2.swift`;
- `AppDelegate.startNewRun`, `showLastReport`, selected inventory reconciliation, and
  `SelectedRepositoryHydrator.hydrateEvidence`/`hydrateOnce`;
- `RepositoryCardsWindowController.selectAllRecommendedRemoval`;
- `Body3RunWindowController.update`, `refreshRepositoryRows`, and `displayState`;
- `RunPresentation`, `Body3Batch`, `Body3Coordinator`, and `Body3RunLog`.

## 3. Closed SS-06 requirements

- **SS-06-01 — Release authority and provenance.** Record Beta v0.6 as a narrow corrective
  candidate with identity `0.6.0 (11)`, exact source revision, merged PR, installed provenance, and
  UAT-open status. Branch only from clean exact `origin/main`.
- **SS-06-02 — Checked-out unknown-relation admission.** A cached `.unavailable` relation may expose
  Fast-forward only when the exact default target is checked out and freshly verified clean.
  Execution must fetch and classify; unknown ref-only remains refused.
- **SS-06-03 — Exact default claimant.** Require one fresh default-branch claimant and physically
  revalidate that exact target. Unrelated stale non-default registrations are not a Fast-forward
  blocker; duplicate default claimants still refuse.
- **SS-06-04 — Operation-scoped linked-worktree evidence.** Repair, Fast-forward, and ref-only
  preservation open linked worktrees from fresh operation evidence and preserve all inherited
  lock/repair-set/ref/hook/identity/digest/pre-mutation gates.
- **SS-06-05 — New-run ownership.** `Start New Run` archives or dismisses terminal presentation and
  opens the chooser. Only active or unsettled work may block it.
- **SS-06-06 — Independent history.** `Show Last Report` opens a read-only historical viewer from
  the durable last-report snapshot; it neither owns nor changes active-run lifecycle state.
- **SS-06-07 — Same-session delta hydration.** Reconciling A,B → B,C retains B's unchanged inspected
  capability and cleanup evidence, hydrates only C, drops A, and resets action selections and
  confirmations. Mutation still validates fresh.
- **SS-06-08 — Cleanup bulk-selection gate.** `Select All Recommended Cleanup` remains disabled with
  explanatory copy until at least one repository cleanup inspection succeeds, then selects only
  recommendations from successfully inspected repositories.
- **SS-06-09 — Stable repository/action results.** Results are left-aligned repository groups with
  fixed action rows. One row keeps its identity while changing queued → running → terminal.
  Operator-facing result text is inline; command events update only the Live Log.
- **SS-06-10 — Historical metadata.** Derive start, end, duration, repositories, attempted actions,
  and outcome counts from durable run evidence for live completion and historical replay.
- **SS-06-11 — Bounded diagnostics and compatibility.** Carry optional redacted bounded technical
  detail through batch/coordinator/log/presentation without exposing raw commands, environment,
  credentials, or arbitrary paths; keep prior valid v2 logs decodable.
- **SS-06-12 — Verification, governed delivery, and UAT.** Add one focused v0.6 selector/script,
  prove the closed relation/topology/session/UI/compatibility matrix, open a ready PR, let controller
  automation merge the exact checked head, install only exact merged main, smoke `0.6.0 (11)`, and
  hand off renewed UAT without claiming acceptance.

## 4. Closed traceability matrix

| Requirement | Implementation task | Detecting tests | Acceptance rows | Required evidence |
|---|---|---|---|---|
| `SS-06-01` | `M0-T01`, `M4-T03`, `M5-T03` | release identity, source/installer checks | `M0-AT-01`, `M4-AT-03`, `M5-AT-03` | baseline/branch receipt; bundle metadata; merged PR/install provenance |
| `SS-06-02` | `M1-T01` | DM2 Body 1 unknown checked-out relation; Behind/Equal/Ahead/Diverged fixtures | `M1-AT-01` | pre/post refs, fetched OID, relation and refusal receipts |
| `SS-06-03` | `M1-T02` | unrelated stale registration; duplicate-default/drift refusals | `M1-AT-02` | fresh claimant census and exact-target identity |
| `SS-06-04` | `M1-T03` | preserved linked worktree; exact stale Repair; changed repair-set/identity refusals | `M1-AT-03` | operation-scoped opener, lock/admission trace, byte/poststate proof |
| `SS-06-05` | `M2-T01` | DM3/AppKit terminal→new-run and unsettled refusal | `M2-AT-01` | lifecycle trace and chooser presentation receipt |
| `SS-06-06` | `M2-T02` | historical viewer independence and malformed-report refusal | `M2-AT-02` | separate owner/window trace; durable snapshot replay |
| `SS-06-07` | `M2-T03` | A,B→B,C delta/no-op reconciliation; selection reset; fresh mutation gate | `M2-AT-03` | hydration counts, retained/dropped IDs, fresh admission receipt |
| `SS-06-08` | `M2-T04` | zero/success/failure/mixed cleanup inspection and selection oracle | `M2-AT-04` | button-state/copy snapshots and selected-ID set |
| `SS-06-09` | `M3-T01` | M5 row identity/order/alignment and command-event isolation | `M3-AT-01` | native screenshots plus stable row-key transition trace |
| `SS-06-10` | `M3-T02` | deterministic live/historical metadata and count tests | `M3-AT-02` | metadata fixture and rendered values |
| `SS-06-11` | `M3-T03` | redaction/size bounds, old-log fixture decoding, malformed detail refusal | `M3-AT-03` | encoded fixture hashes, bounded output, compatibility receipt |
| `SS-06-12` | `M4-T01–T03`, `M5-T01–T04` | focused script, M5 practical/native, installer/source, repository gate, installed smoke | `M4-AT-01–03`, `M5-AT-01–04` | exact tested head, checks/reviews, merge revision, install/doctor/UAT handoff |

Every `SS-06-*` row is release-blocking. No requirement may be silently deferred, combined away, or
declared complete from a neighboring row's evidence.

## 5. Work items — milestones and zero-context task blocks

### M0 — Freeze release authority and branch

#### M0-T01 — Record the corrective release boundary

**Files:**

- Modify: `docs/runbooks/shadowsync-iterative-delivery.md`
- Read: this plan, ADR 0004, ADR 0005, plan v7
- Create implementation branch from exact clean `origin/main`

**Functions/contracts:**

- Stage string: `Beta v0.6 corrective candidate; operator UAT remains open`
- Identity: `0.6.0 (11)`
- Requirements: exact `SS-06-01–12` statements from §3

**Interfaces:**

- Consumes the accepted ADR/plan bytes and current exact merged main.
- Produces one implementation branch and one runbook authority entry; no product behavior changes.

- [ ] From the sanctioned implementation worktree, run:

```bash
test -z "$(git status --porcelain)"
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git switch -c feat/shadowsync-beta-v0.6
```

- [ ] Update only the runbook's current stage/release provenance and add `SS-06-01–12` as authorized
  pending requirements. Preserve all prior UAT evidence, accepted behavior, and `SS-D001`.
- [ ] Record the starting revision and source-plan digest in the M0 receipt.

**Expected outcome:** one clean corrective branch whose only M0 content is truthful release/UAT
authority; no implementation or UAT row is marked complete.

**M0 exit:** `M0-AT-01` has baseline, branch, identity, requirement, and open-UAT evidence.

### M1 — Restore operation admission without weakening safety

#### M1-T01 — Admit only clean checked-out unknown previews

**Files:**

- Modify: `Sources/ShadowSyncCore/RepositoryInventoryDiscovery.swift`
- Modify: `Sources/ShadowSyncCore/RepositoryModelV2.swift`
- Test: `Sources/ShadowSyncCore/DM2Body1SelfTests.swift`

**Functions:**

- `RepositoryInventoryDiscovery.card`
- `makePlannedOperation`
- `RepositoryInventoryGitInspector.cachedExactRelation`
- the relation/capability model for checked-out versus ref-only update targets

**Interfaces:**

- Consumes cached preview relation, checked-out target identity, and fresh cleanliness.
- Produces a selectable candidate only for the clean checked-out case; execution remains authoritative.

- [ ] Add red fixtures for unavailable cached relation on clean checked-out, dirty checked-out,
  unclaimed ref-only, duplicate claimant, Equal, Behind, Ahead, and Diverged targets.
- [ ] Admit only the verified-clean checked-out unavailable-preview case.
- [ ] Preserve ref-only unknown and incomplete Repair refusals.
- [ ] Assert no test fixture mutates before execution fetch/classification.

**Expected outcome:** the card exposes only the bounded candidate; transaction tests prove Equal
no-op, Behind exact advance, and all unsafe/unknown states unchanged.

#### M1-T02 — Scope default-claim validation to the exact target

**Files:**

- Modify: `Sources/ShadowSyncCore/LocalRepositoryInspection.swift`
- Test: `Sources/ShadowSyncCore/DM2Body1SelfTests.swift`

**Functions:**

- `LocalRepositoryInspection.inspectDefaultBranchTarget`
- `DefaultBranchTargetInspection.requireMutableTarget`
- worktree-record parsing and exact claimant validation

**Interfaces:**

- Consumes fresh worktree records for one common directory.
- Produces exactly one physically revalidated default claimant or a refusal.

- [ ] Add red fixtures for one valid default claimant plus unrelated stale non-default registration,
  two default claimants, moved/replaced target, and changed branch/ref.
- [ ] Remove unrelated stale non-default registrations from Fast-forward target ambiguity.
- [ ] Keep duplicate default claimant and target identity/ref drift fail-closed.

**Expected outcome:** unrelated residue is contextual evidence; the exact default target alone owns
Fast-forward admission.

#### M1-T03 — Open linked worktrees from operation evidence

**Files:**

- Modify: `Sources/ShadowSyncCore/GitSafety.swift`
- Modify: `Sources/ShadowSyncCore/RepositoryMaintenance.swift`
- Modify: `Sources/ShadowSyncCore/FastForwardTransactionV2.swift`
- Test: `Sources/ShadowSyncCore/DM2Body1SelfTests.swift`
- Test: `Sources/ShadowSyncCore/DM2Body2SelfTests.swift`

**Functions:**

- add one operation-scoped linked-worktree opener beside `RepositoryHandle.open` and
  `openMovedWorktree`;
- linked-worktree claim verification and `RepositoryHandle.revalidate`;
- maintenance Repair admission;
- `RefOnlyPreservationSnapshot` consumption in the fast-forward transaction

**Interfaces:**

- Consumes fresh root/common-directory identity, registration metadata, expected ref/repair set,
  frozen configuration, and held common-directory lock.
- Produces a verified descriptor-bound linked-worktree handle or refusal.

- [ ] Add preserved linked-worktree, stale-registration Repair, changed identity, changed repair set,
  duplicate default, unsafe hook/config, and post-open drift fixtures.
- [ ] Implement one no-follow, identity-bound operation opener and use it in Repair and preservation.
- [ ] Preserve immediate pre-mutation checks and prove refused fixture bytes/refs are unchanged.
- [ ] Prove successful Repair reopens only the exact preserved linked worktree and successful
  Fast-forward advances only the exact default target.

**Verification:**

```bash
cd global/tools/dev-main-sync
swift build --disable-index-store
# After M4 registers the selector, run:
./scripts/verify-beta-v0.6.sh
```

**M1 exit:** `M1-AT-01–03` all have deterministic relation, claimant, opener, refusal, and poststate
receipts. No live repository was mutated.

### M2 — Separate run/history state and reuse session evidence

#### M2-T01 — Route Start New Run independently

**Files:**

- Modify: `Sources/ShadowSyncApp/AppDelegate.swift`
- Test: `Sources/ShadowSyncCore/DM3PreflightSelfTests.swift`
- Test: `Sources/ShadowSyncApp/M5Harness.swift`

**Functions:** `startNewRunAction`, `startNewRun`, terminal presentation close/archive handling, and
the lifecycle gate that distinguishes terminal from active/unsettled work.

**Interfaces:**

- Consumes current live-run settlement and terminal presentation state.
- Produces chooser presentation or one precise active/unsettled blocker.

- [ ] Add terminal-report, cancelled-settled, active, unsettled, and malformed-report routing tests.
- [ ] Archive/dismiss terminal presentation before opening the chooser.
- [ ] Preserve blocking only for active/unsettled authority and truthful recovery requirements.

**Expected outcome:** completed history never blocks a new chooser; unsettled work still does.

#### M2-T02 — Give Last Report an independent read-only owner

**Files:**

- Modify: `Sources/ShadowSyncApp/AppDelegate.swift`
- Modify only if needed: `Sources/ShadowSyncApp/Body3RunWindow.swift`
- Test: `Sources/ShadowSyncCore/DM3PreflightSelfTests.swift`
- Test: `Sources/ShadowSyncApp/M5Harness.swift`

**Functions:** `showLastReportAction`, `showLastReport`, `historicalViewer`, and
`Body3RunWindowController` historical presentation.

- [ ] Prove historical open/close cannot cancel, resume, foreground-own, or block a live/new run.
- [ ] Load only the validated durable last-report snapshot; malformed snapshots refuse read-only.
- [ ] Preserve window continuity without sharing active lifecycle authority.

**Expected outcome:** historical viewing is independent and read-only.

#### M2-T03 — Reconcile selected scope by delta

**Files:**

- Modify: `Sources/ShadowSyncCore/SelectedRepositoryScope.swift`
- Modify: `Sources/ShadowSyncCore/SelectedRepositoryHydration.swift`
- Modify: `Sources/ShadowSyncApp/AppDelegate.swift`
- Test: `Sources/ShadowSyncCore/DM3PreflightSelfTests.swift`

**Functions:** selected-scope identity/equality, `SelectedRepositoryHydrator.hydrateEvidence`,
`hydrateVerified`, `hydrateOnce`, and AppDelegate selected-inventory reconciliation.

- [ ] Add A,B→B,C, A,B→A,B no-op, identity-changed B, cleanup-inspected B, and restart fixtures.
- [ ] Retain B only when its exact session binding is unchanged; hydrate C; drop A.
- [ ] Reset operation checkmarks/confirmations and retain unchanged card/cleanup evidence.
- [ ] Prove a later mutation still invokes fresh transaction validation.

**Expected outcome:** unchanged inspection work is reused only inside the session and never becomes
mutation authority.

#### M2-T04 — Gate recommended cleanup bulk selection

**Files:**

- Modify: `Sources/ShadowSyncApp/RepositoryCardsWindow.swift`
- Test: `Sources/ShadowSyncApp/M5Harness.swift`

**Functions:** cleanup state tracking, `selectAllRecommendedRemoval`, button enablement/copy, and
`testingRecommendedRemovalIDs`.

- [ ] Keep the button disabled with explanatory text when zero inspections succeeded.
- [ ] In mixed success/failure state, select only `selectAllEligible` candidates belonging to
  successfully inspected repositories.
- [ ] Prove failure/uninspected candidates remain unselected and manual inherited controls unchanged.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/verify-m5.sh --practical-only
```

**M2 exit:** `M2-AT-01–04` have lifecycle, delta-hydration, cleanup-state, and native control
receipts; action selections and confirmations reset.

### M3 — Stabilize repository-grouped results and compatibility

#### M3-T01 — Keep repository/action rows stable

**Files:**

- Modify: `Sources/ShadowSyncApp/Body3RunWindow.swift`
- Test: `Sources/ShadowSyncApp/M5Harness.swift`

**Functions:** `Body3RunWindowController.update`, `operationPresentation`,
`refreshRepositoryRows`, and `displayState`.

- [ ] Key repository groups by logical repository identity and action rows by planned-operation ID.
- [ ] Build left-aligned, width-constrained groups once; update queued/running/terminal content in
  place without reordering or replacing row identity.
- [ ] Render bounded public outcome text inline; route command events only to the Live Log.
- [ ] Add deterministic row-key/order/leading-edge tests and native screenshots at initial,
  mid-run, mixed terminal, and historical states.

**Expected outcome:** no row jumps, ambiguous indentation, horizontal clipping, or raw command event
appears in public results.

#### M3-T02 — Derive historical metadata

**Files:**

- Modify: `Sources/ShadowSyncApp/RunPresentation.swift`
- Modify as needed: `Sources/ShadowSyncCore/Body3Batch.swift`
- Test: `Sources/ShadowSyncCore/DM2Body3SelfTests.swift`
- Test: `Sources/ShadowSyncApp/M5Harness.swift`

**Functions:** run presentation derivation and durable batch report/result metadata.

- [ ] Derive start/end/duration, unique repositories, attempted actions, and terminal outcome counts
  without accepting contradictory or nonterminal totals.
- [ ] Render the same values for live completion and historical replay.

**Expected outcome:** metadata is deterministic, internally consistent, and requires no mutable UI
state.

#### M3-T03 — Add bounded technical detail and preserve v2 decoding

**Files:**

- Modify: `Sources/ShadowSyncCore/Body3Batch.swift`
- Modify: `Sources/ShadowSyncCore/Body3Coordinator.swift`
- Modify: `Sources/ShadowSyncCore/Body3RunLog.swift`
- Modify: `Sources/ShadowSyncApp/RunPresentation.swift`
- Test: `Sources/ShadowSyncCore/DM2Body3SelfTests.swift`

**Functions:** result construction, coordinator terminal-event mapping, log encode/decode/redaction,
and optional presentation detail.

- [ ] Add an optional technical-detail field with an explicit byte bound and existing redaction
  treatment; reject or truncate over-bound input deterministically.
- [ ] Keep operator outcome text separate from technical detail and never encode raw environment,
  credentials, arbitrary URLs, or unredacted absolute paths.
- [ ] Pin pre-v0.6 valid v2 log fixtures and prove byte-compatible decoding with absent new fields.
- [ ] Prove malformed/unknown schema and unredacted secret/path fixtures fail closed.

**Expected outcome:** diagnostics improve without expanding public or durable evidence exposure.

**M3 exit:** `M3-AT-01–03` have stable-row native evidence, metadata receipts, redaction bounds, and
old-log fixture hashes.

### M4 — Close exact-head verification and release identity

#### M4-T01 — Add one focused v0.6 selector and wrapper

**Files:**

- Modify: `Tests/ShadowSyncSelfTests/main.swift`
- Create: `scripts/verify-beta-v0.6.sh`
- Test sources: `DM2Body1SelfTests.swift`, `DM2Body2SelfTests.swift`,
  `DM2Body3SelfTests.swift`, `DM3PreflightSelfTests.swift`, `M5Harness.swift`

**Functions/contracts:** register `--beta-v06-focused-only`; follow `verify-beta-v0.5.sh` owner-private
fixture, cleanup, testing-build, and explicit-selector conventions.

- [ ] Make the selector invoke every SS-06 detecting test and no unrelated performance/full-host gate.
- [ ] Build production and self-test products in one owner-private root, reap helpers, and remove the
  root on success, failure, signal, or cancellation.
- [ ] Emit `verify-beta-v0.6: PASS` only after all named suites pass.

#### M4-T02 — Run the closed operation and UI matrix

**Files:** verification receipts only; no plan-byte updates.

- [ ] Run:

```bash
cd global/tools/dev-main-sync
./scripts/verify-beta-v0.6.sh
./scripts/verify-m5.sh --practical-only
./install.sh --check
./install.sh --build-release-check
./scripts/source-doctor.sh
cd ../../..
bash .github/scripts/verify-skills.sh
bash ~/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
git diff --check
```

- [ ] In isolated fixtures explicitly prove Behind, Equal, Ahead refusal, Diverged refusal, exact
  stale-registration Repair, duplicate-default refusal, changed-target refusal, and no mutation on
  every refusal.
- [ ] Exercise native result presentation and visually inspect leading alignment, stable row order,
  metadata, inline outcomes, cleanup gating, new-run routing, and historical independence.

**Expected outcome:** all deterministic and native evidence names one exact clean head.

#### M4-T03 — Set and attest release identity

**Files:**

- Modify: `Sources/ShadowSyncCore/ReleaseIdentity.swift`
- Modify only corresponding identity/install expectations in README and tests.

- [ ] Set `ReleaseIdentity.version = "0.6.0"` and `buildNumber = "11"`; retain earlier supported
  versions and all stable metadata keys.
- [ ] Rerun M4-T01/T02 after the identity change.
- [ ] Record one `TESTED_HEAD`, source-input digest, metadata-contract digest, production bundle
  identity, and clean status.

**M4 exit:** `M4-AT-01–03` prove the complete SS-06 matrix and `0.6.0 (11)` at one exact clean
`TESTED_HEAD`. Do not install it yet.

### M5 — Governed ready PR, controller merge, exact-main install, UAT handoff

#### M5-T01 — Commit, push, and open the exact tested head ready

**Files:** the complete M0–M4 implementation body and external delivery receipts.

- [ ] Require:

```bash
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$TESTED_HEAD"
git push -u origin feat/shadowsync-beta-v0.6
```

- [ ] Open one PR against `main` at `TESTED_HEAD` and mark it ready immediately so
  `pr-automation / verify` and reviewer/controller automation run.
- [ ] Do not call `gh pr merge --auto`, change auto-merge, directly merge, bypass checks, or add a
  GitHub runner.

**Expected outcome:** one ready PR whose head exactly equals `TESTED_HEAD`.

#### M5-T02 — Hold exact-head checks and controller-owned merge

- [ ] Require runnerless `pr-automation / verify` and every applicable repository check to pass at
  the current PR head.
- [ ] Resolve material review findings on the branch, rerun dependency-mapped local evidence, and
  update `TESTED_HEAD`; never claim old-head receipts for a new head.
- [ ] Let the reviewer/controller automation alone approve, arm, and merge. Record exact PR URL,
  final head, merge commit, check conclusions, and branch disposition.

**Expected outcome:** exact reviewed head is merged into live `origin/main`, or the release remains
truthfully blocked with no install.

#### M5-T03 — Verify and install only exact merged main

- [ ] From the canonical durable main checkout after merge:

```bash
git fetch origin main
test "$(git branch --show-current)" = "main"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
cd global/tools/dev-main-sync
./scripts/verify-beta-v0.6.sh
./scripts/verify-m5.sh --practical-only
./install.sh --check
./install.sh --build-release-check
cd ../../..
bash .github/scripts/verify-skills.sh
cd global/tools/dev-main-sync
./install.sh --apply
./install.sh --doctor
```

- [ ] Verify installed marketing/build identity `0.6.0 (11)`, exact merged source revision,
  signature, one managed owner, startup readiness, state preservation, and no transaction residue.
- [ ] Run installed native smoke for Start New Run, Show Last Report, delta hydration, cleanup gate,
  Behind/Equal on isolated fixtures, Repair fixture, stable results, log, Close, and Quit.

**Expected outcome:** only exact clean merged main is installed and its provenance is recorded.

#### M5-T04 — Hand off open UAT

- [ ] Present the operator with the v0.6 checklist covering every `SS-06-*` workflow, prior
  still-unaccepted workflows, and deferred `SS-D001`.
- [ ] Record each workflow as not tested, feedback pending, change proposed, accepted, rejected, or
  operator-deferred. Do not infer acceptance from tests, install, use, or silence.
- [ ] Do not label Beta v0.6 released or UAT complete until the runbook's explicit closeout policy is
  satisfied.

**M5 exit:** `M5-AT-01–04` have ready-PR, exact checks/review, controller merge, exact-main
install/doctor/smoke, and open-UAT handoff receipts.

## 6. Milestone acceptance ledger

All rows begin `PENDING`. Evidence lives in receipts, PR/check systems, fixture output, and UAT
records—not by editing an accepted plan.

| ID | Objective criterion | Required evidence / receipt | Status |
|---|---|---|---|
| `M0-AT-01` | Corrective branch starts at clean exact main; runbook records `0.6.0 (11)`, SS-06 scope, and open UAT | baseline/head/branch/source-plan digests; runbook diff | PENDING |
| `M1-AT-01` | Checked-out clean unknown preview is selectable; execution decides exact relation; ref-only unknown refuses | relation fixture matrix, fetched OID, pre/post refs | PENDING |
| `M1-AT-02` | One exact default claimant admits; unrelated stale non-default does not block; duplicate/drift refuses | claimant census, identity/ref refusal receipts | PENDING |
| `M1-AT-03` | Repair/Fast-forward/preservation use fresh linked-worktree evidence with all inherited gates | opener/lock/repair-set trace and poststate proof | PENDING |
| `M2-AT-01` | Terminal presentation cannot block Start New Run; active/unsettled work can | AppKit lifecycle trace and chooser/blocker evidence | PENDING |
| `M2-AT-02` | Last Report is independently owned, read-only, and durable-snapshot backed | historical owner/window/replay trace | PENDING |
| `M2-AT-03` | A,B→B,C reuses only unchanged B, hydrates C, drops A, resets actions, and revalidates mutation | delta counts/IDs and fresh admission trace | PENDING |
| `M2-AT-04` | Cleanup bulk control enables only after success and selects only successful inspected recommendations | control snapshots and selected-ID oracle | PENDING |
| `M3-AT-01` | Repository/action rows retain stable identity/order/alignment and isolate commands to Live Log | native screenshots and row-transition trace | PENDING |
| `M3-AT-02` | Live and historical metadata is deterministic and internally consistent | metadata fixtures and rendered-value receipt | PENDING |
| `M3-AT-03` | Technical detail is optional/bounded/redacted and valid prior v2 logs decode | size/redaction negatives and old-log fixture hashes | PENDING |
| `M4-AT-01` | One focused selector/script covers every SS-06 detecting test and self-cleans | selector manifest and script receipt | PENDING |
| `M4-AT-02` | Focused, practical/native, installer/source, repository, doc-warden, and diff gates pass at one head | exact-head command and visual receipts | PENDING |
| `M4-AT-03` | Production bundle attests exact `0.6.0 (11)` and clean tested source | release/source/metadata/bundle digests | PENDING |
| `M5-AT-01` | One ready PR exists at exact tested head with no merge manipulation | PR URL/head and push receipt | PENDING |
| `M5-AT-02` | Required exact-head checks/reviews pass and controller automation merges that head | check conclusions, review disposition, merge revision | PENDING |
| `M5-AT-03` | Clean exact merged main alone is installed and passes doctor/native smoke | main equality, install provenance, doctor/smoke receipt | PENDING |
| `M5-AT-04` | Operator receives complete checklist and UAT remains explicitly open | UAT handoff record with per-workflow statuses | PENDING |

## 7. Rollback and stop conditions

- **Before merge:** stop, leave or close the PR, and do not install. Revert branch commits normally;
  do not rewrite accepted authority or install branch bytes.
- **After merge but before install:** revert through a reviewed PR if product evidence is wrong; do
  not install the suspect revision.
- **After install:** use only existing `install.sh --repair`, lifecycle rollback, and retained-state
  semantics. Never manually delete the app, plist, state tree, socket, transaction slot, or process.
- **Operation safety:** any identity/ref/claim/policy/hook/repair-set/digest/preimage drift stops that
  operation without mutation. Three matching system failures preserve the existing infrastructure
  pause behavior.
- **Architecture stop:** if satisfying SS-06 requires general Git repair, ref-only unknown
  admission, cross-session capability reuse, schema replacement, new dependency, controller change,
  or weakened safety check, stop and return to the operator with evidence; do not expand this plan.
- **UAT stop:** any credible data-loss, credential-exposure, or unsafe-destructive result blocks
  release and returns to requirement clarification. Nonblocking findings remain recorded under the
  iterative-delivery policy rather than silently broadening the beta.

## 8. Definition of done

The implementation is complete only when every ledger row has its required receipt; one exact
tested head passes the full SS-06 matrix; one ready PR merges that exact reviewed head only through
controller/reviewer automation; clean exact merged main alone is installed as `0.6.0 (11)`; doctor
and installed native smoke pass; no owned fixture/process/dirty checkout remains; and the operator
receives a truthful UAT-open handoff. Engineering completion does not itself accept UAT or declare
the beta released.
