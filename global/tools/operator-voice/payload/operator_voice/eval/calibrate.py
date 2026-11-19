"""Calibration harness — build plan §13 M2 worklist 7 / decision D2. Deterministically derives the
evidence-grounded calibration artifacts from the synthetic fixture corpora and checks them against
the preregistered :mod:`operator_voice.eval.calibration_manifest`.

Outputs (written by ``scripts/calibrate.py`` into ``eval/calibration_report.json``):
  * per-corpus signal statistics and SUPPORTED/OBSERVED promotion verdicts (via the *real*
    :func:`operator_voice.kernel.synthesis.synthesize_fact` path, not a re-derivation);
  * a function-word reference distribution derived from the stable OPERATOR corpora only
    (EXTERNAL corpora are excluded — D17);
  * CALIBRATED band scales for the signal facets that clear the preregistered separation bar
    (the rest stay explicitly heuristic);
  * a measured feedback-effect (pre/post correction rate) proving direct feedback lowers the
    future correction rate.

This module reads a JSON corpus file (I/O) and therefore lives in the ``eval`` layer, never the
pure kernel. The runtime loader :func:`load_calibrated_artifacts` lets the application layer feed
the derived reference/bands back into the pure kernel as inputs (kernel stays pure).
"""

from __future__ import annotations

import json
import pathlib
import statistics
from typing import Any

from operator_voice.domain.models import ContextScope, FactState, ProfileFact, new_id
from operator_voice.eval import calibration_manifest as cm
from operator_voice.kernel import bands, features, signals
from operator_voice.kernel.calibration import DEFAULT_CALIBRATION
from operator_voice.kernel.normalize import tokenize_words
from operator_voice.kernel.synthesis import synthesize_fact

_SECRET = b"calibration-harness-fixed-secret"

# Signal facets we attempt to calibrate a band for. function_word_divergence is excluded: it
# depends on the very reference we are deriving here, so it stays heuristic by construction.
_BANDABLE_FACETS: tuple[str, ...] = tuple(
    f for f in signals.SIGNAL_FACETS if f != "function_word_divergence"
)


def default_corpus_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "corpora" / "manifest.json"


def default_report_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3] / "eval" / "calibration_report.json"


def load_corpora(path: pathlib.Path | None = None) -> dict[str, Any]:
    path = path or default_corpus_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _corpus_signal_observations(corpus: dict[str, Any]) -> dict[str, list]:
    """Return {facet: [SignalObservation, ...]} for one corpus (no reference — divergence stays 0
    here; the reference is derived separately)."""
    by_facet: dict[str, list] = {f: [] for f in signals.SIGNAL_FACETS}
    context = ContextScope.from_dict(corpus.get("context", {}))
    for doc in corpus["documents"]:
        obs = signals.signals_to_observations(
            secret=_SECRET, subject_id=corpus["corpus_id"], document_id=doc["document_id"],
            segment_id="seg_0", text=doc["text"], context=context,
        )
        for o in obs:
            by_facet[o.facet].append(o)
    return by_facet


def _document_sources(corpus: dict[str, Any]) -> dict[str, str]:
    return {d["document_id"]: d.get("source_id", d["document_id"]) for d in corpus["documents"]}


