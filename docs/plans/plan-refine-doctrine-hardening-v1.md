# plan-refine doctrine hardening — remove lifecycle ambiguity, tighten authorization, and make review routing deterministic

**Version:** v1
**Status:** ACCEPTED — 2026-08-09
**Date:** 2026-08-09
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Review provenance:** Derived from the completed multi-model review of the merged `plan-refine` capability and its adjacent `swarm` authority/protocol/reporting contracts on 2026-08-09. Baseline evidence for this draft was re-verified against clean worktree `HEAD` `a2a2b5cfb859c0ee6b774ebcc54dc72bbfb9e59e` plus `origin/main` `f951eb67c80610e7061cfa2ef77a4d46da8e08ec`; the target planning surfaces matched `origin/main` at authoring time.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `global/skills/plan-refine/SKILL.md` so the written contract unambiguously distinguishes mutable draft versus accepted immutable plans, assessment-only versus edit authority, deterministic standalone versus swarm routing, least-privilege authorization, and evidence-based ready-for-approval reporting without expanding the capability beyond pre-implementation plan hardening.

**Architecture:** Keep the implementation intentionally small: edit `SKILL.md` only in the sections whose doctrine was called out by review, pin that doctrine with a static `unittest` contract test that validates the written skill text rather than model runtime behavior, and wire the test into the existing repo verifier. This is deliberately not a generalized eval framework because `plan-refine` is a markdown capability, not a Python engine.

**Tech Stack:** Markdown skill contract; Python `unittest`; existing repo verifier `.github/scripts/verify-skills.sh`.

## Global Constraints

- Do not change `global/skills/plan-refine/meta.yml`, `global/skills/plan-refine/install.sh`, `.eco-registry.lock`, or any installer/provenance/exposure surface.
- Keep `plan-refine` strictly pre-implementation and read/write-limited to the target plan only.
- Honor the repo plan convention from `docs/plans/README.md`: drafts may mutate in place; accepted plans require a successor `-vN` file and README index update.
- Do not add a generalized evaluation framework or model harness; use the smallest durable doctrine contract test.
- Preserve `swarm`'s existing reviewer/verifier authority model; `plan-refine` may pass read-only instructions into `/swarm`, but reviewers never edit.
- `PR 1` in this plan and `PR 2` in `docs/plans/eco-lock-digest-exit-status-v1.md` both touch `.github/scripts/verify-skills.sh`; whichever lands second must keep the first stanza intact when rebasing onto latest `main`.

---

## 1. Purpose

`plan-refine` is already the repo's pre-implementation plan-hardening capability, but its current doctrine leaves material ambiguity in four areas that reviewers agreed are implementation-risky: which plan artifact may mutate and when, whether assessment-only prompts silently version or edit, when standalone review must escalate to `/swarm`, and what evidence/uncertainty bars a "ready for approval" verdict. This plan closes those gaps while preserving the capability's lean scope and its existing four-test methodology.

## 2. Scope and non-goals

**In scope:**

- Harden the written doctrine in `global/skills/plan-refine/SKILL.md`.
- Add one focused doctrine-contract test file that asserts the written contract stays present.
- Extend `.github/scripts/verify-skills.sh` just enough to run that doctrine-contract test.

**Explicit non-goals:**

- No changes to `meta.yml`, `install.sh`, exposure, provenance, or `.eco-registry.lock`.
- No sibling backlink requirement.
- No generalized discovery engine or recency-ranking algorithm for target-plan selection.
- No wholesale rewrite of the four-test method.
- No claim that substring/regex assertions prove model execution behavior; the test only proves the written doctrine stays pinned.

## 3. Background and context

The implementation in this repo today is spread across these surfaces:

- `global/skills/plan-refine/SKILL.md:1-202` — the doctrine to harden.
- `global/skills/swarm/SKILL.md:1-120` — explicit swarm-trigger and verifier-gate authority that `plan-refine` must not contradict.
- `global/skills/swarm/references/authority.md:1-95` — default-deny action authority, verifier gate, and ship gate.
- `global/skills/swarm/references/protocol.md:1-240` — reviewer/verifier payloads and the rule that reviewers return findings only.
- `global/skills/swarm/references/report.md:1-70` — residual uncertainty, coverage, and not-evaluated reporting doctrine.
- `docs/plans/README.md:5-21` — governed repo convention for mutable drafts versus immutable accepted plans.
- `.github/scripts/verify-skills.sh:19-32,243-272` — existing explicit repo-verifier pattern to extend.

