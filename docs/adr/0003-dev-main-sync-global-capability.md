# ADR 0003: Own Dev Main Sync as a source-owning global tool capability
Status: accepted — 2026-09-03

**Owners:** Laurence Duggan (`KleinPerkins`); `KleinPerkins/skills` maintainers
**Scope:** canonical source ownership, packaging, installation, distribution, removal, and
documentation authority for the native macOS Dev Main Sync utility
**Decision owner:** Laurence Duggan

## Decision

Own Dev Main Sync directly at `global/tools/dev-main-sync/` in `KleinPerkins/skills` as a
homegrown Flavor-1 `kind: tool`, `shape: snapshot`, `sync_policy: none`,
`post_mgmt: launchd` global capability. This shelf directory—not a second product repository or
copied payload—will contain the canonical Swift/AppKit source, independently testable safe-Git
core, tests, build/package scripts, `tool.yml`, `meta.yml`, and the installer that owns
install, repair, doctor, update, and uninstall behavior.

Register the global capability through the existing WF1 registry with `state: excluded`.
That is an established governed state for global Darwin/GUI or otherwise non-downstream
capabilities: registry, metadata lock, consistency, and delete-propagation remain authoritative, while no
Dev Main Sync bytes enter a downstream payload. The product is machine-global across the
operator's workspaces, but its v1 behavior remains deliberately specific to a home-relative
`~/dev`.

Use the existing `global/tools` shelf and manifest schema. Add no shelf kind, source repository,
Global Capability Binding, standalone release descriptor, bespoke vendor path, cpp installer, or
parallel distribution channel. No shared shelf scaffold is required: default bootstrap/reconcile
already invokes a Flavor-1 tool whose `post_mgmt` is not `none`, while the capability's own
installer provides the authoritative read-only doctor [E3].

The linked execution plan is
[`../plans/dev-main-sync-global-capability-v1.md`](../plans/dev-main-sync-global-capability-v1.md).

## Canonical authority

`KleinPerkins/skills` already exists and is the selected implementation owner, so this repository's
governed `docs/adr/` and `docs/plans/` lanes are canonical now [E2]. This ADR records the ownership
decision; the linked plan is the only execution plan. `KleinPerkins/dev` remains read-only product
context and host-policy authority, and `KleinPerkins/ecosystem-orchestrator` remains the sole WF1
registry/WF2 relationship authority. Neither receives a duplicate ADR or plan.

The future registry row links operational state to this source but is not a second semantic
decision record. No handoff is anticipated. If ownership later changes, the successor decision
must move source once and create a successor plan under the new owner. If this Skills plan is later
accepted, it remains frozen here as historical evidence, as specified under reversal.

## Context and problem

Dev Main Sync is a deliberately small native macOS utility for a non-technical operator. Every
selection session dynamically discovers eligible Git repositories beneath canonical `~/dev`,
including the umbrella repository when safe; deduplicates common Git identities; avoids linked
worktree traversal; excludes policy-prohibited repositories; shows the complete list with no
selection; and requires exact confirmation of a selected subset [E0].

It processes rows deterministically and serially. It fetches remote `main` into `origin/main`,
captures the exact fetched commit, and advances only a clean, attached primary checkout already on
`main` through Git's `--ff-only --no-overwrite-ignore --no-autostash` behavior. Equal is already
current. Ahead, diverged, dirty, busy, missing, detached, inaccessible, removed,
linked-worktree-conflicted, or uncertain states are preserved and skipped/refused. It never
switches branches, creates missing branches, resets, force-updates, rebases, creates a merge
commit, pulls, stashes, cleans, discards changes, rewrites history, pushes, force-pushes, or
suppresses repository safeguards [E0, E10].
Raw and Git-effective origin identities must remain the same approved GitHub repository
immediately before a no-submodule-recursion fetch; replacement refs/grafts cannot participate in
authorization; each Git child enters the inspected worktree by open descriptor and revalidates Git
metadata immediately before execution and after the command [E14].

