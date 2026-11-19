"""Preregistered calibration manifest — build plan §13 M2 worklist 7 ("Run operator-reviewed
calibration and preregister metric thresholds before promoting any fact to SUPPORTED; measure
whether direct feedback lowers future correction rate") and decision D2 ("calibrate, do not
invent ... uncalibrated facts remain OBSERVED").

Like :mod:`operator_voice.eval.manifest`, this module is a FROZEN preregistration: it declares the
metric *definitions* and the *bars* a calibration run must clear, and it is pinned by
:data:`CALIBRATION_MANIFEST_DIGEST` **before** the calibration run's outputs are observed. The run
itself (``scripts/calibrate.py``) produces ``eval/calibration_report.json``; the frozen derived
constants it justifies live in :mod:`operator_voice.kernel.calibration`. Changing a bar after a
report has been observed requires a NEW manifest version with its own digest — never a retroactive
edit (D2/D21 discipline transplanted to calibration).

Nothing here performs I/O or imports the gateway/network (kept importable by the pure kernel path).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

CALIBRATION_MANIFEST_VERSION = "calibration-manifest/v2"


@dataclass(frozen=True, slots=True)
class PromotionThresholds:
    """The preregistered preconditions a fact must meet before synthesis may promote it to
    ``SUPPORTED``. These mirror :data:`operator_voice.kernel.calibration.DEFAULT_CALIBRATION`; the
    calibration run must confirm they cleanly separate the ``stable`` fixture corpora (promote)
    from the ``noisy`` corpus (stay ``OBSERVED``)."""

    min_documents_for_supported: int = 3
    min_sources_for_supported: int = 1
    max_coefficient_of_variation: float = 0.65
    min_documents_for_observed: int = 1


PROMOTION_THRESHOLDS = PromotionThresholds()

# The preregistered PRIMARY signal facets a corpus's promotion verdict is judged on. These are the
# two continuous, always-present core signals (sentence-length burstiness = rhythm; lexical entropy
# = diversity); a corpus promotes to SUPPORTED only when ALL of them clear the thresholds. This
# deliberately excludes facets that can be uniformly zero for a given voice (e.g. no em-dashes ->
# micro_rhythm_rate == 0 with zero variance), so an *absence* of signal can never be mistaken for
# stable, supported evidence. Frozen before observing the run (part of the digest).
PRIMARY_PROMOTION_FACETS: tuple[str, ...] = (
    "burstiness_sentence_length",
    "lexical_entropy",
)


@dataclass(frozen=True, slots=True)
class BandCalibrationRule:
    """Preregistered rule deciding whether a signal facet earns a CALIBRATED band (vs. staying an
    explicitly-labeled heuristic). A facet qualifies only if the stable and noisy corpora separate
    on it by at least ``min_normalized_separation`` (|mean_stable - mean_noisy| / spread) AND the
    within-stable-corpus coefficient of variation is at most ``max_stable_cv``. Facets that fail
    stay heuristic — never silently presented as calibrated fact (audit take-table)."""

    min_normalized_separation: float = 0.15
    max_stable_cv: float = 0.65


BAND_CALIBRATION_RULE = BandCalibrationRule()


@dataclass(frozen=True, slots=True)
class FeedbackEffectMetric:
    """Preregistered definition + direction for "does direct feedback lower future correction
    rate?" (§13 M2.7). ``correction_rate`` = fraction of synthetic contradiction scenarios in which
    a later contradicting observation would force a NEW correction. The bar: with a prior operator
    correction recorded, the rate must be strictly lower than without it (feedback is durable P0
    memory, D15) and must reach ``required_post_feedback_rate`` (0.0 — a recorded correction is
    never silently overwritten, §4.2)."""

    direction: str = "post_feedback_correction_rate < pre_feedback_correction_rate"
    required_post_feedback_rate: float = 0.0


FEEDBACK_EFFECT_METRIC = FeedbackEffectMetric()

# EXTERNAL subjects are excluded from operator calibration entirely (D17). The calibration run must
# report zero EXTERNAL documents contributing to any operator reference/band.
EXTERNAL_CALIBRATION_CONTRIBUTION_MUST_BE_ZERO = True


def _canonical_manifest_json() -> str:
    payload = {
        "manifest_version": CALIBRATION_MANIFEST_VERSION,
        "promotion_thresholds": {
            "min_documents_for_supported": PROMOTION_THRESHOLDS.min_documents_for_supported,
            "min_sources_for_supported": PROMOTION_THRESHOLDS.min_sources_for_supported,
            "max_coefficient_of_variation": PROMOTION_THRESHOLDS.max_coefficient_of_variation,
            "min_documents_for_observed": PROMOTION_THRESHOLDS.min_documents_for_observed,
        },
        "primary_promotion_facets": list(PRIMARY_PROMOTION_FACETS),
        "band_calibration_rule": {
            "min_normalized_separation": BAND_CALIBRATION_RULE.min_normalized_separation,
            "max_stable_cv": BAND_CALIBRATION_RULE.max_stable_cv,
        },
        "feedback_effect_metric": {
            "direction": FEEDBACK_EFFECT_METRIC.direction,
            "required_post_feedback_rate": FEEDBACK_EFFECT_METRIC.required_post_feedback_rate,
        },
        "external_calibration_contribution_must_be_zero": EXTERNAL_CALIBRATION_CONTRIBUTION_MUST_BE_ZERO,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_manifest_digest() -> str:
    return hashlib.sha256(_canonical_manifest_json().encode("utf-8")).hexdigest()


CALIBRATION_MANIFEST_DIGEST = compute_manifest_digest()


@dataclass(frozen=True, slots=True)
class ManifestCheck:
    ok: bool
    failures: tuple[str, ...]


def assert_report_meets_manifest(report: dict) -> ManifestCheck:
    """Pure check that an observed calibration ``report`` (the parsed ``calibration_report.json``)
    clears every preregistered bar. Returns a :class:`ManifestCheck`; callers/tests decide how to
    react. Never mutates the report."""
    failures: list[str] = []

    if report.get("manifest_version") != CALIBRATION_MANIFEST_VERSION:
        failures.append(
            f"report manifest_version {report.get('manifest_version')!r} != {CALIBRATION_MANIFEST_VERSION!r}"
        )
    if report.get("manifest_digest") != CALIBRATION_MANIFEST_DIGEST:
        failures.append("report manifest_digest does not match the frozen preregistered digest")

    # Promotion separation: stable corpora promote, noisy stays observed.
    promotion = report.get("promotion", {})
    for corpus_id, verdict in promotion.get("stable", {}).items():
        if verdict != "SUPPORTED":
            failures.append(f"stable corpus {corpus_id} did not reach SUPPORTED (got {verdict})")
    for corpus_id, verdict in promotion.get("noisy", {}).items():
        if verdict == "SUPPORTED":
            failures.append(f"noisy corpus {corpus_id} wrongly reached SUPPORTED")

    # Feedback effect direction + post bar.
    fb = report.get("feedback_effect", {})
    pre = fb.get("pre_feedback_correction_rate")
    post = fb.get("post_feedback_correction_rate")
    if pre is None or post is None:
        failures.append("feedback_effect missing pre/post correction rate")
    else:
        if not (post < pre):
            failures.append(f"feedback did not lower correction rate: post={post} !< pre={pre}")
        if post > FEEDBACK_EFFECT_METRIC.required_post_feedback_rate:
            failures.append(
                f"post-feedback correction rate {post} exceeds required "
                f"{FEEDBACK_EFFECT_METRIC.required_post_feedback_rate}"
            )

    # EXTERNAL exclusion.
    if EXTERNAL_CALIBRATION_CONTRIBUTION_MUST_BE_ZERO:
        ext = report.get("external_documents_contributing")
        if ext not in (0, None) and ext != 0:
            failures.append(f"EXTERNAL documents contributed to calibration: {ext}")

    return ManifestCheck(ok=not failures, failures=tuple(failures))


__all__ = [
    "CALIBRATION_MANIFEST_VERSION",
    "CALIBRATION_MANIFEST_DIGEST",
    "PromotionThresholds",
    "PROMOTION_THRESHOLDS",
    "PRIMARY_PROMOTION_FACETS",
    "BandCalibrationRule",
    "BAND_CALIBRATION_RULE",
    "FeedbackEffectMetric",
    "FEEDBACK_EFFECT_METRIC",
    "EXTERNAL_CALIBRATION_CONTRIBUTION_MUST_BE_ZERO",
    "compute_manifest_digest",
    "ManifestCheck",
    "assert_report_meets_manifest",
]
