# Dev Main Sync — global tool capability execution plan

**Version:** v1
**Status:** ACCEPTED — 2026-09-03
**Date:** 2026-09-03
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Review provenance:** The initial Mode A / Standalone plan-refine and one bounded swarm pass ran
on 2026-09-03 against `KleinPerkins/skills@83425665` and the linked ADR. They corrected lifecycle,
traceability, registry ordering, failure-state, safe-Git, process, logging, native-gate, and
ownership-reversal gaps. A second operator-requested Mode A pass on 2026-09-03 reverified the same
baseline and source contract, removed a circular executable/resource-hash bundle design, separated
M1 test-root proof from live bootstrap reconciliation, rejected configured SSH transport-command
overrides before network access, and added a plain-language recovery path for an indefinitely
surviving prior Git operation.

**Goal:** Deliver the smallest source-built native macOS capability that lets a non-technical
operator safely fast-forward selected clean `main` checkouts under `~/dev`, with complete native
UX, safe-Git behavior, cancellation, ownership, logging, lifecycle, and removal.
**Architecture:** `global/tools/dev-main-sync/` is the one canonical source/release unit: a
homegrown Flavor-1 snapshot tool whose installer builds one Swift/AppKit bundle containing the
resident status host and same-executable serial worker. The existing metadata lock and bootstrap,
plus a WF1 `excluded` registry row, govern installation and non-propagation; the product-local
installer owns health checks, so no shared-shelf scaffold is needed.
**Tech stack:** Swift 6 standard library, AppKit/Foundation, installed macOS SDK APIs, Apple Git,
launchd, POSIX process/file-lock facilities, shell for build/install orchestration, and ad-hoc local
code signing.

**Linked decision:** [ADR 0003 — Own Dev Main Sync as a source-owning global tool
capability](../adr/0003-dev-main-sync-global-capability.md)

---

## Global Constraints

- Implement only the selected direct global-tool architecture in ADR 0003. Do not create a
  standalone product repository, GCB, external source pointer, duplicated payload, new shelf kind,
  new manifest/lock schema, bespoke vendoring route, or downstream installer.
- Canonical source lives once at `global/tools/dev-main-sync/`. The capability is Flavor 1,
  `kind: tool`, `scope: global`, `shape: snapshot`, `sync_policy: none`, and
  `post_mgmt: launchd`.
- WF1 records `dev-main-sync` with `state: excluded`. Registry, Skills metadata lock, bootstrap/reconcile,
  orchestrator consistency, and delete-propagation remain authoritative. No app/source byte is
  delivered downstream.
- Global capability files contain no cpp-specific literals. Product paths are home-relative; no
  absolute operator path enters source. Tests derive host exclusions from policy inputs rather
  than embedding prohibited downstream names.
- No shared shelf, bootstrap, manifest, lock-format, orchestrator, downstream, or policy-framework
  behavior change is permitted.
- The product is local, single-user, single-machine, arm64, and macOS 26.6.2. Runtime dependencies
  are the one application bundle, macOS frameworks, and installed Git only.
- One executable implements the resident launcher and internal worker mode. There is no second
  product binary, daemon, database, scheduler, backend, telemetry, analytics, updater, history
  dashboard, plugin system, repository registry, or cross-platform abstraction.
- Discovery starts only when selection begins; the idle launcher performs no repository scan.
- Repository selection is the only operator input. v1 has no optional execution control and never
  moves or switches a checkout to `main`.
- Git is launched directly with argument arrays. Never invoke reset, forced ref update, rebase,
  ordinary merge, pull, stash, clean, checkout, switch, branch creation, push, force-push, history
  rewrite, safeguard suppression, or repository repair.
- Git children receive a closed environment allowlist derived from the effective-user account and
  fixed system paths. No inherited `GIT_*`, askpass, SSH-command, trace/TRACE2, curl-verbose, or
  output-redirection variable may bypass command, identity, prompt, or private-log controls.
  Standard input is `/dev/null`; fixed Git/SSH noninteractive settings disable terminal, askpass,
  password, passphrase, and TTY prompts while retaining configured credential helpers and the
  user's SSH agent.
- Immediately before network access, Git's effective fetch URL must resolve to the same approved
  GitHub repository identity as the raw `origin`; fetch explicitly disables submodule recursion.
  Credential helpers and repository safeguards remain enabled.
- v1 rejects an SSH candidate with effective `core.sshCommand`, and any candidate with
  `remote.origin.uploadpack`, before network access rather than silently overriding configured
  transport behavior with its fixed noninteractive command.
- Replacement refs and grafts are ineligible, and every topology/ancestry/update command uses
  Git's no-replace-object mode so only the ordinary object graph can authorize a fast-forward.
- Each Git child enters the already-open, no-follow, inode-verified worktree with `fchdir`; it
  reopens and compares Git metadata identities immediately before `execve` and again after the
  command. Observed drift skips or reports attention. The plan does not claim that Apple Git can
  consume Git-metadata directory file descriptors directly.
- Only a clean, attached primary checkout already on `main` may advance, and only to the exact
  commit fetched in that attempt through Git's
  `--ff-only --no-overwrite-ignore --no-autostash` behavior.
- Every uncertain policy, identity, Git, ownership, or postcondition result fails safe by excluding,
  skipping, refusing, or reporting attention.
- Process in deterministic displayed order with at most one active Git subprocess group. Continue
  after an isolated repository failure unless cancellation was requested.
- Cancellation/takeover requests cooperative stop first, then bounded TERM/KILL only against a
  live, reverified product-owned process group; persisted PID/PGID never authorizes a signal.
- The production state root is derived from the effective user's account record, never
  `HOME`/`XDG_*` authority. A shared lifecycle lock excludes install/remove from active runs, and
  an exclusive run lock owns the worker. Authority lock descriptors are close-on-exec; a separate
  Git-child-inherited operation lease supplies only negative admission evidence after
  host/worker loss.
- Never roll back an already completed repository update.
- Keep one owner-only current/latest log. Open it relative to the verified state-directory
  descriptor, require link count one, and truncate it only after exclusive run ownership; frame,
  bound, escape, and redact all subprocess output.
- Automated tests use an explicit test-root dependency rooted in temporary homes, local bare
  remotes, and disposable worktrees. Default/live lifecycle commands expose no root override,
  make no GitHub request during tests, and touch no real repository.
- A live install, update, or repair builds only from the durable primary Skills checkout when every
  capability input and `.eco-registry.lock` matches the exact reviewed commit and no untracked
  capability input exists. Dirty or ambiguous source refuses before staging.
- Lifecycle writes use owner-verified, descriptor-relative, no-follow user installation roots and
  same-directory atomic replacement; symlinked, special, changed, or multiply linked regular-file
  targets refuse before mutation.
- No GitHub Actions runner, hosted/paid service, full Xcode, XCUITest, or third-party package is a
  prerequisite.
- Acceptance of this plan authorizes no source, registry, lock, installation, release, PR, or
  remote mutation; implementation still requires separate explicit operator GO.

## 1. Purpose

The operator needs one native menu/shortcut entry point to discover current repositories beneath
`~/dev`, choose any subset, and advance only a provably safe checked-out local `main` to the exact
remote commit fetched for that attempt. The utility must deliberately handle all important failure,
concurrency, interruption, and reporting states while remaining one small local capability.

This plan maps the transcript-backed requirements into the selected Skills shelf, component
boundaries, cross-repository registry sequence, milestones, verification, distribution, and
rollback. It does not implement them.

## 2. Scope and non-goals

### In scope

- One direct source-owning global tool capability at `global/tools/dev-main-sync/`.
- Existing `meta.yml`/`tool.yml`/Flavor-1 snapshot semantics, Skills metadata lock, bootstrap
  install/reconcile, and WF1 `excluded` registration.
- Dynamic repository discovery, common-Git-directory deduplication, policy exclusions, and
  execution-time revalidation.
- Native selection, exact confirmation, progress, cancellation, report/reopen, status menu, fixed
  global shortcut, default-app log opening, **Close Run**, and **Quit Utility**.
- Complete safe-Git state matrix and result taxonomy.
- One run/worker owner, verified takeover, process-group cleanup, crash recovery, and one private
  current/latest log.
- Deterministic local build/package, ad-hoc signature, user LaunchAgent, install/reconcile/repair,
  doctor, current-source update, atomic rollback, and uninstall.
- Hermetic core/integration tests, local native smoke/accessibility UAT, static Skills checks,
  lock/registry/zero-link checks, and end-to-end release gates.

### Explicit non-goals

- A standalone repository, SSP, GCB, release descriptor, copied snapshot, or binary-release channel.
- Any downstream capability payload, native downstream bootstrap, or downstream policy change.
- Updating outside `~/dev` or inspecting macOS system `/dev`.
- Switching/moving a checkout, creating missing branches, updating a non-checked-out `main`,
  repairing repositories, resolving divergence, or rolling back completed updates.
- Parallel processing, scheduling, automatic sync/update, notifications, per-repository
  preferences, configurable shortcut, retained history, or historical dashboard.
- GitHub API runtime usage, credential management, cloud state, telemetry, analytics, or paid
  infrastructure.
- Developer ID/notarization, App Store, Intel, multi-user, or cross-platform distribution.
- A generic native-app builder, installer framework, policy framework, workflow engine, or plugin
  architecture.

### Assumptions and decision dependencies

- `state: excluded` remains the accepted WF1 treatment for a global Darwin/GUI,
  host-specific capability.
- One-Mac source build plus ad-hoc signing remains sufficient; notarization and binary distribution
  are not required.
- M1 can prove a complete AppKit build/package/launch path with the installed Command Line Tools.
- Product source can remain home-relative and free of absolute operator or downstream literals.
- The live host-policy declaration shapes remain statically readable through the bounded adapter;
  unknown or dynamic shapes stop release.
- The single-user v1 threat model covers mistakes and observable concurrent drift, not a malicious
  same-UID process racing metadata replacement between the final child-side check and Apple Git's
  own open. No user-space pathname design can make that interval a security boundary.

If any assumption fails, the named milestone stops and the ADR is reopened; the executor does not
add shared infrastructure or weaken safety.