One source-built application bundle contains a lightweight resident AppKit status launcher and the
same executable's short-lived serial worker mode. It provides native selection, confirmation,
progress, cancellation, final reporting, report reopening, menu access, a fixed global shortcut,
verified singleton/takeover behavior, child reaping, and one owner-only current/latest log. It is
local, single-user, and single-machine, with no backend, database, telemetry, scheduler, updater,
history dashboard, plugin framework, or cross-platform abstraction [E0].
An inherited child-liveness lease prevents a restarted run from overlapping a surviving Git child,
and descriptor-relative single-link log opening prevents truncation from targeting another file.

The ownership choice must preserve that complete product while using the smallest governed
delivery path.

## Decision-driving requirements and hard constraints

The decision preserves every stable source requirement and acceptance test recorded in E0,
including:

- dynamic discovery, common-directory deduplication, governing exclusions, and execution-time
  identity/policy revalidation;
- native zero-default selection, selection help, exact confirmation, progress/result states,
  status-item/global-shortcut access, report/log reopening, **Close Run**, and **Quit Utility**;
- exact fetched-target binding, clean/attached/idle checks, complete Git state matrix, independent
  fetched/updated reporting, raw/effective origin parity, ordinary-object-graph ancestry,
  worktree-descriptor child execution with observable metadata-drift refusal, no submodule
  recursion, and an absolute
  destructive/remote-write ban;
- one worker/run owner, cooperative cancellation before bounded verified escalation, no stale-PID
  authority, fixed-root close-on-exec lifecycle/run locks plus a separate Git-child-inherited
  operation lease across simultaneous host/worker loss, no orphan product process, and no rollback
  of completed updates;
- one `0700` state root and one `0600` current/latest log, truncated only by the run-lock owner and
  after descriptor-relative owner/type/link validation, with framed bounded output stripped of
  credentials/authentication material; and
- one native bundle, one serial worker path, no third-party runtime, no manually maintained
  repository registry, no paid runner, and no speculative infrastructure.

The hard gates are:

1. **Safe-Git correctness:** the owner can isolate, test, and release the complete fail-safe Git
   state machine.
2. **Native macOS UX viability:** the owner can build and operate the required AppKit status
   utility, shortcut, windows, and lifecycle with the installed toolchain.
3. **Canonical source ownership:** exactly one governed location owns implementation and release
   truth.
4. **Standard lifecycle compliance:** delivery uses the existing repository or capability
   lifecycle; any scaffold is bounded and evidenced.
5. **Distribution and installation feasibility:** one governed path covers deterministic build,
   install, update, launch-at-login, repair, doctor, and removal.
6. **Prohibited leakage:** global source carries no cpp-specific content, and no `~/dev` or
   operator-machine implementation bytes enter a downstream payload.
7. **Maintenance and reversibility:** ownership, installed state, registration, and metadata-lock state can
   be maintained and cleanly removed without duplicate architectures.

Any failed hard gate disqualifies an alternative. Weighted score cannot compensate for failure.

## Evidence base

Evidence was revalidated read-only on 2026-09-03. “Observed” means the cited bytes or command output
were inspected. “Inference” is explicitly labelled.

