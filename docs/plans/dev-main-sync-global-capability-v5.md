# ShadowSync — operator-selected Phase Tiles icon plan

**Version:** v5
**Status:** ACCEPTED — 2026-09-17
**Date:** 2026-09-17
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** agentic-execution
**Supersedes:** [ShadowSync application identity, icon, and installed-app handoff plan v4](dev-main-sync-global-capability-v4.md)
**Linked decision:** [ADR 0004 — Make Dev Main Sync a repository lifecycle control center](../adr/0004-dev-main-sync-repository-lifecycle-control-center.md)
**Implementation baseline:** clean revision `7533e3c343f4d7d2ab23080b0cef9bcaa6fe414a`
on branch `feat/dev-main-sync-v3-selection-first`
**Frozen predecessors:** v2 SHA-256
`36fc11c68601de2d1874c8e7aed648c9be186cf82cbeca8e65c14af26eae64f4`;
v3 SHA-256 `52f51c621a87bf986f36a87398e2f660dc06c30bd5380c6a6bf8df01875f9dbd`;
v4 SHA-256 `b347ef15a201434b823d07aa04593e729f4082611da8aec7047e563ef4bf7ac2`
**Review state:** the operator selected the final G3 icon and explicitly authorized this accepted
successor and its implementation. These accepted bytes are frozen on creation.

> **For agentic implementers:** execute this plan in order. Never edit an accepted plan to record
> progress. Keep receipts outside the plan.

**Goal:** Replace only ShadowSync's v4 icon artwork with the operator-selected final Phase Tiles
design while preserving the complete v4/v3/v2 product, migration, safety, compatibility, testing,
valid-host, and governed-delivery contracts.

## 1. Authority and unchanged inherited contract

This v5 plan is the sole active authority. It supersedes v4 only because v4's icon composition is
incompatible with the later operator selection. Every v4 requirement, acceptance row, prohibition,
test, migration state, rollback rule, naming rule, stable identifier, and delivery gate remains
release-blocking except the visual artwork contract in v4 §5.1 and its corresponding visual
assertions. In particular:

- `V4-NAME`, `V4-MIG`, `V4-COMP`, `V4-LIFE`, `V4-TEST`, and `V4-GOV` remain unchanged;
- `V4-ICON-01–08`, `DM4-T03/T04/T11`, and `V4-AT-04/05/06/15` remain required with the v5 artwork;
- `DM4-T01–T12`, `DM3-T01–T16`, all retained v1/v2 suites, M1, M5, M6, owner verification,
  production/source/package/symbol/network/broad-route/secret audits, and doc-warden remain gates;
- the installed `Dev Main Sync.app` → `ShadowSync.app` handoff, one label/state/socket/router,
  fail-closed rollback, no-overlap, and last-known-good preservation are unchanged; and
- v4's immutable naming/compatibility matrix remains exact: bundle ID, launchd label/plist, state
  directory, wire schemas, `DevMainSync*` release keys, `devMainSync.*` Git markers, capability
  ID/path, registry identity, and predecessor literals do not change.

No lifecycle, selection, Git, process, timing, state, schema, updater, package dependency, Xcode
project, notarization, installation, remote, or cache-management work is authorized by this plan.
There is no feature-branch install, push, PR, merge, auto-merge, external mutation, real target
repository mutation, paid runner, or threshold/assertion weakening.

## 2. Exact selected visual contract

The final icon is one original full **Phase Tiles** composition:

1. Preserve the existing midnight macOS squircle exactly.
2. Preserve the existing rear violet Phase Tile exactly.
3. Preserve the existing front cyan Phase Tile exactly.
4. Add one custom pale-cyan paired-orbit synchronization glyph, centered on the front tile.
5. Set the glyph's horizontal bounds to 45.1% of the front tile width. The accepted 1024 master
   records glyph bounds `(488,489)–(681,655)`, inclusive width `194px`.
6. Preserve the verified total motif margin of 21.9%.

The paired orbits are a small foreground signifier inside the selected Phase Tiles identity. They
do not turn the icon into a standalone generic circular-arrow icon. There is no text, letter,
third-party mark, copied brand geometry, badge plate, extra tile/layer, extra background element,
or other composition change.

The selected master is pinned by these facts:

- PNG, 1024×1024, 8-bit RGBA, non-interlaced;
- SHA-256 `e4988907fa05ababe3c0b03e8820647a35def13cab44e50e96710a75f24c5ef2`;
- base Phase Tiles pixels have zero RGBA differences from option C outside the glyph overlay
  bounds; and
- the glyph remains clear at 32px and open/readable at 16px on light and dark backgrounds.

## 3. Deterministic asset and production contract

The governed assets remain:

```text
global/tools/dev-main-sync/Resources/ShadowSyncIcon-1024.png
global/tools/dev-main-sync/Resources/ShadowSync.icns
global/tools/dev-main-sync/scripts/generate-icon.sh
```

Replace the committed master with the exact pinned selected bytes. The generation script validates
that master as a regular, single-link, owner-readable 1024×1024 RGBA PNG; creates every required
16/32/128/256/512/1024 representation in fresh owner-private roots; builds `.icns`; generates twice
independently; and requires byte identity. Retain fixed absolute tools, file modes, path/link checks,
alpha/silhouette checks, the v4 safe-margin floor, and explicit `--check`/`--write` separation.

The selected master, not reconstructed geometry, is the source of truth. If the generator currently
draws v4 geometry, simplify it to validate and deterministically scale/package the committed master;
do not re-encode the selected 1024 bytes or add unnecessary geometry code or dependencies.

Production continues to copy stable committed `.icns` bytes before signing and never generates the
icon implicitly. `CFBundleIconFile`, bundle inventory, source-input attestation, source/resource
digest equality, strict codesign, all representations, and repeated-build normalization remain
mandatory. Update only icon hashes and assertions invalidated by the selected visual.

## 4. Implementation worklist

1. Verify the selected input's type, dimensions, ownership, mode, link count, alpha, and SHA-256.
2. Copy its bytes exactly to `Resources/ShadowSyncIcon-1024.png`.
3. Adapt `generate-icon.sh` narrowly to package the committed master deterministically; preserve all
   v4 safety and production-separation checks.
4. Explicitly regenerate `Resources/ShadowSync.icns` and pin the new master/ICNS hashes.
5. Update `DM4-T03/T04/T11`, README visual copy, and source/bundle attestation expectations only
   where the icon bytes or selected visual require it.
6. Inspect extracted 1024/128/32/16 representations on light and dark backgrounds and retain one
   final preview for handoff.
7. Commit implementation normally with hooks. Do not amend, rewrite, push, install, or deliver.

## 5. Required verification

Run focused proof first:

```bash
cd global/tools/dev-main-sync
./scripts/generate-icon.sh --check
# Verify master type/dimensions/alpha/margins and extracted 16/32/128/1024 representations.
# Run focused DM4-T03, DM4-T04, and DM4-T11 selectors.
# Build two fresh production bundles in independent roots and run existing normalization proof.
./scripts/v4-preflight-acceptance.sh
cd ../../..
bash .github/scripts/verify-skills.sh
bash ~/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
```

Required outcomes:

- exact selected master bytes and newly pinned `.icns` bytes;
- deterministic double generation;
- readable required sizes and unchanged v4 margin/path/mode/link constraints;
- plist/resource/inventory/codesign/source-input attestation and two-build normalization pass;
- affected `DM4-T03/T04/T11`, complete `DM4-T01–T12`, v4 preflight, and owner verifier pass;
- v2/v3/v4 hashes remain byte-identical;
- lifecycle, migration, selection, Git, process, and timing files remain unchanged unless an existing
  icon-only expectation is colocated there;
- no owned process, fixture, scratch, rejected design directory, or dirty worktree remains, except
  the explicit selected master/comparison preview retained for handoff.

Do not run M1, the M2 100-repository timing selector, or full M6 unless the host independently
provides three valid idle samples. Their unchanged valid-host evidence remains open and no visual
replacement may manufacture or weaken it.

## 6. v5 acceptance ledger

| ID | Release-blocking observable |
|---|---|
| `V5-AT-01` | Committed master exactly equals the operator-selected pinned PNG |
| `V5-AT-02` | Squircle and both Phase Tiles are unchanged outside the overlay bounds |
| `V5-AT-03` | One pale-cyan paired-orbit glyph is centered on the front tile at 45.1% width |
| `V5-AT-04` | No text, mark, plate, extra tile/layer, or other composition change exists |
| `V5-AT-05` | 16/32/128/1024 renders remain readable and satisfy retained margin/alpha checks |
| `V5-AT-06` | Independent generation produces identical `.icns` bytes |
| `V5-AT-07` | Signed production bundles contain and attest the exact new icon |
| `V5-AT-08` | Two fresh production builds pass existing reproducibility normalization |
| `V5-AT-09` | Affected DM4 tests, complete v4 preflight, and owner verifier pass |
| `V5-AT-10` | Every nonvisual v4/v3/v2 contract and open valid-host gate remains unchanged |

All rows are release-blocking. This local task may claim v5 icon implementation complete after all
environment-independent rows pass. It may not claim release-ready until inherited valid-host
`V4-AT-18` and the remaining governed review/merge/exact-main installation gates pass.

**APPROVED — ShadowSync v5 operator-selected Phase Tiles icon plan**