## 3. Background, authority, and live evidence

### 3.1 Decision and authority

ADR 0003 selects the global capability after both alternatives pass every hard gate on current
evidence and share the same M1 proof condition for the CLT-only AppKit inference. The standalone
repository scores 87.6 and the global capability 84.6; the 3.0-point difference is below the
predefined 10.0-point materiality threshold, so the operator's transparent Alternative 2
tie-breaker applies.

`KleinPerkins/skills` is both the selected implementation owner and the canonical ADR/plan owner.
No artifact handoff is required. `KleinPerkins/ecosystem-orchestrator` owns only the WF1 registry
state and downstream relationship. `KleinPerkins/dev` supplies read-only workspace/policy context.
Neither gets a duplicate decision or plan.

### 3.2 Evidence incorporated by reference

ADR 0003's evidence register is part of this plan. Load-bearing facts are:

- `KleinPerkins/skills@83425665` accepts Flavor-1 snapshot tools, uses the Git commit for source
  identity and `.eco-registry.lock` for normalized metadata, and invokes a tool installer when
  `post_mgmt` is not `none` (E2–E4).
- `KleinPerkins/ecosystem-orchestrator@f3cbeaeb` treats registry `excluded` as governed inventory
  with expected downstream omission and delete-propagation (E5–E6).
- the downstream consumer has no native macOS activation contract, so exclusion—not a new payload
  path—is the compliant v1 lifecycle (E8).
- `KleinPerkins/server-guard@7a4abe7e` establishes nearby Swift source-build/install precedent;
  the installed macOS SDK and Command Line Tools support, but do not yet prove, the complete
  AppKit bundle. M1 owns that proof (E9, E12).
- `KleinPerkins/awa@a88f229b` establishes safety patterns for clean/attached/idle FF-only Git
  maintenance and uncertainty handling (E10).
- local-jobs, AWA, and the dev overlay establish lock/process identity, process group,
  TERM/KILL/reap patterns to adapt (E11).
- live dev worktree policy and baseline sources split hard exclusions across physical paths,
  repository identity, and hook-framework state, requiring a fail-closed pre-Git adapter rather
  than a static repository registry (E13).
- installed Apple Git 2.50.1 `git-config(1)` states that `GIT_SSH_COMMAND` overrides
  `core.sshCommand` and that `remote.<name>.uploadpack` changes the fetch-side program. v1 therefore
  rejects those effective custom commands instead of silently suppressing configured behavior.
- installed `codesign(1)` **SIGNING ATOMICITY** states that signing may modify code by adding
  signature data, while verification checks that sealed components are unaltered. Build identity
  therefore seals source metadata with the bundle and compares a post-sign staged/installed
  digest; it does not place a self-referential executable/resource hash inventory inside the
  bundle.

### 3.3 Affected repositories and intended areas

| Repository | Intended future changes | Explicit boundary |
|---|---|---|
| `KleinPerkins/skills` | `global/tools/dev-main-sync/`; `.eco-registry.lock`; this ADR/plan/indexes | Owns all product source/package/docs. Existing repository-wide manifest/lock checks apply; no shared shelf/schema/bootstrap change. |
| `KleinPerkins/ecosystem-orchestrator` | `config/registry.yml` excluded row; focused existing consistency/status verification only | Sole WF1 state owner. No orchestrator code or downstream PR. |

No implementation change is planned in `KleinPerkins/dev`, AWA, server-guard, cpp, or any target
repository. Their files are evidence or runtime read-only policy inputs only.

## 4. Final target architecture

### 4.1 Canonical capability shape

The future source unit is:

```text
global/tools/dev-main-sync/
├── meta.yml
├── tool.yml
├── README.md
├── install.sh
├── Package.swift
├── Sources/
│   ├── DevMainSyncCore/
│   └── DevMainSyncApp/
├── Resources/
├── Tests/
└── scripts/
```

`meta.yml` uses only existing fields:

- `schema: kp-capability/v1`
- `id: dev-main-sync`
- `kind: tool`
- `flavor: 1`
- `scope: global`
- `owner: KleinPerkins`
- `install: install.sh`
- `post_mgmt: launchd`
- `shape: snapshot`
- `sync_policy: none`
- `expose: cursor claude codex`
- empty supported `provenance_source`, `provenance_ref`, and `provenance_trust` fields because
  Flavor 1 owns source in place

`tool.yml` is the operator/agent-readable tool descriptor. It names the native app and
`install.sh` entrypoint but contains no downstream-specific or absolute machine literal.
`.eco-registry.lock` is regenerated by the existing lock script; it is never hand-edited.

The WF1 registry row is created through the orchestrator's existing exclude verb with a reason
limited to the Darwin/GUI and host-specific non-propagation boundary. The source exists globally
for machine-wide use, but no downstream payload, manifest entry, installer call, or bootstrap
activation is produced.

### 4.2 Component boundaries

| Component | Responsibility | Intended source area |
|---|---|---|
| App host | `NSStatusItem`, menu, fixed shortcut, launcher ownership, selection/progress/report windows, main-actor rendering, worker launch/control, report reopen | `Sources/DevMainSyncApp/` |
| Core model | Stable repository/run/result types, state machines, monotonic timing, presentation-neutral reducers | `Sources/DevMainSyncCore/Model*` |
| Discovery/policy | Bounded no-follow scan, umbrella handling, `.git` directory/file recognition, topology/dedup, GitHub origin validation, governing-policy adapter | `Sources/DevMainSyncCore/Discovery*`, `Policy*` |
| Git inspector/executor | Descriptor-bound direct argument-array Git, raw/effective origin and ordinary-object-graph gates, pre/post inspection, captured-target decision, no-recursion fetch, FF-only update, result classification | `Sources/DevMainSyncCore/Git*` |
| Internal worker | Same executable under a private worker verb; serial coordinator, one Git group, timeouts, cancellation, event stream, final result | `Sources/DevMainSyncApp/Worker*` backed by core modules |
| Process ownership | Close-on-exec launcher/lifecycle/run locks, Git-child-inherited operation lease, spawn/cancel exec gate, ephemeral owner-only host control socket, process birth/executable/group checks, TERM/KILL/reap, channel-loss cleanup | `Sources/DevMainSyncCore/Process*` |
| Log/report | One descriptor-relative single-link `latest.log`, exclusive truncation, framed escaped subprocess data, redaction/bounds, final/partial report reconstruction | `Sources/DevMainSyncCore/RunLog*` |
| Build/lifecycle | Swift release build, bundle/Info.plist, ad-hoc sign, LaunchAgent, atomic user install/reconcile/repair/doctor/uninstall | `scripts/`, `Resources/`, `install.sh` |

The core has no AppKit import. Production uses no third-party library. Process, clock, filesystem,
and event-sink boundaries are injectable only in tests; a production launch cannot override Git,
root, or policy through an untrusted environment variable.

### 4.3 Installed layout

| Item | v1 contract |
|---|---|
| Canonical source | durable primary checkout `~/dev/capabilities/skills/global/tools/dev-main-sync` |
| App | `~/Applications/Dev Main Sync.app` |
| Executable | `Contents/MacOS/DevMainSync`; host plus private internal worker mode |
| LaunchAgent | `~/Library/LaunchAgents/com.kleinperkins.dev-main-sync.plist`; `RunAtLoad=true`, `KeepAlive=false` |
| State | `~/.local/state/dev-main-sync`, where `~` comes from `getpwuid(geteuid())`; physical owner-only `0700`; production ignores `HOME`/`XDG_*` overrides |
| Log | one descriptor-relative, no-follow regular `latest.log`, mode `0600`, link count one |
| Coordination | empty launcher/lifecycle/run lock files, a separate operation-lease file, and one ephemeral host control socket, all owner-only; names/metadata hold no authority |
| Build identity | code-signature-sealed bundle metadata binding version, producing Skills commit, and source-input digest; installer records the post-sign staged/installed bundle digest as command evidence, and doctor verifies signature plus metadata without a separate receipt |

Uninstall removes the app, LaunchAgent, socket/locks after verified drain and preserves
`latest.log`, reporting its path. No repository selection, configuration, run history, or separate
lifecycle receipt is persisted.

### 4.4 Capability lifecycle

1. Before source lands, the orchestrator WF1 row records `state: excluded`; this pre-registration
   creates no payload and ensures the forthcoming global source is never unknown to the registry.
2. A reviewed Skills change adds or updates canonical tool source, tests, descriptor, installer,
   and regenerated `.eco-registry.lock`; status/consistency must then show the global source
   covered and the downstream omission expected.
3. On the durable primary Skills checkout, `bootstrap.sh --reconcile` invokes the idempotent
   installer because `post_mgmt: launchd`.
4. The installer first proves that the durable primary checkout's capability inputs and metadata
   lock are tracked, clean, and byte-identical to one captured reviewed Skills commit, then derives
   its deterministic source-input digest and verifies the capability's metadata-lock row. If the
   existing sealed bundle metadata already matches that digest/contract and the read-only doctor
   finds healthy installed/LaunchAgent state, reconcile returns a no-op without building or
   relaunching an absent utility; an unrelated Skills commit may differ, while the sealed metadata
   honestly retains the commit that produced the identical installed bytes. Otherwise it
   copies those exact tracked bytes into private staging, verifies the staged source-input digest,
   builds there with Command Line Tools, assembles one app whose bundle metadata binds its version,
   Skills revision, and source-input digest, ad-hoc signs/verifies it, then records the post-sign
   staged bundle digest in command evidence. Before any required app/LaunchAgent mutation it rechecks
   the
   captured source identity, opens the fixed state root, acquires the lifecycle lock
   exclusively/nonblocking, then acquires the operation lease exclusively/nonblocking. Worker
   lifecycle ownership or a surviving Git-child lease makes that ordered acquisition fail; the
   installer releases anything acquired, exits non-zero, and changes no installed byte. While both
   are held, no new worker can start and no prior Git holder survives. It asks any verified idle
   launcher to exit, unloads only the owned LaunchAgent label, waits for launcher-lock release, and
   acquires that lock for the mutation; unverifiable ownership or drain refuses unchanged. It then
   opens and verifies the user app/LaunchAgent roots and prior targets without following aliases,
   atomically installs, renders one user LaunchAgent, releases the launcher lock only for the
   controlled bootstrap/start, verifies the installed digest against the post-sign staged digest
   and verifies bundle/launch readiness, and only
   then releases both lifecycle gates. Any failure after launcher drain or bundle
   promotion—including plist rendering, LaunchAgent bootout/bootstrap, process start, or readiness
   verification—restores the prior bundle and plist or removes newly promoted state when none
   existed, restarts/verifies the prior launcher when one existed, and exits non-zero before
   releasing the gates.
   Abrupt installer death can bypass that handler but cannot expose a partial bundle: promotion is
   a same-directory rename. App run admission refuses when sealed bundle metadata, owned plist/job, and
   lifecycle readiness do not agree. On the next reconcile, exclusive gates plus staged/backup
   inventory deterministically keep a fully healthy promoted version and remove residue, or restore
   the complete prior version (remove a partial first install) before retrying; no separate
   lifecycle database or trusted marker is added.