| ID | Kind | Durable evidence | Fact and what it proves |
|---|---|---|---|
| E0 | Observed | Parent transcript `8084ff59-5a37-4458-b6aa-65aa90eb1f33.jsonl`: event 1 original request; event 22 revised requirements §§11–16; later operator corrections dated 2026-09-03 | Defines the product contract, stable requirement families and AT-01–33, and the exact two-option ownership decision. Historical “Build”/“Proceed” text is not implementation authority here. |
| E1 | Observed | `KleinPerkins/dev@fa803c16`: `OPERATING-MANUAL.md` §§3, 5, 9, 10; `_ops/POLICY.md` §§1–4 | Defines `~/dev` placement, capability lifecycle, personal-product boundary, identity, and no-leakage invariants. |
| E2 | Observed | `KleinPerkins/skills@83425665`: `AGENTS.md:9-23`; `README.md:1-40,48-86`; `docs/adr/README.md`; `docs/plans/README.md` | `skills` is canonical for global capabilities, has governed ADR/plan lanes, and separates machine-global source from downstream eligibility. |
| E3 | Observed | `KleinPerkins/skills@83425665`: `.github/scripts/verify-skills.sh:50-121,194-208`; `.github/scripts/eco-lock.sh:1-19,128-151`; `bootstrap.sh:310-339,350-421`; `.eco-registry.lock`; `KleinPerkins/dev@fa803c16:_ops/eco/MANIFEST-CONTRACT.md:28-86` | Existing schemas accept a Flavor-1 `kind: tool` on the `tools` shelf with `shape: snapshot`; the Skills Git commit identifies source while the lock guards normalized capability metadata; bootstrap already invokes any tool with non-`none` post-management. Generic bootstrap doctor validates the tool record rather than installed runtime, so release claims must use the product-local installer doctor. |
| E4 | Observed | `KleinPerkins/skills@83425665`: `local/tools/google-kit-doc-styles/{meta.yml,tool.yml,install.sh}` | A homegrown Flavor-1 snapshot tool can directly own implementation and installer bytes in the shelf with `sync_policy: none`; no external SSP is required by schema. |
| E5 | Observed | `KleinPerkins/ecosystem-orchestrator@f3cbeaeb`: `config/registry.yml:1-35,149-201`; `lib/consistency.sh:61-112`; `lib/selfmanage.sh:152-209`; `tests/test_plugin_discovery.sh` | `state: excluded` is a first-class WF1 registry state, covers global-source inventory without downstream vendoring, and participates in drift/delete-propagation logic. Existing AWA and Darwin/GUI keep-awake entries demonstrate governed exclusion. |
| E6 | Observed | `KleinPerkins/ecosystem-orchestrator@f3cbeaeb`: `config/relationship.yml:1-35`; `config/forbidden-ld.txt`; `config/forbidden-cpp.txt`; `lib/payload.sh`; `lib/reconcile.sh` | The orchestrator alone owns the downstream edge and zero-link gates. Exclusion avoids copying `~/dev`/operator-machine bytes; global source itself must contain no cpp-specific content. |
| E7 | Observed | `KleinPerkins/skills@83425665`: `global/tools/awa/{meta.yml,tool.yml,install.sh}`; `global/tools/operator-voice/{meta.yml,tool.yml,install.sh,README.md}`; `KleinPerkins/dev@fa803c16:_ops/eco/STANDALONE-SYSTEM-PARADIGM.md` | Existing tools prove release-descriptor and portable snapshot distribution. They also prove that a thin SSP pointer would leave source ownership in another repository and therefore would not satisfy Alternative 2 as defined. |
| E8 | Observed | `affirm/card-platform-product@56b88d0d`: `_ops/runbooks/eco-capability-sync.md` §§1–7; `_ops/bin/eco-capability-reconcile.sh:158-270`; `_ops/bin/cpp-bootstrap.sh:300-342` | The downstream lane copies and reconciles permitted capability payloads but has no native macOS app activation contract. Excluded registration is the correct v1 result, not a bespoke downstream installer. |
| E9 | Observed | `KleinPerkins/server-guard@7a4abe7e`: `README.md` install/uninstall; `install.sh:20-47,126-273`; `src/sgd.swift:730-927` | A repository-contained source-built Swift utility can use Command Line Tools, ad-hoc signing, user launchd, native dialogs, verification, and uninstall without a hosted service. The pattern can be implemented inside a tool shelf. |
| E10 | Observed | `KleinPerkins/awa@a88f229b`: `docs/adr/0019-fast-forward-primary-carve-out.md:25-68,72-115`; `SECURITY.md:46-75`; `engine/tests/test_git_primary_maintenance_behavior.py:260-645` | Local precedent supports clean/attached/idle inspection, truthful mutating classification, FF-only/no-overwrite behavior, equal/no-op, divergence refusal, post-fetch recheck, and configured-hook residue preservation. It is evidence to adapt, not code to copy. |
| E11 | Observed | `KleinPerkins/skills@83425665`: `global/skills/local-jobs/lib/flock.py:1-31`, `running.py:1-159`; `KleinPerkins/dev@fa803c16:_ops/bin/install-dev-awa-overlay.sh:600-666`; `KleinPerkins/awa@a88f229b:engine/integrity_detach.py:150-170` | Local patterns establish advisory locks, PID-start checks, exact owned-process discovery, new process groups, TERM/KILL escalation, and reaping. PID alone remains insufficient. |
| E12 | Observed + inference | Live host on 2026-09-03: macOS 26.6.2 arm64; Apple Git 2.50.1; Swift 6.3.3; `/Library/Developer/CommandLineTools`; `xcodebuild` unavailable. SDK: `AppKit/NSStatusItem.h:24-63`, `NSApplication.h:400-426`, `NSWorkspace.h:29-48`, `HIToolbox/CarbonEvents.h:15420-15503` | **Observed:** the toolchain and required API declarations are installed. **Inference:** a complete launchable AppKit bundle can be built with Command Line Tools alone; Milestone 1 must prove this before the native-viability gate is finally cleared. |
| E13 | Observed | `KleinPerkins/dev@fa803c16`: `_ops/policy/worktree-policy.yml:28-57`; `_ops/bin/baseline-lib.sh:100-137,445-459`; root `AGENTS.md` | Governing exclusions span path declarations, repository identity, and foreign-hook checks; the umbrella is explicitly exceptional for this product. A bounded adapter must classify hard exclusions before Git by reading policy/classifier declarations and candidate Git metadata as data, fail closed on unknown shape, and avoid a separate repository registry. |
| E14 | Observed | Installed Apple Git 2.50.1 help/manuals: `git(1)` `--no-replace-objects`; `git-fetch(1)` `--[no-]recurse-submodules`; `git-merge(1)` `--[no-]autostash`; `git-config(1)` `url.<base>.insteadOf`; `git-remote(1)` `get-url` | Repository config can rewrite an effective remote URL or enable merge autostash; Git supports ordinary-object-graph operation, explicit submodule-recursion denial, and explicit autostash denial. Safe authorization checks raw/effective identity, excludes replacement/graft ambiguity, and prevents configured stashing. |

