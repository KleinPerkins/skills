"""EXTERNAL-subject communication analysis — build plan v4 §4.3 subject-kind table, §13 M4
worklist 2, and decision D17 ("external subjects are analysis-only and separately gated").

This module is PURE and deterministic (no I/O, no model, no persistence). It answers three
questions the application service asks when an operator requests insights about a NAMED
non-operator who has been explicitly enrolled as an ``EXTERNAL`` subject:

1. **Is this purpose allowed at all?** (:func:`classify_purpose`) — a request that asks OVT to
   *generate/impersonate*, to *forecast a future decision/action*, to read an *explicit
   protected/sensitive trait* or *mental state*, or to drive a *high-impact decision* about the
   person is REFUSED at the kernel, before any evidence is read. Refusal is by deterministic
   keyword intent, never by a model.
2. **Which facets may be surfaced?** (:func:`is_denied_facet`) — a reviewed high-risk facet
   denylist limits proxy leakage. OVT's own extractors only emit neutral communication-pattern
   facets, so the denylist is a defensive enforcement point: if any protected-trait facet ever
   existed, it is excluded here regardless of how it entered the profile.
3. **What does the evidence actually support?** (:func:`build_insight_observations`) — eligible
   facts become evidence-bounded observations with EXPLICIT uncertainty (confidence + how many
   independent sources) and counter-evidence; the bundle always carries a standing proxy-risk
   warning. Observations are descriptive ("has usually written in short sentences"), never
   prescriptive authoring instructions — a :class:`SubjectInsightBundle` structurally cannot carry
   ``instructions``/``ranked_facts`` (contract-enforced in :mod:`operator_voice.domain.contracts`).
"""

from __future__ import annotations

from dataclasses import dataclass

from operator_voice.domain.models import FactState, ProfileFact, SubjectInsight

EXTERNAL_ANALYSIS_VERSION = "external-analysis/v1"

# A standing, non-removable caveat on every EXTERNAL insight bundle (§4.3: "a denylist and warning
# reduce but do not claim to eliminate proxy leakage"; D17). Never phrased as a guarantee.
PROXY_RISK_WARNING = (
    "Communication-pattern analysis of another person is inherently uncertain and can act as a "
    "proxy for characteristics you did not ask about. These are historical, evidence-bounded "
    "observations only — not predictions of future behavior, not a personality or sensitive-trait "
    "assessment, and never a basis for a high-impact decision about this person."
)

# Reviewed high-risk facet denylist (§13 M4 worklist 2). Never surfaced in an insight bundle even
# if such a fact were somehow present. OVT's extractors do not emit these; this is defense in depth.
HIGH_RISK_FACET_DENYLIST = frozenset(
    {
        "political_lean", "political_affiliation", "religion", "religious_affiliation",
        "ethnicity", "race", "national_origin", "sexual_orientation", "gender_identity",
        "health_status", "medical_condition", "disability", "mental_state", "mental_health",
        "diagnosis", "personality", "personality_type", "sentiment", "mood", "emotion",
        "immigration_status", "union_membership", "criminal_history", "financial_status",
        "credit_score", "income", "pregnancy", "genetic_data", "biometric",
    }
)
# Any facet under one of these namespaces is also denied (a forward-compatible guard so a future
# extractor can't route a protected trait around the flat denylist above).
_DENIED_NAMESPACES = ("sensitive:", "protected:", "trait:", "identity:")


def is_denied_facet(facet: str) -> bool:
    f = (facet or "").strip().lower()
    if f in HIGH_RISK_FACET_DENYLIST:
        return True
    return any(f.startswith(ns) for ns in _DENIED_NAMESPACES)


# --------------------------------------------------------------------------------------
# Purpose classification (fail-closed refusal set — §4.3 subject-kind table, D17)
# --------------------------------------------------------------------------------------

# Generation / impersonation: the whole point of the EXTERNAL boundary is that OVT never produces
# authoring context for someone who is not the operator (§4.3).
_GENERATION_MARKERS = (
    "generate", "write as", "write like", "sound like", "impersonate", "in their voice",
    "in his voice", "in her voice", "as them", "mimic", "draft as", "compose as", "ghostwrite",
    "reply as", "respond as", "author as", "voice match", "voice-match",
)
# Forecasts of a FUTURE decision/action/conduct ("will decide Y").
_FORECAST_MARKERS = (
    "will decide", "will do", "will say", "predict", "prediction", "forecast", "future decision",
    "future behavior", "future behaviour", "what will they", "how will they", "next move",
    "going to decide", "likely to decide", "anticipate their",
)
# Explicit protected / sensitive-trait requests + mental-state diagnosis.
_SENSITIVE_TRAIT_MARKERS = (
    "political", "religion", "religious", "ethnicity", "race", "sexual orientation", "gender identity",
    "health", "medical", "mental state", "mental health", "diagnos", "personality type",
    "psychological profile", "psych profile", "disability", "immigration", "criminal", "sexuality",
    "pregnan", "genetic", "biometric",
)
# High-impact decision support about the person (§4.3 "high-impact decision use").
_HIGH_IMPACT_MARKERS = (
    "hire", "fire", "promote", "terminate", "creditworth", "credit worth", "loan", "underwrit",
    "medical decision", "legal advice", "custody", "sentencing", "should i trust", "background check",
    "should we hire", "should we fire", "performance review of",
)

