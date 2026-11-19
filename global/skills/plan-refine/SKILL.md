---
name: plan-refine
description: >-
 Harden a not-yet-implemented plan before coding. Use to review, stress-test,
 tighten, upgrade, finalize, or assess a plan, spec, RFC, design doc, or roadmap.
 Assessment-only stays read-only; explicit hardening may edit only the governed
 plan surface. Supports an explicitly requested swarm.
---

# plan-refine

Harden a not-yet-implemented plan according to the project's own plan lifecycle.
You govern the *hardening* of the plan; you never implement the plan. Stay
strictly pre-implementation throughout. Assessment-only work is read-only;
explicit hardening/edit authority may write only the narrow,
convention-governed plan surface section 7 permits.

Be rigorous, skeptical, and materiality-driven — change only what you can
justify, and be comfortable leaving things unchanged.

## 1. Take the target plan and establish ground truth

1. **Target plan.** Use the plan path if given as an argument; otherwise identify
 the governed repo plan the operator is discussing (the active plan file, a plan
 under `docs/plans/`, or the project convention's equivalent). If multiple
 plausible target plans exist, ask rather than ranking by recency. Read the
 target plan in full first; section 7 governs whether hardening updates it in
 place or creates its required successor/index artifacts.
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
 conventions such as `docs/plans/` and `docs/adr/`), including how the project
 versions plans (filename suffix, in-body version marker, and index/changelog
 update pattern) — section 7 applies this discovered convention. If none exist,
 ask the operator briefly. You will measure gaps and expansions against these,
 not taste.
5. **Preflight state and intent.** Verify the target plan is still
 pre-implementation. If implementation has already started, stop this workflow
 and say to switch to implementation follow-through or change review instead.
 Assessment-only requests such as "review" or "is this ready?" must not silently
 edit, version, or fork the plan; return findings and proposed changes without
 mutating. Only explicit hardening/edit authority permits mutation. If the
 request's phrasing doesn't unambiguously request a written change — e.g. it
 mixes assessment language ("review", "is this ready") with edit-implying
 language ("improve", "upgrade") — default to assessment-only and confirm in
 one line before mutating.

## 2. Choose your mode (scale review to plan size/risk)

Default to **Mode A / Standalone**. Escalate to **Mode B / Swarm-stacked** only
when the plan is large, high-blast-radius, or genuinely multi-domain — because
parallel independent review catches what one pass misses, and the cost is only
justified when the stakes are real.

**Stay STANDALONE when all hold:** single subsystem/root; `0-2` impacted surfaces;
small surface (`<=10-15` files or `<=5` plan sections); no prod/infra/ruleset/branch-protection/auth/
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

**General fall-through:** if the plan fails a Standalone conjunct (e.g. exceeds
the file/section threshold) but triggers no Escalate disjunct, default to
Standalone with a deeper Test 1 pass rather than escalating on size alone —
size without concentrated risk, irreversibility, or multi-domain surface is not
sufficient grounds for Swarm.

If the agent recommends Swarm but the operator did not explicitly request it, ask
for confirmation before dispatch. State your chosen mode and the one-line reason
before proceeding. The operator may override.

## 3. The four-test methodology (fixed; do these in order)

Catalog every candidate issue before deciding what to do about any of them. The
order is load-bearing, not arbitrary: stale facts invalidate every downstream
judgment, so facts come first; a plan's structural correctness (gaps/flaws)
must be settled before sizing its scope; and surface is trimmed (test 3) before
new surface is considered (test 4), so expansion never compounds an
over-engineered baseline.

1. **Re-verify every fact and assumption, fresh.** Check each against the
 ground-truth baseline and the real source it depends on (disk, git, a live API,
 official docs). Correct any stale reference, invalid assumption, or inconsistency
 — and every downstream number, mechanism, or dependent section derived from it.
2. **Resolve every gap and flaw.** Find every gap, inconsistency, brittleness,
 architectural weakness, missed dependency, or sequencing error, and resolve it.
 Justify each resolution with verified fact or a citable deviation from the
 project's own policy/paradigm/operator requirements — never preference or style.
 Do not relitigate settled scope on stylistic grounds.
