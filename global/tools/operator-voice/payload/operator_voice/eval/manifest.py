"""The preregistered M1 evaluation manifest — build plan §12/§13 M1 worklist item 9.

This module is the ENTIRE content of "the exact mapping from each evidence measure into each of
the ten GA dimension scores," frozen at :data:`MANIFEST_VERSION` / :data:`MANIFEST_DIGEST` before
any of those measures has ever been observed. Nothing in this repository's git history may edit
:data:`DIMENSIONS`, an existing :class:`EvidenceMeasure`'s ``weight``/``dimensions``, or
:data:`MANIFEST_DIGEST` itself once a commit has landed that reports an observed value for any
measure this manifest references (D21: "changing weights after results is forbidden"). A genuine
correction to the formula requires a NEW manifest version with its own digest, landed in a commit
that touches no observed-value file, and the old version's prior observations are never silently
re-scored under the new formula.

Nothing here computes a live GA (`>=95x10`) score. `score_dimension` / `score_all` are pure
functions of caller-supplied :class:`EvidenceReport` values; they exist so a *future* milestone
(M5, `>=95x10` + independent review, per build plan D21/§13) has one unambiguous, already-reviewed
implementation to call — not so M1 can self-score. `evidence_is_complete=False` on a report
produces ``"insufficient_evidence"`` for every dimension that depends on the missing measure,
exactly like the plan's retrieval abstention discipline transplanted to scoring: a missing input
must never be silently treated as zero, missing-and-ignored, or backfilled with a guess.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

MANIFEST_VERSION = "eval-manifest/v1"

# The ten GA dimensions, in the exact order and wording the build plan requests (§13 M5 acceptance
# / §12): "efficacy, accuracy, precision, consistency, resilience, performance, privacy/safety,
# operator friction, integration cohesion, and overall build quality." `overall_build_quality` is
# a rollup of the other nine (see AGGREGATE_DIMENSION below), never an independently-measured
# tenth quantity — but it still carries its own >=95 bar per D21 ("a mean cannot mask a dimension
# below 95"), so a low aggregate is exactly as disqualifying as a low leaf dimension.
DIMENSIONS: tuple[str, ...] = (
    "efficacy",
    "accuracy",
    "precision",
    "consistency",
    "resilience",
    "performance",
    "privacy_safety",
    "operator_friction",
    "integration_cohesion",
    "overall_build_quality",
)
AGGREGATE_DIMENSION = "overall_build_quality"
LEAF_DIMENSIONS: tuple[str, ...] = tuple(d for d in DIMENSIONS if d != AGGREGATE_DIMENSION)


@dataclass(frozen=True, slots=True)
class EvidenceMeasure:
    """One named, independently-collectible evidence input. ``id`` is the caller-facing key in
    :class:`EvidenceReport.values`. ``weight_by_dimension`` maps a subset of :data:`LEAF_DIMENSIONS`
    to this measure's weight within that dimension's own weighted average (weights within one
    dimension across all its assigned measures sum to ``1.0`` — asserted by
    :func:`assert_manifest_well_formed`, never by convention alone). ``source`` documents WHERE the
    measure is collected from, so "preregistered" means something concrete and auditable rather
    than an unfalsifiable promise.
    """

    id: str
    description: str
    source: str
    weight_by_dimension: dict[str, float]


# Each measure is a [0, 100] normalized rate/score computed by operator_voice.eval.metrics from a
# concrete, named evidence source (a test module, a scan, a benchmark run) — never a subjective
# judgment call made at scoring time. Every measure that feeds a dimension is listed here; a
# dimension with zero measures listed is a manifest bug caught by
# assert_manifest_well_formed(), not a silent zero.
MEASURES: tuple[EvidenceMeasure, ...] = (
    EvidenceMeasure(
        id="authorship_isolation_rate",
        description=(
            "Fraction of role/quote/forward/adversarial authorship fixtures where assistant- and "
            "correctly-identified-third-party text contributed zero operator evidence, ambiguous "
            "content stayed inspectable quarantine, and unenrolled EXTERNAL-subject analysis refused."
        ),
        source="tests/unit/test_adapters.py, tests/integration/test_service.py (authorship/quarantine cases)",
        weight_by_dimension={"accuracy": 0.30, "precision": 0.60, "privacy_safety": 0.15},
    ),
    EvidenceMeasure(
        id="exactly_once_recovery_rate",
        description="Fraction of duplicate/interrupted-ingestion fixtures proving exactly-once visible effects and clean recovery.",
        source="tests/integration/test_service.py (duplicate/idempotent ingest cases), tests/integration/test_persistence.py (migration/transaction atomicity)",
        weight_by_dimension={"consistency": 0.25, "resilience": 0.25},
    ),
    EvidenceMeasure(
        id="local_only_zero_egress_rate",
        description="Fraction of fresh-LOCAL_ONLY end-to-end runs (ingest->bundle->feedback->rebuild) with zero Git/private-repo access and an honest no-online-backup report.",
        source="tests/integration/test_service.py, tests/integration/test_profile_pack.py (LOCAL_ONLY remote-verb no-op cases)",
        weight_by_dimension={"efficacy": 0.50, "privacy_safety": 0.20},
    ),
    EvidenceMeasure(
        id="distributor_convergence_rate",
        description="Fraction of home-first / vendor-fixture-first / GCB-embedded-snapshot install trials converging on an identical version+digest receipt, with same-digest no-op, distributor same-version-different-digest refusal (home checkout and --force upgrade), downgrade refusal, and interruption-preserves-prior-runtime all holding.",
        source="tests/integration/test_runtime_install.py, tests/e2e/test_install_sh.py, this session's direct GCB-shelf-embedded + full home-workstation bootstrap runs",
        weight_by_dimension={"consistency": 0.20, "resilience": 0.20, "integration_cohesion": 0.25},
    ),
    EvidenceMeasure(
        id="storage_encryption_scan_clean_rate",
        description="Fraction of scanned Git commits/objects, SQLite/WAL files, backups, and portable payload/receipt files containing zero plaintext operator content, keys, or personal bytes.",
        source="tests/integration/test_persistence.py (crypto round-trip, backup ciphertext scans), tests/integration/test_profile_pack.py (commit-content scans), tests/integration/test_runtime_install.py (payload denylist enforcement)",
        weight_by_dimension={"privacy_safety": 0.30},
    ),
    EvidenceMeasure(
        id="interface_registry_parity_rate",
        description="Fraction of domain.operations.OPERATIONS entries with matching CLI subcommand + MCP tool coverage, generated docs, and a passing colloquial-intent fixture; fraction of direct-service-call attempts that still enforce subject/source policy and consequence gating (i.e. no interface can bypass the one application-service boundary).",
        source="tests/integration/test_interfaces.py, tests/unit/test_docs_and_skill.py",
        weight_by_dimension={"precision": 0.40, "integration_cohesion": 0.30},
    ),
    EvidenceMeasure(
        id="retrieval_determinism_rate",
        description="Fraction of retrieval trials that are byte-identical for the same generation, correctly exclude an injected wrong context, and abstain below the quality floor rather than returning a misleadingly thin bundle.",
        source="tests/unit/test_kernel_pipeline.py (retrieval determinism/abstention cases)",
        weight_by_dimension={"accuracy": 0.35, "consistency": 0.30},
    ),
    EvidenceMeasure(
        id="correction_precedence_durability_rate",
        description="Fraction of direct-feedback/correction fixtures where the correction changes the next bundle, survives local rebuild, survives profile publication + clean-machine restore (Laurence's backend), and is never silently overwritten by later measurement.",
        source="tests/unit/test_kernel_pipeline.py (correction-precedence cases), tests/integration/test_service.py (rebuild + feedback precedence)",
        weight_by_dimension={"accuracy": 0.35, "consistency": 0.25},
    ),
    EvidenceMeasure(
        id="profile_backend_integrity_rate",
        description="For Laurence's configured ENCRYPTED_GIT backend: fraction of clone+recovered-key+rebuild trials reproducing the exact generation digest, with clean plaintext/key scans and safe refusal on a divergent remote head (no force-push, no silent merge).",
        source="tests/integration/test_profile_pack.py (divergent-writer / restore cases)",
        weight_by_dimension={"resilience": 0.20, "privacy_safety": 0.15},
    ),
    EvidenceMeasure(
        id="lifecycle_completeness_rate",
        description="Fraction of export/erasure(-granularity)/key-rotation/key-destruction/exact-rebuild/reanalysis-failure-without-source/off/cancel/migration-failure/doctor scenarios that pass end to end with one plain-language next step each.",
        source="tests/integration/test_persistence.py (erase/backup/retention/migration cases), tests/integration/test_service.py (off/cancel cases)",
        weight_by_dimension={"resilience": 0.15, "operator_friction": 0.50},
    ),
    EvidenceMeasure(
        id="benchmark_budget_adherence_rate",
        description="Fraction of the pinned M1 performance regression budgets (ingest/rebuild/search/context-retrieval p50+p95 latency, peak memory, DB growth, context tokens across synthetic small/medium/large corpora) met by the most recent benchmark run.",
        source="operator_voice.eval.benchmarks.run_benchmark_suite() against docs/generated/m1-benchmark-baseline.json",
        weight_by_dimension={"performance": 1.00, "efficacy": 0.30},
    ),
    EvidenceMeasure(
        id="security_review_clean_rate",
        description="1.0 minus (open P0/P1 security findings / total findings raised in the milestone's independent security review); 1.0 when zero findings were ever raised. Never self-assessed by the implementer.",
        source="Independent security-review subagent disposition, recorded in docs/m1-implementation-ledger.md",
        weight_by_dimension={"privacy_safety": 0.20, "resilience": 0.20},
    ),
    EvidenceMeasure(
        id="deterministic_help_coverage_rate",
        description=(
            "Fraction of domain.operations.OPERATIONS entries with a generated operation card, a "
            "worked example, a non-empty error taxonomy, and (where consequential) a plain-language "
            "challenge/consent description. An M1 PROXY for operator friction — no real operator "
            "telemetry exists yet; a later milestone with actual operator sessions should replace "
            "or supplement this measure rather than treat it as a permanent stand-in."
        ),
        source="operator_voice.docs.generate output vs. operator_voice.domain.operations.OPERATIONS",
        weight_by_dimension={"operator_friction": 0.50, "efficacy": 0.20},
    ),
    EvidenceMeasure(
        id="ecosystem_lifecycle_conformance_rate",
        description=(
            "Binary-per-check average over: global/tools/operator-voice GCB passes verify-skills.sh "
            "(manifest contract + zero-link + lock parity); WF1 registry carries scope=global with "
            "an explicit excluded/enrolled state (never silently absent); no bespoke vendoring, "
            "direct downstream-repo write, or parallel installer channel exists anywhere in the diff."
        ),
        source="the skills capability shelf's verify-skills.sh, the sync orchestrator's config/registry.yml, manual diff review",
        weight_by_dimension={"integration_cohesion": 0.45},
    ),
)

_MEASURES_BY_ID: dict[str, EvidenceMeasure] = {m.id: m for m in MEASURES}


def assert_manifest_well_formed() -> None:
    """Structural self-check, run at import time (below) and by tests. Frozen once this module's
    initial commit lands — see the module docstring's non-edit rule."""
    seen_ids: set[str] = set()
    for m in MEASURES:
        if m.id in seen_ids:
            raise AssertionError(f"duplicate EvidenceMeasure id: {m.id!r}")
        seen_ids.add(m.id)
        for dim in m.weight_by_dimension:
            if dim not in LEAF_DIMENSIONS:
                raise AssertionError(f"measure {m.id!r} references non-leaf/unknown dimension {dim!r}")
    totals: dict[str, float] = {d: 0.0 for d in LEAF_DIMENSIONS}
    for m in MEASURES:
        for dim, w in m.weight_by_dimension.items():
            totals[dim] += w
    for dim, total in totals.items():
        if total <= 0.0:
            raise AssertionError(f"leaf dimension {dim!r} has zero measures assigned — manifest bug, not a valid zero score")
        if abs(total - 1.0) > 1e-9:
            raise AssertionError(f"leaf dimension {dim!r} measure weights sum to {total!r}, not 1.0")