The baseline facts that must remain true after implementation:

- `plan-refine` stays a pre-implementation skill that may only edit the target plan.
- `/swarm` remains explicit-intent-only and default-deny; `plan-refine` may recommend it, but must ask first if the operator did not explicitly request it.
- Residual uncertainty and missing evidence must remain operator-visible and able to block a ready verdict.

## 4. File map

- Modify: `global/skills/plan-refine/SKILL.md:1-16,29-76,116-125,141-202`
- Create: `global/skills/plan-refine/tests/test_skill_contract.py`
- Modify: `.github/scripts/verify-skills.sh:19-32,243-272`

## 5. Lock decomposition

- `lock-1`: lifecycle, target selection, and least-privilege preflight
- `lock-2`: deterministic Mode A versus Mode B routing and swarm integration
- `lock-3`: evidence, residual uncertainty, and approval-gated reporting
- `lock-4`: focused doctrine regression coverage plus verifier hook

## 6. Work items

### Task 1: Pin lifecycle, target-selection, and authorization doctrine

**Files:**

- Modify: `global/skills/plan-refine/SKILL.md:1-16,29-49,116-125,163-179,194-201`
- Create: `global/skills/plan-refine/tests/test_skill_contract.py`
- Modify: `.github/scripts/verify-skills.sh:19-32`

**Interfaces:**

- Consumes: existing `SKILL.md` doctrine; repo plan convention from `docs/plans/README.md`; existing verifier output style from `.github/scripts/verify-skills.sh`.
- Produces: stable written contract text for lifecycle/authorization rules; a doctrine-contract test runner that later tasks extend.

- [ ] **Step 1: Create the initial doctrine-contract test with the lifecycle/authorization scenarios only**

Write `global/skills/plan-refine/tests/test_skill_contract.py` with this exact starting content:

```python
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def must_have(case: unittest.TestCase, pattern: str) -> None:
    case.assertRegex(SKILL, re.compile(pattern, re.MULTILINE | re.DOTALL))


class PlanRefineDoctrineContractTests(unittest.TestCase):
    """These tests pin the written contract in SKILL.md.

    They do NOT claim to validate model runtime behavior. They only ensure the
    doctrine text covering the reviewed scenarios remains present and mutually
    consistent.
    """

    def test_scenario_mutable_draft_and_versioned_plan_edit_in_place(self):
        must_have(self, r"Draft/mutable plan: edit in place")
        must_have(self, r"advance the in-file version marker")

    def test_scenario_accepted_plan_is_immutable_and_requires_successor_file(self):
        must_have(self, r"Accepted/immutable plan")
        must_have(self, r"create the next convention-required successor file")
        must_have(self, r"update the README index row")

    def test_scenario_assessment_only_request_is_read_only(self):
        must_have(self, r'Assessment-only requests such as "review" or "is this ready\?" must not silently edit')
        must_have(self, r"return findings and proposed changes without mutating")

    def test_scenario_implementation_started_routes_elsewhere(self):
        must_have(self, r"Verify the target plan is still pre-implementation")
        must_have(self, r"if implementation has already started, stop this workflow")

    def test_scenario_policy_denies_access_despite_approval(self):
        must_have(self, r"project-policy-derived authorization")
        must_have(self, r"approval never substitutes for actual authorization")
        must_have(self, r"least privilege")

    def test_scenario_retention_copy_is_narrow_and_parallel_forks_stay_forbidden(self):
        must_have(self, r"narrow retention-copy exception")
        must_have(self, r"byte-identical prior version")
        must_have(self, r"forbid unrelated or divergent parallel plan forks")

    def test_multiple_plausible_target_plans_require_a_question(self):
        must_have(self, r"If multiple plausible target plans exist, ask rather than ranking by recency")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new lifecycle/authorization test and confirm it fails before doctrine edits**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
```

Expected:

```text
FAIL: test_scenario_mutable_draft_and_versioned_plan_edit_in_place
FAIL: test_scenario_accepted_plan_is_immutable_and_requires_successor_file
FAIL: test_scenario_assessment_only_request_is_read_only
FAIL: test_scenario_implementation_started_routes_elsewhere
FAIL: test_scenario_policy_denies_access_despite_approval
FAIL: test_scenario_retention_copy_is_narrow_and_parallel_forks_stay_forbidden
FAIL: test_multiple_plausible_target_plans_require_a_question
```

