# Context Efficiency E-01 — durable Skills source repair

**Version:** v1
**Status:** ACCEPTED — 2026-08-15
**Date:** 2026-08-15
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Program milestone:** E-01, “Close the standalone-under-disposable Skills source gap and reconcile owned links/pointers.”
**Review provenance:** Authored from the accepted Context Efficiency Program and ADR 0004, then grounded against clean Skills `origin/main` and the current resolver, reconciler, tests, and runnerless verification recipe. No implementation or machine-local reconciliation was performed while authoring this draft.

**Goal:** Ensure every Skills-owned projection is sourced from the durable primary Skills checkout even when `bootstrap.sh` is invoked from a standalone Skills clone nested below a disposable Cursor worktree, or refuse before mutation with a plain diagnostic when that primary is unavailable or untrusted.

**Architecture:** Extend the existing `bootstrap.sh` source resolver by one ancestry/trust case. Keep the established primary at `${HOME}/dev/capabilities/skills`, preserve current direct-primary and linked-worktree behavior, and feed the resolved root into the existing bootstrap/reconcile path so symlinks and installer-owned pointers converge without a registry, router, runtime, or second delivery channel.

**Tech stack:** Bash, Git worktree metadata, existing `bootstrap.sh`, isolated `HOME` fixtures, existing shell test harness, and `.github/scripts/verify-skills.sh`.

---

## 1. Authority and exact dependency binding

This draft is bound to the following immutable authoring baseline:

| Authority | Exact ref | Bound evidence |
|---|---|---|
| Skills live default branch | `KleinPerkins/skills` `main` at `54537b040e837a00543414e4efacd1b3f3f959b7` | Clean isolated worktree; this is the rollback/source baseline for implementation |
| Accepted Dev program | `KleinPerkins/dev` `main` at `0818be2f3beb0bfafaa17abd6250e780f87a19a1` | `_ops/plans/context-efficiency-program-v1.md` blob `f6de269c9c2f88e78e58abd9c247405cb506a123`, raw SHA-256 `327a87b930a9d26a62388005db39c2b097660e0ebfd95aa01d80b17819c17cc4` |
| Accepted ADR 0004 | Same Dev commit | `_ops/adr/0004-optimize-context-projections-without-moving-authority.md` blob `0578f7d7b4ace6c233d5f56c9d20fc43ad979450`, raw SHA-256 `77ddcd3b5e480b77cf283afd8e5593b08022483920ff55451bf5d79fcfc51060` |

The program audit previously reviewed Skills at `9fa02b9c0d34a554e32994e9258e6241fc1f3c90`. The only changes from that ref through the bound Skills ref are runnerless PR-automation configuration/proof changes (`61799ec` through `54537b0`); they do not alter the resolver, bootstrap, projection layout, or E-01 assumptions.

Implementation must fetch the live default branch again before writing. If `bootstrap.sh`, its source-resolution tests, the projection layout, owner boundary, or either accepted dependency has materially changed, stop and re-adjudicate or supersede this draft; do not layer compatibility behavior onto a stale plan.

## 2. Global constraints and protected invariants

- This artifact is planning-only. Its DRAFT status grants no code, install, release, or machine-local mutation authority.
- Extend the existing Skills resolver only. Do not add a source registry, context registry, runtime, daemon, router, alternate installer, or second capability-delivery channel.
- Reuse `bootstrap.sh --reconcile` and the existing per-capability installers to relink owned projections and refresh installer-owned pointers. Do not hand-edit installed symlinks or pointer JSON.
- The only new classification is a standalone Skills checkout nested below a verified disposable Cursor-worktree ancestor. Do not reinterpret arbitrary clones, ordinary parent repositories, or unrelated worktrees.
- Preserve non-symlink foreign paths: the existing “SKIP, never clobber” behavior remains unchanged.
- Preserve exposure from each `meta.yml`; no capability ID, scope, kind, client exposure, or payload byte changes.
- Preserve Save-Game as checkpoint/reconcile authority, `agent-route` as the sole global root-selection primitive, and the shared model-tier catalog/orchestration semantics.
- Add no context-specific router and no new registry. Do not change AWA semantics, hooks, releases, or its pinned ref.
- Do not read, rewrite, classify, print, or delete any `agent-learnings.md` content or generated `~/AGENTS.md`.
- Keep global/local source authority in Skills and downstream delivery on the existing Skills → orchestrator → governed-consumer path.
- Machine-local rollout requires its own operator GO after merge; plan acceptance and implementation merge do not authorize writes under `~/.cursor`, `~/.claude`, `~/.codex`, or `${XDG_DATA_HOME:-$HOME/.local/share}`.
- Use one writer per tree and the Skills governed PR path. Never arm auto-merge from an implementation agent.

