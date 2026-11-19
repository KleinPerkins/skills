"""Pure evidence-measure collectors — turn raw pass/fail or scan counts into the [0, 100]
normalized rates :mod:`operator_voice.eval.manifest`'s formula consumes. Every function here is a
pure function of its arguments; none of them read a filesystem, run a test suite, or call the
network. That separation matters for the "preregister the formula before observing results"
invariant: this module can be reviewed and frozen (its arithmetic is trivial and obviously
correct) independently of whatever later commit collects and reports actual counts.
"""

from __future__ import annotations

from dataclasses import dataclass

from operator_voice.eval.manifest import EvidenceReport


def rate(passed: int, total: int) -> float:
    """A [0, 100] pass rate. ``total == 0`` is undefined evidence (not a rate of 100 OR 0) — the
    caller must treat a zero-total measure as missing from the :class:`EvidenceReport` it builds,
    never coerce it to a number, so it correctly triggers manifest.ABSTAIN downstream."""
    if total < 0 or passed < 0 or passed > total:
        raise ValueError(f"invalid rate(passed={passed!r}, total={total!r})")
    if total == 0:
        raise ZeroDivisionError("rate() of an empty evidence set is undefined; treat as missing, not zero")
    return 100.0 * passed / total


def clean_rate(open_findings: int, total_findings: int) -> float:
    """1.0-minus-open-fraction, expressed on the same [0, 100] scale as :func:`rate`.
    ``total_findings == 0`` (nothing was ever raised) is a clean 100, unlike :func:`rate` — an
    empty finding set IS meaningful evidence of a clean review, not missing evidence."""
    if open_findings < 0 or total_findings < 0 or open_findings > total_findings:
        raise ValueError(f"invalid clean_rate(open={open_findings!r}, total={total_findings!r})")
    if total_findings == 0:
        return 100.0
    return 100.0 * (1.0 - open_findings / total_findings)


@dataclass(frozen=True, slots=True)
class BudgetAdherence:
    """One pinned regression budget vs. one observed value (build plan §7's "observed baseline
    plus a justified margin"). ``lower_is_better`` covers latency/memory/growth measures; flip it
    for a measure where higher is the desired direction (none exist in M1's budget set today, but
    the field keeps the helper honest rather than latency-shaped-only)."""

    observed: float
    budget: float
    lower_is_better: bool = True

    def met(self) -> bool:
        return self.observed <= self.budget if self.lower_is_better else self.observed >= self.budget


def benchmark_budget_adherence_rate(adherences: list[BudgetAdherence]) -> float:
    """§ Measure ``benchmark_budget_adherence_rate``: fraction of pinned budgets met by the most
    recent benchmark run. Empty input is a caller bug (there is always at least one pinned
    budget once M1's benchmark baseline exists) — raises rather than silently returning 100."""
    if not adherences:
        raise ValueError("benchmark_budget_adherence_rate() requires at least one BudgetAdherence")
    met = sum(1 for a in adherences if a.met())
    return rate(met, len(adherences))


def build_evidence_report(**measures: float) -> EvidenceReport:
    """Thin, typo-resistant constructor: keyword args must be known
    :data:`operator_voice.eval.manifest.MEASURES` ids. Anything else raises immediately rather
    than silently building a report the formula will never look at."""
    from operator_voice.eval.manifest import _MEASURES_BY_ID  # local import: private, intra-package use only

    unknown = set(measures) - set(_MEASURES_BY_ID)
    if unknown:
        raise ValueError(f"unknown evidence measure id(s): {sorted(unknown)!r}")
    for k, v in measures.items():
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"measure {k!r} value {v!r} out of [0, 100] range")
    return EvidenceReport(values=dict(measures))
