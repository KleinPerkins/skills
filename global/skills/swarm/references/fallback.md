# Cross-tool fallback

Use native read-only subagents when the runtime supports the installed role
definitions and preserves their read-only tool contract. Otherwise use this
bounded, **parent-led** fallback. Never claim the fallback has native isolation.

The fallback keeps the **same proportional methodology** — same probe → band →
cohort mapping, same per-band ceilings, same absolute caps, same conformed
finding shape. Only the isolation degrades.

## Fallback procedure

1. Report `execution_mode = parent-led-fallback` and `isolation = degraded`.
2. Fingerprint the exact revision and in-scope file bytes; bind every pass and
   return to that candidate ID.
3. In a distinct reasoning pass, run the **probe** template from
   `charters/probe.md` and emit the probe JSON (`protocol.md` §Probe output).
4. Select the **band** with `python3 scripts/swarm_cli.py size` exactly as in
   native mode (`dimensions.md`). Do **not** default to a large cohort — the
   floor is still 1 reviewer and there is still no mandatory verifier.
5. Run coverage-first `plan`, including bounded evidence packs and any required
   verifier reservation; a gated verifier does not consume pre-dispatch
   capacity. Execute each assignment as its own reasoning pass. Preserve each route's returned `model_class` and `rigor`; render
   `model_slug = parent-led-fallback:<returned-slug>` so the intended allocation
   remains visible without pretending Codex launched that model. Do not leak
   probe conclusions into a charter marked `blind_to_probe`.
6. Honor the same accepted-worker ceilings/concurrency, absolute nine-worker
   cap, 20-minute start cutoff, and planned 25–60 minute healthy completion
   allowance. Account preflight/transport rejection separately from accepted
   passes.
7. Gather git/test/runtime evidence **only** in the parent context and label it
   `parent-test-confirmed`. Never spawn a pass to fulfill an evidence request.
8. Run a **verifier** pass only through the verifier gate (`authority.md`;
   SKILL.md §7). Freeze the expected candidate IDs and authorized accepted-risk
   IDs plus parent-observed coverage before that pass, then supply all
   out-of-band to validation. Any uncovered/failed/partial work withholds
   clearance. Otherwise `shipping_clearance = not_evaluated`.
9. Apply every authority and ship-gate check exactly as in native mode.
10. Render the curated report (`report.md`) and state that isolation was degraded.

If the parent cannot preserve independent passes or a probe-blind critical
review, mark the coverage gap and withhold shipping clearance.

## Native / fallback conformance

Both modes must produce results a reader cannot distinguish on substance:

- band selection and cohort sizing;
- routing obligation stated per charter (`model_class`, intended slug, and rigor)
  with parent-led execution labeled rather than presented as a native launch;
- evidence lineage and finding calibration (risk math, priority, confidence);
- revision-drift handling;
- proportional redundancy (Critical axis only);
- the per-band and absolute budget ceilings;
- authority decisions and the three-line ship gate;
- the curated final report.

Differences in prose, reviewer identity, or non-material ordering are fine.
Differences in authority, evidence claims, risk math, band selection, budgets, or
shipping clearance are not.