## 3. Verified current state and defect

At the bound Skills ref:

- `bootstrap.sh:30-72` exposes `resolve_repo_dir <script_dir>`.
- A copied bootstrap without an adjacent repository resolves to `${HOME}/dev/capabilities/skills` and retains the clean-install clone path.
- A linked Skills worktree is recognized because its `.git` is a `gitdir:` file. `git worktree list --porcelain` supplies the primary checkout, which is validated for path, `.git`, and `global/` presence.
- An ordinary checkout whose `.git` is a directory returns `SCRIPT_DIR` directly.
- A standalone Skills clone nested at a path such as `${HOME}/.cursor/worktrees/<host-repo>/<slot>/capabilities/skills` therefore returns itself, even though deleting the ancestor Cursor worktree deletes every projection target rooted below it.
- `bootstrap.sh:159-251` creates/relinks owned projections and invokes post-management or Flavor-2 installers from the resolved source directory.
- `bootstrap.sh:279-335` prunes only links owned by the selected `REPO_DIR`.
- `bootstrap.sh:337-372` already provides `--install`, `--reconcile`, `--prune`, `--doctor`, `--repair`, and `--dry-run`.
- `global/skills/swarm/tests/test_bootstrap.sh:197-292` already proves direct-primary, linked-worktree, missing-primary, and “no link to temporary linked root” behavior, but its suite is not currently called by the repository verifier.
- `.github/scripts/verify-skills.sh` is the protected custom job run by `.github/pr-recipe.json` as `repo.skills.m3-verify`.
- `global/tools/awa/install.sh:131-164` writes `awa-gcb-pointer/v1`; its `shelf` field comes from the installer’s own source directory. Running the standard reconciler from the resolved durable root is therefore the existing pointer-refresh mechanism.

The gap is not a need for generalized clone discovery. It is one missing trust check before the current ordinary-checkout return path.

## 4. Resolution and reconciliation contract

### 4.1 Internal interfaces

Keep the public CLI unchanged. The implementation may add only these internal Bash helpers to `bootstrap.sh`:

```text
cursor_worktree_ancestor <physical-script-dir>
  stdout: the verified ancestor worktree root, or empty
  status: 0 only when the Skills checkout is a strict descendant of
          ${HOME}/.cursor/worktrees/<repo>/<slot> and that ancestor is itself
          a linked Git worktree; 1 otherwise

validate_established_primary <candidate-root>
  stdout: empty
  status: 0 only when candidate-root is a physical, non-disposable checkout of
          KleinPerkins/skills with .git, global/, and bootstrap.sh present;
          non-zero with one plain diagnostic otherwise

resolve_repo_dir <script-dir>
  stdout: one trusted source root on success
  status: non-zero before any install/reconcile mutation on failure
```

`resolve_repo_dir` retains its name, one-argument call, and stdout contract because the rest of `bootstrap.sh` already consumes it through `REPO_DIR="$(resolve_repo_dir "$SCRIPT_DIR")"`.

### 4.2 Decision order

The resolver must apply this order:

