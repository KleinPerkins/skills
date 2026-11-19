# eco-lock digest exit status — keep valid digest output but return success when `descriptor_ref` is absent

**Version:** v1
**Status:** ACCEPTED — 2026-08-09
**Date:** 2026-08-09
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Review provenance:** Derived from the completed multi-model review and locally reproduced on 2026-08-09 against clean worktree `HEAD` `a2a2b5cfb859c0ee6b774ebcc54dc72bbfb9e59e`. The target implementation surfaces matched `origin/main` `f951eb67c80610e7061cfa2ef77a4d46da8e08ec` at authoring time.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `.github/scripts/eco-lock.sh digest` so a valid capability `meta.yml` without optional `descriptor_ref` returns exit status `0` while preserving the exact digest bytes and keeping `.eco-registry.lock` parity unchanged.

**Architecture:** Add one focused shell regression that exercises both a meta without `descriptor_ref` and an existing plugin meta with `descriptor_ref`, then replace the short-circuit optional print inside `_digest_meta()` with an always-successful `if` block. Reuse the existing repo verifier pattern in `.github/scripts/verify-skills.sh`; do not introduce any broader shell-test framework.

**Tech Stack:** POSIX shell/Bash; existing repo script `.github/scripts/eco-lock.sh`; existing repo verifier `.github/scripts/verify-skills.sh`.

## Global Constraints

- Keep this change isolated to `.github/scripts/eco-lock.sh`, one focused shell regression, and the repo-verifier hook required to run it.
- Preserve digest bytes for both metas with and without `descriptor_ref`.
- Do not modify `.eco-registry.lock`, any `meta.yml`, or unrelated verifier behavior.
- Pair the red regression and green code fix in one reviewable slice; do not rely on a committed failing-test-only state.
- `PR 2` is separate from `PR 1` in `docs/plans/plan-refine-doctrine-hardening-v1.md`. If `PR 1` lands first, rebase onto latest `main` and preserve its `.github/scripts/verify-skills.sh` stanza.

---

## 1. Purpose

`eco-lock.sh digest` currently produces the correct SHA-256 for a valid capability meta that omits `descriptor_ref`, but exits non-zero because `_digest_meta()` ends its brace group with `[ -n "$descriptor_ref" ] && printf ...` while `pipefail` is enabled. The bug is narrow, fully reproduced, and fixable with one shell-logic change plus a focused regression. This plan keeps the scope that small.

## 2. Scope and non-goals

**In scope:**

- Add a shell regression for the reproduced failure mode.
- Fix `_digest_meta()` so optional `descriptor_ref` omission is success, not failure.
- Keep `eco-lock.sh check` and `verify-skills.sh` green after the fix.

**Explicit non-goals:**

- No lockfile rewrite or metadata normalization redesign.
- No new fixtures if existing repo files already cover the needed cases.
- No changes to unrelated `verify-skills.sh` checks.
- No cleanup of other shell idioms in `.github/scripts/eco-lock.sh`.

## 3. Background and context

These observed facts are the baseline for implementation:

- `.github/scripts/eco-lock.sh:130-153` computes the digest in `_digest_meta()`.
- `.github/scripts/verify-skills.sh:243-272` already runs explicit repo checks and is the narrowest place to wire in the regression.
- `global/skills/plan-refine/meta.yml` is a valid meta without `descriptor_ref`.
- `global/plugins/keep-awake/meta.yml` is a valid meta with `descriptor_ref`.

Observed behavior at authoring time:

- `bash .github/scripts/eco-lock.sh digest global/skills/plan-refine/meta.yml` prints `fe719f1315ce5d82ac6b57d48179ae7353b872cf675083d416b6356fdd227c36` and exits `1`.
- `bash .github/scripts/eco-lock.sh digest global/plugins/keep-awake/meta.yml` prints `12e51408252772f6c66341c5b8a8e79bbc0f11fbcae059879e847ce99d730549` and exits `0`.
- `bash .github/scripts/eco-lock.sh check` currently reports `eco-lock: OK (.eco-registry.lock in parity)`.
- `bash .github/scripts/verify-skills.sh` currently reports `verify-skills: OK (global + local + lock + capability-local)`.

## 4. File map