5. `global/tools/dev-main-sync/install.sh --doctor` verifies actual installed state;
   repository-wide bootstrap/static checks continue to verify the capability record without
   claiming native runtime health.
6. Update means advancing the durable Skills checkout through its governed Git/PR lifecycle and
   rerunning reconcile; there is no in-app updater or published binary.
7. Repair is the same canonical-source reinstall with forced verification. A failed replacement
   restores the prior bundle/LaunchAgent.
8. Uninstall acquires the same ordered exclusive lifecycle-plus-operation gates before mutation.
   Contention or unverifiable ownership exits non-zero and leaves app, LaunchAgent, coordination
   state, and log unchanged. With verified exclusive ownership, it asks the idle launcher to quit,
   unloads only the owned label, acquires the released launcher lock, removes only owned
   app/lifecycle state, keeps the latest log, and releases all gates. Source removal separately
   removes the shelf through Skills governance, removes the WF1 row after omission proof, and
   regenerates the lock.

No bootstrap or installer runs from a disposable linked worktree for a release install. Development
tests use an explicit test-only root dependency rather than production `HOME`/`XDG_*`, and may
build from an isolated worktree without activating the live app.

### 4.5 Launcher, worker, and ownership protocol

1. Launch Services normally reactivates the existing app. Any duplicate process first tries a
   nonblocking no-follow `0600` launcher lock; contention becomes a same-UID activation client over
   the incumbent host's private control socket, never a signal.
2. A confirmed run launches the same executable in internal worker mode with a random generation
   and typed local event/control channels. Before admission, the worker acquires, in order and
   nonblocking, the lifecycle lock shared, the operation lease exclusively, and the run lock
   exclusively. Exclusive lifecycle ownership blocks admission; operation/run contention reports
   the existing or surviving run.
3. The worker holds all three before truncating `latest.log`, publishing diagnostics, or invoking
   Git. Failure leaves prior log bytes unchanged. Launcher/lifecycle/run lock descriptors remain
   close-on-exec as required by singleton policy; only a separately duplicated operation-lease
   descriptor is inherited by each Git child.
4. The launcher-lock owner exposes one `0600` host control socket. A duplicate must pass same-UID
   peer and host-generation challenge before it can request existing-run presentation. The
   incumbent host may target its worker only when the live typed channel, current lock holder,
   worker generation, process start identity, executable path, and process group agree. Persisted
   PID/PGID/token or socket name alone has no authority.
5. Explicit takeover requests cooperative cancel, waits for child drain and all gate releases,
   and only then performs fresh discovery. Failed contact/identity stops and starts nothing.
6. Child admission, process-group creation, identity publication, and cancellation admission-close
   share one synchronization gate. A forked child waits on an exec gate until the parent has
   recorded its group/identity and lease; cancellation before release terminates and reaps it.
7. The worker owns at most one Git process group. Cancel/timeout closes admission, sends TERM,
   waits, sends KILL only if the same group remains verified, and waits/reaps.
8. Host-channel EOF invokes the worker's same cancellation path, flushes a terminal/partial log,
   releases all gates, and exits. Worker loss makes the host inspect/drain only same-generation
   owned children and report attention.
9. Full host/worker crash releases authority locks, but a surviving Git group retains the inherited
   operation lease. A restarted worker fails lease acquisition; an installer may acquire lifecycle
   exclusivity but must release it unchanged when lease acquisition fails. Both report the prior
   operation still active, start/change nothing, and send no signal. Once all holders exit, a new
   worker may acquire all gates, parse `latest.log`, treat an old socket/metadata as residue, and
   revalidate from scratch.

Crash reconstruction has one deterministic presentation contract. Completed rows keep their
terminal results. Any row that was active without a terminal record receives read-only postflight
and resolves to `UPDATED_BEFORE_CANCELLATION`, `CANCELLED_NO_UPDATE`, or `NEEDS_ATTENTION`; every
unstarted row becomes `CANCELLED_PENDING`. The aggregate report is **Previous run interrupted —
review required** and remains reopenable from the latest log. While a surviving operation-lease
holder
exists, the launcher instead shows **A previous Git operation is still active** with “Dev Main
Sync will not start another run until it exits.” It offers report/log inspection but no new run or
signal, plus the recovery text: “If it does not finish, restart your Mac before trying again. Dev
Main Sync will not force-stop an operation it cannot verify.” Reconstruction occurs only after
inherited lease release.

Local Git inspection timeout is five seconds; network fetch timeout is 120 seconds. Timeout uses
the exact cancellation path. On operator cancellation, the host gives the worker up to two seconds
to acknowledge cleanup only after closing admission and sending verified process-group `SIGTERM`.
If the worker does not acknowledge, the host revalidates the same
generation/group before sending `SIGTERM` itself. Either owner then allows five seconds from that
verified TERM, sends `SIGKILL` only if the same owned group remains, and waits up to two additional
seconds to reap. A holder still present after that bound produces `NEEDS_ATTENTION`; its inherited
operation lease keeps new runs and lifecycle mutation blocked until kernel-observed release. These
are fixed v1 constants, not operator controls. The utility itself detaches no child.

The lock owner opens `latest.log` with descriptor-relative no-follow semantics, validates owner,
mode, stable device/inode, and link count one, and only then truncates. Worker-authored
newline-delimited records carry a fixed type/run envelope; bounded subprocess bytes are escaped
inside data fields and can never become record framing or recovery authority. A partial trailing
record is ignored on reconstruction. Any file-identity check failure preserves existing bytes,
reports attention, and starts no run.

### 4.6 Discovery and policy

Discovery constructs physical canonical `~/dev` from `getpwuid(geteuid())` and a literal `dev`
component, ignoring `HOME`/`XDG_*`; it never normalizes or probes system `/dev`.

It:

1. evaluates the canonical umbrella checkout separately, then scans below it;
2. reads authoritative host worktree-policy declarations and the static hard path/owner exclusions
   in the host baseline classifier as data, without executing that classifier, and applies path
   exclusions before descent;
3. never follows directory symlinks or escapes the physical root;
4. recognizes `.git` directories and linked-worktree `.git` files, prunes generated/heavy trees,
   stops below each non-root repository boundary, and rejects unsupported hook-framework markers
   through filesystem inspection before invoking Git;
5. resolves candidate `.git`/`commondir`, common/local/worktree config, and required metadata with
   bounded no-follow filesystem reads; rejects includes, malformed/multiple origins, escaping
   `core.worktree`, unparsed worktree config, replacement/graft metadata, object alternates, and
   symlinked or out-of-root Git/object metadata as uncertain; captures physical device/inode
   identities; and compares the raw credential-stripped `origin` identity against derived hard
   owner exclusions before any Git process;
6. only then asks Git with direct arguments/NUL-safe parsing for top level, Git/common directories,
   primary/linked worktrees, branch, and the effective fetch URL after user/system config rewriting;
   raw and effective URLs must both be supported GitHub SSH/HTTPS forms for the same repository
   identity; effective `remote.origin.uploadpack` must be absent, and effective `core.sshCommand`
   must be absent for SSH origins. A mismatch or custom transport command is an unsafe runtime
   exclusion before network access, not a retroactive
   claim that the already completed non-network probe ran inside a path/raw-identity-excluded root;
7. deduplicates by canonical common-directory identity, retaining complete topology;
8. accepts one credential-free GitHub SSH/HTTPS origin, including trusted third-party repositories
   in policy-permitted paths; and
9. sorts normalized relative path then identity.

The policy adapter accepts only the existing bounded declaration shapes and extracts static
physical-path and owner/repository exclusions generically, without embedding downstream-specific
literals or executing Git in a path-, raw-origin-, or hook-excluded root. It distinguishes hard
safety exclusions from baseline criteria that this product deliberately evaluates later (for
example cleanliness) or overrides (the eligible umbrella and permitted GitHub third-party
origins). The explicit product contract permits the canonical root even when another tool's
worktree policy excludes the umbrella for its own purpose. Unsupported, unreadable, conflicting,
dynamic, escaping, or failed policy/classifier/config interpretation excludes the candidate and
blocks release until parity is restored.

This is a versioned policy-format adapter, not a user-editable repository allow/deny registry.
Global source tests use generic fixture names; target-Mac acceptance derives every actual excluded
root from live policy and asserts zero descent/Git. If a governing exclusion cannot be derived
before Git without changing host policy/framework or embedding a prohibited global literal,
implementation stops and reopens ADR 0003.

If the governing host policy itself is missing, unreadable, conflicting, or unsupported at
runtime, selection does not open an apparently empty normal list. It shows **Repository Safety
Policy Unavailable** and “Dev Main Sync could not verify which repositories are safe to inspect.
No repositories were checked.” The only action is **Close**; no new run or log is created and no
candidate receives Git.

Dirty/non-main/ahead/temporarily busy repositories remain selectable when governance permits;
runtime preflight skips them. Duplicates and policy-excluded paths never become rows and receive
zero Git mutation.

### 4.7 Per-repository Git transaction

For each selected row in displayed order, the worker:

1. reopens without following aliases and re-proves root containment, common identity, topology,
   governing eligibility, origin identity, local `main`, clean index/worktree including untracked
   state, hidden index bits, active operations, locks, and absence of replacement refs, grafts,
   alternates, escaping worktree config, or symlinked Git metadata. It records—without yet using as
   a fetch gate—whether the primary is attached on `main` and whether a linked worktree claims
   `main`; it retains no-follow descriptors and device/inode identities for the worktree, Git
   directory, common directory, object directory, and parsed common/local/worktree config;
   dirty, busy, hidden-index, detached, custom-transport, and other terminal prefetch states return immediately per
   the state matrix, while a clean primary on another branch or with `main` in a linked worktree
   may continue only through fetch/classification;
2. constructs a closed child environment from the effective user's canonical home/identity, fixed
   system `PATH`, locale, `TMPDIR`, `SSH_AUTH_SOCK`, and approved proxy variables only; strips all
   inherited `GIT_*`, askpass, SSH-command, trace/TRACE2, curl-verbose, and output-redirection
   variables; connects standard input to `/dev/null`; sets `GIT_TERMINAL_PROMPT=0`, fixed false
   Git/SSH askpass, and—only for SSH origins—a fixed `/usr/bin/ssh` command with `BatchMode=yes` and
   no TTY; sets no-replace behavior explicitly; and invokes the observed absolute Apple Git
   executable directly with argument arrays. The forked child uses `fchdir` on the retained
   worktree descriptor, reopens Git metadata relative to that directory, compares every retained
   identity, and only then passes its exec gate; mismatch skips the row;
3. immediately resolves the effective fetch URL and transport-command config again, requires the
   same approved GitHub repository identity plus absent `remote.origin.uploadpack` and, for SSH,
   absent `core.sshCommand`, then invokes the equivalent of
   `git --no-replace-objects fetch --no-tags --no-prune
   --no-recurse-submodules origin refs/heads/main:refs/remotes/origin/main`—with each token passed
   as a separate argument, no leading `+` refspec, and the descriptor-entered worktree as current
   directory—recording success/failure, before/after remote-tracking commit, and fetched commit;
4. freezes that fetched commit as the attempt target;
5. re-proves descriptor/path/config identity, policy, raw/effective origin, topology, locks, clean
   attached primary `main`, replacement/graft absence, hidden-index absence, and expected local
   commit after fetch;
6. reports exact equality as `ALREADY_CURRENT`, local-ahead as `SKIPPED_AHEAD`, divergence as
   `SKIPPED_DIVERGED`, and local-behind as the sole update candidate;
7. for behind only, invokes the equivalent of
   `git --no-replace-objects merge --ff-only --no-overwrite-ignore --no-autostash
   <captured-commit>` with separate arguments from the descriptor-entered primary worktree,
   without switching, creating a ref, or honoring configured autostash; and
8. verifies attached `main`, HEAD at captured target, and clean index/worktree. Preserve/report
   residue; ambiguous poststate is `NEEDS_ATTENTION`, never success.

Configured credential helpers, hooks, filters, fsmonitor, and maintenance may run. The utility does
not suppress them. Submodule fetch recursion is explicitly disabled. It rechecks after
fetch/update, never resets/cleans residue, and continues to the next row after an isolated result.
This creates one unavoidable contract boundary: NFR-PRI-01 governs network clients authored by Dev
Main Sync and the Git transport destination it selects; it cannot truthfully guarantee that an
existing repository hook, credential helper, filter, fsmonitor, or maintenance program never opens
another connection without suppressing or sandboxing repository behavior, both outside v1 and
contrary to the safeguard contract. Release evidence therefore combines a static “no product
network client” audit, direct Git-origin transport observation, and controlled hook/helper
fixtures; it reports descendant egress separately rather than misattributing it to a product
endpoint.
“Product-owned descendant” means the worker, its direct Git child, and descendants that retain the
run's process-group or inherited lock identity. Repository automation that deliberately
disassociates from both has left that ownership boundary; the utility never signals it and never
claims to have stopped all external repository automation. This local single-user limitation does
not weaken the guarantee that every product-owned process is drained.

Every terminal row independently records `fetched` and `mainUpdated`; known before/target/after
commits; RFC3339 start/end and monotonic duration; operator explanation; and bounded technical log
detail.

### 4.8 Native journey and exact copy

The fixed shortcut is `⌃⌥⌘M`. A collision shows **Keyboard Shortcut Unavailable** in the menu,
leaves menu access working, and adds no preference control.

When idle, **Start New Run…** or the shortcut performs fresh discovery and opens **Update local
main branches**. The complete eligible list appears with no row selected. Controls are **Select
All**, **Clear All**, **Cancel**, and **Review Selection…**. **Review Selection…** is disabled at
zero selection; the inline message is: “Select at least one repository to continue.” Native help
text is: “Only clean main working copies are updated. Repositories that are changed, ahead,
diverged, busy, missing, or checked out elsewhere are skipped.”

Confirmation title is **Ready to update N repositories** and lists the exact selected
identities/paths. Its text is: “The utility will fetch origin and update only repositories that can
be fast-forwarded safely. It will not switch branches, discard work, or repair repositories.”
Buttons are **Back**, **Cancel**, and **Start Update**. Selection/cancellation changes no
repository, worker, or log.

Progress replaces selection and retains every row. Labels are **Pending**; **Checking**,
**Fetching**, or **Updating**; **Updated**; **Already Current**; **Skipped** or **Updated with
Warning**; **Failed** or **Needs Attention**; **Stopping…**; and **Cancelled**. Each uses a native
symbol and text; no meaning depends on color. **Open Log** and **Cancel Run** remain available
until stopping starts, then duplicate cancellation is disabled.

Cancellation warning:

> Stop this run? The current Git operation will be asked to stop. Repositories already completed
> will stay completed. Remaining repositories will be marked Cancelled.

Buttons are **Keep Running** (default) and **Stop Run**.

A second launch during an active run shows title **A run is already active** and message: “Dev
Main Sync is already updating N repositories. You can keep that run, or stop it safely and start a
new selection. Repositories already completed will not be rolled back.” Its actions are **Cancel
New Launch** (default) and **Stop Existing & Start New…**. The latter opens:

> Stop the active run? The current Git operation will be asked to stop first. If it does not exit,
> only this run’s verified process group will be force-stopped. The existing log remains available
> until a new run acquires ownership.

Buttons are **Keep Existing Run** (default) and **Stop & Start New**. Unverified owner copy:
“Nothing was stopped because Dev Main Sync could not verify ownership of the active process. No new
run was started.”

Final examples:

- **Run complete — 5 updated, 3 already current.**
- **Run complete with issues — 4 updated, 2 skipped, 1 failed. Completed updates were kept.**
- **Run cancelled — 3 repositories completed before cancellation; 5 were not run. Completed
  updates were kept.**

The report remains open with overall/per-row outcomes, run/repository start/end/durations, counts,
fetched/updated state, cancellation, and **Open Log**. **Close Run** releases report resources but
keeps launcher/log. Closing active progress only hides it; menu/shortcut restores the same model.
**Quit Utility** confirms cancellation if needed, drains owned resources, unregisters shortcut and
status item, and exits. Menu items are **Start New Run…**, contextual **Show Current Run** or
**Show Last Report**, **Open Latest Log**, and **Quit Utility**.

### 4.9 Result taxonomy

Every terminal result carries result code, UI class, `fetched`, `mainUpdated`, known
before/target/after commits, timing, operator explanation, and bounded technical detail.

| Class | Stable result codes |
|---|---|
| Success | `UPDATED`, `ALREADY_CURRENT`, `UPDATED_BEFORE_CANCELLATION` |
| Warning/skipped | `SKIPPED_AHEAD`, `SKIPPED_DIVERGED`, `SKIPPED_DIRTY`, `SKIPPED_BUSY`, `SKIPPED_PRIMARY_NOT_ON_MAIN`, `SKIPPED_MAIN_IN_LINKED_WORKTREE`, `SKIPPED_LOCAL_MAIN_MISSING`, `SKIPPED_REMOTE_MAIN_MISSING`, `SKIPPED_HIDDEN_INDEX_STATE`, `SKIPPED_UNSUPPORTED_HOOK_FRAMEWORK`, `SKIPPED_REPOSITORY_REMOVED`, `SKIPPED_ORIGIN_CHANGED`, `SKIPPED_IGNORED_FILE_COLLISION`, `UPDATED_WITH_WARNING` |
| Failure | `FAILED_INSPECTION`, `FAILED_FETCH_AUTHENTICATION`, `FAILED_FETCH_NETWORK`, `FAILED_FETCH`, `FAILED_UPDATE`, `NEEDS_ATTENTION` |
| Cancelled | `CANCELLED_PENDING`, `CANCELLED_DURING_FETCH`, `CANCELLED_NO_UPDATE` |

Excluded/duplicate discovery candidates never become run rows.

E0 also listed `CANCELLED_DURING_UPDATE`, but its more specific cancellation contract requires
read-only postflight to resolve that phase to `CANCELLED_NO_UPDATE`,
`UPDATED_BEFORE_CANCELLATION`, or `NEEDS_ATTENTION`. To keep one observable terminal truth, v1
uses `CANCELLED_DURING_UPDATE` only as a nonterminal worker diagnostic while postflight is pending;
it is never serialized as a terminal row result. AT-22 asserts exactly the three postflight
outcomes.

Fetch failures also carry one stable `failureReason` without adding result codes:
`authentication`, `dns`, `transport`, `timeout`, or `other`. Authentication maps to
`FAILED_FETCH_AUTHENTICATION`; DNS, transport, and timeout map to `FAILED_FETCH_NETWORK`; other
fetch failures map to `FAILED_FETCH`. The operator explanation and bounded log detail name the
reason, and AT-16 asserts every mapping plus continuation to the next row.

### 4.10 Complete state matrix