def corpus_signal_stats(corpus: dict[str, Any]) -> dict[str, dict[str, float]]:
    by_facet = _corpus_signal_observations(corpus)
    stats: dict[str, dict[str, float]] = {}
    for facet, obs in by_facet.items():
        values = [float(o.value) for o in obs]
        if not values:
            continue
        mean = statistics.fmean(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        cv = abs(stdev / mean) if mean else 0.0
        stats[facet] = {"mean": mean, "stdev": stdev, "cv": cv, "n": float(len(values))}
    return stats


def corpus_promotion_verdict(corpus: dict[str, Any]) -> str:
    """Run the REAL synthesis path over the corpus's PRIMARY signal facets (preregistered in the
    manifest) and return ``SUPPORTED`` only if ALL of them promote, else ``OBSERVED``. Requiring
    every primary facet — not merely any facet — prevents a degenerate, all-zero facet (an absence
    of signal, e.g. no em-dashes) from being mistaken for stable supported evidence."""
    by_facet = _corpus_signal_observations(corpus)
    doc_sources = _document_sources(corpus)
    context = ContextScope.from_dict(corpus.get("context", {}))
    for facet in cm.PRIMARY_PROMOTION_FACETS:
        obs = by_facet.get(facet, [])
        if not obs:
            return FactState.OBSERVED.value
        result = synthesize_fact(
            subject_id=corpus["corpus_id"], facet=facet, scope=context,
            observations=obs, document_sources=doc_sources, calibration=DEFAULT_CALIBRATION,
        )
        if result.fact.state != FactState.SUPPORTED:
            return FactState.OBSERVED.value
    return FactState.SUPPORTED.value


def derive_function_word_reference(corpora: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Function-word rate (mean, stdev) over all stable OPERATOR documents (EXTERNAL excluded)."""
    per_facet: dict[str, list[float]] = {}
    for corpus in corpora:
        if corpus.get("subject_kind") != "OPERATOR" or corpus.get("label") != "stable":
            continue
        for doc in corpus["documents"]:
            rates = features.compute_function_word_rates(tokenize_words(doc["text"]))
            for facet, rate in rates.items():
                per_facet.setdefault(facet, []).append(rate)
    reference: dict[str, tuple[float, float]] = {}
    for facet, values in per_facet.items():
        mean = statistics.fmean(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        reference[facet] = (mean, stdev)
    return reference


def _normalized_separation(mean_a: float, mean_b: float) -> float:
    denom = abs(mean_a) + abs(mean_b)
    if denom == 0:
        return 0.0
    return abs(mean_a - mean_b) / denom


def derive_calibrated_bands(
    stable_stats: dict[str, dict[str, float]],
    noisy_stats: dict[str, dict[str, float]],
    rule: cm.BandCalibrationRule = cm.BAND_CALIBRATION_RULE,
    basis: str = "",
) -> tuple[dict[str, bands.BandScale], dict[str, dict[str, float]]]:
    """Return (calibrated_scales, evidence). A facet earns a CALIBRATED scale only if it clears the
    preregistered separation + stable-CV bars. Thresholds are set around the stable operator
    distribution (mean ± 0.5·stdev)."""
    calibrated: dict[str, bands.BandScale] = {}
    evidence: dict[str, dict[str, float]] = {}
    for facet in _BANDABLE_FACETS:
        s = stable_stats.get(facet)
        n = noisy_stats.get(facet)
        if not s:
            continue
        sep = _normalized_separation(s["mean"], n["mean"]) if n else 0.0
        stable_cv = s["cv"]
        qualifies = sep >= rule.min_normalized_separation and stable_cv <= rule.max_stable_cv
        evidence[facet] = {"separation": sep, "stable_cv": stable_cv, "qualifies": float(qualifies)}
        if not qualifies:
            continue
        mean, stdev = s["mean"], s["stdev"]
        high = round(mean + 0.5 * stdev, 6)
        medium = round(mean, 6)
        low = round(max(mean - 0.5 * stdev, 0.0), 6)
        thresholds = _dedupe_descending(((high, "high"), (medium, "medium"), (low, "low")))
        calibrated[facet] = bands.BandScale(
            facet=facet, provenance=bands.BandProvenance.CALIBRATED,
            thresholds=thresholds, basis=basis or "calibration_report.json",
        )
    return calibrated, evidence


def _dedupe_descending(items: tuple[tuple[float, str], ...]) -> tuple[tuple[float, str], ...]:
    """Keep a strictly-descending threshold ladder (drop any bound not lower than the prior one)."""
    out: list[tuple[float, str]] = []
    for bound, label in items:
        if not out or bound < out[-1][0]:
            out.append((bound, label))
    return tuple(out)


def measure_feedback_effect() -> dict[str, float]:
    """Measure whether direct feedback lowers the future correction rate, using the REAL synthesis
    precedence path (§13 M2.7). Deterministic synthetic scenarios only.

    Each scenario: an initial measurement establishes a fact at value v1; a later batch of
    observations drifts to v2 != v1.
      * pre-feedback: no prior operator correction. Synthesis silently adopts the drifted value,
        so the operator would have to issue a correction → counts as a needed correction.
      * post-feedback: the operator already corrected the fact to v1 (state=CORRECTED). Synthesis
        must NOT overwrite it (§4.2); the drift is reported but the fact stays v1 → no new
        correction needed.
    """
    scope = ContextScope(channel="slack")
    doc_sources = {"d1": "s1", "d2": "s2", "d3": "s3"}
    scenarios = [(10.0, 20.0), (0.30, 0.70), (5.0, 1.0)]
    pre_needed = 0
    post_needed = 0
    for v1, v2 in scenarios:
        obs_v1 = [_num_obs(f"d{i+1}", "avg_sentence_length", v1) for i in range(3)]
        obs_v2 = [_num_obs(f"d{i+1}", "avg_sentence_length", v2) for i in range(3)]

        # pre-feedback: adopt v1, then drift to v2 with no protection.
        fact_v1 = synthesize_fact(
            subject_id="s", facet="avg_sentence_length", scope=scope,
            observations=obs_v1, document_sources=doc_sources,
        ).fact
        drifted = synthesize_fact(
            subject_id="s", facet="avg_sentence_length", scope=scope,
            observations=obs_v2, document_sources=doc_sources, existing_fact=fact_v1,
        ).fact
        if abs(float(drifted.value) - v1) > 1e-9:
            pre_needed += 1  # value moved off operator intent → operator must correct

        # post-feedback: fact was corrected to v1; later drift must not overwrite it.
        corrected = ProfileFact(
            fact_id=new_id("fact"), subject_id="s", facet="avg_sentence_length", value=v1,
            scope=scope, state=FactState.CORRECTED, confidence=1.0,
        )
        result = synthesize_fact(
            subject_id="s", facet="avg_sentence_length", scope=scope,
            observations=obs_v2, document_sources=doc_sources, existing_fact=corrected,
        )
        if abs(float(result.fact.value) - v1) > 1e-9:
            post_needed += 1  # would only happen if the correction were overwritten (it must not)

    n = len(scenarios)
    return {
        "pre_feedback_correction_rate": pre_needed / n,
        "post_feedback_correction_rate": post_needed / n,
        "scenarios": float(n),
    }


def _num_obs(document_id: str, facet: str, value: float):
    from operator_voice.domain.models import SignalObservation

    return SignalObservation(
        observation_id=new_id("obs"), observation_key=f"{document_id}:{facet}:{value}",
        subject_id="s", document_id=document_id, segment_id="seg", facet=facet, value=value,
    )


def build_report(corpus_path: pathlib.Path | None = None) -> dict[str, Any]:
    data = load_corpora(corpus_path)
    corpora = data["corpora"]

    promotion: dict[str, dict[str, str]] = {"stable": {}, "noisy": {}}
    per_corpus_stats: dict[str, dict[str, dict[str, float]]] = {}
    external_docs = 0
    for corpus in corpora:
        per_corpus_stats[corpus["corpus_id"]] = corpus_signal_stats(corpus)
        if corpus.get("subject_kind") == "EXTERNAL":
            external_docs += len(corpus["documents"])
            continue  # EXTERNAL never contributes to operator promotion/reference (D17)
        verdict = corpus_promotion_verdict(corpus)
        bucket = "stable" if corpus.get("label") == "stable" else "noisy"
        promotion[bucket][corpus["corpus_id"]] = verdict

    reference = derive_function_word_reference(corpora)

    # Aggregate stable operator stats vs the noisy operator corpus for band separation.
    stable_stats = _aggregate_stats(
        [per_corpus_stats[c["corpus_id"]] for c in corpora
         if c.get("subject_kind") == "OPERATOR" and c.get("label") == "stable"]
    )
    noisy_stats = _aggregate_stats(
        [per_corpus_stats[c["corpus_id"]] for c in corpora
         if c.get("subject_kind") == "OPERATOR" and c.get("label") == "noisy"]
    )
    calibrated_scales, band_evidence = derive_calibrated_bands(
        stable_stats, noisy_stats, basis=f"{cm.CALIBRATION_MANIFEST_VERSION} corpora/v2",
    )

    feedback = measure_feedback_effect()

    report = {
        "manifest_version": cm.CALIBRATION_MANIFEST_VERSION,
        "manifest_digest": cm.CALIBRATION_MANIFEST_DIGEST,
        "corpus_manifest_version": data.get("corpus_manifest_version"),
        "promotion_thresholds": {
            "min_documents_for_supported": DEFAULT_CALIBRATION.min_documents_for_supported,
            "min_sources_for_supported": DEFAULT_CALIBRATION.min_sources_for_supported,
            "max_coefficient_of_variation": DEFAULT_CALIBRATION.max_coefficient_of_variation,
            "min_documents_for_observed": DEFAULT_CALIBRATION.min_documents_for_observed,
        },
        "promotion": promotion,
        "per_corpus_stats": per_corpus_stats,
        "function_word_reference": {k: list(v) for k, v in sorted(reference.items())},
        "calibrated_bands": {
            facet: {
                "provenance": scale.provenance.value,
                "thresholds": [list(t) for t in scale.thresholds],
                "basis": scale.basis,
            }
            for facet, scale in sorted(calibrated_scales.items())
        },
        "band_separation_evidence": band_evidence,
        "feedback_effect": feedback,
        "external_documents_contributing": 0,
        "external_documents_seen": external_docs,
    }
    return report


def _aggregate_stats(stats_list: list[dict[str, dict[str, float]]]) -> dict[str, dict[str, float]]:
    """Pool per-corpus facet stats by averaging means/stdevs/cvs (deterministic; corpora are equal
    size here). Sufficient for the separation check."""
    agg: dict[str, dict[str, list[float]]] = {}
    for stats in stats_list:
        for facet, s in stats.items():
            slot = agg.setdefault(facet, {"mean": [], "stdev": [], "cv": []})
            slot["mean"].append(s["mean"])
            slot["stdev"].append(s["stdev"])
            slot["cv"].append(s["cv"])
    out: dict[str, dict[str, float]] = {}
    for facet, slot in agg.items():
        out[facet] = {
            "mean": statistics.fmean(slot["mean"]),
            "stdev": statistics.fmean(slot["stdev"]),
            "cv": statistics.fmean(slot["cv"]),
        }
    return out


def write_report(report: dict[str, Any], report_path: pathlib.Path | None = None) -> pathlib.Path:
    report_path = report_path or default_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


def load_calibrated_artifacts(
    report_path: pathlib.Path | None = None,
) -> tuple[dict[str, tuple[float, float]], dict[str, bands.BandScale]]:
    """Runtime loader: parse a written report into (function_word_reference, calibrated_scales) so
    the application layer can pass them into the pure kernel. Returns empty artifacts when the
    report is absent — the honest heuristic/uncalibrated fallback (never a hidden default)."""
    report_path = report_path or default_report_path()
    if not report_path.exists():
        return {}, {}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    reference = {k: (float(v[0]), float(v[1])) for k, v in report.get("function_word_reference", {}).items()}
    scales: dict[str, bands.BandScale] = {}
    for facet, spec in report.get("calibrated_bands", {}).items():
        scales[facet] = bands.BandScale(
            facet=facet,
            provenance=bands.BandProvenance(spec["provenance"]),
            thresholds=tuple((float(b), str(lbl)) for b, lbl in spec["thresholds"]),
            basis=spec.get("basis", "calibration_report.json"),
        )
    return reference, scales


__all__ = [
    "default_corpus_path",
    "default_report_path",
    "load_corpora",
    "corpus_signal_stats",
    "corpus_promotion_verdict",
    "derive_function_word_reference",
    "derive_calibrated_bands",
    "measure_feedback_effect",
    "build_report",
    "write_report",
    "load_calibrated_artifacts",
]
