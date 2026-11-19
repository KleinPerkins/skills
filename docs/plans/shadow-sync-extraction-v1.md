# ShadowSync standalone extraction and signed delivery — execution package v1

**Version:** v1
**Status:** ACCEPTED — 2026-11-02
**Date:** 2026-11-02
**Owning repository:** `KleinPerkins/skills`
**Plan-type:** standard
**Decision owner:** Laurence Duggan.  
**Implementation leads:** macOS application architect and release engineer, with separate owners for Skills, dev, AWA, and repository administration.

The target is **public `KleinPerkins/shadow-sync`, proprietary licensing, and free standard GitHub-hosted CI**. Your later selection replaces the original initially-private requirement. The product remains **ShadowSync**, distributed as **ShadowSync.app**, with technical identity **`shadow-sync` / `com.kleinperkins.shadow-sync`**.

The decision owner accepted this package on 2026-11-02 with the instruction “PLEASE IMPLEMENT THIS PLAN”. The submitted package SHA-256 is `7b277d2511e41ba4b851c5cb5dab679db0ad9206964c4a427d73d33d6c8084f0`. Acceptance authorizes the scoped implementation and normal governed delivery; external safety, product-release, installation, retirement, and UAT gates remain binding. The investigation statements below describe the pre-implementation evidence snapshot.

**Linked successor:** [ADR 0010](../adr/0010-shadow-sync-extraction-ownership.md). This historical plan remains owned by Skills after product-source handoff. Accepted bytes are immutable under the approved legacy Git-bound transaction; later findings belong in evidence/runbooks or a successor.

**Governance transaction:** one scoped owner-approved legacy documentation transaction; no doc-warden v2 enrollment, synthetic receipt, altered legacy receipt, or frozen-document rewrite. The four-file diff and its acceptance are retained with the source PR. The legacy structural checker validates placement/indexes, not semantic acceptance.

## 1. Verified baseline and delivery reference

### ShadowSync and governing repositories

The investigation distinguished live remote revisions from local checkouts:

- **Skills:** live `main` is `22461fcbfbbf55b1e5a3d1f739e94b63a5425561`. This chat’s clean, detached worktree is at `bccf229ebbe09c205a87b218b94cb5c7ba31b5bf`. The complete ShadowSync subtree is unchanged between them; the intervening commits concern other capabilities. The primary checkout is also behind and must not be reset or repurposed.
- **Sterling:** live `main` is `c7becaebed14b5ebcc19871f4490ba4343641108`; its clean primary checkout remains at `2af29d6a3bccff89ce40e49725bea7b76f5529b3`.
- **dev:** live `main` is `b1b8ee9f995b3c5217a3c4a8958439cb01e39b36`.
- **AWA:** live `main` is `49adac98c5e678d13fd90fd7eb6cfc432fad9952`.
- **Ecosystem orchestrator:** live `main` is `29f487765bcf8719798913cf42d4261f509f1292`.
- **PR automation controller:** live `main` is `fe9a3a20073e7fd4e2fed078188f50ec4a952c2e`.

These revisions are the planning evidence baseline, not permission to execute against stale checkouts. Every implementation work package must revalidate its owning remote and accepted dependencies.

