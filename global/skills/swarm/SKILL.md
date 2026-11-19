---
name: swarm
description: "Use when explicitly asked to launch the swarm, run the swarm, dispatch the swarm, or swarm this plan/change. Starts with one probe and the smallest sufficient bounded cohort; one pass by default. Excludes ordinary reviews, lookups, tests/status, Docker Swarm, boids, and one named reviewer."
---

# Swarm review orchestrator

You are the only operator-facing entrypoint; `swarm-probe`, `swarm-reviewer`, and
`swarm-verifier` are internal, read-only roles. **Prime directive: spend the
right amount** — the smallest valid swarm is **1 probe + 1 reviewer**, no
mandatory verifier, one pass by default. **Call the CLI** for mechanics; load
one leaf for judgment.

## The router (Step → Decision → Load/Call)

| Step | Decision | Load / Call |
|---|---|---|
| 1 Trigger + authority | intent + scope? | `references/authority.md` |
| 2 Fingerprint subject | exact revision + in-scope bytes | `fingerprint` → `references/protocol.md` |
| 3 Probe once | runtime-valid probe model | `route-probe --runtime-models` → probe charter |
| 4 Preflight / plan | critical coverage + packs + verifier + slugs | `plan --runtime-models` → `references/dimensions.md` |
| 5 Dispatch | accepted workers + bounded attempts | `account`, `budget` → `references/routing.md` |
| 6 Conform + curate | findings → fix groups | `validate-finding` → `references/report.md` |
| 7 Verifier gate | run one verifier? | `gate-verifier` → `references/authority.md` |
| 8 Second pass | allowed? | `gate-second-pass` |
| 9 Fix (if authorized) | smallest correction per group | parent-run tests → `references/protocol.md` |
| 10 Ship gate | three-line gate | `references/authority.md` |
| 11 Report | curated state | `render` → `references/report.md` |

```bash
python3 scripts/swarm_cli.py --help   # deterministic mechanics only; no authority
```

Native roles unavailable → parent-led fallback (`references/fallback.md`): same
methodology, degraded isolation.

## 1. Confirm trigger and authority

Fire only on explicit swarm intent ("launch/run/dispatch the swarm," "swarm
this," "harden/fix … with the swarm") — never "review this," lookups, test/status
requests, one named reviewer, Docker Swarm, particle-swarm, or boids. Authority
is default-deny (`authority.md`): "harden/fix" adds fixes + tests, each ship verb
needs its own explicit word, ambiguity gets one question, subagents never mutate.

## 2. Fingerprint the subject

Parent-run `fingerprint` binds every root, in-scope byte, and revision into one
candidate ID carried through the run. Recapture before fixes and shipping
(drift → scoped re-review, `authority.md`). `HEAD` plus a dirty flag is not
exact identity.

## 3. Probe once

Read the executing Cursor Subagent tool's concrete model enum and pass it to
`route-probe`; resolution happens before the API call. Dispatch **exactly one**
probe from pre-probe facts only (never scores). It returns sizing intelligence
and a neutral section/flow map, never a reviewer count.

## 4. Plan and size the cohort

`plan --runtime-models` resolves roles and maps critical territories **before
dispatch**. It reserves required critical coverage, probe-blind redundancy, and
required verifier capacity; gated verifiers are routed without pre-dispatch
reservation. It emits bounded section packs and sequential waves, and
preflight-refuses if required coverage cannot fit. Never truncate a protected
territory. First-match Critical → Trivial; **floor 1 reviewer, base max 5**;
load only surfaced charters; no inheritance. Integration review appears only
for an explicit cross-territory flow, never as a catch-all.

## 5. Dispatch within budget

Track lifecycle with `account`: preflight/model rejection, rejected-before-worker
transport, accepted worker, and completion are distinct. Only an accepted
worker consumes the band/absolute capacity, exactly once; routing and transport
fallback attempts each have their own one-attempt bound. **Absolute accepted
worker ceiling: 9; no new work after 20 min; never a third pass.** Completion
uses the plan's source-size/territory/depth allowance: inspect and stop a
stalled worker, but do not kill a healthy large review at a small-task target.

Pass every model explicitly. Filter ordered catalog candidates through the live
runtime set before any launch; unsupported slugs are reported as filtered, never
emitted. No valid configured model is a precise preflight failure with zero role
launches. Contract-invalid/malformed output is failed coverage; at most one
same-model corrected-charter retry may start if accepted-worker capacity
remains. Evidence gathering stays parent-run only.

## 6. Conform and curate

Validate every return with parent-supplied expected candidate and assignment
IDs. Verifier validation additionally receives frozen finding IDs,
accepted-risk IDs, and parent-observed coverage state. Then curate by root
cause. Invalid or partial means failed coverage, not "no findings."

## 7. Verifier gate (band-independent)

Ask `gate-verifier`; run **one** only when directed/reserved, otherwise zero and
`shipping_clearance = not_evaluated`. Freeze finding scope, accepted-risk
authority, candidate ID, and parent coverage before dispatch. Approval is
invalid on candidate drift, any uncovered required assignment, failed/stalled
worker, malformed/partial return, or missing probe-blind coverage.

## 8. Second pass is gated, never automatic

Ask `gate-second-pass`; allow one only when it holds, then inspect **only** the
named unresolved territory — never a second full swarm. Conditions: `authority.md`.

## 9. Fix only when authorized

Only under explicit `harden`/`fix`: recapture, apply the **smallest attributable
correction per fix group** in the parent, verify with **parent-run tests + diff —
not an auto re-swarm**, and re-review only through §8.

## 10. Ship at the intersection

Before any commit/push/PR/merge/release/install/deploy/external write/destructive
action/cleanup, the three-line ship gate (`authority.md`) must hold; revalidate
before each and report the **observed** outcome, never a green intent.

## 11. Report exact state

`render` → ≤3 sections (**BLUF · FINDINGS · WHERE THINGS STAND**), ≤10 curated
findings, P3/P4 by count, a coverage matrix naming every waived/uncovered
dimension, budget vs. ceiling, and literal shipping status (`report.md`).
Proportionality is locked by the deterministic suite (`evals/evals.json`,
`tests/`).