- [ ] **Step 3: Replace the frontmatter description and section 1 text with the reviewed doctrine**

Replace `global/skills/plan-refine/SKILL.md:1-16` with:

```md
---
name: plan-refine
description: >-
 Harden and refine a not-yet-implemented build/design plan before any code is
 written, advancing it within the project's own plan convention via an ordered
 four-test methodology: re-verify every fact against ground truth, resolve every
 gap/flaw, cut over-engineering, and expand under-scoping for the system's real
 operators. Strictly pre-implementation: assessment-only requests stay read-only;
 explicit hardening/edit requests may mutate only the governed target plan
 artifact. Runs standalone for small/low-risk plans, or provides the review
 doctrine for /swarm on large/high-risk ones after explicit operator consent.
 Use whenever the user wants to review, harden, stress-test, pressure-test,
 tighten, upgrade, finalize, or improve a plan, spec, RFC, design doc, or
 roadmap before implementing it — e.g. "harden this plan", "review and improve
 the plan", "upgrade this plan from v2 to v3", "is this plan ready to
 implement", "pressure-test my plan", "harden this plan with the swarm" — even
 if this skill is not named explicitly.
---
```

Replace `global/skills/plan-refine/SKILL.md:29-49` with:

```md
## 1. Take the target plan and establish ground truth

1. **Target plan.** Use the plan path if given as an argument; otherwise identify
 the governed repo plan the operator is discussing (the active plan file, a plan
 under `docs/plans/`, or the project convention's equivalent). If multiple
 plausible target plans exist, ask rather than ranking by recency. Read the
 target plan in full first — it is the only artifact this skill may mutate.
2. **Ground-truth baseline.** Determine the authoritative baseline to verify facts
 against — the repository's default branch / `origin/main` / the ref the plan
 targets — not merely whatever is checked out. The working tree may not match
 it; verify against the baseline and its actual files unless you first confirm
 the tree matches.
3. **Prior work is a strong prior, not gospel.** Prior audits, reviews,
 transcripts, or "verified" markings inform you but do not excuse re-checking;
 re-verify everything yourself.
4. **Domain conventions to measure against.** Discover the project's operator /
 maintenance model and governing policy from its own docs (for example
 `_ops/POLICY.md`, `AGENTS.md`, `CONTRIBUTING`, runbooks, and plan/ADR authoring
 conventions such as `docs/plans/` and `docs/adr/`). If none exist, ask the
 operator briefly. You will measure gaps and expansions against these, not
 taste.
5. **Preflight state and intent.** Verify the target plan is still
 pre-implementation. If implementation has already started, stop this workflow
 and say to switch to implementation follow-through or change review instead.
 Assessment-only requests such as "review" or "is this ready?" must not silently
 edit, version, or fork the plan; return findings and proposed changes without
 mutating. Only explicit hardening/edit authority permits mutation.
```

- [ ] **Step 4: Replace the authorization clause and plan-editing discipline with least-privilege lifecycle rules**

Replace `global/skills/plan-refine/SKILL.md:116-125` with:

```md
**Authorization + safeguard clause (apply wherever the plan grants a stateful or
self-service action):** require (i) plain-language operator visibility into and
control over the affected state, and (ii) an explicit authorization model stated
plainly and derived from project policy and live repository/tool access. Use
least privilege: approval never substitutes for actual authorization, and no
reviewer/admin/generalized doctrine may expand access beyond what the project
policy already grants. If policy or live access denies read or write, report the
limit honestly and do not escalate by doctrine. Any affordance with a known cost
must be paired with a concrete, justified safeguard (a bound, a rate limit, an
approval/admin step, or a restriction to specific states) rather than added
while ignoring that cost.
```

Replace `global/skills/plan-refine/SKILL.md:163-179` with:

```md
## 7. Read-only and plan-editing discipline

- DO investigate freely read-only: file reads, read-only git and gh/API calls,
 and doc fetches are how you re-verify facts.
- DO apply the repo's own plan lifecycle convention. Draft/mutable plan: edit in
 place and advance the in-file version marker according to section 1, item 4
 (`§1.4`). Accepted/immutable plan: create the next convention-required
 successor file instead of mutating the accepted artifact, and update the README
 index row (or equivalent plan index) as part of that successor cut.
- DO allow a narrow retention-copy exception only when the operator or project
 convention requires a byte-identical prior version preserved separately before
 mutation.
- DO keep version layers aligned: the filename suffix (`-vN`), body marker
 (`Version:`), and plan index entry must describe the same revision.
- DO keep the plan lean: put rationale and justification in your chat report, not
 in the plan — unless a future zero-context executor genuinely needs that
 context to avoid reverting a deliberate choice.
- DON'T write, create, or delete any file other than the governed target plan and
 its convention-required successor/index artifact. No code, skill, workflow,
 config, doc, or governance files beyond that narrow plan surface.
- DON'T fork unrelated or divergent parallel plan branches; successor versions
 and the narrow retention-copy exception are the only allowed multi-file plan
 shapes.
- DON'T commit, push, merge, or mutate branch protection, rulesets, or any live
 system; nothing destructive. DON'T implement the plan.
```

Replace `global/skills/plan-refine/SKILL.md:194-201` with:

```md
## Related skills

- **/swarm** consumes this skill as review doctrine for large/high-risk plans
 (section 6); this skill provides the standards, `/swarm` provides the parallel
 topology.
- **/prompt-architect** is Cursor-only lineage/advisory context for how this
 skill's structure was originally assembled (RISEN + TIDD-EC Do/Don't + CO-STAR
 framing + an explicit definition of done). It is not a runtime dependency and
 is not required to execute `plan-refine`.
```

- [ ] **Step 5: Wire the new doctrine test into the repo verifier**

Insert this stanza in `.github/scripts/verify-skills.sh` immediately after the shared model-tier tests:

```bash
if [ -d global/skills/plan-refine/tests ] && python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'; then
  note "PASS  plan-refine doctrine contract tests"
else
  note "FAIL  plan-refine doctrine contract tests"
  fail=1
fi
```

- [ ] **Step 6: Re-run the lifecycle/authorization test and repo verifier until they turn green**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
bash .github/scripts/verify-skills.sh
```

Expected:

```text
.......
----------------------------------------------------------------------
Ran 7 tests in <about 0.01s>

OK
PASS  plan-refine doctrine contract tests
```

and later in the verifier output:

```text
verify-skills: OK (global + local + lock + capability-local)
```

- [ ] **Step 7: Commit the first independently reviewable slice**

Run:

```bash
git add global/skills/plan-refine/SKILL.md global/skills/plan-refine/tests/test_skill_contract.py .github/scripts/verify-skills.sh
git commit -m "docs: harden plan-refine lifecycle and authorization"
```

### Task 2: Make Mode A versus Mode B mutually exclusive and require explicit swarm consent

**Files:**

- Modify: `global/skills/plan-refine/SKILL.md:51-76,141-161`
- Modify: `global/skills/plan-refine/tests/test_skill_contract.py`

**Interfaces:**

- Consumes: the Task 1 doctrine test file and green verifier hook.
- Produces: deterministic routing thresholds and explicit-consent swarm doctrine.

- [ ] **Step 1: Extend the doctrine test with the routing and consent scenarios**

Append these methods to `global/skills/plan-refine/tests/test_skill_contract.py`:

```python
    def test_mode_vocabulary_and_thresholds_are_explicit_and_mutually_exclusive(self):
        must_have(self, r"Mode A / Standalone")
        must_have(self, r"Mode B / Swarm-stacked")
        must_have(self, r"Stay STANDALONE when all hold")
        must_have(self, r"0 or 1 specialist domain")
        must_have(self, r"Escalate to /SWARM when any hold")
        must_have(self, r"2\+ specialist domains")
        must_have(self, r"3\+ impacted surfaces")

    def test_no_trustworthy_prior_audit_is_a_tiebreak_not_an_automatic_trigger(self):
        must_have(self, r"Treat 'no trustworthy prior audit' as a tie-break or risk signal, not an automatic swarm trigger")

    def test_swarm_recommendation_without_explicit_request_requires_consent(self):
        must_have(self, r"If the agent recommends Swarm but the operator did not explicitly request it, ask for confirmation before dispatch")
        must_have(self, r"reviewers return findings only")
        must_have(self, r"plan-refine orchestrator alone edits")
```

- [ ] **Step 2: Run the test and confirm the new routing scenarios are red first**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
```

Expected:

```text
FAIL: test_mode_vocabulary_and_thresholds_are_explicit_and_mutually_exclusive
FAIL: test_no_trustworthy_prior_audit_is_a_tiebreak_not_an_automatic_trigger
FAIL: test_swarm_recommendation_without_explicit_request_requires_consent
```

- [ ] **Step 3: Replace section 2 with exact mutually exclusive routing rules**

Replace `global/skills/plan-refine/SKILL.md:51-76` with:

```md
## 2. Choose your mode (scale review to plan size/risk)

Default to **Mode A / Standalone**. Escalate to **Mode B / Swarm-stacked** only
when the plan is large, high-blast-radius, or genuinely multi-domain — because
parallel independent review catches what one pass misses, and the cost is only
justified when the stakes are real.

**Stay STANDALONE when all hold:** single subsystem/root; small surface
(`<=10-15` files or `<=5` plan sections); no prod/infra/ruleset/branch-protection/auth/
data-migration mutation and reversible/low-blast-radius outcomes; `0 or 1`
specialist domain; only a few external facts to verify, all low-uncertainty; low
novelty/ambiguity and fits existing architecture.

**Escalate to /SWARM when any hold:** `3+` impacted surfaces, or `2+`
specialist domains (security/authz, data-integrity/migration,
concurrency/ordering, api-contract, reliability, performance, privacy/secrets,
policy/governance, architecture); irreversible or high-blast-radius outcomes, or
the plan mutates prod/infra/rulesets/branch-protection/auth/money-movement or
runs migrations; many facts need fresh live verification or are
high-uncertainty/likely-stale; high novelty/ambiguity or the plan forks the
existing architecture; cross-repo/multi-team surface.

Treat "no trustworthy prior audit" as a tie-break or risk signal, not an
automatic swarm trigger: if a fast standalone Test 1 baseline reveals material
issues concentrated in `2+` domains or touches any irreversible/critical axis,
escalate.

If the agent recommends Swarm but the operator did not explicitly request it, ask
for confirmation before dispatch. State your chosen mode and the one-line reason
before proceeding. The operator may override.
```

- [ ] **Step 4: Replace section 6 with explicit swarm handoff boundaries**

Replace `global/skills/plan-refine/SKILL.md:141-161` with:

```md
## 6. Mode B — Swarm-stacked (large/high-risk)

The four-test methodology is the review *doctrine*; `/swarm` is the parallel
execution *topology*. They compose cleanly because `/swarm`'s reviewer charters
already separate finding authority from mutation authority.

1. Trigger `/swarm` only under explicit swarm intent or after the operator
 confirms a recommendation to escalate. Pass the target plan path, exact
 authoritative baseline/ref, project conventions, and the four-test overlay into
 the swarm request.
2. Supply this skill as the reviewers' standard: the **four tests** become their
 review steps; the **project's policy/paradigm/operator model + this skill's
 standards** become their instructions and the bar they measure against; the
 **materiality bar + strict read-only reviewer authority** become their
 narrowing. Reviewers return findings only.
3. A verifier runs only when `/swarm`'s own gate conditions select one. Never
 promise a verifier by default.
4. As the `plan-refine` orchestrator, curate returned findings by root cause,
 drop anything that fails the materiality bar, then — under explicit harden/edit
 authority — apply the smallest attributable correction per issue to the plan.
 The `plan-refine` orchestrator alone edits; reviewers never edit the plan.
5. The invariants are unchanged: pre-implementation guard, plan-lifecycle
 discipline from section 7, materiality bar, and the same approval-gated report
 below. Swarm parallelizes finding, not authority.
```

- [ ] **Step 5: Re-run the routing test and full verifier**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
bash .github/scripts/verify-skills.sh
```

Expected:

```text
..........
----------------------------------------------------------------------
Ran 10 tests in <about 0.02s>