The `skills` documentation worktree was created from and remains based on live
`origin/main@83425665`. For the other repositories, cited material was either read from the stated
live revision or verified byte-identical to it. No authority is inferred from a stale local branch.

## Decision method

### Scale and materiality

Each criterion uses one scale:

- **5 — established:** current, directly reusable, complete evidence;
- **4 — strong:** viable with bounded product work or one narrow scaffold;
- **3 — conditional:** viable but carries a material unresolved dependency;
- **2 — weak:** requires substantial cross-component support;
- **1 — unsupported:** no compliant end-to-end path; and
- **0 — contradictory:** violates a hard constraint.

Weights were fixed before scoring and total 100%. A difference of **10.0 weighted points** is
material: it requires, for example, a one-level score advantage across criteria carrying half the
total weight, rather than a narrow maturity edge. The operator's Alternative 2 prior applies only
if both alternatives pass every hard gate and their weighted difference is less than 10.0 points.

### Exactly two alternatives

#### Alternative 1 — Standalone repository

Create `KleinPerkins/dev-main-sync` through the existing born-compliant repository path. It owns
the source, native lifecycle, release, source-built package, install/update/remove behavior, tests,
and documentation. It does not participate in the capability registry or downstream edge.

This is a clean, mature product boundary. It reuses repository standards and the server-guard
native precedent [E1, E9–E12]. Its costs are one more repository, one more independent release and
documentation surface, and loss of the already-global capability update/bootstrap entry point.