| State | Required behavior | Terminal result | Local `main` mutation |
|---|---|---|---|
| Local `main` behind fetched target | Revalidate, FF-only to exact target, verify | `UPDATED` | Yes |
| Local `main` equal to target | No merge | `ALREADY_CURRENT` | No |
| Local `main` ahead | Preserve local-only commits | `SKIPPED_AHEAD` | No |
| Local `main` diverged | Preserve both histories; no repair | `SKIPPED_DIVERGED` | No |
| Missing local `main` | Do not create | `SKIPPED_LOCAL_MAIN_MISSING` | No |
| Missing remote `main` | Preserve local | `SKIPPED_REMOTE_MAIN_MISSING` | No |
| Missing/invalid origin | Exclude; if changed after selection, skip | `SKIPPED_ORIGIN_CHANGED` | No |
| Raw/effective origin identity differs or stops being approved GitHub | Skip before network/update | `SKIPPED_ORIGIN_CHANGED` | No |
| Authentication failure | Report and continue | `FAILED_FETCH_AUTHENTICATION` | No |
| Network failure/timeout | Cancel/reap group; continue | `FAILED_FETCH_NETWORK` | No |
| Other fetch failure | Preserve, report bounded detail, continue | `FAILED_FETCH` | No |
| Dirty primary | Skip before fetch | `SKIPPED_DIRTY` | No |
| Clean primary on `main` | Fetch/classify | Relationship result | Behind only |
| `main` in linked worktree | Fetch may complete; never update local `main` | `SKIPPED_MAIN_IN_LINKED_WORKTREE` | No |
| Primary on another branch | Fetch may complete; never switch/update local `main` | `SKIPPED_PRIMARY_NOT_ON_MAIN` | No |
| Detached primary | Skip before mutation | `FAILED_INSPECTION` | No |
| Replacement ref or graft metadata | Skip; ordinary ancestry cannot be proven | `FAILED_INSPECTION` | No |
| Effective custom SSH command or origin upload-pack command | Skip before network; never override silently | `FAILED_INSPECTION` | No |
| Object alternate, escaping/symlinked Git metadata, or unsupported config shape | Skip before network/mutation | `FAILED_INSPECTION` | No |
| Unsupported hook framework appears after selection | Skip before Git | `SKIPPED_UNSUPPORTED_HOOK_FRAMEWORK` | No |
| Repository removed | Mark/continue | `SKIPPED_REPOSITORY_REMOVED` | No |
| Duplicate/symlink alias | Collapse common identity/reject escape | One/no row | At most once |
| Spaces/Unicode/metacharacters | One argument-array path | State-dependent | State-dependent |
| Pending operation/lock | Preserve/skip | `SKIPPED_BUSY` | No |
| Hidden index bits | Preserve/skip | `SKIPPED_HIDDEN_INDEX_STATE` | No |
| Fetch automation creates residue | No merge/cleanup | `SKIPPED_DIRTY` | No |
| Ignored-file collision | Git refuses; preserve | `SKIPPED_IGNORED_FILE_COLLISION` | No |
| Update command fails with verified unchanged ref and no ambiguous residue | Preserve/report/continue | `FAILED_UPDATE` | No |
| Update advances ref but command/postflight has a known warning or residue | Keep update and observed state; warn | `UPDATED_WITH_WARNING` | Yes |
| Update failure leaves ref/poststate ambiguous | Preserve and require operator review | `NEEDS_ATTENTION` | Unknown, reported |
| Local state changes after fetch | Abort | `FAILED_INSPECTION` | No utility update |
| Descriptor/path/config identity changes before a Git stage | Abort before that stage | `FAILED_INSPECTION`; post-update ambiguity is `NEEDS_ATTENTION` | No further utility update |
| `origin/main` moves after fetch | Use captured target; no latest claim | normal result + fetched time | At most captured target |
| Cancel during fetch | Stop/reap/inspect | `CANCELLED_DURING_FETCH` | No |
| Cancel before a pending row starts | Never schedule it | `CANCELLED_PENDING` | No |
| Cancel update before ref move | Preserve prior | `CANCELLED_NO_UPDATE` | No |
| Cancel after verified ref move | Keep completed update | `UPDATED_BEFORE_CANCELLATION` | Yes |
| Cancel with ambiguous update | Preserve/attention | `NEEDS_ATTENTION` | Unknown, reported |
| Worker crash, host survives | Drain same generation; inspect active row; cancel pending rows | active `NEEDS_ATTENTION`; pending `CANCELLED_PENDING` | Inspected |
| Host crash | Worker detects EOF, cancels/logs/exits; completed rows stay terminal, active row gets postflight, pending rows cancel | active postflight outcome; pending `CANCELLED_PENDING`; aggregate **Previous run interrupted — review required** | Inspected before exit/reopen |
| Full host/worker crash with surviving Git holder | Inherited operation lease blocks install and a new run; show blocked copy; send no signal; reconstruct only after proof of exit | no new terminal result while holder survives; then deterministic interrupted reconstruction | No overlap or stale action |
| Full crash with no surviving operation-lease holder | Acquire gates; trust no PID; reconstruct completed/active/pending rows from log plus read-only postflight | active postflight outcome; pending `CANCELLED_PENDING`; aggregate **Previous run interrupted — review required** | No stale action |
| Second launch: cancel new | Existing run/log unchanged | existing continues | None |
| Second launch: takeover | Cooperative stop, verified escalation, lock release, rediscover | prior cancelled; new selection | Prior completions kept |
| Takeover owner unverified | Stop/start nothing | operator-visible failure | No |
| Mixed completion | Keep detailed report open | “Run complete with issues” | Successful updates kept |

## 5. Requirements and verification ledger

Ranges are inclusive: `DISC-01–12` means every ID in that sequence. E0 in ADR 0003 remains the
source of exact SHALL wording and acceptance criteria; this plan preserves rather than renumbers
the complete contract.

**Source-contract proof.** Parent transcript
`8084ff59-5a37-4458-b6aa-65aa90eb1f33.jsonl` event 1 is the original operator request and event 22
is the revised requirements specification (requirements §§11–14, traceability §16, acceptance
§15). The stable catalog copied from that source is:
`SC-01–08`, `INV-01–10`, `ARCH-01`, `DISC-01–12`, `SEL-01–10`, `EXEC-01–08`,
`GIT-01–26`, `PROG-01–07`, `CANCEL-01–09`, `SINGLE-01–11`, `LOG-01–12`,
`REPORT-01–06`, `ACCESS-01–06`, `LIFE-01–07`, `NFR-RSP-01–02`,
`NFR-REL-01–04`, `NFR-A11Y-01–04`, `NFR-PRI-01–03`, `NFR-PERF-01–03`,
`NFR-COMP-01–02`, `NFR-INST-01–05`, `NFR-MNT-01–04`, and `AT-01–33`. The
grouped rows below map every member of those inclusive ranges; their summaries do not replace the
exact source SHALL/acceptance text.

### 5.1 Verification families

| Family | Required future evidence |
|---|---|
| `VT-CAP` | Capability manifest/tool descriptor, source ownership, lock parity, excluded registry, bootstrap dry-run recognition and release reconcile, direct installer doctor, zero-link, downstream absence |
| `VT-CORE` | Swift unit tests for models/reducers/policy/redaction/parsing/timing without AppKit |
| `VT-DISC` | Temporary-tree discovery, no-follow/symlink/Unicode/common-dir/worktree/policy/config/alternate-object fixtures and 100-candidate benchmark |
| `VT-GIT` | Local bare remotes, full matrix, exact command audit, raw/effective URL rewrite, custom SSH/upload-pack refusal, no-recursion checks, replacement/graft ordinary-graph cases, worktree-descriptor and metadata-drift gates, moving target, hook residue, hidden index, collision, timeouts |
| `VT-PROC` | Fixed-root lifecycle/run/operation-gate races, live-owner challenge, stale PID/PGID, spawn/cancel exec-gate races, simultaneous host/worker crash with surviving child trees, channel loss, TERM/KILL/reap/resource counts |
| `VT-UI` | Main-actor/view-model tests, AppKit construction/launch smoke, menu/hotkey states, exact-copy snapshots, defined event-to-render latency trial, manual VoiceOver/keyboard/appearance UAT |
| `VT-LOG` | Descriptor-relative exclusive truncation, hardlink refusal, permissions, framed/escaped subprocess bytes, bounds/redaction, partial/final reconstruction, default-app open/failure |
| `VT-PKG` | Bundle metadata/inventory/signature, explicit test-root install/repair/update/rollback/uninstall, LaunchAgent inspection |
| `VT-E2E` | Isolated test-root native journey through one exact safe update/report plus AT-01–33 on target Mac |

### 5.2 Requirement-to-ADR-to-milestone-to-test traceability

