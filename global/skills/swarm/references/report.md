# Curated report

The swarm keeps **no durable ledger** and no on-disk run state — the transcript
is the record. The orchestrator curates the raw reviewer findings (`SKILL.md`
§6) and renders a tight report with `python3 scripts/swarm_cli.py render`. The
report shows the smallest set of information the operator needs to act.

## Curation before rendering

The orchestrator (not a subagent):

1. **normalizes** findings by affected invariant / root cause;
2. **merges** duplicates that share evidence lineage and correction, preserving
   the contributing charter IDs;
3. **drops** unsupported claims and any sub-70-confidence "confirmed" finding;
4. **groups** accepted findings into **fix groups** by shared files/invariant —
   one fix plan per group, not one patch per reviewer.

`INERT`, non-JSON, contract-invalid, malformed, partial, stalled, errored, and
timed-out returns are failed workers, not no-finding results. Name the exact
assignment and territory; keep it failed even if a later retry succeeds.
Preflight model resolution and rejected-before-worker transport are separate
failure classes and consume no accepted-worker capacity.

## Output caps

- **≤10 curated findings** in the report.
- **P3/P4 duplicates are summarized by count, not listed individually** (e.g.
  "4 P4 style/consistency notes across 3 files").
- Evidence is shown by reference, never as a source dump.

## Three sections (at most)

Render exactly these headings, in order. Omit a section only if it is genuinely
empty (say so in the BLUF).

### 1. BLUF

Verdict; band selected and why (one line); release blockers; the important
findings/fix groups; fixes applied; residual risks and deferrals; coverage
confidence; tests/CI observed; shipping status; and the single required operator
action, if any.

### 2. FINDINGS

The **curated** fix groups only — up to ten — as a compact table:

`Fix group / Finding` · `Focus / Dimension` · `Evidence (ref + lineage)` ·
`Risk` · `Priority` · `Confidence` · `Correction` · `Status`.

P3/P4 duplicates collapse into a trailing one-line count per cluster. Do **not**
print every raw reviewer observation, duplicate, or false positive.

### 3. WHERE THINGS STAND

- **Coverage matrix**: each dimension marked `reviewed`, `waived` (with the probe
  evidence supporting waiver), or `uncovered` — nothing silently dropped;
- preflight/transport rejections and failed accepted workers with exact
  assignment/territory and resulting uncovered coverage;
- band, cohort (roles + resolved model slugs), dispatch/time budget spent vs. the
  accepted-worker ceiling, start cutoff, completion allowance, and verifier
  reservation/gate reason;
- exact candidate ID, section-pack ownership/overlap, and any candidate drift;
- files touched, tests run, branch/commit/push/PR state, worktree cleanliness;
- `shipping_clearance ∈ {approved, failed, not_evaluated}` — **`not_evaluated`
  whenever no verifier ran** (never silently "approved");
- native vs. parent-led-fallback execution mode and isolation quality;
- next-step owner, timing, and blocking status.

Be literal about unknown, blocked, degraded, pending, waived, and not-authorized
states. A curated report that hides a gap is worse than a longer one that names
it.