1. If the script is not running beside a Skills repository, retain the existing `${HOME}/dev/capabilities/skills` clean-install path and `clone_if_missing` behavior.
2. If `.git` is a `gitdir:` file, retain the current linked-worktree path exactly: resolve the first `git worktree list --porcelain` entry, apply the existing path/`.git`/`global/` checks, and use it. Do not add remote-identity requirements to this already-shipped branch.
3. If `.git` is a directory and `cursor_worktree_ancestor` returns no verified ancestor, retain current ordinary-checkout behavior and use `SCRIPT_DIR`.
4. If `.git` is a directory and a verified disposable Cursor-worktree ancestor exists, reject `SCRIPT_DIR` as a projection source. Validate and use exactly `${HOME}/dev/capabilities/skills`.
5. If that established primary is missing, malformed, resolves below a disposable Cursor worktree, or does not identify `KleinPerkins/skills`, return non-zero with a plain diagnostic that names the rejected nested source, the ancestor, the expected primary, and the failed check.

Do not scan sibling directories, rank clones, consult `agent-route`, or persist a choice. The established primary path already exists in the bootstrap contract; this change only refuses an unsafe invocation source and reuses that path.

All comparisons must use physical/canonical paths and strict path-component boundaries; string-prefix lookalikes such as `.cursor/worktrees-backup` are not disposable Cursor-worktree ancestors. Dry-run performs the same resolution and refusal checks as apply mode.

### 4.3 Produced behavior

On success, the existing code consumes the resolved `REPO_DIR` and produces:

- absolute Cursor/Claude/Codex skill links rooted in the durable primary;
- Cursor rule and Cursor/Claude/Codex sub-agent links rooted in the durable primary according to existing `expose:` values;
- existing plugin/tool post-management actions invoked from the durable source;
- refreshed installer-owned pointers, including the AWA GCB `shelf`, through existing installers;
- existing prune behavior limited to links owned by the resolved primary.

No new persisted state, pointer schema, enrollment record, or authority is produced.

## 5. Exact file map and rollback boundary

Implementation is limited to:

- Modify `bootstrap.sh:30-76` — add the bounded ancestor/trust helpers and extend `resolve_repo_dir`.
- Modify `bootstrap.sh:337-372` only if needed to make the existing source-selection log accurately distinguish linked-worktree and nested-standalone recovery; no CLI flag changes.
- Modify `global/skills/swarm/tests/test_bootstrap.sh:197-292` — extend the existing black-box bootstrap fixture matrix.
- Modify `.github/scripts/verify-skills.sh:272-289` — run the existing bootstrap integration test as an explicit required stanza.

No `meta.yml`, payload, AWA pin, lockfile, installer, generated projection, README, policy, or machine-local file changes are planned. `README.md:89-142` already states that the primary repo is the source and that bootstrap is idempotent, so implementation does not make it stale.

E-03 has a separate implementation/rollback boundary. If E-03 lands first and also changes `.github/scripts/verify-skills.sh`, rebase and preserve both independent test stanzas.

## 6. Work items

### Task 1: Add the complete red fixture matrix

**Files:**

- Modify `global/skills/swarm/tests/test_bootstrap.sh`
- Modify `.github/scripts/verify-skills.sh`

**Interfaces:**

- Consumes: current `bootstrap.sh` CLI; temporary Git repositories/worktrees; isolated `HOME`; existing `assert_link`.
- Produces: deterministic black-box coverage for every E-01 root class, reconciliation mode, pointer-source path, and refusal case.