| Source IDs | Contract | Milestones | Proof |
|---|---|---|---|
| `SC-01`, `INV-01`, `INV-03`, `DISC-01–12` | Fresh bounded discovery, no `/dev`, eligibility/dedup/topology, no excluded mutation | M1, M2 | `VT-DISC`; AT-01–07, AT-15 |
| `SC-02–04`, `INV-02`, `INV-04–05`, `GIT-01–26` | Captured target, FF-only/no-op/refusal matrix, no destructive/remote write | M1, M3 | `VT-GIT`; AT-07, AT-10–19 |
| `SC-05`, `INV-06–07`, `SINGLE-01–11` | One launcher/run, safe second launch/takeover, no stale PID authority | M1, M4 | `VT-PROC`; AT-23–27 |
| `SC-06`, `CANCEL-01–09` | Responsive cancellation, bounded owned cleanup, no orphan/rollback | M4 | `VT-PROC`; AT-20–22, AT-27, AT-33 |
| `SC-07`, `INV-09`, `EXEC-01–08` | Confirmed deterministic serial run and isolated-failure continuation | M1, M3 | `VT-CORE`, `VT-GIT`; AT-09–19 |
| `SC-08`, `INV-08`, `SEL-01–10`, `PROG-01–07` | Complete responsive native selection/confirmation/progress | M1, M2, M5 | `VT-UI`, `VT-E2E`; AT-08–09, AT-29–31 |
| `ARCH-01` | One native app bundle, one resident host, same-executable serial worker, testable non-AppKit core | M1, M6 | `VT-CAP`, `VT-CORE`, `VT-PKG`; bundle/process inventory |
| `INV-10`, `LOG-01–12` | One private bounded/redacted log; ownership-before-truncate; open/reconstruct | M1, M4, M5 | `VT-LOG`; AT-23–24, AT-27–29, AT-31 |
| `ACCESS-01–06`, `REPORT-01–06`, `LIFE-01–07` | Menu/shortcut/reopen/report/Close/Quit/resource cleanup | M1, M5, M6 | `VT-UI`, `VT-PKG`; AT-29–33 |
| `NFR-RSP-01–02` | Main-actor responsiveness; 250 ms event-render target | M1, M5 | `VT-UI`; AT-29 |
| `NFR-REL-01–04` | 5 s local/120 s fetch timeout; shared cleanup; channel/crash safety | M3, M4 | `VT-GIT`, `VT-PROC`; AT-16, AT-20–22, AT-27 |
| `NFR-A11Y-01–04` | VoiceOver, keyboard, appearance, safe default focus | M5 | `VT-UI`; AT-30 |
| `NFR-PRI-01–03` | No product network client beyond selected-origin Git transport; no telemetry/content logging; repository-owned helper egress is attributed, not suppressed | M3, M4, M6 | `VT-LOG`, static product-client audit, effective-URL/no-recursion transport audit, controlled descendant-attribution fixture; AT-28 |
| `NFR-PERF-01–03` | 5 s/100-candidate discovery, no idle scan, one Git group | M2, M3, M6 | `VT-DISC`, `VT-PROC`; benchmark/process trace |
| `NFR-COMP-01–02` | macOS 26.6.2 arm64/Apple Git 2.50.1; safe paths | M1, M2, M6 | `VT-DISC`, `VT-GIT`, `VT-E2E`; AT-07 |
| `NFR-INST-01–05` | Sudo-free one-bundle CLT install, atomic repair, RunAtLoad/no KeepAlive | M1, M6 | `VT-CAP`, `VT-PKG`; AT-32–33 |
| `NFR-MNT-01–04` | AppKit-independent core, hermetic tests, no speculative component/dependency | all; M6 audit | `VT-CORE`, `VT-CAP`, inventory audit |

No stable source requirement is deferred. Product ideas outside the ID set remain non-goals.

### 5.3 Original acceptance-test schedule

| Tests | Milestone | Coverage |
|---|---|---|
| AT-01–07 | M2 | add/remove, no `/dev`, umbrella, worktree/symlink dedup, exclusions, origins, safe paths |
| AT-08–09 | M2/M5 | none/all/clear/subset, exact confirmation, pre-worker/log cancellation |
| AT-10–15 | M3 | behind/equal/ahead/diverged/missing/unsafe/changed behavior |
| AT-16–19 | M3 | failure continuation, captured target, ignored collision, hook residue |
| AT-20–22 | M4 | responsive/stubborn cancellation and ref-movement phases |
| AT-23–28 | M4 | ownership race, cancel/takeover, stale PID, deterministic crash/channel reconstruction, private redacted log |
| AT-29–31 | M5 | status/report copy, accessibility/keyboard, menu/shortcut/reopen/log |
| AT-32–33 | M6 | install/repair/Quit and lifecycle resource cleanup |

## 6. Dependencies, owners, sequence, and external gates

| Dependency/gate | Owner | Required before | Proof |
|---|---|---|---|
| Explicit implementation authorization | Laurence Duggan | M1 | Not granted by this plan |
| Skills capability source/metadata-lock governance | `KleinPerkins/skills` owner | each milestone merge | manifest/static checks, metadata-lock parity |
| WF1 excluded registry state | ecosystem-orchestrator owner | M1 completion/release | registry status + consistency; no downstream payload |
| Live host-policy parity/exclusion review | `KleinPerkins/dev` policy owner + product owner | M2 and release | read-only parity; no dev mutation |
| Safe-Git/process/log safety review | product owner/reviewer | M3, M4, and release | full `VT-GIT`, `VT-PROC`, `VT-LOG`, forbidden-command/signal/network audits |
| Target-Mac native/accessibility UAT | Laurence or delegate | M5/M6 | local CLT-only host |
| `⌃⌥⌘M` collision check | product owner/operator | M5 | collision label/menu fallback |
| Capability release/install approval | Laurence Duggan | M6 | all gates green; exact Skills commit, metadata lock, and verified bundle digest |

Order is M1 → M2 → M3 → M4 → M5 → M6. Each milestone is a reviewable production step. Cross-repo
delivery in M1 merges the orchestrator `excluded` row first, then the Skills source/metadata lock. An
excluded record with no source is inert under the current consistency algorithm; after source
lands, the known-set check is already satisfied. If live registry checks no longer accept that
order, hold both draft PRs and use the registry owner's documented safe sequence—never hand-vendor
or bypass.

## 7. Work items

Unless a row names another owner, the responsible implementer is the future
`KleinPerkins/skills` Dev Main Sync implementer; repository owners review and merge only their own
surfaces, and Laurence owns operator UAT and release authorization. A prerequisite cell names both
the dependency and any owner exception.

### Milestone 1 — Minimum viable end-to-end capability

M1 is the smallest vertical slice, not setup. It connects canonical shelf source and WF1-governed
non-propagation through a launchable native app that discovers one isolated eligible repository,
accepts one explicit selection/confirmation, safely fast-forwards a clean primary `main` behind its
captured target, renders the native result, writes the private log, and produces automated evidence.

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M1-T1 | Pre-register WF1 `state: excluded`, then create the canonical Flavor-1 snapshot descriptors/source layout, initial installer contract, and regenerated Skills metadata lock; no payload is produced. | Orchestrator `config/registry.yml` first; then Skills `global/tools/dev-main-sync/{meta.yml,tool.yml,README.md,install.sh,Package.swift,Sources,Resources,Tests,scripts}` and `.eco-registry.lock` | Explicit GO; orchestrator then Skills owners | Before source: excluded row is inert and consistency has no unknown global. After source: manifest/descriptor/metadata-lock/status/consistency green; source appears once; omission expected; downstream diff empty; zero-link global scan green | If Skills does not land, remove inert excluded row. If source lands, uninstall, remove shelf, regenerate the metadata lock, then remove row after absence proof; no downstream cleanup expected | `VT-CAP` source/registry/metadata-lock/no-payload report |
| M1-T2 | Implement AppKit-independent model plus minimal discovery seam, worktree-descriptor-entered direct Git runner with child-side metadata revalidation, ordinary-object-graph mode, effective-origin/no-recursion fetch, exact target, clean-behind/equal decision, and result fields. | `Sources/DevMainSyncCore/`; core tests | M1-T1 | `swift test` proves one behind exact update, equal no-op, raw/effective GitHub identity, no submodule recursion/replacement objects, `fchdir` worktree binding and pre-exec metadata mismatch refusal, explicit no-autostash with configured `merge.autoStash=true`, argument arrays, closed child environment, no terminal/askpass/SSH prompt, trace/output sentinels untouched, no banned command, no AppKit core import | Forward-revert source; temporary bare remotes removed after child drain; never reverse real repo | `VT-CORE`, initial `VT-GIT`, command/environment audit |
| M1-T3 | Implement same-executable worker, typed channels, one-row coordinator, fixed-root lifecycle/run authority locks plus Git-child-inherited operation lease, atomic spawn/cancel exec gate, descriptor-relative private log, cooperative cancellation, and final-log reconstruction. | Core process/log files; app worker entry; tests | M1-T2 | Lock race yields one owner; authority lock descriptors close on exec while a surviving Git-child lease blocks a new run and lifecycle mutation; conflicting `HOME`/`XDG_*` values cannot split production authority; busy/hardlinked log preserves bytes; subprocess bytes cannot forge records; events show checking/fetching/updating/result; channel EOF drains fixtures; log is `0600` and secret-free | Revert worker/log together; remove test state only; retain real latest log | `VT-PROC`/`VT-LOG` slice and resource baseline |
| M1-T4 | Implement LSUIElement status host, fixed shortcut, no-default selection, Review Selection, exact confirmation, progress, final report, Open Log, Close Run, Quit. Build/sign/stage one bundle and render its RunAtLoad/no-KeepAlive LaunchAgent under an explicit test root inside a temporary home; direct-launch the staged app and implement product-local `--check` and `--doctor`. | App source; `Resources/Info.plist`/LaunchAgent; build/install scripts | M1-T2–3 | Using Command Line Tools without `xcodebuild`: compile/package/direct-launch smoke and plist validation pass; the explicit test command stays inside its test root while default/live commands expose no root override; zero selection is inert; one row reaches Updated; report stays; no UI-thread Git wait; codesign/direct doctor green | Quit/remove staged app and plist; source revert does not touch target repos | `VT-UI`/`VT-PKG` slice, bundle inventory, screenshots/UAT notes |
| M1-T5 | Run the isolated native vertical slice from selection through exact update/report/log, verify bootstrap recognizes the post-managed tool in dry-run mode, then run the direct installer doctor and orchestrator status/consistency; prove no real path/network/downstream mutation. | integration fixture/test script within capability | M1-T1–4 | A test-only process seam maps a credential-free fixture GitHub SSH identity to a local bare remote; the behind repo reaches the exact fetched commit and report/log are complete. `bootstrap.sh --reconcile --dry-run` records the installer action without invoking it; the direct installer runs only in explicit test-root mode. The production bundle has no root/Git/SSH override; release inventory proves the seam absent. Real `~/dev`, `/dev`, external network, installed production state, and downstream stay untouched | Drain/delete fixture; uninstall explicit-test-root app; preserve failure evidence only within test temp until diagnosis | `VT-E2E` M1 transcript, OIDs, production-inventory and process/filesystem/network/capability audit |

**M1 gate:** one canonical capability, excluded WF1 state, launchable test-root app, bootstrap
recognition, and exact safe vertical path are proven under Command Line Tools alone; no live
installation, downstream payload, or real-repository mutation exists. Failure to compile, package,
launch, or exercise the AppKit slice stops later
milestones and reopens ADR 0003.

