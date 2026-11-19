# Context Efficiency D-02 — Skills description reduction

**Version:** v1
**Status:** ACCEPTED — 2026-08-21
**Date:** 2026-08-21
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Owner:** KleinPerkins
**Plan-type:** standard
**Program milestone:** D-02, “Scope first, then shorten Skills-owned auto-discovery descriptions.”
**Parent authority:** [`KleinPerkins/dev` Context Efficiency Program v2, Release 1.1 / D-02](https://github.com/KleinPerkins/dev/blob/0c8a3e3bc991ffad8257f6587063369a35781cf4/_ops/plans/context-efficiency-program-v2.md#release-11--reduce-capability-discovery)
**Prerequisites:** Protected-merged D-01 evidence plus E-01 and E-03 merged on Skills `main`.
**Review provenance:** Grounded against refreshed Skills `origin/main`, the protected-merged D-01 evidence, the accepted E-01/E-03 owner plans and merged implementations, the current strict inventory/verifier, all 28 D-01 target realpaths and `meta.yml` exposure declarations, the DRAFT S-02 file map, and current `agent-route` behavior.

This DRAFT is planning-only. It authorizes no description, verifier, parser, test, client-install, scope, metadata, generated-memory, or downstream projection change until the owner accepts the plan and separately gives implementation GO.

**Changelog**
- v1 (2026-08-21) — Define the scope-first, no-scope-move D-02 reduction; bind the 28 D-01 targets to their actual Skills sources; add deterministic 300/600/1,024 description budgets; and require client-native discovery canaries without colliding with S-02.

## 1. Goal

Reduce Skills-owned skill-description metadata exposed through AI client catalogs without weakening ordinary-language discovery, workspace routing, capability semantics, or owner boundaries.

Success means:

1. every one of the 28 D-01 `eligible-skills-d02` rows is bound to its actual Skills source and current `meta.yml` exposure;
2. scope is evaluated first and the current evidence supports no global-to-local move;
3. only the 15 descriptions currently over 300 normalized characters are shortened;
4. the 8 descriptions over 600 reach at most 600 characters and clear the hard gate, with the two over 1,024 also clearing the migration-failure band;
5. all 15 reduction targets reach at most 300 characters unless shortening would lose routing/discovery meaning, in which case implementation stops rather than accepting a weaker descriptor;
6. E-03’s strict YAML 1.2 Core parsing, normalization, exact-duplicate, no-partial-output, and no-fallback contracts remain authoritative;
7. fresh eligible clients still discover and identify every changed skill from ordinary language; and
8. D-02 changes no S-02 file, learned source, client exposure declaration, registry, router, runtime, or downstream payload.

## 2. Authority and exact dependency binding

This draft is bound to:

| Authority | Exact ref | Bound evidence |
|---|---|---|
| Skills live default branch | `KleinPerkins/skills` `origin/main` at `3a13f72f7054d3a7e938f7ac710e8e4699c683fb` | Clean safe worktree; current source, verifier, parser, tests, metadata, and rollback baseline |
| E-01 durable Skills source | [Plan](context-efficiency-e01-durable-skills-source-v1.md); implementation [PR #140](https://github.com/KleinPerkins/skills/pull/140), merge `2cd47ca8050aeba41409053883886c6e06f024b9` | Durable source/reconciliation behavior is merged and an ancestor of Skills `origin/main` |
| E-03 strict description eligibility | [Plan](context-efficiency-e03-description-eligibility-v1.md); implementation [PR #141](https://github.com/KleinPerkins/skills/pull/141), merge `e9e54879008a42dafcd257f67547ac207dc26531` | `skill-description-normalization/v1`, `skills-yaml12-core-profile/v1`, strict candidate discovery, exact duplicate rejection, and zero partial output are merged |
| Dev parent program | Program commit `0c8a3e3bc991ffad8257f6587063369a35781cf4`; live Dev `origin/main` observed at `618da97572a6cca9fb48ed10c2f724a893e74d1c` | Program-v2 blob `d452a49a1f4e0eac579947a9a853637138966706`; raw SHA-256 `447dbc08695a68b18d1c11fa82d1363b69a1f96cd9b25cda349cfaeb586cf2d6` |
| D-01 accepted inventory evidence | [`capability-discovery-inventory-v1.json`](https://github.com/KleinPerkins/dev/blob/618da97572a6cca9fb48ed10c2f724a893e74d1c/_ops/evidence/context-efficiency/capability-discovery-inventory-v1.json), protected-merged in [Dev PR #289](https://github.com/KleinPerkins/dev/pull/289) | Evidence commit `618da97572a6cca9fb48ed10c2f724a893e74d1c`; blob `f1aef037b70ef6f2c03b31d03c73efdf73525b0f`; raw SHA-256 `7a72a32b49ab2555d94dabc0dae9b1086bba2cc28107263f9feaa5dd17a7dd3c`; 28 eligible rows / 13,013 normalized characters |
| S-02 boundary | [DRAFT S-02 plan](context-efficiency-s02-skills-reduction-v1.md) | S-02 targets static generated/global wording, including `continual-learning-consolidate`; D-02 excludes every S-02 file |

Before implementation, refresh both repositories and reproduce every binding:

```bash
git fetch --prune origin main
test "$(git rev-parse origin/main)" = \
  "3a13f72f7054d3a7e938f7ac710e8e4699c683fb" ||
  printf '%s\n' "Skills main moved; re-adjudicate material drift"
git merge-base --is-ancestor \
  2cd47ca8050aeba41409053883886c6e06f024b9 origin/main
git merge-base --is-ancestor \
  e9e54879008a42dafcd257f67547ac207dc26531 origin/main

: "${DEV_ROOT:?set DEV_ROOT to a clean KleinPerkins/dev checkout}"
git -C "$DEV_ROOT" fetch --prune origin main
git -C "$DEV_ROOT" cat-file -e \
  "origin/main:_ops/evidence/context-efficiency/capability-discovery-inventory-v1.json"
test "$(git -C "$DEV_ROOT" rev-parse \
  'origin/main:_ops/evidence/context-efficiency/capability-discovery-inventory-v1.json')" = \
  "f1aef037b70ef6f2c03b31d03c73efdf73525b0f"
```

The literal Skills-main equality is an authoring-baseline probe, not a permanent pin. If `origin/main` advances before implementation, inspect the complete delta. Continue only when descriptor layout, E-03 contracts, D-01 target ownership, S-02 separation, verifier wiring, and client-exposure semantics remain materially unchanged; otherwise supersede this plan.

## 3. Global constraints and protected invariants

- Plan acceptance satisfies only the owner-plan gate. A separate implementation GO is required.
- Add no registry, router, daemon, runtime, service, dependency, analytics store, client adapter, or second installer/reconciliation path.
- Keep E-03’s bounded YAML 1.2 Core parser as the sole parser. No PyYAML/ambient-package path, line-parser fallback, partial rows, partial totals, or best-effort mode may satisfy the gate.
- Keep `skill-description-normalization/v1`, `skills-yaml12-core-profile/v1`, the pinned Unicode whitespace set, strict UTF-8, scalar counting, and exact normalized duplicate rejection unchanged.
- Preserve every capability’s `meta.yml`, ID, kind, flavor, scope, owner, exposure, provenance fields, descriptor reference, install contract, body, auxiliary payload, and install path except for the 15 explicitly authorized `description` values.
- Preserve Save-Game behavior, model-tier/orchestration semantics, `agent-route` workspace-routing behavior, and all capability bodies. D-02 changes catalog metadata, not operational instructions.
- `agent-route` routes workspaces, not skills. Per-skill selection proof belongs to each client’s native skill catalog. The separate `agent-route` canary covers its own client discovery and its existing workspace-routing unit contract.
- Preserve zero-link: no `cpp`, `card-platform-product`, or Affirm path/token may enter `global/` or `local/`.
- Never read, print, classify, edit, or delete `agent-learnings.md`, generated `~/AGENTS.md`, or private operator data. No learned-data access is necessary for D-02.
- Do not edit installed client projections directly. Source changes occur in Skills; machine reconciliation uses the existing Skills bootstrap only after the machine-local gate.
- Do not edit any of the 13 D-01 targets already at or below 300 characters.
- For Flavor-2 targets, the pinned provenance continues to identify the upstream base. Only the frontmatter `description` may become an owner-approved local metadata adaptation; all body and auxiliary bytes remain unchanged. Do not alter provenance fields or claim the complete local `SKILL.md` remains byte-verbatim after an approved description-only adaptation.
- `local/plugins/continual-learning/SKILL.md` is the Skills-authored local governor descriptor, not the marketplace payload. Its `descriptor_ref` binds `plugin.json`, not `SKILL.md`; D-02 changes only the governor’s `description` and never touches `plugin.json`, marketplace cache bytes, runtime writers, or `meta.yml`.
- Use one writer per tree, normal Skills hooks/checks, and the reviewer App’s merge gate. Do not mark a draft implementation PR ready prematurely, arm auto-merge, merge, approve, bypass checks, force-push, or push to `main`.

## 4. Verified current state

At the bound Skills ref:

- E-01 and E-03 implementations are merged at `2cd47c…` and `e9e548…`.
- `.github/scripts/verify-skills.sh` runs the strict E-03 test file and repository inventory for every tracked `global/**/SKILL.md` and `local/**/SKILL.md` candidate.
- `scripts/skill-description-inventory.py` discovers 29 tracked candidates, reports 13,387 normalized characters, and reports no exact normalized duplicate.
- The current script enforces YAML validity, normalization, completeness, and duplicates, but has no 300/600/1,024 budget classification or diagnostic.
- D-01’s client-observed eligible subset contains exactly 28 Skills-owned rows totaling 13,013 normalized characters. The remaining tracked candidate, `global/tools/operator-voice/payload/operator_voice/skill/SKILL.md` at 374 characters, is not a D-02 reduction target; the repo-wide budget gate will warn on it but D-02 will not edit it.
- D-01 captured Cursor exposure. Fresh D-02 canaries expand only according to each target’s current `meta.yml expose`; they do not infer Claude or Codex support from Cursor’s installed path.

### 4.1 Source/scope reconciliation

The 28 eligible installed rows resolve to:

| Source class | Count | D-02 treatment |
|---|---:|---|
| `global/skills/*/SKILL.md` | 23 | 14 over-budget descriptions are reduced; 9 compliant descriptions remain byte-identical |
| `global/plugins/keep-awake/SKILL.md` | 1 | 207 characters; byte-identical canary/input only |
| `local/plugins/continual-learning/SKILL.md` | 1 | 495 characters; reduce only the frontmatter description |
| `local/skills/*/SKILL.md` | 3 | `continual-learning-consolidate` 276, `session-close` 211, and `update-skills` 278; all remain byte-identical |

### 4.2 Exact reduction set

Severity uses the current normalized count and §6 precedence.

| Skill | Source | Current chars | Current band | `meta.yml expose` |
|---|---|---:|---|---|
| `claude-api` | `global/skills/claude-api/SKILL.md` | 1,068 | migration failure | Cursor, Claude, Codex |
| `plan-refine` | `global/skills/plan-refine/SKILL.md` | 1,060 | migration failure | Cursor, Claude, Codex |
| `xlsx` | `global/skills/xlsx/SKILL.md` | 948 | failure | Cursor, Claude, Codex |
| `save-game` | `global/skills/save-game/SKILL.md` | 928 | failure | Cursor, Claude, Codex |
| `pr-steward` | `global/skills/pr-steward/SKILL.md` | 898 | failure | Cursor |
| `capability` | `global/skills/capability/SKILL.md` | 727 | failure | Cursor, Claude, Codex |
| `agent-route` | `global/skills/agent-route/SKILL.md` | 654 | failure | Cursor, Claude, Codex |
| `swarm` | `global/skills/swarm/SKILL.md` | 625 | failure | Cursor, Claude, Codex |
| `prompt-architect` | `global/skills/prompt-architect/SKILL.md` | 534 | warning | Cursor |
| `continual-learning` | `local/plugins/continual-learning/SKILL.md` | 495 | warning | Cursor |
| `pdf` | `global/skills/pdf/SKILL.md` | 437 | warning | Cursor, Claude, Codex |
| `doc-coauthoring` | `global/skills/doc-coauthoring/SKILL.md` | 428 | warning | Cursor, Claude, Codex |
| `internal-comms` | `global/skills/internal-comms/SKILL.md` | 329 | warning | Cursor, Claude, Codex |
| `algorithmic-art` | `global/skills/algorithmic-art/SKILL.md` | 324 | warning | Cursor, Claude, Codex |
| `skill-creator` | `global/skills/skill-creator/SKILL.md` | 319 | warning | Claude |

The 13 D-01 targets already at or below 300 are `canvas-design` 289, `frontend-design` 204, `local-jobs` 291, `mcp-builder` 277, `session-close` 211, `slack-gif-creator` 227, `theme-factory` 262, `update-skills` 278, `web-artifacts-builder` 288, `webapp-testing` 204, `continual-learning-consolidate` 276, `keep-awake` 207, and `verification-before-completion` 225. They are evidence/canary inputs only and remain byte-identical.

### 4.3 Scope-first conclusion

The existing Skills paradigm defines `global/` as reusable capabilities eligible for standard downstream lifecycle handling and `local/` as operator-machine-only capabilities; per-client exposure is separately controlled by `meta.yml`.

The scope evaluation concludes:

1. the 24 currently global D-01 targets are reusable capability descriptions, and D-01 provides no evidence that demoting any one would preserve intended cross-client/downstream access;
2. the four local targets are already correctly local, including the continual-learning governor;
3. a global-to-local move would change paths, `meta.yml scope`, lock/orchestrator inputs, exposure consequences, and rollback surface outside this plan’s authorized file map; and
4. no manual-only conversion or machine-specific opt-out is valid evidence for changing repository scope.

**Decision: no scope moves; proceed to description shortening.** If implementation discovers a genuine demotion candidate, stop and supersede this plan with an exact scope-migration plan rather than widening D-02.

### 4.4 S-02 non-overlap

S-02 may touch `local/skills/continual-learning-consolidate/{scripts/**,SKILL.md,README.md}`. D-02 does not touch any of those files because `continual-learning-consolidate` is already compliant at 276 characters. S-02 does not touch `local/plugins/continual-learning`. Therefore the D-02 implementation file map and S-02 file map do not collide.

## 5. Exact scope and authorized file map

### 5.1 This plan PR

This planning PR may edit only:

- `docs/plans/context-efficiency-d02-skills-description-reduction-v1.md`
- `docs/plans/README.md`

It must not change any description, parser, verifier, test, metadata, lock, installer, client projection, or generated artifact.

### 5.2 Later implementation PR

The later D-02 implementation is limited to:

- `.github/scripts/verify-skills.sh`
- `scripts/skill-description-inventory.py`
- `scripts/tests/test_skill_description_inventory.py`
- `global/skills/agent-route/SKILL.md`
- `global/skills/algorithmic-art/SKILL.md`
- `global/skills/capability/SKILL.md`
- `global/skills/claude-api/SKILL.md`
- `global/skills/doc-coauthoring/SKILL.md`
- `global/skills/internal-comms/SKILL.md`
- `global/skills/pdf/SKILL.md`
- `global/skills/plan-refine/SKILL.md`
- `global/skills/pr-steward/SKILL.md`
- `global/skills/prompt-architect/SKILL.md`
- `global/skills/save-game/SKILL.md`
- `global/skills/skill-creator/SKILL.md`
- `global/skills/swarm/SKILL.md`
- `global/skills/xlsx/SKILL.md`
- `local/plugins/continual-learning/SKILL.md`

For each `SKILL.md`, only the parsed frontmatter `description` value may change. Every other frontmatter key/value and every byte after the closing frontmatter delimiter remain unchanged.

Read-only proof may inspect all 28 target `meta.yml`/`SKILL.md` files, the D-01 evidence, `global/skills/agent-route/tests/unit_test.py`, install links, and client catalogs. These are not additional mutation paths.

### 5.3 Out of scope

- Any `meta.yml`, `.eco-registry.lock`, `plugin.json`, `descriptor_ref`, installer, bootstrap implementation, registry, downstream copy, or orchestrator configuration.
- Every compliant D-01 source, especially all `continual-learning-consolidate` files.
- `global/tools/operator-voice/**`; its non-eligible 374-character descriptor may warn but is not reduced by D-02.
- Skill bodies, reference files, scripts, model catalogs, routing engines, Save-Game state, hooks, launchd jobs, plugin caches, client settings, or client-owned descriptors.
- CPP payloads, manual downstream vendoring, generated-lock editing, or D-04 lifecycle reconciliation.
- Learned/private source access or generated-memory output.
- General semantic deduplication, fuzzy similarity, description ranking, telemetry, or dynamic context management.

## 6. Reduction and budget contract

### 6.1 Description reduction

For each of the 15 targets:

1. parse and normalize the current value with E-03’s unchanged contracts;
2. inventory the ordinary-language intents, domain nouns, verbs, product/client names, exclusions, and trigger phrases that distinguish the skill;
3. draft the smallest description that preserves those routing signals without copying body instructions;
4. require at most 300 normalized Unicode scalar values;
5. compare exact normalized strings across the complete E-03 candidate set; and
6. run source and fresh-client canaries before acceptance.

The hard gate is at most 600 for every candidate. D-02’s candidate acceptance target is at most 300 for all 15 changed descriptions. If any target cannot reach 300 without losing discovery/routing meaning, stop and report the exact target and lost intent; do not weaken canaries, leave an unexplained warning, move the skill to local scope, or add a router.

### 6.2 Deterministic budget classification

Apply this precedence to every E-03 candidate after the complete strict inventory and duplicate check succeed:

| Normalized characters | Classification | CLI effect |
|---:|---|---|
| `0..300` | `OK` | No budget diagnostic |
| `301..600` | `DESCRIPTION_BUDGET_WARNING` | Sorted warning on stderr; exit remains `0` when no failure exists |
| `601..1024` | `DESCRIPTION_BUDGET_FAILURE` | Sorted failure on stderr; exit `3`; zero stdout |
| `1025+` | `DESCRIPTION_MIGRATION_FAILURE` | Sorted migration failure on stderr; exit `3`; zero stdout |

Threshold comparison is strictly “over”: 300, 600, and 1,024 are the upper bounds of their lower bands. Migration-failure precedence prevents one row from also emitting a generic failure.

Diagnostics are content-safe and deterministic:

```text
DESCRIPTION_BUDGET_WARNING <path>: characters=<N> limit=300
DESCRIPTION_BUDGET_FAILURE <path>: characters=<N> limit=600
DESCRIPTION_MIGRATION_FAILURE <path>: characters=<N> limit=1024
```

Sort diagnostics by raw UTF-8 path bytes. Emit counts and paths only—never normalized description text.

### 6.3 E-03 compatibility

- Preserve the successful stdout schema `skill-description-inventory/v1` byte-for-byte for an unchanged warning-free input. Do not silently mutate a versioned JSON schema.
- Build the complete strict inventory in memory before budget evaluation.
- Parser, malformed-input, unsupported-YAML, missing/non-string description, candidate-set, unreadable-source, and exact-duplicate failures remain `BLOCKED_PREREQUISITE`, exit `3`, and zero stdout.
- Budget failures are validly parsed but release-ineligible input. They also exit `3` with zero stdout so no caller can consume a failing partial inventory.
- Warning-only input emits the complete existing JSON document to stdout and deterministic warning lines to stderr.
- The CLI remains `python3 scripts/skill-description-inventory.py --repo .`; no mode flag, baseline allowlist, target registry, exemption file, or alternate parser is added.
- `.github/scripts/verify-skills.sh` continues to run the focused suite and one strict repository inventory. It must preserve stderr so warnings are visible and must let any nonzero budget result set the existing `fail=1`.
- Budget enforcement covers every tracked `global/**/SKILL.md` and `local/**/SKILL.md` candidate discovered by E-03. Eligibility controls D-02 edit scope, not parser or verifier completeness.

The current baseline should classify as 2 migration failures, 6 failures, and 8 warnings: the 15 D-02 reduction targets plus the non-target `operator-voice` warning. After all 15 reductions, the repository should exit `0` with only the pre-existing non-target `operator-voice` warning.

## 7. Work items

### Task 1: Reconfirm scope, ownership, and non-overlap before edits

**Files:**

- No source modifications
- Read-only: D-01 evidence, all target `meta.yml`/`SKILL.md` files, S-02 plan, E-03 inventory output

**Interfaces:**

- Consumes: §2 exact authorities, D-01’s 28 eligible rows, realpath/source mapping, Skills scope paradigm, and S-02 file map.
- Produces: one PR-body scope-decision table with `capability_id`, source path, current scope, current exposure, normalized count, and decision `retain-global` or `retain-local-existing`; no tracked registry.

- [ ] Refresh Skills and Dev owner refs and revalidate exact blobs/digests.
- [ ] Re-query D-01 for exactly 28 `eligible-skills-d02` rows and 13,013 characters.
- [ ] Resolve every installed path to one of the 28 approved source paths; unknown, moved, or multiply attributed source stops.
- [ ] Re-run E-03 inventory and require complete output, no duplicates, and current source counts.
- [ ] Confirm 24 targets remain global and four remain local; record `no scope moves`.
- [ ] Confirm the 15-path reduction set and 13-path byte-identical set.
- [ ] Diff S-02’s current authorized paths and require zero D-02 mutation-path intersection.
- [ ] Confirm `local/plugins/continual-learning` remains a local Skills-authored governor and its `plugin.json`/`descriptor_ref` are outside D-02.

Read-only commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/skill-description-inventory.py --repo . \
  >"${TMPDIR:-/tmp}/d02-inventory-before.json"
python3 - "${TMPDIR:-/tmp}/d02-inventory-before.json" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["normalization_contract"] == "skill-description-normalization/v1"
assert value["parser_profile"] == "skills-yaml12-core-profile/v1"
assert value["normalized_duplicates"] == []
PY
rm -f "${TMPDIR:-/tmp}/d02-inventory-before.json"
```

Before budget implementation this command exits `0`; that is baseline evidence that E-03 does not yet enforce D-02 thresholds.

### Task 2: Pin budget boundaries with failing tests

**Files:**

- Modify `scripts/tests/test_skill_description_inventory.py`
- Modify `scripts/skill-description-inventory.py` only enough to expose importable budget signatures/constants for red tests

**Interfaces:**

- Consumes: complete E-03 candidate rows and §6’s threshold/diagnostic contract.
- Produces: deterministic tests for boundary precedence, stdout suppression, warning visibility, global/local coverage, and E-03 compatibility.

- [ ] Add named constants for 300, 600, and 1,024; tests assert the exact values.
- [ ] Add table tests for counts 0, 300, 301, 600, 601, 1,024, and 1,025.
- [ ] Require exactly one classification per row with migration precedence.
- [ ] Add a mixed global/local fixture proving both scopes enter one sorted budget result.
- [ ] Add warning-only CLI coverage: exit `0`, complete existing JSON stdout, deterministic warning stderr.
- [ ] Add failure and migration-failure CLI coverage: exit `3`, zero stdout, sorted content-safe stderr.
- [ ] Add a mixed warning/failure fixture proving complete evaluation without emitting inventory stdout.
- [ ] Retain every E-03 malformed/unsupported/duplicate/no-partial-output test unchanged and green.
- [ ] Add a verifier-facing regression proving a budget failure makes the inventory invocation nonzero without any shell-side parser fallback.

Focused red command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/tests -p 'test_skill_description_inventory.py' -v
```

Expected before implementation: new budget tests fail because classification and diagnostics do not exist. Do not commit a failing-test-only state.

### Task 3: Implement one layered budget gate

**Files:**

- Modify `scripts/skill-description-inventory.py`
- Modify `scripts/tests/test_skill_description_inventory.py`
- Modify `.github/scripts/verify-skills.sh`

**Interfaces:**

- Consumes: Task 2 tests and E-03’s complete `skill-description-inventory/v1` object.
- Produces: one deterministic warning/failure layer on the existing strict inventory; unchanged candidate discovery/parser/normalizer.

- [ ] Implement budget classification only after complete parsing, normalization, and duplicate checks.
- [ ] Sort diagnostic rows by raw UTF-8 path bytes.
- [ ] Preserve successful v1 JSON bytes for warning-free fixtures.
- [ ] Emit warning-only diagnostics while retaining exit `0` and full stdout.
- [ ] Emit failure/migration diagnostics with exit `3` and zero stdout.
- [ ] Keep diagnostics free of description text and source content.
- [ ] Update the existing verifier stanza label/comment to state that strict repository inventory now includes D-02 budgets.
- [ ] Do not parse JSON or stderr in shell, add an allowlist, or duplicate thresholds in Bash.
- [ ] Prove current repository source produces 2 migration failures, 6 failures, 8 warnings, exit `3`, and zero stdout before description edits.

Focused commands:

```bash
python3 -m py_compile \
  scripts/skill-description-inventory.py \
  scripts/tests/test_skill_description_inventory.py
bash -n .github/scripts/verify-skills.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/tests -p 'test_skill_description_inventory.py' -v

out="$(mktemp)"
err="$(mktemp)"
set +e
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/skill-description-inventory.py --repo . >"$out" 2>"$err"
rc=$?
set -e
test "$rc" -eq 3
test ! -s "$out"
test "$(grep -c '^DESCRIPTION_MIGRATION_FAILURE ' "$err")" -eq 2
test "$(grep -c '^DESCRIPTION_BUDGET_FAILURE ' "$err")" -eq 6
test "$(grep -c '^DESCRIPTION_BUDGET_WARNING ' "$err")" -eq 8
rm -f "$out" "$err"
```

The repository verifier is expected red at this intermediate point. Budget code and description reductions land in one green implementation PR.

### Task 4: Shorten exactly 15 descriptions and preserve routing signals

**Files:**

- Modify only the 15 `SKILL.md` paths in §5.2

**Interfaces:**

- Consumes: per-target current normalized description, body semantics, current `meta.yml expose`, and §9 ordinary-language intent.
- Produces: 15 unique normalized descriptions of at most 300 characters, with unchanged non-description frontmatter and body bytes.

- [ ] Create a review checklist per target containing retained task nouns, action verbs, product/client names, exclusions, and trigger phrases.
- [ ] Draft each description independently; do not use a generic template that creates exact duplicates or erases distinctions.
- [ ] Reduce the eight hard-failure targets to at most 300, thereby necessarily clearing 600 and 1,024.
- [ ] Reduce the seven warning targets to at most 300.
- [ ] Change only each parsed `description` value; preserve every other frontmatter value and post-frontmatter byte.
- [ ] Preserve explicit “do not run”/assessment routing where the original description distinguishes assessment from action.
- [ ] Preserve `agent-route`’s workspace-routing, move, route-only, and wrong-root signals.
- [ ] Preserve `continual-learning`’s local governor, marketplace plugin, cadence, repair, and tracked-`AGENTS.md` safety signals without touching plugin payload/provenance.
- [ ] Re-run the inventory and require all 15 target rows at most 300 and exactly one non-target warning for `operator-voice`.
- [ ] Stop if any description cannot meet 300 without losing its §9 canary intent.

Green budget probe:

```bash
out="$(mktemp)"
err="$(mktemp)"
PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/skill-description-inventory.py --repo . >"$out" 2>"$err"
test -s "$out"
test "$(grep -c '^DESCRIPTION_BUDGET_WARNING ' "$err")" -eq 1
grep -F \
  'DESCRIPTION_BUDGET_WARNING global/tools/operator-voice/payload/operator_voice/skill/SKILL.md:' \
  "$err"
test "$(grep -c '^DESCRIPTION_BUDGET_FAILURE ' "$err" || true)" -eq 0
test "$(grep -c '^DESCRIPTION_MIGRATION_FAILURE ' "$err" || true)" -eq 0
python3 - "$out" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["normalized_duplicates"] == []
assert value["candidate_count"] == 29
PY
rm -f "$out" "$err"
```

The candidate count is bound to the current authoring baseline. If legitimate descriptors are added or removed before implementation, re-adjudicate the target and warning expectations rather than editing the assertion blindly.

### Task 5: Prove source integrity, routing, and eligible clients

**Files:**

- No files beyond §5.2
- Read-only: `global/skills/agent-route/tests/unit_test.py`, target metadata, isolated client projections

**Interfaces:**

- Consumes: exact implementation candidate, E-03/D-02 inventory, existing bootstrap, isolated HOME, and fresh eligible client processes.
- Produces: source-only integrity evidence, one workspace-routing regression result, and per-target native catalog discovery/identification evidence.

- [ ] Compare each changed file with `origin/main` and prove only the parsed description differs.
- [ ] Require all 13 compliant D-01 target files byte-identical to `origin/main`.
- [ ] Require all `meta.yml`, `plugin.json`, body, auxiliary, installer, lock, and S-02 files byte-identical to `origin/main`.
- [ ] Run `global/skills/agent-route/tests/unit_test.py` and require its existing workspace-routing contract green.
- [ ] In an isolated HOME, reconcile the candidate through the existing bootstrap; require every target link to resolve to candidate source according to `meta.yml expose`, with no extra client link.
- [ ] Run §9’s fresh Cursor, Claude, and Codex rows only for skills exposed to that client.
- [ ] For every affected skill/client pair, require catalog discovery and correct ordinary-language identification without executing the skill.
- [ ] Record client version/environment class, fresh-process proof, source path/digest, shortened normalized digest/count, prompt ID, selected skill, and pass/fail.
- [ ] Do not substitute a current chat, source test, installed-file existence, or unsupported-client claim for fresh-client evidence.

Required source gates:

```bash
python3 -m py_compile \
  scripts/skill-description-inventory.py \
  scripts/tests/test_skill_description_inventory.py
bash -n .github/scripts/verify-skills.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/tests -p 'test_skill_description_inventory.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 \
  global/skills/agent-route/tests/unit_test.py
bash .github/scripts/verify-skills.sh
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check .
git diff --check
```

### Task 6: Deliver the implementation and reconcile only after gates

**Files:**

- No files beyond §5.2

**Interfaces:**

- Consumes: green exact implementation candidate, owner acceptance, protected Skills merge, machine-local dry-run, and explicit machine-local GO.
- Produces: merged Skills source, reconciled client links, fresh-client receipts, and D-04 handoff evidence.

- [ ] Commit with normal hooks and a concise why-focused message.
- [ ] Open one governed DRAFT Skills PR with exact changed-file list, before/after counts, budget diagnostics, source-integrity proof, canary matrix, rollback, and stop conditions.
- [ ] Run Bugbot and fix all in-scope findings; do not widen scope.
- [ ] Require exact-head `pr-automation / verify` green and reviewer-App governance.
- [ ] Stop for owner acceptance; do not mark ready, merge, or arm auto-merge.
- [ ] After protected merge, verify exact merged commit and rerun all source gates.
- [ ] Preview the normal machine reconcile:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile --dry-run
```

- [ ] Obtain explicit machine-local GO naming the merged commit and dry-run before apply.
- [ ] Apply only through `bootstrap.sh --reconcile`, prove second-run convergence, restart eligible clients, and run §9.
- [ ] Hand exact owner refs/digests/counts/client results to D-04; do not hand-vendor or edit generated locks.

## 8. Approval, owner, exact-digest, release, and machine-local gates

| Gate | Required evidence and authority | Failure behavior |
|---|---|---|
| Dependency/ref gate | Skills main, E-01/E-03 ancestry, program blob/digest, and D-01 evidence blob/digest remain valid | Stop; revise or supersede |
| Owner-plan gate | Operator accepts this DRAFT under Skills plan governance; accepted v1 bytes freeze | No implementation while DRAFT |
| Scope-decision gate | Exact 28-row source/scope/exposure map; explicit no-scope-move result; zero S-02 mutation overlap | Stop on demotion proposal, unknown source, or overlap |
| Test/contract gate | Red budget tests demonstrate missing behavior; green exact boundaries and E-03 compatibility | No source reductions accepted without biting tests |
| Exact-candidate gate | Exact head plus SHA-256/count map for verifier, parser, test, and 15 descriptions; non-description byte proof | Any byte/ref change revokes candidate approval |
| Owner PR gate | Exact-head `pr-automation / verify` and reviewer-App governance | No merge or downstream use |
| Release-GO gate | No separate Skills semver release; explicit owner approval treats the exact protected merge as D-02 source | Keep merged candidate unreconciled locally |
| Machine-local gate | Operator approves exact merged commit and bootstrap dry-run | No HOME/client projection mutation |
| Live-client gate | Every eligible §9 pair passes in a fresh client | Stop rollout; revert/reconcile prior source |
| D-04 handoff gate | Exact merged source/install digests, budget result, canaries, and rollback ref handed to standard lifecycle owners | D-04 remains blocked |

Acceptance of this plan satisfies only the owner-plan gate.

## 9. Fresh-client evidence rows

### 9.1 Ordinary-language identification intents

Every prompt ends with “do not run it.” The client must identify the named skill from its native catalog, not from a prompt-supplied skill name.

| Skill | Ordinary-language intent |
|---|---|
| `agent-route` | Which skill moves this session to the right workspace when the current repository is wrong? |
| `algorithmic-art` | Which skill creates seeded generative art with p5.js? |
| `capability` | Which skill helps a non-technical operator view, add, update, remove, or repair capabilities? |
| `claude-api` | Which skill helps build with the Claude API or Anthropic SDK and current model parameters? |
| `continual-learning` | Which skill checks or repairs the local continual-learning plugin, cadence, and tracked-memory safety? |
| `doc-coauthoring` | Which skill guides a structured workflow for coauthoring a document? |
| `internal-comms` | Which skill helps draft internal company communications? |
| `pdf` | Which skill handles reading, creating, editing, or combining PDF files? |
| `plan-refine` | Which skill hardens a not-yet-implemented build plan before coding? |
| `pr-steward` | Which skill asynchronously babysits pull requests opened during this session? |
| `prompt-architect` | Which skill analyzes and improves a prompt using structured frameworks? |
| `save-game` | Which skill saves or resumes durable execution state across sessions? |
| `skill-creator` | Which skill creates or improves an agent skill and evaluates its quality? |
| `swarm` | Which skill launches a bounded multi-agent review of a plan or change? |
| `xlsx` | Which skill handles spreadsheet files as the primary input or output? |

### 9.2 Client cohorts

| Client / fresh cohort | Affected skills required by current `meta.yml expose` | Required evidence |
|---|---|---|
| Cursor Desktop, fresh Dev root/chat | `agent-route`, `algorithmic-art`, `capability`, `claude-api`, `continual-learning`, `doc-coauthoring`, `internal-comms`, `pdf`, `plan-refine`, `pr-steward`, `prompt-architect`, `save-game`, `swarm`, `xlsx` | Each appears in the native skill catalog and each §9.1 prompt identifies the expected skill without executing it. `agent-route` additionally passes its existing unit contract and a harmless route-only fixture proves workspace routing, not skill routing. |
| Claude, fresh process | `agent-route`, `algorithmic-art`, `capability`, `claude-api`, `doc-coauthoring`, `internal-comms`, `pdf`, `plan-refine`, `save-game`, `skill-creator`, `swarm`, `xlsx` | Each is discovered from the approved source and each §9.1 prompt identifies the expected skill without loading an unsupported client or taking action. |
| Codex, fresh process | `agent-route`, `algorithmic-art`, `capability`, `claude-api`, `doc-coauthoring`, `internal-comms`, `pdf`, `plan-refine`, `save-game`, `swarm`, `xlsx` | Each is discovered from the approved source and each §9.1 prompt identifies the expected skill without action. No Codex claim is made for Cursor-only `continual-learning`, `pr-steward`, or `prompt-architect`, or Claude-only `skill-creator`. |

Cursor Cloud is not claimed because these are user-home Skills projections unless a later product-specific closure plan proves Cloud eligibility. Current-chat recognition is not fresh-client evidence.

## 10. Acceptance criteria and D-02 definition of done

- The exact parent program and D-01 evidence blobs/digests are revalidated.
- E-01 and E-03 implementation commits remain ancestors of the implementation base.
- Scope is evaluated first and concludes no moves; every `meta.yml scope`/`expose` value remains unchanged.
- The D-02 implementation touches only §5.2 paths.
- D-02 touches no S-02 file; every `continual-learning-consolidate` file remains byte-identical.
- All 13 compliant D-01 descriptors remain byte-identical.
- Exactly 15 descriptions change, and only their parsed description values change.
- All 15 changed descriptions are unique after E-03 normalization and at most 300 characters.
- Every tracked global/local candidate passes E-03 parsing/normalization/duplicate checks.
- Counts 301–600 warn, 601–1,024 fail, and 1,025+ migration-fail with deterministic precedence and boundary tests.
- Failure/migration input exits `3` with zero stdout; warning-only input exits `0` with complete unchanged v1 JSON and deterministic stderr.
- The final exact candidate has no D-02 target warning/failure. Only the non-target `operator-voice` 374-character warning remains.
- `verify-skills.sh`, focused tests, repository inventory, `agent-route` unit contract, zero-link, doc-warden, and diff checks pass.
- Every affected skill passes native catalog discovery and ordinary-language identification on every client named by its current `meta.yml expose`.
- No unsupported Codex/Claude/Cursor claim, current-chat substitution, or source-file-presence substitution appears in evidence.
- No registry, parser fallback, router, runtime, dependency, metadata change, manual downstream vendoring, learned-data access, or generated-memory write is introduced.
- Rollback is proven against the prior Skills source and existing bootstrap reconciliation.
- Exact protected merge and client evidence are ready for D-04’s standard lifecycle handoff.

## 11. Clean-state receipts

Before implementation edits:

```bash
git fetch --prune origin main
git status --short
git rev-parse origin/main
git diff --check
```

Expected: empty status, reviewed fresh base, and no diff errors.

Before the implementation PR:

```bash
git status --short
git diff --check
git diff --name-only origin/main...HEAD
git rev-parse HEAD
bash .github/scripts/verify-skills.sh
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check .
```

Expected changed-file set:

```text
.github/scripts/verify-skills.sh
global/skills/agent-route/SKILL.md
global/skills/algorithmic-art/SKILL.md
global/skills/capability/SKILL.md
global/skills/claude-api/SKILL.md
global/skills/doc-coauthoring/SKILL.md
global/skills/internal-comms/SKILL.md
global/skills/pdf/SKILL.md
global/skills/plan-refine/SKILL.md
global/skills/pr-steward/SKILL.md
global/skills/prompt-architect/SKILL.md
global/skills/save-game/SKILL.md
global/skills/skill-creator/SKILL.md
global/skills/swarm/SKILL.md
global/skills/xlsx/SKILL.md
local/plugins/continual-learning/SKILL.md
scripts/skill-description-inventory.py
scripts/tests/test_skill_description_inventory.py
```

The implementation receipt records exact head/merge; changed-file SHA-256 values; per-target before/after normalized count/digest; parser/test/verifier digests; unchanged metadata/body/S-02 proofs; command exits; remote Check names; client versions/cohorts/results; machine reconcile result; and rollback ref. It contains no description text, learned content, private data, credentials, or raw client context.

This plan PR itself must show exactly:

```text
docs/plans/README.md
docs/plans/context-efficiency-d02-skills-description-reduction-v1.md
```

## 12. Rollout and rollback

Roll out in this order:

1. accepted owner plan;
2. separate implementation GO;
3. scope/ref revalidation and red budget tests;
4. one exact green implementation candidate;
5. governed DRAFT Skills PR, Bugbot, exact-head checks, and owner acceptance;
6. protected merge;
7. exact merged-source revalidation;
8. operator-approved bootstrap dry-run and machine-local GO;
9. normal Skills reconciliation and second-run convergence;
10. fresh eligible-client canaries; and
11. D-04 standard lifecycle handoff.

Before merge, rollback is closing the draft implementation PR and deleting its branch. After merge but before machine reconciliation, use a governed revert of the implementation PR and treat D-02 as incomplete.

After machine reconciliation:

1. governed-revert the D-02 implementation or advance to a separately accepted corrective commit;
2. restore the established Skills primary to the approved prior commit;
3. run `bootstrap.sh --reconcile --dry-run`, obtain machine-local rollback GO, then run `bootstrap.sh --reconcile`;
4. prove target links and descriptions resolve to the prior approved source;
5. restart affected clients and rerun the eligible canaries; and
6. record the rollback ref/digests/results for D-04.

Exposure is not expected to change. Rollback nevertheless verifies source and exposure parity against the pre-D-02 ref. Never hand-edit client links, plugin caches, CPP payloads, generated locks, or learned data.

Closing or reverting this DRAFT plan PR changes no runtime state. Once accepted, v1 is byte-immutable; a material revision requires `context-efficiency-d02-skills-description-reduction-v2.md` with `Supersedes:`.

## 13. Stop conditions

Stop if:

- the parent program, D-01 evidence, E-01/E-03 ancestry, source mapping, owner attribution, or exact digests cannot be revalidated;
- any D-01 target resolves outside the approved Skills source or has ambiguous ownership;
- a global-to-local move appears necessary or beneficial, or a manual-only conversion is proposed without separate authority;
- any D-02 mutation path overlaps S-02, including any `continual-learning-consolidate` file;
- a target cannot reach 300 characters without losing a §9 routing/discovery intent;
- `agent-route` workspace routing regresses or is incorrectly repurposed as a skill router;
- a fresh eligible client cannot discover or identify a changed skill;
- a parser fallback, partial inventory, baseline exemption, target registry, new router/runtime, or third-party dependency is proposed;
- an E-03 parser/normalization/duplicate invariant must change;
- `local/plugins/continual-learning` reduction would touch plugin payload, `plugin.json`, `descriptor_ref`, cache/runtime behavior, or learned data;
- Flavor-2 provenance fields, skill bodies, auxiliary payloads, metadata, exposure, install paths, or compliant descriptions would change;
- zero-link fails or downstream reconciliation would require manual CPP vendoring/generated-lock edits;
- repository-owned focused/full checks or exact-head remote checks are red;
- machine-local GO is absent before client reconciliation; or
- rollback source, exposure, link, or fresh-client proof cannot be demonstrated.
