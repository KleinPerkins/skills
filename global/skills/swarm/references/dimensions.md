# Review dimensions and band selection (design + fallback reference)

This is the **human-readable design rationale and parent-led fallback reference**
for sizing. The **runtime source of truth is the code**: `swarm_helper`
(`DIMENSION_NAMES`, `PROTECTED_AXES`, `BAND_SPEC`, `select_band` / `size_cohort`),
surfaced through `python3 scripts/swarm_cli.py plan` / `size`. When this prose and
the code disagree, the code wins.

The sixteen dimensions are a **reconnaissance map, not sixteen review
obligations.** The probe scores them once so the orchestrator can see where risk
concentrates and pick the smallest sufficient cohort. A high score signals where
attention *may* be warranted; it never asserts a defect exists and never, by
itself, buys a reviewer.

## The D01–D16 map lives with the probe

The full per-dimension descriptions and their `focus_area` routing are carried by
the **probe charter** (`charters/probe.md`) — only the probe scores all sixteen —
and mirrored in code (`swarm_helper.DIMENSION_NAMES`, `PROTECTED_AXES`). They are
**not** duplicated here. For each dimension the probe records an integer `score`
and `confidence` (1–100) plus a `hotspot` flag; the score measures how much
specialized attention the surface plausibly needs — combining risk, complexity,
novelty, breadth, and uncertainty.

Score anchors (recon signal, not review mandates):

- **1–19** negligible; basic confirmation only.
- **20–39** low and familiar; no dedicated reviewer.
- **40–59** material or moderately uncertain; targeted inspection warranted.
- **60–79** high complexity/impact/coupling/novelty; a specialist is warranted.
- **80–89** very high risk or uncertainty; a strong specialist with explicit evidence.
- **90–100** critical or system-wide; independent redundancy on that axis.

## Probe → band (the core mapping)

The orchestrator (not the probe) selects the band with `python3
scripts/swarm_cli.py plan` (or `size`). Evaluate **Critical → Trivial; first
match wins.** Count distinct **territories / focus areas**, never high-scoring
dimensions. The floor is **1** reviewer; the base maximum is **5**. This table
mirrors `swarm_helper.select_band`; the code is authoritative.

| Band | Selected when (first match, top-down) | Reviewers | Coverage / depth | Verifier | 2nd pass |
|---|---|---:|---|---|---|
| **Critical** | any dimension ≥90; or D04/D05/D07 ≥80; or multi-repo migration (D03≥60) with any score ≥80 | **4–5** (incl. 1 independent/blind on the critical axis) | redundancy **only on the ≥90 axis**; specialist elsewhere | **yes (1)** | gated |
| **Deep** | max score 80–89; or D04/D05/D07 in 60–79; or multi-repo (no migration) with max ≥60 | **3–4** | specialist + strong, explicit evidence paths | gated | gated |
| **Standard** | max score 60–79; or 3–5 impacted surfaces; or ≥2 distinct specialist focus areas | **2–3** | specialist on the driving axis | gated | no |
| **Small** | max score 40–59; or single root, ≤15 files, ≤2 focus areas | **1–2** | targeted inspection of hotspots | no | no |
| **Trivial** | single root, ≤5 files / ≤100 lines, max score <40, `fix_character=cosmetic`, no protected-axis hotspot | **1** | the one impacted surface | no | no |

The reviewer counts are the base cohort. Per-band accepted-worker ceilings,
concurrency, the absolute nine-worker cap, the 20-minute start cutoff, and the
scope-aware 25–60 minute completion allowance live in `swarm_helper`. `budget`
checks accepted workers; `account` distinguishes preflight/transport rejection,
worker acceptance, and completion.

## Sizing rules

- **Waiver is explicit, never silent.** A dimension scored below its band's
  threshold is *waived* and shown in the coverage matrix with the probe evidence
  that supports waiver. Low confidence (<70) or a named hotspot **blocks** waiver
  and forces at least targeted inspection.
- **Charters are organized by impacted surface / focus area**, not one reviewer
  per dimension. Related dimensions share one reviewer by `focus_area`: the probe
  charter maps each dimension to a focus_area, and the committed
  `charters/INDEX.md` (surfaced by CLI `plan`) maps each focus_area to its charter
  so only the surfaced charters load.
- **Coverage is planned before reviewer dispatch.** Every protected/critical
  territory and required probe-blind duplicate is reserved together with the
  required verifier slot. A gated verifier is routed but does not reserve
  pre-dispatch capacity. If bounded assignments do not fit, `plan` returns a
  capacity refusal before any reviewer launch; it never truncates the territory
  list.
- **Large artifacts are partitioned.** Neutral section maps cover all in-scope
  lines; each evidence pack is at most 3,000 lines and carries exact candidate
  identity. Overlap is explicit for independent contradiction checks. A
  probe-blind reviewer may receive identity/file/section/flow facts but no probe
  conclusions.
- The orchestrator may **merge** probe-suggested territories to reduce the count.
  It may **not** raise the count above the band without a listed trigger.
- **Redundancy is proportional.** Only the Critical band uses two independent
  reviewers, and only on the ≥90 (or ≥80 protected) axis — one of them blind to
  probe conclusions. No other band carries redundancy.
- **Integration is explicit.** Add an integration reviewer only when a named
  cross-territory flow requires consistency review; never use one as a
  catch-all substitute for omitted territories.
- Thresholds here are the starting calibration and are tunable. The **invariants**
  are fixed: floor of 1 reviewer, first-match band selection, no mandatory
  verifier, single pass by default.

## What this reference deliberately does not contain

There is **no** `reviewers = 4 + …` formula and **no** "always 4–12" floor. The
old doctrine welded a six-agent minimum into sizing; it is gone. The smallest
valid swarm is **1 probe + 1 reviewer**. `python3 scripts/swarm_cli.py plan` (or
`size`) consumes the probe JSON (`protocol.md` §Probe output) and returns the band
plus a cohort plan honoring these rules.
