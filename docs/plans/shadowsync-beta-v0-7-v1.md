# ShadowSync Beta v0.7 corrective release execution plan

**Version:** v1
**Status:** ACCEPTED — 2026-10-05
**Date:** 2026-10-05
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Linked decision:** [ADR 0005 — Separate ShadowSync preview admission from mutation evidence and result ownership](../adr/0005-shadowsync-preview-admission-and-result-ownership.md)
**Inherited authority:** [ShadowSync Beta v0.6 corrective release plan](shadowsync-beta-v0-6-v1.md)
**Planning baseline:** clean linked worktree at exact `origin/main`
`c95c4009226b8385d8bf222a0da31f14de1817f2`
**Implementation branch:** `fix/shadowsync-beta-v0.7-build12`
**Release identity:** marketing version `0.7.0`, build `12`
**Stage:** Beta v0.7 bounded corrective candidate; operator UAT remains open

> **Immutable authority:** the operator approved every requirement below before implementation.
> Preserve this accepted plan byte-identically. Record implementation and delivery receipts in the
> mutable runbook, commits, tests, PR, and release metadata. Automated success never closes UAT.

## 0. Goal and closed dependency order

Cut one bounded corrective beta that removes the proven quadratic Live Log main-thread path,
clarifies unavailable Repair without weakening its all-or-nothing safety gate, and makes selected
repositories visibly own their child actions. Preserve the v0.6 execution plan, durable log,
cancellation semantics, two-worker scheduler, stable row identity, and every mutation proof.

```text
M0 freeze authority and release identity
  → M1 bound and coalesce Live Log work
  → M2 correct unavailable Repair presentation
  → M3 add stable repository/action hierarchy
  → M4 close exact-head release verification
  → M5 open one ready PR and stop at controller merge
```

M1–M3 may share one branch but retain independently detecting tests. M5 cannot start until one
clean exact head has all required receipts.

## 1. Frozen scope, invariants, and non-goals

### 1.1 Requirements

- **SS-07-01 — Release authority.** Cut only `0.7.0 (12)` from the exact baseline and branch named
  above. Keep Beta UAT open and preserve accepted ADR 0005 and the v0.6 plan byte-identically.
- **SS-07-02 — Linear, lazy Live Log projection.** Render and redact each newly arrived record once,
  retain the existing 131,072-character bounded suffix behavior, and never rebuild the complete
  record prefix as the run grows. While Live Log is collapsed, update only bounded in-memory
  projection state; expansion catches up in one bounded snapshot.
- **SS-07-03 — Coalesced UI delivery and evidence.** Coalesce queued event/UI-log work without
  changing event order, immutable plan state, confirmations, cancellation, append-only durable
  logging, or the two-worker scheduler. Capture non-sensitive update duration, maximum backlog,
  coalesced visible render count, rendered-character count, and UI-heartbeat latency. Deterministic
  tests prove record visits remain linear and regular expressions are compiled once, without a
  timing SLA.
- **SS-07-04 — Truthful unavailable Repair.** Keep Git's exact all-or-nothing prune set and every
  existing proof gate unchanged. An unattempted unavailable optional Repair uses neutral disabled
  copy with generalized total/unproven/detached counts and “Nothing will be changed.” Registration
  identifiers and proof reasons appear only in Technical diagnostics. Orange/error presentation is
  reserved for attempted actions that refuse or fail.
- **SS-07-05 — Stable visual hierarchy.** Keep repository cards and action-row objects stable.
  Render each 13-point semibold repository parent with trailing `N of M steps`; indent 12-point
  regular child titles by 24–28 points; render 11-point details; and draw a 1-point vertical
  connector with horizontal elbows from the parent gutter to every child. Action titles remain
  primarily neutral while icons/details use semantic status colors. Geometry and identities remain
  stable through queued, running, terminal, and historical presentation.
- **SS-07-06 — Governed verification and delivery.** Add focused selector
  `--beta-v07-focused-only` and `scripts/verify-beta-v0.7.sh`; prove focused, core, AppKit, native
  visual, high-volume, installer/source, repository, doc, and diff gates at one clean exact head;
  visually inspect native captures; then open one normal ready PR. Controller automation alone
  reviews and merges. Do not install before merge or infer UAT acceptance.

### 1.2 Preserved invariants

- Detached stale registrations remain unavailable in Beta. No commit-preservation, removal,
  granular-prune, or preservation-store semantics are added.
