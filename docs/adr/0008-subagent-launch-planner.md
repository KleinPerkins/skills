# ADR 0008: Plan each subagent launch with the tier checker and ride out rejected models in a fixed order
Status: accepted — 2026-10-21
Supersedes: ADR-0006 (transport-failure-only retry, structure-only checking, and fallback-only reporting clauses only) — [source](0006-subagent-task-tier-routing.md)

**Owners:** Laurence Duggan (`KleinPerkins`); `KleinPerkins/skills` maintainers
**Scope:** `global/rules/subagent-orchestration` (rule, `verify_model_tiers.py`, tests);
`model-tiers.json` and its schema are unchanged
**Decision owner:** Laurence Duggan (approved 2026-10-21 through the implementation instruction for
this change)

## Decision

1. **A planner names the model.** `verify_model_tiers.py plan` takes a work kind and the offered
   model list and prints a primary model, a secondary from another provider, the order to try
   them, and warnings. Work kinds map to tiers in code: `find` and `run` to `economy`, `build` and
   `review` to `standard`, `design` to `deep`, `sign-off` to `critical`. A tier can only be raised
   to a stronger class, with a reason, so design stays deep and sign-off stays critical. Reviews
   and sign-offs name the author's provider (`none` for a human) and prefer a different one.
   Agents run the planner before each work kind's first launch in a session and launch exactly the
   model it names.
2. **Rejected launches follow one fixed order.** Primary, secondary, wait 60 seconds, primary,
   secondary, then FATAL; with no secondary, primary, wait, primary, FATAL. This replaces "after a
   transport failure, try only the next listed live candidate". A launch rejected before the
   subagent starts follows the order; a failure after it started is handled under Fleet
   Stewardship without switching models; a slug the tool refuses as not offered means re-read the
   list and re-plan. FATAL means launch nothing more for that tier, let running workers reach a
   safe point, then stop and report. The planner itself never sleeps, uses the network, or keeps
   state.
3. **Every quality loss is reported, not only fallbacks.** The planner warns on `step-down` (a
   lower effort level than the catalog's first entry of that model family in the tier, judged by
   catalog order alone), `fallback` (the primary's family differs from the choice when every
   candidate is offered), `raised`, and `not-independent` (a review model shares the author's
   provider). A launch that runs on the secondary is also reported as a fallback. Pinned subagent
   types, initially only Bugbot, choose their own model, so they never count as the tier's review
   or as a different-provider review.
4. **The catalog check covers backup strength, not only structure.** `validate_catalog` also fails
   when a backup's model family leads only weaker tiers (strength: economy 1, standard 2, deep and
   critical 3). Other levels of a tier's own first family are allowed and show up as step-downs. A
   family that leads no tier has no declared strength to compare, so it passes. Replacing a tier's
   first candidate therefore never fails just because the old first choice no longer leads any
   tier.
5. **A rejection in one session is an outage, not drift.** `model-tiers.json` changes only when the
   live list drops a model or rejections persist across sessions.

ADR 0006's other decisions stand: routing by task tier, effort fixed by the picker, schema
`cursor-model-tiers/v2`, no tests or docs depending on catalog content, and no calendar expiry. The
checker's no-argument and `--runtime-models` output and exit codes are unchanged.

## Why

On 2026-10-21 Cursor's servers began rejecting `composer-2.5-fast` about one second after launch
("AI Model Not Found") while the subagent tool still offered it. The incident exposed five gaps: an
offered model is not always a working one, and the checker only compared names; the rule's only
retry clause covered transport failures, so one worker relaunched the same failing launch several
times; `family()` hid effort-level step-downs, which broke ADR 0006's promise that a level change
shows up as a reported fallback; the Bugbot subagent type ignores the model argument, so plans that
named its model were wrong; and the tier choice existed only as prose. A computed, tested plan
closes all five while compliance stays behavioral. The operator treats the rejection as a temporary
outage, so the catalog keeps `composer-2.5-fast` first in `economy`.

## Consequences

- While a model is rejected, its tier's work moves to the plan's secondary and is reported, with no
  catalog edit.
- `~/dev` setup and `verify-skills.sh` keep calling the checker exactly as before; the swarm still
  reads schema v2 directly.
- A plan proves only that a model is offered, not that the server accepts it; acceptance is known
  only at launch, which is why the attempt order exists.
- Downstream copies receive the rule and checker through the existing ecosystem-orchestrator sync.
- No dispatch or lifecycle enforcement hooks are added.