OK
PASS  plan-refine doctrine contract tests
verify-skills: OK (global + local + lock + capability-local)
```

- [ ] **Step 6: Commit the routing/consent slice**

Run:

```bash
git add global/skills/plan-refine/SKILL.md global/skills/plan-refine/tests/test_skill_contract.py
git commit -m "docs: make plan-refine swarm escalation deterministic"
```

### Task 3: Require baseline evidence, residual uncertainty, and an approval-gated ready verdict

**Files:**

- Modify: `global/skills/plan-refine/SKILL.md:181-193`
- Modify: `global/skills/plan-refine/tests/test_skill_contract.py`

**Interfaces:**

- Consumes: Tasks 1-2 doctrine and contract test file.
- Produces: exact report fields for baseline/ref, evidence status, rejected candidates, approval gate, and unresolved-unknown blocking.

- [ ] **Step 1: Extend the doctrine test with the reporting/uncertainty scenario**

Append this method to `global/skills/plan-refine/tests/test_skill_contract.py`:

```python
    def test_residual_uncertainty_and_report_fields_are_explicit(self):
        must_have(self, r"exact baseline/ref and evidence status")
        must_have(self, r"residual uncertainty")
        must_have(self, r"material unknowns block a ready-for-approval verdict")
        must_have(self, r"Changes made")
        must_have(self, r"Considered but not acted on")
        must_have(self, r"nothing gets implemented until the operator confirms")
```

- [ ] **Step 2: Run the test and confirm the reporting scenario is red first**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
```

Expected:

```text
FAIL: test_residual_uncertainty_and_report_fields_are_explicit
```

- [ ] **Step 3: Replace section 8 with exact report requirements**

Replace `global/skills/plan-refine/SKILL.md:181-193` with:

```md
## 8. Definition of done — the approval-gated report

Finish with a structured chat report (not embedded in the plan) containing, in
order:
- **Mode and target:** the chosen mode (`Mode A / Standalone` or
  `Mode B / Swarm-stacked`) with the one-line reason from section 2, plus the
  target plan path and version before/after.
- **Baseline and evidence status:** the exact baseline/ref used for verification
  and whether the working tree matched it or diverged.
- **Changes made:** each as a one-line description plus a one-or-two-line
  rationale tied explicitly to one of the four tests.
- **Considered but not acted on:** each candidate as one line, with the reason
  it did not clear the materiality bar.
- **Residual uncertainty:** unresolved evidence gaps or bounded unknowns from
  standalone or swarm review. Material unknowns block a ready-for-approval
  verdict.
- **Updated plan presented for approval:** state plainly that nothing gets
  implemented until the operator confirms.
```

- [ ] **Step 4: Re-run the full doctrine test and repo verifier**

Run:

```bash
python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'
bash .github/scripts/verify-skills.sh
```

Expected:

```text
...........
----------------------------------------------------------------------
Ran 11 tests in <about 0.02s>

OK
PASS  plan-refine doctrine contract tests
verify-skills: OK (global + local + lock + capability-local)
```

- [ ] **Step 5: Commit the reporting slice and establish the first PR boundary**

Run:

```bash
git add global/skills/plan-refine/SKILL.md global/skills/plan-refine/tests/test_skill_contract.py .github/scripts/verify-skills.sh
git commit -m "docs: require plan-refine evidence-based approval reports"
```

`PR 1` ends here. It must contain only:

- `global/skills/plan-refine/SKILL.md`
- `global/skills/plan-refine/tests/test_skill_contract.py`
- `.github/scripts/verify-skills.sh`

No `eco-lock` changes belong in this PR.

## 7. Acceptance criteria

- The final doctrine-contract test names all nine required scenarios explicitly and passes.
- The test text honestly states that it validates the written `SKILL.md` contract, not model execution behavior.
- Mode thresholds are mutually exclusive: `0 or 1` specialist domain can stay standalone; `2+` specialist domains force swarm; `3+` impacted surfaces force swarm; lack of a trustworthy prior audit is a tie-break only.
- Assessment-only prompts are read-only.
- Accepted plans are immutable and require successor-file creation plus index handling.
- No bare `item 4` references remain; plan-convention cross-references use
  `section 1, item 4` / `§1.4`.
- Least-privilege authorization is explicit, and approval never escalates beyond repo policy.
- Material residual uncertainty blocks a ready-for-approval verdict.
- No metadata, installer, provenance, or lockfile surfaces changed.

## 8. Rollback

This work is intentionally easy to revert in slices:

- Revert `docs: harden plan-refine lifecycle and authorization` to remove the lifecycle/authorization doctrine and its first test slice.
- Revert `docs: make plan-refine swarm escalation deterministic` to restore the old routing thresholds and swarm wording.
- Revert `docs: require plan-refine evidence-based approval reports` to remove the reporting doctrine and final test coverage.
- Reverting the whole feature is safe because the test file and verifier hook are additive and scoped to `plan-refine`; no persisted state or repo metadata changes are involved.
