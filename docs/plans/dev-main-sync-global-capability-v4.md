# ShadowSync — application identity, icon, and installed-app handoff plan

**Version:** v4
**Status:** ACCEPTED — 2026-09-17
**Date:** 2026-09-17
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Supersedes:** [Dev Main Sync process-free repository chooser and selected-scope execution plan v3](dev-main-sync-global-capability-v3.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Implementation baseline:** clean revision `2da2d7076e5c40a482d9da0d076bb1885212a479`
on branch `feat/dev-main-sync-v3-selection-first`
**Frozen predecessor:** v3 SHA-256
`52f51c621a87bf986f36a87398e2f660dc06c30bd5380c6a6bf8df01875f9dbd`
**Review state:** the operator authorized the ShadowSync successor, its integration into the existing
v3 implementation branch, and implementation after this accepted plan is committed. These accepted
bytes are frozen on creation; implementation proceeds without another plan-approval checkpoint.

> **For agentic implementers:** execute this plan task-by-task in dependency order. Each task is a
> zero-context work unit with exact files, symbols, invariants, tests, and completion evidence.
> Never edit this accepted plan to record progress. Keep implementation notes and evidence outside
> the plan.

**Goal:** Ship the complete v3 product as **ShadowSync**, with a real original macOS icon and a
single safe forward transition from the installed `Dev Main Sync.app`, while preserving every v3
safety, selection, performance, lifecycle, wire, state, and delivery guarantee.

**Architecture:** Treat the rename as an application-identity and lifecycle migration, not a new
product or state system. Rename operator-facing and Swift implementation identity; retain the
existing bundle ID, launchd label, state location, capability path, schemas, metadata keys, and Git
namespace. Extend the existing lifecycle transaction to inspect, drain, stage, promote, prove,
rollback, repair, and uninstall both app-name generations under one launchd and state authority.
Build a committed deterministic icon asset ahead of production builds; production copies and
verifies the stable `.icns` before signing.

**Tech stack:** Swift 6.2, AppKit, SwiftPM without an Xcode project, Darwin/POSIX descriptor APIs,
existing source-built lifecycle and release attestation, macOS `sips`/`iconutil` for controlled
asset generation, existing no-dependency self-test harnesses, and isolated owner-private
`/private/tmp` fixtures.

---

## 0. Authority, implementation body, and dependency order

This v4 plan is the sole active implementation authority. It supersedes v3 without weakening or
replacing its product architecture. Every requirement, acceptance row, test, prohibition, and
delivery gate in v3 remains release-blocking unless this plan explicitly strengthens or renames its
application-identity spelling. In particular:

- all `V3-CAT`, `V3-PREF`, `V3-BIND`, `V3-AUTH`, `V3-SCOPE`, `V3-LIFE`, `V3-PERF`,
  `V3-COMP`, and `V3-GOV` requirements remain in force;
- `DM3-T01` through `DM3-T16` and `V3-AT-01` through `V3-AT-22` remain required;
- all v1/v2 retained safety suites remain required and their assertions may not be weakened;
- v3's one selected scope, no pre-Continue process/network/authority work, linear selected-only
  execution, canonical authority, one lifecycle router, and proven drain remain unchanged; and
- the accepted v2/v3 bytes are historical evidence and may not be edited.

There is one integrated implementation body and one eventual Draft PR from the existing v3
implementation branch. Live GitHub inspection at plan time found no PR for the branch. The rename,
icon, migration, v3 implementation, release checks, review, merge, and exact-main installation land
together. No intermediate commit is installable or independently releasable.

```text
Task 1 freeze identity matrix and add red compatibility tests
  → Task 2 rename application and Swift implementation identity
  → Task 3 add and attest the deterministic icon
  → Task 4 implement old-app → ShadowSync lifecycle handoff
  → Task 5 close all acceptance and governed delivery
```

No feature branch is installed. No second PR, temporary launchd label, second state tree, feature
flag, dual-running mode, broad fallback, or old-name steady state is allowed.

## 1. Verified current state and exact defect

The implementation agent must re-run the named searches at Task 1. At the v4 baseline:

| Surface | Verified baseline | v4 consequence |
|---|---|---|
| SwiftPM identity | Package/product `DevMainSync`; targets/modules/directories `DevMainSyncCatalog`, `DevMainSyncCore`, `DevMainSyncApp`, `DevMainSyncSelfTest`, `DevMainSyncCompileTests` | Rename package, product, implementation targets/modules/directories, imports, object paths, and test target names to `ShadowSync*` |
| Testing compile identity | `DEV_MAIN_SYNC_TESTING` gates test-only source | Rename to `SHADOW_SYNC_TESTING`; production audits must reject the old compile flag |
| Bundle identity | `Dev Main Sync.app`, executable `Contents/MacOS/DevMainSync`, display/name `Dev Main Sync` | Install/build only `ShadowSync.app` with executable/process `ShadowSync` and display/name `ShadowSync` |
| Bundle icon | `Info.plist` has no `CFBundleIconFile`; bundle has no icon resource | Add `ShadowSync.icns`, plist declaration, build copy, inventory/hash/signature proof |
| Stable bundle trust | `CFBundleIdentifier` and ad-hoc codesign ID are `com.kleinperkins.dev-main-sync` | Preserve exactly; changing them would create an unrelated app identity and break installed trust continuity |
| Stable launchd identity | Label/plist filename `com.kleinperkins.dev-main-sync`; one `ProgramArguments.0` path | Preserve label and plist filename; atomically change only the verified program path to ShadowSync |
| Stable state | `~/.local/state/dev-main-sync` owns preferences, authorities, logs, host registration/socket, retention/recovery evidence, and locks | Preserve the directory and every existing schema; there is no state migration |
| Lifecycle | `InstallationPaths` and transaction slots know only `Dev Main Sync.app` and `DevMainSync` | Model current and predecessor app identities explicitly and transact both |
| Release identity | Custom `DevMainSync*` plist keys plus `dev-main-sync-release/v1` feed release admission | Preserve keys/schema/version values exactly; add icon bytes through existing bundle inventory/source attestation |
| Capability identity | path/id/slug `global/tools/dev-main-sync` / `dev-main-sync`; `tool.yml.name` is `Dev Main Sync`; `meta.yml` has no display-name field | Preserve path/id/slug/registry identity; set supported display metadata and operator copy to ShadowSync; do not invent an unsupported `meta.yml` field |
| Naming breadth | Shell `rg` finds old names across app/core/catalog sources, tests, fixtures, scripts, resources, package metadata, and README | Classify every match as rename, stable compatibility, predecessor fixture, or prohibited stale name |
| Current evidence | Exact-head Body 2, v3 preflight, M5, and owner verifier pass; M1 timing and M6 delayed-host readiness remain host-sensitive | Baseline evidence is informative only; rerun all dependency-mapped gates at final v4 head |

The generic Finder/Launchpad icon is explained by the missing plist icon key and missing bundled
icon resource. The duplicate-app risk is explained by the existing lifecycle's single canonical
`paths.app`: simply changing that literal would leave the old app outside transaction, rollback,
repair, doctor, and uninstall ownership.

## 2. Naming and compatibility contract

### 2.1 Exact matrix

| Identity class | v4 value | Action and rationale |
|---|---|---|
| Operator-visible product name | `ShadowSync` | Rename menus, windows, alerts, status guidance, reports intended for people, README, `tool.yml.name`, installer/doctor output |
| App bundle | `~/Applications/ShadowSync.app` | New sole forward canonical bundle |
| Bundle executable/process | `ShadowSync` / `Contents/MacOS/ShadowSync` | New sole forward executable and process identity |
| Swift package/product | `ShadowSync` | Rename |
| Swift targets/modules/directories | `ShadowSyncCatalog`, `ShadowSyncCore`, `ShadowSyncApp`, `ShadowSyncSelfTest`, `ShadowSyncCompileTests`; matching `Sources/*` and `Tests/*` | Rename implementation identity, imports, build products, object paths, fixture references |
| Swift implementation symbols | `ShadowSync*` where a symbol carries product identity | Rename non-wire types such as app delegate, admission probes, and test drivers; neutral domain symbols need no prefix |
| Test-only compile flag | `SHADOW_SYNC_TESTING` | Rename all guards and compiler invocations; old flag absent from production/test source after migration |
| Bundle display/name | `ShadowSync` | Set `CFBundleDisplayName` and `CFBundleName` |
| Bundle icon | `ShadowSync.icns` | Set `CFBundleIconFile`; include exact resource |
| Bundle/codesign identity | `com.kleinperkins.dev-main-sync` | Retain compatibility-critical identifier |
| Launchd label/plist | `com.kleinperkins.dev-main-sync` / `com.kleinperkins.dev-main-sync.plist` | Retain the one installed job and registration identity |
| State directory | `~/.local/state/dev-main-sync` | Retain all user state; no copy, rename, fork, or migration |
| Wire/schema/version strings | every existing `dev-main-sync-*` and `dev-main-sync-*/vN` value | Retain byte-for-byte unless a test-only human label is outside serialized compatibility |
| Custom plist metadata keys | every existing `DevMainSync*` key | Retain; these are release-wire keys, not visible branding |
| Existing release version/build | current `0.1.0` / `1` contract | Preserve unless the repository's release policy independently requires a bump; source revision/input digest distinguishes the new build |
| Git config namespace/markers | existing `devMainSync.*` values | Retain closed command/test/config compatibility |
| Capability/registry identity | `dev-main-sync`, `global/tools/dev-main-sync`, existing lock entry | Retain; no ecosystem re-registration or path migration |
| Shell fixture/root prefixes | existing private `dev-main-sync-*` ownership prefixes | Retain where cleanup and capability identity depend on them; they are not app branding |
| Historical predecessor fixtures | exact `Dev Main Sync.app` / `DevMainSync` values | Retain only in explicitly named migration/rollback fixtures and compatibility constants |
| Existing persisted historical prose | original bytes in retained logs/reports/evidence | Never rewrite state history merely to remove old branding; current UI labels it as historical predecessor evidence |
| Documentation history | v1/v2/v3 plan and ADR bytes | Retain immutable; v4 and current README explain the new name |

`meta.yml` currently has no display-name field in the repository's `kp-capability/v1` pattern.
Therefore `tool.yml.name` is the supported catalog display owner. Preserve `meta.yml`'s stable
`id: dev-main-sync`; add no ungoverned key merely to simulate a rename. If Task 1 proves the live
schema has gained a supported display field before implementation begins, use `ShadowSync` there
and update its lock digest through the normal registry path in the same PR.

### 2.2 Closed rename rule

Create a deterministic naming manifest from:

```bash
rg -n --hidden --glob '!docs/plans/**' --glob '!.git/**' \
  'Dev Main Sync|DevMainSync|DEV_MAIN_SYNC|ShadowSync|SHADOW_SYNC' \
  global/tools/dev-main-sync
```

Every old-name match must be recorded in exactly one class from §2.1. Production operator copy,
app paths, executable names, Swift implementation identity, and test compile identity must have
zero old-name matches. Stable identifiers and predecessor tests use a narrow explicit allowlist
that names the file, literal, and compatibility reason. A broad regex exclusion or directory-wide
allowlist is forbidden.

Do not rename domain concepts merely because their source directory changes. Do not alter coding
keys, schema strings, persisted filenames, log/report wire values, Git command grammar, launchd
label, state paths, capability paths, or registry identity.

## 3. Protected v3 invariants and explicit exclusions

### 3.1 Required preservation

1. The chooser is usable within v3's one-second physical gate and performs zero process, network,
   or authority admission before Continue.
2. Selection preferences remain separate from canonical authority and stay in the existing state
   directory.
3. Continue rebinds selected locators through current policy/root descriptors; heavy work remains
   selected-only and linear.
4. Disabled repositories never enter review, confirmation, worker, or operation payloads.
5. Existing wire encodings and fixture digests remain byte-compatible despite Swift type/module
   renames.
6. Existing Git/AWA closed grammars, hooks, cancellation, process identity, child reaping, authority
   staging, lifecycle locks, retention, redaction, and no-real-mutation tests remain intact.
7. One `AppLifecycleRouter`, one launchd job, one host socket/registration, and one drain barrier
   own the application lifecycle.
8. Ad-hoc signing, source revision/input attestation, metadata lock identity, canonical bundle
   inventory, path hardening, and reproducible-build normalization remain mandatory.
9. Hotkey/menu activation and existing-window foreground behavior continue through the same
   verified host and socket.

### 3.2 Non-goals

- no bundle-ID or codesign-ID migration;
- no launchd-label or plist-filename migration;
- no state-directory, schema, wire, custom metadata-key, Git namespace, capability-ID, source-path,
  or registry identity migration;
- no second launchd job, state tree, host socket, app updater, migration daemon, or compatibility
  background service;
- no Xcode project, asset catalog, `Assets.car`, notarization, new signing authority, third-party
  icon generator, package dependency, telemetry, or network client;
- no generic circular sync-arrow icon, text/letters inside the icon, third-party mark, or corporate
  brand imitation;
- no cache reset as release evidence and no destructive Finder/Launchpad cache manipulation;
- no v1/v2/v3 plan or ADR edit;
- no performance threshold, fixture size, lifecycle timeout, safety assertion, cancellation/drain,
  fail-closed, or coverage weakening;
- no paid or self-hosted GitHub Actions runner;
- no feature-branch install, real target-repository mutation, push, PR creation, merge, or
  auto-merge during plan authoring.

## 4. Installed-app handoff architecture

### 4.1 Two recognized bundle generations, one forward owner

Extend `InstallationPaths` (or a narrow adjacent value type) with:

```text
currentApp       = ~/Applications/ShadowSync.app
currentExecutable = currentApp/Contents/MacOS/ShadowSync
predecessorApp   = ~/Applications/Dev Main Sync.app
predecessorExecutable = predecessorApp/Contents/MacOS/DevMainSync
launchAgent      = ~/Library/LaunchAgents/com.kleinperkins.dev-main-sync.plist
state            = ~/.local/state/dev-main-sync
```

Forward build/install/update writes only `currentApp` and `currentExecutable`. The predecessor
values exist solely for inspection, drain, transition, rollback, repair, doctor, uninstall, and
tests. All launchd and host-control calls retain `InstallationPaths.label`.

Bundle verification must accept a predecessor only when all existing ownership, mode, no-link,
xattr, signature, bundle-ID, release metadata, inventory, and known-release checks pass. A
directory named like the predecessor is never authority by name alone.

The transaction-slot vocabulary is also exact:

```text
current incoming/previous/incomplete/quarantine:
  .ShadowSync.app.incoming
  .ShadowSync.app.previous
  .ShadowSync.app.incomplete.<nonce>
  .ShadowSync.app.quarantine.<generation>
predecessor rollback/recovery:
  .Dev Main Sync.app.incoming
  .Dev Main Sync.app.previous
  .Dev Main Sync.app.incomplete.<nonce>
  .Dev Main Sync.app.quarantine.<generation>
shared plist transaction:
  .com.kleinperkins.dev-main-sync.plist.incoming
  .com.kleinperkins.dev-main-sync.plist.previous
  .com.kleinperkins.dev-main-sync.plist.incomplete.<nonce>
  .com.kleinperkins.dev-main-sync.plist.quarantine.<generation>
```

Before starting a cross-generation transaction, recover or refuse every pre-existing predecessor,
current, plist, host-owner, and socket slot through the existing exact ownership/release rules.
Only one transaction may use the shared plist slots under lifecycle authority.

### 4.2 Migration state machine

| State | Admission | Required action | Result |
|---|---|---|---|
| Neither app; no plist/job | Fresh install | Stage and verify ShadowSync, render existing-label plist to new executable, promote, bootstrap, prove ready | ShadowSync steady state |
| Verified predecessor only; plist/job points to predecessor | Forward migration | Execute §4.3 transaction | ShadowSync steady state or fully restored predecessor |
| Verified ShadowSync only; plist/job points to ShadowSync | Update/repair | Existing lifecycle transaction under new paths | ShadowSync steady state |
| Both canonical apps exist | Fail closed by default | `repair` classifies exact release/path/job/host evidence; preserve both until one known-good owner is proven | Reconcile to ShadowSync or report precise refusal |
| Predecessor app with plist absent/job absent | Repairable only with verified bundle and no conflicting state | Stage ShadowSync; preserve predecessor as rollback source until readiness | ShadowSync or predecessor restored |
| Plist/job points to predecessor but predecessor is absent/corrupt | Refuse ordinary install/update | Repair may use only verified backups/current bundle and exact host evidence | No blind deletion or invented ownership |
| Plist/job points to ShadowSync while predecessor remains | Interrupted post-ready cleanup | Prove current bundle, loaded path, ready host, release, signature, and state registration; then quarantine/remove predecessor | ShadowSync steady state |
| Incoming/previous/quarantine slots from either generation | Recovery | Classify slots by generation and paired plist/release; recover through §4.4 | One known-good generation or recoverable refusal |
| Plist/job points elsewhere, second label exists, or process path mismatches both | Refuse | Read-only doctor explanation | No mutation |

The lifecycle state model must retain both canonical-path existence and identity independently; it
must not collapse “both exist” into a preferred path before verification.

### 4.3 Forward transition order

For a verified running predecessor:

1. Build the source release outside installed paths and verify ShadowSync bundle identity,
   executable, icon, release metadata, inventory, source-input digest, architecture, and signature.
2. Acquire existing run, lifecycle, and launcher authorities; pin the same Applications, LaunchAgents,
   and state parents.
3. Inspect both canonical app paths, all old/new transaction slots, the existing-label plist,
   launchd program/PID, host registration, socket, release, and process identity.
4. Require the job and ready process to agree on the verified predecessor executable and release.
5. Ask the predecessor host to exit through the existing authenticated state/socket protocol; close
   future work admission and wait for the existing lifecycle/child/authority drain proof.
6. Boot out the existing label using the exact predecessor program and verify no predecessor
   process remains. Never signal an unverified PID or process group.
7. Stage the verified ShadowSync bundle under an owner-only same-parent incoming/incomplete name;
   render the same plist label with `ProgramArguments.0 = currentExecutable`; fsync and verify both.
8. Preserve the predecessor bundle and plist as paired rollback artifacts before promotion. A
   canonical-path rename may remove the old visible path only after the verified bytes remain in
   an owned rollback slot.
9. Atomically promote ShadowSync and its plist under pinned parents; verify their post-rename
   identities and bytes.
10. Bootstrap the one existing label, prove loaded program equals `currentExecutable`, and prove
    the ready host identity/release/signature/state registration/socket. Verify activation in the
    isolated harness; installation must not force an operator window merely to prove readiness.
11. Only after step 10 may old canonical/backup bytes be quarantined and removed through existing
    owned-tree rules. Clean new-generation backups/incoming slots and release lifecycle authority.

No step starts the predecessor and ShadowSync concurrently. A launchd label loaded at either path
must be booted out and proven absent before the other path is bootstrapped.

### 4.4 Failure, interruption, and rollback matrix

| Failure boundary | Required safe outcome |
|---|---|
| New build/icon/source attestation fails | Installed predecessor untouched and running |
| Authority, parent pin, old bundle/plist/host verification fails | No mutation; exact refusal |
| Cooperative old-host drain fails or times out | Old app/plist/state retained; no new bootstrap |
| Failure after old drain but before backup | Re-bootstrap verified predecessor if it was previously running; otherwise preserve stopped state truthfully |
| Failure after paired backup but before new promotion | Restore predecessor canonical app/plist atomically and restore prior running/stopped disposition |
| Failure after new app promotion but before plist promotion | Remove only verified unstarted new app, restore predecessor pair |
| Failure after new plist promotion but before bootstrap | Boot out any partial registration, restore predecessor pair and launchd path |
| New bootstrap or readiness proof fails | Drain/bootout only verified new host, restore predecessor app/plist, bootstrap old when previously running, prove old readiness |
| New ready proof passes; old cleanup fails | Keep ShadowSync authoritative and report owned cleanup residue; repair completes cleanup without relaunching old |
| Crash at any rename/fault cut | Next install/update/repair/doctor classifies exact old/new canonical and slot identities before mutation |
| Rollback itself cannot prove one owner | Preserve every recoverable bundle/plist/state artifact and fail closed; never delete the last known-good bundle |

Rollback restores launchd ownership and `ProgramArguments.0` together with the matching bundle.
It preserves the single state directory and all preferences, authorities, logs, retention evidence,
locks, host ownership records, and recovery bytes. A forward rollback after v4 ships must use
v4-aware lifecycle code; installing a byte-old v3 bundle that cannot classify ShadowSync state is
forbidden.

Preservation does not mean impossible byte equality for live coordination records. Preference,
authority, log, retention, and durable recovery content must remain byte-identical unless the
invoked lifecycle verb already has an explicit retained-state transition. `host-owner.json` must
change from the verified predecessor process/path/release to the verified ShadowSync
process/path/release, `host.sock` is safely replaced by the new host, and lock files may change
identity while retaining their fixed names, ownership, modes, and authority semantics. Tests
classify these expected coordination changes explicitly and reject every other state delta.

### 4.5 Lifecycle verb behavior

- **install/update:** recognize absent, predecessor, current, and exact transitional states; converge
  only to ShadowSync.
- **repair:** recover paired old/new incoming/previous/quarantine cuts using exact bundle/plist/
  release/host evidence; never pick by mtime or name alone.
- **doctor:** report canonical old/new bundle presence, signatures/releases, plist program path,
  loaded process path/PID disposition, ready registration/socket, state preservation, and residue
  class in plain language.
- **rollback:** restore one paired known-good generation and matching launchd path; after v4 release,
  supported forward rollback remains dual-generation-aware.
- **uninstall:** drain whichever verified generation owns the existing label, then remove both
  verified bundle names and both generations' owned transaction residue under existing retention
  semantics. Unknown/corrupt paths are refused, not recursively deleted.

Uninstall retains the existing state/retention contract. It does not create a second “ShadowSync”
state archive or silently discard old-name evidence.

## 5. Icon asset and bundle contract

### 5.1 Original design

Create one original, text-free ShadowSync icon:

- a dark offset shadow/crescent paired with two aligned luminous layers or lanes;
- visual meaning: quiet background synchronization and aligned state;
- indigo/slate base with cyan-to-violet accent;
- high contrast against light and dark macOS backgrounds;
- a simple recognizable silhouette at 16×16;
- at least 15% mask-safe margin on every edge;
- no circular synchronization arrows, letters, words, third-party marks, copied product geometry,
  or Affirm branding.

Review the 1024, 128, 32, and 16 pixel renders before acceptance. The icon must remain legible in
Finder list view and menu/application surfaces without relying on text.

### 5.2 Deterministic source and packaging

Add:

```text
Resources/ShadowSyncIcon-1024.png
Resources/ShadowSync.icns
scripts/generate-icon.sh
```

The committed 1024×1024 PNG is the master. `generate-icon.sh`:

1. validates a regular, single-link, owner-readable 1024×1024 RGBA/RGB PNG;
2. creates a fresh owner-private iconset in `/private/tmp`;
3. uses only fixed absolute macOS tool paths and explicit sizes for
   `icon_16x16.png`, `icon_16x16@2x.png`, `icon_32x32.png`,
   `icon_32x32@2x.png`, `icon_128x128.png`, `icon_128x128@2x.png`,
   `icon_256x256.png`, `icon_256x256@2x.png`, `icon_512x512.png`, and
   `icon_512x512@2x.png`;
4. runs `/usr/bin/iconutil -c icns`;
5. generates twice in independent roots and requires byte-identical outputs;
6. verifies all dimensions, nonempty alpha/silhouette bounds, 15% safe margin, file modes, and
   committed SHA-256 values; and
7. replaces the committed `.icns` only through an explicit asset-generation invocation, never as a
   production-build side effect.

If `sips`/`iconutil` on the supported macOS version cannot reproduce identical bytes, stop and
replace only the generation implementation with a deterministic in-repository standard-library
encoder; do not whitelist variable icon bytes or add a dependency/Xcode project.

### 5.3 Production consumption and proof

`build-app.sh` copies the already committed `Resources/ShadowSync.icns` to
`Contents/Resources/ShadowSync.icns` before signing. It does not regenerate or rewrite the icon.
Set `CFBundleIconFile` to `ShadowSync.icns`. Before signing, require:

- plist key equals the exact resource name;
- resource is a regular, single-link `0644` file;
- source and copied SHA-256 match the pinned committed asset;
- `iconutil` can read/extract the expected size representations;
- bundle inventory contains the icon exactly once; and
- no old icon/resource name exists.

After signing, existing `BundleArtifactIdentity` inventory and canonical digest include the icon
bytes automatically; source-input attestation includes the master, `.icns`, and generation script.
Verify strict codesign, bundle ID, executable, icon key/resource, and repeated-build normalization.

Finder/Launchpad icon caches are nondeterministic UI projections. Release truth is the signed new
bundle path, plist declaration, readable icon, LaunchServices-normal registration, and physical
appearance after ordinary launch/login behavior. Document a cache refresh only if physical testing
demonstrates a stale projection; never delete caches or treat cache manipulation as proof.

## 6. Exact implementation boundary

### 6.1 Required renames

```text
Sources/DevMainSyncCatalog        → Sources/ShadowSyncCatalog
Sources/DevMainSyncCore           → Sources/ShadowSyncCore
Sources/DevMainSyncApp            → Sources/ShadowSyncApp
Tests/DevMainSyncSelfTests        → Tests/ShadowSyncSelfTests
Tests/DevMainSyncCompileTests     → Tests/ShadowSyncCompileTests
Package/product/target/module names and imports → matching ShadowSync names
DEV_MAIN_SYNC_TESTING             → SHADOW_SYNC_TESTING
```

Use `git mv` so history remains reviewable. Rename product-prefixed source filenames and non-wire
symbols when they carry application implementation identity. Leave neutral domain filenames and
symbols unchanged inside their renamed target directories.

### 6.2 New files

- `global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png`
- `global/tools/dev-main-sync/Resources/ShadowSync.icns`
- `global/tools/dev-main-sync/scripts/generate-icon.sh`
- `global/tools/dev-main-sync/scripts/v4-preflight-acceptance.sh`
- focused migration/icon fixture files only when required by existing test harness conventions

### 6.3 Expected modified files

- `global/tools/dev-main-sync/Package.swift`
- `global/tools/dev-main-sync/Resources/Info.plist`
- all renamed Swift target/test sources containing product identity, imports, or compile guards
- `global/tools/dev-main-sync/Sources/ShadowSyncCore/InstallationLifecycle.swift`
- `global/tools/dev-main-sync/Sources/ShadowSyncCore/ReleaseIdentity.swift`
- `global/tools/dev-main-sync/Sources/ShadowSyncApp/LifecycleMain.swift`
- `global/tools/dev-main-sync/Sources/ShadowSyncApp/main.swift`
- `global/tools/dev-main-sync/Sources/ShadowSyncApp/M6Harness.swift`
- `global/tools/dev-main-sync/scripts/build-app.sh`
- `global/tools/dev-main-sync/scripts/source-doctor.sh`
- all existing `verify-*`, `m1-*`, `m6-*`, `v2-body*`, and `v3-preflight-*` scripts that resolve
  product, target, object, bundle, executable, compile-flag, or migration paths
- `global/tools/dev-main-sync/install.sh`
- `global/tools/dev-main-sync/tool.yml`
- `global/tools/dev-main-sync/README.md`
- `.github/scripts/verify-skills.sh` only if its exact product/target audit requires the new names

Stable path/ID/schema/label/state literals remain only under the allowlist in §2. Historical test
fixtures may add predecessor literals but production UI must not.

## 7. Requirements and deterministic test strategy

### 7.1 Closed v4 requirements

| IDs | Requirement |
|---|---|
| `V4-NAME-01–08` | ShadowSync UI/bundle/executable/process/package/target/module/test identity; supported metadata/README branding; exhaustive classified old-name audit; stable identifiers preserved |
| `V4-MIG-01–12` | One-label old→new transition; exact dual-path inspection; cooperative drain; paired staging/promotion; no duplicate process; readiness before cleanup; complete fault-cut rollback/recovery |
| `V4-ICON-01–08` | Original design; committed 1024 master and `.icns`; deterministic generation; plist/resource/build/inventory/source-attestation/signature/reproducibility proof |
| `V4-COMP-01–08` | Bundle ID, label/plist, state, schemas, custom keys, Git namespace, capability path/id, registry identity, wire bytes, preferences/authority/log/retention preserved |
| `V4-LIFE-01–08` | install/update/repair/doctor/rollback/uninstall recognize both generations; forward writes only ShadowSync; one router/socket/job/state; hotkey/foreground/drain preserved |
| `V4-TEST-01–08` | Migration, duplicate prevention, every interruption boundary, state preservation, icon sizes/hash, zero stale UI naming, no old steady process, all v1/v2/v3 gates |
| `V4-GOV-01–06` | One integrated Draft PR; no feature install; final valid-host M1/M6 evidence; clean reviews; reviewer-App merge; exact-main install; no paid infrastructure |

All v3 requirement families remain required in addition to this table.

### 7.2 v4 acceptance tests

Add `--v4-preflight-only` plus focused `--dm4-t01-only` through `--dm4-t12-only` selectors to the
existing renamed self-test/harness rather than a parallel framework:

| Test ID | Required proof |
|---|---|
| `DM4-T01 naming-classification` | Every old-name match is a stable identifier or explicit predecessor fixture; zero stale operator/UI/app/Swift implementation identity |
| `DM4-T02 package-and-production-identity` | Package/products/targets/modules/imports/directories/compile flag and production symbols use ShadowSync; old test flag cannot expose seams |
| `DM4-T03 bundle-and-icon-contract` | ShadowSync bundle/executable/display/icon key/resource, all icon sizes/margins/hash, strict signature, bundle inventory, no generic/missing icon |
| `DM4-T04 deterministic-icon-generation` | Two fresh icon generations are byte-identical and equal committed `.icns`; invalid master/tool output refuses |
| `DM4-T05 fresh-and-current-install` | Fresh install and ShadowSync→ShadowSync update/repair use one existing label/state and prove ready |
| `DM4-T06 predecessor-forward-migration` | Verified installed Dev Main Sync running/stopped states migrate to ShadowSync; state/preferences/authorities/logs/retention bytes preserved |
| `DM4-T07 duplicate-prevention` | Old and new processes never overlap; both canonical apps and mismatched label/process states fail closed or repair through exact evidence |
| `DM4-T08 migration-fault-cuts` | Every §4.4 cut restores predecessor or preserves ready ShadowSync plus recoverable residue; never deletes last known-good bundle |
| `DM4-T09 repair-doctor-rollback-uninstall` | Every old/new/transitional state; paired path ownership; both verified bundle names removed on uninstall under retained-state semantics |
| `DM4-T10 host-activation-and-drain` | Existing socket, hotkey/menu foreground, lifecycle exit, child/authority drain, and exactly-once host ownership survive migration |
| `DM4-T11 release-attestation-reproducibility` | Icon and renamed executable are in source/bundle digests; independent production builds differ only by already-accepted UUID/signature normalization |
| `DM4-T12 inherited-v3-closure` | `DM3-T01–T16`, v1/v2 retained suites, M1/M5/M6, owner verifier, production audits, and physical selected-scope checks all pass at one exact v4 head |

### 7.3 Required fixtures and negative cases

Use only isolated owner-private roots and synthetic launch controllers/hosts. Cover:

- installed predecessor absent/running/stopped/stale; valid and corrupt bundle/plist pairings;
- current absent/running/stopped; old+new canonical paths; label points old/new/other;
- old/new incoming, previous, incomplete, and quarantine permutations at every rename boundary;
- host registration and socket bound to old/new/mismatched executable and release;
- failure before/after old drain, each app/plist backup/promotion, bootstrap, ready proof, and cleanup;
- malformed/unsafe/symlink/hardlink/foreign-owner paths with zero destructive action;
- classified state snapshots before/after migration, rollback, repair, and uninstall: durable
  content byte equality plus only the expected host-owner/socket/lock transitions from §4.4;
- icon missing, renamed, changed, malformed, wrong mode/link count, wrong size, and mismatched hash;
- cold fresh build pairs in different equal- and unequal-length roots;
- zero launch of a real repository mutation and zero install into the operator's actual home.

No test reduces repository counts or timing assertions. Tests may preserve old names only inside
the explicit predecessor fixture namespace.

## 8. Work items — one integrated implementation body

### Task 1: Freeze the identity matrix and add red tests

**Files:**

- Modify the current self-test entrypoint and M6 harness only as needed for `DM4-T01–T12`; Task 2
  then renames them
- Add focused predecessor/icon fixtures under existing test conventions
- Do not modify production behavior yet

**Interfaces:**

- Consumes the exact v4 baseline's current bundle, release, state, package, and naming values.
- Produces pinned compatibility digests, one classified naming manifest, and red test selectors.
- Starts no installed lifecycle and mutates no real application or repository.

**Inspect first:**

- `Package.swift`, `Resources/Info.plist`, `tool.yml`, `meta.yml`, README
- `InstallationPaths`, `InstallationLifecycle`, `LifecycleMain`, `ReleaseIdentity`,
  `BundleArtifactIdentity`
- `build-app.sh`, `install.sh`, `source-doctor.sh`, every verification script
- all shell-`rg` old-name matches and every `DEV_MAIN_SYNC_TESTING` guard

- [ ] Record current file/match inventory and classify each old-name occurrence.
- [ ] Pin canonical v3 wire encodings, state-tree bytes, release metadata keys, label, bundle ID,
  capability ID/path, and registry digest.
- [ ] Add red `DM4-T01–T12` tests, including source/package audits and all lifecycle cuts.
- [ ] Record exact current M1/M6 host-sensitive blockers without changing their oracles.

**Completion evidence:** baseline revision/hashes; classified manifest; named red failures; frozen
compatibility digests. Do not commit a red-only state independently.

### Task 2: Rename application and Swift implementation identity

**Files:** execute §6.1 and update all §6.3 naming consumers.

**Interfaces:**

- Consumes the Task 1 compatibility matrix and red tests.
- Produces the ShadowSync package/modules/executable/UI while retaining every stable identifier.
- Changes no lifecycle transition semantics; Task 4 owns old/new installed-state behavior.

- [ ] `git mv` target/test directories and product-prefixed implementation filenames.
- [ ] Rename package/product/targets/modules/imports/object paths and compile flag.
- [ ] Rename non-wire implementation symbols and every operator-facing string.
- [ ] Set bundle/display/executable paths to ShadowSync while preserving §2 stable values.
- [ ] Update `tool.yml.name` and README; preserve `meta.yml.id` and capability path.
- [ ] Make `DM4-T01/T02` green and rerun wire digest compatibility.

**Completion evidence:** exhaustive match classification; production old-name count zero outside
stable literal allowlist; successful testing/production package builds.

### Task 3: Create, package, and attest the icon

**Files:** add §5.2 files; modify `Info.plist`, `build-app.sh`, release/bundle tests, README.

**Interfaces:**

- Consumes one committed 1024×1024 master and fixed macOS asset tools.
- Produces one deterministic committed `.icns` copied by production builds before signing.
- Extends existing source/bundle attestation without adding a runtime generator or dependency.

- [ ] Create and visually inspect the original master at required sizes/backgrounds.
- [ ] Implement deterministic generation and independent double-generation assertion.
- [ ] Commit stable `.icns`; set `CFBundleIconFile`; copy before signing.
- [ ] Bind icon bytes into source and bundle inventory/digests and verify extraction/sizes/hash.
- [ ] Make `DM4-T03/T04/T11` icon portions green.

**Completion evidence:** master and `.icns` SHA-256; size/margin report; double-generation equality;
signed bundle inventory and ordinary physical icon screenshots at 16/32/128/application scale.

### Task 4: Implement the dual-generation lifecycle transition

**Files:** lifecycle, host entry, installer/doctor, M6 harness, and lifecycle scripts named in §6.3.

**Interfaces:**

- Consumes one verified source ShadowSync bundle plus exact old/new installed-state evidence.
- Produces one ready ShadowSync owner or a restored/recoverable verified predecessor state.
- Uses the existing launchd label, state authority, host protocol, lifecycle locks, and drain proof.

- [ ] Add explicit current/predecessor paths and exact dual-generation inspection.
- [ ] Implement §4.3 drain/stage/paired-backup/promote/bootstrap/ready/cleanup order.
- [ ] Implement every §4.4 rollback and interruption cut.
- [ ] Extend install/update/repair/doctor/rollback/uninstall per §4.5.
- [ ] Preserve one label/socket/state/router and old/new process mutual exclusion.
- [ ] Prove state/preferences/authority/log/retention bytes survive.
- [ ] Make `DM4-T05–T10` green.

**Completion evidence:** transition traces; fault-cut matrix; no-overlap process census; paired
rollback identities; state pre/post digests; doctor and uninstall receipts.

### Task 5: Full acceptance, review, merge, and exact-main install

**Files:** finalize verification scripts and README; root owner verifier only where required.

**Interfaces:**

- Consumes the complete integrated exact branch head and all retained v3/v2 test surfaces.
- Produces one self-cleaning v4 receipt, one Draft PR, and—after explicit GO/merge—one exact-main
  installed ShadowSync handoff.
- Performs no feature-branch install, direct merge, auto-merge mutation, or real repository action.

- [ ] Add `scripts/v4-preflight-acceptance.sh` as one self-cleaning v4 entrypoint that composes the
  retained v3 gate and adds v4 naming/icon/migration proof without duplicating harness ownership.
- [ ] Run `DM4-T01–T12`, all `DM3-T01–T16`, retained v1/v2 suites, M1, M5, M6, owner verifier,
  source/package/symbol/network/broad-route/secrets audits, and doc-warden.
- [ ] Under a valid host, require M1's unchanged `<5s` 100-repository gate and M6's unchanged
  delayed-host readiness gate at the final integrated exact commit.
- [ ] Run 20 cold first-screen trials and selected 1/3 among 51 poison repositories without changing
  v3 thresholds or fixtures.
- [ ] Prove two clean production builds satisfy existing reproducibility normalization and include
  identical icon bytes.
- [ ] Keep the existing PR Draft. Run Bugbot until clean and rerun after material fixes.
- [ ] Run security review over descriptor/process/lifecycle/state/signature boundaries and clear
  every material finding.
- [ ] Present exact head, diff, naming allowlist, asset hashes, migration ledger, tests, physical
  metrics, and residual uncertainty at the explicit operator ready gate.
- [ ] Only after operator GO mark ready; leave approval/auto-merge to the reviewer App.
- [ ] After merge, update the durable primary to exact clean `origin/main`, rerun all gates, install
  only exact main, migrate the installed predecessor, run doctor, and complete physical acceptance.

**Verification commands:**

```bash
cd global/tools/dev-main-sync
./scripts/generate-icon.sh --check
./scripts/v4-preflight-acceptance.sh
./scripts/v3-preflight-acceptance.sh
./scripts/v2-body1-acceptance.sh
./scripts/v2-body2-acceptance.sh
./scripts/v2-body4-acceptance.sh
./scripts/verify-m1.sh
./scripts/verify-m5.sh
./scripts/verify-m6.sh
cd ../../..
bash .github/scripts/verify-skills.sh
bash ~/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
```

Use the renamed paths/products/selectors produced by Task 2 where command internals change. Keep
stable script entrypoint names unless a script is app-branded rather than capability-versioned.

## 9. Acceptance ledger

| Acceptance ID | Final observable requirement | Evidence |
|---|---|---|
| `V4-AT-01` | All operator-facing application identity says ShadowSync | `DM4-T01/T02`; copy audit |
| `V4-AT-02` | Bundle/process/executable and Swift implementation identity use ShadowSync | `DM4-T02`; package/symbol/process census |
| `V4-AT-03` | Stable bundle ID, label/plist, state, schemas, metadata keys, Git namespace, capability ID/path remain exact | `DM4-T01/T12`; pinned digest matrix |
| `V4-AT-04` | Original icon meets design, size, margin, readability, and no-mark requirements | visual review plus `DM4-T03` |
| `V4-AT-05` | Icon generation is deterministic and production copies stable committed bytes | `DM4-T04/T11` |
| `V4-AT-06` | Signed bundle declares and contains the readable icon exactly once | `DM4-T03`; bundle inventory/codesign |
| `V4-AT-07` | Fresh install writes only ShadowSync under the existing label/state | `DM4-T05` |
| `V4-AT-08` | Verified installed predecessor migrates through cooperative drain with no process overlap | `DM4-T06/T07` |
| `V4-AT-09` | Old bundle is removed/quarantined only after new ready proof | `DM4-T06/T08` |
| `V4-AT-10` | Every fault cut preserves/restores the last known-good bundle and matching plist ownership | `DM4-T08` |
| `V4-AT-11` | Both canonical paths and mismatched job/process states never create duplicate ownership | `DM4-T07/T09` |
| `V4-AT-12` | repair/doctor/rollback/uninstall safely recognize both generations and residue | `DM4-T09` |
| `V4-AT-13` | Preferences, authorities, logs, retention, locks, sockets, recovery evidence survive with no state migration | `DM4-T06/T09`; byte snapshots |
| `V4-AT-14` | Hotkey/menu foreground, host activation, lifecycle exit, and drain remain correct | `DM4-T10`; M5/v3 |
| `V4-AT-15` | Independent production builds preserve reproducibility with identical icon bytes | `DM4-T11`; M6 |
| `V4-AT-16` | No old executable/process or stale user-facing name exists in forward steady state | `DM4-T01/T07`; physical census |
| `V4-AT-17` | Every inherited v3 requirement and acceptance row passes at final v4 head | `DM4-T12`; `DM3-T01–T16`; v3 ledger |
| `V4-AT-18` | M1 `<5s`/100-repository and M6 delayed-host readiness pass unchanged on a valid host | final exact-head M1/M6 receipts |
| `V4-AT-19` | No paid runner, second job/state, updater, dependency, Xcode project, or cache-based truth source exists | governance/source/package audits |
| `V4-AT-20` | One Draft PR, clean reviews, explicit GO, reviewer-App merge, exact-main install occur in order | delivery receipt |

All rows are release-blocking. No baseline pass substitutes for final exact-head evidence after the
rename/build/lifecycle changes.

## 10. Physical acceptance and delivery gates

### 10.1 Pre-merge isolated physical acceptance

1. Build testing and production ShadowSync bundles from exact Draft PR head in fresh private roots.
2. Verify package/module/executable/process names, icon key/resource/sizes/hash, inventory,
   signature, bundle ID, and stable custom metadata.
3. Create a complete synthetic installed predecessor with valid app/plist/job/host/socket/state.
4. Snapshot and classify the full state tree; migrate; prove no old/new process overlap; require
   durable content equality and only the expected coordination-record transitions.
5. Exercise every fault cut, both canonical apps, wrong-path label/process, repair, doctor,
   rollback, and uninstall.
6. Exercise icon display in Finder list/icon view and normal application launch on light/dark
   backgrounds without cache deletion.
7. Repeat v3's 20 cold chooser trials and zero pre-Continue child/network/authority proof.
8. Select 1 and 3 among 51 poison repositories; exercise Save/Manage/Continue/Cancel/Quit, host
   activation, and drain.
9. Require all helpers reaped and all isolated roots removed.

### 10.2 Remote gates

- Open one Draft PR from the existing implementation branch after local final-head gates pass; keep
  that PR Draft throughout implementation and review.
- Exact-head runnerless `pr-automation / verify` passes.
- Bugbot and security review have no unresolved material finding.
- Operator receives exact head, asset hashes, migration/fault ledger, naming allowlist, full test
  receipts, valid-host metrics, and residual uncertainties.
- Only explicit operator GO permits Ready for Review.
- The reviewer App alone approves and arms native governed merge.
- Never call `gh pr merge --auto`, alter auto-merge, directly merge, bypass checks, or add runners.

### 10.3 Post-merge installed handoff

1. Require the durable primary to be clean `main` exactly equal to `origin/main`.
2. Re-run source attestation, icon check, v4/v3/v2/M1/M5/M6, owner, and doc-warden gates.
3. Build and install only from exact clean main through the existing source-built lifecycle.
4. Migrate the installed verified predecessor through §4.3; do not manually delete or move it.
5. Run doctor and record source/input/bundle/icon hashes, signature, label/program/PID, ready host,
   state preservation, and absence of old/residue paths.
6. Physically verify icon, menu/hotkey foreground, chooser performance, selected no-op flow,
   cancellation, and Quit drain without mutating a real repository.
7. Confirm no old process/bundle, temporary fixture, helper, dirty checkout, unpushed implementation
   commit, open material review, or unrecorded recovery state remains.

## 11. Planning-lane validation and freeze

For this plan-authoring task only:

```bash
bash ~/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
git diff --check
git diff --name-only
shasum -a 256 \
  docs/plans/dev-main-sync-global-capability-v2.md \
  docs/plans/dev-main-sync-global-capability-v3.md
rg -n 'V4-(NAME|MIG|ICON|COMP|LIFE|TEST|GOV)|DM4-T|V4-AT-' \
  docs/plans/dev-main-sync-global-capability-v4.md
```

Required result before commit:

- only this v4 plan and `docs/plans/README.md` differ;
- v2/v3 SHA-256 values remain
  `36fc11c68601de2d1874c8e7aed648c9be186cf82cbeca8e65c14af26eae64f4` and
  `52f51c621a87bf986f36a87398e2f660dc06c30bd5380c6a6bf8df01875f9dbd`;
- doc-warden reports this v4 plan `CONFORMANT`;
- all seven v4 requirement families, `DM4-T01–T12`, `V4-AT-01–20`, inherited v3 closure, naming
  matrix, migration/fault matrix, icon contract, valid-host M1/M6 evidence, and governed delivery
  prohibitions are present;
- no unresolved placeholder, scratch plan copy, secret, or operator-specific absolute path exists.

**APPROVED — ShadowSync v4 application identity, icon, and installed-app handoff plan**