- Modify: `.github/scripts/eco-lock.sh:130-153`
- Create: `scripts/tests/test_eco_lock_digest.sh`
- Modify: `.github/scripts/verify-skills.sh:243-272`

## 5. Lock decomposition

- `lock-1`: reproduce the bad exit status with a focused shell regression that survives `set -e`
- `lock-2`: replace the short-circuit optional print with an always-successful conditional
- `lock-3`: run `eco-lock.sh check` and the full repo verifier unchanged after the fix

## 6. Work items

### Task 1: Add the regression and prove the current script is red

**Files:**

- Create: `scripts/tests/test_eco_lock_digest.sh`
- Modify: `.github/scripts/verify-skills.sh:243-272`

**Interfaces:**

- Consumes: existing `.github/scripts/eco-lock.sh`; existing metas `global/skills/plan-refine/meta.yml` and `global/plugins/keep-awake/meta.yml`.
- Produces: one focused shell regression and one repo-verifier stanza that can report this defect without touching lockfile generation semantics.

- [ ] **Step 1: Create the shell regression with `set -e`-safe red-status capture**

Write `scripts/tests/test_eco_lock_digest.sh` with this exact content:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
cd "$REPO"

fail=0
pass() { printf 'PASS  %s\n' "$1"; }
fail_case() { printf 'FAIL  %s\n' "$1"; fail=1; }

expect_digest_ok() {
  local meta="$1" expected="$2" label="$3" output rc
  if output="$(bash .github/scripts/eco-lock.sh digest "$meta")"; then
    rc=0
  else
    rc=$?
  fi
  if [ "$rc" -ne 0 ]; then
    fail_case "$label returned rc=$rc"
    return
  fi
  if [ "$output" = "$expected" ]; then
    pass "$label"
  else
    fail_case "$label produced $output (expected $expected)"
  fi
}

expect_digest_ok \
  "global/skills/plan-refine/meta.yml" \
  "fe719f1315ce5d82ac6b57d48179ae7353b872cf675083d416b6356fdd227c36" \
  "digest succeeds without descriptor_ref"

expect_digest_ok \
  "global/plugins/keep-awake/meta.yml" \
  "12e51408252772f6c66341c5b8a8e79bbc0f11fbcae059879e847ce99d730549" \
  "digest succeeds with descriptor_ref"

if bash .github/scripts/eco-lock.sh check >/dev/null 2>&1; then
  pass "eco-lock parity stays green"
else
  fail_case "eco-lock parity stays green"
fi

