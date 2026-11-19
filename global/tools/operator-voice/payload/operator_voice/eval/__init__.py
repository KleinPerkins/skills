"""Preregistered evaluation manifest, evidence measures, and benchmark harness — build plan
§13 M1 worklist item 9 / §12: "M1 creates a versioned evaluation manifest before tuning: corpus
eligibility, document-level/time-aware splits, leakage checks, metric formulas, aggregation
weights, abstention rules, observed-baseline-derived pass bands, and the exact mapping from each
evidence measure into each of the ten GA dimension scores." D21: "M1 preregisters the exact
evidence-to-score mapping; changing weights after results is forbidden."

Sequencing invariant enforced by this package's own commit history, not by code: ``manifest.py``
(the formula/weights/mapping) must land in a commit BEFORE any commit that adds a measured
baseline value. No function in this package computes or reports a GA (≥95×10, §13 M5) score —
that scoring event, and the independent review that must accompany it, is out of M1 scope. What
M1 *does* produce is the frozen manifest itself, plus the M1 performance-benchmark baseline
(§7: "M1 benchmarks synthetic small/medium/large corpora ... and pins lightweight regression
budgets as observed baseline plus a justified margin") — a narrower, already-in-M1-scope sibling
of the same "measure before committing to a number" discipline.
"""