### Milestone 2 — Complete discovery, policy, and selection

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M2-T1 | Complete bounded root scan, umbrella, `.git` directory/file, no-follow containment, pruning, common-dir dedup, topology, raw/effective origins, stable sorting, and runtime descriptor/device/inode identity. | core discovery files/fixtures | M1 | AT-01–04, AT-06–07; 100 candidates <5 s; no `/dev`; safe spaces/Unicode/metacharacters; include/multiple-origin/escaping-worktree/worktree-config/object-alternate/symlink fixtures fail before Git; same-identity GitHub rewrites pass the later non-network effective check, while retargeting rewrites and effective SSH/upload-pack command overrides fail before fetch | Revert discovery source; no discovered list persists | `VT-DISC`, path/config/object audit, benchmark |
| M2-T2 | Complete live-policy adapter without prohibited literals: read bounded host worktree-policy and static hard path/owner exclusions as data, preflight raw candidate Git metadata and unsupported hook markers without Git, apply product root/third-party/cleanliness distinctions, fail closed on unknown shape with exact blocking copy, and add parity tests without a registry. | core policy files/fixtures | M2-T1; read-only dev policy review | AT-05; every live hard path/raw-origin/hook exclusion derived from policy gets zero descent/Git; excluded downstream target and hard-no-touch fixture are absent; valid permitted third-party remains; global policy failure matches **Repository Safety Policy Unavailable**, preserves the prior log, and invokes zero Git; effective rewrite must remain approved GitHub same-identity before network; zero-link passes | Revert adapter; release stays blocked on parity failure; never modify host policy as a workaround | `VT-DISC` policy parity tied to dev revision; zero Git invocation/mutation audit |
| M2-T3 | Complete native list/help and none/all/clear/subset/cancel/Review Selection/exact confirmation/back/Start Update states. | App selection controllers/view models/tests | M2-T1–2 | AT-08–09; list equals independent oracle; cancel leaves process/log hash; keyboard labels work | Revert UI slice; no selection persistence | `VT-UI` selection/accessibility evidence |

**M2 gate:** AT-01–09 and discovery half of AT-15 pass; live policy parity and zero-link are green;
no user-maintained repository registry exists.

### Milestone 3 — Complete safe-Git and serial matrix

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M3-T1 | Complete preflight/revalidation for worktree-descriptor and Git-metadata identity, clean attached primary `main`, raw/effective origin/topology/linked-main, operations/locks, replacement refs/grafts, hidden bits, expected commit, and fetch residue. | core Git inspector/fixtures | M2 | Dirty/detached/busy/replaced/grafted/hidden/missing/retargeted/swapped rows match the matrix without local-main mutation; controlled path/config swaps before every observable Git gate refuse; clean non-main and linked-main fixtures may fetch but always skip update without switching | Revert core; fixtures disposable; preserve unexpected fixture state | `VT-GIT` preflight matrix, AT-12–15 plus replacement/swap cases |
| M3-T2 | Complete non-force/no-tags/no-prune/no-recurse fetch, immutable target, no-replace-object topology/ancestry, post-fetch revalidation, equal/ahead/diverged/behind decision, worktree-bound FF-only/no-overwrite/no-autostash update, postconditions/warnings/errors. | core Git transaction/error/redaction files | M3-T1 | AT-10–19; effective URL retarget, custom SSH/upload-pack command, no-recursion, replacement/graft, configured-autostash, observable-gate path/config drift, and inherited trace/output-routing cases fail safe; fixture sentinels remain untouched; moving ref never substitutes; ignored collision/hook residue preserved; no banned family; fetched/update independent | Revert source only; never roll back a completed update | Full `VT-GIT`, OID, worktree/metadata identity, environment, and command evidence |
| M3-T3 | Complete deterministic multi-row coordinator, per-row continuation, 5 s local/120 s fetch timeouts, one group, monotonic timing, all result codes. | coordinator/timing/failure fixtures | M3-T1–2 | Auth/DNS/transport/timeout distinct and later row continues; one group; stable order; all fields serialize | Revert coordinator; completed rows stay; pending untouched | AT-16 plus serial/process trace |

**M3 gate:** all Git requirements and AT-10–19 pass; security review accepts the closed command
set, state matrix, and zero destructive/remote-write audit.

### Milestone 4 — Ownership, cancellation, takeover, and logging

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M4-T1 | Harden descriptor-relative no-follow launcher/lifecycle/run locks plus the separate operation lease, fixed effective-user root, close-on-exec authority locks with only the duplicated lease inherited by Git, owner diagnostics, same-UID host socket, host/worker generation challenges, lock-holder/birth/executable/group proof, atomic spawn/cancel gate, duplicate activation, and stale cleanup. | core process ownership/tests | M1 process slice; M3 | One launcher/worker; a verified duplicate routes through the incumbent host; lifecycle exclusivity and run admission cannot overlap; surviving lease blocks both; unrelated PID receives zero signals; unverified takeover starts nothing; conflicting environment roots, modes, symlinks, descriptors, and stale sockets fail safe; authority lock FDs never leak through exec; no child can exec before identity publication | Revert after fixture drain; remove stale names only when no live owner | `VT-PROC`, AT-23–27 signal/admission audit |
| M4-T2 | Complete cooperative cancellation, timeout reuse, fixed 2 s acknowledgement/5 s TERM/2 s post-KILL bounds, reverify before signal, wait/reap, host/worker/simultaneous loss, inherited operation-lease blocking, and read-only interrupted postflight/outcomes. | process supervisor/crash fixtures | M4-T1; M3 | AT-20–22,25,27; virtual-clock and real smoke evidence match every bound; responsive/stubborn/nested supervised descendants drain; a surviving holder returns `NEEDS_ATTENTION` and blocks a new run/lifecycle mutation without unrelated signalling; completed/active/pending rows reconstruct deterministically; before/after/ambiguous ref outcomes correct | Revert only after drain; completed updates remain; no cleanup Git | Signal/lock ordering, waits, reconstruction, and resource counts |
| M4-T3 | Complete readable structured log: descriptor-relative single-link open/truncate, fixed record envelope, escaped bounded stdout/stderr, RFC3339/run IDs, per-repo events, intent, control sanitization/redaction, exit/final/timing, flush-before-unlock, reconstruction/open/error. | core log/redaction/parser tests | M4-T1–2 | AT-23–24,27–28; two runs leave one log; non-owner/hardlink actions preserve hash; forged/newline subprocess bytes remain data; secrets/user-info/headers/env/content markers absent; partial-tail/truncation behavior explicit | Revert writer/parser compatibly; do not truncate an older readable log before ownership | `VT-LOG`, identity/mode/framing and seeded-secret evidence |

**M4 gate:** AT-20–28 plus inherited operation-lease, spawn/cancel, and log
identity/framing extensions pass;
no signal uses persisted PID/PGID alone, no new run overlaps a surviving prior Git holder, and no
owned descendant/resource remains after every terminal path.

### Milestone 5 — Complete native UX and accessibility

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M5-T1 | Render all rows/states/active phases, mixed/cancelled report, timings/counts/copy, Open Log and partial/final reopen within latency target. | progress/report controllers/reducers | M3–4 | AT-29; no row disappears; text/symbol distinctions survive monochrome; every §4.8 title/message/action/state/summary matches an exact-copy snapshot. In each of three 60-second target-Mac trials with 100 displayed rows and one synthetic worker event every 25 ms, monotonic time from event emission to completed main-actor render has p95 ≤250 ms | Revert presentation with compatible core/log | `VT-UI` exact-copy snapshots, state results, and raw/p95 latency evidence |
| M5-T2 | Complete menu and shortcut behavior by state, collision label, current/last report, active-window hide/restore, Close Run, Quit cancellation/drain, default-app log open/failure. | menu/hotkey/app lifecycle | M4 | AT-31,33; shortcut works frontmost; collision leaves menu; open failure inline; Quit stays gone until manual/login | Unregister status/shortcut; restore prior bundle through installer; log preserved | menu/hotkey/process/resource trace |
| M5-T3 | Complete VoiceOver order/labels, keyboard-only journey, safe default focus, enlarged text, dark/high-contrast layout, target-Mac operator UAT. | App accessibility/layout/tests; existing README test procedure only | M5-T1–2; operator | AT-30; complete journey without pointer; Return never confirms cancel/takeover; appearances usable | Revert UI release, not core/Git; retain prior install | automated semantics and operator UAT result |

**M5 gate:** AT-29–31 and target-Mac native/accessibility UAT pass; collision behavior is known and
safe.

### Milestone 6 — Install, update, removal, and release acceptance