[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Run the regression first and confirm the pre-fix red result**

Run:

```bash
bash scripts/tests/test_eco_lock_digest.sh
```

Expected:

```text
FAIL  digest succeeds without descriptor_ref returned rc=1
PASS  digest succeeds with descriptor_ref
PASS  eco-lock parity stays green
```

- [ ] **Step 3: Wire the regression into the repo verifier**

Insert this stanza in `.github/scripts/verify-skills.sh` after the lock-parity check and before the capability-local tests:

```bash
if [ -x scripts/tests/test_eco_lock_digest.sh ]; then
  if bash scripts/tests/test_eco_lock_digest.sh; then
    note "PASS  eco-lock digest regression"
  else
    note "FAIL  eco-lock digest regression"
    fail=1
  fi
else
  note "FAIL  scripts/tests/test_eco_lock_digest.sh missing"
  fail=1
fi
```

- [ ] **Step 4: Run the full repo verifier and confirm the regression is the only new failure**

Run:

```bash
bash .github/scripts/verify-skills.sh
```

Expected excerpt:

```text
FAIL  eco-lock digest regression
verify-skills: FAILED
```

### Task 2: Apply the minimal green fix without changing digest bytes

**Files:**

- Modify: `.github/scripts/eco-lock.sh:138-153`

**Interfaces:**

- Consumes: Task 1's red regression.
- Produces: a zero-exit `digest` path for valid metas without `descriptor_ref`, preserving all canonical bytes.

- [ ] **Step 1: Replace the short-circuit optional print with an always-successful conditional**

Replace the tail of `_digest_meta()` in `.github/scripts/eco-lock.sh` with:

```bash
  {
    printf 'id=%s\n'                "$(_field id "$m")"
    printf 'kind=%s\n'              "$(_field kind "$m")"
    printf 'shelf=%s\n'             "$shelf"
    printf 'flavor=%s\n'            "$(_field flavor "$m")"
    printf 'scope=%s\n'             "$(_field scope "$m")"
    printf 'source_path=%s\n'       "$source_path"
    printf 'shape=%s\n'             "$shape"
    printf 'sync_policy=%s\n'       "$sync_policy"
    printf 'owner=%s\n'             "$(_field owner "$m")"
    printf 'install=%s\n'           "$(_field install "$m")"
    printf 'expose=%s\n'            "$expose"
    printf 'provenance_source=%s\n' "$(_field provenance_source "$m")"
    printf 'provenance_ref=%s\n'    "$(_field provenance_ref "$m")"
    if [ -n "$descriptor_ref" ]; then
      printf 'descriptor_ref=%s\n' "$descriptor_ref"
    fi
  } | _sha
```

- [ ] **Step 2: Re-run the focused regression and confirm both digests stay byte-identical**

Run:

```bash
bash scripts/tests/test_eco_lock_digest.sh
```

Expected:

```text
PASS  digest succeeds without descriptor_ref
PASS  digest succeeds with descriptor_ref
PASS  eco-lock parity stays green
```

- [ ] **Step 3: Re-run the direct script checks**

Run:

```bash
bash .github/scripts/eco-lock.sh digest global/skills/plan-refine/meta.yml
bash .github/scripts/eco-lock.sh digest global/plugins/keep-awake/meta.yml
bash .github/scripts/eco-lock.sh check
```

Expected:

```text
fe719f1315ce5d82ac6b57d48179ae7353b872cf675083d416b6356fdd227c36
12e51408252772f6c66341c5b8a8e79bbc0f11fbcae059879e847ce99d730549
eco-lock: OK (.eco-registry.lock in parity)
```

- [ ] **Step 4: Commit the green regression-and-fix slice**

Run:

```bash
git add .github/scripts/eco-lock.sh .github/scripts/verify-skills.sh scripts/tests/test_eco_lock_digest.sh
git commit -m "fix: keep eco-lock digest zero-exit without descriptor_ref"
```

This commit deliberately contains the red regression and the minimal green fix together; it does not rely on a separately committed failing-test-only state.

### Task 3: Re-run the full verifier and establish the second PR boundary

**Files:**

- No new files beyond Tasks 1-2.

**Interfaces:**

- Consumes: green regression plus minimal code fix.
- Produces: final verification evidence for the repo gate and an isolated `PR 2`.

- [ ] **Step 1: Run the full repo verifier**

Run:

```bash
bash .github/scripts/verify-skills.sh
```

Expected excerpt:

```text
PASS  eco-lock digest regression
verify-skills: OK (global + local + lock + capability-local)
```

- [ ] **Step 2: Record the final isolation boundary**

`PR 2` contains only:

- `.github/scripts/eco-lock.sh`
- `.github/scripts/verify-skills.sh`
- `scripts/tests/test_eco_lock_digest.sh`

No `plan-refine` doctrine files belong in this PR.

## 7. Acceptance criteria

- `bash scripts/tests/test_eco_lock_digest.sh` fails red before the fix and passes green after it.
- The red test uses an `if output="$(...)"; then rc=0; else rc=$?; fi` pattern (or equivalent) so `set -e` does not swallow the failing status.
- A valid meta without `descriptor_ref` returns exit status `0` and keeps digest `fe719f1315ce5d82ac6b57d48179ae7353b872cf675083d416b6356fdd227c36`.
- A valid meta with `descriptor_ref` still returns exit status `0` and keeps digest `12e51408252772f6c66341c5b8a8e79bbc0f11fbcae059879e847ce99d730549`.
- `bash .github/scripts/eco-lock.sh check` remains green.
- `bash .github/scripts/verify-skills.sh` remains green.
- No `.eco-registry.lock` or `meta.yml` changes are required.

## 8. Rollback

Rollback is straightforward and low-risk:

- Revert `fix: keep eco-lock digest zero-exit without descriptor_ref` to remove the regression and code fix together.
- If a later follow-up needs a different shell idiom, keep the same acceptance test and digest-byte assertions; do not delete the regression without a narrower replacement.
- No data migration or lockfile repair is required because the fix does not alter the canonical digest bytes or committed lock parity.
