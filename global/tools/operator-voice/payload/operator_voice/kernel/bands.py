"""Signal confidence bands — build plan §13 M2 worklist 2 ("replace uncited labels with
calibrated/explicitly heuristic bands") and decision D3 (audit §4.5: retain the *descriptive*
statistics; reject the detection-evasion *framing*).

The forensic audit's central methodological finding about the vendor signal code (audit take-table
rows for specificity-patterns / argument-flow / zscore) is that several qualitative labels were
presented as settled fact on top of **hardcoded, uncited numeric thresholds**. The audit's
instruction is explicit: "replace ... with either a cited baseline or an explicitly-labeled-as-
heuristic confidence band, not presented as settled fact."

This module encodes exactly that discipline. Every band a signal is mapped into carries a
:class:`BandProvenance`:

  * ``CALIBRATED`` — the threshold set was derived from the synthetic fixture corpus by
    ``scripts/calibrate.py`` and frozen into the calibration manifest (M2.7). The ``basis`` names
    the manifest revision.
  * ``HEURISTIC`` — no corpus calibration exists for this signal; the threshold is a transparent,
    explicitly-labeled heuristic and MUST be surfaced as such (never as settled fact).

Pure data + pure functions; no I/O, no model, no network (kernel purity, §7/D7).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

BAND_VERSION = "bands/v2"


class BandProvenance(str, enum.Enum):
    CALIBRATED = "calibrated"
    HEURISTIC = "heuristic"


@dataclass(frozen=True, slots=True)
class Band:
    """The result of classifying one raw signal value."""

    facet: str
    label: str
    provenance: BandProvenance
    lower_bound: float
    basis: str

    def as_dict(self) -> dict[str, object]:
        return {
            "facet": self.facet,
            "label": self.label,
            "provenance": self.provenance.value,
            "lower_bound": self.lower_bound,
            "basis": self.basis,
        }


@dataclass(frozen=True, slots=True)
class BandScale:
    """A descending ladder of (inclusive-lower-bound, label) thresholds for one signal facet.

    ``thresholds`` MUST be sorted high→low; :meth:`classify` returns the first band whose lower
    bound the value meets, else the implicit terminal ``floor_label``."""

    facet: str
    provenance: BandProvenance
    thresholds: tuple[tuple[float, str], ...]
    basis: str
    floor_label: str = "minimal"

    def __post_init__(self) -> None:
        bounds = [b for b, _ in self.thresholds]
        if bounds != sorted(bounds, reverse=True):
            raise ValueError(f"BandScale thresholds for {self.facet} must be descending: {bounds}")

    def classify(self, value: float) -> Band:
        for lower, label in self.thresholds:
            if value >= lower:
                return Band(
                    facet=self.facet, label=label, provenance=self.provenance,
                    lower_bound=lower, basis=self.basis,
                )
        return Band(
            facet=self.facet, label=self.floor_label, provenance=self.provenance,
            lower_bound=float("-inf"), basis=self.basis,
        )


# --------------------------------------------------------------------------------------
# Default HEURISTIC scales. These are transparent, explicitly-labeled heuristics — NOT settled
# fact (audit take-table). Any facet the M2.7 calibration manifest covers is overridden by a
# CALIBRATED scale at classify time; the rest stay honestly heuristic.
#
# The specificity ratio ladder (>0.4 / >0.25 / >0.15) reproduces the vendor's *shape* but is
# demoted to HEURISTIC exactly because the audit flagged those exact numbers as uncited
# (specificity-patterns take-table row). The argument-flow ladder generalises the vendor's
# "strong-match-ratio → confidence band" pattern (argument-flow take-table row) and is likewise
# heuristic until calibrated.
# --------------------------------------------------------------------------------------

_HEURISTIC_BASIS = (
    "explicitly-labeled heuristic (audit take-table: uncited vendor threshold demoted to "
    "heuristic, not presented as settled fact)"
)

HEURISTIC_SCALES: dict[str, BandScale] = {
    "specificity_ratio": BandScale(
        facet="specificity_ratio",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((0.40, "high"), (0.25, "medium"), (0.15, "low")),
        basis=_HEURISTIC_BASIS,
        floor_label="generic",
    ),
    "argument_flow_ratio": BandScale(
        facet="argument_flow_ratio",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((0.50, "structured"), (0.25, "moderate"), (0.10, "loose")),
        basis=_HEURISTIC_BASIS,
        floor_label="unstructured",
    ),
    "micro_rhythm_rate": BandScale(
        facet="micro_rhythm_rate",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((25.0, "high"), (10.0, "medium"), (3.0, "low")),
        basis=_HEURISTIC_BASIS,
        floor_label="flat",
    ),
    "lexical_entropy": BandScale(
        facet="lexical_entropy",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((0.85, "high"), (0.70, "medium"), (0.50, "low")),
        basis=_HEURISTIC_BASIS,
        floor_label="repetitive",
    ),
    "burstiness_sentence_length": BandScale(
        facet="burstiness_sentence_length",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((0.30, "bursty"), (0.10, "moderate"), (-0.10, "even")),
        basis=_HEURISTIC_BASIS,
        floor_label="very_even",
    ),
    "function_word_divergence": BandScale(
        facet="function_word_divergence",
        provenance=BandProvenance.HEURISTIC,
        thresholds=((2.0, "distinctive"), (1.0, "notable"), (0.5, "slight")),
        basis=_HEURISTIC_BASIS,
        floor_label="typical",
    ),
}


def classify(facet: str, value: float, calibrated_scales: dict[str, BandScale] | None = None) -> Band:
    """Classify ``value`` for ``facet``, preferring a CALIBRATED scale (from the M2.7 manifest)
    and falling back to the transparent heuristic scale. Raises ``KeyError`` for an unknown facet
    so a signal can never be silently mis-banded."""
    scales = dict(HEURISTIC_SCALES)
    if calibrated_scales:
        scales.update(calibrated_scales)
    if facet not in scales:
        raise KeyError(f"no band scale registered for signal facet {facet!r}")
    return scales[facet].classify(value)


__all__ = [
    "BAND_VERSION",
    "BandProvenance",
    "Band",
    "BandScale",
    "HEURISTIC_SCALES",
    "classify",
]