- Preview evidence never authorizes mutation. The common-directory lock, exact Repair set, refs,
  hooks, identity, digest, postflight, and immediate pre-mutation checks remain authoritative.
- Durable Body 3 logging stays append-only and valid older v2 logs remain decodable.
- The immutable execution plan, action-state UI, grouped confirmation, cancellation behavior, and
  maximum two concurrent workers do not change.
- Tests use isolated fixtures or owned temporary repositories. No live user repository operation
  may run and the installed `0.6.0 (11)` app remains untouched.
- No feature-head install, direct/admin merge, agent-armed auto-merge, check bypass, workflow-policy
  change, paid runner, or mutation of unrelated branches/operator data is allowed.

### 1.3 Non-goals

- `NSOutlineView`, a generalized tree component, repository-card redesign, granular Git prune,
  detached-commit preservation, retention changes, scheduler tuning, or performance SLA.
- New report/log schema family, external telemetry, raw path/command/credential instrumentation,
  new package dependency, or unrelated cleanup.
- Declaring v0.6 or v0.7 UAT complete.

## 2. Evidence and implementation seams

The first successful operator batch completed 20/20 actions over five repositories and wrote 816
records, including 745 command records, with a 50-events/second peak and a 786 KB durable log. The
macOS diagnostic recorded 90 CPU seconds over 146 seconds (62% average); 24 of 26 samples were in
`Body3RunWindowController.update → Body3RunLogReader.render → NSRegularExpression`. The current
path schedules one uncoalesced main-actor task per event, rebuilds/redacts every prior record, and
replaces the full `NSTextView` even while collapsed. Memory remained near 100 MB. This is a proven
CPU/main-thread rendering defect, not evidence for worker-count or durable-log changes.

The lifecycle inventory also found 11 stale registrations across 7 of 19 authority records.
`dev`, `intent-router`, and `skills` contained mixed branch-backed and detached stale registrations.
The all-or-nothing refusal is correct; per-registration orange failures and wording that implies
selection could admit an unprovable set are presentation defects.

Implement through existing seams:

- `Redactor`, `Body3RunLogReader`, and a bounded incremental log projection;
- the Body 3 event handoff in `AppDelegate` and `Body3RunWindowController`;
- `RepositoryMaintenancePlanner`, additive optional repository-card diagnostics, and
  `RepositoryCardsWindowController`;
- stable `Body3RunWindowController` repository/action views and AppKit harness geometry;
- release identity, package metadata, README/install/source manifests, focused selector, and
  verification wrapper.

## 3. Milestones and acceptance rows

### M0 — Freeze authority

- Create the named branch only from clean exact baseline `c95c400…`.
- Add this accepted plan and index row; update the mutable runbook with `SS-07-01–06`, evidence,
  open-UAT state, and candidate identity.
- Do not edit this plan after M0.

**M0-AT-01:** plan/index/runbook name the exact baseline, branch, identity, closed scope, preserved
safety boundaries, and open UAT; doc and diff checks pass.

### M1 — Bound and coalesce Live Log

- Precompile and reuse the existing redaction expressions without changing replacements or bounds.
- Add a bounded incremental projection that visits each record once and reproduces the current
  rendered line and earlier-events-omitted behavior.
- Coalesce main-actor event delivery and visible log flushes while preserving ordered state and
  confirmation handling. Collapsed presentation performs zero `NSTextView` replacements; expansion
  performs one bounded catch-up, followed by coalesced incremental snapshots.
- Capture and expose bounded, non-sensitive performance evidence: records, maximum backlog,
  projection work, visible renders, rendered characters, update duration, and heartbeat latency.
- Add deterministic high-volume tests that compare canonical output, prove linear record visits,
  stable compiled-expression identities, collapsed/expanded behavior, and fewer visible renders
  than events without asserting wall-clock thresholds.

**M1-AT-01:** 816-record and larger deterministic fixtures preserve rendered/redacted output and
show one projection visit per record, no complete-prefix rerender, one expression compilation set,
zero collapsed visible writes, bounded catch-up, and coalesced event/UI work.

### M2 — Correct unavailable Repair

- Classify detached versus other independently unproven stale registrations during read-only
  planning without changing successful evidence or transaction admission.
- Emit one neutral public summary with generalized counts and “Nothing will be changed”; keep
  identifiers/reasons in bounded redacted Technical diagnostics.
