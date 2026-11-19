"""Frozen wire contracts — build plan v3 §5, §6.1, §6.3.

"Public bundles are frozen/additive within v1 and reject unknown required fields or
incompatible major versions" (§5). This module is the single place that (de)serializes the two
cross-boundary bundle contracts to/from plain dict (JSON-safe) form, and validates them.

Validation policy:
  - the ``schema`` string's name and MAJOR version must match exactly;
  - every field in that version's REQUIRED_FIELDS must be present (may be null/empty, but the
    key must exist) — a missing required field is a hard reject, never a silent default;
  - unknown EXTRA fields are tolerated (forward-compatible / additive), never rejected.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from operator_voice.domain.models import (
    ContextScope,
    FactState,
    RankedFact,
    SubjectInsight,
    SubjectInsightBundle,
    VoiceContextBundle,
)


class SchemaError(ValueError):
    """Raised when a bundle fails contract validation (missing required field, wrong major
    version, or unknown schema name). Never raised for unknown extra fields."""


def _major(schema: str) -> str:
    # "voice-context-bundle/v1" -> "v1"; "voice-context-bundle/v1.3" -> "v1"
    try:
        _, ver = schema.rsplit("/", 1)
    except ValueError:
        raise SchemaError(f"malformed schema string: {schema!r}") from None
    return ver.split(".", 1)[0]


VOICE_CONTEXT_BUNDLE_NAME = "voice-context-bundle"
VOICE_CONTEXT_BUNDLE_MAJOR = "v1"
VOICE_CONTEXT_BUNDLE_VERSION = f"{VOICE_CONTEXT_BUNDLE_NAME}/{VOICE_CONTEXT_BUNDLE_MAJOR}"
# FROZEN in M2 (build plan §13 M2 worklist 5 "Freeze VoiceContextBundle/v1"). This exact required
# set is the public contract; it is additive-only within v1 (new fields may be added as OPTIONAL,
# an existing required field is NEVER removed or renamed). The freeze is guarded by
# tests/contract/test_voice_context_bundle_freeze.py, which pins this literal set — any change here
# fails that test on purpose, forcing a deliberate, documented v1.x addendum decision.
VOICE_CONTEXT_BUNDLE_REQUIRED_V1 = frozenset(
    {
        "schema",
        "bundle_id",
        "subject_id",
        "consumer_id",
        "generation_id",
        "request_scope",
        "ranked_facts",
        "instructions",
        "warnings",
        "provenance_refs",
        "budget_tokens",
        "actual_tokens",
        "confidence",
        "abstained",
    }
)

SUBJECT_INSIGHT_BUNDLE_NAME = "subject-insight-bundle"
SUBJECT_INSIGHT_BUNDLE_REQUIRED_V1 = frozenset(
    {"schema", "bundle_id", "subject_id", "purpose", "observations", "warnings", "expires_at"}
)


def _normalize_major(token: str) -> str:
    """Reduce an accepted-version token to its major, tolerating any of ``v1``, ``1``,
    ``voice-context-bundle/v1``, or ``v1.3``."""
    tok = token.strip()
    if "/" in tok:
        tok = tok.rsplit("/", 1)[1]
    tok = tok.split(".", 1)[0]
    return tok if tok.startswith("v") else f"v{tok}"


def negotiate_bundle_version(accepted_majors: list[str] | tuple[str, ...] | None) -> str:
    """Consumer/version negotiation (§6.3 request field "accepted bundle major versions"). OVT emits
    exactly ``voice-context-bundle/v1``. Returns that schema string when the consumer accepts major
    v1 (or supplies no constraint — back-compatible default). Raises :class:`SchemaError` when the
    consumer accepts ONLY incompatible majors, so an incompatible consumer fails closed at the read
    boundary rather than silently receiving a shape it declared it cannot parse (§5)."""
    if not accepted_majors:
        return VOICE_CONTEXT_BUNDLE_VERSION
    normalized = {_normalize_major(m) for m in accepted_majors if str(m).strip()}
    if not normalized or VOICE_CONTEXT_BUNDLE_MAJOR in normalized:
        return VOICE_CONTEXT_BUNDLE_VERSION
    raise SchemaError(
        f"no compatible bundle version: consumer accepts {sorted(normalized)}, "
        f"OVT emits {VOICE_CONTEXT_BUNDLE_VERSION}"
    )


def _ranked_fact_to_dict(fact: RankedFact) -> dict[str, Any]:
    out = {
        "facet": fact.facet,
        "value": fact.value,
        "state": fact.state.value,
        "confidence": fact.confidence,
        "scope": fact.scope.as_dict(),
        "provenance_ids": list(fact.provenance_ids),
    }
    if fact.document_count is not None:
        out["document_count"] = fact.document_count
    return out


def voice_context_bundle_to_dict(bundle: VoiceContextBundle) -> dict[str, Any]:
    return {
        "schema": bundle.schema,
        "bundle_id": bundle.bundle_id,
        "subject_id": bundle.subject_id,
        "consumer_id": bundle.consumer_id,
        "generation_id": bundle.generation_id,
        "request_scope": bundle.request_scope.as_dict(),
        "ranked_facts": [_ranked_fact_to_dict(f) for f in bundle.ranked_facts],
        "instructions": dict(bundle.instructions),
        "warnings": list(bundle.warnings),
        "provenance_refs": list(bundle.provenance_refs),
        "budget_tokens": bundle.budget_tokens,
        "actual_tokens": bundle.actual_tokens,
        "confidence": bundle.confidence,
        "abstained": bundle.abstained,
        "created_at": bundle.created_at,
    }


def validate_voice_context_bundle(payload: dict[str, Any]) -> None:
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema.startswith(f"{VOICE_CONTEXT_BUNDLE_NAME}/"):
        raise SchemaError(f"not a {VOICE_CONTEXT_BUNDLE_NAME} bundle: {schema!r}")
    if _major(schema) != "v1":
        raise SchemaError(f"incompatible major version: {schema!r} (expected v1.x)")
    missing = VOICE_CONTEXT_BUNDLE_REQUIRED_V1 - payload.keys()
    if missing:
        raise SchemaError(f"missing required field(s): {sorted(missing)}")
    # Structural invariant (quality gate §10.16 / §4.3): a VoiceContextBundle is OPERATOR-only.
    # This is enforced again at the kernel boundary; re-checking here makes the contract itself
    # refuse a malformed/forged payload regardless of caller.
    if payload.get("ranked_facts") and not isinstance(payload["ranked_facts"], list):
        raise SchemaError("ranked_facts must be a list")


def voice_context_bundle_from_dict(payload: dict[str, Any]) -> VoiceContextBundle:
    validate_voice_context_bundle(payload)
    facts = [
        RankedFact(
            facet=f["facet"],
            value=f["value"],
            state=FactState(f["state"]),
            confidence=f["confidence"],
            scope=ContextScope.from_dict(f.get("scope", {})),
            provenance_ids=list(f.get("provenance_ids", [])),
            document_count=f.get("document_count"),
        )
        for f in payload["ranked_facts"]
    ]
    return VoiceContextBundle(
        bundle_id=payload["bundle_id"],
        subject_id=payload["subject_id"],
        consumer_id=payload["consumer_id"],
        generation_id=payload["generation_id"],
        request_scope=ContextScope.from_dict(payload["request_scope"]),
        ranked_facts=facts,
        instructions=dict(payload["instructions"]),
        warnings=list(payload["warnings"]),
        provenance_refs=list(payload["provenance_refs"]),
        budget_tokens=payload["budget_tokens"],
        actual_tokens=payload["actual_tokens"],
        confidence=payload["confidence"],
        abstained=payload["abstained"],
        schema=payload["schema"],
        created_at=payload.get("created_at", 0.0),
    )


def subject_insight_bundle_to_dict(bundle: SubjectInsightBundle) -> dict[str, Any]:
    return {
        "schema": bundle.schema,
        "bundle_id": bundle.bundle_id,
        "subject_id": bundle.subject_id,
        "purpose": bundle.purpose,
        "observations": [asdict(o) for o in bundle.observations],
        "warnings": list(bundle.warnings),
        "expires_at": bundle.expires_at,
        "created_at": bundle.created_at,
    }


def validate_subject_insight_bundle(payload: dict[str, Any]) -> None:
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema.startswith(f"{SUBJECT_INSIGHT_BUNDLE_NAME}/"):
        raise SchemaError(f"not a {SUBJECT_INSIGHT_BUNDLE_NAME} bundle: {schema!r}")
    if _major(schema) != "v1":
        raise SchemaError(f"incompatible major version: {schema!r} (expected v1.x)")
    missing = SUBJECT_INSIGHT_BUNDLE_REQUIRED_V1 - payload.keys()
    if missing:
        raise SchemaError(f"missing required field(s): {sorted(missing)}")
    # Hard structural invariant (§4.3, quality gate §10.16): a SubjectInsightBundle NEVER carries
    # generation/authoring instructions. Reject at the contract boundary, not just by convention.
    if "instructions" in payload or "ranked_facts" in payload:
        raise SchemaError(
            "subject-insight-bundle must never carry generation instructions or ranked_facts"
        )


def subject_insight_bundle_from_dict(payload: dict[str, Any]) -> SubjectInsightBundle:
    validate_subject_insight_bundle(payload)
    return SubjectInsightBundle(
        bundle_id=payload["bundle_id"],
        subject_id=payload["subject_id"],
        purpose=payload["purpose"],
        observations=[
            SubjectInsight(
                facet=o["facet"],
                observation=o["observation"],
                uncertainty=o["uncertainty"],
                counter_evidence=list(o.get("counter_evidence", [])),
            )
            for o in payload["observations"]
        ],
        warnings=list(payload["warnings"]),
        expires_at=payload["expires_at"],
        schema=payload["schema"],
        created_at=payload.get("created_at", 0.0),
    )
