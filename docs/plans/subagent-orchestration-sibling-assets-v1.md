# subagent-orchestration sibling assets — declare, co-install, and verify required runtime siblings

**Version:** v1
**Status:** DRAFT — 2026-09-01
**Date:** 2026-09-01
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Companion ADR:** [`docs/adr/0002-subagent-orchestration-sibling-assets.md`](../adr/0002-subagent-orchestration-sibling-assets.md)
**Review provenance:** Root cause reproduced live on 2026-09-01 from clean state against `origin/main` `2d737862cd3a2adb36dae7748f05fde631fb48ee` (the merged 2026-09-01 tactical catalog refresh, [PR #172](https://github.com/KleinPerkins/skills/pull/172)). This plan is NOT yet implemented; it is authored alongside the Proposed ADR and executed only after the ADR is accepted.

> **For agentic workers:** Implement task-by-task. Each task is a self-contained work item with exact files, interfaces, and steps; steps use checkbox (`- [ ]`) syntax. Land Tasks 1–2 as one reviewable slice (contract + installer + CI move in lockstep); Task 3 is a separate PR; Task 4 (freshness automation) is a separate, lower-priority PR gated on an operator choice of automation surface.

**Goal:** Make `model-tiers.json` a declared, co-installed, and verified part of the
`subagent-orchestration` payload so it can never again be silently missing from a local install or
stale in cpp — using ONE generic capability-contract mechanism, not a `model-tiers.json` special case.

**Architecture:** Add an OPTIONAL `assets:` list to the `kp-capability/v1` meta contract. Teach the
single generic installer (`bootstrap.sh`) and the capability `install.sh` to co-install each declared
asset next to the primary payload; teach both doctors and the CI gate (`verify-skills.sh`) to fail on
a missing declared asset. The ecosystem orchestrator already vendors the sibling, so cpp needs only a
prompt post-refresh sync (existing WF2). The freshness recurrence is removed by an agent-driven
re-verification on the operator's existing automation surface — no new infra.

**Tech Stack:** POSIX shell/Bash (`bootstrap.sh`, `install.sh`, `.github/scripts/verify-skills.sh`);
YAML meta (`meta.yml`); Python 3 checker (`verify_model_tiers.py`); existing automation surfaces
(Cursor Automation / `local-jobs`) and the ecosystem-orchestrator sync (WF2).

## Global Constraints

- ONE generic correction in the existing capability lifecycle. No new registry, daemon, service,
  cache, installer channel, or `kp-capability/v1` schema-version bump.
- `assets:` is optional and additive; it must not change `.eco-registry.lock` parity or any digest
  bytes, and must not break sibling-repo validators.
- Do not change the installed rule path (`~/.cursor/rules/subagent-orchestration.mdc`) or Cursor's
  flat rules-dir convention.
- No paid or self-hosted CI runners for the freshness re-check; it is agent-driven.
- Do not modify the catalog content or its freshness guard as part of the packaging fix.
- Keep the tactical catalog concern (already merged) and this durable change in separate PRs.

---

## 1. Purpose

The `subagent-orchestration` capability's payload contract declares only its `.mdc`. The generic
installer, doctors, reconcile/repair, and CI therefore handle only the `.mdc`, so `model-tiers.json`
is never installed locally (the operator hand-symlinked it on 2026-09-01) and drifts stale in cpp.
This plan closes the contract gap generically and wires detection into every lifecycle verb.

## 2. Scope and non-goals

**In scope:**

- Declare `assets: [model-tiers.json]` in the capability meta (optional generic field).
- Co-install declared assets in `bootstrap.sh` (rule branch) and the capability `install.sh`.
- Verify declared assets in `bootstrap.sh` doctor, `install.sh --doctor`, and `verify-skills.sh`.
- Add a focused installer regression proving co-install + missing-sibling detection.
- Confirm sibling-repo validators tolerate the optional key.
- Document the post-refresh orchestrator sync and the agent-driven freshness re-verification.

**Explicit non-goals:**

- No new package infra, registry, daemon, cache, or installer channel.
- No schema-version bump; no change to the digest field set or the lockfile.
- No embedding of catalog data into the `.mdc`.
- No fix for the unrelated `~/dev/_ops` `.bak` dangling-symlink lifecycle.
- No implementation of the freshness automation code beyond a bounded, revertible entry on an
  existing automation surface (Task 4), and only after the surface is chosen.

## 3. Background and context (observed 2026-09-01)

- `global/rules/subagent-orchestration/meta.yml` is a 10-line `kp-capability/v1` rule meta with keys
  `schema,id,kind,flavor,scope,owner,install,post_mgmt,expose` and no payload-sibling declaration.
- `bootstrap.sh:344-375` `install_unit()` rule branch links only `$d/$id.mdc` →
  `$CURSOR_RULES_DIR/$id.mdc`. `link_path()` (`bootstrap.sh:283-296`) records every link in
  `DESIRED_LINKS`, so anything linked here is prune-safe (`bootstrap.sh:428-447`).
- `bootstrap.sh:378-400` `doctor_unit()` rule branch checks only that `$d/$id.mdc` exists in source.
- `global/rules/subagent-orchestration/install.sh` links only the `.mdc` and its `--doctor` checks
  only that link.
- `.github/scripts/verify-skills.sh:80` asserts a fixed required-key set is present (does NOT reject
  unknown keys); `verify-skills.sh:150` checks the rule `.mdc` exists in source.
- Consumers already expect an installed sibling: `swarm_helper.py:676-683` resolves
  `~/.cursor/rules/model-tiers.json` (via the `.mdc` symlink's dir), and
  `subagent-orchestration.mdc:12-13` tells agents to read the installed sibling.
- The orchestrator vendors the sibling already: `ecosystem-orchestrator/lib/payload.sh`
  `payload_shared_list()` returns `model-tiers.json`, `subagent-orchestration.mdc`,
  `verify_model_tiers.py` for this capability (excludes `tests/*`).
- `assets:` is NOT in `eco-lock.sh`'s digest field list, so adding it leaves `.eco-registry.lock`
  unchanged.

## 4. File map

- Modify: `global/rules/subagent-orchestration/meta.yml` (add `assets:`)
- Modify: `bootstrap.sh` (add `assets_list()`; co-install in rule branch; verify in doctor)
- Modify: `global/rules/subagent-orchestration/install.sh` (co-install + doctor the declared assets)
- Modify: `.github/scripts/verify-skills.sh` (assert declared assets exist in source)
- Create: `scripts/tests/test_sibling_assets.sh` (focused installer regression)
- Modify: `.github/scripts/verify-skills.sh` (wire the regression, mirroring the eco-lock stanza)

## 5. Lock decomposition

- `lock-1`: declare `assets:` and make CI assert declared source assets exist (red→green)
- `lock-2`: co-install declared assets in the generic installer + capability `install.sh`
- `lock-3`: verify installed assets in both doctors; add the sandbox-HOME regression
- `lock-4`: confirm sibling-repo validator tolerance; document post-refresh sync
- `lock-5`: (separate PR, operator-gated) agent-driven freshness re-verification entry

## 6. Work items

### Task 1: Declare the asset and assert its source presence in CI

**Files:**

- Modify: `global/rules/subagent-orchestration/meta.yml`
- Modify: `.github/scripts/verify-skills.sh` (after the per-kind payload check near `:150`)

**Interfaces:**

- Consumes: existing `verify-skills.sh` per-capability meta loop (`$m` = meta path, `$dir` = capability dir).
- Produces: an optional `assets:` contract field and a CI assertion that each declared asset exists in source.

- [ ] **Step 1: Add the optional declaration to the capability meta**

Append to `global/rules/subagent-orchestration/meta.yml`:

```yaml
# Runtime sibling assets that must be installed alongside the rule payload (kp-capability/v1
# optional `assets:`). Consumers read the catalog from the installed rules dir or source co-location.
assets: [model-tiers.json]
```

- [ ] **Step 2: Assert declared assets exist in source (generic, all kinds)**

In `.github/scripts/verify-skills.sh`, immediately after the per-kind payload `case` that ends with
the `rule) [ -f "$dir/$idv.mdc" ] ...` arm (around `verify-skills.sh:150`), add:

```bash
    # kp-capability/v1 optional `assets:` — every declared runtime sibling must exist in source.
    for asset in $(awk -F'assets:[[:space:]]*' '/^assets:/{print $2; exit}' "$m" | tr -d '[]' | tr ',' ' '); do
      [ -n "$asset" ] || continue
      [ -f "$dir/$asset" ] || { note "FAIL  $dir declares asset '$asset' but $dir/$asset is missing in source"; fail=1; }
    done
```

- [ ] **Step 3: Prove green (the asset exists) and red (temporarily rename it)**

```bash
bash .github/scripts/verify-skills.sh   # expect: OK
mv global/rules/subagent-orchestration/model-tiers.json /tmp/mt.json
bash .github/scripts/verify-skills.sh   # expect: FAIL naming the missing declared asset
mv /tmp/mt.json global/rules/subagent-orchestration/model-tiers.json
bash .github/scripts/verify-skills.sh   # expect: OK again
```

### Task 2: Co-install declared assets in the generic installer and capability install.sh

**Files:**

- Modify: `bootstrap.sh` (add `assets_list()`; extend `install_unit()` rule branch)
- Modify: `global/rules/subagent-orchestration/install.sh`

**Interfaces:**

- Consumes: `meta_get`/`exposes` parsing conventions and `link_path()` (`bootstrap.sh:283-296`).
- Produces: `~/.cursor/rules/<asset>` symlinks recorded in `DESIRED_LINKS` (prune-safe), created by
  install/reconcile/repair and by a standalone `install.sh` run.

- [ ] **Step 1: Add a list reader mirroring `exposes()`**

Add near `meta_get()` (`bootstrap.sh:254`):

```bash
assets_list() {
  awk -F'assets:[[:space:]]*' '/^assets:/{print $2; exit}' "$1" 2>/dev/null | tr -d '[]' | tr ',' ' '
}
```

- [ ] **Step 2: Co-install declared assets in the rule branch**

Replace the `rule)` arm of `install_unit()` (`bootstrap.sh:355-358`) with:

```bash
    rule)
      exposes "${d}meta.yml" cursor || return 0
      [ -f "$d/$id.mdc" ] || { log "  WARN   missing rule payload: $d/$id.mdc"; return 0; }
      link_path "$d/$id.mdc" "$CURSOR_RULES_DIR/$id.mdc" "$dry"
      for asset in $(assets_list "${d}meta.yml"); do
        [ -n "$asset" ] || continue
        if [ -f "$d/$asset" ]; then
          link_path "$d/$asset" "$CURSOR_RULES_DIR/$asset" "$dry"
        else
          log "  WARN   $id declares asset '$asset' but $d/$asset is missing"
        fi
      done ;;
```

- [ ] **Step 3: Co-install + doctor the assets in the capability install.sh**

In `global/rules/subagent-orchestration/install.sh`, after linking the `.mdc` (and in the `--doctor`
branch), iterate the meta-declared assets from the sibling `meta.yml` and link/verify each
`$HOME/.cursor/rules/<asset> -> $SRC/<asset>`, reusing the existing symlink/real-path guards. Read
the list with the same awk as `assets_list()` so the declaration stays the single source of truth.
`--doctor` must exit non-zero if any declared asset link is missing or does not resolve to source.

- [ ] **Step 4: Prove co-install into a sandbox HOME (no real-client side effects)**

```bash
REPRO=/tmp/sibling-assets; rm -rf "$REPRO"; mkdir -p "$REPRO/home/.cursor/rules"
HOME="$REPRO/home" bash global/rules/subagent-orchestration/install.sh
test -L "$REPRO/home/.cursor/rules/model-tiers.json" && echo "PRESENT (co-install works)" || echo "ABSENT (regression)"
HOME="$REPRO/home" bash bootstrap.sh --install --dry-run 2>&1 | rg 'model-tiers'   # expect a LINK line
rm -rf "$REPRO"
```

### Task 3: Verify installed assets in doctors + add a focused regression

**Files:**

- Modify: `bootstrap.sh` `doctor_unit()` (`bootstrap.sh:378-400`, rule arm at `:388`)
- Create: `scripts/tests/test_sibling_assets.sh`
- Modify: `.github/scripts/verify-skills.sh` (wire the regression, mirroring the eco-lock stanza at `:243-272`)

**Interfaces:**

- Consumes: Task 2's co-install behavior.
- Produces: a doctor that fails on a missing declared source asset, and a sandbox-HOME regression
  proving co-install and missing-sibling detection.

- [ ] **Step 1: Extend the rule doctor arm to assert declared assets exist in source**

Replace the rule arm at `bootstrap.sh:388` with:

```bash
    rule)
      [ -f "$d/$id.mdc" ] || { log "  FAIL   $d missing $id.mdc"; err=1; }
      for asset in $(assets_list "${d}meta.yml"); do
        [ -n "$asset" ] || continue
        [ -f "$d/$asset" ] || { log "  FAIL   $d declares asset '$asset' but $d/$asset is missing"; err=1; }
      done ;;
```

- [ ] **Step 2: Create the sandbox-HOME regression**

Write `scripts/tests/test_sibling_assets.sh` that, using a temp `HOME`: (a) runs the capability
`install.sh` and asserts `~/.cursor/rules/model-tiers.json` is a symlink resolving to the source
catalog; (b) asserts `install.sh --doctor` exits 0 with the asset present; (c) removes the asset link
and asserts `install.sh --doctor` exits non-zero; (d) asserts `bootstrap.sh --install --dry-run`
emits a link line for `model-tiers.json`. Follow the `set -e`-safe `if output=...; then rc=0; else
rc=$?; fi` capture pattern used in `scripts/tests/test_eco_lock_digest.sh`.

- [ ] **Step 3: Wire the regression into the repo verifier**

Add a stanza mirroring the eco-lock regression wiring (`verify-skills.sh:243-272`):

```bash
if [ -x scripts/tests/test_sibling_assets.sh ]; then
  if bash scripts/tests/test_sibling_assets.sh; then
    note "PASS  sibling-assets regression"
  else
    note "FAIL  sibling-assets regression"; fail=1
  fi
else
  note "FAIL  scripts/tests/test_sibling_assets.sh missing"; fail=1
fi
```

- [ ] **Step 4: Run the full gate**

```bash
bash .github/scripts/verify-skills.sh   # expect: OK (global + local + lock + capability-local)
```

### Task 4: Sibling-repo tolerance, post-refresh sync, and agent-driven freshness re-verification

**Files:**

- No `skills` code beyond Tasks 1–3 for the tolerance/sync checks (verification + documentation).
- Separate PR / operator-gated: one entry on the chosen automation surface.

**Interfaces:**

- Consumes: `~/dev/_ops/eco/manifest.sh` and kp-mcp `verify-capabilities.sh` (shared-contract
  validators); the ecosystem-orchestrator sync (WF2); an existing automation surface
  (Cursor Automation or `local-jobs`) plus the tactical-refresh shape from PR #172.

- [ ] **Step 1: Confirm the optional key is tolerated by sibling validators**

Run the shared-contract validators against a meta carrying `assets:` and confirm none rejects the
unknown key. If any enforces a closed key set, widen that validator to allow the optional `assets:`
list FIRST, in its own repo under its own governance, before relying on the field.

- [ ] **Step 2: Document the post-refresh orchestrator sync**

Record that a catalog-refresh PR merging to `skills` `main` must be followed by an
ecosystem-orchestrator sync (WF2) so cpp's vendored `model-tiers.json` is re-vendored under its
normal governed PR rather than drifting. No orchestrator code change is required (it already vendors
the sibling); this is a runbook/cadence note plus, optionally, a non-blocking orchestrator-side
"declared assets present in payload" completeness check.

- [ ] **Step 3: Add the agent-driven freshness re-verification (operator-gated surface)**

On the operator-chosen surface, add one automation entry that, on a periodic trigger, runs an agent
that: reads the live `Task`-tool model enum; runs `verify_model_tiers.py`; and, if the catalog is
within a warn window of `MAX_CATALOG_AGE_DAYS` or any slug mismatches the live enum, updates
`model-tiers.json` + `verify_model_tiers.py` in lockstep (the PR #172 shape) and opens/stewards the
refresh PR, then triggers the Step 2 sync after merge. It must no-op when the catalog is fresh and
consistent. This removes the recurring manual PM task using existing skills (`automate` /
`local-jobs` / `pr-steward`) with no new infra and no paid runners.

## 7. Acceptance criteria

- `assets: [model-tiers.json]` is declared in the capability meta; `.eco-registry.lock` is unchanged
  (no regen needed) and `eco-lock.sh check` stays green.
- `verify-skills.sh` fails when a declared asset is absent from source and passes when present.
- After `bootstrap.sh --install` (or `install.sh`) into a sandbox `HOME`,
  `~/.cursor/rules/model-tiers.json` is a symlink resolving to the source catalog; a second run is
  idempotent; `--reconcile` does not prune it.
- `install.sh --doctor` and `bootstrap.sh` doctor fail when the declared asset is missing and pass
  when present.
- `scripts/tests/test_sibling_assets.sh` is red before Task 2 and green after Tasks 2–3; the full
  `verify-skills.sh` gate is green.
- Sibling-repo validators accept the optional `assets:` key (or are widened first).
- No installed rule path, Cursor rules-dir convention, catalog content, or freshness guard is changed
  by Tasks 1–3.

## 8. Rollback

- Remove the `assets:` line from `meta.yml`: the installer and CI revert to `.mdc`-only (pre-ADR
  behavior) with no lockfile or data migration.
- Revert the `bootstrap.sh` / `install.sh` / `verify-skills.sh` commits and delete
  `scripts/tests/test_sibling_assets.sh` to fully restore prior logic; digest bytes and lock parity
  are untouched throughout, so no repair is needed.
- The Task 4 automation entry is independently revertible (delete the entry); the catalog and its
  freshness guard are never modified by rollback.