#### Alternative 2 — Global capability

Store the canonical product directly on the existing `global/tools` shelf as a Flavor-1 snapshot
tool. Its own installer builds and manages the one native bundle. The existing Skills bootstrap
invokes it because `post_mgmt: launchd`; the Skills commit identifies its source and the metadata
lock guards its capability contract; WF1 records it as excluded; orchestrator consistency treats
that omission as governed; no downstream payload is created [E2–E6].

This is not an external SSP disguised by a pointer: there is no second source repository,
`provenance_source`, release descriptor, or duplicated snapshot. It is also not a new shelf kind.
The source-owning directory is the one release unit. Product-local `install.sh --check` and
`--doctor` verify source/package and installed state; changing generic bootstrap health semantics
would affect unrelated tools and is unnecessary [E3].

### Alternative 2 proof obligation

| Obligation | Evidence-based conclusion |
|---|---|
| Canonical source ownership | **Supported:** Flavor-1 means homegrown line-for-line source; snapshot tools may carry direct bytes. `global/tools/dev-main-sync/` is the sole source [E3, E4]. |
| Native utility implementation | **Supported for this ownership decision:** snapshot validation does not constrain implementation language; installed Swift/AppKit declarations and nearby source-built precedent support the same bounded feasibility inference for either owner. M1 remains the implementation proof [E3, E9, E12]. |
| Deterministic build/package | **Supported as product-owned behavior:** the shelf's `install.sh` and build scripts create and verify the bundle; the reviewed Skills commit binds their source. No generic native builder is needed [E3, E9]. |
| Governed release/distribution | **Supported:** the reviewed Skills commit is the source-release identity, while regenerated `.eco-registry.lock` binds normalized capability metadata; bootstrap installs from that canonical checkout. No second artifact channel is added [E2, E3]. |
| Install/update | **Supported:** `post_mgmt: launchd` causes default bootstrap/reconcile installation. The idempotent default installer updates/repairs from current canonical bytes; its own doctor verifies the installed result [E3]. |
| Registration/discoverability | **Supported:** `meta.yml`/`tool.yml`, the metadata lock, and a WF1 `state: excluded` row provide inventory and operator/agent discovery without downstream bytes [E3–E5]. |
| Reconcile/lock | **Supported:** bootstrap reconcile invokes managed post-install tools; `.eco-registry.lock` fingerprints scope, shelf, kind, shape, sync policy, and other normalized metadata—not source bytes—while Git owns source identity [E3]. |
| Orchestrator propagation | **Supported as governed non-propagation:** `excluded` is the live standard for global capabilities that must not be copied. Consistency and delete-propagation enforce absence [E5, E6]. |
| cpp consumption where permitted | **Not permitted in v1:** the product is Darwin GUI and `~/dev` specific, and the downstream has no native activation contract. The standard excluded state is used; no payload or installer is invented [E5, E8]. |
| Clean removal/rollback | **Supported with bounded product work:** installer owns verified drain, stage-by-stage post-promotion restoration, and fail-closed uninstall; removing the shelf plus WF1 row and regenerating the lock returns registry/source inventory to zero. No downstream payload exists [E3, E5, E9]. |

No new shelf kind, manifest field, lock format, reconcile algorithm, bootstrap behavior,
orchestrator behavior, or downstream mechanism is required. The existing shelf suffices.

### Hard-gate result

