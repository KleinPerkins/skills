# Dev Main Sync — repository lifecycle control center execution plan

**Version:** v2
**Status:** ACCEPTED — 2026-09-09
**Date:** 2026-09-09
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Supersedes:** [Dev Main Sync global tool capability execution plan v1](dev-main-sync-global-capability-v1.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Review state:** operator-approved at semantic head `2eb0f343937b881a29eb4f7eebf45ec8b664b655`;
this transition changes only lifecycle metadata and the approved action label below.

**Primary product actions:** **Fast-forward**, **Repair**, **Cleanup**. Combined batches execute
**Repair → Fast-forward → Cleanup**.

**Goal:** Turn the shipped native utility into a safe local workspace lifecycle control center
that groups physical Git state under one logical repository, keeps verified remote-default
branches current, repairs only closed recoverable states, explains feature-work purpose, and
retires proven-complete local state without data loss.

**Architecture:** Keep the accepted source-owning Flavor-1 global capability and installed native
app. Replace `RepositoryCandidate` as the product aggregate with explicit remote, clone,
worktree, branch, PR association, update-target, card, operation, and event entities. Safety
belongs to an exact operation/target; immutable Git identities and compare-and-swap guards bind
every mutation.

---

## 0. Authority, checkpoint, and body order

This v2 plan succeeds, without editing, the accepted v1 plan. ADR 0003 and plan v1 remain
byte-identical historical evidence. ADR 0004 reaffirms global capability ownership and supersedes
only the v1 product model and operational assumptions named below; ADR 0004 and this accepted plan
are the active authorities.

The operator approved this plan's single pre-implementation checkpoint—the ADR/plan and repair/
removal matrices—on 2026-09-09. Approval authorizes the fixed implementation bodies, ordinary
reviewer-App
delivery, and installation of each independently deployable production step only from exact clean
merged `origin/main`. It never authorizes cleanup of real operator work: each destructive batch
still requires fresh item selection and explicit confirmation. It authorizes no direct merge,
auto-merge arming, dirty/unmerged install, or PR-controller action.

Post-approval delivery order is fixed:

0. **Finish preserved PR #192** without mixing v2 work into it.
1. **Body 1 — corrected installed vertical slice:** logical grouping, bounded first-launch canonical
   onboarding, explicit authority plus its lifecycle compatibility, actual remote defaults,
   target-scoped checked-out fast-forward, corrected repository-card UI, plain refusal copy,
   focused production verification, and exact merged-main installation acceptance.
2. **Body 2 — approved repair and inventory preview:** the approved repair/initialization rows,
   branch/worktree/PR inventory through the closed optional `gh` adapter, deterministic
   activity/purpose state, and removal-safety preview. No cleanup.
3. **Body 3 — operator-authorized cleanup and execution control:** closed Worktree/Branch
   recommendations, protected recovery artifacts, preferred AWA cleanup plus visible operator
   override, exact Git ordinary/force/CAS paths, the batch DAG, two-worker scheduling, progress,
   structured events, cancellation, and recovery.
4. **Body 4 — only remaining necessary ref-only/compatibility work:** ref-only fast-forward for an
   existing default branch not checked out anywhere, v1 log/report decoding, retention-state
   compatibility, and any compatibility work proven necessary by Bodies 1–3.
5. **Merged-main acceptance:** after every required body is merged, verify and install only exact
   clean `origin/main`. This is a release gate, not another implementation body.

No body may absorb speculative follow-on work merely because a nearby abstraction could support
it.

## 1. Product value and scope

### 1.1 Operator value

Dev Main Sync v2 SHALL provide one legible local workspace control center that:

- keeps verified local default branches current without switching or discarding work;
- repairs only known recoverable metadata states whose exact action and refusal boundary are
  decided in this plan;
- shows feature branches, worktrees, clone association, PR purpose, and activity as context;
- recommends protection/removal separately from permission, preserves local state by default, and
  lets the human deliberately override with truthful loss/disruption warnings; and
- exposes what ran, what refused, why, and what remains recoverable.

### 1.2 In scope

- one normalized GitHub repository card with nested independent clones/common directories;
- explicit branch-to-worktree and branch-to-PR associations;
- one app-owned canonical local root per writable logical repository, with one bounded first-launch
  confirmation for unambiguous single-writable-clone cards;
- actual remote-default resolution from the selected origin;
- checked-out and ref-only default-branch fast-forward with exact OID guards;
- four closed repair/initialization decisions in §6;
- read-only local branch/worktree/PR inventory through one closed optional `gh` adapter,
  deterministic purpose mapping, and centralized activity bands;
- direct operator-selected local feature worktree/branch removal with protective recommendations,
  restore-proven retention, explicit override risk, and no remote/default/no-touch cleanup;
- per-operation eligibility, preview, dependency execution, cancellation, and recovery;
- compact repository cards, scoped warnings, state icons plus text, and expandable live events;
- migration from current candidate/log/report state without rewriting old evidence; and
- focused local macOS verification plus the existing governed Draft-PR/reviewer-App path.

### 1.3 Non-goals

- accessibility expansion beyond the currently shipped baseline;
- GitHub check/status-check inventory or CI conclusions;
- remote branch deletion;
- general Git repair, dirty-state repair, divergence resolution, rebase, reset, checkout/switch,
  stash, clean, branch-OID force update, object repair, or auth repair; §8's exact local worktree
  force removal is the only force-capable exception;
- paid runners, hosted runners, or a new service;
- PR-controller, reviewer-App, VPS, or fleet configuration changes;
- cpp workflow or bootstrap changes;
- any chaos-scheduler mutation;
- broad/automatic cleanup, scheduled cleanup, or age-based deletion;
- telemetry, analytics, database, backend, plugin framework, or historical dashboard; and
- installation from a linked worktree, dirty tree, branch head, or unmerged revision.

## 2. Revalidated evidence and current delta

### 2.1 Evidence ledger

All observations below are read-only and dated 2026-09-09 unless a revision is explicit.

| ID | Evidence | Revalidated fact | Design consequence |
|---|---|---|---|
| E-01 | `KleinPerkins/skills` remote and clean documentation worktree | GitHub default is `main`; live `origin/main` and the v2 docs base are `63cca5ece62686fa3d9c0b589d31257bd6e0ce39`. PR #190 merged as `851fd05`; PR #191 merged as `63cca5e`. | This plan is based on exact current main, not PR #192 or a stale local primary. |
| E-02 | Current `RepositoryDiscovery` practical live projection | 49 physical rows: 6 eligible and 43 blocked. Block reasons: 17 external worktree, 6 hook, 15 reference, 3 policy-excluded physical clones, 1 missing local `main`, 1 unsafe topology. | Current eligibility measures whole physical clones and produces mostly false product blockers. |
| E-03 | Normalized live origins | 43 logical repositories. Five origins have independent duplicate clones, producing six surplus rows: `ai-analytics-context` (3), `awa` (2), `chaos-scheduler` (2), `duggan-bach-source` (2), and `kp-mcp` (2). | Group top-level by normalized origin; retain every physical clone beneath it. |
| E-04 | Live policy classification, corrected for `~/dev` | 26 writable logical repositories, 2 protected (`affirm/card-platform-product`, `kleinperkins/chaos-scheduler`), and 15 reference. The earlier 25/3/15 hypothesis treated `~/dev` as protected; it is writable for this product. | Preserve cpp/no-touch/reference policy while removing the imported umbrella ban. |
| E-05 | Read-only GitHub repository metadata for all 43 origins | Remote defaults: 37 `main`, 4 `master` (`affirm/all-the-things`, `affirm/mlops`, `affirm/snowflake-permission-specs`, `affirm/web-style-guide`), 1 `develop` (`affirm/web-ux`), 1 `next` (`open-gsd/gsd-core`); none unavailable. | Resolve symbolic remote `HEAD`; no branch-name registry or `main` fallback. |
| E-06 | Direct local/default tracking-ref comparison | Current hard-coded-`main` view is 20 Equal, 23 Behind, 6 Unavailable. Using actual defaults is 25 Equal, 23 Behind, 0 Ahead, 0 Diverged, 1 Unavailable; only `open-gsd/gsd-core` lacks local `next`. | The supplied 25/23/0/0/1 clue remains correct only after actual-default resolution. |
| E-07 | `Models.swift`, `RepositoryDiscovery.swift`, `LocalRepositoryInspection.swift`, `GitTransaction.swift` | `RepositoryCandidate` conflates origin, physical clone, primary checkout, linked topology, cached relation, update target, and clone-wide block. Discovery deduplicates common-directory identity; selection/admission key by path; fetch/update hard-code `main`; the primary must be on `main`. | Replace the aggregate and path-keyed action model; preserve low-level identity guards. |
| E-08 | `RepositoryPolicy.swift` plus live blocker inspection | Marker-only `.pre-commit-config.yaml` blocks two repositories with no installed hooks. Valid/dangling pre-commit chains and a Husky path also block whole clones regardless of selected command. | Marker presence is a product defect, not repository repair. Run applicable hooks normally and react only to actual veto/residue. |
| E-09 | Installed bundle, launchd, lifecycle doctor | App `0.1.0` is signed, healthy, loaded, and running from source `851fd05`; current source main is one commit newer (`63cca5e`, a practical artifact-policy test correction). | No planning-lane install/update. Each independently deployable body installs only from exact clean merged main. |
| E-10 | PR and host-policy state | PR #192 is Draft/Open at `7b08e19`; `KleinPerkins/dev` local/remote main is `6464a09`; host-policy PR #352 is merged. Its manual one-PR squash merge is not standing authority. | Preserve PR #192; consume host policy read-only; use ordinary reviewer-App delivery. |
| E-11 | Supplied screenshots and `dev-main-sync-repository-model.canvas.tsx` | Both screenshots and the proposed model canvas were accessible. The warning/row boundary is visually weak and duplicate origins appear as peer rows. No unavailable ideal screenshot was treated as evidence. | Use one bounded card per origin with warnings and controls inside their owner. |
| E-12 | `RunLog.swift` and `Coordinator.swift` | v1 already has private line-framed redacted events, checkpoints, cancellation, and a serial coordinator, but truncates one latest log and lacks operation/worker/DAG semantics and an in-app live log. | Evolve existing safety primitives; do not replace them with a database or history service. |
| E-13 | Documentation governance | ADR 0003 and plan v1 are accepted/frozen. Successors and mutable indexes are the required route. `doc-warden` v1 compatibility `check` accepts a repository path; the generated slug example is not path-resolvable from this worktree. | Add ADR 0004 and plan v2; change only the two required index rows/additions; run the check with the exact absolute worktree path. |
| E-14 | AWA kernel cleanup and retention source | `clean` detects ignored files, but its `--bundle` artifact is ordinary, secret-filtered by default, and eligible for seven-day/pressure retention; AWA refusal/liveness governs agent cleanup. Protected Retain is separate and explicit. | Treat AWA as read-only provenance/liveness/recommendation plus preferred adapter. The shipped utility's direct human-selected override uses its own Git path, never edits AWA state, and never claims AWA approved it. |
| E-15 | Installed GitHub CLI and v1 process boundary | `/opt/homebrew/bin/gh` resolves to a stable regular executable; installed `gh 2.97.0` successfully returns the bounded PR fields needed by §7.3. Current `DescriptorProcessRunner` admits only `/usr/bin/git`, and M6 rejects in-process network clients/dependencies. | Add one separate identity-verified, no-shell, read-only `gh pr list` adapter in Body 2; retain the ban on `URLSession`, `curl`, `wget`, arbitrary gh/API execution, and check inventory. |
| E-16 | Disposable local Git fixture | Git admitted two forced worktrees claiming one branch; `branch -d` refused that claimed branch, while `update-ref -d` deleted its ref and left both symbolic claims dangling. Non-force `worktree remove` deleted an ignored file/root. A second missing root changed the prune dry-run set. Fixture was removed. | Store all claims; make an immediate empty-set check mandatory before CAS; use explicit operator-authorized force-capable Git removal for local file state; hold the lock across final prune dry-run/action. |
| E-17 | Direct operator correction (2026-09-09) | Recurring AWA problems have produced a large pile-up of old worktrees with unclear provenance and reported disk use approaching 100 GB. This planning lane did not inspect or mutate that live state. | Default to protection/recovery, but make deliberate human choice final in the shipped utility; AWA advice/refusal cannot create a permanent runtime veto. |

### 2.2 Exact built-versus-gap delta

| Capability | Built on current main | v2 gap |
|---|---|---|
| Product ownership/install | One source-owning native global tool, signed bundle, launchd lifecycle, doctor, rollback, private state | Preserve; Body 1 adds canonical-authority lifecycle compatibility and is installed from exact merged main; later bodies add only their state |
| Discovery | Bounded `~/dev` scan, physical no-follow checks, common-dir dedup, artifact/reference/policy visibility | Group common directories under normalized origins; model branches/worktrees explicitly; make `~/dev` writable |
| Identity | Credential-free GitHub identity and raw/effective-origin parity | Make normalized origin the top-level key and canonical-root choice explicit |
| Defaults/relations | Cached `origin/main`; hard-coded local/remote `main` | Resolve remote `HEAD`; use dynamic local/remote refs and exact ahead/behind counts |
| Eligibility | One clone-wide `blockedReason`; primary-path selection | Per-operation, per-target evidence/refusal; ambiguity disables only dependent controls |
| Worktrees | Registered topology captured; non-Cursor external roots broadly block | Treat location/feature dirtiness as context unless the worktree claims/might claim the default or is the removal target |
| Hooks | Broad marker/fingerprint admission block | Let Git resolve/run applicable hooks; scope actual veto/residue to the triggering operation |
| Update | Captured fetch target, FF-only checked-out primary `main`, postflight, no banned commands | Checked-out actual-default target in any verified worktree; later ref-only CAS |
| Repair | None | Two approved Git-owned worktree metadata repairs plus one explicit default initialization; one cosmetic rejection |
| Purpose inventory | Clone path, branch gate, relation only | Branch/worktree/clone/upstream/commit/PR/activity/purpose inventory plus separate removal recommendation/permission through one bounded optional `gh` adapter |
| Cleanup | No target-repository cleanup | Operator-selected non-default feature worktree then branch removal; four recommendation classes; restore-proven files/history; preferred AWA path plus explicit native Git override; remote/default/no-touch exclusions |
| Execution | Deterministic serial rows and cancellation | Dependency DAG, same-common-dir serialization, two independent workers, localized skip/continue/pause |
| UI | Flat rows, eligible/blocked count, Select All, progress/report | Bounded cards; distinct Worktree/Branch type visuals; recommendation badges; visible override/dependencies; Recommended-only cleanup Select All; nested live log |
| Events | Private redacted v1 line records for one run | v2 recommendation/AWA/retention/override/command/residue plus operation/worker/status fields, exact final counts, in-app expansion, v1 compatibility |

## 3. Frozen safety and governance constraints

- Keep ADR 0003's source-owning Flavor-1 capability, one app, no downstream payload, no new
  repository, no new installer channel, no paid runner, and no cpp-specific global bytes.
- Preserve the current closed Git environment, descriptor/open identity checks, raw/effective
  origin parity, no-replace-object behavior, no submodule recursion, captured fetch target,
  process ownership, inherited operation lease, private state/log modes, cancellation, redaction,
  install rollback, and source attestation unless this plan explicitly narrows or extends them.
- Never suppress a hook with `--no-verify`; never reset, pull, rebase, stash, clean, switch,
  checkout, force-update a ref OID, push, force-push, or delete a remote branch. Only §8's explicit
  human-confirmed local worktree removal admits Git `--force`; it never weakens ref/remote rules.
- `chaos-scheduler` remains permanent no-touch. `affirm/card-platform-product` remains under its
  repository-owned workflow. Reference clones remain read-only and receive zero action controls.
- Hidden declared artifact paths remain omitted before repository Git inspection.
- AWA continues to govern agent mutations and remains the preferred cleanup adapter for AWA-managed
  worktrees. At shipped native-utility runtime, its database/lease/heartbeat/provenance/refusal is
  read-only recommendation evidence, not authorization authority over a human's explicit local
  feature-removal choice. Dev Main Sync never edits or clears AWA state, never claims AWA approved an
  override, and surfaces stale AWA bookkeeping after external removal. This exception does not apply
  to implementation/testing agents or any other shell/tool workflow.
- Freeze the policy/config digest for each preview. Revalidate it at operation admission. If it
  changes unexpectedly, refuse dependent operations and require fresh discovery.
- A `~/dev` fast-forward is the final possible mutation in a batch. No later operation uses policy
  bytes that it may have changed.
- GitHub PR inventory is optional, read-only, and non-authoritative for fast-forward safety. Only
  the closed §7.3 local `gh` adapter may access GitHub; missing executable/auth/network never blocks
  a safely verified default update.
- Every real mutation remains explicit and selected. Recommendation never equals permission: no age,
  PR state, AWA signal, card category, or icon auto-selects repair/removal, while an advisory Keep or
  AWA refusal never hides the operator-override path for an otherwise in-scope local feature item.

### 3.1 v1 behaviors explicitly retired upon v2 acceptance/delivery

- clone-as-repository top-level rows;
- hard-coded `main` refs, copy, and result names;
- Cursor-managed location as an eligibility rule;
- unrelated worktree placement, dirtiness, detached state, or branch as a clone-wide blocker;
- broad hook-marker/framework presence as an admission blocker;
- one monolithic clone/card `isEligible` boolean;
- duplicate top-level cards for one normalized origin;
- reference repositories in blocked counts or Select All;
- AWA's umbrella worktree exclusion imported as a `~/dev` update ban; and
- branch age or PR state as removal authorization.

Compatibility decoders may name these legacy states but cannot create a v2 operation from them.

## 4. Domain model and identity

### 4.1 Required entities

| Entity | Stable identity and required fields | Responsibility |
|---|---|---|
| `RemoteRepository` | normalized lower-case `owner/repository`; credential-free validated origins; policy category; resolved default ref/name/OID/time | Top-level logical repository and remote truth |
| `LocalClone` | physical primary root; Git/common-directory device+inode; raw/effective origin; policy disposition; clone kind; all worktrees | One independent clone/common-directory under the remote |
| `Worktree` | physical path/root/registration identity; clone association; attached/detached claim; tracked/index/untracked/ignored state; AWA/provenance/liveness signals; recommendation; operator-override selection | Explicit physical checkout/removal target; warning signals never erase an in-scope feature control |
| `Branch` | full local ref; tip OID; clone association; upstream/ref OID; relation to resolved default; commit date; claiming worktree IDs (zero-to-many); recommendation; override selection | Local feature/default state at one exact ref; claims remain explicit dependencies |
| `PullRequestAssociation` | strict remote owner/repository + head owner/repository + head branch + observed head OID; number/link/state/draft/update time | Read-only purpose evidence; zero or multiple records stay explicit |
| `DefaultBranchUpdateTarget` | remote repository; canonical clone; resolved default ref; expected local/fetched OIDs; checked-out worktree or ref-only mode | Exact fast-forward authority and mutation grain |
| `RepositoryCard` | one remote identity; canonical authority state; nested clones/worktrees/branches/PRs; operation summaries | Presentation aggregate only; owns no safety boolean |
| `PlannedOperation` | operation ID/type; target identities; dependencies; recommendation; retention plan/result; AWA signal; ordinary/override permission; evidence digest; consequence copy; status | Sole owner of action state; recommendation and permission are separate |
| `RunEvent` | schema/run/sequence/time/repository/operation/phase/worker/status/detail/duration | Append-only bounded execution/recovery evidence |

### 4.2 Grouping and association invariants

1. Parse only supported credential-free GitHub SSH/HTTPS origins after raw/effective identity parity.
2. Group top-level by normalized `owner/repository`, case-insensitive for comparison and stable in
   lower case. Preserve provider display casing only as non-authoritative presentation.
3. Within one remote, group physical representations by common-directory device/inode. Independent
   clones remain separate `LocalClone` records even when paths or branch names match.
4. Associate each worktree to exactly one common directory by verified registration/backlink and
   physical identity. Unknown, stale, or contradictory association is retained as scoped warning.
5. Associate every verified worktree whose `HEAD` claims an exact full local branch ref. A branch
   stores the complete zero-to-many set of claiming worktree IDs; forced/abnormal duplicate claims
   remain explicit rather than being collapsed to one optional claim. Detached HEAD is explicit,
   never guessed from a commit match.
6. A branch may have zero, one, or multiple PR records. Do not collapse multiple PRs into one state.
7. A `RepositoryCard` contains all observed clones. A reference-only card is never “blocked”; it is
   read-only context in the collapsed Reference section.

### 4.3 Explicit canonical-root authority

The app owns one private regular `0600` file in the existing state directory:
`repository-authorities.json` (`dev-main-sync-repository-authorities/v1`). It contains only sorted
records of normalized remote identity, operator-selected physical primary root, last observed
common-directory identity, and update timestamp. It contains no credential or repository content.
The app—not the operator—writes it through descriptor-relative, no-follow, same-directory atomic
replacement after an explicit **Use as canonical root** confirmation.

A declaration is usable only when the path still exists and the live root/common directory,
origin, policy category, owner/mode, and normalized identity match. The observed device/inode is a
drift detector, not authority by itself. If one remote has:

- one declared, matching writable clone: target-dependent controls use it;
- no declaration and exactly one writable clone: include the card in §4.4 bulk onboarding and keep
  dependent operations disabled until that confirmation is committed;
- no declaration and multiple writable clones: show **Choose canonical root** inside that card and
  keep dependent operations disabled until one root is individually confirmed;
- a declaration that no longer matches: show every candidate and **Canonical root needs review**;
- only protected/reference clones: expose no canonical action; or
- ambiguous/unknown origin or common-directory identity: preserve the card with scoped warnings
  and disable only dependent actions.

No path priority, current branch, relation, modification time, PR recency, or “primary checkout”
automatically selects authority.

### 4.4 Bounded first-launch authority onboarding — Body 1

When v2 starts with no usable authority records, show one app-operated **Confirm canonical roots**
panel before the normal operation preview. It lists normalized owner/repository plus the full
candidate root for every writable card having exactly one writable `LocalClone`. Nothing is hidden:
the operator may deselect any row, cancel, or confirm the displayed set. Confirmation performs one
validated atomic authority-file replacement containing only the selected still-matching roots.

Cards with zero or multiple writable clones are excluded from this bulk set and remain visible with
per-card **Choose canonical root** controls. A stale prior declaration is never silently replaced.
The PM never edits JSON or infrastructure manually; the native app owns all writes and invokes no agent. The normal
**Select All** control remains operation-only: it cannot invoke onboarding, select a canonical root,
or broaden a prior confirmation. After confirmation or cancellation, rediscover and derive update
eligibility only from persisted, revalidated authority records.

## 5. Actual-default and fast-forward contract

### 5.1 Remote-default resolution

For the canonical clone, through the existing closed environment and effective transport checks:

1. Revalidate policy, root/common-directory identity, raw/effective origin, config contributors,
   replacements/grafts/alternates, and active operation state.
2. Run bounded `git ls-remote --symref origin HEAD` and require exactly one symbolic
   `ref: refs/heads/<D>\tHEAD` plus one valid commit OID for `HEAD`. A detached/missing/ambiguous
   remote `HEAD` is `Unavailable`; never fall back to `main` or a local `origin/HEAD`.
3. Validate `<D>` with Git ref syntax and materialize exact refs
   `refs/heads/<D>` and `refs/remotes/origin/<D>`.
4. Store the branch name/OID/time only in the discovery snapshot. Re-resolve at operation admission;
   a changed default invalidates that operation preview and requires re-inspection.

No GitHub API/default-metadata transport is added. The selected origin's symbolic remote `HEAD` is
the only default-branch authority; §7.3's optional gh adapter is PR-purpose-only.

### 5.2 Exact fetch

After the same transport/config/identity gates, invoke with separate arguments:

```text
/usr/bin/git --no-replace-objects fetch --porcelain --verbose
  --no-write-fetch-head --no-tags --no-prune --no-recurse-submodules
  --no-auto-maintenance origin
  refs/heads/<D>:refs/remotes/origin/<D>
```

The existing process runner supplies the verified worktree descriptor, closed environment,
`/dev/null` input, no-replace-object behavior, timeouts, operation lease, and captured output.
Require one exact reported remote-tracking target and freeze its OID. The command must not update
`FETCH_HEAD`, fetch tags, prune refs, recurse into submodules, or start maintenance. Never add a
leading `+` refspec.

### 5.3 Relation and branch-claim recheck

After fetch, reopen/revalidate every worktree registration in the canonical common directory and
map each branch to its complete zero-to-many claiming-worktree ID set. Let local default OID be `L`
and captured target be `T`:

- `L == T`: Equal; no mutation.
- `L` ancestor of `T`: Behind; eligible for one target mode below.
- `T` ancestor of `L`: Ahead; refuse mutation with local-commit copy.
- neither ancestor: Diverged; refuse mutation with manual-reconciliation copy.
- local default absent: only the separate initialization operation in R-04 may create it.
- any unknown default claim, default claim-set size greater than one, changed ref, changed
  registration, or operation/lock drift: refuse this fast-forward and preserve all state.

### 5.4 Checked-out target mode — Body 1

When exactly one verified worktree in the canonical clone is attached to `refs/heads/<D>`:

- that worktree, not “the primary,” is the update target;
- its path category alone is context; positive active-use evidence, unsafe identity, dirty tracked
  or untracked state, hidden index state, active operation, or uncertain claim refuses the update;
- unrelated feature worktrees may be dirty, external, Cursor-managed, AWA-managed, or detached
  without blocking this target;
- under the common-directory operation lock, immediately before mutation re-enumerate every claim
  and require the default claim set to equal exactly this target worktree plus unchanged
  common/worktree/ref identity and `L`;
- run `git --no-replace-objects merge --ff-only --no-overwrite-ignore --no-autostash T` from the
  verified target descriptor; and
- reverify default ref `== T`, branch claim, worktree cleanliness, topology, policy, config, and
  operation-relevant hook residue. A moved ref with ambiguous residue is Needs Attention, never
  rolled back.

### 5.5 Ref-only target mode — Body 4

When the complete claim set for `refs/heads/<D>` is empty, the local ref exists at expected `L`, and
relation is Behind, hold the common-directory operation lock, immediately re-enumerate every claim,
require the set still empty, then run:

```text
/usr/bin/git --git-dir=<verified-common-dir> update-ref
  refs/heads/<D> <T> <L>
```

`<L>` is mandatory compare-and-swap authority. `update-ref` does not enforce worktree claims, so the
locked immediate empty-set check is a separate mandatory veto. A claim appearing, claim-set drift,
ref change, hook veto, lock, policy/config drift, or OID mismatch refuses with no retry. Reverify the
ref at `T` and prove no worktree acquired the branch. This mode does not touch an index or worktree.

### 5.6 Operation-relevant hooks

Remove all marker/family admission blockers. Freeze and inspect the effective hook path/config for
the exact target, but let Git invoke the hooks applicable to the selected command. In particular,
reference transactions and any post-merge/post-index hooks that Git actually invokes must run;
commit-time hooks irrelevant to a no-commit operation must not pre-block it.

A hook can affect only its triggering operation:

- a pre/reference veto is Refused with the bounded Git/hook reason and unchanged ref proof;
- a post-hook nonzero result or residue after a moved ref is Succeeded with Warning or Needs
  Attention according to verified poststate;
- unknown hook-path/config drift refuses that operation; and
- the app never disables, edits, installs, repairs, or bypasses repository hooks.

Deterministic fixtures trace the actual hook invocations for fetch, merge-ff, update-ref, worktree
prune/repair/remove, and branch deletion on the supported Apple Git version. The production rule is
“what Git invokes,” not a permanent guessed hook-name list.

## 6. Closed repair and initialization safety matrix

### 6.1 Dispositions

| ID | Candidate | Disposition | Why |
|---|---|---|---|
| R-01 | Stale/prunable non-default worktree registration | **Approved — Repair** | Git owns the metadata cleanup; an absent root contains no recoverable worktree bytes, and the branch ref remains intact. The all-prunable-set rule closes the non-path-scoped command risk. |
| R-02 | Provably moved existing non-default worktree | **Approved — Repair** | `git worktree repair <path>` is path-scoped and preserves checkout/ref contents when identity, cleanliness, branch, and inactivity are proven. |
| R-03 | Missing/stale local `origin/HEAD` | **Rejected** | v2 resolves remote `HEAD` directly and does not depend on local `origin/HEAD`; mutation would be cosmetic and adds no safety or operator value. |
| R-04 | Missing local default ref | **Approved — Initialize, not Repair** | Creating an absent ref is initialization. A verified remote default and zero-old-object CAS can create it without overwriting history or a worktree claim. |

**Deferred:** none. Core decisions are closed; states outside these rows are refusals, not future
repair promises.

### 6.2 R-01 — prune stale non-default registrations

- **Detection predicate:** in one verified common directory, a registration directory is intact and
  owned; its `gitdir` resolves to an absent worktree root (`ENOENT`, not inaccessible); its `HEAD`
  is a valid symbolic `refs/heads/<B>` where `<B> != <D>`; it is not locked; and both Git's
  `worktree prune --dry-run --expire=now --verbose` C-locale diagnostic projection and the app's
  no-follow registration inventory identify the same item. Git emits this verbose projection on
  bounded standard error; it is normalized only into registration identities already proven from
  metadata.
- **Required evidence:** common-dir and registration identities/modes; absent physical root;
  valid non-default symbolic claim; branch ref exactly at OID `H`; proof that the surviving branch
  ref preserves `H`; dry-run candidate set; policy/config digest; AWA/Cursor/ordinary ownership
  class; bounded active-use evidence.
- **Preconditions:** every registration Git would prune with `--expire=now` is explicitly selected
  and independently satisfies this row; every affected claim is attached, known, non-default, and
  backed by an unchanged surviving branch ref preserving its commits; no held common-dir/product
  lock, active Git operation, AWA lease/heartbeat, or authoritative active root; policy/config and
  preview dry-run set are unchanged.
- **Exact Git action:** acquire the shared common-directory mutation lock; repeat all registration,
  claim, ref, preservation, and activity guards; then run
  `git --git-dir=<common> worktree prune --dry-run --verbose --expire=now` under `LC_ALL=C` as the
  immediate atomic gate. Require its exact normalized set to equal the selected/proven set and,
  without releasing the lock, run exactly once
  `git --git-dir=<common> worktree prune --verbose --expire=now` under `LC_ALL=C`. Never unlink or
  edit `.git/worktrees/*` manually.
- **Expected identity/ref guards:** expected common-dir device/inode; digest of all registration
  identities and `HEAD`/`gitdir` bytes; expected branch-ref OIDs; expected dry-run output set.
- **Postconditions:** every selected registration is absent from Git's worktree list and admin
  inventory; no unselected registration changed; every branch ref/OID and the default ref are
  unchanged; no worktree path was deleted.
- **Race/refusal:** any extra/missing final dry-run item, root appearance, registration/ref/claim or
  preservation change, detached/unknown/default claim, inaccessible path, lock/activity evidence,
  hook veto, or postcondition mismatch refuses before mutation or reports Needs Attention after an
  observed partial Git action. The shared lock serializes Dev Main Sync/AWA participants, but cannot
  prevent an arbitrary external `rm` in the sub-second gap between Git's final dry-run and prune;
  Git's normal object/reflog grace and the unchanged branch ref preserve commits, and unexpected
  poststate is Needs Attention. Do not auto-retry or claim universal exclusion.
- **Operator copy:** “Repair can remove Git's stale registration for this missing non-default
  worktree. The branch and commits stay in place.” Refusal: “Repair stopped because Git would also
  prune another registration or the evidence changed. Nothing was deleted by Dev Main Sync.”
- **Positive test:** two absent non-default registrations, both selected/proven, are pruned together;
  their branch OIDs and an unrelated default worktree remain byte/OID-identical.
- **Refusal tests:** one unselected prunable item; detached/default/unknown `HEAD`; missing or moved
  branch ref/unpreserved tip; locked registration; root reappears; active AWA heartbeat; another
  registration becomes stale between preview and the locked final dry-run; registration/ref/dry-run
  drift; hook veto; post-inventory mismatch. Assert no manual metadata deletion path exists.

### 6.3 R-02 — repair a moved existing non-default worktree

- **Detection predicate:** one physical owner-controlled path exists; its `.git` marker resolves to
  a verified registration in the expected common directory; that registration's `gitdir` points to
  an absent old path while all other backlinks/`commondir`/`HEAD` identities agree; `HEAD` claims a
  valid non-default branch; and the target path is not a symlink or alternate clone.
- **Required evidence:** physical path/root identity; marker and registration bytes/identities;
  common-dir identity; branch ref/tip; clean tracked/untracked and ordinary index state via the
  explicit git-dir/work-tree view with optional locks disabled; no positive active-use evidence;
  policy/config digest and ownership class.
- **Preconditions:** non-default attached branch; exact branch OID unchanged; no dirty/untracked or
  hidden index state; no active Git operation, held common-dir/product lock, AWA lease/heartbeat, or
  authoritative active root; no unsafe owner/mode/symlink/config/object state; path not claimed by
  another registration.
- **Exact Git action:**
  `git --git-dir=<verified-common-dir> worktree repair <verified-physical-path>` with separate
  arguments. No `--force`, manual marker edit, or registration edit.
- **Expected identity/ref guards:** common/root/marker/registration identities; old absent path;
  exact non-default full ref and OID; complete worktree-registration set digest.
- **Postconditions:** `git worktree list --porcelain -z` maps the repaired path to the same
  registration/common directory and branch; both backlinks agree; root/branch/default OIDs,
  tracked/untracked/index state, and other registrations are unchanged.
- **Race/refusal:** changed/missing path, branch/default claim, dirtiness, active-use evidence,
  identity/backlink drift, another registration claim, hook veto, or postcondition mismatch refuses
  or reports Needs Attention. Never guess the moved-from path and never auto-retry.
- **Operator copy:** “Repair can reconnect this clean moved feature worktree to its existing Git
  registration. Files and branch commits will not be changed.” Refusal: “Repair stopped because
  the path, branch, activity, or Git registration could not be proven unchanged.”
- **Positive test:** physically move a clean feature worktree, prove the stale old backlink, repair
  the new path, and assert byte-identical files/index plus unchanged branch/default OIDs.
- **Refusal tests:** dirty/untracked/hidden index; detached/default/unknown branch; symlinked root;
  wrong common directory; active heartbeat/held lock; old path still present; concurrent move/ref
  change; command veto; partial/postcondition mismatch.

### 6.4 R-03 — reject local `origin/HEAD` repair

- **Detection predicate:** remote `HEAD` is verified as `<D>`, while local
  `refs/remotes/origin/HEAD` is absent, stale, or points elsewhere.
- **Required evidence:** verified remote symbolic `HEAD`, unchanged origin identity, and observed
  local symbolic-ref state solely for explanation.
- **Preconditions:** none create an operation; this row is always non-mutating.
- **Exact Git action:** **none**. Do not run `remote set-head`, `symbolic-ref`, or `update-ref` for
  local `origin/HEAD`.
- **Expected identity/ref guards:** all refs must remain unchanged during detection.
- **Postconditions:** the app uses `<D>` directly; local `origin/HEAD` remains as found.
- **Race/refusal:** remote-default drift invalidates the view and triggers re-inspection, not repair.
- **Operator copy:** “Local origin/HEAD is stale, but Dev Main Sync does not depend on it. No repair
  is needed.”
- **Positive test:** missing and stale local `origin/HEAD` still resolve/update the actual default
  through remote `HEAD`, with no local symbolic-ref mutation.
- **Refusal test:** assert no planned operation, Git mutation, control, or result code can be
  created for this state.

### 6.5 R-04 — initialize a missing local default ref

- **Detection predicate:** verified remote symbolic `HEAD` is `refs/heads/<D>` with fetched target
  `T`; `refs/heads/<D>` is absent; its complete claim set is empty with no unknown claim; the ref
  namespace has no
  file/directory conflict; and the canonical clone/common directory is otherwise safe.
- **Required evidence:** remote-default response and captured fetch OID; zero local default ref;
  complete verified worktree claims; object-format-specific zero old OID; common-dir/origin/config/
  policy identities; object `T` present as a commit.
- **Preconditions:** explicit **Initialize default branch** selection; unchanged origin/default;
  the complete default claim set is empty; no active operation, held lock, replacement/graft/
  alternate, unsafe owner/mode/symlink, hook/config drift, or conflicting ref namespace. Feature worktree dirty state
  is context unless its branch claim is unknown; the canonical common directory itself must be
  safely inspectable.
- **Exact Git action:** under the shared common-directory mutation lock, immediately re-enumerate
  all claims and require the default claim set still empty, then run
  `git --git-dir=<verified-common-dir> update-ref refs/heads/<D> <T> <zero-old-OID>` where the zero
  OID length matches the repository object format. `update-ref` does not enforce claims; this is
  initialization, never automatic repair.
- **Expected identity/ref guards:** local default absent; target `T` unchanged; complete worktree
  claim digest unchanged; common-dir/origin/default/config identities unchanged.
- **Postconditions:** local default exists exactly at `T`; the complete claim set remains empty; no
  index/path changed;
  remote-tracking ref remains `T`; relationship is Equal.
- **Race/refusal:** a new branch/worktree claim, ref creation, default/OID/config drift, lock,
  applicable hook veto, or postcondition mismatch refuses. CAS failure is terminal for that preview;
  re-inspect rather than retry.
- **Operator copy:** “Initialize can create the missing local `<D>` branch at the verified remote
  commit. No worktree will be switched.” Refusal: “Initialization stopped because the branch,
  worktree claims, or remote default changed. Existing state was preserved.”
- **Positive test:** SHA-1 and supported SHA-256 fixture repositories create the absent default at
  exact `T`, leave every worktree/index unchanged, and report Equal.
- **Refusal tests:** conflicting ref namespace; default claim appears; competing ref creation;
  remote-default/target drift; ahead/diverged substitute ref; hook veto; active lock/operation;
  replacement/graft/alternate; unsafe ownership/mode/symlink.

### 6.6 States explicitly excluded from Repair

The following create no Repair operation: dirty tracked/untracked/index state; hidden index bits;
Ahead or Diverged history; unknown/default branch claims; detached feature HEAD; object corruption,
replacement, graft, or alternate ambiguity; authentication/network failure; policy/config
unavailability; hook veto/residue; unsafe owner, mode, type, hardlink, or symlink; active Git
operations, AWA leases/heartbeats, or held product/common-dir locks; and mere existence of an
unheld lock file. The app neither deletes lock files nor turns inability to prove activity into a
repair suggestion.


## 7. Product defects, lifecycle inventory, and activity

### 7.1 Known product defects — explicitly NOT repository Repair

These states describe v1 product-model defects or ordinary context. They must never produce a
Repair control against the repository:

1. a linked worktree outside Cursor's managed location;
2. presence of a hook-framework/config marker without an operation-relevant veto;
3. macOS `/var` versus physical `/private/var` path spelling for the same verified object;
4. multiple independent clones with the same normalized origin;
5. a feature branch checked out in the primary worktree while the default is safely elsewhere or
   unclaimed;
6. hard-coded `main` when remote `HEAD` names another default;
7. cached relation drift before fresh fetch/re-inspection;
8. stale lock-alert copy after no held lock/operation remains; and
9. dirty state in an unrelated feature worktree.

The remedy is product identity, canonicalization, fresh evidence, scoped copy, or target selection—not
Git repair.

### 7.2 Branch/worktree/PR inventory contract

For every `LocalClone`, enumerate local branches and verified worktrees without checkout or mutation.
Each explicit branch/worktree row shows:

- full local branch name or Detached;
- worktree physical path, clone/common-directory association, and every current claim ID;
- tracked, untracked, ignored, hidden-index, and operation/lock state at the granularity needed by
  available actions;
- relation to the resolved default with exact ahead/behind counts;
- configured upstream plus local/upstream OIDs and relation when verifiable;
- branch tip commit date;
- zero or more PR links/numbers and state: **Draft**, **Open**, **Merged**, **Closed**,
  **Unavailable**, or **Ambiguous**;
- PR `updatedAt` for each record;
- one centralized activity band;
- a separate **Purpose** status;
- a separate Worktree/Branch **Removal recommendation** badge from §8.2; and
- a separate permission/action state: unselected, selected Recommended, selected Recovery, selected
  Operator override, dependency-blocked Branch claim, or hard-excluded.

No check/status-check inventory, merge-readiness conclusion, reviewer state, or remote deletion
control is present. Neither Purpose nor recommendation is permission.

### 7.3 Bounded optional GitHub transport — Body 2

Add one `ReadOnlyGitHubCLIAdapter`; do not widen `DescriptorProcessRunner`, whose Git-only
trampoline and repository snapshot contract remain unchanged. Discovery checks only the approved
absolute entrypoints `/opt/homebrew/bin/gh` and `/usr/local/bin/gh`, in that order. Resolve at most
one candidate, open the resolved executable no-follow, and require a regular executable owned by
root or the effective user, not group/world writable, with stable device/inode/owner/mode/size/mtime
before child admission. Bind the admitted child `ProcessIdentity` to that resolved path. Absence or
identity drift disables only PR inventory.

The adapter admits exactly this separate-argument grammar after validating normalized owner/repo and
the exact local short branch as data, never options:

```text
<verified-gh> pr list
  --repo <owner/repository>
  --head <branch>
  --state all
  --limit 100
  --json number,url,state,isDraft,headRefName,headRefOid,isCrossRepository,updatedAt,closedAt,mergedAt
```

There is no shell, `gh api`, alternate subcommand, search expression, user-provided field/filter,
write, check-status field, token argument, `URLSession`, `curl`, or `wget`. Standard input is
`/dev/null`. The closed environment uses the verified account `HOME` only for gh's existing
authenticated configuration/keychain plus `GH_PROMPT_DISABLED=1`, `NO_COLOR=1`, `CLICOLOR=0`,
`GH_PAGER=cat`, `PAGER=cat`, `LANG=C`, and `LC_ALL=C`; it never accepts `GH_TOKEN`, dumps environment, or
logs configuration. Bound each child to 15 seconds and 64 KiB per stream, at most one live gh child
globally, and one per-run cache entry per normalized repository/branch/OID. Cancellation uses the
existing verified process-group TERM/KILL/reap protocol. Limit/output truncation, malformed JSON,
missing executable, unsupported fields, authentication/rate/network failure, timeout, or cancellation
returns **PR status unavailable** and never blocks fast-forward.

Installed `gh 2.97.0` was read-only proven to support this exact command and field set. M6's
production audit changes from “no network client executable” to “only `/usr/bin/git` plus this
identity-verified closed gh adapter”: it still requires no in-process network framework/client,
`curl`, `wget`, broad executable runner, arbitrary gh grammar, token argument/logging, or dependency.

### 7.4 Strict association and deterministic purpose

An **Exact** association requires exactly one returned record where:

1. the `--repo` owner/name equals the `RemoteRepository` identity;
2. `isCrossRepository == false` (fork heads are never Exact);
3. `headRefName` equals the exact local short branch; and
4. `headRefOid` equals the branch's current exact tip OID.

Retain every candidate record in the row. A same-name record with another OID is **Superseded**
when it is the sole related record; a fork, multiple records, malformed identity, or contradictory
result is **Ambiguous**. Association quality and Purpose are recomputed whenever the local tip or
cached query key changes.

The closed Purpose oracle, evaluated in this order, is:

1. more than one candidate record, any fork/cross-repository candidate, or contradictory identity →
   **Ambiguous**;
2. exactly one Exact record with `isDraft == true` or `state == OPEN` → **Active**;
3. exactly one Exact record with `state == MERGED` and non-null `mergedAt` → **Completed** for this
   exact current tip through PR evidence;
4. current tip independently proven ancestor of the fetched default → **Integrated** without
   changing or claiming any PR association;
5. exactly one Exact record with `state == CLOSED`, null `mergedAt`, and non-null `closedAt` →
   **Closed incomplete**;
6. one same-name/OID-different record and no Exact record → **Superseded**;
7. successful empty lookup without default ancestry → **No known PR**; and
8. adapter unavailable/failure/truncation → **Unavailable**.

Only rule 3 may produce **Completed** from PR evidence. Neither Completed nor Integrated is a commit
preservation sink or permission by itself; §8 independently computes recommendation, recovery need,
and explicit selection. A closed table-driven oracle tests every rule, precedence edge, OID change,
multiple-record case, and GitHub failure.

### 7.5 Central activity heuristic

Calculate one function from the newest verified local commit date and exact associated PR update
date:

- **Recent:** age `<= 7` complete days;
- **Idle:** age `8–30` complete days; and
- **Stale Candidate:** age `> 30` complete days.

Unknown dates yield **Activity unavailable**. Use one captured wall-clock per discovery so all rows
share a boundary. Staleness contributes to §8 recommendation only alongside independent purpose,
identity, and preservation evidence. It never selects, authorizes, or weakens repair/removal guards.

## 8. Operator-authorized local feature removal

### 8.1 Authority, permission, and hard exclusions

Dev Main Sync's shipped native UI is a direct human-operator surface. For local feature cleanup,
the operator's explicit runtime selection and grouped final confirmation authorize the utility;
AWA does not. AWA remains read-only provenance/liveness/recommendation evidence and the preferred
worktree cleanup adapter when its normal path succeeds. An AWA refusal, stale heartbeat/lease, bad
provenance, or unavailable engine changes recommendation/copy but never hides the in-scope control.
The app never edits AWA database/lease/heartbeat state and never reports an override as AWA-approved.
After external removal it reads AWA again and presents stale bookkeeping as advisory residue.

Recommendation and permission are separate axes:

- recommendation answers **what the utility advises** from current evidence;
- permission answers **what this human explicitly selected and confirmed**;
- no recommendation auto-selects or automatically removes anything; and
- **Keep** and **Override risk** retain a visible **Remove anyway / Operator override** path.

Every verified non-default local feature Worktree and Branch receives that interaction pattern.
These targets remain outside cleanup controls, with no override in this plan:

1. a resolved local default branch or any worktree claiming/might-claim it;
2. the canonical default update target while it holds update authority;
3. `chaos-scheduler`, cpp/repository-owned workflow, reference-only, or other permanent no-touch
   repository state;
4. a remote branch/ref;
5. the running Dev Main Sync executable/process, installed app/launcher/state directory, or its
   source/install lifecycle; and
6. an arbitrary non-Git directory or path not exactly bound to a verified Git worktree registration.

A Branch with any claiming worktree is in-scope and visible but its remove action is dependency-
blocked until all claims are removed and fresh discovery proves the complete zero-to-many set empty.
This Git integrity dependency cannot be overridden because deleting the ref would dangle a live
worktree. The exception here applies only to the shipped utility's human-runtime path; every agent,
implementation test, shell command, and repository contribution remains governed by AWA/repository
policy.

### 8.2 Closed Worktree and Branch recommendation state machines

The same four badges, checkbox location, action placement, and final-confirmation mechanics apply to
both entity types. Classification is recomputed from one immutable preview and never becomes
permission by itself.

| Badge/state | Worktree recommendation predicate | Branch recommendation predicate | Visible action |
|---|---|---|---|
| **Recommended** | Non-default feature worktree; purpose fulfilled; no current-session/active/recent/AWA warning; exact clean ordinary index; no unretained local files/history; identity known | Non-default feature branch; claim set empty; purpose fulfilled; tip already preserved by verified default ancestry, exact remote branch, or completed artifact; no active/recent warning | **Remove**; strongest green recommendation; eligible for Select All |
| **Recovery copy required** | In-scope removal is reasonable, but tracked/index changes, untracked/ignored files, or unique commits require the §8.3 artifact and can be completely captured | Claim set empty and removal is reasonable, but unique local history lacks another durable sink and can be captured by §8.3 | **Remove with recovery**; never selected by Select All |
| **Keep** | Default protective state for active/recent, dirty, Draft/Open/incomplete purpose, unknown provenance, stale/active AWA heartbeat/lease, AWA refusal, or unavailable AWA evidence | Default protective state for active/recent, Draft/Open/incomplete/unknown purpose, uncertain evidence, or nonempty/unknown claim set | **Remove anyway…** remains visible; for Branch claims, show **Remove claiming worktrees first** until zero |
| **Override risk** | Confirmed preservation gap/failure/decline, current-session/active-use signal, unsafe-but-bounded provenance, or likely file/disruption loss | Claim set empty but unique history is unpreserved/declined, identity/purpose advises against removal, or disruption/data loss is likely | **Operator override…** with exact consequence text; never selected by Select All |

Apply the rows in this closed precedence: hard exclusion (outside the state machine); nonempty or
unknown Branch claims (**Keep**, dependency-blocked); known preservation failure/decline/gap
(**Override risk**); active/current-session, Recent, Draft/Open/incomplete purpose, unknown identity,
or AWA warning/refusal/unavailable (**Keep**); removal-reasonable state whose complete supported
recovery has not yet run (**Recovery copy required**); fulfilled purpose with already preserved and
clean state (**Recommended**); otherwise **Keep**. Dirty/local-file state begins at Keep unless exact
inventory proves complete §8.3 capture is supported, at which point it may become Recovery copy
required; unsupported/secret-excluded capture becomes Override risk.

Activity bands remain Recent `<=7d`, Idle `8–30d`, and Stale Candidate `>30d`. Staleness may
strengthen a recommendation only when purpose and preservation evidence independently support it;
it never grants permission. AWA active/refusal/unavailable evidence normally yields **Keep** or
**Override risk**, not an absent control. If evidence changes after preview, recompute; a newly worse
consequence than the grouped confirmation produces **Skipped — review changed risk**, not silent
escalation or a second modal in the same run.

### 8.3 Protected restore-proven recovery artifact

Before any selected **Remove with recovery**, create one app-owned artifact in the existing private
state directory:

```text
retention/<artifact-id>/
├── manifest.json
├── branch.bundle          # when a named branch/history exists
├── worktree.tar           # when worktree bytes need preservation
└── index.snapshot/        # index plus required shared-index bytes, when present
```

`manifest.json` uses `dev-main-sync-retention/v2` and records artifact ID, normalized repository,
clone/common-dir/worktree/registration identities, full branch ref and exact tip OID, object format,
entry-relative paths/types/modes/symlink targets/content SHA-256, index/status digest, included and
excluded paths, secret authorization, creation time, component hashes, restore proof, and bounded
restore instructions. It contains no credential values, file content, diff, raw environment, or
unbounded subprocess output.

Capture uses descriptor-relative, no-follow enumeration beneath the still-verified worktree. Exclude
only the `.git` administrative marker and symlink targets outside the root; include modified tracked
bytes, ordinary/staged index state, untracked files, ignored files, empty directories needed for
restore, and the branch objects needed to recreate exact `H`. Snapshot the verified index and any
required shared-index dependencies. Unknown index extensions, unreadable entries, hardlink/symlink
escape, special files, concurrent change, or incomplete enumeration fails completeness.

Because arbitrary local bytes may contain credentials, each selected Recovery row includes one
inline, pre-artifact **Include possible secrets in protected recovery copy** choice. This is not a
modal or removal confirmation; the one final grouped confirmation later repeats the resulting
included/excluded state. Without authorization, no payload bytes—branch bundle, index snapshot, or
tracked-modification/untracked/ignored worktree content—are archived; omitted history/OID and exact
relative paths are listed, secret-shaped paths are highlighted, and retention is incomplete, so the
item becomes **Override risk**. With authorization, all bounded artifact payload is included and
stays only in the private app state root: directory mode `0700`,
artifact files `0400`, no auto-expiry/pressure deletion, no logging/content preview, and no upload. Copy states that this local artifact is permission-protected, not encrypted or remote
backup.

Create components in a private same-directory incomplete slot. Verify the branch bundle, restore it
to a fresh private repository at exact `H`, restore index/worktree components, and require identical
entry manifest, file hashes/types/modes/symlink targets, index entries/flags, porcelain-v2 status
digest, and connectivity. Fsync components/manifest and atomically publish only after proof. A
failed/cancelled proof deletes only the incomplete slot, preserves any previously completed
artifact, and leaves the source untouched. Completed artifacts are durable, listable, and have exact
restore instructions; v2 adds no artifact deletion or garbage collector.

Retention runs before removal. Success records **recovery-backed** for final confirmation. Failure,
decline, excluded secrets, or any capture gap never silently continues: recommendation becomes
**Override risk**, names the exact known/unknown data at risk, and remains selectable only as an
operator override.

### 8.4 Exact Worktree runtime removal algorithm

For each selected Worktree, execute once in dependency order:

1. **Preflight.** Revalidate in-scope non-default feature classification, normalized origin, root/
   common-dir/registration device+inode, `.git` backlink, attached branch/ref/OID, full claim set,
   tracked/index/untracked/ignored manifest, policy/config, current process/install exclusions,
   recommendation, AWA snapshot, row selection, and any inline secret-recovery choice.
2. **Optional recovery.** Complete §8.3 before destructive confirmation. Failure, decline, or a gap
   reclassifies the row as **Override risk** with exact consequences; it does not remove the control.
3. **Final permission.** After every selected artifact attempt, the coordinator presents the one
   §9.1 grouped confirmation. Only rows retained and explicitly confirmed in their final class are
   admitted; cancel/deselect leaves source and completed artifacts intact. For an AWA-managed row,
   confirmation explicitly names the native fallback admitted if AWA refuses: ordinary-only for
   Recommended, one-force after complete recovery for Recovery-backed, or the displayed force level
   for Operator override.
4. **Preferred AWA attempt.** For an AWA-managed target, first invoke only its normal guarded
   `dev-worktree.sh clean --path <path>` adapter—no `--bundle`, `--delete-branch`, or `--force`—and
   record its exact bounded disposition. Success proceeds to postflight. Refusal/unavailability is
   advisory, never rewritten as success, and proceeds to the row's confirmed native fallback. An
   unselected/deselected row is **Protected/Skipped**, with override still visible on rediscovery.
5. **Immediate native gate.** Acquire the shared common-directory mutation lock. Reopen all identity
   descriptors; repeat the complete content/index/claim/process snapshot; require exact preview or
   confirmed-risk equivalence, unchanged recovery proof, and a non-default feature target. A risk
   worse than final confirmation skips for fresh review. The lock serializes Dev Main Sync/AWA
   participants, not arbitrary external writers; disclose the bounded sub-second residual.
6. **Git-supported removal.** With separate arguments and `/dev/null` input, first run
   `/usr/bin/git --git-dir=<common> worktree remove <path>`. On exact dirty/local-file refusal,
   rescan/revalidate under the same lock and run
   `/usr/bin/git --git-dir=<common> worktree remove --force <path>` only when either complete
   Recovery-backed force or Operator override was named in final confirmation. Run
   `/usr/bin/git --git-dir=<common> worktree remove --force --force <path>` only for an exact Git
   locked-worktree refusal named as Operator override. No shell, wildcard, arbitrary path, `rm`,
   branch deletion, or remote operation is admitted.
7. **Interruption.** Cancellation before child admission performs no removal and keeps completed
   recovery. After admission, use verified process-group TERM/KILL/reap, then always postflight;
   never assume rollback, auto-retry, or repeat a force command.
8. **Postflight/residue.** Independently inspect physical path, Git worktree list/admin registration,
   every ref/OID/claim, recovery artifact, and AWA read-only state. Path+registration absent and refs
   unchanged is success even if AWA bookkeeping is stale; show **Removed by external operator
   selection — AWA still reports stale state**, or **Removed by Operator override** for that class,
   with recovery guidance. Partial Git state is Needs Attention. If the
   path is absent and only a proven stale Git registration remains, offer R-01 Repair separately.

A broken-metadata case that Git cannot remove even with the admitted force level is explicitly
**Deferred last-resort cleanup**: preserve path/ref/artifact, show the exact Git residue, and do not
manually delete files or `.git/worktrees/*`. This keeps the common pile-up path practical—normal,
dirty, ignored, AWA-refused, and Git-locked worktrees are supported—without adding a blind filesystem
engine. A successor may add a narrow owned-path fallback only with a closed identity/action matrix.

### 8.5 Exact Branch runtime removal algorithm

Branch removal is always a separate, subsequently selected operation after Worktree postflight.
Render it throughout, but admit execution only after the complete claiming-worktree set is freshly
empty. Under the common-directory lock, re-enumerate all claims immediately before every command;
`update-ref` does not enforce claims, so any claim/drift refuses regardless of override.

1. Revalidate exact non-default local `refs/heads/<B>` at expected `H`, origin/common-dir, purpose,
   recommendation, sinks/recovery, AWA advisory evidence, and row selection.
2. If history needs preservation, complete §8.3 before destructive confirmation. Failure/decline
   changes the item to **Override risk** with exact potentially unreachable history.
3. Admit only the row's final class retained in the one §9.1 grouped confirmation.
4. For **Recommended** default-ancestor history with a verified default worktree, try
   `/usr/bin/git -C <default-worktree> branch -d <B>`; any refusal preserves the ref and never falls
   through unless the already confirmed matrix row explicitly admits CAS.
5. For verified default ancestry without a default worktree, an exact remote sink, a recovery-backed
   branch, or an explicitly confirmed unpreserved-history override, run only
   `/usr/bin/git --git-dir=<common> update-ref -d refs/heads/<B> <H>` after the immediate empty-claim
   gate. The override copy lists commits/history that may become unreachable.
6. Reverify local ref absent, all claims still empty, default/remote refs unchanged, and recovery
   state. Never delete/push a remote branch and never call `branch -D`.

### 8.6 Closed removal action matrix

| ID | Recommendation / permission | Exact path | Success and residue |
|---|---|---|---|
| C-01 | Worktree **Recommended**, selected | Preferred normal AWA adapter when managed; on refusal/unavailable or non-AWA target, confirmed native ordinary §8.4 path only | Path+Git registration absent; branch/refs unchanged; AWA stale state advisory only |
| C-02 | Worktree **Recovery copy required**, selected; artifact restore-proven | Publish §8.3, try preferred AWA when managed, then confirmed ordinary→single-force Recovery-backed path | Artifact remains protected; removal result and any AWA/Git residue explicit |
| C-03 | Worktree **Keep/Override risk**, explicit Operator override | Preferred AWA attempt, then exact non-force refusal and one admitted `--force` or `--force --force` path under final gate | Never called safe/AWA-approved; exact discarded or recovery-backed file/index state logged |
| C-04 | Branch **Recommended**, claims empty, selected | `branch -d` when applicable; otherwise exact expected-old CAS with verified sink | Local ref absent; commits remain in verified sink; no remote mutation |
| C-05 | Branch **Recovery copy required**, claims empty, selected; artifact restore-proven | Publish §8.3, then exact expected-old CAS | Artifact restores exact `H`; local ref absent; claims/default/remote unchanged |
| C-06 | Branch **Keep/Override risk**, claims empty, explicit history-loss override | Exact expected-old CAS only after grouped consequence confirmation | Local ref absent; report names potentially unreachable history; never implies preservation |
| C-07 | Default/canonical/no-touch/reference/remote/product/non-Git target, or Branch with claims | No cleanup command; branch claim dependency remains visible until Worktrees removed | Hard exclusion/integrity dependency stated; no override or hidden mutation |

### 8.7 Deterministic removal, recommendation, and override tests

- closed Worktree and Branch table oracles cover all four recommendation states, transitions, and
  the rule that staleness contributes to recommendation but never permission;
- AWA refusal, active/stale heartbeat/lease, bad provenance, and engine unavailable keep the control
  visible as **Remove anyway / Operator override**; none alone counts as runtime authorization or an
  infrastructure circuit-breaker failure;
- normal AWA cleanup succeeds as the preferred first path; no call includes bundle/branch/force
  flags, and Dev Main Sync never edits AWA state or labels an override AWA-approved;
- dirty tracked, staged/index, untracked, ignored, secret-shaped, special, unreadable, and concurrent
  file fixtures classify Recovery or Override risk with exact gaps;
- branch bundle plus worktree/index artifact round-trips exact `H`, file manifest, modes/symlinks,
  index flags/status, ignored/untracked bytes, and explicit authorized secret inclusion;
- retention success remains protected and restore-proven; retention failure, cancellation, decline,
  or excluded secrets leaves source untouched and exposes a truthful selectable override;
- a dirty/ignored worktree produces a non-force Git refusal, then only confirmed complete
  Recovery-backed or Operator-override permission admits one-force removal; a Git-locked fixture
  requires exact double-force grammar; no force command runs without grouped authorization;
- external removal of an AWA-managed worktree leaves simulated stale AWA bookkeeping visible as
  advisory residue while Git/path postflight reports the real outcome;
- forced duplicate claims and preview→delete races keep Branch execution blocked until all selected
  Worktrees are gone; after empty-set revalidation, a confirmed unpreserved-history override deletes
  only exact expected local `H` through CAS;
- Select All chooses only **Recommended** rows; Recovery, Keep, and Override risk require individual
  selection;
- one final confirmation renders separate **Recommended**, **Recovery-backed**, and **Operator
  override — data/disruption risk** groups with paths/refs/OIDs/artifacts/AWA signals/consequences;
- Worktree/Branch rows share checkbox/action geometry but retain distinct icon/accent/type labels;
- cancellation/failure preserves completed artifacts and reconstructs partial path/registration/ref/
  AWA residue without auto-retry; and
- production symbol/process audit proves no agent, shell, AWA-state writer, arbitrary executable,
  filesystem deletion, remote deletion, `branch -D`, reset, checkout, stash, or clean path exists.

## 9. Batch DAG, progress, events, and recovery

### 9.1 Planning and execution graph

One immutable preview expands selected controls into `PlannedOperation` nodes:

```text
Repair
  → re-inspect
  → Fast-forward
  → re-inspect
  → Create selected worktree/branch recovery artifacts
  → one grouped final removal confirmation
  → Remove worktree
  → re-inspect claims
  → Remove local branch
  → verify Git + AWA residue
```

Only individually selected/applicable nodes exist, except **Select All** selects only
**Recommended** removal rows and never Recovery/Keep/Override risk. The planner records exact entity
identities, OIDs, recommendation, permission, AWA signal, recovery requirement/result, dependencies,
evidence digest, and consequence copy. It never converts warning, age, PR purpose, or AWA state into
permission.

There is exactly one final removal confirmation per batch, not one modal per item. It groups rows as
**Recommended**, **Recovery-backed**, and **Operator override — data/disruption risk**, and shows
type, path/ref, expected OID, artifact/result, AWA signal, exact force/CAS consequence, and excluded
or potentially lost state. Selection, plan approval, Select All, purpose, or age never substitutes
for this grouped confirmation. A materially worse risk discovered afterward skips that row for a
fresh preview rather than escalating silently.

Execution rules:

- serialize every node sharing one Git common directory;
- default to exactly two workers across independent remote/common-directory targets; no setting;
- a repository-local failure/refusal skips only dependent nodes and other repositories continue;
- if Keep/Override risk was not explicitly selected, mark **Protected/Skipped**; if override was
  selected, execute only the confirmed §8 path and report it without a safety-success label;
- an AWA refusal/unavailable result is advisory and does not increment the infrastructure circuit
  breaker when an operator-confirmed native override path exists; other safety refusals remain
  expected terminal results, not systemic failures;
- after three consecutive infrastructure-equivalent failures with the same normalized signature,
  stop admitting new work and pause the batch; running children drain;
- the signature is a closed redacted tuple of operation kind, failure class, executable/transport
  stage, and stable error code—never a raw path, environment value, credential, or prose line;
- successful or differently signed infrastructure results reset the consecutive counter;
- cancellation closes admission, asks current verified children to stop, uses the existing bounded
  TERM/KILL/reap protocol, marks unstarted nodes Cancelled, skips dependents, preserves every
  completed recovery artifact/mutation, and postflights partial Worktree/Branch/AWA residue; and
- restart trusts only structured event/ref postflight plus current identities, never persisted PID.

### 9.2 `~/dev` terminal mutation

Freeze the batch policy/config authority digest during preview and revalidate it before each node.
If `KleinPerkins/dev` is selected for Fast-forward:

1. schedule all non-`~/dev` nodes first;
2. schedule the `~/dev` Fast-forward alone after both workers are idle;
3. run no `~/dev` Repair/Remove node in the same batch;
4. treat it as the final mutation; and
5. compare policy/config authority after completion. Whether changed or not, end the batch; if
   changed, invalidate every cached discovery/preview and require fresh discovery before another
   run.

### 9.3 Status and progress contract

`queued` and `running` are nonterminal. Terminal statuses are `succeeded`, `skipped`, `refused`,
`failed`, and `cancelled`. The only valid transitions are:

```text
queued → running → succeeded | skipped | refused | failed | cancelled
queued → cancelled  (only when never started)
```

No transition leaves a terminal state. The progress header shows total operations, terminal/total
count, current phase, active workers `0–2`, and monotonic elapsed time. Only terminal operations
contribute to completed/live/final counts. Repository cards show only their nodes and dependencies.
A normal final report is emitted only after every planned operation is terminal, so its five terminal
status counts include every node exactly once and sum to total; repository counts remain separate.
Recovery treats persisted `queued`/`running` as unfinished evidence, never completed work: it
revalidates current state, emits a terminal interrupted/cancelled result with bounded detail, and
never restarts the operation automatically.

Exact recovery copy:

- cancellation: **Run cancelled — completed changes were kept; unfinished operations did not
  start or were stopped and rechecked.**
- infrastructure pause: **Run paused after three matching system failures — running operations were
  drained. Review the live log, then start a fresh inspection.**
- interrupted recovery: **Previous run interrupted — current repository state was rechecked. No
  unfinished operation was restarted automatically.**

### 9.4 Structured event file and in-app live log

Evolve the existing private `latest.log` rather than add a database/history service. After exclusive
run ownership and identity checks, a new admitted run replaces the previous latest file. From its
first record until terminal fsync, the v2 file is append-only. Each bounded JSON line includes:

- schema and run ID;
- monotonically increasing sequence;
- RFC3339 time;
- normalized repository identity;
- operation ID, target type, and kind;
- phase and worker ID (`1` or `2`, or coordinator);
- recommendation and ordinary/override selection;
- bounded AWA signal/disposition without database content;
- retention requirement, artifact ID, restore result, and excluded-state summary;
- exact admitted Git/AWA executable plus ordered argv (including canonical target path/ref and force
  level, never token/environment values) and outcome;
- status, postflight residue, and recovery state;
- bounded redacted detail; and
- optional monotonic duration milliseconds.

No record contains raw environment, credential-bearing URL, headers, repository file content,
diff, prompt, or unbounded subprocess output. Keep descriptor-relative no-follow, owner/mode,
single-link, framing, redaction, partial-tail, and fsync protections from v1.

The app renders the same validated event stream in an expandable **Live log** panel while the run
is active and in the final report. The default view remains compact; expanding does not reread an
unsafe path or execute a shell. Recovery requires a contiguous schema/run/sequence prefix and fresh
entity/ref postflight. Unknown/newer records remain bounded raw-incompatible evidence and block
automatic continuation, not ordinary fresh discovery.

## 10. Repository-card UI contract

### 10.1 List hierarchy

Use three sections:

1. **Writable repositories** — default open; selected operation summary; cleanup **Select All**
   selects only visible **Recommended** Worktree/Branch rows, never Recovery/Keep/Override risk,
   cards, dependencies, or hidden children.
2. **Protected repositories** — default open; no controls; exact reason such as
   **Repository-owned workflow** or **Permanent no-touch**.
3. **Reference repositories** — collapsed by default; read-only context; excluded from blocked
   counts, selection counts, Select All, fetch, GitHub PR inventory unless opened, and worker
   payloads.

A first-launch **Confirm canonical roots** panel appears above these sections when §4.4 has
unambiguous rows. It shows every proposed root and one explicit confirmation; ambiguous cards stay
inside Writable with per-card selection. A top summary reports operation-ready/refused counts for
writable repositories and separate protected/reference counts. It never says references are blocked.
Select All is disabled as authority input. It never grants removal permission beyond the visible
Recommended cleanup rows; Recovery and override choices are always individual.

### 10.2 One bounded card per normalized origin

Each card border contains, in order:

- header: `owner/repository`, actual default branch, policy category, and current operation summary;
- canonical root: selected clone, primary checkout branch, and default-branch worktree/ref-only
  target;
- exact default and upstream relations with ahead/behind numbers and evidence time;
- nested independent clone rows by common directory;
- nested Worktree and Branch rows with all zero-to-many claim IDs, duplicate-claim warning,
  cleanliness, activity, deterministic purpose, PR records, §8 recommendation badge, and separate
  selection/override/dependency state;
- the same checkbox/action geometry for both types, with Branch removal visibly dependent on all
  claiming Worktree removals;
- nested **Repair**, **Initialize**, **Fast-forward**, **Remove**, **Remove with recovery**, and
  **Remove anyway / Operator override** controls only at their true target grain—even when AWA
  advises Keep/refuses/unavailable; and
- a warning/refusal panel physically inside the card that owns it.

Cards remain compact through progressive disclosure. Do not render separate top-level cards for
independent clones of the same origin.

### 10.3 Type, PR-state, and recommendation visuals

Use one compact row layout but make entity type obvious before path text:

- **Worktree:** bundled folder-tree/worktree vector icon, blue/teal type accent, and visible
  **Worktree** label;
- **Branch:** bundled Git-branch vector icon, purple/indigo type accent, and visible **Branch** label;
- **PR state:** separate GitHub-like Draft/Open/Merged/Closed icon+text+color tokens that never reuse
  the type accent as status meaning; and
- **Recommendation:** a distinct text badge—**Recommended**, **Recovery copy required**, **Keep**,
  or **Override risk**—beside the common checkbox/action position.

Pair every icon and color with visible text; color is supplementary. If actual Octicon assets are
used, include their license/notice. Preserve native dark/high-contrast legibility and compact density.
Nested connectors show each Worktree→Branch claim and the Branch action's dependency count without
requiring the operator to infer type or relationship from a path.

Truthful copy examples:

- **Keep — AWA reports this worktree active. Removal remains available as Operator override.**
- **Recovery copy required — local staged, untracked, or ignored files must be retained first.**
- **Override risk — recovery did not include 2 secret-shaped paths; Remove anyway may permanently
  lose them.**
- **Branch waiting — remove 2 claiming worktrees before this local ref can be selected.**

No vague clone-wide “blocked,” green=safe implication, or AWA-approved wording may replace a known
recommendation, permission, consequence, or hard exclusion.

### 10.4 Compact wireframe examples

```text
[ ]  ▦  Worktree   …/awa-old-17          [Keep]          [Remove anyway…]
     teal type rail · AWA: active/refused (advisory) · local files: unknown

[x]  ⑂  Branch     feature/card-cleanup  [Recommended]   [Remove]
     purple type rail · PR: Merged ✓ (green status) · stale 46d · claims: 0

[ ]  ▦  Worktree   …/dirty-experiment     [Override risk] [Operator override…]
     teal type rail · staged + ignored + secret gap · may lose named local state
```

The production assets use distinct folder-tree and Git-branch vectors; the text glyph is illustrative
only. All three examples retain identical checkbox/badge/action geometry, while type rail/icon/label
and independent PR status make them scannable.

## 11. Migration and compatibility

1. Add the v2 model beside current v1 decoding. Do not rewrite accepted docs, v1 log bytes, current
   installed report, or PR #192 history.
2. On first v2 discovery, construct `RemoteRepository`/`LocalClone`/`Worktree`/`Branch` from fresh
   source—not by promoting cached `RepositoryCandidate` eligibility.
3. Existing v1 log/report records remain reopenable through a read-only decoder and are labelled
   **Legacy run — clone-based model**. They create no v2 operation or canonical authority.
4. `repository-authorities.json` begins absent. Body 1 provides the one bounded §4.4 confirmation
   for all displayed single-writable-clone cards; duplicate/multiple-writable-clone cards stay
   disabled until individually selected. No automatic migration or Select All path guesses authority.
5. Body 1 adds the authority file to lifecycle doctor/install/update/uninstall allowlists and proves
   preservation/rollback before its first exact merged-main install. Body 3 adds v2 protected
   Worktree/Branch recovery artifacts and override event fields to lifecycle allowlists. Update/
   repair preserve them; verified uninstall reports and preserves authority, artifacts, and
   `latest.log` rather than silently deleting restore/authorization evidence.
6. Keep current result/report meaning through explicit mappings where semantics are identical.
   Clone-wide unsupported-Cursor/hook/main blockers do not map to v2 refusals; fresh target-scoped
   inspection replaces them.
7. Body 1 may ship with checked-out target mode only. Body 4 adds existing-ref CAS only after its
   focused race tests pass. No temporary fallback switches a branch or updates a ref without CAS.
8. Source-built lifecycle changes remain test-root-only until their body merges. Body 1 is an
   independently deployable production step and must pass exact merged-main source attestation,
   install/reconcile, product-local doctor, updater smoke, and rollback evidence before Body 2.
   Each later independently deployable body repeats that merged-main gate for its changed boundary;
   Milestone 5 repeats full-product acceptance after all bodies.
9. Body 2 discovers the optional local `gh` adapter fresh after update/install. A missing, moved,
   unsupported, or unauthenticated executable invalidates only cached PR purpose and requires no
   state migration, credential copy, or fallback transport.
10. Existing v1/ordinary AWA bundles remain readable evidence but never become complete v2
    Worktree+index+history artifacts by migration. Recommendation/override selection is per-run,
    app-operated through the native UI, invokes no agent, and creates no operator-edited policy/config. AWA state remains
    external read-only advisory state; Dev Main Sync persists only its own event/artifact records.


## 12. Corrected requirements, focused tests, and traceability

### 12.1 Closed v2 requirements

| IDs | Requirement |
|---|---|
| `V2-ID-01–05` | One normalized remote card; nested common-dir clones/worktrees/branches with zero-to-many claims; explicit canonical root; bounded single-clone bulk onboarding; ambiguity disables only dependent actions. |
| `V2-UPD-01–07` | Resolve actual remote default; exact bounded fetch; fresh relation/claim checks; checked-out FF; ref-only CAS; operation-relevant hooks; no mutation for Ahead/Diverged/unknown. |
| `V2-REP-01–04` | Implement exactly R-01/R-02/R-04 and the non-mutating R-03 rejection with their stated predicates, guards, copy, and tests. |
| `V2-INV-01–07` | Complete branch/worktree/clone/upstream/commit/PR inventory; one closed optional gh adapter; strict association; deterministic purpose/activity; separate removal recommendation and permission. |
| `V2-REM-01–10` | Visible operator path for every non-default local feature item; four recommendation states separate from permission; protected file/index/history recovery; preferred advisory AWA path plus exact native force override; worktree-before-branch; empty-claim CAS; grouped confirmation; hard exclusions/no remote deletion. |
| `V2-BAT-01–06` | Recovery→worktree→branch DAG; common-dir serialization/two workers; Recommended-only Select All; grouped risk confirmation; AWA refusal excluded from override circuit breaking; cancellation/`~/dev` handling. |
| `V2-UI-01–06` | Writable/protected/reference hierarchy; one bounded card; common Worktree/Branch interaction with distinct icon/accent/label; recommendation badges; visible AWA override; claim dependencies; compact wireframes. |
| `V2-LOG-01–05` | Closed run transitions and terminal-only counts; recommendation/AWA/retention/override/command/outcome/residue event evidence; bounded redaction; cancellation recovery. |
| `V2-COMP-01–03` | Body-1 authority lifecycle compatibility/install; later retention and read-only v1 compatibility; every production step installs only exact clean merged main. |
| `V2-GOV-01–04` | Preserve source/capability and protected/reference/hidden-artifact boundaries; no non-goal leakage; surgical verification; governed Draft-PR delivery. |

No source requirement is silently deferred. Ref-only update is sequenced to Body 4, not omitted.

### 12.2 Smallest deterministic test matrix

The implementer first maps changed symbols to these tests, then runs only the smallest affected set.
Production build/symbol/inventory checks are added when AppKit, process, lifecycle, test-seam, or
packaging boundaries change.

| Test ID | Deterministic proof | First body |
|---|---|---|
| `DM2-T01 identity-authority` | Independent clones group once; zero-to-many claims remain explicit; bounded onboarding lists/atomically confirms only single-writable-clone cards; cancel/deselect/multiple/stale cases remain disabled; Select All cannot write authority; `~/dev`/policy classes stay exact. | 1 |
| `DM2-T02 remote-default` | Local bare/served fixtures advertise `main`, `master`, `develop`, `next`, changed, missing, detached, and malformed `HEAD`; no fallback to `main`/local `origin/HEAD`; exact fetch flags and target capture audited. | 1 |
| `DM2-T03 checked-out-target` | Default in primary/linked roots; unrelated feature worktrees; force-capable duplicate-claim fixture; Equal/Behind/Ahead/Diverged; full claim/ref/config/policy races; locked FF-only exact target and postflight. | 1 |
| `DM2-T04 ref-only-cas` | Empty-claim existing default Behind updates by expected-old CAS; immediate full claim re-enumeration catches duplicate/appearing claim; `update-ref` claim blindness never bypasses veto; index/worktrees byte-identical. | 4 |
| `DM2-T05 operation-hooks` | Trace hooks Git actually invokes for fetch/merge/update-ref/worktree/branch commands; marker-only repository remains usable; veto and post-residue affect only the triggering operation; no bypass. | 1–4 |
| `DM2-T06 repair-initialize` | Every R-01–R-04 case; locked final prune dry-run exact-set gate including a newly stale registration; detached/unknown/default/unpreserved refusal; claim-safe initialization; no manual metadata/lock deletion or generic repair. | 2 |
| `DM2-T07 inventory-purpose` | Closed Purpose oracle covers exact Draft/Open/Merged/Closed, Integrated ancestry, OID-different Superseded, fork/multiple Ambiguous, empty/Unavailable, and OID change; exact 7/8/30/31-day boundaries; no purpose/age creates removal. | 2 |
| `DM2-T08 recommendation-permission` | Closed Worktree/Branch four-state oracle; active/recent/dirty/Open/AWA/unknown signals recommend Keep without hiding override; staleness never permits; claims dependency-block Branch; Select All Recommended-only; grouped confirmation separates recommendation/recovery/override. | 3 |
| `DM2-T09 recovery-artifact` | Protected v2 artifact restores exact branch `H`, tracked bytes, staged/index state/flags, untracked/ignored files, modes/symlinks/status; explicit secret inclusion; corrupt/incomplete/excluded/declined/cancelled proof becomes Override risk and preserves completed artifacts. | 3 |
| `DM2-T10 awa-advisory-override` | Normal AWA `clean --path` remains preferred; refusal/active/stale/unavailable changes recommendation not control; confirmed native override proceeds without AWA-state mutation/approval claim; independent postflight surfaces stale AWA bookkeeping as advisory residue. | 3 |
| `DM2-T11 batch-cancel-policy` | Recovery→worktree→claim-reinspect→branch order; same-common-dir/two-worker bounds; one grouped confirmation; AWA refusal with selected override does not trip circuit breaker; Protected/Skipped without override; cancellation preserves artifacts/partial residue; `~/dev` final. | 3 |
| `DM2-T12 card-events-recovery` | Worktree teal folder-tree label versus Branch purple Git-branch label with independent PR colors; shared mechanics, badges/dependencies/wireframes; closed run transitions; events include recommendation/AWA/retention/override/command/outcome/residue; partial recovery truthful. | 1, 3 |
| `DM2-T13 compatibility-release` | Body 1 authority lifecycle/update/uninstall/rollback and exact merged-main install first; later retention/v1 read-only compatibility; each body and final product pass source/doctor/symbol acceptance without test seams. | 1, 3, 4, release |
| `DM2-T14 gh-adapter` | Exact approved-path executable identity, closed `pr list` argv/environment/fields, JSON/output/cache/concurrency bounds, timeout/cancel/redaction, auth/network absence degradation, and M6 audit allowing no other network client/executor. | 2 |
| `DM2-T15 native-removal-override` | Disposable fixtures prove non-force refusal→Recovery-backed/override single force for dirty content, exact double force for locked worktree, immediate identity/content/claim recheck, interruption/postflight, no blind filesystem fallback, and exact-ref history-loss CAS only after claims empty. | 3 |
| `DM2-T16 direct-human-runtime` | Production audit proves no agent/runtime AWA authorization call; every feature removal starts from direct UI selection; AWA objects/unavailable still show override; hard exclusions have no control; remote refs/product/non-Git paths cannot enter command grammar. | 3 |

### 12.3 Requirement → design → test traceability

| Requirements | Design authority | Detecting tests / acceptance | Delivery |
|---|---|---|---|
| `V2-ID-01–05` | §§4, 10 | `DM2-T01`, `DM2-T12`; one card per origin, all claim IDs, bounded onboarding, explicit target proof | Body 1 |
| `V2-UPD-01–04,06–07` | §5.1–5.4, §5.6 | `DM2-T02`, `DM2-T03`, `DM2-T05`; exact command/OID/refusal audit | Body 1 |
| `V2-UPD-05` | §5.5 | `DM2-T04`, `DM2-T05`; claim/ref race and index/worktree byte audit | Body 4 |
| `V2-REP-01–04` | §6 | `DM2-T06`; matrix-positive and every named refusal case | Body 2 |
| `V2-INV-01–07` | §7 | `DM2-T07`, `DM2-T14`; closed gh adapter, Purpose/activity oracle, recommendation/permission split | Body 2 |
| `V2-REM-01–10` | §8 | `DM2-T08–T10`, `DM2-T15–T16`; state machine, recovery, AWA/native override, claims, exclusions | Body 3 |
| `V2-BAT-01–06` | §9.1–9.2 | `DM2-T11`; grouped confirmation, circuit behavior, DAG/process/ref/policy evidence | Body 3 |
| `V2-UI-01–06` | §10 | `DM2-T01`, `DM2-T08`, `DM2-T12`; type/badge/override/dependency/Select-All snapshots | Bodies 1–3 |
| `V2-LOG-01–05` | §9.3–9.4 | `DM2-T11–T12`; authorization/AWA/recovery/command/residue schema and recovery proof | Body 3 |
| `V2-COMP-01–03` | §11 | `DM2-T13`; Body-1 authority lifecycle/install, later retention/v1, merged-source identity | Bodies 1,3,4/release |
| `V2-GOV-01–04` | §§0,1.3,3,15 | focused structural/command/symbol/diff reviews; reviewer-App evidence | Every body |

## 13. Milestone and Draft-PR roadmap

For Bodies 1–4, complete the body, open one Draft PR, resolve its focused reviews, merge only through
the ordinary reviewer App, then verify/install that exact clean merged `origin/main` and run the
product-local doctor before starting the next body. These are governed delivery steps authorized by
the single plan checkpoint, not new operator checkpoints. Installing cleanup capability never
authorizes a real destructive run; item selection and explicit confirmation remain mandatory.

### Milestone 0 — finish the preserved guidance body

**PR boundary:** existing Draft PR #192 only.

- Resume only after this plan is approved.
- Preserve its current five uncommitted menu-guidance edits as their own body.
- Revalidate its exact head/worktree then complete focused tests and review without mixing any v2
  model, repair, cleanup, batch, or documentation-lane change.
- Merge through the ordinary reviewer-App path. Do not arm auto-merge or call a merge command.

**Exit:** PR #192 is cleanly delivered or truthfully held on a material finding. Body 1 does not
start on top of its dirty worktree.

### Milestone 1 / Body 1 — minimum viable corrected installed vertical slice

**Value:** one end-to-end repository-centric default update is usable in production shape.

Implement:

- the §4 entities needed for discovery/card/update, normalized-origin grouping, nested clones and
  branch/worktree associations;
- app-owned explicit canonical-root selection, §4.4 bulk onboarding, per-card ambiguity handling,
  and authority-file drift/lifecycle compatibility;
- actual remote-default resolution and exact fetch;
- checked-out target-scoped Equal/Behind/Ahead/Diverged behavior, including unrelated feature
  worktrees and operation-relevant hooks;
- writable/protected/reference sections and bounded repository cards with plain refusal copy;
- current v1 serial coordinator/log compatibility sufficient for this slice; and
- no repair, PR inventory, cleanup, second worker, retention, or existing-ref CAS.

**Smallest verification:** dependency map → `DM2-T01–T03`, relevant `DM2-T05`, Body-1 subset of
`DM2-T12`, and authority lifecycle cuts in `DM2-T13`; production Swift build, test-seam/banned-command
symbol audit, and one isolated onboarding→selection→verified actual-default FF→report journey. After
reviewer-App merge, attest and install exact clean merged main, run doctor/updater smoke, and prove
rollback plus authority preservation.

**Exit:** logical duplicates render once; bounded onboarding makes unambiguous cards update-ready
without guessing; duplicate claims/roots remain explicit; `master`/`develop`/`next` fixtures work; a
clean checked-out default fast-forwards; unrelated feature work is context; and the installed exact
merged-main app delivers this value before Body 2.

### Milestone 2 / Body 2 — approved repairs and lifecycle preview

**Value:** the operator can understand feature-work purpose and fix only the two known worktree
metadata states or explicitly initialize an absent default.

Implement:

- R-01, R-02, the non-mutating R-03 explanation, and R-04 **Initialize** exactly;
- complete branch/worktree/upstream/commit-date inventory;
- the §7.3 identity-verified closed optional gh adapter and M6 audit change;
- strict PR association plus the closed Purpose oracle for exact/multiple/OID-different/unavailable
  states;
- centralized activity plus separate Purpose, Worktree/Branch recommendation, and permission/
  dependency preview states; and
- visible preview of Recommended/Recovery/Keep/Override controls and hard exclusions only—no
  worktree, branch, retention, or AWA mutation.

**Smallest verification:** dependency map → `DM2-T06–T07`, `DM2-T14`, relevant `DM2-T05` hook
traces, operation/control snapshots, gh executable/grammar/M6 audit, GitHub-outage degradation, and
command-enum audit; finish with this body's exact merged-main install/doctor gate.

**Exit:** every repair candidate has its final disposition/copy/tests; no generic Repair exists;
PR/age/AWA state never authorize or erase a control; removal previews distinguish recommendation
from permission and name exact recovery/override consequences without executing cleanup.

### Milestone 3 / Body 3 — operator-authorized cleanup, batch execution, and live evidence

**Value:** the utility recommends protection and recovery by default while the human can deliberately
retire accumulated non-default feature state—even when AWA advises against it—with exact consequence
and recovery evidence.

Implement:

- §8's four Worktree/Branch recommendation states, separate permission, C-01–C-07, and hard
  exclusions;
- protected restore-proven branch/worktree/index artifacts including explicit secret authorization;
- preferred normal AWA cleanup plus native non-force/single-force/double-force operator override,
  independent Git/AWA postflight, advisory stale-bookkeeping residue, and deferred filesystem fallback;
- exact empty-claim Branch CAS including explicit unpreserved-history override;
- the full recovery→worktree→claim-reinspect→branch DAG, Recommended-only Select All, one grouped
  confirmation, default two-worker scheduling, and AWA-refusal circuit-breaker exclusion;
- local failure continuation, three-signature infrastructure pause, and `~/dev` terminal mutation;
- closed run transitions, cancellation/drain/recovery, exact final counts, expanded event fields,
  and in-app live log; and
- lifecycle preservation for completed v2 recovery/override evidence.

**Smallest verification:** dependency map → `DM2-T08–T12`, `DM2-T15–T16`; exact AWA/native argv
audit, force/claim/retention/secret/interruption fixtures, UI type/recommendation snapshots, process/
resource/redaction checks, focused production build/symbol/security audit, isolated mixed batch/cancel/
recovery, zero real-repository/AWA mutation, then exact merged-main install/doctor.

**Exit:** every non-default feature Worktree/Branch has a visible path; AWA remains preferred but
cannot veto confirmed override; default/no-touch/remote/product/non-Git exclusions hold; recovery
round-trips files/index/history; force/CAS only follow grouped authorization; stale AWA residue is
truthful; no agent/runtime AWA writer/filesystem fallback exists; partial runs preserve artifacts;
installed merged main passes doctor.

### Milestone 4 / Body 4 — necessary ref-only and compatibility closure

**Value:** safe canonical defaults can remain current even when not checked out, without branch
switching or losing v1 evidence.

Implement only:

- §5.5 expected-old ref-only fast-forward for an existing local default;
- complete v1 log/report read compatibility and explicit legacy labels;
- retention-state and v1 evidence update/repair/uninstall compatibility not completed earlier; and
- narrow compatibility fixes proven necessary by Bodies 1–3.

Do not add another repair, cleanup mode, performance SLA, branch workflow, or remote mutation.

**Smallest verification:** dependency map → `DM2-T04–T05`, `DM2-T13`, targeted claim/ref races,
legacy fixture hashes, lifecycle failure cuts for new state entries, production build/symbol audit,
and this body's exact merged-main install/doctor gate.

**Exit:** existing-ref CAS is safe under claim/ref races; v1 evidence remains readable/unchanged;
installer/doctor/update/uninstall treat v2 durable state truthfully.

### Milestone 5 — merged-main install acceptance

After all required implementation bodies merge through the reviewer App:

1. verify live remote `origin/main` and exact local clean main in the durable primary Skills checkout;
2. run only the final dependency-mapped focused product, packaging, source-attestation, policy,
   zero-link, and lifecycle checks plus the isolated production journey;
3. verify no open material review finding and no uncommitted/untracked capability input;
4. reconcile/install that exact merged revision through the existing source-built lifecycle;
5. run the installed lifecycle doctor and operator selection/cancel-before-mutation smoke; and
6. record app/source revision, bundle digest, launcher state, and no target-repository mutation.

Never install a Draft PR, worktree branch, dirty source, or guessed equivalent revision.

## 14. Six-month failure rehearsal

Assume the redesign failed six months after release. Exactly eight plausible causes and their
preventive evidence are:

| ID | Failure cause | Earliest warning | Mitigation folded into design | Detecting test / acceptance evidence |
|---|---|---|---|---|
| FR-01 | Clone/AWA-wide eligibility conflation returned and recreated cleanup pile-up | One AWA refusal/unknown provenance hides Remove, or one feature warning disables another target | `PlannedOperation` separates recommendation/permission; §8 keeps in-scope override visible while hard exclusions stay closed | `DM2-T01`, `DM2-T08`, `DM2-T10`, `DM2-T16` control-availability oracle |
| FR-02 | Staleness/recommendation became automatic permission | Crossing day 30, Merged, Recommended, or green badge auto-selects/removes without human confirmation | §§7.4–7.5 and §8 separate purpose/recommendation/permission; Select All is Recommended-only but final grouped confirmation remains mandatory | `DM2-T07–T09`, `DM2-T11–T12` selection/confirmation oracle |
| FR-03 | “Repair” expanded into dirty/lock/history/general Git mutation | A new Repair result lacks one R-ID or command outside prune/repair/initialization appears | Closed R-01–R-04 enum and §6.6 refusal boundary; adding a row requires successor authority | `DM2-T06` command/control audit and all excluded-state fixtures |
| FR-04 | The app updated the wrong independent clone or remained useless with no roots | Canonical root is inferred, bulk onboarding hides paths, Select All writes authority, or first launch has zero actionable single-clone cards | Explicit per-root display/confirmation; bulk only for exactly one writable clone; duplicate roots stay per-card; authority lifecycle ships/installs in Body 1 | `DM2-T01`, `DM2-T12`, `DM2-T13` onboarding/cancel/drift/install cases |
| FR-05 | Operator override bypassed zero-to-many claims and dangled a worktree | Branch override becomes selectable with claims, duplicate/appearing claim collapses, or CAS skips the immediate scan | Claims are a non-overridable Git integrity dependency; worktree-first DAG, shared lock, pre-CAS full re-enumeration | `DM2-T03/T04/T08/T15` forced duplicate and preview→override races |
| FR-06 | Force/override lost squash history, index state, local files, or secrets without truthful consent | Artifact omits a class, restore differs, force runs after an unconfirmed risk change, or report implies preservation | v2 artifact covers history+tracked/index/untracked/ignored; secrets explicit; incomplete proof becomes Override risk; exact loss appears in one grouped confirmation/log | `DM2-T09`, `DM2-T11–T12`, `DM2-T15` restore/failure/force/redaction matrix |
| FR-07 | A host policy change during a batch invalidated later safety decisions | Policy/config digest changes yet another repository operation starts, especially after `~/dev` update | Frozen preview digest, admission recheck, unexpected-change refusal, `~/dev` alone and terminal | `DM2-T11` injected pre-node and `~/dev` policy-change schedules |
| FR-08 | Progress/recovery was unusable, hiding partial success or leaving unsafe retries | Queued/running count as complete, terminal counts do not sum, sequence breaks, or restart auto-replays a node | Closed transitions, terminal-only counts, operation/worker/phase evidence, exact postflight, no auto-replay | `DM2-T12` transition/mixed/cancel/crash/partial-tail/redaction assertions |

**Three most likely:** FR-01 clone/AWA-wide veto regression, FR-04 wrong canonical clone, and FR-08
unusable progress/recovery. They sit at tempting implementation shortcuts and therefore have direct
model/UI/event acceptance gates.

**Three most preventable:** FR-02 staleness-as-safety, FR-03 broad repair, and FR-06 squash data
loss. Closed authority, recommendation/permission rules, command enums, and restore tests prevent them rather
than merely detect them in production.

The mitigations above are requirements in §§4, 6–9 and tests in §12; they are not a later hardening
phase.

## 15. Surgical verification, review, and delivery rules

For this plan and every implementation body:

1. Build a dependency map from changed files/types/commands to `DM2-T*` IDs.
2. Run the smallest deterministic tests that cover those dependencies.
3. Add a production build, package inventory, and symbol/test-seam audit only when relevant.
4. Add a security review only when the body changes mutation commands, process/lock behavior,
   retention/deletion, redaction/events, or installation boundaries. Bodies 1–4 each name the
   relevant boundary; PR #192 does not gain a security review solely from this plan.
5. Open one Draft PR per body and leave it unarmed. Run one initial Bugbot review per body. Rerun
   Bugbot or security review only after a material finding caused a material change.
6. Fix all material findings in that body and rerun only the affected deterministic evidence.
7. Use the ordinary reviewer-App exact-head path. Never call `gh pr merge --auto`, direct merge,
   bypass checks/reviews, alter the controller/VPS/config, or treat dev PR #352's manual squash as
   standing authority.
8. After each Body 1–4 merge, install only that exact clean merged `origin/main` and run its
   dependency-mapped production/doctor gate; Milestone 5 repeats full acceptance.

No reflexive full-suite run substitutes for dependency coverage. A full product suite is justified
only when the dependency map shows broad shared-core/lifecycle impact or at the final merged-main
acceptance if current repository policy requires it.

## 16. Exact acceptance

The v2 roadmap is complete only when all of the following are true:

1. one normalized owner/repository card contains every independent clone/worktree and every
   branch's complete zero-to-many claim set with no duplicate top-level card or collapsed claim;
2. the corrected logical classes are policy-derived: writable includes `~/dev`; cpp, no-touch, and
   reference behavior remains exact; hidden artifacts remain absent;
3. canonical authority is explicit, app-written, and drift-refusing; first launch offers one bounded
   confirmation only for displayed single-writable-clone cards, duplicate roots remain per-card,
   Select All cannot authorize roots, and Body 1 lifecycle/install preserves the authority file;
4. remote `main`/`master`/`develop`/`next` fixtures resolve from remote `HEAD`; missing/ambiguous
   remote `HEAD` never falls back;
5. exact fetch writes no `FETCH_HEAD`, tags, prunes, submodules, or maintenance and captures one target;
6. checked-out and ref-only modes mutate only Behind at exact target; every mutation immediately
   re-enumerates the full claim set under lock; duplicate/appearing claims veto; Equal is no-op;
   Ahead, Diverged, unknown claims, and races preserve state;
7. marker-only and unrelated worktrees do not block safe targets; actual hook veto/residue affects
   only its operation and no hook is bypassed;
8. the only repair/initialization behavior is R-01, R-02, R-03 rejection, and R-04; prune holds the
   common lock across its immediate exact-set dry-run/action, rejects unsafe claims/unpreserved tips,
   and states the bounded external-rm residual risk; every named test/copy passes;
9. branch/worktree/PR/activity/purpose fields match §7; the identity-verified closed gh adapter is
   the only optional PR transport; absence/failure and deterministic Exact/Superseded/Ambiguous/
   Integrated purpose never block updates or become removal permission;
10. Worktree and Branch each implement the closed Recommended/Recovery copy required/Keep/Override
    risk states; staleness and AWA signals affect recommendation only; selection and permission remain
    separate and no destructive operation is automatic;
11. every non-default local feature Worktree/Branch has a visible removal path even when AWA refuses,
    reports active/stale/bad provenance, or is unavailable; normal AWA worktree cleanup remains first,
    but Dev Main Sync never edits AWA state or claims an external override was AWA-approved;
12. protected retention captures/restores exact branch history, tracked bytes, staged/index state,
    untracked/ignored files, modes/symlinks, and status; possible secrets require explicit inclusion
    and private protected storage; incomplete/failed/declined recovery becomes Override risk with
    exact loss copy while completed artifacts survive cancellation/failure;
13. Worktree removal follows exact preflight→recovery→AWA→locked final snapshot→ordinary Git→confirmed
    single/double-force→postflight grammar; an ignored-file race cannot be silently lost; cancellation
    is bounded; no blind filesystem deletion exists and Git-unremovable broken metadata is truthfully
    deferred;
14. external removal re-inspects physical path, Git registration/refs/claims, artifact, and AWA
    separately; Git-owned stale registration uses only R-01 Repair and stale AWA bookkeeping is
    advisory residue/recovery guidance rather than a false failure or success;
15. Branch removal is a separate selected operation after all claiming Worktrees are removed; every
    CAS immediately proves the zero-to-many claim set empty and exact expected local `H`; unpreserved
    history requires explicit grouped override; no remote deletion or `branch -D` exists;
16. cleanup Select All chooses only Recommended rows; Recovery/Keep/Override risk require individual
    selection; one final confirmation separates Recommended, Recovery-backed, and Operator-override
    risk groups and names exact file/history/disruption consequences;
17. the batch obeys recovery→worktree→claim-reinspect→branch dependencies, common-dir serialization,
    two-worker bound, local continuation, three-signature pause, cancellation drain/artifact
    preservation, and terminal `~/dev` rule; AWA refusal with a confirmed native override is not an
    infrastructure circuit-breaker event;
18. queued/running remain nonterminal; only the closed transitions occur; completed/final counts use
    terminal statuses only and recovery never treats unfinished records as completed;
19. event/log/report data records recommendation, AWA signal, retention result, override selection,
    exact executable/argv/outcome, residue, and recovery state while remaining private, bounded,
    redacted, contiguous, and free of raw environment/credentials/content;
20. Worktree rows use folder-tree icon+blue/teal+Worktree, Branch rows use Git-branch icon+purple/
    indigo+Branch, PR state remains visually independent, badges use icon/color/text, and claim
    nesting/dependencies plus the three §10.4 wireframes pass snapshot/accessibility checks;
21. production audit proves direct UI selection is the only cleanup origin and no agent, shell,
    AWA-state writer, arbitrary executable/path, product install/state removal, arbitrary non-Git
    removal, or remote-ref removal path exists;
22. resolved defaults, canonical update targets, cpp/repository-owned workflows, permanent no-touch,
    reference-only, remote, product/runtime/install, and non-Git targets stay outside cleanup controls;
23. v1 logs/reports remain byte-identical/readable and no cached v1 eligibility creates v2 action;
24. capability ownership, no-downstream/paid-runner/controller/cpp/chaos-scheduler boundaries remain
    unchanged;
25. every implementation body has a clean Draft-PR diff, focused evidence, resolved material
    findings, ordinary reviewer-App delivery, and exact merged-main install/doctor acceptance; and
26. final full-product acceptance installs exact clean merged current `origin/main` and records zero
    target-repository mutation during release smoke.

## 17. Planning-lane verification and stop condition

Before this documentation Draft PR is handed off:

- verify ADR/plan naming, successor pointers, links, and exactly the required two index updates;
- run repository-correct read-only doc-warden classification;
- use shell `rg` to confirm required sections, all four repair rows/dispositions, all seven cleanup
  rows, exactly eight failure-rehearsal causes, all sixteen deterministic tests, body order 0–4, and prohibited-scope statements;
- inspect the diff for credentials, absolute operator-only implementation literals outside evidence,
  accidental product/code changes, and copied raw environment/log data;
- verify only `docs/adr`, `docs/plans`, and their two indexes changed;
- re-hash/re-status the preserved PR #192 worktree against the initial capture;
- commit with governed identity/hooks, push the follow-up to existing Draft PR #193 without arming
  it, and verify its exact head; and
- prove no background process or temporary fixture remains.

Operator approval was recorded on 2026-09-09 at semantic head
`2eb0f343937b881a29eb4f7eebf45ec8b664b655`. This lifecycle-only transition freezes the plan;
implementation begins only through Body 0 after governed merge.

**APPROVED — Dev Main Sync v2 plan and repair/removal matrices**