ShadowSync currently contains **111 tracked files**. Its Swift package has `ShadowSyncCatalog`, `ShadowSyncCore`, `ShadowSyncApp`, the executable `ShadowSyncSelfTest`, and `ShadowSyncCompileTests`. It declares Swift tools **6.2**, minimum macOS **26.0**, and currently has no package dependencies. Runtime dependencies include the Apple frameworks, `/usr/bin/git`, `/bin/launchctl`, the optional bounded `gh` adapter, and the governed host-policy/AWA integration. [Current package](https://github.com/KleinPerkins/skills/blob/22461fcbfbbf55b1e5a3d1f739e94b63a5425561/global/tools/dev-main-sync/Package.swift)

The installed application was inspected directly:

- Location: `/Users/laurence.duggan/Applications/ShadowSync.app`.
- Version **0.9.0**, build **14**, **arm64**, minimum macOS **26.0**.
- Bundle identifier **`com.kleinperkins.dev-main-sync`**.
- Ad-hoc signature, no Team Identifier; strict signature verification passed.
- Embedded source revision **`6c1d5fcc6ac2bdd7d3b2e733aeab98b72b1561dd`**, from [Skills PR #234](https://github.com/KleinPerkins/skills/pull/234), rather than the original v0.9 revision recorded in the release runbook.
- LaunchAgent **registered but not running**, with `RunAtLoad=false`, `KeepAlive=false`, and `--managed-host`.
- State remains under `~/.local/state/dev-main-sync`, including authorities, saved selections, retention artifacts, `latest.log`, socket/owner records, and coordination locks.
- Actual Login Item registration is **unverified**: the read-only Background Task Management query required unavailable authorization. `RunAtLoad=false` does not establish the user’s Login Item preference.
- Global process absence is also **unproven** because process enumeration was unavailable. Migration must establish exclusion through authenticated process identity, launchd state, sockets, and locks.

The [iterative-delivery runbook](https://github.com/KleinPerkins/skills/blob/22461fcbfbbf55b1e5a3d1f739e94b63a5425561/docs/runbooks/shadowsync-iterative-delivery.md) still records Beta v0.9 with UAT open. Its original installed-source receipt is historical, not current installed provenance.

There is a governance discrepancy to resolve prospectively: ADR 0005 and the v0.6 plan remain marked **DRAFT**, and [PR #216](https://github.com/KleinPerkins/skills/pull/216) explicitly introduced draft authority, while later delivery text treats their behavior as accepted. The extraction must adopt the required behavior explicitly in successor records; it must not rewrite historical acceptance status.

### Hard-no-touch dependency status

The safety remediation is not complete:

1. AWA’s generic contract merged through [PR #184](https://github.com/KleinPerkins/awa/pull/184), governed by accepted ADR 0027 and its frozen plan.
2. Maintenance-release governance merged through [PR #185](https://github.com/KleinPerkins/awa/pull/185).
3. There is still **no remote `release/1.8` branch and no `v1.8.2` tag**.
4. Installed AWA and Skills remain pinned to **v1.8.1**, commit `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`.
5. dev’s `_ops/policy/worktree-policy.yml` has no `hard_no_touch_paths`.
6. ShadowSync has no hard-no-touch consumer. Its current closed parser would reject that new policy field rather than support it.
7. Controller `main` still rejects non-default PR bases. The retained maintenance-base branch is explicitly unfinished and stale; it is not an implementation branch that can safely be resumed unchanged.

**Consequence:** extraction, renaming, CI, packaging, and synthetic safety tests can proceed independently. Installed activation remains blocked by the governed controller/AWA release and downstream policy sequence.

### Sterling parity matrix

Sterling’s current sources were inspected at its live revision, including its [delivery ADR](https://github.com/KleinPerkins/sterling.io/blob/c7becaebed14b5ebcc19871f4490ba4343641108/docs/adr/0001-native-github-delivery-and-signed-macos-updates.md) and [release runbook](https://github.com/KleinPerkins/sterling.io/blob/c7becaebed14b5ebcc19871f4490ba4343641108/docs/runbooks/releasing.md).

| Area | Observed Sterling configuration and exercise | Proposed ShadowSync adaptation | Acceptance evidence |
|---|---|---|---|
| Repository and protection | Public; squash-only; linear history; one approval; stale-review dismissal; resolved discussions; strict `ci-required` from GitHub Actions App `15368`; force-push/deletion protection. Public secret scanning, push protection, vulnerability reporting, and Dependabot security updates enabled. | Same public protection model, explicit proprietary license, plus the narrow dev exception below. Protect release tags and enable immutable releases. | Read-back settings/rulesets; rejected unauthorized push/tag operations in disposable administration fixtures; exact-head ordinary PR canary. |
| CI and ordinary PR delivery | Current-main [CI run 41290790685](https://github.com/KleinPerkins/sterling.io/actions/runs/41290790685) passed quality, macOS 15, macOS 26, and aggregate gate. [App run 41290772286](https://github.com/KleinPerkins/sterling.io/actions/runs/41290772286) approved PR #12’s exact head and armed native squash auto-merge. | macOS 26 arm64 only; substantive ShadowSync runtime suites; explicit Xcode selection. The installed reviewer App alone approves and arms exact-head native squash auto-merge. | Successful source and PR runs; stale-head/race/untrusted-author/protected-path refusal tests; verified native merge of the tested revision. |
| Release management and credentials | Release-please has created/updated [PR #5](https://github.com/KleinPerkins/sterling.io/pull/5). [Credential-readiness run 41164898459](https://github.com/KleinPerkins/sterling.io/actions/runs/41164898459) proved disposable signing, notarization authentication, and Sparkle key matching. **No product tags, releases, or assets exist.** | Independent version/build sequence; ShadowSync-specific Sparkle key; protected release environment; full signed application and installed-update qualification. | Separate readiness receipt, notarization receipt, immutable release receipt, clean-install evidence, and build-15→16 update evidence. |
| Updates and artifact immutability | Sparkle 2.10.1 is pinned. Feed is `releases/latest/download/appcast.xml`. Tag update/deletion is protected, but GitHub release immutability is **disabled**. Publication/installed updates are unexercised. | Immutable release assets; protected beta/stable Pages feeds; pilot promotion of identical bytes; lifecycle coordinator around replacement. | Tamper rejection, feed verification, interrupted update/recovery matrix, installed update, and channel-promotion evidence. |
| Dependency maintenance | Successful push and scheduled dependency jobs exist, including [run 41402908913](https://github.com/KleinPerkins/sterling.io/actions/runs/41402908913). No Dependabot-authored PR has exercised the complete refresh/approval/merge path. | Weekly dependency maintenance, exact pins, separate bot eligibility, mandatory CI for dependency changes. | First actual eligible dependency PR completes the governed path; no-op jobs alone do not qualify it. |

The account-plan API returned `plan:null`; exact billing-plan identity was not available through the authenticated token. Private Skills protections demonstrate capability, but do not establish every private-repository entitlement. GitHub documents that environment reviewer approvals are unavailable for private repositories on Free/Pro/Team, while standard hosted runners are free for public repositories. Your public-source selection resolves both constraints without weakening controls. [Environment limits](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments), [hosted-runner policy](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)

## 2. Destination, ownership, draft ADRs, and complete identity change

### Destination and extraction boundary

Use **`/Users/laurence.duggan/dev/personal/shadow-sync`** as the durable primary checkout. ShadowSync becomes a standalone macOS product, alongside Sterling. Reusable generic policy remains in AWA and concrete host policy remains in dev.

The destination contains:

- Existing Swift package, application/catalog/core modules, resources, icon provenance, and third-party notices.
- Existing self-tests, fixtures, native probes, shell verification scripts, and safety contracts.
- A minimal Xcode packaging project that consumes the existing modules and embeds/signs Sparkle and the lifecycle coordinator.
- Repository-owned build, CI, release, provenance, migration, recovery, and update tooling.
- Product documentation, adopted requirements, open defects/UAT, and sanitized historical evidence.
- `AGENTS.md`, repository policy, CODEOWNERS, security policy, dependency configuration, and governed documentation.

It does **not** import Skills’ unrelated capabilities, `.git` history, local hooks/state, installed bundles, logs, saved repository selections, retention archives, credentials, machine-local configuration, or raw screenshots containing private information.

Use a **reviewed snapshot export**, not a mirror, subtree history import, or filtered copy of the entire private repository. The initial import records:

- Original repository and exact source revision.
- Original subtree identity.
- Original-to-destination path mapping, file modes, and SHA-256 hashes.
- Explicit transformations for sanitization and renaming.
- Third-party provenance and license obligations.
- A private full receipt and a public sanitized provenance manifest.

Keep useful history in the original private Skills repository. Public historical summaries are identified as derived records, with their original revision/digest references. Accepted historical documents remain byte-preserved.

Public proprietary source remains visible and forkable under GitHub’s service terms; proprietary licensing does not make the published source confidential. The export review is therefore a publication gate. [GitHub licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)

### Accepted architectural decisions (destination ADR adoption pending)

**ADR 0001 — Standalone ownership and provenance — ACCEPTED IN THIS PLAN**

- ShadowSync becomes a public, proprietary macOS product owned by `KleinPerkins/shadow-sync`.
- Import a sanitized snapshot with provenance; preserve private history in Skills.
- Preserve existing product behavior and open UAT. No general UI redesign, Git-repair expansion, cleanup-permission expansion, or broader operating-system support.
- The original source becomes frozen during handoff. After parity verification, the new repository becomes the sole implementation authority.

**ADR 0002 — Permanent technical identity — ACCEPTED IN THIS PLAN**

- Adopt `shadow-sync`, `ShadowSync`, and `com.kleinperkins.shadow-sync` throughout active technical surfaces.
- Preserve `ShadowSync.app` and executable `ShadowSync`.
- Use explicit legacy readers for migration and historical records; new writes use only the new identity.
- Never retain a running legacy identity, legacy lock namespace, or source installer indefinitely.

**ADR 0003 — Installation, lifecycle, and update authority — ACCEPTED IN THIS PLAN**

- Retain the managed-LaunchAgent/manual-router architecture.
- A signed bundled `ShadowSyncLifecycleCoordinator` owns first install, identity migration, repair, removal, and update coordination.
- Sparkle is the sole normal distribution-update mechanism after the new identity is established.
- The production application requires no Skills checkout or compiler.
- Existing source installers become fixture/development tools and refuse production mutation.
- A failed signing, migration, or Sparkle qualification leaves delivery incomplete; it does not authorize a source-updater fallback.

**ADR 0004 — Native GitHub delivery exception — ACCEPTED IN THIS PLAN**

- Only `KleinPerkins/shadow-sync` is authorized to use free standard GitHub-hosted Actions runners and the Sterling-style reviewer App process.
- The reviewer App alone approves eligible exact heads and arms native squash auto-merge.
- Ordinary implementation PRs do not acquire a generic operator code-review gate.
- Protected automation administration and product release approval remain separate owner-controlled activities.
- Skills, the controller fleet, and existing runnerless policies remain unchanged.

The dev-owned companion decision must register this specific exception in its policy/baseline classification, so enforcement does not mistake the new repository for runnerless drift or rewrite it into a fleet profile.

### Interfaces owned elsewhere

**AWA** retains `awa-hard-no-touch/v1` and its matching semantics. Use a separately accepted AWA contract adoption for the existing:

- `load_hard_no_touch_matcher(path, home=...)`
- `HardNoTouchMatcher.classify(candidate)`

Do not use the broader `PolicyConfig.load` path or copy the matcher into Swift.

The ShadowSync adapter uses isolated Python, a verified installed AWA module, a trusted home derived from account identity, typed stdin, and one bounded JSON response. Only the exact result `matched=false`, `kind=none`, `policy_valid=true` permits subsequent candidate access. Missing/wrong pins, malformed output, extra stdout, timeout, invalid candidate, and invalid policy fail closed. Candidate paths never enter argv, environment, or diagnostic logs.

The separate AWA adoption ADR/tests must bind the exact eventual v1.8.2 commit and module digest. It adds no runtime code to the frozen v1.8.2 release scope.

**dev** retains all concrete roots and namespace prefixes. Add a small dev-owned compatibility manifest binding the policy schema and policy digest; it contains no duplicated policy literals. ShadowSync verifies that deployed binding before discovery. This matters because AWA’s optional field can legitimately be absent: a valid “no match” result alone does not prove the required host policy was deployed.

**Skills** retains a minimal `shadow-sync` discovery record:

- `shape: descriptor-only`
- `sync_policy: none`
- `post_mgmt: none`
- `expose: none`
- Public source/release pointer and provenance only.
- Any schema-required installer accepts checks/information only; it cannot clone, build, download, register, or install.

**Ecosystem orchestrator** renames its excluded registry entry and keeps it excluded: standalone macOS product, discovery only, no downstream runtime or payload. Current `dev-main-sync` is already excluded; there is no verified cpp payload consumer and no cpp change is planned.

### Rename and compatibility inventory

The source scan found **597 matching lines across 70 files**, covering application/core/catalog code, metadata/resources, a legacy fixture, and all 28 scripts. The implementation records each occurrence in the rename ledger; the following mappings cover the discovered families.

| Surface and owner | Old → new | Consumers, persistence, migration and retirement |
|---|---|---|
| Repository and checkout — new product/Skills | `KleinPerkins/skills:global/tools/dev-main-sync` → `KleinPerkins/shadow-sync` repository root; durable checkout → `~/dev/personal/shadow-sync` | Build/release/documentation consumers switch at source-authority handoff. Private originals remain in Git history, not as a second editable source. |
| Capability and registry — Skills/orchestrator | `dev-main-sync` → `shadow-sync`; `global/tools/dev-main-sync` → minimal `global/tools/shadow-sync` descriptor | Replace metadata and excluded registry entry together through ordered PRs; regenerate `.eco-registry.lock` with lockkit. Old entry/wrapper removed after compatibility retirement. |
| Product/module names — ShadowSync | Existing `ShadowSync.app`, `ShadowSync`, `ShadowSyncCatalog/Core/App/SelfTest` remain | Already final names; assert them in packaging and executable discovery. No gratuitous module rename. |
| Bundle, OSLog and process authority — ShadowSync | `com.kleinperkins.dev-main-sync` → `com.kleinperkins.shadow-sync` | Persisted/external. Migrate through the coordinator; validate new signing requirements, peer identity, owner records, and routing. Old ID allowed only in legacy readers/evidence. |
| LaunchAgent — ShadowSync/macOS | `com.kleinperkins.dev-main-sync.plist` and label → `com.kleinperkins.shadow-sync.plist` and label | Boot out old label before new admission; preserve exact program/arguments and opt-in startup semantics. Verify old label absent before commit. |
| Login Item/preferences — ShadowSync/macOS | Old bundle registration/defaults domain → new bundle registration/domain | No automatic transfer assumption. Native Settings removal of old item; preserve desired startup intent; normal new-ID opt-in. Copy only recognized app-owned preference keys; retain old plist for rollback until retirement. |
| State root — ShadowSync | `~/.local/state/dev-main-sync` → `~/.local/state/shadow-sync` | Atomic same-parent rename with the same open lock descriptors/inodes. No symlink, alias, duplicate active state, or replacement lock file. |
| State files — ShadowSync | `repository-authorities.json`, `selection-preferences.json`, `latest.log`, `retention/`, `host-owner.json`, `host.sock`, `launcher/lifecycle/operation/run.lock` | Basenames remain meaningful. Authorities/selections migrate schema without changing user choices. Logs/retention preserve existing bytes. Ephemeral host/socket records are regenerated under the new release identity. |
| Release metadata — ShadowSync | `DevMainSync{ReleaseSchema,SourceRevision,SourceInputSHA256,MetadataContractSHA256,Architecture,BuildMode}` → `ShadowSync…` | New signed manifest replaces installed-source/eco-lock trust. `MetadataContractSHA256` is renamed during extraction, then superseded explicitly by a standalone release-contract digest; no live Skills metadata dependency remains. |
| Symbols and helpers — ShadowSync | `devMainSync*` → `shadowSync*`; active `DevMainSync*` → `ShadowSync*`; `dms_*` → `shadow_sync_*` | Mechanical source/script change with compile/runtime coverage. Historical legacy-adapter names are narrowly allowlisted. |
| Environment and command protocols — ShadowSync | `DEV_MAIN_SYNC_*`, `DMS_*` → `SHADOW_SYNC_*`; `--dev-main-sync-*`, `--dms-test-*`, `--_dms-*` → corresponding `--shadow-sync-*` forms | Rename producers and consumers atomically. Includes sentinel, fixture, executable, root, mode, request, output, timeout, repository, origin and remote variables. Existing `SHADOW_SYNC_TESTING` remains. Production rejects test-only routes. |
| Schemas — ShadowSync | `dev-main-sync-…/vN` → `shadow-sync-…/vN` | Covers release, host, host-request/response, control, log v1/v2, event, report, batch-plan/report v2, authorities v1, selections v1, retention v2, and harness schemas. Legacy data decoding remains explicit; new writes use new names. |
| Temporary/build paths — ShadowSync | `.dev-main-sync-app.*`, `/private/tmp/dev-main-sync-*`, `/dev-main-sync-source`, `/dev-main-sync-build` → `shadow-sync` forms | Development/fixture consumers change together. Owned cleanup verifies exact paths and process identities; no broad cleanup glob. |
| Delivery and references — all affected owners | Active old script labels, CI strings, documentation links and source pointers → new repository identity | New tags `shadow-sync-vX.Y.Z`; artifacts include version, build and architecture; feeds use the new repository. Frozen ADRs, receipts, historical filenames and exact compatibility fixtures retain original spelling. |

Add `verify-technical-identity` to scan tracked content, filenames, generated plists/manifests, executable strings, signing identifiers, and cross-repository active references. Exceptions are file-specific and token-specific, with a reason, owner, and retirement class—never a blanket exclusion for an entire source directory.

Legacy installation readers remain for **at least two verified standalone releases and 90 days**, then retire through a reviewed change after known installations have migrated. Historical log/retention readers may remain as documented data-format compatibility; they cannot launch the old product or write old-format active state.

## 3. Installation, cutover, update, and recovery design

### First installation

Distribute a notarized DMG containing the signed application and bundled coordinator. Launching the verified distribution from a noncanonical location enters setup only; it cannot enumerate or operate on repositories.

The coordinator installs into `~/Applications/ShadowSync.app`, registers the new managed LaunchAgent with `RunAtLoad=false` and `KeepAlive=false`, and proves staged readiness. It requires neither a source checkout nor a compiler. Existing Git/AWA/host-policy prerequisites remain separately validated; standalone installation does not silently install those dependencies.

Unknown existing bundles, a conflicting `/Applications` installation, wrong ownership, symlinks, malformed state, or ambiguous old/new installations cause a non-destructive refusal with a precise recovery path.

### Legacy build-14 migration

The supported initial migration input is the verified legacy `0.9.0 (14)` identity. Other legacy builds require an explicitly supported receipt or recovery procedure; matching a display name is insufficient.

1. **Preflight and preservation.** Verify old bundle, release metadata, state ownership/modes, policy readiness, free space, same-filesystem staging, and every expected coordination entry. Save a private manifest and byte-preserving rollback copy of the app, plist, preferences, authorities, selections, logs and retention metadata. Do not inspect protected repositories.
2. **Retire legacy launch routes.** The current Skills installer must already refuse production mutation. Record desired startup behavior and require the old Login Item to be disabled/removed through normal System Settings. Do not launch unsafe old 0.9 merely to query startup status, edit BTM databases, or assume the new bundle can unregister the old one.
3. **Drain under existing authority.** Preserve the established lock ordering and acquire lifecycle/operation authority. Request authenticated cooperative exit; wait for owned work and descendants to drain. Boot out only the verified legacy label and acquire launcher exclusion. Never signal an unverified PID or delete a contended lock.
4. **Persist the transaction.** Write and fsync `shadow-sync-migration/v1`, identifying preimages, phases, rollback artifacts, app identities and device/inode evidence. Recovery can find it at either the old or new state path.
5. **Move the state namespace.** Hold the same log-namespace and coordination descriptors while atomically renaming the state directory. Assert unchanged lock inodes. Do not unlink/recreate locks or retain an old-path alias. Avoid lock upgrades while holding lower-order locks.
6. **Migrate active documents.** Validate and atomically translate authority and selection schemas while preserving roots, origin bindings, document IDs, revisions and selection intent. Preserve existing log/retention bytes; historical decoders read old frames and new writes use new schemas. Malformed/newer data is preserved and refused, never reset.
7. **Replace the application transactionally.** Reuse identity-checked incoming/previous staging, fsync, and no-replace promotion. Install the new plist and regenerate ephemeral host/socket records. Keep the old label absent.
8. **Prove staged readiness.** Release only the admission locks needed by the new host while retaining the same effective operation lock. The new host must authenticate its release and control channel without accessing repositories, starting Git/network work, or acquiring the coordinator-held operation lock.
9. **Commit and opt in.** Commit the journal only after app, state, label, signature and readiness converge. Release operation exclusion. Present the preserved startup intent and use normal `SMAppService.mainApp` opt-in for the new identity. No automatic startup registration.

Apple’s Service Management API treats registration and authorization as explicit operations; bundle-ID changes must not be treated as registration transfer. [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice?language=objc)

### Sparkle integration

Keep the managed-host design. Add a signed coordinator with signing identifier `com.kleinperkins.shadow-sync.lifecycle-coordinator`, staged into an owner-only transaction location before replacement so it can survive application-bundle replacement.

For every reachable installation route:

- Stop new operation admission and wait for active work to settle.
- Establish authenticated coordinator communication, durable `shadow-sync-update/v1`, and continuous lock ownership before permitting Sparkle’s installation transition.
- Keep operation exclusion through replacement, signature/provenance validation, new-label routing, and staged readiness.
- Regenerate release-bound socket/owner records; do not compare the new app against the old release’s code hash.
- Commit only after verified convergence; preserve a recovery transaction on interruption.

Use Sparkle 2.10.1 initially, with the inspected archive SHA-256:

`1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27`

Manual checking and opt-in scheduled checking are supported. Silent automatic installation is disabled for the first standalone release. All reachable install-on-quit/ordinary-quit paths must still obey the coordinator. A relaunch-postponement delegate is insufficient because Sparkle documents paths where it is not called. [Sparkle delegate contract](https://sparkle-project.org/documentation/api-reference/Protocols/SPUUpdaterDelegate.html), [update settings](https://sparkle-project.github.io/documentation/customization/)

The existing bundle verifier rejects every symlink, which is incompatible with Sparkle’s normal framework topology. Replace that rule with a sealed manifest walker that permits only the exact reviewed internal framework links, rejects escapes and unexpected files, and verifies all nested code. Do not solve this by disabling library validation.

### Failure and rollback rules

- **Active/contended work:** postpone; leave installation unchanged.
- **Both state roots or installations present:** refuse automatic selection/merging; preserve both and report exact conflicts.
- **Interrupted transaction:** reacquire the recorded lock namespace, validate journal/preimages, and resume idempotently. Never infer completion from an app version alone.
- **Failure before readiness commit:** stop the candidate, restore verified old app/plist/state schemas and directory name using the same lock inodes. Restore the old app only to a **stopped** state while its safety remediation remains unresolved.
- **Failure after readiness commit:** keep the new installation authoritative; repair forward. Cleanup failure must not produce mixed old/new state.
- **Coordinator crash:** durable journal blocks operation admission. Recovery from the signed DMG can repair a missing or unusable installed app.
- **Rollback after new-version operations:** no automatic downgrade. First prove state-format compatibility and preserve new data; otherwise use a newer corrective build.
- **Login Item rollback:** never silently recreate old registration. Report startup as disabled and preserve the user’s desired setting.
- **Legacy retirement:** remove old executable launch routes, plist, preference residue and compatibility wrapper only after verification. Retain a non-executable recovery archive until migration, installed-update proof and the retention gate pass.

Public source disclosure and deletion of the last rollback copy are consequential boundaries. Public export requires the approved sanitized manifest; rollback-copy deletion requires a separate retirement receipt. No user-data deletion is required for extraction.

## 4. Repository governance, substantive CI, and signed releases

### Repository configuration specification

Bootstrap administration creates/configures the repository only after the export and governance gates pass:

- Public visibility; default branch `main`; proprietary license; Lucide ISC and Sparkle notices retained.
- Squash-only merges, branch deletion after merge, linear history, force-push/deletion protection.
- One required approval, stale-approval dismissal, resolved conversations, strict current-base `ci-required` bound to GitHub Actions.
- Protected `shadow-sync-v*` tags and GitHub immutable releases enabled before the first product release.
- CODEOWNERS for product code and stricter ownership for workflows, policy, signing, installer/update authority, release scripts, dependency locks, entitlement files, release metadata and feed publication.
- Private vulnerability reporting, public secret scanning/push protection, dependency graph, alerts and security updates enabled where available and verified by read-back.
- Actions use full commit pins, read-only default token permissions, standard hosted runners only, no larger/self-hosted runners, no paid usage, and bounded artifact retention.
- No existing fleet App, controller or excluded repository is modified as an incidental bootstrap step.

Use the existing approved reviewer App model with repository-scoped tokens and the minimum required Contents/Pull requests/Metadata permissions. Ordinary eligibility must check open/non-draft status, same-repository head, trusted author, complete changed-file list, exact workflow/head correspondence, correct check integration, and absence of protected paths.

Release-please and dependency PRs use their explicit policies, not the ordinary-author shortcut. Privileged automation must execute trusted default-branch code, never arbitrary PR code with an App token.

Protected automation changes receive technical review and the prescribed owner/admin administration path. This is not a generic operator code-review requirement for ordinary implementation.

### CI specification

Initial support is **arm64 on macOS 26**, deployment target **26.0**. Do not claim Intel, universal binaries, macOS 15, or macOS 27 support.

Select **Xcode 26.6, build 17F113**, through `/Applications/Xcode_26.6.app/Contents/Developer`, and its bundled Swift toolchain. Preserve the package’s Swift-tools minimum 6.2. Capture and validate Xcode/Swift/SDK/image identity in receipts. GitHub’s inspected runner manifest lists this toolchain; hosted image revisions remain moving inputs and must be recorded. [Runner manifest at verified revision](https://github.com/actions/runner-images/blob/6d2bc0ac6b93f732b1a5baebf587d812853892c4/images/macos/macos-26-arm64-Readme.md)

A universal build is deferred: cross-compiling an Intel slice would not establish Intel runtime, installer, native UI or update support.

Required workflow jobs:

- **`quality` — Ubuntu, 15-minute timeout:** source/identity checks, schema validation, shell/Python checks, documentation/provenance, secret/private-data scanning, dependency/action-pin validation, and protected-path classification.
- **`compile-package` — macOS 26 arm64, 30 minutes:** production/testing builds, explicit compile-only SwiftPM checks, minimum OS/architecture/resource validation, and production exclusion of test seams.
- **`runtime-safety` — macOS 26 arm64, 90 minutes:** execute `ShadowSyncSelfTest` through the canonical harness, including Git safety, policy, locking, child ownership, cancellation, report/retention and repository lifecycle cases.
- **`native-and-lifecycle` — macOS 26 arm64, 90 minutes:** executable/AppKit probes, simulated-launchd lifecycle tests, installer/update fault injection, and focused beta regressions.
- **`package-contract` — macOS 26 arm64, 30 minutes:** production bundle layout, nested-code inventory, coordinator separation, release manifest, signature structure and updater-disabled development build.
- **`ci-required` — always evaluated:** require every mandatory job and suite receipt for the exact head, with no missing, skipped, cancelled, failed, zero-test or incomplete mandatory result.

Run on PRs, ready-for-review/synchronization events, main pushes, and explicit verification dispatches. Cancel superseded PR runs; serialize release transactions. Do not use path filters that silently omit mandatory coverage.

Existing substantive entrypoints to preserve/adapt include:

- `scripts/m1-core-tests.sh`, `m1-native-e2e.sh`, `verify-m1.sh`
- `verify-m5.sh`, `verify-m6.sh`, `m6-lifecycle-e2e.sh`
- v2 body acceptance, v3/v4 preflight acceptance, and beta v0.2–v0.9 verification scripts.

Plain `swift test` is explicitly a compile/package check with zero registered runtime tests; it cannot satisfy `runtime-safety`. [Existing test contract](https://github.com/KleinPerkins/skills/blob/22461fcbfbbf55b1e5a3d1f739e94b63a5425561/global/tools/dev-main-sync/README.md)

Create a suite manifest with stable test IDs and machine-readable completion receipts. The aggregate compares expected versus executed IDs and checks cleanup completion. Initially keep the existing suites intact; introduce deterministic sharding only if measured runtime requires it, retaining complete roster coverage.

Use disposable homes, state directories, local bare remotes and injected launchd adapters. Disable any existing “practical” mode that projects the real host inventory in CI. No test may probe real chaos-scheduler paths. Failed safety assertions cannot be converted into allowed failures or retries that hide the original result.

Retain small sanitized receipts and failure diagnostics for 14 days; retain release evidence with the release. No caches or artifact settings may create paid usage. Verify the applicable zero-paid-usage controls during bootstrap.

### Release and credential specification

Initial versions:

- **0.10.0, build 15:** first signed standalone migration candidate.
- **0.10.1, build 16:** first independently signed installed-update proof.
- Later builds increase monotonically; abandoned builds are never reused.
- `CFBundleVersion` and Sparkle’s build version agree. Semantic version and build number remain separate.

Use release-please for release PRs and changelogs. The release PR includes the allocated build, source revision, changes, migration compatibility, test evidence and known UAT limits.

Protected `release` environment:

- Reviewer: `KleinPerkins`.
- Protected branches only.
- Solo-owner self-review permitted, matching Sterling.
- Credentials become available only after environment approval.
- Environment approval authorizes release activity, not UAT acceptance.

Credential names:

- Repository: `AUTOMERGE_APP_ID`, `AUTOMERGE_APP_PRIVATE_KEY`.
- Release environment: `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`, `SPARKLE_PRIVATE_ED_KEY`.
- Nonsecret variable: `SPARKLE_PUBLIC_ED_KEY`.

The owner provisions credentials. Reuse an existing Apple team/certificate arrangement only after verifying it is the intended ShadowSync publisher. Generate a **new ShadowSync-only Sparkle key**; never reuse Sterling’s update key. Configuration inspection reads names/status only, never secret values.

The release pipeline:

1. Verify the exact tagged revision is on `main`, has passing required coverage, matches release metadata, and uses an unused increasing build.
2. Resolve dependencies before exposing signing credentials.
3. Build the production artifact with the pinned toolchain.
4. Import the signing certificate into an ephemeral keychain; preserve/restore the search list and delete temporary keys/files on every exit.
5. Sign nested helpers/frameworks inside-out, then the app, with Developer ID, hardened runtime and secure timestamps.
6. Use no additional entitlements by default. Reject `get-task-allow`, unsigned executable memory and disabled library validation unless a separately reviewed requirement proves necessity.
7. Submit with `notarytool`; require accepted status, retain the submission/log receipt, staple the app/DMG, and validate staples.
8. Verify signature, Team ID, designated requirements, architecture, deployment target, release manifest and Gatekeeper acceptance.
9. Produce `ShadowSync-X.Y.Z-buildN-macos-arm64.dmg`, the Sparkle ZIP, dSYMs, checksums, notices, appcast proposal and provenance receipt.
10. Sign the update ZIP with the ShadowSync EdDSA key and independently verify it.
11. Attach all assets while the release is draft; publish immutable and non-Latest only after the candidate gates pass.
12. Verify downloaded distributed bytes and release attestation; do not rely only on local build outputs.

Apple requires valid Developer ID signatures, hardened runtime and timestamps for this notarization route; notarization remains distinct from product acceptance. [Apple notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)

Use protected Pages feeds in the same public repository:

- `https://kleinperkins.github.io/shadow-sync/beta.xml`
- `https://kleinperkins.github.io/shadow-sync/appcast.xml`

Entries point to immutable tag-specific assets. The release job proposes channel changes; a protected promotion PR validates increasing builds, artifact digest/attestation, EdDSA signature and OS requirements. Beta candidates are published only to an explicitly selected pilot channel. Stable feed and GitHub Latest remain unchanged until the relevant installed and product gates pass.

The first two candidates remain beta qualification releases. Publishing build 16 to the pilot feed is a controlled test step; successful installed 15→16 evidence is required before broader promotion. Do not rebuild assets during promotion.

GitHub release immutability locks assets and associated tags at publication. Partial publication is handled by idempotent draft completion; published bad candidates require a new build/version, not asset replacement. [Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)

For key compromise, freeze channel promotion, revoke affected publisher credentials with Apple where appropriate, rotate update credentials through Sparkle’s supported trust transition, and issue a new corrective build. If an installed client cannot safely establish the new trust, recovery uses an independently verified notarized DMG. Never disable update-signature verification.

## 5. Ordered execution, verification, and acceptance gates

### Planning artifact locations

Before implementation, persist this package through the owning documentation workflow:

- **Skills parent plan:** `/Users/laurence.duggan/dev/capabilities/skills/docs/plans/shadow-sync-extraction-v1.md`.
- **Private evidence/rename ledger:** adjacent governed evidence under Skills, with exact revisions, manifests and sensitive evidence retained privately.
- **Skills ownership successor ADR:** next available number in `docs/adr/`, superseding only the source-ownership portion of ADR 0004.
- **dev exception ADR and policy change:** dev’s `_ops/adr/`, `_ops/POLICY.md` and baseline documentation.
- **New repository:** born under doc-warden v2, with project/roadmap/state under `.planning/`, semantic records under `.planning/artifacts/`, phase plans under `.planning/phases/`, the four ADRs under `docs/adr/`, and release/migration/recovery/UAT runbooks under `docs/runbooks/`.

Use validated previews and the applicable owner adoption workflow. Do not silently migrate Skills’ entire documentation system or rewrite frozen legacy documents. The proposed requirements below become the stable requirements for the new product’s accepted planning baseline.

### Phase and PR work packages

**P0 — Accept and freeze the planning baseline — 1–2 engineering days**

Owner: architect and documentation owner.  
Repositories: Skills, dev; AWA for the classifier-contract adoption.

- Persist requirements, ADR drafts, evidence ledger, rename ledger and phase dependencies.
- Resolve the v0.6/ADR 0005 discrepancy through a prospective adoption record.
- Accept the narrow native-delivery exception and AWA adapter contract.
- Verify document schemas, links, source revisions and unchanged historical bytes.

**Exit:** accepted, digest-bound scope and decisions.  
**Recovery:** revise draft/successor documents; no runtime impact.

**P1 — Public export and repository bootstrap — 2–3 days**

Owner: source architect and repository administrator.  
Repositories: Skills and new `shadow-sync`.

- Produce the allowlisted snapshot and provenance manifest.
- Review all exported files/history boundaries for secrets, machine data and private evidence.
- Create the public repository only after export review; configure identity, default branch, license and initial control files.
- Use native managed worktrees, unique `DEV_SESSION_ID`, local noreply identity and prescribed writer guards.

**Exit:** reviewed initial public tree with no unrelated Skills history.  
**Recovery:** correct unpublished export; after publication, treat disclosure as permanent and use normal corrective commits.

**P2 — Source ownership and technical rename — 3–5 days**

Owner: application engineer.  
Repository: `shadow-sync`; Skills source remains frozen.

- Import modules/resources/tests; perform every rename family.
- Add explicit legacy readers and automated identity completion checks.
- Establish standalone release/provenance contracts and packaging project.
- Preserve behavior and open UAT.

**Exit:** renamed source builds, executes runtime suites and has no unintended active old identity.  
**Recovery:** ordinary source revert; installed build 14 remains untouched/stopped.

**P3 — Governance and operating CI — 3–5 days**

Owner: release engineer and repository administrator.  
Repository: `shadow-sync`; dev exception must be accepted.

- Add the substantive jobs, suite receipts, aggregate gate and negative automation tests.
- Configure rulesets, reviewer App, release environment, immutable releases and dependency maintenance.
- Exercise a ready ordinary PR through exact-head verification, App approval and native squash merge.
- Verify failed/missing/skipped coverage and protected-path changes remain blocked.

**Exit:** CI and ordinary PR delivery proven operational, not merely checked in.  
**Recovery:** fix/revert through the protected administration path; do not bypass failed gates.

**P4 — External safety prerequisites — independently owned; estimate excluded**

Owners: controller maintainer, AWA release owner, Skills binding owner, dev policy owner.

- Rebuild maintenance-base support from current controller `main`, then deploy and verify it.
- Establish/enroll the governed maintenance branch and release exact AWA v1.8.2.
- Update Skills’ exact AWA pin and regenerate lockkit output.
- Install/verify the exact runtime through its authorized process.
- Merge/deploy dev’s authorized concrete policy and compatibility binding.
- Keep the app stopped until a compatible ShadowSync consumer is ready.

**Exit:** exact release/pin/runtime/policy evidence satisfies the frozen downstream gates.  
**Recovery:** owner-governed release recovery; do not remove hard-no-touch policy to accommodate an old application.

**P5 — Policy consumer and compatibility — 2–4 days**

Owner: application engineer with AWA contract owner.  
Repositories: `shadow-sync`, AWA contract tests, dev compatibility manifest.

- Implement the typed adapter to the pinned AWA matcher.
- Apply classification before candidate metadata access, authority changes, selection hydration and every later admission.
- Preserve visible disabled protected rows and fail-closed behavior.
- Test real pinned-module parity and synthetic protected roots.

**Exit:** zero-target-access evidence on every refusal path; deployed-policy binding verified.  
**Recovery:** stop application operations on incompatibility; no Swift fallback matcher.

**P6 — Signed setup, migration and recovery coordinator — 6–9 days**

Owner: macOS application architect.  
Repository: `shadow-sync`.

- Implement source-free installation, transactional identity migration, retained-lock handoff, journal recovery and publisher verification.
- Adapt bundle validation for sealed nested framework topology.
- Exercise fresh install, exact build-14 migration, conflicts, malformed data, interruption at every phase, retry and stopped rollback.
- Prove readiness under denied repository/network access.

**Exit:** isolated fault matrix passes without data loss, split locks or dual hosts.  
**Recovery:** signed coordinator recovery from the DMG; no destructive reset.

**P7 — Sparkle and release pipeline — 4–6 days**

Owner: release engineer and application engineer.  
Repository: `shadow-sync`.

- Integrate the pinned Sparkle framework and new key.
- Implement coordinator-gated replacement and release-bound readiness.
- Add signed packaging, notarization, provenance, immutable release and feed-proposal workflows.
- Exercise invalid signatures, wrong publisher, stale builds, failed replacement, coordinator death and update retry.

**Exit:** credential readiness and complete candidate pipeline proven, with no source-installer dependency.  
**Recovery:** retain prior feed/installation; repair through signed artifacts or a higher corrective build.

**P8 — Signed candidates and native qualification — 3–5 days plus UAT time**

Owner: release engineer; operator owns physical/UAT acceptance.

- Produce build 15, then build 16 from exact merged revisions.
- Test clean quarantined installation without Skills/source/compiler.
- Test legacy migration, new Login Item opt-in, logout/login, duplicate launches, managed-host routing and physical UI behavior.
- Prove installed Sparkle 15→16, preserved authority/selections/logs, no operation overlap and supported recovery.
- Verify minimum macOS 26.0 and the current supported macOS 26 host; hosted CI on a later point release alone does not establish the minimum.

**Exit:** signed release and installed migration/update milestones evidenced separately.  
**Recovery:** keep promotion frozen and ship a new corrective candidate; UAT stays open.

**P9 — Skills/orchestrator cutover and legacy retirement — 2–3 days plus compatibility window**

Owners: Skills and orchestrator maintainers; release engineer verifies installation.

- Replace frozen Skills implementation with the discovery-only descriptor.
- Rename the excluded registry entry and regenerate locks through lockkit.
- Update active consumers and documentation pointers.
- Disable legacy production installation before live migration; retain only the bounded compatibility wrapper.
- After verified migration/update and the retirement window, remove the wrapper and old machine registrations/residue through the explicit retirement procedure.

**Exit:** one implementation owner, one production update authority, one active identity, and no unintended active old references.  
**Recovery:** revert metadata handoff if necessary; never reactivate unsafe build 14 automatically.

Planning estimate: **approximately 26–42 engineering days**, excluding controller/AWA external waiting, credential administration and operator UAT. This assumes reuse of the existing runtime/test architecture and one application engineer with release-engineering support. Packaging/CI and synthetic policy work can run in separate worktrees; overlapping lifecycle/lock changes must remain serialized under one writer.

### Requirements-to-verification matrix

| Requirements and owner | Dependencies | Required positive and negative evidence | Completion gate |
|---|---|---|---|
| **EX-01–04:** public export, ownership, licensing, complete rename — architect/Skills owner | P0–P2 | Per-file provenance; export/secret review; no private-history import; new identity in source, resources, symbols and artifacts; only documented legacy exceptions; registry/lock parity. | Source extraction and ownership handoff accepted. |
| **GV-01–04:** governance, free CI, App delivery, credential separation — release engineer/admin | Accepted dev exception, P3 | Settings read-back; exact-head successful PR; stale approval, changed head, missing check, untrusted PR and protected-path refusals; no privileged token in PR execution; zero-paid-usage controls. | Governance active and CI/App behavior exercised. |
| **SF-01–05:** Git safety, policy rejection, cancellation, cleanup and concurrency — application/AWA/dev owners | P4–P5; existing safety suites | Dirty/diverged/wrong-origin/default-claim/hook/ref-race refusals; no target access before policy acceptance; malformed/missing policy; cancellation at admission and execution; all children reaped; lock contention and surviving-lease tests. | Safety dependency chain and substantive suites pass. |
| **MG-01–06:** install, migration, state preservation, startup, update and rollback — macOS architect | P6–P7, safety chain | Fresh install; same-inode transition; simultaneous old/new attempts; malformed/newer state; every transaction fault cut; retry; failed replacement; coordinator death; no-source setup; Login Item removal/new opt-in; preserved authority/selections/logs; 15→16 installed update. | Native migration/update receipt; legacy host never overlaps. |
| **RL-01–05:** signing, distribution, feed integrity, recovery and acceptance — release engineer/operator | P7–P9 | Production test-seam exclusion; Developer ID/nested-code/timestamp/entitlement checks; notarization/stapling/Gatekeeper; wrong-key/tampered ZIP refusal; immutable assets; channel rollback; physical-input/UI evidence and explicit UAT decision. | Signed release, promotion, retirement and UAT recorded separately. |

### Separate definitions of completion

- **Source extraction complete:** reviewed public source/provenance exists, renamed code passes substantive verification, and new repository owns further implementation.
- **Repository governance complete:** accepted exception, rulesets, App, protected environment, security settings and administration procedures are active and read back.
- **CI operational:** mandatory runtime coverage and negative aggregate-gate behavior have executed successfully on exact revisions.
- **Signed release complete:** distributed bytes are Developer ID signed, notarized, stapled, immutable and traceable. Credential readiness alone is insufficient.
- **Installed migration/update complete:** preserved-state build-14→15 migration and signed build-15→16 update pass native verification.
- **Legacy retirement complete:** old launch/installation routes, active state namespace, registry identity and temporary compatibility wrappers are gone under the retirement gate.
- **UAT accepted:** the operator explicitly closes the round against the recorded criteria. Merge, installation, screenshots and isolated observations do not imply acceptance.

### Recorded execution authorization

The **public repository, proprietary licensing and free hosted CI choices are already settled**.

The owner’s acceptance approves these architectural and execution decisions:

1. Sanitized snapshot extraction into `~/dev/personal/shadow-sync`, with private Skills history retained.
2. Permanent `com.kleinperkins.shadow-sync` identity and bounded legacy compatibility.
3. Managed-host preservation, signed source-free lifecycle coordinator, and coordinator-gated Sparkle updates.
4. The narrow ShadowSync-only native GitHub Actions/App exception.
5. macOS 26 arm64 support, first candidates `0.10.0 (15)` and `0.10.1 (16)`, and protected beta/stable feeds.
6. The AWA-owned adoption of the existing pinned classifier API and the explicit installed-safety dependency gates.
7. The phase sequence, technical review requirements, and distinct release/retirement/UAT approvals.

Acceptance does not declare the external safety prerequisites satisfied or authorize a release/install before its stated gates. Implementation had not begun at the time this package was submitted for acceptance.
