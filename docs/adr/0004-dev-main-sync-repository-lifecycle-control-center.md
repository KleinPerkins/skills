# ADR 0004: Make Dev Main Sync a repository lifecycle control center
Status: accepted — 2026-09-09
Supersedes: ADR-0003 — [source](0003-dev-main-sync-global-capability.md)

**Owners:** Laurence Duggan (`KleinPerkins`); `KleinPerkins/skills` maintainers
**Scope:** Dev Main Sync repository identity, default-branch maintenance, bounded repair,
local branch/worktree inventory and retirement, batch execution, and operator presentation
**Decision owner:** Laurence Duggan

## Decision

Retain Dev Main Sync as the source-owning Flavor-1 global tool at
`global/tools/dev-main-sync/`, but replace its clone-wide, hard-coded-`main` operating model
with a repository-centric local workspace lifecycle model.

The v2 model makes these decisions:

1. **One logical repository card.** The top-level identity is the normalized,
   credential-free GitHub `owner/repository`. Independent clones nest beneath that card,
   grouped internally by physical Git common directory. Worktrees and local branches are
   explicit associated entities rather than facts flattened into a clone row.
2. **One explicit update authority.** Each writable logical repository has exactly one
   Dev Main Sync canonical local root. The app stores that operator choice and revalidates
   its path, origin, common-directory identity, ownership, and policy before every
   dependent action. It never infers authority from path naming, cleanliness, recency,
   current branch, or which clone is already up to date. Missing or ambiguous authority
   disables only actions that need it. On first launch, one bounded confirmation may show
   and accept all cards that have exactly one writable clone; cards with multiple writable
   clones still require an individual choice. Select All never chooses authority.
3. **Operation-scoped eligibility.** A `PlannedOperation` and its exact target own safety
   eligibility. A feature worktree, duplicate clone, hook marker, stale relation, or
   GitHub lookup failure cannot disable an unrelated safe fast-forward. Permanent
   no-touch, repository-owned workflow, reference-only, origin, ownership, and live-policy
   boundaries remain enforced.
4. **Actual remote defaults and target-scoped fast-forward.** Resolve the selected
   origin's symbolic remote `HEAD`, fetch only that branch without prune, tags, submodule
   recursion, maintenance, or `FETCH_HEAD`, then classify Equal, Behind, Ahead, or
   Diverged. Behind may advance through `merge --ff-only` in the uniquely verified
   worktree that has the default branch checked out, or through compare-and-swap
   `update-ref` when the complete zero-to-many worktree-claim set is empty. Git does not
   enforce worktree claims for `update-ref`; every claim set is therefore re-enumerated in
   the locked pre-mutation window. Ahead, Diverged, uncertain identity, and races never
   mutate.
5. **Only narrow, decided repair.** Approve Git-owned pruning of a fully proven all-safe
   set of stale non-default worktree registrations; approve path-scoped
   `git worktree repair <path>` for a clean, provably moved non-default worktree; reject
   local `origin/HEAD` repair as cosmetic; and approve missing-local-default creation only
   as an explicitly named initialization using a zero-old-object compare-and-swap. No
   dirty-state repair, history reconciliation, lock deletion, object repair, auth repair,
   policy repair, hook bypass, or general Git repair enters the product.
6. **Direct operator authority for local feature retirement.** Dev Main Sync owns removal
   of non-default local feature worktrees and branches selected by the human operator in
   the shipped native utility. AWA contributes read-only provenance/liveness advice and is
   the preferred worktree cleanup adapter when it succeeds, but AWA refusal, stale state,
   bad provenance, or engine absence cannot hide the control or veto an explicitly selected
   **Operator override**. The utility never edits AWA state or claims AWA approved the
   override; it reports external operator authorization and advisory AWA residue afterward.
   Agents implementing/testing the utility remain fully governed by repository/AWA rules.
7. **Recommendation is not permission.** Worktree and Branch rows share a closed four-state
   recommendation pattern: **Recommended**, **Recovery copy required**, **Keep**, and
   **Override risk**. Age, PR purpose, dirtiness, active signals, and AWA state affect that
   recommendation, not whether a non-default feature item has a visible removal path.
   Default branches, canonical update targets, permanent no-touch repositories, remote
   branches, product installation/state, and arbitrary non-Git directories remain outside
   cleanup controls.
