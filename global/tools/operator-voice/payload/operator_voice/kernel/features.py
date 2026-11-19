"""Tier-1 deterministic stylometric features — build plan v3 audit §4.1 (write-like-me Tier-1),
§3.2 ("One versioned SignalObservation registry"), §7 ("Core extraction is deterministic and
stdlib-first"). Every function is pure and stdlib-only (``re``, ``statistics``, ``collections``);
no NLP dependency is imported for Tier-1 (optional NLP tiers are a separate M2+ extra, §7).

Each public ``compute_*`` function returns a plain float/dict value; :func:`extract_all` wraps
them into :class:`~operator_voice.domain.models.SignalObservation` rows with a stable
:func:`observation_key` HMAC idempotency key (§5 SignalObservation, quality gate §10.3 exactly-
once ingestion).
"""

from __future__ import annotations

import hashlib
import hmac
import statistics
from collections import Counter
from typing import Any

from operator_voice.domain.models import ContextScope, SignalObservation, new_id, now_ts
from operator_voice.kernel.normalize import split_sentences, tokenize_words

FEATURE_REGISTRY_VERSION = "features/v2"

# A small, fixed, closed function-word set (English). Deliberately conservative for M1 — this is
# the write-like-me "Tier-1" set audited as strongest/reusable (audit §3.1); it is a re-authored,
# independently-written closed list, not copied source (see NOTICE).
FUNCTION_WORDS: tuple[str, ...] = (
    "the", "a", "an", "and", "but", "or", "because", "however", "therefore", "although",
    "so", "yet", "nor", "if", "unless", "while", "since", "though", "moreover", "furthermore",
    "of", "in", "on", "at", "to", "for", "with", "by", "as", "that", "this", "these", "those",
)

_PUNCTUATION_MARKS: tuple[str, ...] = (".", ",", "!", "?", ";", ":", "-", "—", '"', "'")

CONTRACTION_SUFFIXES = ("n't", "'re", "'ve", "'ll", "'d", "'m", "'s")


def observation_key(secret: bytes, subject_id: str, document_id: str, segment_id: str, facet: str) -> str:
    """Stable keyed-HMAC idempotency key (§5 SignalObservation). Re-ingesting the same
    document/segment/facet under the same install always yields the same key, so duplicate
    ingestion is a pure UPSERT, never a duplicate row (quality gate §10.3)."""
    msg = f"{subject_id}\x1f{document_id}\x1f{segment_id}\x1f{facet}\x1f{FEATURE_REGISTRY_VERSION}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def compute_sentence_length_stats(sentences: list[str]) -> dict[str, float]:
    lengths = [len(tokenize_words(s)) for s in sentences if s.strip()]
    if not lengths:
        return {"mean": 0.0, "stdev": 0.0, "count": 0.0}
    mean = statistics.fmean(lengths)
    stdev = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0
    return {"mean": mean, "stdev": stdev, "count": float(len(lengths))}


def compute_burstiness(lengths: list[int]) -> float:
    """Goldstein-style burstiness index B = (sigma - mu) / (sigma + mu) over inter-event
    magnitudes (here: sentence token-lengths as the event-size series). B in [-1, 1]; B=0 is a
    perfectly regular (Poisson-like) series, B>0 is bursty (audit §3.1 voice-analyser-mcp
    "burstiness" concept — independently re-derived from the standard Goldstein/Barabasi
    formula, not copied source; see NOTICE)."""
    if len(lengths) < 2:
        return 0.0
    mu = statistics.fmean(lengths)
    sigma = statistics.pstdev(lengths)
    denom = sigma + mu
    if denom == 0:
        return 0.0
    return (sigma - mu) / denom


def compute_mattr(words: list[str], window: int = 50) -> float:
    """Moving-Average Type-Token Ratio. Falls back to plain TTR when the text is shorter than
    one window (avoids MATTR's known short-text instability)."""
    n = len(words)
    if n == 0:
        return 0.0
    if n <= window:
        return len(set(words)) / n
    ratios = []
    for i in range(0, n - window + 1):
        win = words[i : i + window]
        ratios.append(len(set(win)) / window)
    return statistics.fmean(ratios)


def compute_punctuation_rates(text: str) -> dict[str, float]:
    total_chars = max(len(text), 1)
    counts = Counter(ch for ch in text if ch in _PUNCTUATION_MARKS)
    # rate per 1000 characters — stable regardless of document length
    return {f"punct_{_punct_name(mark)}_rate": (counts.get(mark, 0) / total_chars) * 1000.0 for mark in _PUNCTUATION_MARKS}


def _punct_name(mark: str) -> str:
    return {
        ".": "period", ",": "comma", "!": "exclamation", "?": "question", ";": "semicolon",
        ":": "colon", "-": "hyphen", "—": "emdash", '"': "dquote", "'": "squote",
    }.get(mark, "other")


def compute_function_word_rates(words: list[str]) -> dict[str, float]:
    n = max(len(words), 1)
    counts = Counter(words)
    return {f"fw_{w}_rate": (counts.get(w, 0) / n) * 100.0 for w in FUNCTION_WORDS}


def compute_contraction_rate(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    n_contracted = sum(1 for w in words if any(suf in w.lower() for suf in CONTRACTION_SUFFIXES))
    return n_contracted / len(words)


def compute_avg_word_length(words: list[str]) -> float:
    if not words:
        return 0.0
    return statistics.fmean(len(w) for w in words)


def extract_features(text: str) -> dict[str, Any]:
    """Compute the full Tier-1 feature set for one authored segment. Pure function of ``text``."""
    sentences = split_sentences(text)
    words = tokenize_words(text)
    sentence_lengths = [len(tokenize_words(s)) for s in sentences if s.strip()]

    features: dict[str, Any] = {}
    features["sentence_length"] = compute_sentence_length_stats(sentences)
    features["burstiness_sentence_length"] = compute_burstiness(sentence_lengths)
    features["mattr"] = compute_mattr(words)
    features["ttr"] = len(set(words)) / len(words) if words else 0.0
    features["avg_word_length"] = compute_avg_word_length(words)
    features["contraction_rate"] = compute_contraction_rate(text)
    features.update(compute_punctuation_rates(text))
    features.update(compute_function_word_rates(words))
    features["word_count"] = float(len(words))
    features["sentence_count"] = float(len(sentences))
    return features


def features_to_observations(
    *,
    secret: bytes,
    subject_id: str,
    document_id: str,
    segment_id: str,
    text: str,
    context: ContextScope,
) -> list[SignalObservation]:
    """Flatten :func:`extract_features` into one :class:`SignalObservation` per scalar facet.
    Distribution-shaped facets (``sentence_length``) keep their sub-dict in ``distribution``."""
    features = extract_features(text)
    observations: list[SignalObservation] = []
    for facet, value in features.items():
        if isinstance(value, dict):
            scalar_value = value.get("mean", 0.0)
            distribution = {k: float(v) for k, v in value.items()}
        else:
            scalar_value = value
            distribution = None
        key = observation_key(secret, subject_id, document_id, segment_id, facet)
        observations.append(
            SignalObservation(
                observation_id=new_id("obs"),
                observation_key=key,
                subject_id=subject_id,
                document_id=document_id,
                segment_id=segment_id,
                facet=facet,
                value=scalar_value,
                distribution=distribution,
                context=context,
                method_version=FEATURE_REGISTRY_VERSION,
                created_at=now_ts(),
            )
        )
    return observations