- [ ] Extend the fixture projection with a minimal Flavor-2 test tool whose installer writes a HOME-relative pointer containing its own physical source directory. It must perform no network access and must not use the real AWA runtime.
- [ ] Preserve the existing direct-primary and linked-worktree cases.
- [ ] Construct a real host Git primary plus a linked worktree rooted under `${HOME}/.cursor/worktrees/<repo>/<slot>`, then create an independent Skills Git repository with a `.git` directory below that linked ancestor.
- [ ] Create the established primary at `${HOME}/dev/capabilities/skills` with the same Skills remote identity and fixture payload.
- [ ] Add an in-place-upgrade case whose existing skill links and fixture pointer target the nested standalone root; `--reconcile` must retarget both to the established primary.
- [ ] Add `--dry-run` coverage proving the planned durable targets are printed while existing links/pointer bytes remain unchanged.
- [ ] Add missing-primary, wrong-origin primary, and primary-below-disposable-ancestor cases. Each must return non-zero before writes and include the plain diagnostic fields from §4.2.
- [ ] Run reconcile twice and compare ordered link targets plus pointer bytes to prove idempotence.
- [ ] Run `--repair` from the nested standalone checkout and prove installers receive the durable source.
- [ ] Inventory every fixture-owned link after apply and fail if any target is below the disposable ancestor.
- [ ] Wire `bash global/skills/swarm/tests/test_bootstrap.sh` into `.github/scripts/verify-skills.sh`.

Focused red command:

```bash
bash global/skills/swarm/tests/test_bootstrap.sh
```

Expected before the resolver fix: the pre-existing primary/linked cases pass, while the new nested-standalone cases fail because links and the fixture pointer use the nested root; missing/untrusted-primary cases incorrectly succeed.

Required verifier red command:

```bash
bash .github/scripts/verify-skills.sh
```

Expected before the resolver fix: `FAIL  durable bootstrap source fixtures` followed by `verify-skills: FAILED`. Do not commit a failing-test-only state; the red test and green fix land in one reviewable implementation PR.

### Task 2: Extend the resolver minimally and turn the matrix green

**Files:**

- Modify `bootstrap.sh`

**Interfaces:**

- Consumes: Task 1’s root-class fixtures and the existing `resolve_repo_dir` call site.
- Produces: one durable `REPO_DIR` or a non-zero plain refusal before mutation; no public CLI or persisted schema changes.

- [ ] Add strict physical-path/component checks for the Cursor worktree root.
- [ ] Verify the ancestor is a linked Git worktree, rather than trusting path spelling alone.
- [ ] Validate the established primary’s repository identity and required source surfaces.
- [ ] Route only the nested-standalone case to the established primary; leave copied-script, direct-primary, and linked-worktree branches behaviorally unchanged.
- [ ] Keep resolution before `DESIRED_LINKS`, directory creation, linking, pruning, and installer invocation.
- [ ] Use one plain source-selection message for successful recovery and one actionable diagnostic family for refusal.

Focused green command:

```bash
bash global/skills/swarm/tests/test_bootstrap.sh
```

Expected after the fix: every primary, linked-worktree, nested-standalone, missing/untrusted-primary, dry-run, reconcile, repair, pointer, and idempotence case reports `PASS`.

### Task 3: Prove repository and isolated-install closure

**Files:**

- No files beyond §5.

**Interfaces:**

- Consumes: green focused fixtures and the locked runnerless recipe.
- Produces: exact implementation commit/digests and deterministic verification evidence for owner review.

- [ ] **Clean install:** clone the candidate source to `${HOME}/dev/capabilities/skills` under an empty isolated HOME, run `--reconcile`, and require newly created links/pointer fixtures to use that durable primary.
- [ ] **In-place upgrade/repair:** begin with links and the fixture pointer rooted below the disposable ancestor, then require `--reconcile` and `--repair` to converge to the durable primary.
- [ ] **Failure:** run every missing/untrusted-primary fixture and require non-zero, pre-mutation refusal with the §4.2 diagnostic.
- [ ] **Idempotence:** run the clean and upgrade reconciliations twice and require identical ordered target/pointer bytes.
- [ ] Run shell syntax checks:

```bash
bash -n bootstrap.sh
bash -n global/skills/swarm/tests/test_bootstrap.sh
bash -n .github/scripts/verify-skills.sh
```

- [ ] Re-run the focused fixture and full owner verifier:

```bash
bash global/skills/swarm/tests/test_bootstrap.sh
bash .github/scripts/verify-skills.sh
```

- [ ] Run documentation governance read-only and record pre-existing unrelated drift separately:

```bash
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
```

- [ ] Record the implementation commit plus SHA-256 for each changed implementation/test file. Present that exact candidate for owner review; any post-approval byte change invalidates the candidate GO.
- [ ] Open the implementation PR through Skills’ ordinary governed path and wait for the exact-head `pr-automation / verify` check and reviewer App. The implementation agent must not arm auto-merge.

### Task 4: Reconcile the operator machine only after merged-ref GO

**Files:**

- No repository edits. This task mutates machine-local projections only after the gate in §7.

**Interfaces:**

- Consumes: merged Skills default-branch commit, explicit operator GO, existing bootstrap/reconciler, and existing capability installers.
- Produces: durable machine-local links/pointers and projection-specific fresh-client evidence.

- [ ] Fetch the merged Skills default branch into the established primary and verify its exact commit/digests match the approved implementation.
- [ ] Capture a private pre-change inventory of Skills-owned symlink targets and the SHA-256/schema/source/ref/shelf fields of `${XDG_DATA_HOME:-$HOME/.local/share}/awa/gcb-pointer.json`; record no learned content or secrets.
- [ ] Preview:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile --dry-run
```

- [ ] Present the preview and exact merged commit to the operator. Apply only after explicit machine-local release GO:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile
```

- [ ] Re-run the preview and require convergence with no remaining relink/prune action.
- [ ] Enumerate active Skills-owned links under `~/.cursor/{skills,rules,agents}`, `~/.claude/{skills,agents}`, and `~/.codex/{skills,agents}`; require every target to resolve outside `${HOME}/.cursor/worktrees`.
- [ ] Require the AWA GCB pointer’s `shelf` to resolve under `${HOME}/dev/capabilities/skills/global/tools/awa`, while its approved `source`, `ref`, checkout, and release pointer remain unchanged by E-01.
- [ ] Run only the affected fresh-client rows in §8, then hand content-safe refs/digests/results to the Dev evidence ledger. Do not make the ledger executable.

## 7. Approval, owner, release, and machine-local gates

| Gate | Required evidence and authority | Failure behavior |
|---|---|---|
| Dependency/ref gate | Skills and Dev refs/blobs in §1 re-fetched and still semantically valid | Stop and revise/supersede; no implementation |
| Owner-plan gate | Operator accepts this Skills DRAFT under `docs/plans/README.md`; accepted bytes then freeze | DRAFT remains non-executable |
| Exact-candidate gate | Exact implementation commit and changed-file SHA-256 set reviewed; source-trust semantics explicitly approved | Any byte/ref change revokes GO |
| Owner PR gate | Skills required exact-head check passes and reviewer App governs merge | No merge or machine rollout |
| Release-GO gate | There is no separate Skills semver release for bootstrap. “Release GO” means the operator explicitly approves the exact merged Skills commit for live reconciliation | Keep merged code unapplied locally |
| Machine-local gate | Operator approves the dry-run that will relink client projections and refresh installer-owned pointers | No writes under HOME/XDG |
| Live-client gate | Fresh eligible Cursor, Claude, and Codex evidence passes after reconciliation | Stop rollout and restore durable prior projections |
| Program evidence gate | Dev ledger records owner ref, source/install digests, client/root classes, results, and rollback ref without private content | E-01 remains incomplete; E-09 stays blocked |

Plan acceptance is only the owner-plan gate. It does not satisfy any later gate.

## 8. Fresh-client evidence rows

Run these only after the merged implementation is reconciled. “Fresh” means a newly started client process/chat that cannot reuse the old catalog.

