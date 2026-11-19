# Context Efficiency E-05 — pin the qualified AWA v1.5.2 release

**Version:** v1
**Status:** ACCEPTED — 2026-08-17
**Date:** 2026-08-17
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Program milestone:** E-05, “Pin the qualified AWA release in Skills.”
**Plan-type:** standard
**Review provenance:** Authored from the accepted Context Efficiency Program v2, live Skills main after E-01/E-03, the current AWA Global Capability Binding (GCB), the WF1 lockkit/registry contracts, the Dev clean-room gate, and the published AWA v1.5.2 tag/release. The operator explicitly accepted this narrow planning step; no GCB pin, generated lock, installed runtime, client home, Dev overlay, or E-09 evidence changed while authoring it.

**Goal:** Move the Skills-owned AWA GCB from qualified release v1.5.1 to qualified release v1.5.2 at exact commit `a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3`, preserving the standalone-release boundary and proving the pinned source, contract digest, isolated install, metadata lock, idempotence, and rollback.

**Architecture:** Keep `global/tools/awa` as a global-scope, Flavor-2 `release-descriptor` for the independently released AWA Standalone System Package (SSP). Change only the release pointer and its generated metadata-lock row. The existing metadata-driven GCB installer clones the exact pin and delegates to AWA’s own installer; no AWA runtime bytes enter Skills. Existing Skills verification and Dev clean-room surfaces verify the candidate without becoming source authority.

---

## 1. Authority and exact dependency binding

Implementation is bound to:

| Authority | Exact binding | Required fact |
|---|---|---|
| Skills live main | `e9e54879008a42dafcd257f67547ac207dc26531` | E-03 merge; implementation rollback/source base |
| Skills E-01 | `2cd47ca8050aeba41409053883886c6e06f024b9` | Durable Skills source merged and ancestor of live main |
| Skills E-03 | `e9e54879008a42dafcd257f67547ac207dc26531` | Strict description eligibility merged |
| Context Efficiency Program v2 | `KleinPerkins/dev`, `_ops/plans/context-efficiency-program-v2.md`, E-05 | E-05 requires E-01/E-03 plus qualified immutable E-04 release |
| Prior AWA GCB | AWA v1.5.1, `f4b3c9b85ea1cce83d00ab9eb9f26bf3be900342` | Rollback pin |
| Qualified AWA release | tag/release `v1.5.2`, commit `a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3` | Published, non-draft, non-prerelease; lightweight tag resolves directly to this commit |
| AWA release version | `pyproject.toml` version `1.5.2` at the tagged commit | Version identity agrees with release |
| AWA hook-owner contract | `contracts/awa-contract.v1.json` SHA-256 `408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9` | Canonical `awa-hook-owner/v1` contract shipped by v1.5.2 |

Before editing, refresh both live remotes and reproduce every row. Stop if Skills main advanced materially, either prerequisite merge is absent, tag `v1.5.2` moved, release state changed, version/ref disagrees, or the contract digest differs. A harmless later Skills main requires rebase and re-proving this plan; material GCB, lockkit, verifier, clean-room, or release drift requires a successor plan.

## 2. Scope, invariants, and non-goals

### Required invariants

- AWA remains `kind: tool`, `flavor: 2`, `scope: global`, `shape: release-descriptor`, and `sync_policy: standalone-release`.
- `provenance_source` remains `github.com/KleinPerkins/awa`; only its exact release commit advances.
- `meta.yml`, `tool.yml`, and `README.md` name the same exact commit and v1.5.2 release.
- `global/tools/awa/install.sh` remains metadata-driven and byte-identical unless a pre-edit proof shows that it cannot consume the new pin. Such a failure is a stop condition, not authorization to widen this plan.
- The GCB carries only a release pointer. AWA’s kernel, engine, hook scripts, runtime, contract file, and release pointer remain owned and installed by `KleinPerkins/awa`.
- `.eco-registry.lock` is generated only by the canonical lockkit-owned normalizer. It is never hand-edited.
- AWA remains a **global-scope** capability in the Skills metadata lock and remains **excluded** from orchestrator CPP delivery because it is an SSP. No local-scope row or enrollment mutation is created.
- E-01 durable-source and E-03 strict-description verifier stanzas remain unchanged and green.
- Every install/repair/doctor proof uses a disposable clone and isolated `HOME`/XDG roots.

