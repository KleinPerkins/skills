# ADR 0006: Route subagents by task tier to fixed-level models; reported fallbacks trigger catalog maintenance
Status: accepted — 2026-10-19
Supersedes: ADR-0002 (catalog-freshness clauses only) — [source](0002-subagent-orchestration-sibling-assets.md)

**Owners:** Laurence Duggan (`KleinPerkins`); `KleinPerkins/skills` maintainers
**Scope:** `global/rules/subagent-orchestration` (rule, `model-tiers.json`, `verify_model_tiers.py`)
and the `/swarm` catalog loader
**Decision owner:** Laurence Duggan (approved 2026-10-19)

## Decision

1. **Route by task tier.** Agents pick one of four tiers by the hardest thing the subagent must get
   right: `deep` (architecture, planning, ambiguous or cross-system, security-sensitive,
   irreversible, shipping), `critical` (independent review and sign-off, merge and release gates,
   `/swarm` adjudication), `standard` (well-specified builds, refactors, tests, docs, routine
   review), `economy` (search, mechanical edits, running checks, polling, log summaries). Each tier
   lists candidate models in preference order; the first one on the live list wins.
2. **Effort comes from the picker.** Cursor offers each switched-on model to subagents at exactly
   one level, the one last chosen in a chat's model picker, and the subagent tool has no effort
   input. Agents choose models, not efforts. The catalog no longer carries an `effort` field
   (schema `cursor-model-tiers/v2`); `/swarm` keeps its per-tier rigor obligation as its own policy.
3. **Reported fallbacks trigger maintenance.** A fallback is a tier that resolves to a different
   model family than its first candidate, or to nothing. Agents report every fallback in their
   final report, and the fix is a one-file edit to `model-tiers.json` from the live list. The
   checker validates structure only (four tiers, non-empty duplicate-free well-formed names, at
   least two providers per tier) and, given `--runtime-models`, prints each tier's resolution,
   warns on a fallback, and fails only when a tier has no match. `verified_against` is an
   informational "last checked against the live list" date with no age limit.
4. **No tests or docs depend on catalog content.** Tests use synthetic names or derive from the
   catalog, so refreshing it never needs another edit.

ADR 0002's sibling-asset decision (declare, co-install, and verify `model-tiers.json`) stands
unchanged. Only its catalog-freshness clauses are superseded: the kept 30-day guard and the
agent-driven re-verification job.

## Why

The July 2026 30-day expiry compared the catalog with a hand-recorded copy of Cursor's list, so it
only proved the two files agreed with each other, never with Cursor. It caught no real drift (the
daily freshness job printed OK while half the catalog's names were no longer offered) and would have
broken machine setup and `make verify` on a fixed date with nothing actually wrong. Drift is only
visible at dispatch time, where the agent sees the live list, so that is where it is now detected
and reported; do not re-add a calendar expiry.

The stale catalog also routed both top tiers to the same fallback model and never reached the
operator's chosen deep model, because its names carried effort levels Cursor no longer offers.

## Consequences

- The `subagent-model-tier-freshness` local job is retired, with no scheduled replacement.
- `~/dev` setup and verification keep calling the checker with no arguments; it now passes on any
  well-formed catalog.
- The operator keeps the tier models switched on at their chosen picker levels; a level change
  shows up as a reported fallback, not a broken build.
- cpp receives the updated rule, catalog, and swarm helper through the ecosystem-orchestrator sync;
  the rule and swarm should land together because the swarm loader requires schema v2.