_REFUSAL_CATEGORIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "generation_or_impersonation",
        _GENERATION_MARKERS,
        "EXTERNAL subjects never receive generation or authoring context — OVT will not help you "
        "write as, sound like, or impersonate another person.",
    ),
    (
        "future_decision_forecast",
        _FORECAST_MARKERS,
        "OVT reports historical communication patterns only; it will not forecast a specific future "
        "decision, action, or conduct of another person.",
    ),
    (
        "protected_or_sensitive_trait",
        _SENSITIVE_TRAIT_MARKERS,
        "OVT will not infer protected or sensitive traits (political, religious, health, mental "
        "state, orientation, etc.) about another person.",
    ),
    (
        "high_impact_decision_support",
        _HIGH_IMPACT_MARKERS,
        "OVT will not provide analysis to drive a high-impact decision (hiring/firing, credit, "
        "medical, legal, custody, trust) about another person.",
    ),
)


@dataclass(frozen=True, slots=True)
class PurposeVerdict:
    allowed: bool
    category: str  # "analysis" when allowed; otherwise the refusal category
    reason: str


def classify_purpose(purpose: str) -> PurposeVerdict:
    """Deterministic, keyword-driven purpose gate. Returns ``allowed=False`` (with the specific
    refusal category + plain-language reason) for any generation/impersonation, future-decision
    forecast, protected/sensitive-trait, or high-impact-decision purpose; otherwise ``allowed=True``
    with category ``analysis``. Order is fixed so a purpose that trips multiple markers gets a
    stable, deterministic category."""
    text = (purpose or "").strip().lower()
    if not text:
        return PurposeVerdict(False, "unspecified_purpose", "An explicit analysis purpose is required for an EXTERNAL subject.")
    for category, markers, reason in _REFUSAL_CATEGORIES:
        if any(marker in text for marker in markers):
            return PurposeVerdict(False, category, reason)
    return PurposeVerdict(True, "analysis", "historical communication-pattern analysis")


# --------------------------------------------------------------------------------------
# Evidence -> insight observations (evidence-bounded, uncertainty + counter-evidence)
# --------------------------------------------------------------------------------------

# Only calibrated/curated states become external observations. OBSERVED is too raw, MODEL_HYPOTHESIS
# is never trusted without operator confirmation (and there is no operator for an EXTERNAL subject),
# DEPRECATED is excluded from all retrieval.
_INSIGHTABLE_STATES = frozenset({FactState.SUPPORTED, FactState.CONFIRMED, FactState.CORRECTED})


def _uncertainty_phrase(fact: ProfileFact) -> str:
    conf = fact.confidence
    if fact.source_count <= 1:
        strength = "low confidence (a single source)"
    elif conf >= 0.8:
        strength = f"higher confidence ({conf:.0%}, {fact.source_count} sources)"
    elif conf >= 0.5:
        strength = f"moderate confidence ({conf:.0%}, {fact.source_count} sources)"
    else:
        strength = f"low confidence ({conf:.0%})"
    span = ""
    if fact.confidence_interval:
        lo, hi = fact.confidence_interval
        span = f"; observed range ~{lo:.2g}–{hi:.2g}"
    return f"{strength}{span}"


def _counter_evidence(fact: ProfileFact) -> list[str]:
    caveats: list[str] = []
    if fact.source_count <= 1:
        caveats.append("supported by only one source — may not generalize.")
    if fact.document_count <= 2:
        caveats.append(f"based on very few samples (documents={fact.document_count}).")
    if fact.confidence < 0.5:
        caveats.append("below the trust floor; treat as tentative.")
    caveats.append("a communication pattern is not a stable trait and can change by context.")
    return caveats


def build_insight_observations(
    facts: list[ProfileFact], *, max_observations: int = 25
) -> tuple[list[SubjectInsight], list[str]]:
    """Turn an EXTERNAL subject's retained facts into evidence-bounded observations. Returns
    ``(observations, warnings)``. Denied facets are excluded (and counted in a warning so the
    exclusion is visible, never silent). Deterministic ordering: by facet then scope key."""
    warnings: list[str] = []
    denied = sorted({f.facet for f in facts if is_denied_facet(f.facet)})
    if denied:
        warnings.append(
            f"{len(denied)} high-risk facet(s) were excluded from this analysis by the denylist."
        )
    eligible = [
        f
        for f in facts
        if f.state in _INSIGHTABLE_STATES and not is_denied_facet(f.facet)
    ]
    eligible.sort(key=lambda f: (f.facet, f.scope.key()))
    observations: list[SubjectInsight] = []
    for fact in eligible[:max_observations]:
        scope_note = "" if fact.scope.key().startswith("general|") else f" in {fact.scope.key()}"
        observations.append(
            SubjectInsight(
                facet=fact.facet,
                observation=(
                    f"Has historically shown '{fact.facet}'{scope_note} around {_render_value(fact.value)}."
                ),
                uncertainty=_uncertainty_phrase(fact),
                counter_evidence=_counter_evidence(fact),
            )
        )
    if not observations and not warnings:
        warnings.append("No calibrated communication-pattern evidence is available for this subject yet.")
    return observations, warnings


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{float(value):.3g}"
    text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."


__all__ = [
    "EXTERNAL_ANALYSIS_VERSION",
    "PROXY_RISK_WARNING",
    "HIGH_RISK_FACET_DENYLIST",
    "is_denied_facet",
    "PurposeVerdict",
    "classify_purpose",
    "build_insight_observations",
]
