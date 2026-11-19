# ADR 0011: Assess work and select explicit Codex model and effort
Status: accepted — 2026-11-02
Supersedes: ADR-0006/0008/0009 only for the newly activated Codex route.

**Decision owner:** Laurence Duggan (`KleinPerkins`).
**Authority:** explicit instruction “PLEASE IMPLEMENT THIS PLAN” for the
[Codex-first execution plan](../plans/codex-work-assessment-v1.md).
**Owners:** Skills owns assessment/policy/adapter; dev owns installed instructions.

## Decision

Use a hybrid evidence-backed rubric and deterministic resolver. Compute the highest
of ambiguity, reasoning complexity and dependency coupling, with source-edit and
review/security floors. Keep consequences separate from reasoning effort. Select
model family first, effort second, according to the accepted D0-D3 policy.

Add a dedicated Codex entrypoint, source policy and closed JSON contracts. Native
multi_agent_v1.spawn_agent receives explicit model/effort and fresh context.
Parent tasks receive advice only. No inference from API listings, no inherited
model/effort, no custom-role qualification, no permission from routing records.

Permit one same-pair availability retry after 60 seconds and one separately
accounted quality escalation after completed failed checks, diagnosis and cleanup.
Independent review uses fresh context, prefers another capable model and never
claims provider diversity. External repository gates remain authoritative.

## Why

The historical native resolver shares a Cursor-shaped catalog. Its non-economy
Codex choices converge on one old model at maximum effort, while assessment is
mostly caller-chosen work labels. A dedicated policy makes task evidence and
selection reproducible without maintaining other-client compatibility.

## Consequences

Preserve prior accepted ADRs/evidence and existing resolver bytes. Add a successor
caller in dev after source delivery and native qualification. Activation and
rollback use the governed instruction operation; no enforcement hook is added.
The 16-worker synthetic screen is bounded evidence, not a performance benchmark.
Neither source tests nor worker handles prove actual execution identity.
