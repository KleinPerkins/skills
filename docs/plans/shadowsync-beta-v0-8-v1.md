# ShadowSync Beta v0.8 corrective release execution plan

**Version:** v1
**Status:** ACCEPTED — 2026-10-05
**Date:** 2026-10-05
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Linked decision:** [ADR 0005 — Separate ShadowSync preview admission from mutation evidence and result ownership](../adr/0005-shadowsync-preview-admission-and-result-ownership.md)
**Inherited authority:** [ShadowSync Beta v0.7 corrective release plan](shadowsync-beta-v0-7-v1.md)
**Planning baseline:** clean linked worktree at exact `origin/main`
`7c5e4c8efdb26b245cdc27a87765056df67dc753`
**Implementation branch:** `fix/shadowsync-beta-v0.8-build13`
**Release identity:** marketing version `0.8.0`, build `13`
**Stage:** Beta v0.8 bounded corrective candidate; operator UAT remains open

> **Immutable authority:** the operator approved every requirement below before implementation.
> Preserve this accepted plan byte-identically. Record implementation and delivery receipts in the
> mutable runbook, commits, tests, PR, and release metadata. Automated success never closes UAT.

## 0. Goal and closed dependency order

Cut one bounded corrective beta that restores large-index Fast-forward and exact Repair execution,
keeps conservative remote-relation safety while making its presentation truthful, and applies the
approved dark-panel and completed-report polish. Preserve every existing mutation gate, the
accepted repository/action hierarchy, the v0.7 performance correction, and open-UAT semantics.

```text
M0 freeze authority and release identity
  → M1 align bounded execution evidence and diagnostics
    → M2 clarify conservative relation presentation
    → M3 apply AppKit and completed-report polish
  → M4 close exact-head release verification
  → M5 open one ready PR and stop at controller merge
```

M1–M3 may share one branch but retain independently detecting tests. M5 cannot start until one
clean exact head has all required receipts.

## 1. Frozen scope, invariants, and non-goals

### 1.1 Requirements

- **SS-08-01 — Release authority.** Cut only `0.8.0 (13)` from the exact baseline and branch named
  above. Preserve ADR 0005 and the accepted v0.6/v0.7 plan bytes; keep operator UAT open.
- **SS-08-02 — Bounded execution evidence.** Use the existing 32 MiB inventory capacity for
  execution and exact Repair/preservation commands that require complete output. Keep explicit
  truncation checks and fail closed above that bound. Do not make subprocess capture unbounded.
- **SS-08-03 — Truthful command diagnostics.** Distinguish successful-but-truncated output from a
  nonzero exit. Never expose ordinary `ls-files` output or filenames as failure detail. Command
  audit records describe admitted commands accurately instead of inheriting a later aggregate
  operation failure code. Genuine target, configuration, identity, or policy drift retains the
  existing public refusal and technical classification.
- **SS-08-04 — Conservative relation presentation.** Keep internal `.unavailable` state and every
  execution gate unchanged when cached tracking state differs from the advertised remote. Present
  that known condition exactly as
  `Default relation: Remote changed since last fetch · exact comparison pending`, followed by the
  existing `Ready after fresh safety revalidation.` Never infer ahead/behind before guarded fetch.
- **SS-08-05 — Appearance-aware cleanup panel.** Replace the alpha-composited control background
  with a named dynamic color that resolves under the effective appearance by blending
  `.windowBackgroundColor` 8% toward `.labelColor`. Preserve semantic label, secondary-label,
  separator, and standard-control colors; respond correctly to Aqua/Dark Aqua changes.
- **SS-08-06 — Completed-report metadata.** Remove repository names from the top metadata block.
  Render persisted UTC start/end timestamps in the autoupdating device timezone with fixed
  12-hour AM/PM wall-clock text and timezone abbreviations. Round duration to the nearest whole
  second, decompose canonical days/hours/minutes/seconds, omit zero units, pluralize correctly, and
  show `0 seconds` when all units are zero. Keep repository count, attempted-action count, and
  nonzero terminal outcome counts.
- **SS-08-07 — Governed verification and delivery.** Add focused v0.8 selectors and a self-cleaning
  verification wrapper; prove large-index Fast-forward and exact Repair, hidden-index and over-limit
  refusal, genuine freshness drift, relation presentation, deterministic date/DST/duration,
  Aqua/Dark Aqua visuals, collapsed/expanded high-volume rendering, installer/source identity, and
  repository/doc/diff gates at one clean exact head. Open one normal ready PR and leave controller
  automation alone to review and merge.