3. **Simplify over-engineering — but only where a test demonstrably holds.**
 Something is over-engineered if: (a) it solves a problem of marginal value for
 the effort/surface/operator-overhead it adds — marginal meaning never actually
 observed, no concrete need in the current or clearly-planned system, and unlikely
 at the plan's stated load ceiling; (b) it pursues technical perfection where a
 materially simpler mechanism would be reliable and adequate at the cost of only
 rare/negligible edge cases; (c) it adds hardening/redundancy/a fallback/"plan B"
 for a case that is already marginal or whose primary path is already resilient
 enough that the backup is very unlikely to ever add value. Simplify toward the
 Occam's-razor version — never cut merely because a leaner version is imaginable.
4. **Expand under-scoping — but only where a test demonstrably holds.**
 Something is under-scoped if: (a) an action or outcome the end-state design
 can produce leaves the operator to personally diagnose a failure, decode a raw
 error/log/API payload, or interpret differently-styled output from different
 agents, with no plain-language feedback loop; (b) a new capability duplicates
 or bypasses the project's existing IDE/CLI parity pattern instead of exposing
 itself through it; (c) documentation, operating policy, or governance (drift
 detection, coverage/canaries, runbooks) that this plan's own change touches
 would go stale or contradict it, with no one named to update it. Where any of
 (a)-(c) demonstrably holds, close that specific gap: give the failure mode
 either fully automatic handling or a small, distilled, plain-language
 operator-facing surface that lets the operator state intent in ordinary
 language while an agent with full tool access and intent-routing decides what
 to run; expose new operator tooling through the existing shared primitive
 (thin IDE surface + thin CLI entrypoint) rather than a parallel mechanism; and
 update only the documentation/policy/governance that (c) actually implicates
 — never everything the plan merely touches.

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

## 4. The materiality bar (both directions)

Make only a change you can justify with verified fact, a closed gap, a demonstrated
over-engineering test, or a demonstrated under-scoping gap — never preference or
style. Leaving something unchanged is a fine outcome, and if zero changes clear
this bar, do not advance the version marker, cut a successor file, or touch the
plan index — the plan and its version stay exactly as they were. Treat low-value
changes with real scrutiny and reject them by default. Every change you keep must
tie to one of the four tests.

## 5. Mode A — Standalone (default)

Walk tests 1->4 yourself, single-threaded, cataloguing candidates as you go; keep
only the changes that clear the materiality bar. For assessment-only intent,
return findings and proposed changes without mutation. Under explicit harden/edit
authority, apply corrections only through section 7's project-convention
lifecycle; then write the report in section 8.

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
- DON'T write, create, or delete any file other than the governed target plan,
 its convention-required successor/index artifact, or its narrow retention copy
 (per the DO above). No code, skill, workflow, config, doc, or governance files
 beyond that narrow plan surface.
- DON'T fork unrelated or divergent parallel plan branches; successor versions
 and the narrow retention-copy exception are the only allowed multi-file plan
 shapes.
- DON'T commit, push, merge, create/delete/checkout git branches or tags,
 rebase, reset, or stash — or mutate branch protection, rulesets, or any live
 system; nothing destructive beyond reading git state. DON'T implement the plan.

## 8. Definition of done — the approval-gated report

Finish with a structured chat report (not embedded in the plan) containing, in
order:
- **Mode and target:** the chosen mode (`Mode A / Standalone` or
  `Mode B / Swarm-stacked`) with the one-line reason from section 2, plus the
  target plan path and version before/after.
- **Baseline and evidence status:** the exact baseline/ref used for verification
  and whether the working tree matched it or diverged.
- **Changes made or proposed:** each as a one-line description plus a
  one-or-two-line rationale tied explicitly to one of the four tests, and
  whether it was applied (harden/edit authority) or is proposed pending
  approval (assessment-only).
- **Considered but not acted on:** each candidate as one line, with the reason
  it did not clear the materiality bar.
- **Residual uncertainty:** unresolved evidence gaps or bounded unknowns from
  standalone or swarm review. Material unknowns block a ready-for-approval
  verdict.
- **Outcome and approval gate:** Assessment-only requests return findings and
  proposed changes without mutation. Under explicit harden/edit authority,
  **Updated plan presented for approval** applies only when no material unknowns
  remain; otherwise readiness is blocked and the missing evidence is named. In
  every path, nothing gets implemented until the operator confirms.

## Related skills

- **/swarm** consumes this skill as review doctrine for large/high-risk plans
 (section 6); this skill provides the standards, `/swarm` provides the parallel
 topology.
- **/prompt-architect** is Cursor-only lineage/advisory context for how this
 skill's structure was originally assembled (RISEN + TIDD-EC Do/Don't + CO-STAR
 framing + an explicit definition of done). It is not a runtime dependency and
 is not required to execute `plan-refine`.
