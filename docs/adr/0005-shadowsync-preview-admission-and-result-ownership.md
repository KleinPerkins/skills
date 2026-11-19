# ADR 0005: Separate ShadowSync preview admission from mutation evidence and result ownership
Status: draft — 2026-10-04

**Related authority:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](0004-dev-main-sync-repository-lifecycle-control-center.md)
**Decision owner:** Laurence Duggan
**Scope:** ShadowSync operation admission, linked-worktree validation, session evidence reuse,
historical-report ownership, and repository/action result semantics

## Decision

Supplement ADR 0004 with the following durable rules. This ADR does not supersede or weaken ADR
0004's repository identity, canonical-root authority, operation-scoped eligibility, closed repair,
retention, removal, batch, or delivery decisions.

1. **Preview evidence is not mutation evidence.** Discovery may expose an operation as selectable
   from bounded cached evidence, but selection never authorizes mutation. The executing transaction
   must reacquire and validate the evidence on which that mutation depends inside its own locked
   admission window. A failed or changed revalidation refuses without mutation.
2. **A checked-out target may survive an unknown preview relation.** When the exact default branch
   is checked out in one freshly identified, verified-clean target, an unavailable cached preview
   relation may expose Fast-forward as a candidate. Execution must fetch the exact advertised
   remote object and freshly resolve Equal, Behind, Ahead, or Diverged before acting. Only Behind
   may advance; Equal is a verified no-op; Ahead, Diverged, unavailable execution evidence, and
   drift refuse. An unknown ref-only target remains ineligible because it lacks the checked-out
   worktree evidence needed for this bounded admission.
3. **Default claims and linked worktrees are operation-scoped.** Fast-forward requires one fresh
   default-branch claimant and physical revalidation of that exact worktree. Unrelated stale
   non-default registrations cannot veto it. Repair and preservation must open linked worktrees
   from fresh operation evidence rather than a stale discovery snapshot. Duplicate default claims,
   changed identities, changed refs, changed repair sets, unsafe hooks, policy drift, or incomplete
   topology still refuse.
4. **Session evidence may be reused; mutation validation may not.** An unchanged repository binding
   may retain inspected card and optional-cleanup evidence for the life of the current app session.
   Reconciliation hydrates only added or materially changed repositories and drops removed ones.
   Action selections and confirmations reset. No session cache crosses restart or substitutes for
   fresh per-mutation validation.
5. **Historical reports are independent owners.** A completed durable report is not an active run.
   `Start New Run` may archive or dismiss terminal presentation and open selection unless active or
   unsettled work remains. `Show Last Report` opens an independent read-only historical viewer whose
   lifecycle cannot block, resume, cancel, or otherwise mutate a new run.
6. **Repository and action results have stable semantics.** A logical repository owns one stable
   result group and each planned action owns one stable row from queued through running to terminal.
   Status changes update that row in place. Bounded operator-facing success, warning, refusal, and
   failure text appears inline. Command events remain in the Live Log. Historical start/end/duration,
   repositories, attempted actions, and outcome counts are derived from durable run evidence.
   Optional technical detail is bounded and redacted, and previously valid v2 logs remain decodable.

## Why

Beta v0.5 UAT exposed three evidence/ownership mismatches:

- the immutable clone model knew linked worktrees while a stale discovery snapshot supplied an
  empty linked-worktree set to later transactions;
- a live remote object absent from the local cache produced an unavailable preview relation even
  though execution could safely fetch and classify that exact object; and
- completed-report routing, current-run ownership, same-session inspection, and visual result rows
  were coupled, causing unnecessary rehydration, blocked new runs, and unstable presentation.

ADR 0004 already requires operation-scoped eligibility and fresh target checks. The correction is
therefore to separate cheap preview evidence from authoritative execution evidence and to assign
session/history/result state to explicit owners, not to replace the architecture.

### Alternatives rejected

1. **Require complete relation and topology evidence during discovery.** This preserves the false
   blockers: cache misses and unrelated stale registrations continue to hide an operation that the
   transaction can safely decide after exact fetch and fresh inspection.
2. **Trust the preview through mutation.** Cached relation, cleanliness, identity, claim, or repair
   evidence can drift. Reusing it as authorization would weaken ADR 0004's race and target guards.
3. **Block the whole repository on any stale registration.** This returns to clone-wide eligibility
   and lets unrelated non-default residue disable a physically verified default target.
4. **Always discard and rebuild the selected session.** It is simple but repeats expensive,
   unchanged inspections and discards useful cleanup evidence without adding mutation safety.
5. **Use one window/state owner for live and historical runs.** Terminal presentation can then block
   a new run or be mistaken for active work, and a historical viewer can affect live lifecycle state.
6. **Append transient action rows and raw command output.** Row movement obscures repository/action
   outcomes, while raw command details in public results expand the credential and path disclosure
   surface. Stable rows plus a bounded Live Log preserve both clarity and diagnostics.

## Consequences

### Positive

- Safe checked-out Fast-forward is available despite a bounded preview cache miss.
- Unrelated stale non-default registrations no longer veto an exact verified default target.
- Fast-forward, Repair, and preservation consume one coherent operation-scoped topology.
- Unchanged same-session inspections are retained without caching mutation authorization.
- New-run and historical-report flows cannot accidentally own or block each other.
- Batch and historical results remain spatially stable and operator-readable.

### Costs and risks

- Discovery capability and transaction admission become explicitly different states and need
  separate tests.
- Session evidence requires exact identity/version keys and deterministic invalidation.
- Historical and live windows require independent ownership and close behavior.
- Result schemas must preserve stable identifiers and backward decoding while adding metadata and
  bounded technical detail.

### Safety invariants

- No mutation occurs from an unavailable execution relation.
- Ref-only unknown-relation Fast-forward remains refused.
- Locking, exact repair-set, ref, hook, identity, policy, digest, and immediate pre-mutation checks
  remain mandatory.
- Duplicate default claims or changed physical identities refuse.
- Technical detail stays optional, bounded, redacted, and separate from operator-facing outcomes.
- Release identity, governed PR/controller merge, exact-merged-main installation, and open UAT
  status remain execution-plan gates, not consequences inferred from accepting this ADR.