### 1.2 Preserved invariants

- Preview evidence never authorizes mutation. Common-directory locks, exact Repair sets, refs,
  hooks, identity, digest, preservation, postflight, and immediate pre-mutation checks remain
  authoritative.
- Detached stale registrations remain unavailable. No cleanup/pruning behavior or selection
  semantics change.
- The immutable execution plan, append-only durable log, cancellation, confirmations, two-worker
  scheduler, and old-log compatibility do not change.
- The accepted stable repository cards, action rows, connector geometry, hierarchy typography,
  accessibility, and state-transition identities remain unchanged.
- The v0.7 incremental/lazy/coalesced Live Log path and runtime instrumentation remain in place.
- Tests use isolated fixtures or owned temporary repositories. No live user repository operation
  may run and installed `0.7.0 (12)` remains untouched.
- No feature-head install, direct/admin merge, agent-armed auto-merge, check bypass, workflow-policy
  change, paid runner, or mutation of unrelated branches/operator data is allowed.

### 1.3 Non-goals

- Streaming subprocess redesign, unbounded output, worker-count changes, direct-index-only
  substitution, granular prune, detached-commit preservation/removal, preservation-store changes,
  or new cleanup semantics.
- `NSOutlineView`, hierarchy redesign, repository-card redesign, new telemetry, package
  dependencies, performance SLA, or unrelated cleanup.
- Declaring Fast-forward, Repair, pruning, or overall Beta UAT accepted.

## 2. Evidence and implementation seams

The v0.7 operator run `24c274d8-8c8d-49e3-94d0-6f5193e47dc3` completed 18 terminal actions across
nine repositories: 13 succeeded, two skipped, and three failed. `pr-automation-controller` was the
only proven freshness refusal; its `.git/config` identity changed after planning. `dev` and
`skills` were false failures: `git ls-files -v -z` exited zero but emitted 26,854 and 55,578 bytes,
respectively, above the execution runner's 16,384-byte bound. Six of 19 catalog authorities exceed
that old bound. Inventory already uses a bounded 32 MiB capacity.

The same run recorded maximum main-actor update time 3.356 ms, maximum heartbeat latency
12.311 ms, approximately 37 MB resident memory after the run, and no hang diagnostic. Preserve the
v0.7 rendering design and test both collapsed and sustained expanded Live Log paths.

Implement through existing seams:

- `DescriptorProcessRunner`, Body 3 runner construction, complete-output call sites, and typed
  truncation diagnostics;
- `RepositoryInventoryDiscovery` relation context and `RepositoryCardsWindowController`
  presentation;
- `cleanupInspectionSection` and an appearance-aware named dynamic color;
- `Body3RunMetadataPresentation` with deterministic timestamp/duration formatters;
- release identity, package metadata, README/install/source assertions, focused selector, and
  verification wrapper.

## 3. Milestones and acceptance rows

### M0 — Freeze authority

- Create the named branch only from clean exact baseline `7c5e4c8…`.
- Add this accepted plan and index row; update the mutable runbook with `SS-08-01–07`, evidence,
  open-UAT state, candidate identity, and preserved v0.7 evidence hash.
- Do not edit this plan after M0.

**M0-AT-01:** plan/index/runbook name the exact baseline, branch, identity, closed scope, preserved
safety boundaries, and open UAT; doc and diff checks pass.

### M1 — Align bounded execution evidence

- Apply the existing 32 MiB inventory limit only to production action/Repair/removal runners whose
  complete bounded output is required.
- Keep status, timeout, cancellation, and stdout/stderr truncation independently typed. On
  truncation, expose command/status/bound metadata only; omit captured normal stdout.
- Mark command audit rows as admitted; terminal records remain the source of operation outcome.
- Add catalog-shaped large-index fixtures for checked-out Fast-forward Behind/already-current,
  exact Repair/preservation, hidden-index refusal, and output above 32 MiB. Re-prove genuine
  target/config drift and all existing locks/digests/postflight gates.

**M1-AT-01:** status-zero index output above 16 KiB and below 32 MiB completes the intended safe
path; output above 32 MiB refuses before mutation without filenames; genuine drift still refuses;
large-index exact Repair preserves every unselected worktree, ref, and byte.

### M2 — Clarify conservative relation presentation

- Retain `.unavailable` whenever tracking and advertised remote OIDs differ.
- Carry a bounded presentation reason that distinguishes this stale-cache condition from missing
  refs or general inspection failure.
