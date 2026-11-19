# Codex-first work assessment and model dispatch
**Status:** ACCEPTED — 2026-11-02
**Date:** 2026-11-02
**Owning repository:** `KleinPerkins/skills`
**Plan-type:** agentic-execution

**Owner:** Laurence Duggan; implementation authorized by “PLEASE IMPLEMENT THIS PLAN”.
**Decision:** [ADR0011](../adr/0011-codex-work-assessment.md).

## Accepted outcome

Make assessment -> model -> effort -> native dispatch -> outcome verification the
active Codex default. Skills owns source; dev owns qualified pinned instructions.
Use structured evidence, minimum-sufficient selection, parent advice and fresh
independent review. Cursor/Claude compatibility, app-server, CLI/SDK, intent-router
and downstream distribution are not requirements of this release.

## Assessment and policy

Work classes: inspect/operate/build/design/assure. Record objective, deliverable,
scope, acceptance criteria, ambiguity/reasoning/coupling ratings with evidence,
consequences, reversibility, verification and review requirements. Highest rating
wins; unresolved routing questions need assessment. Source edits have D1 floor;
security judgment, technical independent review and sign-off have D2 floor.
Consequential actions add authorization/review, not automatic effort inflation.

D0 mechanical -> gpt-6-luna/low; D1 bounded judgment -> gpt-6.1-sol/medium;
D2 complex reasoning -> gpt-6.1-sol/high; D3 demanding synthesis -> gpt-6-astra/high.
Family and effort are separate. No automatic max/ultra. Initial choices require
native screening, not claims of optimum cost or model superiority.

## Interfaces and lifecycle

Dedicated assess/plan/observe/refresh/source-digest commands return versioned
records with assessment, reasons, difficulty, pair, required checks, source/policy
binding, dispatch and lifecycle. Identical inputs yield identical decisions.
Require fresh (15-minute) native tool/session/source/host evidence. Encode exact
multi_agent_v1.spawn_agent model/effort and fork_context:false for ordinary agents.
Parent target is advice only. Preserve explicit native permission requirements.

Only proven prelaunch rejection allows one same-pair retry after 60 seconds.
Quality escalation requires completed failed predefined checks, diagnosis and
verified cleanup. Once per task: D0 -> Sol/medium, D1 -> Sol/high, D2 -> Astra/high,
D3 -> Astra/xhigh, or stronger reassessed requirements. Infrastructure failures,
permissions, ambiguous checks and uncertain cleanup never qualify. Keep requested
settings distinct from actual native acknowledgement. Refresh proposes only.

## Validation and delivery

Test classes/bands/floors, length invariance, malformed evidence, native contract,
missing pairs, parent advice, overrides, identity mismatch, retry and escalation
budgets. Run the Skills owner gate. Define two synthetic fixtures per band and
compare preferred/escalation pairs, at most 16 started workers; all preferred
checks must pass before complete-policy activation. Record limitations honestly.

Deliver Skills source and evidence through governed merge, then dev caller/pin,
rendering/tests and native instruction activation. Verify both owner suites,
preview/apply/readback, rollback preservation and a fresh-session discovery/plan.
Completion requires merged source, passing native qualification and active fresh
Codex instructions. Existing sessions may retain old instructions. Report phases
separately; do not rewrite frozen historical evidence or bypass reviewer authority.

## Work items

**Files:** source-owned Codex resolver, policy, caller contract, tests and native
evidence in Skills; Codex host caller/rendering/activation sources in dev.

**Interfaces:** assess/plan/observe/refresh/source-digest; native spawn arguments;
dev preview/apply/verify/rollback using a merged source revision and digest.

- [ ] Implement the assessment, policy, adapter and lifecycle with offline tests.
- [ ] Complete the bounded native screen and preserve its exact evidence.
- [ ] Deliver Skills through the prescribed checks and reviewed merge.
- [ ] Deliver and activate the qualified dev caller; verify fresh discovery and rollback.
