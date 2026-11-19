# ShadowSync — final release closure plan

**Version:** v6
**Status:** ACCEPTED — 2026-09-18
**Date:** 2026-09-18
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Supersedes:** [ShadowSync operator-selected Phase Tiles icon plan v5](dev-main-sync-global-capability-v5.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Implementation baseline:** clean revision `4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1`
on branch `feat/dev-main-sync-v3-selection-first`
**Frozen predecessors:** v2 SHA-256
`36fc11c68601de2d1874c8e7aed648c9be186cf82cbeca8e65c14af26eae64f4`;
v3 SHA-256 `52f51c621a87bf986f36a87398e2f660dc06c30bd5380c6a6bf8df01875f9dbd`;
v4 SHA-256 `b347ef15a201434b823d07aa04593e729f4082611da8aec7047e563ef4bf7ac2`;
v5 SHA-256 `9073bb8c2110ab259dd03634ece66d5d7f2f93448d3eb7921dd00455bc085627`
**Review provenance:** the operator explicitly authorized this immutable successor to correct
v5's missing agentic task-block structure without changing the accepted product or icon.

> **For agentic implementers:** execute the one work item below from its complete block. Never edit
> this accepted plan to record progress; preserve receipts separately.

**Goal:** Close ShadowSync's remaining valid-host and governed-delivery gates without changing the
implemented product, selected icon, tests, thresholds, lifecycle, or compatibility contract.

**Architecture:** Treat revision `4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1` as the completed
product baseline. Obtain the three missing valid-host receipts at one exact branch head, then use
the existing Draft-PR, review, reviewer-App merge, exact-main verification, and installed-app
handoff path from v4.

**Tech stack:** existing Swift 6.2/AppKit/SwiftPM verification scripts, isolated owner-private
fixtures, runnerless GitHub PR automation, and the existing source-built lifecycle installer.

---

## Global Constraints

- Every v5/v4/v3/v2 requirement, acceptance row, test, prohibition, migration/rollback rule,
  stable identifier, and delivery gate remains release-blocking and unchanged.
- Do not modify product code, icon bytes, tests, scripts, lifecycle/selection/Git behavior,
  thresholds, fixture sizes, assertions, timeouts, state, schemas, identifiers, or accepted plans.
- Do not run host-sensitive gates until three naturally observed samples satisfy the inherited
  valid-host criteria. Never wait, poll, alter processes, weaken criteria, or label hostile-host
  evidence as passing.
- Run M1, M2 performance, and full M6 sequentially, never concurrently. Reap every owned process
  and remove every isolated fixture after each command.
- No feature-branch install, real target-repository mutation, direct merge, agent-armed auto-merge,
  bypassed check, paid/self-hosted runner, new dependency, system remediation, or cache manipulation.
- Only explicit operator GO permits Ready for Review. The reviewer App alone approves and arms the
  governed merge.

## 1. Purpose

v5 correctly froze and implemented the operator-selected icon but omitted doc-warden's required
agentic work-item shape. This successor repairs only that governance structure and records the
remaining release work in one zero-context block.

## 2. Frozen product and visual contract

Icon adoption is implemented at
`4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1`:

- master `global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png`, SHA-256
  `e4988907fa05ababe3c0b03e8820647a35def13cab44e50e96710a75f24c5ef2`;
- packaged `global/tools/dev-main-sync/Resources/ShadowSync.icns`, SHA-256
  `a9f19db0e6f29ac63676fdc4874db1e6d0d97c85dc5a158a409109a2167274ee`;
- unchanged midnight macOS squircle, rear violet Phase Tile, and front cyan Phase Tile;
- one custom pale-cyan paired-orbit glyph centered on the front tile, bounds
  `(488,489)–(681,655)`, width `194px`, exactly 45.1% of the front tile;
- zero base Phase Tiles RGBA differences outside those overlay bounds and 21.9% motif margin; and
- no text, third-party mark, badge plate, extra tile/layer, generic standalone arrow icon, or other
  composition change.

Exact-head focused icon, signed-bundle/attestation, two-build normalization, `DM4-T01–T12`, v4
preflight, and owner verification receipts already pass at that implementation revision. A
documentation-only v6 commit does not invalidate those source-dependent receipts.

## 3. Preserved application contract

ShadowSync remains the operator-visible app/package/product/executable and Swift implementation
identity. The existing `com.kleinperkins.dev-main-sync` bundle/codesign ID and launchd label/plist,
`~/.local/state/dev-main-sync`, `DevMainSync*` release metadata keys, `dev-main-sync-*` wire/schema
values, `devMainSync.*` Git markers, capability ID/path, registry identity, one state/socket/job/
router, and explicit predecessor literals remain byte-compatible. The verified dual-generation
handoff, cooperative drain, paired rollback, no-overlap, repair/doctor/rollback/uninstall, and
last-known-good preservation contracts remain exact.

## 4. Remaining release boundary

Only these outcomes remain:

1. valid-host M1's unchanged `<5s` 100-repository gate;
2. valid-host M2's unchanged 100-candidate performance selector;
3. full M6 including delayed-host readiness and lifecycle/reproducibility closure;
4. one governed Draft PR, clean exact-head checks and reviews, explicit operator GO, reviewer-App
   merge, and exact-main installation/doctor/physical acceptance.

## 5. Work items

### Task 1: Obtain valid-host evidence and deliver exact main

**Files:**

- Read/execute: `global/tools/dev-main-sync/scripts/verify-m1.sh`
- Read/execute: `global/tools/dev-main-sync/scripts/build-app.sh`
- Read/execute: `global/tools/dev-main-sync/Tests/ShadowSyncSelfTests/main.swift`
- Read/execute: `global/tools/dev-main-sync/scripts/verify-m6.sh`
- Read/execute: `global/tools/dev-main-sync/scripts/v4-preflight-acceptance.sh`
- Read/execute after merge: `global/tools/dev-main-sync/install.sh`
- Verify unchanged: `global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png`
- Verify unchanged: `global/tools/dev-main-sync/Resources/ShadowSync.icns`
- Modify: no repository file; store command, PR, merge, install, and doctor receipts outside frozen
  plan bytes through the existing governed delivery record.

**Interfaces:**

- Consumes: one clean exact branch `HEAD` containing product baseline
  `4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1`, three naturally valid idle samples, the existing
  `ShadowSyncSelfTest --m2-performance-only` selector, runnerless `pr-automation / verify`,
  Bugbot/security review, explicit operator GO, and the existing lifecycle installer.
- Produces: exact-head M1/M2/M6 receipts, one Draft PR URL and immutable tested head, clean review
  disposition, reviewer-App merge revision, clean `main == origin/main` proof, exact-main install
  source/bundle/icon identities, doctor output, and final physical acceptance.

- [ ] **Step 1 — Freeze one valid exact branch head**

Run only after three naturally observed samples satisfy the inherited host criteria:

```bash
cd global/tools/dev-main-sync
test -z "$(git status --porcelain)"
TESTED_HEAD="$(git rev-parse HEAD)"
git merge-base --is-ancestor \
  4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1 "$TESTED_HEAD"
```

Expected: clean branch head containing the exact completed icon implementation. Record
`TESTED_HEAD` and all three host samples. Do not manufacture samples or continue after an invalid
sample.

- [ ] **Step 2 — Run M1 and M2 sequentially**

Run M1 first:

```bash
./scripts/verify-m1.sh
```

Expected: PASS including the unchanged `<5s` 100-repository gate.

Then run the exact M2 performance selector in a fresh private root:

```bash
ROOT="$(mktemp -d /private/tmp/shadowsync-v6-m2.XXXXXX)"
trap 'rm -rf "$ROOT"' EXIT
./scripts/build-app.sh \
  --scratch-path "$ROOT/swift" \
  --output-dir "$ROOT/output" \
  --testing
swift build \
  --package-path . \
  --scratch-path "$ROOT/swift" \
  --configuration release \
  --product ShadowSyncSelfTest \
  --disable-index-store \
  -Xswiftc -DSHADOW_SYNC_TESTING
BIN="$(swift build \
  --package-path . \
  --scratch-path "$ROOT/swift" \
  --configuration release \
  --product ShadowSyncSelfTest \
  --disable-index-store \
  -Xswiftc -DSHADOW_SYNC_TESTING \
  --show-bin-path)"
"$BIN/ShadowSyncSelfTest" \
  --app-executable "$ROOT/output/ShadowSync.app/Contents/MacOS/ShadowSync" \
  --m2-performance-only
rm -rf "$ROOT"
trap - EXIT
```

Expected: PASS including `m2-hundred-candidate-discovery-budget`; no owned helper or fixture
remains.

- [ ] **Step 3 — Run full M6 at the same exact head**

```bash
./scripts/verify-m6.sh
test "$(git rev-parse HEAD)" = "$TESTED_HEAD"
test -z "$(git status --porcelain)"
```

Expected: PASS including delayed-host readiness, lifecycle fault cuts, source/bundle attestation,
and repeated-build normalization. M1, M2, and M6 receipts name the same `TESTED_HEAD`.

- [ ] **Step 4 — Open and review one Draft PR**

```bash
cd "$(git rev-parse --show-toplevel)"
gh pr create \
  --draft \
  --base main \
  --head feat/dev-main-sync-v3-selection-first \
  --title "feat: ship ShadowSync" \
  --body "Implements the accepted ShadowSync v6 release closure plan."
```

Expected: one Draft PR at exact `TESTED_HEAD`. Require runnerless `pr-automation / verify` PASS;
run Bugbot and security review until no material finding remains; rerun dependency-mapped checks
after any material source fix. Do not arm auto-merge or mark ready.

- [ ] **Step 5 — Cross the explicit GO and reviewer-App merge gates**

After presenting the exact head, all receipts, icon hashes, compatibility/migration ledger, review
disposition, and residual uncertainty, obtain explicit operator GO. Then mark the unchanged Draft
PR ready through the ordinary GitHub ready-for-review action.

Expected: the reviewer App alone approves and arms native governed merge at the exact reviewed head.
Do not call `gh pr merge --auto`, direct-merge, bypass checks, or alter merge automation. Record the
merged `origin/main` revision and confirm the feature branch is deleted through the governed path.

- [ ] **Step 6 — Verify and install exact main**

From the durable primary checkout after the governed merge:

```bash
git fetch origin main
test "$(git branch --show-current)" = "main"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
cd global/tools/dev-main-sync
./scripts/generate-icon.sh --check
./scripts/v4-preflight-acceptance.sh
./scripts/verify-m1.sh
./scripts/verify-m5.sh
./scripts/verify-m6.sh
cd ../../..
bash .github/scripts/verify-skills.sh
bash ~/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
cd global/tools/dev-main-sync
./install.sh --apply
./install.sh --doctor
```

Expected: every exact-main gate passes before installation; the installed app is the verified
`ShadowSync.app` with the pinned icon, one existing label/state/socket owner, preserved durable
state, no predecessor process/bundle or transaction residue, and successful menu/hotkey/chooser/
selected-no-op/cancel/Quit physical acceptance without mutating a real repository.

**Definition of done:** M1, M2 performance, and full M6 pass at one valid exact branch head; one
governed PR merges that exact reviewed product through the reviewer App after explicit operator GO;
clean exact `main == origin/main` passes all inherited gates; exact-main ShadowSync installation,
doctor, physical acceptance, state preservation, icon identity, process census, and cleanup all
pass; no paid runner, unpushed commit, open material review, owned process, or fixture remains.

## 6. Acceptance criteria

- `V6-AT-01`: v6 is structurally conformant and v2–v5 bytes remain frozen.
- `V6-AT-02`: the selected master and ICNS retain their pinned SHA-256 values and 45.1% glyph.
- `V6-AT-03`: valid-host M1, M2 performance, and full M6 pass at one exact branch head.
- `V6-AT-04`: all v5/v4/v3/v2 nonvisual and visual contracts remain unchanged.
- `V6-AT-05`: one Draft PR passes runnerless verification and clean reviews before explicit GO.
- `V6-AT-06`: the reviewer App alone governs merge; exact clean main alone is installed.
- `V6-AT-07`: post-install doctor and physical acceptance prove one ready ShadowSync owner,
  preserved state, correct icon, no predecessor/residue, and no real repository mutation.

## 7. Rollback

Before merge, leave the PR Draft or close it; do not install. After merge, use only the existing
dual-generation-aware `install.sh --repair`, lifecycle rollback, and retained-state semantics from
v4. Never manually delete an app, plist, state tree, socket, transaction slot, or process. If exact
ownership/readiness cannot be proven, preserve all recoverable bytes and fail closed.

**APPROVED — ShadowSync v6 final release closure plan**