| Hard gate | Alternative 1 | Alternative 2 |
|---|---|---|
| Safe-Git correctness | **PASS** — isolated core and local Git precedent are compatible with one product repository [E10]. | **PASS** — the same isolated core lives in one source-owning shelf; location does not weaken the safety gate [E3, E10]. |
| Native macOS UX viability | **PASS for the ownership decision; release proof pending** — source-built Swift precedent and installed AppKit declarations support a bounded CLT-only feasibility inference [E9, E12]. | **PASS for the ownership decision; release proof pending** — snapshot source/installer can use the same inferred build path; `post_mgmt: launchd` is established [E3, E9, E12]. |
| Canonical source ownership | **PASS** — one repository owns source. | **PASS** — one Flavor-1 shelf directory owns source; there is no SSP/payload copy [E3, E4]. |
| Standard lifecycle compliance | **PASS** — born-compliant repository lifecycle is established [E1]. | **PASS** — existing tool/snapshot/post-management, product-local installer, metadata lock, and excluded registry states cover the lifecycle without shared-framework change [E2–E6]. |
| Distribution/installation feasibility | **PASS** — standalone installer can own the source-built path [E9]. | **PASS** — canonical Skills checkout → bootstrap/reconcile → tool installer is one path; native build remains tool-owned [E3, E9]. |
| Prohibited leakage | **PASS** — no capability/downstream edge exists. | **PASS** — source contains no cpp-specific content and excluded registry state creates no downstream payload [E5, E6, E8]. |
| Maintenance/reversibility | **PASS** — one repository/installer is bounded. | **PASS** — one shelf/installer plus standard registry/metadata-lock removal is bounded; no copied payload must be unwound [E3, E5]. |

No gate has observed counter-evidence. This is an architecture-feasibility pass, not an
implementation or release qualification: both alternatives depend on the same explicitly labelled
CLT-only AppKit inference, so it cannot distinguish their ownership fitness. M1 must prove that
inference before later work; failure disqualifies both current shapes and reopens this DRAFT ADR.

### Weighted assessment

| Criterion | Weight | Alternative 1 score → points | Alternative 2 score → points | Evidence-based rationale |
|---|---:|---:|---:|---|
| Safe-Git correctness | 25% | 4 → 20.0 | 4 → 20.0 | Both keep the independently testable state machine and release gate with the source that invokes it [E10]. |
| Native macOS UX viability | 15% | 4 → 12.0 | 4 → 12.0 | Both share the installed SDK/toolchain, nearby source-built Swift precedent, and the same bounded CLT-only AppKit inference that M1 must prove [E9, E12]. |
| Canonical source ownership | 15% | 5 → 15.0 | 5 → 15.0 | Each offers exactly one source owner; Flavor-1 direct ownership avoids SSP/snapshot duplication [E2–E4]. |
| Standard lifecycle compliance | 15% | 5 → 15.0 | 4 → 12.0 | Born-compliant repository delivery has a direct native precedent. The capability path is established, but no current source-owning global native app exercises it end to end; product-local verification closes that bounded evidence gap [E1–E5]. |
| Distribution/installation feasibility | 12% | 4 → 9.6 | 4 → 9.6 | Both require product-specific native bundle work; Skills bootstrap already calls post-managed installers [E3, E9]. |
| Prohibited leakage | 8% | 5 → 8.0 | 5 → 8.0 | Standalone has no edge; the capability's standard excluded state enforces no downstream payload [E5, E6]. |
| Maintenance/reversibility | 10% | 4 → 8.0 | 4 → 8.0 | Standalone adds a repository; capability adds one registry row/metadata lock and shares a repo. Each has a bounded uninstall/revert path [E1–E5, E9]. |
| **Total** | **100%** | **87.6** | **84.6** | **Alternative 1 leads by 3.0 points.** |

The 3.0-point difference is below the predefined 10.0-point materiality threshold.

### Application of the operator prior

Both alternatives pass all hard gates on current evidence, share the same M1 native-build proof
condition, and neither has a material weighted advantage. The operator's declared tie-breaker
therefore selects **Alternative 2 — Global capability**.
Alternative 1's 3.0-point lifecycle-maturity advantage is real but insufficient to outweigh that
prior; no score was changed to force the result.