### Non-goals

This plan does not authorize:

- vendoring any AWA runtime or contract bytes into Skills or CPP;
- enrolling AWA in CPP sync, approving a CPP payload digest, invoking `cpp-sync`, or changing `config/registry.yml`;
- changing AWA exposure, scope, kind, shape, sync policy, installer behavior, or source repository;
- hand-editing `.eco-registry.lock` or bypassing lockkit;
- changing the Dev AWA pin, Dev host overlay, hook ownership selection, `~/.cursor/hooks.json`, or any real installed runtime;
- changing `bootstrap.sh`, client projections, generated memory, private operator data, E-06, E-07, E-09, or any later release;
- moving, recreating, or publishing the immutable `v1.5.2` tag/release.

## 3. Verified current state

At Skills main `e9e5487`:

- `global/tools/awa/meta.yml` pins v1.5.1 commit `f4b3c9b85ea1cce83d00ab9eb9f26bf3be900342`.
- `global/tools/awa/tool.yml` and `README.md` repeat that exact pin.
- `.eco-registry.lock` records AWA metadata digest `efa2fdfcbcb5b3a3fad7ffe6a7cfdd529b6ec350ab9dfab92beed54afe706122`.
- `install.sh` reads `provenance_source` and `provenance_ref`; it contains no release-specific commit and already supports static check, clone-at-pin install, repair, doctor, and idempotent GCB-pointer writes.
- `.github/scripts/verify-skills.sh` owns the Skills repository gate, including lock parity and the merged E-01/E-03 checks.
- Dev `_ops/eco/clean-room.sh` owns the cross-repository fresh-clone, isolated-HOME AWA shelf `--check`; it is a read-only verification dependency, not a Skills implementation file.
- Orchestrator registry entry `awa` is `state: excluded` with the explicit SSP/no-CPP-delivery reason. The registry is the global enrollment SoT; `.eco-registry.lock` remains all-scope metadata parity, not enrollment.

The prior v1.5.1 pin PR changed exactly `meta.yml`, `tool.yml`, `README.md`, and the generated AWA lock row. v1.5.2 preserves the GCB interface, so the same narrow boundary is expected.

## 4. Exact implementation and rollback boundary

Expected modified files:

1. `global/tools/awa/meta.yml`
   - change `provenance_ref` to `a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3`;
   - change only the release-version comment from v1.5.1 to v1.5.2.
2. `global/tools/awa/tool.yml`
   - change `release.commit` to the same exact commit.
3. `global/tools/awa/README.md`
   - change the displayed pinned commit to the same exact commit.
4. `.eco-registry.lock`
   - regenerate through lockkit after the `meta.yml` change; only the AWA row digest may change.

Expected unchanged, explicitly verified surfaces:

- `global/tools/awa/install.sh`;
- `.github/scripts/verify-skills.sh`;
- `bootstrap.sh`, `.github/pr-recipe.json`, and all PR-automation files;
- every other capability file and lock row;
- orchestrator `config/registry.yml`;
- Dev `_ops/eco/clean-room.sh`, AWA source/release, and all real HOME/XDG state.

If implementation requires another tracked file, stop. Do not “fix nearby” verifier, clean-room, installer, registry, Dev overlay, or release behavior under E-05.

## 5. Implementation sequence

### 5.1 Establish exact live authority

From a fresh Skills safe workspace based on live main:

```bash
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
test "$(git rev-parse origin/main)" = \
  "e9e54879008a42dafcd257f67547ac207dc26531"
git merge-base --is-ancestor \
  2cd47ca8050aeba41409053883886c6e06f024b9 origin/main

test "$(gh api repos/KleinPerkins/awa/git/ref/tags/v1.5.2 \
  --jq '.object.type + " " + .object.sha')" = \
  "commit a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3"
test "$(gh api repos/KleinPerkins/awa/releases/tags/v1.5.2 \
  --jq '(.draft == false and .prerelease == false)')" = true
```

Fetch/clone AWA v1.5.2 into a disposable directory, then require:

```text
HEAD = a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3
pyproject.toml version = 1.5.2
SHA-256(contracts/awa-contract.v1.json)
  = 408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
```

### 5.2 Prove the existing guards bite before the coordinated update

In a disposable copy only:

1. change `meta.yml` to the candidate pin without regenerating the lock;
2. require `bash .github/scripts/eco-lock.sh check` to fail;
3. make `tool.yml` disagree with `meta.yml` and require this exact candidate-coherence assertion to fail:

   ```bash
   META_REF="$(awk -F': *' '/^provenance_ref:/{gsub(/"/,"",$2); print $2; exit}' \
     global/tools/awa/meta.yml)"
   TOOL_REF="$(awk '/^release:/{release=1; next} release && /^  commit:/{print $2; exit}' \
     global/tools/awa/tool.yml)"
   test "$META_REF" = "$TOOL_REF"
   grep -qxF "| Pinned commit | \`$META_REF\` |" global/tools/awa/README.md
   ```

4. discard the disposable copy.

No intentionally failing state is committed.

### 5.3 Apply the narrow pointer update

Edit only the three human-authored release-pointer files in §4. Assert the old v1.5.1 commit no longer appears under `global/tools/awa/`, and the new commit appears exactly in `meta.yml`, `tool.yml`, and `README.md`. Require `install.sh` to remain byte-identical to `origin/main`.

### 5.4 Regenerate the metadata lock through lockkit

Use orchestrator lockkit, not a text editor. Because implementation runs in a linked worktree, create a temporary `lockkit/v1` config outside the repository with this exact target shape, replacing `<absolute-current-Skills-worktree>` with `git rev-parse --show-toplevel`:

```yaml
schema: lockkit/v1
master: templates/eco-lock/eco-lock.sh
targets:
  - name: e05-skills
    root: <absolute-current-Skills-worktree>
    script: .github/scripts/eco-lock.sh
    lock: .eco-registry.lock
    verify: .github/scripts/verify-skills.sh
```

The `name: e05-skills` row defines the target used below; do not point this temporary config at the primary Skills checkout. Then run:

```bash
LOCKKIT_CONFIG="$TMP_LOCKKIT_CONFIG" \
  /Users/laurence.duggan/dev/personal/ecosystem-orchestrator/bin/orchestrator.sh \
  lockkit --allow-dirty write e05-skills
LOCKKIT_CONFIG="$TMP_LOCKKIT_CONFIG" \
  /Users/laurence.duggan/dev/personal/ecosystem-orchestrator/bin/orchestrator.sh \
  lockkit check e05-skills
```

The generated diff must change only the AWA row in `.eco-registry.lock`; `.github/scripts/eco-lock.sh` must remain byte-identical to `origin/main`. Run `bash .github/scripts/eco-lock.sh check` again. Do not run `enroll`, `exclude`, `demote`, `approve`, `cpp-sync`, or edit the registry.

### 5.5 Prove exact release consumption in an isolated home

Use a disposable local clone containing the exact AWA v1.5.2 commit as `AWA_CLONE_URL`, plus fresh `HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, and `XDG_STATE_HOME`. Run:

```text
global/tools/awa/install.sh --check
global/tools/awa/install.sh
global/tools/awa/install.sh --doctor
global/tools/awa/install.sh
global/tools/awa/install.sh --repair
global/tools/awa/install.sh --doctor
```

Require:

- checkout HEAD equals `a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3`;
- `gcb-pointer.json` schema is `awa-gcb-pointer/v1`, source is `github.com/KleinPerkins/awa`, and ref is the exact candidate commit;
- `release-pointer.json` schema is `awa-release-pointer/v1`, version is `1.5.2`, commit is the exact candidate commit, hook-owner contract is `awa-hook-owner/v1`, and its contract SHA-256 equals `408e271e…c4d9`;
- installed contract bytes have that same digest;
- second install and repair preserve the exact pin and produce no duplicate pointer, runtime, or backup state;
- candidate Skills and AWA source trees remain byte-clean;
- every write remains under the disposable roots.

This is an isolated direct-mode SSP proof only. E-06 owns later external host-hook selection and the Dev overlay. Do not preview or apply any real-machine install.

### 5.6 Run owner and cross-repository verification

Run:

```bash
bash -n global/tools/awa/install.sh
CHECK_ROOT="$(mktemp -d)"
trap 'rm -rf "$CHECK_ROOT"' EXIT
env HOME="$CHECK_ROOT/home" \
  XDG_DATA_HOME="$CHECK_ROOT/data" \
  XDG_CONFIG_HOME="$CHECK_ROOT/config" \
  XDG_STATE_HOME="$CHECK_ROOT/state" \
  bash global/tools/awa/install.sh --check