| Affected cohort | Required evidence |
|---|---|
| Cursor Desktop, fresh Dev root | Skills category shows representative global/local IDs; installed rule and capability source paths resolve to the durable Skills primary; an assessment-only `plan-refine` invocation and read-only Save-Game status/resume route succeed; `agent-route` remains discoverable; shared model-tier catalog digest and semantics are unchanged |
| Claude, fresh process | Representative Skills and supported sub-agents are discovered from the durable primary; one assessment-only explicit/ordinary-language skill invocation succeeds; Save-Game remains discoverable without creating a checkpoint |
| Codex, fresh process | Representative Codex-exposed Skills are discovered from the durable primary and one harmless assessment-only invocation succeeds; no claim is made for sub-agents whose `meta.yml` does not expose Codex |

Cursor Cloud is not an affected row: E-01 repairs user-home projections that are absent in Cloud. Background/multi-root behavior is unchanged and needs only source-level contract coverage, not a context-size claim.

## 9. Acceptance criteria and E-01 definition-of-done map

- **Primary fixture:** direct primary invocation still sources itself and reconciles successfully.
- **Linked-worktree fixture:** current first-primary resolution remains green and no installed target uses the linked checkout.
- **Nested-standalone fixture:** a standalone Skills repository below a verified Cursor linked-worktree ancestor resolves only to the established primary.
- **Missing-primary fixture:** absent, malformed, wrong-origin, or disposable established primary returns non-zero with a plain diagnostic before writes.
- **Dry-run fixture:** source validation is identical to apply mode and no link/pointer byte changes.
- **Idempotence fixture:** second reconcile produces identical link targets and pointer bytes with no residual action.
- **Repair/upgrade fixtures:** stale disposable links/pointer converge to the durable primary through the standard reconcile/repair paths.
- No active Skills-owned client link or AWA GCB `shelf` targets a disposable Cursor-worktree root.
- Foreign non-symlink paths remain untouched; exposure and payload bytes are unchanged.
- Focused fixture and full `.github/scripts/verify-skills.sh` pass at the exact implementation commit.
- Affected fresh Cursor/Claude/Codex rows pass; source tests are not substituted for fresh-client evidence.
- Save-Game, `agent-route`, model-tier/orchestration semantics, AWA pin/product behavior, learned-data boundaries, and the no-registry/no-router rule remain intact.
- Dev receives content-safe evidence and can mark E-01 green; E-09 remains blocked until every other prerequisite is independently green.

## 10. Clean-state receipts

Before implementation edits:

```bash
git fetch origin --prune
git status --short
git rev-parse origin/main
git diff --check
```

Expected: empty status, the reviewed/refreshed owner baseline, and no diff errors.

Before implementation PR:

```bash
git status --short
git diff --check
git diff --name-only origin/main...HEAD
git rev-parse HEAD
```

Expected changed-file set:

```text
.github/scripts/verify-skills.sh
bootstrap.sh
global/skills/swarm/tests/test_bootstrap.sh
```

After machine reconciliation, the private receipt records: merged Skills commit; pre/post projection-target digests; AWA pointer digest and non-secret identity fields; dry-run/apply/idempotence results; affected client/root classes; and rollback commit. It records no learned content, credentials, or raw private data.

## 11. Rollout and rollback

Roll out in this order: accepted owner plan → exact implementation candidate review → governed Skills PR/check/merge → operator-approved live dry-run → live reconcile → idempotence inventory → fresh-client canary → remaining affected clients → Dev evidence.

If source resolution or a client canary fails:

1. Stop before further clients.
2. Keep or restore links at the last known-good **durable** Skills primary; never restore a disposable target.
3. Revert the implementation commit through the governed Skills PR path if the resolver itself is defective.
4. From the durable primary at the rollback ref, run the standard reconciler and verify every target/pointer again.
5. Restart affected clients and repeat the fresh-client rows.

Rollback does not edit capability payloads, AWA release state, Save-Game state, or learned data. Closing or reverting this DRAFT planning PR changes no runtime state. Once accepted, v1 is byte-immutable; a material revision requires `context-efficiency-e01-durable-skills-source-v2.md` with `Supersedes:`.