- Render the exact approved copy only for stale-cache versus advertised-remote evidence.
- Add equal cached/advertised, stale cached remote, missing refs, and post-fetch exact relation
  fixtures.

**M2-AT-01:** no pre-fetch path claims ahead/behind; stale-cache Fast-forward remains selectable
only under the existing checked-out/clean proof; post-fetch exact relation uses the existing exact
graph comparison.

### M3 — Apply AppKit and completed-report polish

- Add a named dynamic optional-cleanup-panel fill derived from semantic AppKit colors and effective
  appearance. Preserve standard text, border, and control tokens.
- Format start/end in deterministic injected timezone/locale tests while production uses
  autoupdating local time. Show timezone abbreviation for each timestamp.
- Round duration before canonical decomposition. Required boundaries are:
  `499 ms → 0 seconds`, `500 ms → 1 second`, `59,500 ms → 1 minute`,
  `3,599,500 ms → 1 hour`, and `86,399,500 ms → 1 day`.
- Render exactly two metadata lines: timing/duration, then repository/action/outcome counts. Remove
  repository names from the top block.
- Re-prove stable hierarchy geometry/identities and high-volume collapsed/expanded behavior.

**M3-AT-01:** Aqua and Dark Aqua resolved-color/contrast fixtures and visually inspected captures
are readable; DST/timezone and duration boundary tests are deterministic; accepted hierarchy bytes
and behavior do not change.

### M4 — Close one exact release head

- Set all release/catalog/installer/README expectations consistently to `0.8.0 (13)`.
- Register `--beta-v08-focused-only` and `scripts/verify-beta-v0.8.sh`.
- Run focused, core/transaction, AppKit/native visual, high-volume collapsed/expanded,
  installer/source, full repository, doc-warden, frozen-authority, and diff gates.
- Inspect every generated visual. Prove any broad baseline failure from an untouched exact-main
  source rather than hiding it or expanding scope.

**M4-AT-01:** one clean `TESTED_HEAD` passes the complete mapped matrix and attests production
identity `0.8.0 (13)`, bounded output, truthful diagnostics/relation copy, deterministic metadata,
dynamic appearance, unchanged safety/hierarchy, and no owned process/temp residue.

### M5 — Governed ready PR

- Perform a subtractive whole-body review and remove speculative code.
- Commit meaningful complete work, push the exact tested head, and open one normal ready PR.
- Resolve only in-scope exact-head findings with minimal pushes and refreshed evidence.
- Never install, arm/alter auto-merge, merge, bypass checks, or change workflow policy.

**M5-AT-01:** one ready PR names the exact clean tested head; installed v0.7 and live repositories
are unchanged; the linked worktree is clean; and all owned helpers and temporary roots are removed.

## 4. Verification matrix

| Requirement | Detecting evidence |
|---|---|
| `SS-08-01` | plan/index/runbook diff; exact baseline/branch/identity assertions |
| `SS-08-02` | 16 KiB–32 MiB Fast-forward/Repair fixtures; >32 MiB refusal; hidden-index and preservation regressions |
| `SS-08-03` | typed exit/truncation diagnostics; no-stdout-leak assertion; admitted command-record checks; genuine-drift fixtures |
| `SS-08-04` | equal/stale/missing/post-fetch relation matrix and exact public-copy assertion |
| `SS-08-05` | Aqua/Dark Aqua dynamic-resolution, contrast, control-token, and native visual checks |
| `SS-08-06` | fixed timezone/DST parsing, rounding/radix/pluralization boundaries, and no-name metadata assertions |
| `SS-08-07` | focused/core/AppKit/native/install/source/repository/doc/diff gates and exact ready PR |

Every row is release-blocking. Evidence lives outside this immutable plan.

## 5. Stop and rollback conditions

- Stop before implementation if the branch does not start from the exact clean baseline.
- Stop and return to the operator if the correction requires weakening a mutation gate, changing
  cleanup semantics or worker count, replacing the UI architecture, adding telemetry/dependencies,
  or modifying accepted authority bytes.
- Any identity/ref/claim/policy/hook/Repair-set/digest/preimage drift remains a safe refusal.
- Before merge, abandon or correct the PR normally and do not install. Installation is a separate
  exact-merged-main task.

## 6. Definition of done

The implementation task is complete only when `M0-AT-01` through `M5-AT-01` have objective receipts
at one exact clean head, native visuals were inspected in both appearances, the complete corrective
body passed subtractive review, one ready PR is at the controller gate, installed v0.7 and live
repositories remain untouched, and all owned temporary resources are removed. Engineering
completion does not accept or close operator UAT.