## Why Alternative 2 wins

The direct Flavor-1 snapshot shape closes the earlier apparent ownership gap: unlike the two
existing Flavor-2 GCBs, it can make the shelf itself the canonical implementation owner. Existing
post-management, product-local installer health, metadata lock, registry exclusion, consistency, and
bootstrap behavior cover the delivery path without a new kind, shared scaffold, or downstream
mechanism. Dev Main Sync stays one product directory and one installed app while avoiding the
standing overhead of another repository.

Alternative 1 did not win because its material advantages are limited to a more mature independent
product-release boundary. The native build, safe-Git testing, install lifecycle, and reversal work
still have to be built either way. Its weighted advantage is only 3.0 points; under the published
rule, the operator prior resolves that non-material difference toward Alternative 2.

## Consequences

### Positive

- One existing repository and one source-owning tool directory contain all implementation and
  release truth.
- No repository creation, external SSP, duplicate payload, GCB pointer, new shelf kind, or
  standalone distribution channel is needed.
- The normal Skills update/bootstrap path installs or reconciles the machine-level utility.
- WF1 registry and the Skills metadata lock retain inventory/contract authority while Git owns
  source identity and standard exclusion keeps all app and `~/dev` bytes out of downstream
  payloads.
- Safe-Git source, tests, native bundle, installer, and uninstall evolve in one reviewed change set.

### Negative

- A native application and its tests add more source volume to a repository primarily organized
  around agent capabilities.
- The Skills repository's release cadence now carries a machine-specific native tool, even though
  its registry state prevents downstream delivery.
- Generic `bootstrap.sh --doctor` proves the tool record, not the installed native runtime; release
  and repair claims must run the capability's own installer doctor.
- Native/AppKit verification remains a local macOS release gate because the current runnerless
  Linux path cannot exercise AppKit and full Xcode is not installed.
- `state: excluded` means the capability is globally available on the operator's machine but is not
  team-distributed through WF2. Promotion would be a new decision.

## Risks, dependencies, and operating implications

| Risk or dependency | Required response |
|---|---|
| Global-scope semantics could be mistaken for downstream eligibility | `meta.yml` remains global; the sole registry authority records `excluded`; product source contains no downstream-specific language; docs state machine-global/non-downstream v1. |
| Safe-Git race or incomplete state detection | Enter the inspected worktree by descriptor; revalidate metadata at the child exec gate and after Git; capture target; use Git-enforced FF-only/no-overwrite/no-autostash; skip observed uncertainty; full matrix and forbidden-command audit gate release [E10, E14]. |
| Effective config or replacement metadata changes authorization | Require matching approved raw/effective GitHub identity immediately before fetch, disable submodule recursion, exclude graft/replacement metadata, and use no-replace-object mode throughout [E14]. |
| Existing Git hook/helper performs independent network I/O | The source privacy invariant applies to product-authored clients and selected-origin Git transport. v1 neither suppresses nor sandboxes repository behavior; verification distinguishes descendant egress and makes no false guarantee about third-party hook/helper destinations. |
| Host exclusions span bounded YAML, repository identity, and classifier declarations | Parse only static hard path/owner declarations as data; inspect candidate Git metadata and unsupported hook markers through bounded no-follow filesystem reads before Git; distinguish product-specific root/third-party/cleanliness behavior; fail closed on unknown/dynamic shapes; parity-test live governing sources without a repository registry, prohibited global literal, or host-policy change [E13]. |
| Bootstrap install can warn and continue | Release/install verification always follows bootstrap/reconcile with the capability's direct installer doctor; no “installed” claim comes from bootstrap exit alone. |
| Dirty shelf bytes could be mislabeled as a reviewed Skills revision | Live install/update/repair refuses unless all capability inputs and the metadata lock are tracked, clean, and byte-identical to the reviewed commit; the signed bundle manifest also binds a source-input digest. |
| Process takeover after crash | Fixed-root close-on-exec launcher/lifecycle/run locks, live control channel, UID, executable, birth identity, and process-group agreement—not persisted PID/PGID—govern authority; a separate Git-child-inherited operation lease blocks overlap without authorizing a signal [E11]. |
| Log path is swapped or hard-linked | Open relative to the verified private state directory, require no-follow regular owner-only single-link identity before truncate, and frame/escape subprocess bytes as non-authoritative data. |
| Install/update fails after bundle promotion | Every later failure restores the prior bundle/plist and launch readiness, or removes newly promoted state when no prior install existed, before returning non-zero; failure injection gates release. |
| Uninstall ownership is unverifiable | Return non-zero and leave app, LaunchAgent, state, and log unchanged while reporting preserved paths and recovery route. |
| Command Line Tools only | Installed tools/API declarations support but do not prove the full AppKit bundle; M1 must compile, package, launch, and exercise the vertical slice under CLT alone before this gate is final [E12]. |
| Local ad-hoc signing | v1 remains source-built on one Mac. Developer ID/notarized or multi-machine distribution reopens this ADR. |
| Cross-repository registry change | Ecosystem-orchestrator owns the WF1 row. Land the inert excluded row before source, then land Skills source/metadata lock; removal proves source absence before deleting the row. Use governed changes only and never vendor downstream [E5, E6]. |