bash .github/scripts/eco-lock.sh check
bash .github/scripts/verify-skills.sh
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check \
  "$(git rev-parse --show-toplevel)"
git diff --check
```

For the Dev clean-room gate, create a disposable Dev clone, place a committed clone of the exact Skills candidate at its ignored `capabilities/skills` path, and run that disposable Dev clone’s `_ops/eco/clean-room.sh`. This validates the candidate pin without changing Dev or relying on the primary Skills checkout. If any full gate is already red on exact base, reproduce it with the same command/environment and record the exact base/head differential; do not broaden E-05.

## 6. Evidence and governed delivery

The implementation PR must record:

- Skills base, implementation head/tree, and exact four-file diff;
- v1.5.2 tag object, release URL/state/time, commit/tree, and version;
- AWA contract path and SHA-256;
- old and new AWA metadata-lock row digests;
- expected-red lock/coherence probes;
- static check, isolated install/doctor/repair/idempotence results;
- GCB and release-pointer schemas/refs/digests;
- full Skills verifier, candidate-aware Dev clean-room, doc-warden, scope, secrets, and exact-base differential results;
- proof that `install.sh`, verifier, clean-room, registry, Dev, AWA release, and real HOME/XDG state did not change.

Open one ordinary Skills implementation PR only after this accepted plan is protected-merged and the operator gives the separate implementation GO. Keep it draft through defect review, run Bugbot, fix applicable findings, run verification-before-completion, then mark ready. The reviewer App owns any native auto-merge action; agents never arm it, approve, bypass, or manually merge.

## 7. Rollout, rollback, and stop conditions

### Rollout

Accepted plan → separate E-05 implementation GO → exact pin/lock candidate → governed Skills PR/checks/merge → exact merged-main re-verification. E-05 repository merge does **not** authorize real-home installation. E-06 separately owns Dev host-overlay consumption and its machine-local GO.

### Rollback

Before merge, close or revise the candidate. After merge, use a governed Skills revert to restore v1.5.1 commit `f4b3c9b85ea1cce83d00ab9eb9f26bf3be900342` in the three pointer files, regenerate `.eco-registry.lock` through lockkit, and rerun the same isolated install/doctor and owner gates. Never move/delete v1.5.2. If a v1.5.2 defect requires a new AWA build, publish a separately reviewed patch release and author a successor pin plan.

### Stop conditions

Stop before commit or push if:

- live Skills main or either merged prerequisite does not match §1;
- v1.5.2 is absent, draft/prerelease, moved, not version 1.5.2, or has a different contract digest;
- the candidate needs AWA runtime vendoring, a new registry/delivery channel, or a Dev/CPP change;
- `install.sh`, verifier, clean-room, registry, or any file outside §4 would need modification;
- lockkit cannot generate a one-row AWA lock change or another lock row changes;
- isolated install escapes its temporary roots, pin/pointer/contract identity disagrees, idempotence or rollback fails, or source bytes mutate;
- a candidate-owned verifier/check fails;
- a baseline failure cannot be reproduced identically on exact base;
- real-home/client reconciliation, E-06, private data, or E-09 would be required.

## 8. Acceptance criteria

- The plan itself is protected-merged and byte-frozen before implementation begins.
- The eventual implementation changes exactly the three AWA pointer files plus the lockkit-generated `.eco-registry.lock`.
- All pointer surfaces bind AWA v1.5.2 commit `a2b13f7…fc3`.
- Exact AWA source and installed contract digest equal `408e271e…c4d9`.
- AWA remains a global Flavor-2 standalone-release descriptor and excluded from CPP delivery.
- No AWA runtime bytes are vendored; `install.sh`, Skills verifier, Dev clean-room, registry, and Dev overlay remain unchanged.
- Static, isolated install/doctor/repair/idempotence, lockkit, full owner, clean-room, and rollback proofs pass.
- No real HOME/XDG/client state, generated memory, E-06, or E-09 work is touched.

Acceptance of this plan clears only the E-05 planning prerequisite. It does not itself mutate the pin or authorize implementation; the next step is a separate explicit E-05 implementation run.