8. **Preserve by default; disclose deliberate loss.** The normal route revalidates exact
   identity/claims and creates a protected, restore-proven artifact for unique commits or
   tracked/index/untracked/ignored files. Possible secrets require explicit inclusion and
   protected local storage. If preservation is incomplete, failed, or declined, the item
   becomes **Override risk** with exact loss/disruption copy; one grouped final confirmation
   may still authorize Git-supported ordinary or force-capable worktree removal and exact-ref
   CAS branch deletion. Worktree removal precedes branch removal. Remote refs are never
   deleted, and no blind filesystem cleanup is added.
9. **Legible bounded execution.** Present compact repository cards with visually distinct
   Worktree and Branch rows, recommendation badges, common checkbox/action mechanics, and
   one grouped risk confirmation. Execute Recovery → Remove worktree → re-inspect claims →
   Recovery → Remove local branch → verify after any selected Repair/Fast-forward work,
   serializing one common directory and using two workers only across independent targets.
   Persist bounded recommendation/AWA/retention/override/command/residue events and render
   them as an expandable in-app live log.
10. **One bounded optional PR transport.** Lifecycle purpose inventory may invoke only an
   identity-verified `gh` executable from approved absolute locations through a dedicated,
   no-shell read-only adapter. Its closed grammar is one `gh pr list` query for normalized
   owner/repository and exact head branch with a fixed field list, timeout, output cap,
   cancellation, cache, concurrency bound, and redaction. Missing CLI/auth/network makes
   PR purpose Unavailable and never blocks Git maintenance.

`~/dev` is a normal writable `KleinPerkins/dev` repository for Dev Main Sync. AWA's
separate rule excluding the umbrella from agent worktree creation remains intact and is
not imported as a Dev Main Sync update ban. A selected `~/dev` fast-forward is the final
mutation in a batch; the batch ends and requires fresh discovery if that update changes
policy or configuration authority.

The implementation plan is
[`../plans/dev-main-sync-global-capability-v2.md`](../plans/dev-main-sync-global-capability-v2.md).

## Why

### Current evidence

Read-only discovery against current source and host state on 2026-09-09 found:

- 49 physical clone rows but only 43 normalized GitHub repositories;
- five duplicate-origin groups accounting for six surplus top-level rows;
- a corrected logical policy split of 26 writable, 2 protected, and 15
  reference repositories (`~/dev` moved from the tentative protected count to writable);
- current product output of 6 selectable and 43 blocked rows, including 17 blocked by
  external-worktree placement and 6 by broad hook detection;
- remote defaults of 37 `main`, 4 `master`, 1 `develop`, and 1 `next`; and
- after using those real defaults, 25 Equal, 23 Behind, 0 Ahead, 0 Diverged, and
  1 Unavailable local relation.

The current source confirms that `RepositoryCandidate` carries origin identity, one clone
path, common-directory identity, linked worktrees, cached `origin/main` relation, update
target, and one clone-wide `blockedReason`. Discovery deduplicates common-directory
identity rather than normalized origin. Selection and worker admission are path-keyed.
The transaction hard-codes `refs/heads/main`, `refs/remotes/origin/main`, and a primary
checkout attached to `main`. Any non-Cursor external linked worktree and broad hook marker
can block that whole candidate.

The supplied selection-window screenshots and repository-model canvas were accessible and
match the live/source evidence. No inaccessible ideal screenshot was used as authority. The
operator directly reports recurring AWA problems, unclear old-worktree provenance, and disk use
approaching 100 GB; this documentation lane did not inspect or mutate that live cleanup state.

The installed app is healthy and running at Skills source
`851fd05fc6ad16b8b1fba6906cf99a7784650aba`; live `origin/main` is
`63cca5ece62686fa3d9c0b589d31257bd6e0ce39`. Draft PR #192 remains at
`7b08e19cd13bc8f86b7ff7fe331dd12a7a26e9ea`. These are evidence snapshots, not
authorization to update the installation or resume that PR.

### Product value

The operator needs a safe local workspace lifecycle control center, not a list of physical
clones that mostly says no. It should:

- keep verified local default branches current;
- repair only known recoverable metadata states;
- show what feature work exists and why;
- recommend protection/recovery by default while keeping deliberate local feature removal
  available with truthful override consequences; and
- make every safety decision understandable before and after execution.

