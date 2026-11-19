"""Profile synthesis — build plan v3 §4.2 (profile states/precedence) and §3.2 ("One state
machine, temporal validity, source diversity, calibrated confidence").

:func:`synthesize_fact` is the single place that turns aggregated
:class:`~operator_voice.domain.models.SignalObservation` rows into a
:class:`~operator_voice.domain.models.ProfileFact`. It never mutates a ``CORRECTED`` or
``CONFIRMED`` fact's value/state from new measurements alone (§4.2: "New observations may
contradict a correction, but cannot silently replace it") — a contradiction is reported back to
the caller instead, and the frozen fact continues to be built/returned unchanged in the same
call so its ``valid_to``/``superseded_by`` bookkeeping stays centralized here.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from operator_voice.domain.models import (
    ContextScope,
    FactState,
    ProfileFact,
    ReviewReason,
    SignalObservation,
    new_id,
    now_ts,
)
from operator_voice.kernel.calibration import CalibrationThresholds, DEFAULT_CALIBRATION

SYNTHESIS_VERSION = "synthesis/v2"


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    fact: ProfileFact
    contradiction: bool
    contradiction_detail: Optional[str] = None
    # M2 (§13 worklist 3): review reasons the kernel deterministically attaches to this synthesis
    # (LOW_SOURCE_DIVERSITY, DRIFT, ...). The application layer persists them as operator review
    # items; the kernel itself performs no I/O.
    review_reasons: tuple[ReviewReason, ...] = ()
    # When material drift caused a NEW fact to supersede an existing one, the id of the fact the
    # caller must deprecate (set valid_to + superseded_by). None when the fact was updated in place.
    superseded_fact_id: Optional[str] = None


def _coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0:
        return 0.0
    stdev = statistics.pstdev(values)
    return abs(stdev / mean)


def synthesize_fact(
    *,
    subject_id: str,
    facet: str,
    scope: ContextScope,
    observations: list[SignalObservation],
    document_sources: dict[str, str],
    existing_fact: Optional[ProfileFact] = None,
    calibration: CalibrationThresholds = DEFAULT_CALIBRATION,
) -> SynthesisResult:
    """Aggregate ``observations`` (all sharing ``facet``+``scope``) into one :class:`ProfileFact`.

    ``document_sources`` maps document_id -> source_id, so source-diversity can be computed
    without a persistence round-trip (kernel purity: no I/O).
    """
    values = [float(o.value) for o in observations if isinstance(o.value, (int, float))]
    doc_ids = {o.document_id for o in observations}
    src_ids = {document_sources.get(d, d) for d in doc_ids}
    doc_count = len(doc_ids)
    src_count = len(src_ids)
    cv = _coefficient_of_variation(values)
    mean_value = statistics.fmean(values) if values else 0.0

    if existing_fact is not None and existing_fact.state in (FactState.CORRECTED, FactState.CONFIRMED):
        # §4.2: never silently replace. Detect contradiction, but return the frozen fact as-is.
        # A non-numeric existing value (e.g. a corrected string-valued facet like a banned
        # phrase) can never be numerically contradicted by aggregated numeric observations;
        # such facets are corrected/confirmed only via explicit feedback, never via this
        # numeric-aggregation path, so the safe default is "no contradiction detected".
        existing_is_numeric = isinstance(existing_fact.value, (int, float))
        contradiction = (
            bool(values)
            and existing_is_numeric
            and abs(mean_value - float(existing_fact.value)) > 1e-9
        )
        return SynthesisResult(
            fact=existing_fact,
            contradiction=contradiction,
            contradiction_detail=(
                f"new aggregate {mean_value!r} differs from {existing_fact.state.value} value "
                f"{existing_fact.value!r}"
            )
            if contradiction
            else None,
        )

    review_reasons: list[ReviewReason] = []

    if doc_count >= calibration.min_documents_for_supported and src_count >= calibration.min_sources_for_supported and cv <= calibration.max_coefficient_of_variation:
        state = FactState.SUPPORTED
        confidence = max(0.0, min(1.0, 1.0 - cv))
        # Source-diversity cap (§13 M2 worklist 3): a fact promoted on too few distinct sources is
        # a monoculture — cap its confidence and flag it for operator review rather than presenting
        # a single source as fully corroborated.
        if src_count < calibration.min_sources_for_full_confidence:
            confidence = min(confidence, calibration.single_source_confidence_cap)
            review_reasons.append(ReviewReason.LOW_SOURCE_DIVERSITY)
    elif doc_count >= calibration.min_documents_for_observed:
        state = FactState.OBSERVED
        confidence = max(0.0, min(0.5, 1.0 - cv))
    else:
        state = FactState.OBSERVED
        confidence = 0.0

    # Drift / temporal validity (§13 M2 worklist 3): when a prior OBSERVED/SUPPORTED fact exists and
    # the new aggregate value has drifted materially, mint a NEW fact (preserving history) and tell
    # the caller to supersede the old one, rather than silently overwriting it in place. A
    # non-material change keeps the existing fact_id (update in place, as M1). Corrected/confirmed
    # facts are handled above and never reach here.
    superseded_fact_id: Optional[str] = None
    reuse_fact_id = existing_fact.fact_id if existing_fact else None
    if existing_fact is not None and isinstance(existing_fact.value, (int, float)) and values:
        prior = float(existing_fact.value)
        denom = abs(prior) if prior != 0 else 1.0
        if abs(mean_value - prior) / denom > calibration.drift_relative_threshold:
            superseded_fact_id = existing_fact.fact_id
            reuse_fact_id = None  # new fact id — do not overwrite the drifted history
            review_reasons.append(ReviewReason.DRIFT)

    fact_id = reuse_fact_id if reuse_fact_id is not None else new_id("fact")
    fact = ProfileFact(
        fact_id=fact_id,
        subject_id=subject_id,
        facet=facet,
        value=mean_value,
        scope=scope,
        state=state,
        confidence=confidence,
        confidence_interval=(min(values), max(values)) if values else None,
        document_count=doc_count,
        source_count=src_count,
        provenance_ids=[o.observation_id for o in observations],
        synthesis_version=SYNTHESIS_VERSION,
        valid_from=now_ts(),
    )
    return SynthesisResult(
        fact=fact, contradiction=False,
        review_reasons=tuple(review_reasons), superseded_fact_id=superseded_fact_id,
    )