# `overall_build_quality`'s own weighted rollup of the nine leaf dimensions. Equal weight by
# design (D21 forbids inventing a per-dimension importance ordering after the fact); a future
# manifest version may justify unequal weights, but only in a NEW frozen version, never a
# retroactive edit to this one.
AGGREGATE_WEIGHTS: dict[str, float] = {d: 1.0 / len(LEAF_DIMENSIONS) for d in LEAF_DIMENSIONS}


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Caller-supplied, already-collected evidence. ``values`` maps an :data:`EvidenceMeasure.id`
    to its observed [0, 100] rate; a measure absent from ``values`` is treated as missing evidence
    (triggers abstention for every dimension that depends on it), never as zero."""

    values: dict[str, float] = field(default_factory=dict)

    def get(self, measure_id: str) -> Optional[float]:
        return self.values.get(measure_id)


ABSTAIN = "insufficient_evidence"


def score_dimension(dimension: str, report: EvidenceReport) -> "float | str":
    """Pure function: (dimension, report) -> a [0, 100] float, or the literal string
    :data:`ABSTAIN` if any measure with nonzero weight for this dimension is missing from
    ``report``. Raises :class:`ValueError` for an unknown dimension name (a caller bug, not an
    evidence gap)."""
    if dimension == AGGREGATE_DIMENSION:
        leaf_scores: dict[str, float] = {}
        for dim in LEAF_DIMENSIONS:
            leaf = score_dimension(dim, report)
            if leaf == ABSTAIN:
                return ABSTAIN
            leaf_scores[dim] = leaf  # type: ignore[assignment]
        return sum(leaf_scores[d] * AGGREGATE_WEIGHTS[d] for d in LEAF_DIMENSIONS)
    if dimension not in LEAF_DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}; must be one of {DIMENSIONS!r}")
    total = 0.0
    for m in MEASURES:
        w = m.weight_by_dimension.get(dimension)
        if w is None:
            continue
        v = report.get(m.id)
        if v is None:
            return ABSTAIN
        total += v * w
    return total


def score_all(report: EvidenceReport) -> dict[str, "float | str"]:
    """Score every dimension in :data:`DIMENSIONS` order. Never called by M1 itself with real
    values — see module docstring — but exercised by tests against synthetic reports so the
    formula's arithmetic is proven correct before it is ever asked to matter."""
    return {dim: score_dimension(dim, report) for dim in DIMENSIONS}


def _canonical_manifest_json() -> str:
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "dimensions": DIMENSIONS,
        "aggregate_dimension": AGGREGATE_DIMENSION,
        "aggregate_weights": AGGREGATE_WEIGHTS,
        "measures": [
            {"id": m.id, "weight_by_dimension": m.weight_by_dimension}
            for m in MEASURES
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_manifest_digest() -> str:
    """SHA-256 over the canonical (formula + weights only, no prose) JSON projection of this
    manifest. A change to any weight or measure->dimension mapping changes this digest — the
    mechanical tripwire behind the "no edits after results are observed" rule: any PR that both
    changes this digest AND touches a file recording an observed value is a process violation,
    detectable by diff inspection even without a bespoke CI check."""
    return hashlib.sha256(_canonical_manifest_json().encode("utf-8")).hexdigest()


assert_manifest_well_formed()
MANIFEST_DIGEST = compute_manifest_digest()
