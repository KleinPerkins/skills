# ShadowSync — exact Lucide draft-pull-request glyph plan

**Version:** v7
**Status:** ACCEPTED — 2026-09-18
**Date:** 2026-09-18
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Supersedes:** [ShadowSync final release closure plan v6](dev-main-sync-global-capability-v6.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Implementation baseline:** clean revision `086c83a87dc09d135f31d29f1f4965dcf5c1880b`
on branch `feat/dev-main-sync-v3-selection-first`
**Frozen predecessors:** v2 SHA-256
`36fc11c68601de2d1874c8e7aed648c9be186cf82cbeca8e65c14af26eae64f4`;
v3 SHA-256 `52f51c621a87bf986f36a87398e2f660dc06c30bd5380c6a6bf8df01875f9dbd`;
v4 SHA-256 `b347ef15a201434b823d07aa04593e729f4082611da8aec7047e563ef4bf7ac2`;
v5 SHA-256 `9073bb8c2110ab259dd03634ece66d5d7f2f93448d3eb7921dd00455bc085627`;
v6 SHA-256 `650448daf0563d888950e9414912cdf11d0a3ba68c5391e6867aa7fc2403c534`
**Review provenance:** the operator attached screenshot SHA-256
`6ab37cccd8101b2b984965638fc4dc375caa1882c50e815f09370890d68c7555`, selected glyph
number 8 left-to-right, and required exact upstream geometry rather than an interpretation.

> **For agentic implementers:** execute the two work items below in order. Never edit this
> accepted plan to record progress; preserve receipts separately.

**Goal:** Replace only ShadowSync's paired-orbit foreground mark with the exact operator-selected
Lucide draft-pull-request geometry, while preserving the Phase Tiles base and every inherited
product, migration, safety, compatibility, valid-host, review, and delivery contract.

**Architecture:** Keep the committed 1024px master as production artwork and the existing
deterministic copy-only ICNS pipeline. Rebuild the artwork from the clean unmarked Phase Tiles base,
overlay one source-pinned Lucide path at a bounded optical scale, record the required ISC notice,
then close the unchanged v6 valid-host and governed-delivery work.

**Tech stack:** Swift 6.2/AppKit/SwiftPM, dependency-free deterministic PNG/ICNS tooling, macOS
`sips`/`iconutil`, isolated owner-private fixtures, and runnerless GitHub PR automation.

---

## Global Constraints

- Every v6/v5/v4/v3/v2 requirement, acceptance row, test, prohibition, migration/rollback rule,
  stable identifier, and delivery gate remains release-blocking except the foreground glyph.
- Change no squircle, Phase Tile, gradient, shadow, position, scale, product code, lifecycle,
  selection, Git behavior, state, schema, identifier, threshold, fixture size, timeout, or test
  strength.
- Add no package/runtime dependency. Do not ship an SVG; pin its canonical bytes, primitives,
  revision, URL, digest, and ISC notice in source-controlled provenance.
- No feature-branch install, real target-repository mutation, push/PR/merge during icon
  implementation, agent-armed auto-merge, paid runner, system remediation, or cache manipulation.
- Do not run M1, M2 performance, or full M6 until three naturally observed valid-host samples.
  Never wait or poll for idle, alter processes, or relabel hostile-host evidence.

## 1. Exact source identification

Choice #8 is Lucide's `git-pull-request-draft`, confirmed with high confidence:

- project: [Lucide](https://github.com/lucide-icons/lucide);
- release: `1.47.0`, tag commit
  `3b9ea6d08707edc439f25a4c354cb0d6b8bee973`;
- source:
  `https://github.com/lucide-icons/lucide/blob/3b9ea6d08707edc439f25a4c354cb0d6b8bee973/icons/git-pull-request-draft.svg`;
- canonical SVG SHA-256:
  `8451a55443bc5560d1654a6c389984a2077775a9ffa372d75ad1dc865491dc9f`;
- last glyph-changing commit:
  `f620c85e3b8ecb7c9089de19df7e7b7ff3863efd`;
- license: ISC, canonical `LICENSE` SHA-256
  `b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57`.

The geometry is exact:

```xml
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="18" cy="18" r="3" />
  <circle cx="6" cy="6" r="3" />
  <path d="M18 6V5" />
  <path d="M18 11v-1" />
  <line x1="6" x2="6" y1="9" y2="21" />
</svg>
```

The screenshot's neighboring standard/closed/create/arrow pull-request glyphs and #8's open
lower-left stem, two separated upper-right dash segments, top-left node, and lower-right node match
this Lucide family. Primer Octicons is rejected: its filled-path candidate has a lower-left node
that is absent from screenshot choice #8.

`git-pull-request-draft` is not listed among Lucide's Feather-derived icons, so the Lucide ISC
terms apply. The notice must reproduce the ISC copyright, permission, and disclaimer text.

## 2. Exact visual contract

Restore the original unmarked Phase Tiles option C:

- unchanged midnight macOS squircle;
- unchanged rear violet tile;
- unchanged front cyan tile;
- unchanged gradients, shadows, corner radii, bounds, positions, and scale;
- motif bounds `(224,328)–(799,731)` and 21.9% minimum canvas margin.

Overlay the exact source geometry with its 24×24 ratios, 2-unit stroke, round caps/joins, open
lower-left stem, two solid short segments that create the dotted upper-right stem, and both circular
nodes. Only stroke color/opacity may adapt to the palette. Use pale ice/cyan with sufficient contrast
on the front tile; do not add a plate, fill, glow that changes geometry, shadow that changes the
visible stroke ratios, or any extra mark.

Target a visible glyph width of `198px` over the front tile's `430px` width: 46.0%, within the
operator-approved 45–47% band. Center the source geometry optically on the front tile. Record final
integer raster bounds and actual ratio after antialiasing; any adjustment must stay inside 45–47%
and may only correct raster centering, not source geometry.

## 3. Implemented baseline and unchanged release contract

The superseded paired-orbit master at
`4c06e465e6ef38d1a84dd229ad5b27ba6af02fe1` has SHA-256
`e4988907fa05ababe3c0b03e8820647a35def13cab44e50e96710a75f24c5ef2`; its ICNS has SHA-256
`a9f19db0e6f29ac63676fdc4874db1e6d0d97c85dc5a158a409109a2167274ee`.
Use it only as before/after evidence and to verify unchanged pixels outside the old overlay bounds
`(488,489)–(681,655)`. Do not use its paired-orbit pixels as the new base.

ShadowSync remains the operator-visible app/package/product/executable and Swift identity.
`com.kleinperkins.dev-main-sync`, its one launchd label/plist, `~/.local/state/dev-main-sync`,
`DevMainSync*` release keys, `dev-main-sync-*` wires/schemas, `devMainSync.*` Git markers,
capability ID/path, registry identity, one state/socket/job/router, dual-generation lifecycle,
cooperative drain, paired rollback, no-overlap, and last-known-good preservation remain exact.

## 4. Acceptance boundary

The icon change must pass exact-source provenance/license, clean-base pixel preservation,
master/ICNS determinism, 1024/128/32/16 light/dark review, `DM4-T03/T04/T11`, signed bundle
inventory/source attestation, two-build normalization, full v4/DM4 preflight, owner verification,
and clean fixture/process audits. M1, M2 performance, full M6, Draft PR, reviews, merge, and
exact-main installation remain open afterward.

## 5. Work items

### Task 1: Replace the foreground glyph exactly

**Files:**

- Create: `global/tools/dev-main-sync/THIRD_PARTY_NOTICES.md`
- Modify: `global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png`
- Modify: `global/tools/dev-main-sync/Resources/ShadowSync.icns`
- Modify: `global/tools/dev-main-sync/scripts/generate-icon.sh`
- Modify: `global/tools/dev-main-sync/Sources/ShadowSyncCore/DM4PreflightSelfTests.swift`
- Modify: `global/tools/dev-main-sync/README.md`
- Test: `global/tools/dev-main-sync/scripts/v4-preflight-acceptance.sh`
- Test: `.github/scripts/verify-skills.sh`

**Interfaces:**

- Consumes: screenshot choice #8 digest, Lucide `git-pull-request-draft` release/source/license
  pins from §1, clean Phase Tiles option C geometry from §2, the current committed-master input and
  copy-only production ICNS pipeline, `DM4-T03/T04/T11`, bundle inventory/source attestation, and
  existing reproducibility normalization.
- Produces: clean-base PNG evidence, exact Lucide-geometry raster evidence, final master/ICNS
  SHA-256 values, ISC notice and source pin, affected DM4 receipts, signed-bundle/attestation
  receipt, two-build normalization receipt, full v4 preflight, owner verification, and one final
  light/dark comparison preview.

- [ ] **Step 1 — Reconfirm canonical source bytes and license**

```bash
GH="$(command -v gh)"
COMMIT=3b9ea6d08707edc439f25a4c354cb0d6b8bee973
"$GH" api \
  "repos/lucide-icons/lucide/contents/icons/git-pull-request-draft.svg?ref=$COMMIT" \
  --jq .content | /usr/bin/base64 --decode | shasum -a 256
"$GH" api \
  "repos/lucide-icons/lucide/contents/LICENSE?ref=$COMMIT" \
  --jq .content | /usr/bin/base64 --decode | shasum -a 256
```

Expected: SVG `8451a55443bc5560d1654a6c389984a2077775a9ffa372d75ad1dc865491dc9f`;
license `b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57`.

- [ ] **Step 2 — Restore and verify clean Phase Tiles base**

Recover the trusted original option-C artifact when available. Otherwise reconstruct it
deterministically from the established squircle/tile bounds, radii, gradients, shadows, and
unchanged pixels surrounding the old overlay. Never copy, blur, inpaint, or retain paired-orbit
pixels inside `(488,489)–(681,655)`.

```bash
python3 scripts/verify-icon-base.py \
  --base /private/tmp/shadowsync-v7-base-c.png \
  --prior Resources/ShadowSyncIcon-1024.png \
  --allowed-prior-overlay 488,489,681,655
```

Expected: base dimensions/alpha/motif bounds pass; every pixel outside the allowed old-overlay
rectangle equals the paired-orbit baseline; the rectangle contains only the deterministic
continuation of the original front-tile gradient and no old foreground mark. Keep
`verify-icon-base.py` only if required for reproducible proof; otherwise include the equivalent
bounded verification in the existing generator and commit no redundant helper.

- [ ] **Step 3 — Render exact Lucide geometry**

Map the 24-unit viewBox uniformly to a 198px visible stroke envelope, preserving all coordinates,
2-unit relative stroke width, circles, separated path segments, line, round caps, and round joins.
Center the visible envelope on the front tile and use only one fixed pale ice/cyan stroke treatment.

```bash
python3 scripts/verify-icon-provenance.py \
  --source-sha256 8451a55443bc5560d1654a6c389984a2077775a9ffa372d75ad1dc865491dc9f \
  --base /private/tmp/shadowsync-v7-base-c.png \
  --output Resources/ShadowSyncIcon-1024.png \
  --target-width 198
```

Expected: exact primitive/ratio/cap/join checks pass; measured width is 45–47% of 430px; only pixels
inside the reported new overlay bounds differ from clean C. As in Step 2, integrate this proof into
the existing generator instead of committing a separate helper when that is simpler.

- [ ] **Step 4 — Add minimum provenance and regenerate ICNS**

Create `THIRD_PARTY_NOTICES.md` with the exact project, icon, release/tag commit, source URL, source
digest, license digest, unmodified geometry statement, color/opacity adaptation statement, and full
Lucide ISC notice. Do not claim the glyph is original.

```bash
./scripts/generate-icon.sh --write
./scripts/generate-icon.sh --check
```

Expected: two independent generations are byte-identical; the committed master and ICNS equal
new pinned hashes; production remains copy-only; source and bundle attestation include the notice.

- [ ] **Step 5 — Verify sizes, pixels, bundle, tests, and preview**

```bash
# Extract and inspect 1024/128/32/16 representations on light and dark backgrounds.
# Run the existing focused selectors for DM4-T03, DM4-T04, and DM4-T11.
./scripts/v4-preflight-acceptance.sh
cd ../../..
bash .github/scripts/verify-skills.sh
```

Expected: exact-source/license/base-pixel audits pass; details remain legible at 32px and 16px;
signed bundle plist/resource/inventory/source attestation and two fresh build normalization pass;
`DM4-T01–T12`, v4 preflight, and owner verifier pass. Preserve one final comparison showing
unmarked C, paired-orbit predecessor, and choice #8 at 256/128/32/16 on light/dark backgrounds.

- [ ] **Step 6 — Commit the verified asset body**

```bash
DEV_SESSION_ID=dev-main-sync-v3-impl-20260912 git add \
  global/tools/dev-main-sync/THIRD_PARTY_NOTICES.md \
  global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png \
  global/tools/dev-main-sync/Resources/ShadowSync.icns \
  global/tools/dev-main-sync/scripts/generate-icon.sh \
  global/tools/dev-main-sync/Sources/ShadowSyncCore/DM4PreflightSelfTests.swift \
  global/tools/dev-main-sync/README.md
DEV_SESSION_ID=dev-main-sync-v3-impl-20260912 \
  git commit -m "feat(shadowsync): adopt exact Lucide draft glyph"
```

Expected: one normal commit, no amend/rewrite, no unplanned file, and a clean worktree with no owned
process/fixture/scratch except the explicit final preview.

**Definition of done:** the exact source-pinned Lucide geometry replaces only the prior foreground
mark; clean C is otherwise byte-preserved; notice/license obligations are met without a runtime
dependency; all icon, bundle, attestation, normalization, DM4, v4, and owner gates pass; one preview
and complete hashes/bounds/ratio/receipts remain; no product/lifecycle behavior changed.

### Task 2: Close valid-host evidence and governed delivery

**Files:**

- Read/execute: `global/tools/dev-main-sync/scripts/verify-m1.sh`
- Read/execute: `global/tools/dev-main-sync/scripts/build-app.sh`
- Read/execute: `global/tools/dev-main-sync/Tests/ShadowSyncSelfTests/main.swift`
- Read/execute: `global/tools/dev-main-sync/scripts/verify-m6.sh`
- Read/execute after merge: `global/tools/dev-main-sync/install.sh`
- Modify: no repository file; use existing governed command/PR/merge/install receipt sinks.

**Interfaces:**

- Consumes: clean exact icon-implementation `HEAD`, three naturally valid idle samples, existing
  `--m2-performance-only`, runnerless `pr-automation / verify`, clean Bugbot/security reviews,
  explicit operator GO, reviewer-App merge, and the dual-generation lifecycle installer.
- Produces: same-head M1/M2/M6 receipts, one Draft PR URL/reviewed head, reviewer-App merge revision,
  clean `main == origin/main`, exact-main install/doctor receipts, physical acceptance, and final
  cleanup.

- [ ] **Step 1 — Run valid-host M1, M2, and M6 sequentially**

After three naturally valid samples, record one clean `TESTED_HEAD`; run
`./scripts/verify-m1.sh`, then a fresh private-root `ShadowSyncSelfTest
--m2-performance-only`, then `./scripts/verify-m6.sh`. Require all three receipts to name
`TESTED_HEAD`; remove each fixture before the next gate.

- [ ] **Step 2 — Open one Draft PR and clear reviews**

```bash
gh pr create \
  --draft \
  --base main \
  --head feat/dev-main-sync-v3-selection-first \
  --title "feat: ship ShadowSync" \
  --body "Implements the accepted ShadowSync v7 plan."
```

Expected: exact-head runnerless verification passes; Bugbot and security review have no material
finding; the PR remains Draft and unarmed until explicit operator GO.

- [ ] **Step 3 — Merge only through governed automation**

Present exact head, receipts, provenance/license, hashes, bounds, migration ledger, reviews, and
residual uncertainty. After explicit operator GO, mark the unchanged PR ready. The reviewer App
alone approves and arms merge. Never call `gh pr merge --auto`, direct-merge, bypass checks, or add
a runner.

- [ ] **Step 4 — Verify and install exact main**

From a clean durable primary with `main == origin/main`, rerun source/icon/v4/v3/v2/M1/M5/M6,
owner, and doc-warden gates before `global/tools/dev-main-sync/install.sh --apply`; then run
`install.sh --doctor` and physical icon/menu/hotkey/chooser/selected-no-op/cancel/Quit acceptance
without mutating a real repository.

**Definition of done:** valid-host M1/M2/M6 pass at one exact head; one reviewed Draft PR merges only
through the reviewer App after explicit GO; exact clean main alone is installed; doctor, physical
acceptance, state preservation, process/residue census, provenance, and cleanup all pass.

## 6. Acceptance criteria

- `V7-AT-01`: exact Lucide source identity, revision, primitives, digest, and ISC notice are pinned.
- `V7-AT-02`: clean Phase Tiles C is unchanged outside the measured choice-8 overlay.
- `V7-AT-03`: glyph geometry/caps/joins/nodes/dashes match upstream exactly at 45–47% tile width.
- `V7-AT-04`: master/ICNS determinism, sizes, attestation, signed bundle, normalization, DM4, v4,
  owner, and preview gates pass.
- `V7-AT-05`: all v6/v5/v4/v3/v2 non-glyph contracts and frozen plan bytes remain unchanged.
- `V7-AT-06`: valid-host M1/M2/M6 and governed Draft-PR-to-exact-main delivery remain mandatory.

## 7. Rollback

Before merge, leave or close the PR Draft and do not install. After merge, use only the existing
dual-generation-aware repair/rollback and retained-state semantics. Never manually delete an app,
plist, state tree, socket, transaction slot, or process; preserve recoverable bytes and fail closed
when ownership/readiness cannot be proven.

**APPROVED — ShadowSync v7 exact Lucide draft-pull-request glyph plan**
