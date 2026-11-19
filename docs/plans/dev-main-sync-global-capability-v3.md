# Dev Main Sync — process-free repository chooser and selected-scope execution plan

**Version:** v3
**Status:** ACCEPTED — 2026-09-12
**Date:** 2026-09-12
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Supersedes:** [Dev Main Sync repository lifecycle control center execution plan v2](dev-main-sync-global-capability-v2.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Implementation baseline:** clean revision `71b8149dfff38ff27056cfb0d7bf0aa509a6437b`
on branch `fix/dev-main-sync-preflight-surface`
**Review state:** the operator approved this v3 architecture and authorized implementation. These
accepted bytes are frozen on creation; implementation starts from this plan without another plan
approval checkpoint.

> **For agentic implementers:** execute this plan task-by-task in dependency order. Every task is
> a zero-context work unit with exact files, symbols, invariants, tests, commands, and completion
> evidence. Keep the checkbox steps current in implementation-session notes; never edit this
> accepted plan to record progress.

**Goal:** Show a usable repository chooser almost immediately, let the operator maintain saved
editable repository defaults, and defer every Git/GitHub/process/network/heavy inspection until
explicit **Continue**, after which all discovery, refresh, confirmation, and execution remain
strictly linear in one immutable selected repository scope.

**Architecture:** Preserve the shipped v2 repository/operation/wire model. Add an isolated
process-free catalog target and a separate `RepositorySelectionCandidate`; persist selection intent
in its own CAS-protected document; bind selected policy-relative locators to a freshly opened
governed-root descriptor at Continue; require a staged verified-authority capability before any
`RepositoryCard`, `PlannedOperation`, removal, confirmation, or worker payload can be constructed;
replace every production broad discovery route with selected-scope hydration; and drive the app
through one `@MainActor` lifecycle router whose Quit path ends only at a proven drain barrier.

**Tech stack:** Swift 6.2, AppKit, Darwin/POSIX descriptor APIs, existing closed Git/GitHub runners,
existing source-built lifecycle, existing no-dependency Swift self-test harness, and isolated
`/private/tmp` acceptance fixtures.

---

## 0. Authority, body choice, and dependency order

This plan changes no ADR 0004 product action or v2 mutation algorithm. It closes a pre-operation
architecture defect exposed by a physical run:

- the chooser shell appeared in **72 ms**;
- before operator selection, heavyweight inventory then ran for **13m 04.911s**;
- that preselection path started at least **1,727 Git child processes**;
- it inspected roughly **51 repositories**; and
- all six P1 blocker groups were independently source-confirmed at the exact baseline above.

### One integrated implementation body

There is exactly **one implementation body**. Catalog isolation, preference semantics, Continue
binding, authority staging, selected-only refresh, app lifecycle ownership, and drain proof share
one admission boundary. Splitting them would create an unacceptable interim release in which a fast
chooser could still feed broad discovery, preferences could be mistaken for authority, or Quit
could terminate after admission closed but before children/authority drained.

The body remains reviewable through seven ordered tasks and focused commits inside one Draft PR.
No commit is installed or marked ready independently. The production step forward occurs only when
all tasks, all v3 acceptance, retained v2 safety tests, Bugbot, security review, and the explicit
ready gate are complete at one exact PR head.

Dependency order:

```text
Task 1 compatibility locks and red tests
  → Task 2 process-free catalog and immediate chooser
  → Task 3 complete saved-defaults lifecycle
  → Task 4 Continue binding and staged authority types
  → Task 5 selected-only heavy discovery/refresh/worker execution
  → Task 6 one lifecycle router and real drain
  → Task 7 lifecycle compatibility, acceptance, delivery, merged-main install
```

Temporary invariant during implementation: no intermediate commit is deployable, no production
entry point may be switched to the new chooser until Tasks 2–6 are complete together, and all
existing mutation paths remain unreachable from selection intent until Task 4's staged gate is
active. The final PR must contain no feature flag, parallel legacy chooser, broad fallback, or
temporary compatibility bypass.

## 1. Verified current state and exact defect

| Surface | Current symbol/file | Baseline behavior | v3 consequence |
|---|---|---|---|
| Heavy physical model | `RepositoryCandidate` in `Sources/DevMainSyncCore/Models.swift` | Codable clone snapshot carries path, origin, identities, policy/hook digests, topology, relation, and block reason | Preserve its stored/wire shape unchanged; it cannot become chooser state |
| Broad discovery | `RepositoryDiscovering.discover()` and `RepositoryDiscovery.discover()` | Recursively scans `~/dev`, validates candidates concurrently, and runs Git through `DiscoveryGitProbe` | Remove parameterless production discovery; accept only validated selected locators after Continue |
| Heavy inventory | `RepositoryInventoryDiscovering.discoverInventory()` and `RepositoryInventoryDiscovery.discoverInventory()` | Acquires `RunAuthority`, duplicates the operation lease, discovers all candidates, starts Git/gh children, and builds all cards | The chooser cannot call this API; production inventory requires immutable selected scope |
| First window | `startRepositoryInventoryDiscovery` and `RepositoryCardSelectionWindowController(preparingRepositoryList:)` in `AppDelegate.swift`/`RepositoryCardsWindow.swift` | Presents a loading surface, then waits for broad heavy inventory before repository choice | Replace with a process-free catalog chooser; selected hydration begins only after Continue |
| Authority | `RepositoryAuthorityDocument`, `RepositoryAuthorityStore`, `CanonicalAuthorityProposal` | Fresh matching clones, `RepositoryHandle` revalidation, expected file identity, revisioned atomic replacement | Preserve and reuse; preferences never construct, update, or imply authority |
| Operation safety | `RepositoryDiscovery.validateRuntimeEligibility` | Rechecks selectable operation, authority, governed policy, origin, root/common identity, graph metadata, and topology | Preserve and call behind the new verified capability; do not weaken or duplicate it |
| Card/operation construction | `RepositoryCard`, `PlannedOperation`, `RepositoryInventoryRemovalCandidates.make` | Structurally validated but can be constructed in the same broad inventory phase that discovers authority proposals | Restrict construction to a staged verified-authority capability |
| Body 3 refresh | `RunCoordinator.runBody3`, `freshInventory`, `Body3ExecutionContext.record` | Optional no-argument inventory provider or broad `discoverInventory()` can refresh every repository per node | Require exact selected/node scope; reject out-of-scope output before state recording or child admission |
| Worker refresh | production `WorkerMain.dispatch` in `Worker.swift` | Decodes selected operations, then runs parameterless broad inventory before admission | Derive selected locator scope from unchanged wire values and hydrate only that scope |
| Disabled rows | `RepositoryCardsWindow` | Review payloads include only selected operations/removals; disabled rows do not enter payloads | Preserve this strength in both chooser and cards |
| Child cleanup | `WorkerSession`, `WorkerPostReapEvidence`, `LifecycleGate` | Post-reap evidence and lifecycle checks exist, but app-level inventory/body-task completion and Quit ownership are split across flags/controllers | Integrate these safeguards into one router and explicit drain barrier |

The implementation must re-read these symbols at task start. If their semantics have materially
changed from this table, stop before mutation and determine whether a v4 successor is required.

## 2. Scope, protected invariants, and non-goals

### 2.1 In scope

- a process-free, bounded repository catalog and immediately usable chooser;
- selection/deselection, **Save as defaults**, **Continue**, **Cancel**, **Quit**, and later
  **Change/Manage saved selection**;
- complete preference persistence, conflict, corruption, unsupported-schema, and recovery UX;
- descriptor-bound locator validation and fresh selected hydration at Continue;
- canonical onboarding proposals and confirmation within the selected scope;
- a second fresh selected-only hydration that creates operation authority;
- selected-only operation/card/removal/worker/Body 3 refresh;
- one app lifecycle phase/router and a real process/ownership/authority drain barrier;
- process/performance instrumentation and physical scale acceptance;
- lifecycle doctor/install/update/repair/uninstall compatibility for the preference document; and
- governed Draft-PR review, merged-main installation, and post-install physical acceptance.

### 2.2 Frozen v2 strengths

The implementation SHALL integrate, not rewrite, these verified safeguards:

1. `RepositoryDiscovery.validateRuntimeEligibility` operation-time safety checks.
2. `RepositoryAuthorityStore` fresh clone matching, `RepositoryHandle` revalidation, expected
   identity/revision checks, fsynced same-directory atomic replacement, and post-write verification.
3. `RepositoryCardsWindow` exclusion of disabled rows from review payloads.
4. `WorkerSession` verified stop/reap behavior and `WorkerPostReapEvidence`.
5. Existing `LifecycleGate` evidence categories, folded into the new top-level router.
6. Effective Git origin/rewrite/transport logic as authority; direct `.git/config` parsing remains
   an advisory chooser hint only.
7. Every current Codable schema and coding key for `RepositoryCandidate`,
   `RepositoryAuthorityDocument`, `RepositoryCard`, `PlannedOperation`, Body 3 plan/event/report
   values, `WorkerRequest`/`WorkerWireMessage`, `RepositoryResult`, `RunEvent`, and `RunReport`.
8. Existing exact Git/AWA command grammars, operation locks, postflight, redaction, retention,
   cancellation escalation, install attestation, and no-test-seam production checks.

### 2.3 Explicit non-goals

- no new repository action, repair class, cleanup class, Git command, network client, or remote
  mutation;
- no change to v2 recommendation, retention, AWA-advisory, force, ref-CAS, or report semantics;
- no migration of preferences into `RepositoryAuthorityDocument`;
- no recursive general-purpose filesystem indexer, Spotlight dependency, database, daemon, watcher,
  scheduler, telemetry, analytics, or recurring infrastructure;
- no paid GitHub Actions runner or self-hosted Actions runner;
- no accessibility expansion;
- no cpp/bootstrap/orchestrator/controller/VPS/chaos-scheduler change;
- no feature-branch installation, live repository cleanup, or target-repository mutation during
  implementation acceptance; and
- no broad production discovery retained “for convenience.”

## 3. Threat, race, and failure model

This remains an accidental/race integrity boundary for one local user account, not a defense
against a malicious same-UID process or root.

| Threat/race | Required defense | Failure result |
|---|---|---|
| Catalog path contains symlink, replacement, escape, or excessive breadth | Policy-relative bounded no-follow enumeration; aggregate budgets; no arbitrary recursion | Row disabled or whole catalog degraded; no child/network/authority |
| Advisory origin is stale or forged | Treat direct `.git/config` text only as a label/default hint | Effective identity remains unknown until heavy selected hydration |
| Preference file changes between render and Save | File identity + document identity + revision CAS | Conflict shown; reload/reapply, never overwrite |
| Governed root is replaced between chooser and Continue | Reopen descriptor, bind identity, rebuild catalog, compare root identity and locator | Continue fails closed and returns to chooser recovery |
| Locator is absolute, ambiguous, hidden, excluded, artifact, reference, no-touch, duplicate, or changed | Normalize and reject before repository descriptor/hydration | Disabled/skipped with exact reason; never payload |
| Preference intent is confused with Git authority | Separate types/targets; no conversion from preference to verified capability | Compile-time construction failure plus runtime negative tests |
| Onboarding proposal becomes stale before confirmation | Existing authority-store fresh clones/descriptor/CAS checks | No authority change; selected hydration restarts |
| Selected hydration returns an unselected repository | Exact scope membership and root-bound identity checks before recording | Refuse result; no card/state/child admission |
| Body 3 per-node refresh broadens to all repositories | Exact-repository scope derived from immutable plan node | Refuse before `Body3ExecutionContext.record` or child start |
| Double click, menu/hotkey overlap, stale controller, or stale task completion | One `@MainActor` reducer with generation-bound effects and atomic admission transitions | Later event is ignored or acknowledged without duplicate work |
| Save commits while chooser generation changes | Observe rename linearization and report persistence before UI staleness suppression | Saved truth retained and surfaced on current/reopened chooser |
| Cancel/Quit closes admission while a child remains | Cancellation token plus ownership settlement and drain barrier | UI stays Cancelling/Draining; process does not terminate |
| Directory fsync fails after preference rename | Rename remains the linearization point; reread and surface durability uncertainty | Never claim “not saved”; block another Save until reload |

## 4. Process-free catalog and first-screen contract

### 4.1 Target and API boundary

Add a Swift target `DevMainSyncCatalog` in `Package.swift`. `DevMainSyncCore` depends on it;
`DevMainSyncApp` imports it directly. The target has no dependency on Core or App and owns:

```text
RepositorySelectionCandidate
RepositorySelectionLocator
RepositorySelectionPolicyDisposition
RepositorySelectionCatalog
RepositorySelectionCatalogLimits
RepositorySelectionCatalogResult
RepositorySelectionPreferenceDocument
RepositorySelectionPreferenceEntry
```

Its sole discovery entry is synchronous:

```swift
public static func discoverCatalog(
    configuration: RepositorySelectionCatalogConfiguration
) -> RepositorySelectionCatalogResult
```

The configuration contains already-open host-policy/config descriptors, configured governed-root
descriptors and identities, a monotonic deadline, and aggregate limits. It contains no executable
path, runner, `RunAuthority`, operation lease, task closure, URL, credential, repository handle, or
mutation capability.

The entire target is structurally forbidden from referencing or linking:

- `Process`, `NSTask`, `posix_spawn*`, `fork`, `vfork`, `exec*`, `system`, `popen`;
- `/usr/bin/git`, `gh`, worktree helpers, scripts, shell interpreters, arbitrary executables;
- `URLSession`, `NSURLSession`, Network.framework, sockets, `connect`, DNS APIs;
- `RunAuthority`, `LifecycleAdmissionAuthority`, `RepositoryHandle`,
  `DescriptorProcessRunner`, `ClosedProcessRunner`, `DiscoveryGitProbe`; or
- detached tasks/operation queues that can spawn or admit child work.

Foundation value/data/string APIs and Darwin descriptor-relative read-only filesystem calls are
allowed. A build/object-symbol/source audit enforces this boundary in addition to runtime tests.

### 4.2 Lightweight model

`RepositorySelectionCandidate` is chooser-only and is never Codable into a worker, operation, log,
or report. It contains only:

- normalized logical repository ID when direct config text yields one supported advisory GitHub
  origin, otherwise a deterministic local catalog ID;
- `RepositorySelectionLocator`: configured governed-root logical key plus normalized relative path
  components, never an absolute repository authority;
- bounded display label and compact policy-relative location;
- policy disposition and visibility;
- selection eligibility plus one precise disabled reason;
- advisory origin hint and its source (`directConfig` or `unavailable`);
- catalog root identity and generation; and
- default-selection state derived from the preference snapshot.

It contains no `RepositoryCandidate`, `LocalClone`, root/common-directory Git identity, effective
origin, writability proof, graph metadata, worktree topology, operation eligibility, authority
record, card, planned operation, or removal candidate.

### 4.3 Aggregate limits and deterministic degradation

All limits apply across the complete call, not once per directory:

| Limit | Production value | Counting rule |
|---|---:|---|
| Configured governed roots | 8 | Extra roots degrade the whole catalog |
| Relative traversal depth | 4 components | Descend only through policy-declared shelf prefixes; never arbitrary recursion |
| Directory entries observed | 4,096 | Count every returned entry, including skipped/hidden entries |
| Directories opened | 1,024 | Count root and shelf directories across all roots |
| Policy/config files opened | 512 | Count all bounded host-policy and optional direct `.git/config` files |
| Aggregate policy/config bytes | 2,097,152 | Sum bytes read across all files; no per-file reset |
| Direct `.git/config` bytes | 65,536 each, included above | Read regular, owned, single-link, no-follow files only |
| Candidate rows | 512 | Count visible enabled and disabled rows |
| Elapsed time | 750 ms internal deadline | Check before/after each open/read/enumeration unit |

Traversal is deterministic: configured root order, then Unicode-normalized bytewise relative
component order. It may inspect the governed root itself and only policy-declared durable shelf
paths needed for `~/dev`, including `capabilities`, `personal`, `affirm/src`, and `affirm/vendor`;
it stops at a direct `.git` entry and never descends inside a repository. Hidden implementation
directories and declared artifacts/test fixtures are omitted before repository/config access.

Any aggregate limit, deadline, unreadable required policy, changed descriptor identity, malformed
policy, or unsafe entry returns a bounded partial projection plus a catalog-level degraded reason.
The chooser remains open with **Reload**, **Cancel**, and **Quit**, but **Continue** and **Save as
defaults** are disabled because the catalog is not complete. It never silently treats a sorted
prefix as the complete repository set.

### 4.4 Visibility and usable chooser

The chooser must:

- appear before any heavyweight inventory task, run authority, child, or network admission;
- show every catalogued durable in-scope repository;
- show policy-visible excluded/protected/reference/no-touch/unsafe entries disabled with exact
  reasons;
- omit policy-declared artifacts, confirmed fixtures, and hidden implementation directories;
- apply valid saved defaults to eligible rows only and show unresolved saved entries separately;
- support selection/deselection, **Save as defaults**, **Continue**, **Cancel**, and **Quit**;
- expose **Change/Manage saved selection** whenever cards/reports are visible later; and
- acknowledge Cancel immediately, then remain visibly Cancelling if selected hydration must drain.

The first usable chooser acceptance target is at most **1.000 second** from action entry to enabled
row interaction at representative 50+ repository scale, with p95 and maximum reported separately.
The internal 750 ms catalog deadline leaves UI publication margin. Heavyweight discovery is not on
that path.

Before Continue, acceptance instrumentation must prove:

```text
Git children = 0
gh children = 0
helper/script children = 0
all other children = 0
network attempts/work = 0
run/lifecycle/operation authority acquisitions = 0
```

## 5. Saved-defaults document and complete transition table

### 5.1 Document schema

The preference file is
`selection-preferences.json` with schema
`dev-main-sync-repository-selection-preferences/v1` in the existing private state directory:

```text
schema: fixed string
documentID: lower-case UUID
revision: UInt64
entries:
  - repositoryID: normalized logical repository ID
    locator:
      governedRoot: configured logical root key such as ~/dev
      components: nonempty relative path components
```

Records are sorted by repository ID then locator. Duplicate repository IDs or duplicate normalized
locators are invalid. Absolute paths, empty/dot/parent/hidden components, controls, separators
inside components, artifacts, credentials, origins with userinfo, executable paths, authority
identities, OIDs, timestamps, tokens, and arbitrary metadata are forbidden. The file contains intent
only and no secret material.

`RepositorySelectionPreferenceStore` lives in Core and uses `SecureStateDirectory`. Reads require a
regular owner-owned single-link `0600` file, at most 1 MiB, opened no-follow and identity-checked
before/after. Save compares all of:

1. expected named-file `FileIdentity` or expected absence;
2. expected `documentID` or absent-lineage token; and
3. expected `revision`.

A valid update keeps `documentID` and increments `revision` exactly once; creation uses a new UUID
and revision `1`. `UInt64.max` is readable but not writable. Save writes one same-directory
owner-only temp file, fsyncs it, verifies the CAS again, and atomically renames it. The successful
rename is the linearization point. Fsync the containing directory where supported/required, reread
the installed document, and never report success from stale pre-rename state.

### 5.2 State and transition table

| Observed state/event | Chooser behavior | Save transition | Continue/recovery behavior |
|---|---|---|---|
| File absent | No rows preselected; explain that defaults are not yet saved | CAS expected absence → new `documentID`, revision 1 | Manual selection may Continue; Save creates defaults |
| Valid supported document | Apply only exact ID+locator matches; unresolved entries remain visible | Identity+documentID+revision CAS → same ID, revision +1 | Continue uses current checked rows, never authority |
| File externally changed before Save | Keep operator's unsaved checked rows in memory and show conflict | Refuse before rename; no overwrite | **Reload saved defaults** then reapply choices; operator explicitly retries |
| Malformed JSON/shape/value | Show **Saved defaults unavailable**; do not infer or reset | Save disabled until explicit **Recover defaults…** | Manual session selection may Continue; recovery replaces only after current file-identity confirmation and preserves exact bounded old bytes in one fixed owner-only recovery slot |
| Unsafe ownership/mode/type/link/size | Do not read bytes; show exact unsafe class | No write, rename, chmod, unlink, or recovery mutation | Manual session selection may Continue; **Retry inspection**, read-only doctor guidance, or Quit |
| Newer unsupported schema | Show read-only incompatibility without parsing entries | Never overwrite or downgrade | Manual session selection may Continue without defaults; update app or Quit |
| Unknown/missing saved IDs or locators | Render each under **Saved but not currently found**; do not select or drop it silently | Explicit Manage choice retains or removes each unresolved entry | Unresolved entries never enter Continue payload; resolved rows may Continue |
| Duplicate repository IDs or locators | Treat whole document as malformed; never pick one | Same explicit recovery path as malformed | No silent dedupe/reset |
| Write failure before rename | Existing document and in-memory choices remain | Report **Defaults were not saved**; clean only the owned temp | Retry from unchanged CAS snapshot or reload if identity changed |
| Rename succeeds, then directory fsync/reread fails | Record that persistence linearized before any generation/UI suppression | Do not claim failure or retry write automatically | Show **Defaults saved; durability confirmation needs reload** and block another Save until reload |
| Rename succeeds, then notification/controller generation changes | Persistence completion event is routed before stale-controller rendering decisions | Saved revision remains authoritative | Current chooser/report gets a concise saved acknowledgement, or the next Manage view must surface it |
| Revision is `UInt64.max` | Load entries read-only and explain revision exhaustion | No wrap/reset | Manual Continue allowed; explicit recovery starts a new documented lineage |
| Explicit recovery confirmed | Preserve bounded malformed bytes in fixed recovery slot; replace only if named identity is unchanged | New `documentID`, revision 1 through the same temp/fsync/rename path | Reopen Manage view and show new lineage plus recovery receipt |

Recovery is preference-only. It cannot modify `repository-authorities.json`, repository bytes, Git
state, policy, or worker payloads. No state above silently overwrites, silently resets, silently
deduplicates, or silently discards an unresolved entry.

## 6. Continue binding, selected hydration, and authority staging

### 6.1 Atomic Continue admission

One `@MainActor` router event handles Continue. It atomically:

1. verifies the current phase/generation and complete catalog;
2. closes chooser admission so double-click, Return, menu, and stale controllers cannot submit
   again;
3. snapshots one immutable sorted `RepositorySelectionIntent`;
4. disables selection/Save/Continue and shows selected count plus hydration progress;
5. starts no work when selection is empty; and
6. hands the immutable intent to Core without any `RepositoryCandidate` or operation value.

### 6.2 Fresh root- and locator-bound scope

`SelectedRepositoryScopeBinder.bind(intent:)` must perform this order:

1. reread current bounded host policy;
2. open each configured governed root no-follow and verify owner/type/mode;
3. capture the root descriptor identity and canonical physical path;
4. rebuild the complete process-free catalog under the same aggregate bounds;
5. normalize and match each selected repository ID plus locator exactly once;
6. reject unknown, missing, duplicate, or ambiguous ID/locator mappings;
7. reject absolute, empty, dot, parent, hidden, artifact, excluded, reference, no-touch, replaced,
   or policy-invisible locators;
8. traverse every relative component using descriptor-relative `openat` with
   `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, verifying ownership/mode and root identity at every step;
9. open the selected repository root descriptor only after all lexical/policy checks pass; and
10. emit one immutable `ValidatedSelectedRepositoryScope` bound to policy digest, catalog
    generation, governed-root identity, normalized IDs/locators, and retained descriptor-safe
    identities.

No absolute path from a preference or chooser is accepted. Directory replacement between chooser
and Continue, or during component traversal, fails closed and returns to the chooser with
**Repository locations changed — reload before continuing**.

### 6.3 Type-level authority stages

The production type graph is:

```text
RepositorySelectionIntent
  → ValidatedSelectedRepositoryScope
  → SelectedRepositoryHydrationEvidence + [CanonicalAuthorityProposal]
  → operator confirmation through RepositoryAuthorityStore
  → fresh ValidatedSelectedRepositoryScope
  → VerifiedRepositoryAuthorityCapability
  → RepositoryCard / PlannedOperation / RemovalCandidate
  → AuthorizedOperationEnvelope
  → confirmation / WorkerRequest / RunCoordinator
```

Rules:

- initial selected hydration produces evidence and onboarding proposals only;
- if selected repositories lack canonical authority, show one selected-scope onboarding panel with
  explicit roots and confirm/cancel controls;
- confirmation commits only through the existing `RepositoryAuthorityStore` fresh matching clone,
  `RepositoryHandle`, expected identity/revision, descriptor, and CAS checks;
- after confirmation, or immediately when no onboarding write is needed, discard first-pass
  hydration and perform a fresh selected-only hydration;
- only that second pass can create `VerifiedRepositoryAuthorityCapability`;
- the capability constructor is internal to the selected hydrator and requires one fresh matching
  authority record, canonical-authority uniqueness, root/common-directory identity, raw/effective
  origin parity, effective transport, policy digest, graph metadata, worktree topology, and current
  operation eligibility;
- `RepositoryCard`, `PlannedOperation`, `RepositoryInventoryRemovalCandidates.make`, confirmation
  rows, and worker request construction require the capability or an
  `AuthorizedOperationEnvelope` derived from it;
- Codable decoding preserves wire compatibility but yields untrusted decoded values that must be
  rewrapped only after fresh capability validation; and
- no preference/catalog/default type has an initializer, conversion, protocol conformance, or
  helper capable of constructing authority, card, operation, removal, confirmation, or worker
  payload values.

Disabled rows remain presentation-only and are excluded from selection, review, confirmation,
Body 3 plans, and `WorkerRequest`, preserving the current review-payload strength.

## 7. Selected-only heavy work and linear refresh

### 7.1 Production API closure

Replace production parameterless/broad APIs with selected scope:

```text
RepositoryDiscovering.discover(scope: ValidatedSelectedRepositoryScope)
RepositoryInventoryDiscovering.discoverInventory(scope: ValidatedSelectedRepositoryScope)
RepositoryInventoryDiscovery.discoverInventory(scope:..., authority:...)
RunCoordinator.runBody3(plan:..., selectedScope:...)
```

Delete in production:

- parameterless `RepositoryDiscovering.discover()`;
- parameterless `RepositoryInventoryDiscovering.discoverInventory()`;
- production parameterless `RepositoryDiscovery.discover()`;
- production parameterless `RepositoryInventoryDiscovery.discoverInventory()`;
- `RunCoordinator.runBody3`'s optional no-argument `inventoryProvider`;
- all-repository fallback in AppDelegate onboarding/canonical-root refresh;
- production worker broad inventory admission; and
- any helper that reconstructs selected work by rescanning all governed repositories.

Broad fixture builders may remain only inside `#if DEV_MAIN_SYNC_TESTING` and must be absent from the
production binary/source-call audit. Live diagnostics must use the process-free catalog or require
an explicit validated selection; they cannot retain an accidental production broad hook.

### 7.2 Scope behavior

After Continue, the immutable validated scope is the maximum set any heavy phase may touch.
Heavy discovery:

- iterates selected locators once in deterministic order;
- performs Git/gh/worktree/process/file inspection only beneath those bound descriptors and existing
  explicitly registered selected-repository worktrees;
- rejects any discovered repository ID, locator, root/common identity, origin, or policy result not
  in scope before recording it;
- reports progress as `Hydrating n of N — owner/repository`, plus bounded phase text;
- supports Cancel with immediate acknowledgement, closes future child admission, reaps admitted
  children, releases authority, then returns to the still-editable chooser; and
- is `O(selected repositories + selected repository topology)`, never
  `O(selected × all catalog repositories)`.

For Body 3, derive an exact one-repository scope for every reinspection, retention, final
confirmation refresh, removal refresh, residue refresh, and policy invalidation node. Validate
returned membership before `Body3ExecutionContext.record`, prepared-row mutation, event recording,
or child start. A per-node result for another repository is a confused-deputy refusal, not context.

The unchanged production worker wire carries selected operations. `WorkerMain.dispatch` derives
their unique normalized IDs/locators, binds a fresh selected scope from current policy/root
descriptors, hydrates only those repositories, obtains verified capabilities, wraps decoded
operations in authorized envelopes, and only then invokes `RunCoordinator`. It never calls broad
inventory.

### 7.3 Poison and scale proof

Fixtures must create at least 51 catalog repositories, select 1–3 safe repositories, and make every
unselected repository poisonous through independent sentinels:

- unreadable/unsafe repository internals;
- a Git executable trap;
- a gh/network trap;
- a worktree helper trap;
- an access observer that fails on any unselected path; and
- changed/ambiguous origin/topology.

Catalog enumeration may observe bounded shelf entry names and advisory config only. After Continue,
tests require zero unselected repository content opens, Git/gh/helper invocations, process
admissions, network attempts, cards, events, operations, or worker payloads. Runtime and process
counts for selecting 1 and 3 repositories must stay within a fixed additive envelope independent of
whether the catalog has 3 or 51 repositories.

## 8. One app lifecycle and real drain

### 8.1 Phase enum and router

Add one `@MainActor AppLifecycleRouter` and one exhaustive phase enum. Case names may be adjusted to
Swift style, but the semantic states are fixed:

```text
idle
chooser
savingDefaults
bindingSelection
hydratingSelected
onboardingAuthority
cardsAndReview
executing
cancelling
drainingForQuit
```

Associated state carries generation, immutable selection/scope identity, owned task token, active
controller identity, cancellation/drain evidence, and deferred Quit. AppDelegate routes all
start/menu/hotkey, Continue, Save, Manage/Change, onboarding, review, Cancel, task completion,
worker completion, close, and Quit events through the reducer. Existing `LifecycleGate` becomes a
router guard/evidence adapter; parallel booleans may not remain as independent authority.

### 8.2 Ordering rules

1. Continue, Manage/Change, Cancel, and Quit each change phase before launching effects.
2. A phase/generation admits each user event at most once; double clicks and menu/hotkey overlap are
   ignored with stable acknowledgement.
3. Stale controllers cannot emit accepted events after phase transition.
4. Task completion first settles its owned task and child/authority evidence, then services deferred
   Quit, then decides whether a controller is still current, then renders.
5. Preference Save completion records whether rename linearized and publishes persistence outcome
   before stale-generation UI suppression.
6. Manage/Change from cards/report returns to a fresh process-free chooser, preserving no operation
   authority and starting no heavy work until the next Continue.
7. Cancel during binding/hydration/onboarding closes admission, cancels pending confirmation,
   acknowledges visibly, waits for owned work to settle, then rebuilds a process-free chooser.
8. Quit from chooser with no work terminates after proving no ownership; Quit during any owned work
   becomes deferred and enters draining.
9. No controller close, Task deallocation, token cancellation, or “no current window” observation
   counts as drain proof.

### 8.3 Drain barrier

`AppDrainBarrier` is satisfied only when one generation-bound snapshot proves all:

- process admission closed for catalog, hydration, worker, Body 3, and confirmation effects;
- every owned async task completion has been observed on the router;
- every admitted Git/gh/helper/worker child is reaped;
- `WorkerPostReapEvidence.childDrainVerified == true` for worker paths;
- worker ownership protocol is complete or the existing evidence-safe no-child case applies;
- Body 3 scheduler workers are terminal and confirmation waiters settled;
- inventory/hydration run authority and operation lease are released;
- run/lifecycle/operation authority is released;
- no stop/takeover/authority commit/save transaction remains;
- preference linearization outcome has been recorded; and
- the barrier snapshot belongs to the current Quit generation.

Only then may `terminateAfterConfirmedQuit` call app termination. Failed or unverifiable drain shows
**Quit paused — Dev Main Sync could not prove all work stopped** and remains running with read-only
diagnostics; it never sends an unverified signal or terminates anyway.

Adversarial tests cover task-first/worker-first/report-first/reap-first/authority-first ordering,
double Quit, Quit during Save before and after rename, Quit during catalog publication, Continue
plus Quit overlap, Cancel plus Quit overlap, stale controller callbacks, stale generations,
confirmation wait, stubborn children, post-reap failure, authority-release delay, and successful
deferred termination exactly once.

## 9. Performance and process instrumentation

Add one test-only `DevMainSyncAdmissionProbe` used by all app-owned process/network/authority
admission points and one parent-side physical harness. Production behavior remains closed and does
not emit telemetry.

Evidence layers:

1. **Target dependency audit:** `DevMainSyncCatalog` links no Core/App/process/network symbols.
2. **Source/object symbol audit:** fail on every forbidden API/symbol/path in §4.1.
3. **Injected admission probe:** fail immediately if any child/network/authority admission occurs
   before the Continue event.
4. **Parent process census:** capture descendants by parent/process-group identity throughout the
   pre-Continue interval and require none.
5. **Network-denied physical run:** run the isolated testing app with network denied and local
   sentinels; require zero attempted network-admission records, not merely zero successful requests.
6. **Monotonic timing:** record action entry, window visible, first enabled row, Continue, first
   child, hydration complete, and report. Require first enabled row ≤1.000 s; require first child
   time strictly after Continue.

Representative scale is at least 51 durable catalog entries distributed across the real supported
shelf depths, including writable, protected, no-touch, reference, artifact, hidden, unsafe, and
unknown-origin cases. Run 20 cold fixture trials and report p50, p95, and maximum; all 20 must meet
the 1-second gate. A live target-Mac run after merged-main install repeats the child/network
pre-Continue proof and records catalog/selected counts without recording private repository
content.

## 10. Migration, compatibility, rollback, and recovery

### 10.1 Compatibility

- `RepositoryCandidate` remains the heavyweight physical snapshot. Do not rename, repurpose,
  remove, or add coding keys.
- All current Codable/wire/worker/operation/report formats and legacy fixtures remain byte-compatible.
- `repository-authorities.json` schema and records remain unchanged. Absolute canonical roots stay
  only in that authority document and are freshly revalidated.
- `selection-preferences.json` starts absent; no authority record or old selection is auto-migrated
  into it.
- First v3 launch therefore shows no selected defaults. The operator can select, Save, Continue, or
  Continue without saving.
- Existing v1/v2 logs, reports, authority, retention artifacts, and installed state remain readable
  and preserved.
- Lifecycle install/update/repair/uninstall/doctor adds the preference file and fixed recovery slot
  to its exact state allowlist, validates their schemas/modes/ownership, preserves them on
  update/repair, and reports preservation on uninstall.
- Direct config origin text may prefill a logical chooser ID only; fresh effective Git origin and
  transport remain authoritative after Continue.

### 10.2 Runtime recovery

- Catalog degradation: keep chooser open; Reload after the named bound/policy condition changes.
- Selection binding drift: discard scope/evidence and return to fresh chooser.
- Hydration failure: retain checked intent in memory, show per-selected failure, allow Retry,
  Change selection, Cancel, or Quit.
- Onboarding conflict: persist nothing, reload selected evidence, and ask again only for still-missing
  authority.
- Preference conflict/corruption/unsafe/newer state: follow §5.2 exactly.
- Cancellation: preserve already completed authority/preference writes truthfully; no operation
  starts unless the second fresh capability pass completes.
- Interrupted execution: retain v2 event/ref/postflight recovery behavior; never replay an unfinished
  operation.

### 10.3 Rollback

Before merge, close/revert the Draft PR; no installed state exists. After merge but before install,
use a governed forward revert and do not install the defective revision.

After v3 has written preferences, rollback uses a forward compatibility commit that may restore the
prior chooser/execution behavior only if it retains safe read/allowlist/preservation support for
`selection-preferences.json` and its recovery slot. Do not install a byte-old v2 bundle that would
misclassify valid v3 state. A full preference-format rollback requires an explicit export/preserve
receipt and successor plan; never silently delete or reset defaults.

Repository mutations already completed under v2/v3 are never reversed automatically. Authority
records, logs, retention artifacts, and preference recovery bytes remain protected. Any drain,
scope, authority, or compatibility uncertainty blocks rollback installation until doctor passes.

## 11. Exact implementation and file boundary

### 11.1 New files

- `global/tools/dev-main-sync/Sources/DevMainSyncCatalog/RepositorySelectionCatalog.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCatalog/RepositorySelectionPolicy.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCatalog/RepositorySelectionPreferences.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/RepositorySelectionPreferenceStore.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/SelectedRepositoryScope.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/SelectedRepositoryHydration.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/RepositoryChooserWindow.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/AppLifecycleRouter.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/DM3PreflightSelfTests.swift`
- `global/tools/dev-main-sync/scripts/v3-preflight-acceptance.sh`

### 11.2 Expected modified files

- `global/tools/dev-main-sync/Package.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/Models.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/RepositoryDiscovery.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/RepositoryInventoryDiscovery.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/RepositoryModelV2.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/RepositoryLifecycle.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/Body3Coordinator.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/Coordinator.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncCore/InstallationLifecycle.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/AppDelegate.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/RepositoryCardsWindow.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/Body3RunWindow.swift` only for selected
  hydration/cancellation/drain presentation
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/Worker.swift`
- `global/tools/dev-main-sync/Sources/DevMainSyncApp/M6Harness.swift`
- `global/tools/dev-main-sync/Tests/DevMainSyncSelfTests/main.swift`
- `global/tools/dev-main-sync/scripts/source-doctor.sh`
- `global/tools/dev-main-sync/scripts/verify-m1.sh`
- `global/tools/dev-main-sync/scripts/verify-m5.sh`
- `global/tools/dev-main-sync/scripts/verify-m6.sh`
- `global/tools/dev-main-sync/install.sh`
- `global/tools/dev-main-sync/README.md`

Existing v2 self-tests and scripts are modified only when their compile-time construction must pass
the new trusted capability boundary; their semantic assertions must not be weakened. No file
outside this capability, `.github/scripts/verify-skills.sh` to invoke the new acceptance script,
and this already-frozen plan/index is in the implementation boundary.

## 12. Requirements, deterministic tests, and blocker traceability

### 12.1 Closed requirements

| IDs | Requirement |
|---|---|
| `V3-CAT-01–08` | Separate lightweight candidate/target; synchronous process-free API; aggregate limits; deterministic visibility/degradation; immediate usable chooser; zero pre-Continue process/network/authority |
| `V3-PREF-01–10` | Separate intent schema; complete Save/Manage lifecycle; identity+revision CAS; atomic durability; all §5.2 states; no secret/authority; no silent reset/overwrite |
| `V3-BIND-01–08` | Atomic Continue; fresh policy/root/catalog; normalized exact matching; descriptor-relative no-follow traversal; full rejection set; root identity binding |
| `V3-AUTH-01–06` | Evidence/proposal first pass; explicit onboarding; fresh second pass; verified capability-only construction; retained runtime checks; disabled-row exclusion |
| `V3-SCOPE-01–08` | Immutable selected scope; no production broad API/fallback; exact Body 3 node refresh; production worker selected hydration; out-of-scope refusal; linearity/poison proof |
| `V3-LIFE-01–09` | One MainActor router; atomic action admission; save-before-stale ordering; useful progress/cancellation/recovery; ownership settlement; deferred Quit; real drain barrier |
| `V3-PERF-01–05` | ≤1-second physical first screen; 20-trial timing; zero pre-Continue children/network; first child after Continue; small-selection versus 51-entry scale |
| `V3-COMP-01–05` | Preserve heavyweight and all current Codable/wire formats; separate preferences/authority; lifecycle compatibility; legacy evidence; effective origin authority |
| `V3-GOV-01–06` | One integrated Draft PR; focused/full verification; Bugbot+security loops; explicit ready gate; reviewer-App merge; exact-main install; no paid/new recurring infrastructure |

### 12.2 Deterministic test matrix

| Test ID | Required proof |
|---|---|
| `DM3-T01 preserve-heavy-wire-model` | Baseline canonical encodings/decodings and coding keys for every §2.2 model remain byte/semantic compatible; `RepositoryCandidate` stays heavyweight and absent from chooser state |
| `DM3-T02 catalog-boundary` | Catalog target source/import/object/link audit contains no process, runner, authority, Git/gh/helper, task-spawn, or network path |
| `DM3-T03 catalog-limits-visibility` | Every aggregate root/depth/entry/directory/file/byte/row/time boundary; deterministic order; visible disabled policy rows; omitted hidden/artifact fixtures; incomplete catalog disables Continue/Save |
| `DM3-T04 chooser-defaults` | Immediate interactive rows; select/deselect; Save, Continue, Cancel, Quit; later Manage/Change; unresolved defaults visible; disabled rows never payload |
| `DM3-T05 preference-transition-table` | Every §5.2 row including external CAS conflict, duplicate IDs, unsafe file, newer schema, pre-rename failure, post-rename fsync/generation outcome, revision exhaustion, explicit recovery |
| `DM3-T06 locator-root-binding` | Fresh policy/root/catalog; all forbidden locator classes; descriptor-relative traversal; root/repository replacement before/during Continue; duplicate/ambiguous ID+locator rejection |
| `DM3-T07 authority-stages` | Preferences cannot compile/convert into authority; first hydration emits evidence/proposals only; authority confirmation uses current store safeguards; only fresh second pass yields verified capability |
| `DM3-T08 capability-construction` | Card, operation, removal, confirmation, authorized envelope, and worker payload constructors reject absent/stale/wrong capability; current runtime eligibility checks still execute |
| `DM3-T09 body3-broad-refresh-confused-deputy` | Every Body 3 refresh is exact-node selected scope; injected foreign repository result is rejected before context/event/child state; no optional no-arg provider |
| `DM3-T10 selected-worker-poison` | Production-like worker derives selected scope from unchanged wire; 1–3 selected among 51; no unselected access/process/network/payload; decoded operations require reauthorization |
| `DM3-T11 lifecycle-ordering` | Exhaustive phase/event table; Continue/Manage/Cancel/Quit overlap; double click/hotkey/menu; stale controllers/tasks; save rename observed before generation suppression |
| `DM3-T12 admission-close-is-not-drain-proof` | Closing admission alone cannot satisfy Quit; task ownership, all reaps, worker post-reap, Body 3 settlement, preference outcome, and authority release are individually required |
| `DM3-T13 scale-linearity` | 3-entry versus 51-entry catalog with selection 1/3; heavy file/process counts and time follow selected topology, not catalog size or selected×catalog |
| `DM3-T14 physical-first-screen` | 20 cold trials; all usable chooser times ≤1.000 s; pre-Continue child/network/authority counts zero; first child strictly after Continue; selected progress/cancel recovery usable |
| `DM3-T15 lifecycle-migration` | Absent/valid/malformed/unsafe/newer preference state across install/update/repair/doctor/uninstall/rollback cuts; authority/log/retention/wire fixtures unchanged |
| `DM3-T16 production-governance` | No production broad discovery/test seam/forbidden symbol; exact source/package/command audits; all retained v2 suites and owner verifier; no install command before merge |

### 12.3 Six blocker closure map

| Verifier blocker ID | Requirement/design closure | Implementation task | Detecting test |
|---|---|---|---|
| `preserve-heavy-wire-model` | §2.2 items 7–8, §4.2, §10.1; `V3-COMP-01–05` | Task 1 locks baseline bytes before constructor/API edits | `DM3-T01`, `DM3-T15` |
| `admission-close-is-not-drain-proof` | §8.3 barrier requires independent task/reap/post-reap/authority evidence; `V3-LIFE-07–09` | Task 6 replaces flag-based Quit completion | `DM3-T12` |
| `body3-broad-refresh-confused-deputy` | §7 exact-node scope and pre-record rejection; `V3-SCOPE-03–06` | Task 5 removes `freshInventory` broad fallback/provider | `DM3-T09` |
| `define-unusable-file-transition-table` | Complete §5.2 state/action/retry/recovery table; `V3-PREF-04–10` | Task 3 implements every row without silent reset | `DM3-T05`, `DM3-T15` |
| `locator-resolution-not-root-descriptor-bound` | §6.2 descriptor-bound root and component traversal; `V3-BIND-02–08` | Task 4 binds fresh selected scope | `DM3-T06` |
| `authority-and-operation-construction-share-phase` | §6.3 staged types and second hydration; `V3-AUTH-01–06` | Task 4 closes constructors behind verified capability | `DM3-T07`, `DM3-T08` |

No blocker is closed by prose alone: each maps to a production task and a deterministic negative
test that fails if the old shortcut returns.

## 13. Work items — one integrated implementation body

### Task 1: Freeze compatibility and add the red architecture matrix

**Files:**

- Create `Sources/DevMainSyncCore/DM3PreflightSelfTests.swift`
- Modify `Tests/DevMainSyncSelfTests/main.swift`
- Modify existing v2 fixture/test helpers only as needed to expose canonical baseline encodings

**Symbols to inspect first:**

- `RepositoryCandidate`, `RepositoryAuthorityDocument`, `RepositoryCard`, `PlannedOperation`,
  `RunReport` in `Models.swift`/`RepositoryModelV2.swift`
- `Body3BatchPlan`, `Body3LogRecord`, `Body3BatchReport`
- `WorkerRequest`, `WorkerWireMessage`
- current `V2Body1SelfTestRunner` through `V2Body4SelfTestRunner`

**Interfaces:**

- Consumes the exact baseline's current model initializers and canonical sorted JSON encoding.
- Produces `V3PreflightSelfTestRunner` with focused selectors for `DM3-T01` through `DM3-T15`.
- Captures representative baseline wire bytes/digests before changing construction APIs.
- Does not add a new production coding key, schema value, or compatibility decoder.

- [ ] Add `--v3-preflight-only` and focused `--dm3-t01-only` through
  `--dm3-t15-only` arguments to the existing self-test executable.
- [ ] Construct nontrivial representative values for every format named in `DM3-T01`, encode with
  sorted keys, decode, and pin exact bytes or SHA-256 plus semantic equality.
- [ ] Add compile-time negative fixture targets/helpers proving selection/preference types cannot
  satisfy capability-only constructors after Task 4.
- [ ] Add initially red runtime tests for pre-Continue process/authority admission, broad API
  absence, Body 3 foreign-result rejection, worker poison isolation, lifecycle ordering, and drain.
- [ ] Run the unchanged v2 focused suites before implementation and record their pass/digest
  baseline.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/v2-body1-acceptance.sh
./scripts/v2-body2-acceptance.sh
./scripts/v2-body4-acceptance.sh
```

The baseline has no tracked `scripts/v2-body3-acceptance.sh`. Run its existing Body 3 selector
directly with the same isolated build recipe used by the other acceptance scripts:

```bash
CAPABILITY="$(pwd)"
. "$CAPABILITY/scripts/owned-cleanup.sh"
SCRATCH="$(mktemp -d /private/tmp/dev-main-sync-v3-baseline-body3.XXXXXX)"
trap 'status=$?; dms_reap_owned_root_helpers "$SCRATCH" v3-baseline-body3 || status=1; dms_remove_owned_root "$SCRATCH" v3-baseline-body3 || status=1; exit "$status"' EXIT
export SWIFTPM_MODULECACHE_OVERRIDE="$SCRATCH/swift-module-cache"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache"
BUILD_ARGS=(--package-path "$CAPABILITY" --scratch-path "$SCRATCH/testing" --disable-index-store -Xswiftc -DDEV_MAIN_SYNC_TESTING)
swift build "${BUILD_ARGS[@]}" --product DevMainSync
BIN_DIR="$(swift build "${BUILD_ARGS[@]}" --show-bin-path)"
CORE_OBJECTS=("$BIN_DIR/DevMainSyncCore.build/"*.swift.o)
xcrun swiftc -swift-version 6 -DDEV_MAIN_SYNC_TESTING \
  -module-cache-path "$SCRATCH/module-cache" -I "$BIN_DIR/Modules" \
  -o "$BIN_DIR/DevMainSyncSelfTest" \
  "$CAPABILITY/Tests/DevMainSyncSelfTests/main.swift" "${CORE_OBJECTS[@]}" \
  -framework Foundation
"$BIN_DIR/DevMainSyncSelfTest" --app-executable "$BIN_DIR/DevMainSync" --body3-only
```

**Completion evidence:** exact baseline revision; canonical model digests; unchanged v2 pass
receipts; named red `DM3-T*` failures. Do not commit a failing-only state separately.

### Task 2: Build the process-free catalog and immediate chooser

**Files:**

- Modify `Package.swift`
- Create all three `Sources/DevMainSyncCatalog/*` files from §11.1
- Create `Sources/DevMainSyncApp/RepositoryChooserWindow.swift`
- Modify `AppDelegate.swift`, `RepositoryPolicy.swift`, and `RepositoryCardsWindow.swift`
- Modify `verify-m5.sh`

**Symbols to inspect first:**

- `RepositoryDiscovery.scan`, `RepositoryPolicyLoader.parseWorktreePolicy`,
  `RepositoryPolicy.pathDisposition`
- `startRepositoryInventoryDiscovery`, `presentRepositoryInventory`
- `RepositoryCardSelectionWindowController` loading/rendering states

**Interfaces:**

- Consumes only bounded host-policy/root/config descriptors.
- Produces `RepositorySelectionCatalogResult` and chooser callbacks carrying
  `RepositorySelectionIntent`.
- Heavy `RepositoryCandidate` and inventory APIs are unreachable before Continue.
- Aggregate limits and visibility exactly match §4.

- [ ] Add the isolated target/dependency graph and shared bounded policy projection without creating
  a second semantic source of policy truth.
- [ ] Implement deterministic descriptor-relative shelf enumeration, advisory config parsing, all
  aggregate counters, and deadline degradation.
- [ ] Implement the chooser with every control/disabled reason and unresolved-default section.
- [ ] Route start/menu/hotkey to show the chooser and publish catalog rows without starting heavy
  inventory.
- [ ] Add source, object-symbol, imported-library, process-admission, and network-admission
  assertions.
- [ ] Make `DM3-T02`, `DM3-T03`, and first-screen portions of `DM3-T04/T14` green.

**Verification:**

```bash
cd global/tools/dev-main-sync
swift test
./scripts/verify-m5.sh
```

**Completion evidence:** target dependency graph; aggregate-limit matrix; visibility snapshots;
catalog p50/p95/max; zero pre-Continue process/network/authority ledger.

### Task 3: Implement the complete saved-defaults lifecycle

**Files:**

- Finalize `Sources/DevMainSyncCatalog/RepositorySelectionPreferences.swift`
- Create `Sources/DevMainSyncCore/RepositorySelectionPreferenceStore.swift`
- Modify `RepositoryChooserWindow.swift`, `AppLifecycleRouter.swift`, and `AppDelegate.swift`
- Modify `InstallationLifecycle.swift`, `M6Harness.swift`, `source-doctor.sh`, `install.sh`

**Symbols to inspect first:**

- `RepositoryAuthorityStore.snapshot`, `requireExpectedIdentity`, `replace`
- `SecureStateDirectory`
- state allowlists near `InstallationLifecycle`'s `allowed`/`allowedStateEntries`
- `source-doctor.sh` state entry and authority validation
- authority Save completion ordering in `completeOnboardingCommit` and
  `completeCanonicalRootCommit`

**Interfaces:**

- Consumes normalized chooser intent only.
- Produces one preference snapshot/result with explicit pre/post-linearization status.
- Reuses atomic-write patterns without sharing authority schema or constructors.
- Implements every §5.2 transition in Body 1; none is deferred.

- [ ] Implement strict schema parsing, ownership/mode/type/link/size checks, file identity,
  `documentID`+revision CAS, revision exhaustion, same-directory temp/fsync/rename/directory sync,
  and post-write reread.
- [ ] Implement Save acknowledgement, external-conflict reload/reapply, unresolved-entry Manage,
  malformed explicit recovery, unsafe/newer read-only behavior, and post-rename uncertainty.
- [ ] Ensure persistence linearization reaches the router before stale-generation rendering checks.
- [ ] Add exact state allowlist, doctor, update/repair/uninstall preservation, and rollback cuts.
- [ ] Make `DM3-T04`, `DM3-T05`, and preference portions of `DM3-T15` green.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/verify-m6.sh
```

**Completion evidence:** transition-table row-by-row receipt; conflict and recovery file identities;
pre/post-rename fault-cut results; lifecycle preservation receipt; proof preferences cannot alter
authority.

### Task 4: Bind fresh locators and enforce staged authority construction

**Files:**

- Create `Sources/DevMainSyncCore/SelectedRepositoryScope.swift`
- Create `Sources/DevMainSyncCore/SelectedRepositoryHydration.swift`
- Modify `RepositoryModelV2.swift`, `RepositoryLifecycle.swift`,
  `RepositoryAuthorityStore.swift`, `RepositoryInventoryDiscovery.swift`
- Modify `RepositoryChooserWindow.swift`, `RepositoryCardsWindow.swift`,
  `AppLifecycleRouter.swift`, `AppDelegate.swift`

**Symbols to inspect first:**

- both `RepositoryDiscovery.validateRuntimeEligibility` overloads and
  `validateRemovalRuntimeEligibility`
- `RepositoryAuthorityStore.confirmOnboarding`, `confirmCanonicalRoot`, `revalidate`
- `CanonicalAuthorityProposal`, `RepositoryInventorySelection.admit`
- constructors for `RepositoryCard`, `PlannedOperation`, and
  `RepositoryInventoryRemovalCandidates.make`

**Interfaces:**

- Consumes immutable selection intent and current root/policy descriptors.
- Produces first-pass evidence/proposals, then a second-pass
  `VerifiedRepositoryAuthorityCapability`.
- Preferences/catalog types have no authority conversion.
- Current v2 safety revalidation remains mandatory behind the capability.

- [ ] Implement atomic Continue closure and exact descriptor-bound binder order from §6.2.
- [ ] Add every forbidden locator/identity/ambiguity negative case before repository hydration.
- [ ] Split hydration into evidence/proposal and fresh capability passes.
- [ ] Keep onboarding commits solely in `RepositoryAuthorityStore` with fresh clones,
  `RepositoryHandle`, expected identity/revision, and CAS.
- [ ] Close card/operation/removal/confirmation/authorized-worker construction behind the verified
  capability while keeping encoded formats identical.
- [ ] Preserve disabled-row payload exclusion and add compile/runtime negative tests.
- [ ] Make `DM3-T06`, `DM3-T07`, and `DM3-T08` green.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/v2-body1-acceptance.sh
./scripts/v2-body2-acceptance.sh
./scripts/v2-body4-acceptance.sh
```

**Completion evidence:** descriptor/root replacement traces; locator rejection matrix; type
dependency diagram; onboarding CAS receipts; wire digests identical to Task 1.

### Task 5: Remove broad production refresh and prove selected-only linear execution

**Files:**

- Modify `Models.swift`, `RepositoryDiscovery.swift`, `RepositoryInventoryDiscovery.swift`
- Modify `Body3Coordinator.swift`, `Coordinator.swift`, `Worker.swift`
- Modify `AppDelegate.swift`, `RepositoryCardsWindow.swift`, `Body3RunWindow.swift`
- Modify v2 self-tests only to pass explicit testing scopes

**Symbols to inspect first:**

- `RepositoryDiscovering`, `IsolatedRepositoryDiscovery`
- `RepositoryInventoryDiscovering`, both `discoverInventory` methods
- `RunCoordinator.runBody3`, local `freshInventory`, `Body3ExecutionContext.record`,
  `refreshedSelection`
- production `WorkerMain.dispatch` inventory refresh
- all shell-`rg` call sites of `discover()` and `discoverInventory()`

**Interfaces:**

- Consumes only `ValidatedSelectedRepositoryScope` or one exact node-derived sub-scope.
- Produces selected inventory/authorized envelopes only.
- Heavy file/process/network complexity is linear in selected topology.
- No out-of-scope return is recorded or allowed to start a child.

- [ ] Change protocols and production implementations to require selected scope.
- [ ] Delete every production parameterless route, optional no-argument provider, and broad
  fallback named in §7.1.
- [ ] Make each Body 3 refresh exact-repository and validate membership before context/event/child.
- [ ] Make production worker bind current selected scope from unchanged wire values and freshly
  reauthorize decoded operations.
- [ ] Add 51-repository poison fixtures and selected 1/3 scale comparisons.
- [ ] Use shell `rg` plus production symbol/source audit to prove no broad route remains.
- [ ] Make `DM3-T09`, `DM3-T10`, and `DM3-T13` green.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/v3-preflight-acceptance.sh
```

**Completion evidence:** complete removed-call inventory; exact-node Body 3 traces; poison sentinel
counts all zero; selected 1/3 versus catalog 3/51 process/file/time comparison.

### Task 6: Consolidate lifecycle routing and prove the drain barrier

**Files:**

- Create/finalize `Sources/DevMainSyncApp/AppLifecycleRouter.swift`
- Modify `AppDelegate.swift`, `RepositoryChooserWindow.swift`,
  `RepositoryCardsWindow.swift`, `Body3RunWindow.swift`, `Worker.swift`
- Modify `verify-m5.sh`

**Symbols to inspect first:**

- `LifecycleGate`, inventory/authority/body3 flags in `DevMainSyncAppDelegate`
- `configureSelectionCancellation`, `executeBody3Batch`, `quitUtility`,
  `terminateAfterConfirmedQuit`
- `RunWindowController.requestQuitAfterConfirmation`, `gateSnapshot`,
  `handleWorkerExit`
- `WorkerSession`, `WorkerPostReapEvidence`, and existing process-ownership evidence in
  `ProcessOwnership.swift`

**Interfaces:**

- Consumes all app lifecycle events in one MainActor reducer.
- Produces generation-bound effects and one drain-barrier verdict.
- Existing worker stop/reap verification is evidence, not inferred completion.
- No independent boolean/controller becomes action authority.

- [ ] Implement the exhaustive phase/event transition table and generation-bound effect ownership.
- [ ] Route Continue, Save, Manage/Change, Cancel, onboarding, review, execution completion, and Quit
  through it.
- [ ] Enforce task-settlement → deferred-Quit → controller-currentness → rendering completion order.
- [ ] Implement every drain predicate in §8.3 and a precise blocked diagnostic.
- [ ] Add adversarial ordering, stale callback, double-admission, stubborn child, delayed authority,
  and exactly-once termination tests.
- [ ] Remove superseded app flags/routing branches; adapt `LifecycleGate` rather than duplicating it.
- [ ] Make `DM3-T11`, `DM3-T12`, and full `DM3-T14` green.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/verify-m5.sh
./scripts/v3-preflight-acceptance.sh
```

**Completion evidence:** exhaustive transition matrix; each drain predicate's independent negative
test; exactly-once Quit trace; cancellation acknowledgement/progress/recovery screenshots or
structured AppKit snapshots.

### Task 7: Close lifecycle compatibility, full acceptance, and governed delivery

**Files:**

- Finalize `scripts/v3-preflight-acceptance.sh`
- Modify `verify-m1.sh`, `verify-m5.sh`, `verify-m6.sh`, `source-doctor.sh`, `install.sh`
- Modify `.github/scripts/verify-skills.sh` to invoke the v3 capability acceptance
- Modify `global/tools/dev-main-sync/README.md`
- No accepted plan edits

**Symbols to inspect first:**

- `scripts/owned-cleanup.sh` cleanup/reap helpers
- production symbol/network/dependency audits in v2 acceptance scripts
- `InstallationLifecycle` doctor/preservation and `source-doctor.sh`
- root `.github/scripts/verify-skills.sh`

**Interfaces:**

- Produces one self-cleaning isolated acceptance entrypoint and owner-verifier receipt.
- Starts no background process that survives the script.
- Performs no install or real repository/AWA mutation before merge.
- Delivery follows the exact governed gates below.

- [ ] Make `v3-preflight-acceptance.sh` build testing and production products in one fresh
  owner-only `/private/tmp` root, run `DM3-T01–T15`, perform target/symbol/process/network/broad-route
  audits, run 20 first-screen trials, and reap/remove every owned helper/fixture.
- [ ] Run dependency-mapped v2 suites, then full `verify-m1.sh`, `verify-m5.sh`, `verify-m6.sh`
  because discovery, AppKit lifecycle, process ownership, and install boundaries all changed.
- [ ] Run the complete Skills owner verifier and doc-warden read-only check.
- [ ] Inspect production symbols/strings/imports and package contents for test seams, broad routes,
  unapproved process/network paths, dependencies, secrets, and downstream links.
- [ ] Update README with chooser/defaults/Continue/Manage/cancellation behavior and safe local
  verification commands; keep install warnings exact.
- [ ] Open one Draft PR. Run Bugbot until no material finding remains. Run security review because
  descriptor binding, persistence, process admission, authority, worker, and Quit boundaries
  changed; rerun after every material security fix.
- [ ] Present exact head, changed-file set, test receipts, physical metrics, and residual
  uncertainties at the explicit ready gate. Mark ready only after operator GO.
- [ ] Leave merge/auto-merge control to the reviewer App/native governed path.
- [ ] After merge, update the durable primary to exact clean `origin/main`, verify source
  attestation, install that exact main through the existing lifecycle, run doctor, and repeat the
  physical checklist in §15.

**Verification:**

```bash
cd global/tools/dev-main-sync
./scripts/v3-preflight-acceptance.sh
./scripts/verify-m1.sh
./scripts/verify-m5.sh
./scripts/verify-m6.sh
cd ../../..
bash .github/scripts/verify-skills.sh
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
```

**Completion evidence:** all `DM3-T*` receipts; retained v2/full-suite receipts; production audit;
clean process/fixture inventory; Bugbot/security resolution; exact-head required Check; ready GO;
reviewer-App merge; exact merged-main source/install/bundle digests; doctor and post-install
physical acceptance.

## 14. Acceptance ledger

| Acceptance ID | Final observable requirement | Requirement IDs | Task/test evidence |
|---|---|---|---|
| `V3-AT-01` | Chooser rows are usable within 1.000 s in all 20 representative trials | CAT, PERF | Tasks 2/7; `DM3-T03/T14` |
| `V3-AT-02` | Before Continue there are zero children, network work, and authority acquisitions | CAT, PERF | Tasks 2/7; `DM3-T02/T14` |
| `V3-AT-03` | Every durable policy-visible repository appears; hidden/artifact fixtures do not | CAT | Task 2; `DM3-T03` |
| `V3-AT-04` | Save, editable defaults, Continue, Cancel, Quit, and later Manage/Change are complete | PREF, LIFE | Tasks 2/3/6; `DM3-T04/T11` |
| `V3-AT-05` | Preference state table has no silent overwrite/reset/dedupe/drop | PREF | Task 3; `DM3-T05/T15` |
| `V3-AT-06` | Continue rereads policy/catalog and binds locators beneath current root descriptors | BIND | Task 4; `DM3-T06` |
| `V3-AT-07` | Replaced/forbidden/unknown/duplicate/ambiguous locators fail before hydration | BIND | Task 4; `DM3-T06` |
| `V3-AT-08` | Preferences cannot construct authority or operations | PREF, AUTH | Tasks 3/4; `DM3-T07/T08` |
| `V3-AT-09` | Only fresh second-pass selected hydration yields operation capability | AUTH | Task 4; `DM3-T07/T08` |
| `V3-AT-10` | Existing runtime eligibility/authority/origin/policy/topology safeguards still execute | AUTH, COMP | Tasks 1/4; `DM3-T01/T08` plus v2 suites |
| `V3-AT-11` | Every heavy production API requires selected scope; no fallback remains | SCOPE | Task 5; `DM3-T09/T10/T16` |
| `V3-AT-12` | Body 3 refresh rejects foreign results before state/event/child admission | SCOPE | Task 5; `DM3-T09` |
| `V3-AT-13` | Unselected poison repositories receive no heavy access/process/network/payload | SCOPE, PERF | Task 5; `DM3-T10/T13` |
| `V3-AT-14` | Heavy work is linear in selected repositories/topology | SCOPE, PERF | Task 5; `DM3-T13` |
| `V3-AT-15` | One lifecycle router resolves all overlap/stale-generation orderings | LIFE | Task 6; `DM3-T11` |
| `V3-AT-16` | Quit waits for task ownership, every reap, post-reap verification, and authority release | LIFE | Task 6; `DM3-T12` |
| `V3-AT-17` | Save linearization is observed before stale UI suppression | PREF, LIFE | Tasks 3/6; `DM3-T05/T11` |
| `V3-AT-18` | `RepositoryCandidate` and all current Codable/wire formats remain compatible | COMP | Task 1; `DM3-T01/T15` |
| `V3-AT-19` | Disabled rows never enter review/confirmation/worker payloads | AUTH, COMP | Tasks 2/4; `DM3-T04/T08` |
| `V3-AT-20` | Preference state survives install/update/repair/uninstall/forward rollback safely | COMP | Tasks 3/7; `DM3-T15` |
| `V3-AT-21` | No paid runner, service, daemon, watcher, telemetry, or new recurring job exists | GOV | Task 7; `DM3-T16` |
| `V3-AT-22` | Draft PR, clean reviews, explicit ready GO, reviewer-App merge, exact-main install occur in order | GOV | Task 7 delivery receipt |

`CAT`, `PREF`, `BIND`, `AUTH`, `SCOPE`, `LIFE`, `PERF`, `COMP`, and `GOV` in the ledger refer to
the corresponding `V3-*` requirement families in §12.1. Every acceptance row is release-blocking.

## 15. Physical acceptance and delivery gates

### 15.1 Pre-merge isolated physical checklist

1. Build a production app and testing app from the exact Draft PR head in a fresh owner-only
   `/private/tmp` root; do not install either.
2. Populate at least 51 representative catalog repositories and all visibility classes.
3. Launch the isolated app under the admission probe and network-denied harness.
4. Record action-entry, window-visible, and first-enabled-row monotonic times for 20 cold trials;
   require each ≤1.000 s.
5. Wait at the usable chooser before Continue; require zero child/process/network/authority
   admission and zero descendant census.
6. Exercise select/deselect, Save, external preference conflict, Manage/Change, unresolved default,
   Cancel acknowledgement, hydration cancellation, recovery, and Quit.
7. Select 1, then 3 repositories; prove the first child starts only after Continue and poison
   repositories stay untouched.
8. Exercise onboarding confirmation, fresh second hydration, cards/review, a no-mutation Equal
   operation fixture, Body 3 foreign refresh injection, cancellation, and deferred Quit drain.
9. Verify all helper PIDs are reaped and the isolated root is removed.

### 15.2 Remote PR gates

- One Draft PR contains the complete body and stays Draft during implementation/review.
- Required exact-head `pr-automation / verify` passes.
- Bugbot has no unresolved material finding.
- Security review has no unresolved material finding.
- The exact head/diff/evidence is presented at the explicit operator ready gate.
- Only after GO may the PR be marked ready.
- The reviewer App alone may approve/arm native governed merge.
- Never call `gh pr merge --auto`, enable or disable auto-merge, directly merge, bypass checks,
  alter reviewer/verifier automation, or introduce a paid runner.

### 15.3 Post-merge install and target-Mac acceptance

1. In the durable physical primary Skills checkout, fetch and require clean local `main` exactly
   equal to current `origin/main`.
2. Re-run source attestation plus `v3-preflight-acceptance.sh`, `verify-m1.sh`, `verify-m5.sh`,
   `verify-m6.sh`, and the owner verifier from that exact revision.
3. Install only through the existing source-built lifecycle from exact clean main.
4. Run the installed lifecycle doctor and record source revision, source-input digest, bundle
   digest, signature, launcher identity, and preference-state result.
5. Open the installed chooser and repeat first-screen time plus zero pre-Continue child/network/
   authority acceptance at the representative live catalog scale.
6. Exercise Save, reopen/Manage, Continue with a harmless Equal/no-op selected repository, Cancel
   during selected hydration, and Quit drain. Do not select Cleanup or mutate real repository
   state.
7. Confirm unselected live repositories receive no Git/gh/helper process or heavy file access.
8. Confirm the kitchen is clean: no temporary fixture, background task, helper process, dirty
   checkout, unpushed implementation commit, open material review, or unrecorded recovery state.

## 16. Planning-lane verification and freeze

For this plan-authoring stage only:

```bash
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check \
  /Users/laurence.duggan/.cursor/worktrees/skills/dev-main-sync-v2-body1-20260909
git diff --check
git diff --name-only
```

Required result: only this v3 plan and `docs/plans/README.md` differ; v2 remains byte-identical.
Shell `rg` must find all six exact blocker IDs, every `V3-*` requirement family, `DM3-T01` through
`DM3-T16`, `V3-AT-01` through `V3-AT-22`, the one-body decision, the preference transition table,
the ≤1-second/zero-process physical gate, selected-only poison/scale proof, real drain predicates,
rollback, migration, and governed delivery prohibitions. No unresolved placeholder or scratch plan
copy may remain.

**APPROVED — Dev Main Sync v3 process-free chooser and selected-scope execution plan**