| ID | Purpose and concrete change | Intended files/locations | Prerequisites/owner | Verification and acceptance | Rollback | Completion evidence |
|---|---|---|---|---|---|---|
| M6-T1 | Harden deterministic release build/version, clean exact-source staging, code-signature-sealed bundle metadata, post-sign bundle-digest verification, fixed-root lifecycle-gated install/reconcile/repair, verified launcher drain/restart, LaunchAgent readiness, and direct product doctor under CLT only. | capability build/resources/installer/tests | M5 | Clean builds from one captured commit have identical declared source-input digest, version, and checks; any post-sign bundle-byte variance is explained. Modified/untracked capability input, mismatched metadata-lock row, or source/head change before promotion refuses. Bundle metadata binds the producing Skills revision and source-input digest before signing; the signature seals metadata, executable, and resources together; installer and later doctor verify that signature and metadata, while install evidence proves the installed bundle digest equals the post-sign staged digest. No circular executable/resource hash inventory or separate receipt exists. Identical-source/contract healthy reconcile is a byte/process no-op across unrelated Skills commits, retains honest producing provenance, and does not require a live launcher. Existing launcher exits and installer takes its lock before mutation; unverified drain or symlink/special/changed install target changes nothing; controlled restart hands the lock to one verified new launcher. Repeated reconcile leaves one app/launcher; conflicting `HOME`/`XDG_*` values still target one authority root; user-only writes; RunAtLoad/no KeepAlive | Atomic backup restores prior bundle/plist and verified prior launch readiness; bootout only owned label | `VT-CAP`, `VT-PKG`, AT-32 |
| M6-T2 | Prove current-Skills update and uninstall: an active/surviving run holder blocks replacement; lifecycle exclusivity blocks new run admission; launcher-lock transfer blocks duplicate activation; successful update preserves compatible latest log; handled failures restore prior readiness; abrupt death is reconstructed without run admission; verified uninstall removes owned lifecycle state and preserves log, while contention or unverifiable ownership changes nothing. | installer/README/lifecycle tests | M6-T1 | Race run admission and duplicate activation against lifecycle/launcher acquisition and every promotion stage: exactly one side owns each gate, no run uses mixed app state, and blocked action changes no inventory/hash. Inject ordinary failures and hard process death at each bundle/plist/launch boundary: handled N→failed N+1 restores healthy N; restart after a crash keeps only fully verified N+1 or restores N; failed first install leaves or reconstructs to no app/plist/process; incomplete lifecycle refuses app runs. N→N+1 metadata/digest match; verified uninstall leaves no app/agent/process/socket and one `0600` log; interrupted/blocked uninstall reports or reconstructs residue and never authorizes a run from mixed state | Reconcile prior reviewed capability revision through a forward restore commit or verified uninstall; never reset target repos | lifecycle/launcher race and crash-cut trace, stage-by-stage first-install/update rollback, and all uninstall inventories |
| M6-T3 | Run full suites, AT-01–33, product-network/direct-transport/descendant-attribution, privacy, dependency, and banned-command audits, static verifier/lock, orchestrator status/consistency, target-Mac E2E/UAT, explicit-test-root install/update/remove rehearsal, and docs checks. | existing product/Skills/orchestrator test surfaces only | M6-T1–2 | Every ledger row green or release blocked; static/runtime audit finds no product network client beyond direct selected-origin Git transport; controlled hook/helper egress is separately attributed; downstream diff empty; no third-party runtime, GitHub API, or runner exists; no real-repository, production-installation, cpp, or host-policy mutation occurs | Drain and remove only the explicit test root; do not release/install live | Combined exact-revision verification output |
| M6-T4 | With explicit release approval, merge exact reviewed Skills source/metadata lock, verify excluded WF1 state, reconcile from durable primary, and verify live status/shortcut/log/Quit/doctor plus embedded build identity. | standard Skills/orchestrator governed delivery and user install paths | All gates; explicit operator GO | Source commit/metadata lock/registry exact; no payload; installed bundle metadata matches the producing merged commit and installed digest matches post-sign staging evidence; production selection/cancel-before-worker smoke proves launcher/UI readiness with zero target-repository Git command; clean primary | Forward-restore prior capability bytes with regenerated metadata lock, or uninstall; never rewrite history or roll back completed repo updates | merged identities, registry status, app metadata/doctor, operator sign-off |

**M6 gate:** all stable requirements and AT-01–33 are green; Skills source/reconcile is the sole
distribution path; excluded non-propagation, update, rollback, and removal are proven.

## 8. Acceptance criteria

The plan is complete only when:

1. one source-owning `global/tools/dev-main-sync/` exists with one ADR/plan; there is no
   standalone/GCB/copied source.
2. existing manifest/tool/metadata-lock formats validate, WF1 shows `excluded`, orchestrator consistency
   reports expected omission, and downstream has no Dev Main Sync byte or manifest row.
3. installed inventory is one app executable/bundle, one no-KeepAlive user LaunchAgent, private
   coordination state, and one current/latest log.
4. all `VT-*` families and AT-01–33 pass on the target Mac; automated tests mutate no real
   repository.
5. full state matrix behavior matches; command audit has zero banned Git family; product-network
   and direct-transport audits see only selected-origin Git, with repository helper/hook egress
   separately attributed under the stated boundary.
6. discovery reflects additions/removals, includes eligible umbrella, deduplicates common
   identities, avoids linked traversal, and makes zero Git invocation inside hard-excluded roots.
7. native keyboard/VoiceOver journey covers select/confirm/progress/cancel/mixed report/log/reopen/
   Close/Quit.
8. race, stale PID/PGID, spawn/cancel, takeover, lifecycle/update admission, simultaneous
   host/worker crash, inherited operation-lease, timeout, hardlinked-log, and stubborn-child
   fixtures cause no overlap, unrelated signal, orphan product process, false success, forged log
   record, or active/log-target overwrite.
9. install/reconcile/repair/update/uninstall are sudo-free, atomic, source-bound, CLT-only, and
   verified by the product-local doctor plus repository-wide static/lock checks.
10. no new shelf/schema/distribution framework, host-policy change, downstream path, backend,
    database, scheduler, plugin, telemetry, updater, third-party runtime, or paid runner exists.
11. the exact candidate Skills revision, metadata lock, registry state, installed bundle
    metadata/digest verification, and operator release approval agree.

## 9. Rollback

### Milestone/source rollback

- Before live install, forward-revert the affected Skills changes and regenerate the metadata lock; after
  source absence is proven, remove the inert excluded registry row through its owner.
- Product source changes use normal reviewed forward reverts, never reset/force-push.
- A registry-first/source-first interruption is repaired by completing or reverting the matching
  governed change. It never triggers downstream vendoring.

### Installed rollback

The installer stages a new bundle/LaunchAgent while the prior version remains recoverable.
An active run blocks replacement. Any post-promotion failure restores the prior bundle and plist,
or removes newly promoted state when none existed, restarts/verifies the prior launcher when one
existed, and returns non-zero. Later rollback uses a forward Skills change restoring reviewed prior
capability bytes with a regenerated metadata lock, followed by reconcile, or uses verified
uninstall.

Uninstall asks the verified host/worker to quit, uses the normal cancel/drain path, rechecks lock
release, unloads only `com.kleinperkins.dev-main-sync`, removes owned app/coordination state, and
preserves `latest.log`. Unverified ownership stops removal.
It leaves the app, LaunchAgent, coordination state, and log byte-for-byte unchanged, returns
non-zero, and prints the preserved paths plus: “Close Dev Main Sync and try Remove again. If a
previous Git operation does not finish, restart your Mac before trying again.” If that still does
not establish verified ownership, an agent must review the preserved state before any manual step.

Application/capability rollback never reverses a repository already fast-forwarded and never
invokes reset, clean, checkout, stash, rewrite, or push in target repositories.

### Ownership reversal

Only a successor ADR under ADR 0003's reversal conditions may choose another owner. It must
uninstall/deactivate this capability, create a successor plan under the new owner, move source once,
remove shelf/registry/metadata-lock state, prove downstream absence, then activate the replacement.
This accepted Skills plan remains frozen as historical evidence. Two active installers, source
owners, or canonical plans may not overlap.

## 10. Risks and mitigations

| Risk | Mitigation/gate |
|---|---|
| TOCTOU between inspection/update | Descriptor/device/inode binding through child admission, captured target, after-fetch revalidation, Git FF-only/no-overwrite, postflight, attention on uncertainty |
| Effective Git config retargets origin or supplies a custom transport command | Compare raw and effective approved GitHub identity at discovery and immediately before fetch; reject effective SSH/upload-pack commands rather than override them; disable submodule recursion |
| Replacement refs/grafts fake ancestry | Exclude their metadata and use no-replace-object mode for every topology/ancestry/update command |
| Hooks/filters leave residue | Never suppress; recheck; no update after fetch residue; preserve/no cleanup |
| Existing Git hook/helper opens its own network connection | NFR-PRI-01 covers product-authored clients and selected-origin transport; do not suppress or sandbox repository behavior; distinguish descendant egress in controlled network evidence and make no stronger runtime claim |
| Global source cannot embed downstream exclusions | Parse live host-policy exclusions generically before descent/Git; derive acceptance fixtures; zero-link scan; stop rather than add prohibited literals |
| Host policy is split across bounded YAML and classifier declarations | Parse only static path declarations as data before Git; preflight hook markers via filesystem; fail closed on unknown/dynamic shape; parity test; no user registry or host-framework change |
| Bootstrap warns on install failure | Mandatory direct product doctor before success/release claims; bootstrap exit alone is never proof |
| Dirty source could be mislabeled as a reviewed Skills revision | Live lifecycle commands prove all capability inputs and the metadata lock tracked and clean before staging; embed the exact revision plus source-input digest; inject modified/untracked-input refusals |
| Install/remove races a run or uses a different environment root | Derive one effective-user state root; workers hold lifecycle shared and run exclusive; lifecycle mutation requires nonblocking exclusive ownership; race and conflicting-environment fixtures |
| Stale process identity | Live lock holder + UID + birth/executable/group + generation challenge; metadata has no authority |
| Crash leaves descendant or permits overlap | Bidirectional channels, same-worker process group, Git-child-inherited operation lease, shared cancel path, TERM/KILL/wait and simultaneous crash-cut tests |
| Git tracing/logging leaks credentials/content or targets another inode | Closed Git-child environment, trace/output sentinels, pre-write redaction, URL-user-info stripping, no environment/content logging, framed escaped bounded output, descriptor-relative single-link file checks, private modes |
| Failed update leaves mixed app/plist state | Inject every post-promotion failure; restore and health-check the prior bundle/plist/launcher before returning non-zero |
| Uninstall cannot prove ownership | Fail closed with unchanged state, non-zero result, preserved-path inventory, and explicit recovery route |
| UI freeze/ambiguity | Main-actor rendering only, off-thread worker, typed events, 250 ms target, text+symbol, keyboard/VoiceOver UAT |
| No full Xcode/paid macOS runner | Core/view-model/AppKit construction automation and bundle smoke locally; explicit target-Mac UAT/release gate; no hidden dependency |
| Ad-hoc signature insufficient later | v1 stays one-Mac source-built; notarization/multi-machine reopens ADR |
| Skills repo source volume/cadence | One capability directory, one executable, no generated artifact committed, focused verifier; ADR reversal threshold monitors material cost |

## 11. Readiness and stop conditions

Implementation begins only after explicit operator approval. Release begins only after all
milestone, requirement, AT, capability, zero-link, registry, native, and lifecycle gates are green.

Stop and reopen ADR 0003 rather than silently expand scope if:

- the global tool cannot remain canonical without an external/duplicated source;
- any shared shelf, manifest, lock-format, bootstrap, or orchestrator behavior change is required;
- live host policy cannot be consumed without modifying its framework or embedding prohibited
  global literals;
- safe Git or process ownership cannot pass the closed matrices;
- downstream native consumption becomes required;
- Developer ID/notarized/multi-machine distribution becomes required; or
- implementation needs another daemon, database, updater, third-party runtime, paid runner, hosted
  service, or generic framework.
