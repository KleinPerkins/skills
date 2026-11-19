"""Deterministic retrieval — build plan v3 §7 (performance/token design) and quality gate §10.11:
"Retrieval never injects the whole profile or raw examples by default, respects a token budget,
and abstains below the quality floor."

Determinism contract (§7): "Repeating the same query against the same generation returns
byte-identical context except for ``bundle_id`` and ``created_at``." Ranking is therefore a total order with an explicit final tie-breaker
(``fact_id``) so no two facts can ever compare equal.

M2 (build plan §13 worklist 1, "multi-context synthesis, ranking, and bleed tests"): scope
matching now flows through ``kernel.taxonomy``. A fact may serve a request either exactly or via
an explicitly-enumerated relaxation (a more-general value on a relaxable dimension, or a
same-base-language variant fallback). Every relaxation a *selected* fact relied on is reported in
the bundle warnings — there is no unreported bleed, and cross-base-language facts are never
selected at all. This generalises M1's silent exact+general fallback while preserving its
observable behaviour for the single-dimension cases.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from operator_voice.domain.contracts import voice_context_bundle_to_dict

from operator_voice.domain.models import (
    FACT_STATE_PRECEDENCE,
    RETRIEVAL_ELIGIBLE_STATES,
    ContextScope,
    FactState,
    ProfileFact,
    RankedFact,
    VoiceContextBundle,
    new_id,
    now_ts,
)
from operator_voice.kernel import taxonomy

RETRIEVAL_VERSION = "retrieval/v2"

EMITTED_JSON_SEPARATORS = (",", ":")
MIN_TOKEN_BUDGET, MAX_TOKEN_BUDGET = 200, 10**12 - 1
OPERATOR_AUTHORITATIVE_STATES = frozenset({FactState.CORRECTED, FactState.CONFIRMED})
_TRUNCATION_WARNING, _ABSTAIN_WARNING = "token_budget_truncated", "abstained_below_quality_floor"
# Sizing swaps in envelope values at least as wide as any real one, so the cut never depends on the
# clock, the ids or the budget's digits, and the sized total bounds the emitted one.
_SIZING_ENVELOPE = {"bundle_id": "b" * 64, "created_at": "9" * 24,
                    "budget_tokens": MAX_TOKEN_BUDGET, "actual_tokens": MAX_TOKEN_BUDGET}


# A whole profile is never injected (§7 hard rule); this is the minimum number of eligible,
# in-scope facts required before the bundle is considered informative enough to return instead
# of abstaining.
QUALITY_FLOOR_MIN_FACTS = 1

# Conservative stdlib-only token estimator (§7: "Unknown tokenizers use a conservative estimator
# and surface uncertainty; they never silently overrun"). ~4 characters/token is a standard
# conservative approximation for English text across common tokenizers.
_CHARS_PER_TOKEN_ESTIMATE = 4


class BundleBudgetError(ValueError):
    """Even an abstention envelope cannot fit the requested budget."""


def estimate_tokens(text: str, tokenizer: str | None = None) -> int:
    if not text:
        return 0
    # A named tokenizer could plug in a real encoder later; unknown/None always uses the
    # conservative estimator and never silently overruns a budget.
    return max(1, (len(text) // _CHARS_PER_TOKEN_ESTIMATE) + 1)


def _fact_sort_key(fact: ProfileFact) -> tuple[int, float, float, str]:
    # (state precedence desc, confidence desc, recency desc, fact_id asc) — §7 "stable
    # tie-breakers over scope match, operator precedence, confidence, recency policy, fact ID".
    return (
        -FACT_STATE_PRECEDENCE[fact.state],
        -fact.confidence,
        -fact.valid_from,
        fact.fact_id,
    )


def rank_facts_with_relaxations(
    facts: list[ProfileFact], request_scope: ContextScope
) -> list[tuple[ProfileFact, tuple[str, ...]]]:
    """Rank retrieval-eligible facts for a request, pairing each with the ordered relaxation tags
    it required (empty tuple = exact-scope match). Facts are grouped by taxonomy candidate order
    (exact first, then base-language / context relaxations per ``taxonomy.candidate_scopes``) and
    within each group sorted by the M1 total order (state, confidence, recency, fact_id). Facts
    that would be cross-context or cross-base-language *bleed* are excluded entirely."""
    eligible = [f for f in facts if f.state in RETRIEVAL_ELIGIBLE_STATES]
    candidates = taxonomy.candidate_scopes(request_scope)
    index: dict[str, int] = {}
    relax: dict[str, tuple[str, ...]] = {}
    for i, cand in enumerate(candidates):
        key = cand.scope.key()
        if key not in index:  # first (most-specific) candidate wins for a given scope key
            index[key] = i
            relax[key] = cand.relaxations

    grouped: list[tuple[int, ProfileFact]] = []
    for fact in eligible:
        norm_key = taxonomy.normalize_scope(fact.scope).key()
        if norm_key in index:
            grouped.append((index[norm_key], fact))
        # else: not exact and not an enumerated relaxation → excluded as bleed (never blended).

    grouped.sort(key=lambda pair: (pair[0], _fact_sort_key(pair[1])))
    out: list[tuple[ProfileFact, tuple[str, ...]]] = []
    for cand_index, fact in grouped:
        norm_key = taxonomy.normalize_scope(fact.scope).key()
        out.append((fact, relax[norm_key]))
    return out


def rank_facts(facts: list[ProfileFact], request_scope: ContextScope) -> list[ProfileFact]:
    return [fact for fact, _relaxations in rank_facts_with_relaxations(facts, request_scope)]


@dataclass(frozen=True, slots=True)
class BundleRequest:
    subject_id: str
    consumer_id: str
    generation_id: str
    scope: ContextScope
    token_budget: int
    tokenizer: str | None = None


def _instructions_for(fact: ProfileFact) -> str:
    return f"{fact.facet}={fact.value!r} (confidence={fact.confidence:.2f})"


def serialized_tokens(bundle: VoiceContextBundle, tokenizer=None, *, fixed_envelope: bool = False) -> int:
    payload = voice_context_bundle_to_dict(bundle)
    if fixed_envelope:
        payload.update(_SIZING_ENVELOPE)
    return estimate_tokens(json.dumps(payload, separators=EMITTED_JSON_SEPARATORS, default=str), tokenizer)


def _one_fact_per_key(ranked):
    authoritative, inferred = {}, {}
    for fact, relaxations in ranked:
        key = (fact.facet, fact.value) if fact.facet in taxonomy.SET_VALUED_FACETS else fact.facet
        if fact.state in OPERATOR_AUTHORITATIVE_STATES:
            current = authoritative.get(key)
            if current is None or _fact_sort_key(fact) < _fact_sort_key(current[0]):
                authoritative[key] = (fact, relaxations)
        elif fact.scope.channel not in taxonomy.LEGACY_CHANNEL_LABELS:
            inferred.setdefault(key, (fact, relaxations))
    first = sorted(authoritative.values(), key=lambda pair: _fact_sort_key(pair[0]))
    return first, [pair for key, pair in inferred.items() if key not in authoritative]


def build_context_bundle(request: BundleRequest, facts: list[ProfileFact],
                         warnings: list[str] | None = None) -> VoiceContextBundle:
    authoritative, inferred = _one_fact_per_key(rank_facts_with_relaxations(facts, request.scope))
    envelope = (request, list(warnings or []), new_id("bundle"), now_ts())

    def size(pairs, truncated=True, extra=()):
        return serialized_tokens(_assemble(*envelope, pairs, truncated, extra), request.tokenizer, fixed_envelope=True)

    def finish(pairs, truncated, extra=()):
        tokens = size(pairs, truncated, extra)
        if tokens > request.token_budget:
            # Request metadata and caller warnings cannot be silently dropped. If even the
            # abstention envelope cannot fit, refuse instead of emitting an oversized bundle.
            raise BundleBudgetError(f"token_budget cannot fit the bundle envelope; minimum_budget_tokens:{tokens}")
        return replace(_assemble(*envelope, pairs, truncated, extra), actual_tokens=tokens)

    floor = size(authoritative)
    if floor > request.token_budget:
        return finish([], False, (f"minimum_budget_tokens:{floor}", _ABSTAIN_WARNING))
    chosen = list(authoritative)
    for pair in inferred:  # strict prefix: stop at the first fact that doesn't fit
        if size(chosen + [pair]) > request.token_budget:
            break
        chosen.append(pair)
    truncated = len(chosen) < len(authoritative) + len(inferred)
    if len(chosen) < QUALITY_FLOOR_MIN_FACTS:
        return finish([], truncated, (_ABSTAIN_WARNING,))
    return finish(chosen, truncated)


def _assemble(request, caller_warnings, bundle_id, created_at, pairs, truncated, extra):
    selected = [fact for fact, _ in pairs]
    warnings = list(caller_warnings)
    if truncated:
        warnings.append(_TRUNCATION_WARNING)
    relaxations = {tag for _, tags in pairs for tag in tags}
    warnings.extend(f"context_relaxation:{tag}" for tag in sorted(relaxations))
    warnings.extend(extra)
    return VoiceContextBundle(
        bundle_id=bundle_id,
        subject_id=request.subject_id,
        consumer_id=request.consumer_id,
        generation_id=request.generation_id,
        request_scope=request.scope,
        ranked_facts=[
            RankedFact(
                facet=f.facet, value=f.value, state=f.state, confidence=f.confidence,
                scope=f.scope, provenance_ids=[], document_count=f.document_count,
            )
            for f in selected
        ],
        instructions={
            "generative": [_instructions_for(f) for f in selected if f.state != FactState.CORRECTED],
            "corrective": [_instructions_for(f) for f in selected if f.state == FactState.CORRECTED],
        },
        warnings=warnings,
        provenance_refs=[],
        budget_tokens=request.token_budget,
        actual_tokens=0,
        confidence=sum(f.confidence for f in selected) / len(selected) if selected else 0.0,
        abstained=bool(extra),
        created_at=created_at,
    )