Separating remote repository, clone, worktree, branch, pull-request purpose, update target,
and operation makes that value possible while preserving exact Git identity/claim guards,
process boundaries, hard exclusions, installation safety, and agent-governance policy. It
intentionally removes AWA refusal as authorization authority only for the shipped utility's
direct human-runtime cleanup path.

### Alternatives rejected

1. **Patch the current blocker list.** Allowing more worktree roots or hook fingerprints
   would leave clone-as-repository identity, hard-coded `main`, duplicate cards,
   path-keyed selection, and clone-wide eligibility intact.
2. **Infer a canonical clone.** Choosing by path convention, recency, cleanliness, active
   branch, or current relation can silently update the wrong independent clone. Authority
   must be explicit.
3. **Build a general Git repair and cleanup engine.** Dirty-state repair, divergence
   resolution, object repair, remote deletion, broad lock cleanup, and automated stale
   deletion add risk without current operator value.
4. **Use AWA refusal as a runtime deletion veto.** AWA continues to protect agent mutations and
   remains the preferred adapter for its managed worktrees, but the native utility's explicit
   human-runtime removal path cannot be vetoed by stale/unavailable AWA state. cpp keeps its
   repository-owned workflow; neither AWA nor cpp becomes the product owner.

## Consequences

### Positive

- Duplicate local clones become context under one stable repository identity.
- Actual remote defaults work without special-case branch registries.
- An unrelated feature worktree no longer blocks a verified default-branch target.
- Safety refusals are local to the operation that depends on missing evidence.
- Repair and removal have closed evidence/action matrices rather than generic “fix” or “clean”
  behavior.
- Squash-merged or dirty local work defaults to restore-proven retention, while a deliberate
  operator override remains available with exact consequence copy.
- AWA signals remain visible and its normal cleanup stays preferred without allowing stale AWA
  state to create permanent cleanup pile-up.
- `~/dev` can be maintained without weakening AWA's separate agent-worktree policy.
- Progress, cancellation, and recovery are inspectable in the app without exposing raw
  environment or credentials.

### Negative

- The model and UI gain real entities for clones, worktrees, branches, PR associations,
  operations, and events.
- Canonical-root choices and retention artifacts become durable state that installation
  and uninstall compatibility must handle safely beginning in the body that creates them.
- PR purpose inventory needs read-only GitHub access; failure must degrade to
  `Unavailable` without blocking Git maintenance.
- A human can deliberately remove work despite dirty/active/AWA/data-loss warnings. The product
  must make that consequence unmistakable, retain by default, and record external authorization
  without presenting the action as safe or AWA-approved.
- Two independent workers require per-common-directory serialization and deterministic
  cancellation/recovery evidence.

### Supersession and compatibility

ADR 0003 remains immutable historical evidence. This ADR retains and reasserts its
source-owning global capability, one native app, Skills/WF1 ownership, no downstream
payload, source-built installation, runnerless verification, and no-paid-runner decisions.
It supersedes ADR 0003's v1 operational assumptions: clone-as-repository rows,
hard-coded `main`, primary-checkout-only updates, Cursor-location eligibility, broad hook
blocking, serial clone-wide eligibility, and no repair/inventory/removal lifecycle.

The accepted v1 plan remains immutable historical evidence; this accepted v2 plan owns
implementation order, migration, and acceptance. Existing v1
logs/reports remain readable; v2 does not rewrite them. Each independently deployable body
may install only from its exact clean merged `origin/main`; the final gate revalidates the
complete product.

### Non-goals

- accessibility expansion beyond the currently shipped baseline;
- GitHub check-status inventory;
- remote branch deletion;
- general Git repair or divergence resolution;
- paid or hosted runners;
- PR-controller, reviewer-App, or VPS changes;
- cpp workflow changes;
- chaos-scheduler mutation;
- broad cleanup automation or age-based deletion; and
- installation from a dirty branch, linked worktree, or unmerged revision.

## Approval boundary

Operator approval of this ADR and its linked plan was recorded on 2026-09-09 as the one
checkpoint before implementation. It authorizes the planned implementation bodies only after the
preserved PR #192 body is finished through its existing Draft PR, ordinary reviewer-App delivery,
and installation of each production step from exact clean merged `origin/main`. It does
not authorize cleanup of a real operator branch/worktree: every destructive batch still
requires fresh item selection and explicit confirmation. It does not authorize direct
merge, auto-merge arming, controller changes, or installation from unmerged/dirty source.