- Leave selectable fully proven Repair unchanged. Emit no Repair-unavailable row when no stale
  registration exists. Keep attempted refusal/failure terminal presentation semantic.
- Add mixed branch-backed/detached, fully repairable, no-stale, pluralization, diagnostics, and
  unchanged-mutation-gate regressions.

**M2-AT-01:** fixtures prove identical operation availability/refusal boundaries, correct neutral
copy in every count case, no identifier in public copy, and exact identifiers/reasons only inside
Technical diagnostics.

### M3 — Add stable hierarchy

- Replace direct child labels only with a minimal stable row/container presentation; do not replace
  card, repository, or action identities during status transitions.
- Apply the exact typography, indentation, connector, semantic color, and trailing step-count
  requirements from `SS-07-05`.
- Extend AppKit tests for row/group identities, child inset, connector width/elbows, fonts, neutral
  titles, semantic details, accessibility text, and queued/running/terminal/historical stability.
- Generate native initial, running, terminal, and historical captures and inspect them against the
  approved design concept.

**M3-AT-01:** deterministic geometry/identity tests pass and inspected native captures show one
unambiguous repository parent for every child action without clipping or row movement.

### M4 — Close one exact release head

- Set all release/catalog/installer/README expectations consistently to `0.7.0 (12)`.
- Register `--beta-v07-focused-only` and an owner-private self-cleaning
  `scripts/verify-beta-v0.7.sh` that covers M1–M3.
- Run the focused selector; relevant Body 1/2/3 and transaction/core suites; M5 practical/native
  visual checks; deterministic high-volume fixture; installer/source checks; full repository gate;
  doc-warden; and `git diff --check`.
- Inspect every generated visual. Classify a broad failure against exact baseline evidence rather
  than hiding it or expanding scope.

**M4-AT-01:** one clean `TESTED_HEAD` passes the complete mapped matrix and attests production
identity `0.7.0 (12)`, source bytes, bounded linear work, native hierarchy, unchanged safety, and no
owned process/temp residue.

### M5 — Governed ready PR

- Perform a subtractive whole-body review; remove speculative code and confirm all non-goals.
- Commit meaningful complete work, push the exact tested head, and open one normal ready PR against
  `main`.
- Resolve only in-scope exact-head findings with minimal pushes and refreshed dependent evidence.
- Never install the candidate, arm/alter auto-merge, merge, bypass checks, or change workflow policy.
  Stop at the controller review/check/merge gate and report exact head/state.

**M5-AT-01:** one ready PR names the exact clean tested head; applicable checks/review are accurately
reported; installed v0.6 and operator data are unchanged; the linked worktree is clean; and no owned
helpers or temporary roots remain.

## 4. Verification matrix

| Requirement | Detecting evidence |
|---|---|
| `SS-07-01` | plan/index/runbook diff; exact baseline/branch/identity assertions |
| `SS-07-02` | canonical old/new rendering equality; redaction/bound tests; 816+ record linear counters; collapsed/expanded AppKit tests |
| `SS-07-03` | event-order, backlog/coalescing, update/heartbeat instrumentation, confirmation and cancellation regressions |
| `SS-07-04` | mixed detached, fully repairable, no-stale, count/copy/diagnostics fixtures plus unchanged transaction safety suite |
| `SS-07-05` | AppKit identity/font/inset/connector/color/accessibility tests and visually inspected native captures |
| `SS-07-06` | focused wrapper, mapped core/AppKit/native gates, install/source checks, repository gate, doc-warden, diff check, exact ready PR |

Every row is release-blocking. Evidence lives outside this immutable plan.

## 5. Stop and rollback conditions

- Stop before implementation if the branch does not start from the exact clean baseline.
- Stop and return to the operator if the correction requires weakening Repair, changing worker
  count, replacing the UI architecture, changing durable schema compatibility, adding telemetry or
  a dependency, or modifying accepted authority bytes.
- Any identity/ref/claim/policy/hook/Repair-set/digest/preimage drift remains a safe operation
  refusal; do not “fix” it through presentation code.
- Before merge, abandon or correct the PR normally and do not install. After merge, installation is
  a separate exact-main task.

## 6. Definition of done

The implementation task is complete only when `M0-AT-01` through `M5-AT-01` have objective
receipts at one exact clean head, native visuals were inspected, the whole corrective body passed
subtractive review, one ready PR is at the controller gate, installed v0.6 and live repositories
remain untouched, and all owned temporary resources are removed. Engineering completion does not
accept or close operator UAT.
