# Context Efficiency S-02 — Skills generated/global reduction

**Version:** v1
**Status:** ACCEPTED
**Date:** 2026-08-20
**Owning repository:** `KleinPerkins/skills`
**Owner:** KleinPerkins
**Plan-type:** standard
**Parent authority:** `KleinPerkins/dev` `_ops/plans/context-efficiency-program-v2.md` Release 1 / S-02
**Prerequisite evidence:** `KleinPerkins/dev` E-09 protected-merged in PR #283, squash `84f9a314c9d4165d232d19f3557a271eb5851350`

This plan is ACCEPTED; its Skills-owned Release 1 generated/global reduction is implemented, merged ([PR #152](https://github.com/KleinPerkins/skills/pull/152)), and PASS-evidenced in the Release-1 record `_ops/evidence/context-efficiency/release1-static-reduction-v1.json` in `KleinPerkins/dev`.

**Changelog**
- v1 (2026-08-20) — Establish the narrow S-02 plan for reducing Skills-owned generated/global projections after the protected E-09 denominator.

## 1. Goal

Reduce Skills-owned contribution to the E-09 seven-payload denominator while preserving routing behavior, model-tier behavior, and every learned source bullet represented in the generated home projection.

Success means:

1. `subagent-orchestration` is smaller without weakening model selection, sync/async, fleet stewardship, cleanup, or subagent-output rules;
2. `generated-home-agents` is smaller only through accepted generator/template improvements that preserve all learned facts and user preferences;
3. any real-home generated-memory candidate is produced only after a separate private machine GO; and
4. the later Dev S-04 measurement can compare against the protected E-09 receipt without changing workload identity.

## 2. Exact Scope

E-09 Skills-owned baseline rows:

| Projection | Source file | Installed E-09 path | E-09 characters | E-09 words |
|---|---|---|---:|---:|
| `generated-home-agents` | `local/skills/continual-learning-consolidate/scripts/continual_learning_consolidate.py` | `/Users/laurence.duggan/AGENTS.md` | 22,817 | 2,981 |
| `subagent-orchestration` | `global/rules/subagent-orchestration/subagent-orchestration.mdc` | `/Users/laurence.duggan/.cursor/rules/subagent-orchestration.mdc` | 2,907 | 414 |

Authorized implementation files:

- `global/rules/subagent-orchestration/subagent-orchestration.mdc`
- `global/rules/subagent-orchestration/model-tiers.json` only if a test proves the prose cannot preserve the catalog contract without a source-of-truth pointer update
- `global/rules/subagent-orchestration/tests/**`
- `local/skills/continual-learning-consolidate/scripts/continual_learning_consolidate.py`
- `local/skills/continual-learning-consolidate/scripts/lib/memory.py`
- `local/skills/continual-learning-consolidate/tests/**`
- `local/skills/continual-learning-consolidate/README.md` and `SKILL.md` only if made stale by implementation
- `docs/plans/README.md` for this plan's lifecycle row

Out of scope:

- Any direct/manual edit to `~/AGENTS.md`, `~/agent-learnings.md`, workspace `agent-learnings.md`, Cursor transcript files, or generated-memory source files during plan acceptance or source implementation. A later real-home `~/AGENTS.md` write is allowed only through the gated `continual-learning-consolidate` generator path in §4-§6.
- Dev-owned rules, AWA-owned rules, CPP payloads, local job schedules, or client settings.
- Changing `agent-route` semantics except as a canary dependency invoked by existing tools.
- Adding registries, stores, services, dependencies, or networked measurement.

## 3. Semantic Inventory

### `subagent-orchestration`

Must preserve:

- the economy / standard / deep tier rubric and concrete model-catalog requirement;
- no lazy inheritance for subagents when a tier should be selected;
- sync vs async rules, including no backgrounding answer-critical work;
- smallest sufficient fleet and no blind polling;
- worker cleanup responsibility and orchestrator intervention when cleanup fails;
- `/swarm` reservation and role routing compatibility.

Reduction direction:

- Move repeated rationale into short rules.
- Replace examples that restate the same constraint with one precise example.
- Point to `model-tiers.json` for catalog data instead of repeating catalog prose.

### `generated-home-agents`

Must preserve:

- every durable learned user preference and workspace fact represented by the current private source set;
- separation between hand-authored `agent-learnings.md` and generated `~/AGENTS.md`;
- privacy gate behavior, secret scanning, deterministic ordering, duplicate suppression, dry-run behavior, and atomic write/restore semantics;
- exact `continual-learning-consolidate --dry-run --json` reporting needed for E-09/S-04 evidence;
- no generated output write before all validation and scanning passes.

Reduction direction:

- Remove generator-emitted boilerplate that does not carry a learned fact.
- Prefer concise section framing over repeated long sentences.
- Deduplicate semantically identical learned facts while retaining the source-backed fact once.
- Keep every fact recoverable in the generated output; do not replace learned facts with vague pointers.

## 4. Implementation Plan

1. Reconfirm `KleinPerkins/dev` `main` contains protected E-09 evidence PR #283 and record the Skills-owned E-09 row hashes.
2. Create a clean Skills writer branch from `origin/main`; do not use the dirty primary checkout.
3. For `subagent-orchestration`, make source-only prose reductions and update/add tests if any behavioral contract moves from prose into `model-tiers.json` or a pointer.
4. For `generated-home-agents`, first use isolated `HOME` fixtures only. Prove the generator can emit a smaller output while preserving every fixture fact and while keeping dry-run/no-write behavior.
5. Stop for a separate private machine GO before running any real-home generated-memory candidate that reads actual `agent-learnings.md` sources or evaluates a candidate `~/AGENTS.md`.
6. After the private GO, run only dry-run first. If dry-run reports a candidate reduction with preserved source count and no scanner warnings, ask for an exact-digest gate before any real write.
7. If an exact-digest gate is approved, run the generator once, capture content-free before/after digests and counts, and immediately verify restore/re-run behavior.
8. Reinstall/reconcile Skills-projected rules through the standard Skills bootstrap/update path. Do not hand-edit installed Cursor files.
9. Build PR evidence that reports only counts, digests, source counts, test results, canaries, and semantic-invariant checklist results. No learned text or private paths beyond the already-approved E-09 logical paths enters the PR.

## 5. Private and Exact-Digest Gates

S-02 has two independent gates:

1. **Private machine GO:** required before reading actual learned sources for a candidate beyond the already approved E-09 dry-run metadata.
2. **Exact-digest GO:** required before writing any real `~/AGENTS.md` candidate. The gate must name the candidate output SHA-256, source-count, unique source-digest count, pre-image SHA-256, rollback artifact, and command.

Without both gates, implementation may modify only source code, docs, tests, and isolated fixtures.

## 6. Verification

Required source checks:

```bash
git status --short --branch
python3 global/rules/subagent-orchestration/verify_model_tiers.py
python3 -m unittest discover -s global/rules/subagent-orchestration/tests -p 'test_*.py'
python3 local/skills/continual-learning-consolidate/tests/test_consolidator.py
bash local/skills/continual-learning-consolidate/tests/integration_install.sh
bash .github/scripts/verify-skills.sh
"$HOME/dev/_ops/bin/doc-warden.sh" check .
git diff --check
```

Required generated-memory checks after the separate private gates:

```bash
continual-learning-consolidate --dry-run --json
continual-learning-consolidate --json
continual-learning-consolidate --dry-run --json
```

The final dry-run must report `changed=false`, the approved source count, zero scanner warnings, and the approved output digest.

Required canaries:

- Fresh Cursor/Codex/Claude routing can still discover `subagent-orchestration`.
- A same-repository implementation prompt still selects a concrete model tier rather than inheriting lazily.
- A prompt asking to run a background reviewer does not claim completion before reviewer output returns.
- A generated-memory restore rehearsal can restore the pre-image from the rollback artifact and then reapply the candidate.

## 7. Rollback

Before merge, close the implementation PR and delete the branch.

After merge, revert the Skills implementation PR and rerun the standard Skills install/update path. If real-home generated memory was written, restore the protected pre-image artifact, rerun `continual-learning-consolidate --dry-run --json`, and verify `changed=false` against the restored digest. Never rewrite the protected Dev E-09 evidence.

## 8. Stop Conditions

Stop if:

- E-09 evidence is missing, not protected-merged, or no longer matches the approved Skills-owned baseline rows;
- isolated fixtures show lost learned facts, changed ordering invariants, or reduced scanner coverage;
- private-source access is needed before the separate private machine GO;
- exact output digest approval is absent before a real generated-memory write;
- any client loses subagent routing/model-tier behavior;
- implementation would require direct edits outside Skills source/control surfaces; or
- S-01/S-02 together cannot plausibly reach the 30% Release 1 target without AWA S-03.