Operationally, the installed AppKit host is a lightweight status launcher, not a scheduled sync
daemon. **Close Run** closes run presentation/resources while retaining launcher and latest log.
**Quit Utility** uses the same cancellation/drain protocol, unregisters the shortcut/status item,
and exits. Its LaunchAgent uses `RunAtLoad` without `KeepAlive`.

## Reversal conditions

Laurence Duggan, or the then-current `KleinPerkins/skills` owner with Laurence's approval, may
reopen this decision when evidence establishes any of:

1. native source/test volume materially degrades Skills review, verification, or release cadence;
2. implementation requires any shared shelf, manifest, lock-format, or bootstrap behavior change;
3. capability install/update/removal cannot meet the same reliability as a standalone owner;
4. Developer ID/notarized, multi-machine, or independently versioned binary distribution becomes
   necessary;
5. a second real product owner needs an independent release/security boundary; or
6. measured lifecycle cost changes either alternative's score by at least 10.0 weighted points.

A successor ADR must rerun the same gates and weights against live evidence. Reversal to a
standalone owner is one cutover: stop/uninstall the shelf-owned app, create the born-compliant
repository, create its successor plan, move canonical source once, remove the shelf, update/remove
the WF1 row and metadata lock through their owners, prove downstream absence, then activate the new
installer. If accepted, the Skills plan remains frozen and is never moved or edited. There must
never be two active installers, source owners, app bundles, registry records, or active canonical
plans. If accepted, this ADR would be superseded through the index; its bytes would remain frozen.

## Assumptions and external gates

- **Assumption:** `state: excluded` remains an accepted registry state for a global Darwin/GUI,
  host-specific capability [E5].
- **Assumption:** local source build and ad-hoc signing are sufficient; Developer ID/notarization is
  not required.
- **Assumption:** product bytes can remain home-relative and contain no absolute operator path.
- **Assumption:** repository automation that deliberately leaves both the supervised Git process
  group and inherited lock identity is external repository behavior, not a product-owned
  descendant; the utility never signals or claims to drain it.
- **Assumption:** single-user v1 protects against mistakes and observable concurrent drift, not a
  malicious same-UID process racing Git-metadata replacement after the final child-side check.
- **External gate:** implementation, registry mutation, metadata-lock regeneration, installation, and
  release require later explicit authorization; this ADR grants none.
- **External gate:** the fixed shortcut `⌃⌥⌘M` must be collision-tested; collision reports
  **Keyboard Shortcut Unavailable** and leaves menu access available.
