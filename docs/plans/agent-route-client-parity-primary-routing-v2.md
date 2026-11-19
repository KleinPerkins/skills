# Agent-route revision v2 — canonical successor pointer

**Status:** GENERATED PROJECTION — points to the approved canonical successor.
**Date:** 2026-11-03
**Owning repository:** KleinPerkins/skills
**Plan-type:** standard
**Supersedes:** `agent-route-client-parity-primary-routing-v1.md` — conflicting router requirements only, as mapped below.

This file provides the named v2 successor entry required by the immutable legacy plan.
It is a mutable navigation projection, not a second semantic plan or an acceptance receipt.
The canonical records below define the requirements, decisions, tasks and gates.
Source execution requires verified planning merge; this pointer supplies no merge evidence.

- Canonical plan: [PLAN-f7571d74-f495-5461-ae37-ed0e227347d5-2ad7b541-b2e5-59de-b7b0-8b72ee2c8d6a v1](../../.planning/artifacts/PLAN-f7571d74-f495-5461-ae37-ed0e227347d5-2ad7b541-b2e5-59de-b7b0-8b72ee2c8d6a-v1.md).
- Canonical plan digest: `sha256:e4b7a24667fe099aa76ae28c22dfe17e847190c86733cf3087f2a5f7ec2e77f3`.
- Governance sidecar: [requirement/task/assumption bindings](../../.planning/artifacts/PLAN-f7571d74-f495-5461-ae37-ed0e227347d5-2ad7b541-b2e5-59de-b7b0-8b72ee2c8d6a-v1.governance.json).
- Specification: [SPEC-f7571d74-f495-5461-ae37-ed0e227347d5-75ad1e06-6e7c-58fd-832b-5c1df331b991 v1](../../.planning/artifacts/SPEC-f7571d74-f495-5461-ae37-ed0e227347d5-75ad1e06-6e7c-58fd-832b-5c1df331b991-v1.md).
- Product requirements: [PRD-f7571d74-f495-5461-ae37-ed0e227347d5-c8edf48e-bdd5-51df-b618-0e8905c57209 v2](../../.planning/artifacts/PRD-f7571d74-f495-5461-ae37-ed0e227347d5-c8edf48e-bdd5-51df-b618-0e8905c57209-v2.md).
- Architecture: [ADR 0012](../adr/0012-separate-ecosystem-discovery-from-codex-project-entry.md).
- Observed publication source: `980968718eb5544f3e9d9ccca54d16f990343aa2`. This is branch publication, not a planning-merge claim.

## Supersession navigation

These references identify the conflicting legacy clauses; they do not add decisions.

| Legacy v1 clauses | Canonical successor authority |
|---|---|
| §2 items 1–2, §3.1, and §6 client-exposure/equivalent-client routing criteria | ADR decisions 2 and 10; plan S2, S3 and L1: Codex-only entry, separate three-client search, later bounded native qualification. |
| §2 items 3–4, §§3.2–3.3, and §6 checkout grouping/primary representative criteria | ADR decision 4 and specification Data and trust contract: separate repository/clone/worktree identities; no primary-preference ranking contract. |
| §§3.2–3.3 legacy field propagation, old-index compatibility, route verdicts and `discover --full`; §6 no-new-store/scoring constraints | ADR decisions 1 and 7–10; specification Interfaces, Refresh and Failure handling; plan S1–S3 and L2: new bounded index contract and deliberate legacy incompatibility/retirement. |
| §4 exact old implementation boundary and corresponding §5/§7 file-scope restrictions | Canonical plan S1–S4 and Owner package resolution: source extraction, search consumer, narrow entry and their explicit package/check boundaries. |
| §6 final criterion and §7 separate implementation-GO requirements | Canonical plan Global constraints and G3: source execution follows accepted planning and verified planning merge under the existing human authorization. Later installation and retirement remain separately gated. |

All non-conflicting owner, privacy, excluded-access, immutable-history and consequence boundaries
remain governed by their canonical sources. This pointer grants no installation, runtime cleanup,
downstream distribution, new-chat, AWA or model-policy authority.

## Unaccepted feedback drafts

The mutable plan/ADR indexes withdraw the unaccepted feedback-loop drafts from active work in
favor of the canonical revision. [The plan](agent-route-feedback-loop-v1.md) and
[ADR 0001](../adr/0001-agent-route-feedback-loop.md) remain unchanged historical drafts; no
acceptance is asserted and no learned-feedback implementation is authorized.
