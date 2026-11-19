"""``OperatorVoiceService`` — build plan v3 §6: "One application service is the sole business-
logic/mutation boundary; CLI/MCP/skill are thin callers that never touch persistence directly."

Every public method's name is exactly an :class:`~operator_voice.domain.operations.Operation`'s
``handler_name`` (dotted registry key with ``.`` replaced by ``_``), and every method's keyword
arguments are exactly that operation's declared :class:`~operator_voice.domain.operations.ArgSpec`
names — this is what lets a single operation registry generate the CLI, MCP tool schema, and
docs without a second hand-maintained mapping (§6.1).

Consequential operations (posture ``CONSEQUENTIAL``) never mutate on the first call: absent a
matching, valid ``challenge_literal``, the method computes the live consequence, issues (or
reuses) a one-use challenge, and returns a ``confirmation_required`` response instead of touching
persistence. The kernel enforces this (:mod:`operator_voice.kernel.consequences`); this class
cannot be called in a way that bypasses it (§6: "Skill wording or approval UI cannot bypass it").
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

import operator_voice

from operator_voice.adapters.base import ADAPTER_VERSION
from operator_voice.adapters.registry import get_scanner
from operator_voice.application.cancellation import OperationCancelled, checkpoint, is_off, set_off, set_on
from operator_voice.application.gateway import (
    EXTERNAL_DATA_CLASS,
    GatewayCallRequest,
    ModelGateway,
    gateway_from_config,
)
from operator_voice.application.transactions import OperationRefused, staged_operation
from operator_voice.domain.models import (
    AdapterType,
    RETIRED_ADAPTER_TYPES,
    AuthorshipState,
    BackendMode,
    ContextScope,
    CurationRun,
    CurationRunStatus,
    CurationTrigger,
    ExportManifest,
    FactState,
    FeedbackAction,
    FeedbackEvent,
    GatewayConfig,
    ModelCallRecord,
    ProfileBackendConfig,
    ProfileFact,
    ProfileGeneration,
    ProfileSyncState,
    ReviewItem,
    ReviewReason,
    ReviewStatus,
    SourceCurationState,
    SourceDocument,
    SourceRegistration,
    SubjectAlias,
    SubjectInsight,
    SubjectInsightBundle,
    SubjectKind,
    SubjectRegistration,
    SyncStatus,
    ValidationOutcome,
    new_id,
    now_ts,
)
from operator_voice.domain.operations import Group, Posture, get_operation, public_operations
from operator_voice.kernel import authorship, external_analysis, feedback as feedback_kernel, normalize, reconcile, signals, synthesis, taxonomy, validation
from operator_voice.kernel.calibration import DEFAULT_CALIBRATION
from operator_voice.kernel.consequences import compute_consequence, issue_challenge, verify_challenge
from operator_voice.kernel.features import FEATURE_REGISTRY_VERSION, features_to_observations
from operator_voice.kernel.reconcile import FactView
from operator_voice.kernel.retrieval import BundleRequest, build_context_bundle
from operator_voice.kernel import retrieval
from operator_voice.kernel.synthesis import SynthesisResult, synthesize_fact
from operator_voice.persistence import audit, backup, erase, migrations, portability, profile_pack, retention, store
from operator_voice.persistence.crypto import CryptoContext
from operator_voice.persistence.sqlite import transaction
from operator_voice.runtime.paths import RuntimePaths

SERVICE_VERSION = "service/v1"
# Completed daily fetch freshness, shared by all channels. Partial imports do not reset it.
# Unenrolled legacy/manual capture retains its import-time status compatibility.
_CHANNEL_STALE_AFTER_HOURS = 48.0
GENERATION_DOC_SCOPE = ContextScope()  # M1's single (general) scope; retained for legacy generation records
# M2 emits two additive extractor families (M1 stylometric features + M2 Tier-2 signals); the
# generation's provenance string pins both so a profile pack is reproducible from its version bundle.
_EXTRACTION_VERSION = f"{FEATURE_REGISTRY_VERSION}+{signals.SIGNALS_VERSION}"


class ServiceError(RuntimeError):
    pass


def backend_health_copy(cfg: ProfileBackendConfig) -> str:
    if cfg.mode == BackendMode.ENCRYPTED_GIT:
        return "This profile is on this computer; an encrypted copy syncs to your private backup repo"
    return cfg.health


_CONSUMER_ID_HINT = "pass your agent/tool name as --consumer-id <your-agent/tool-name>"
_PAUSED_OPERATOR_GUIDANCE = (
    "run 'operator-voice subject-list' and pass the paused subj_* explicitly with --subject-id; "
    "setup does not reactivate an already-registered paused operator subject"
)


def _unknown_subject_error(
    subject_id: str, *, needs_consumer_id: bool = False,
) -> ServiceError:
    detail = (
        f"unknown subject_id {subject_id!r}; --subject-id is an opaque subj_* identifier, "
        "never a name, handle, or email. Run 'operator-voice subject-list' to resolve it."
    )
    if needs_consumer_id:
        detail += f" For context-get, consumer_id is required: {_CONSUMER_ID_HINT}."
    return ServiceError(detail)


class ConfirmationRequired(RuntimeError):
    def __init__(self, operation: str, literal_prompt: str, consequence_summary: str):
        super().__init__(consequence_summary)
        self.operation = operation
        self.literal_prompt = literal_prompt
        self.consequence_summary = consequence_summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "confirmation_required",
            "operation": self.operation,
            "consequence": self.consequence_summary,
            "instructions": f"Re-run with challenge_literal={self.literal_prompt!r} to confirm.",
        }


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Portable-profile (de)serialization (§13 M4 worklist 4). Plain JSON-safe dicts only; the
# sensitive sealing/opening is done by ``persistence.portability``. Kept as free functions so the
# portability round-trip is unit-testable without a service/DB.
# --------------------------------------------------------------------------------------


def _subject_to_portable(s: SubjectRegistration) -> dict[str, Any]:
    return {
        "subject_id": s.subject_id, "kind": s.kind.value, "display_label": s.display_label,
        "approved_purposes": list(s.approved_purposes), "consent_basis": s.consent_basis,
        "generation_permission": s.generation_permission, "retention_policy": s.retention_policy,
        "active": s.active, "created_at": s.created_at, "reviewed_at": s.reviewed_at,
    }


def _subject_from_portable(d: dict[str, Any]) -> SubjectRegistration:
    return SubjectRegistration(
        subject_id=d["subject_id"], kind=SubjectKind(d["kind"]), display_label=d["display_label"],
        approved_purposes=list(d.get("approved_purposes", [])), consent_basis=d.get("consent_basis", "operator-attested"),
        # An EXTERNAL subject can never gain generation permission on import, regardless of the archive.
        generation_permission=bool(d.get("generation_permission", True)) and SubjectKind(d["kind"]) == SubjectKind.OPERATOR,
        retention_policy=d.get("retention_policy", "default"), active=bool(d.get("active", True)),
        created_at=float(d.get("created_at", now_ts())), reviewed_at=d.get("reviewed_at"),
    )


def _fact_to_portable(f: ProfileFact) -> dict[str, Any]:
    return {
        "subject_id": f.subject_id, "facet": f.facet, "value": f.value, "scope": f.scope.as_dict(),
        "state": f.state.value, "confidence": f.confidence,
        "confidence_interval": list(f.confidence_interval) if f.confidence_interval else None,
        "document_count": f.document_count, "source_count": f.source_count,
        "synthesis_version": f.synthesis_version, "valid_from": f.valid_from,
    }


def _feedback_to_portable(e: FeedbackEvent) -> dict[str, Any]:
    return {
        "feedback_id": e.feedback_id, "subject_id": e.subject_id, "utterance_digest": e.utterance_digest,
        "action": e.action.value, "reason": e.reason, "target_fact_id": e.target_fact_id,
        "target_facet": e.target_facet, "prior_value": e.prior_value, "new_value": e.new_value,
        "actor": e.actor, "resulting_generation_id": e.resulting_generation_id, "created_at": e.created_at,
    }


def _feedback_from_portable(d: dict[str, Any]) -> FeedbackEvent:
    return FeedbackEvent(
        feedback_id=d["feedback_id"], subject_id=d["subject_id"], utterance_digest=d.get("utterance_digest", ""),
        action=FeedbackAction(d["action"]), reason=d.get("reason", ""), target_fact_id=d.get("target_fact_id"),
        target_facet=d.get("target_facet"), prior_value=d.get("prior_value"), new_value=d.get("new_value"),
        actor=d.get("actor", "operator"), resulting_generation_id=d.get("resulting_generation_id"),
        created_at=float(d.get("created_at", now_ts())),
    )


def _alias_to_portable(a: SubjectAlias) -> dict[str, Any]:
    return {
        "alias_id": a.alias_id, "subject_id": a.subject_id, "source_type": a.source_type,
        "source_native_id": a.source_native_id, "confidence": a.confidence,
        "verification_state": a.verification_state, "valid_from": a.valid_from,
        "valid_to": a.valid_to, "collision_review": a.collision_review,
    }


def _alias_from_portable(d: dict[str, Any]) -> SubjectAlias:
    return SubjectAlias(
        alias_id=d["alias_id"], subject_id=d["subject_id"], source_type=d["source_type"],
        source_native_id=d["source_native_id"], confidence=float(d.get("confidence", 1.0)),
        verification_state=d.get("verification_state", "operator_attested"),
        valid_from=float(d.get("valid_from", now_ts())), valid_to=d.get("valid_to"),
        collision_review=d.get("collision_review"),
    )


def _generation_to_portable(g: ProfileGeneration) -> dict[str, Any]:
    return {
        "generation_id": g.generation_id, "subject_id": g.subject_id, "schema_version": g.schema_version,
        "normalization_version": g.normalization_version, "extraction_version": g.extraction_version,
        "synthesis_version": g.synthesis_version, "taxonomy_version": g.taxonomy_version,
        "policy_version": g.policy_version, "tokenizer_version": g.tokenizer_version,
        "feature_registry_version": g.feature_registry_version, "content_digest": g.content_digest,
        "creation_reason": g.creation_reason, "parent_generation_id": g.parent_generation_id,
        "diff_summary": g.diff_summary, "created_at": g.created_at,
    }


def _generation_from_portable(d: dict[str, Any]) -> ProfileGeneration:
    return ProfileGeneration(
        generation_id=d["generation_id"], subject_id=d["subject_id"], schema_version=d["schema_version"],
        normalization_version=d["normalization_version"], extraction_version=d["extraction_version"],
        synthesis_version=d["synthesis_version"], taxonomy_version=d["taxonomy_version"],
        policy_version=d["policy_version"], tokenizer_version=d["tokenizer_version"],
        feature_registry_version=d["feature_registry_version"], content_digest=d["content_digest"],
        creation_reason=d.get("creation_reason", "imported"), parent_generation_id=d.get("parent_generation_id"),
        diff_summary=dict(d.get("diff_summary", {})), created_at=float(d.get("created_at", now_ts())),
    )


def _canonical_channel(raw: str) -> str:
    """Map adapter-declared channel labels to the closed retrieval vocabulary."""
    channel = taxonomy.disambiguate("channel", raw)
    if channel not in taxonomy.CANONICAL["channel"]:
        return taxonomy.GENERAL_VALUES["channel"]
    return channel


def _canonical_output_type(raw: str) -> str:
    """Map an adapter-declared output_type label to the closed retrieval vocabulary — the exact
    mirror of :func:`_canonical_channel`, so an adapter that tags a candidate's output form (e.g. a
    Google Doc as ``doc``) has it survive into the persisted ``ContextScope`` instead of collapsing
    to the ``text`` default. An unrecognized value falls back to the general ``text`` bucket."""
    output_type = taxonomy.disambiguate("output_type", raw)
    if output_type not in taxonomy.CANONICAL["output_type"]:
        return taxonomy.GENERAL_VALUES["output_type"]
    return output_type


class OperatorVoiceService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        crypto: CryptoContext,
        profile_pack_crypto: Optional[CryptoContext] = None,
        paths: Optional[RuntimePaths] = None,
        gateway: Optional[ModelGateway] = None,
        providers: Optional[dict] = None,
    ):
        self.conn = conn
        self.crypto = crypto
        self.profile_pack_crypto = profile_pack_crypto
        self.paths = paths
        # §D7 + §13 M2 worklist 4: injected, disabled-by-default model gateway, built from persisted
        # operator policy (both egress switches default OFF). The deterministic ingest/synthesis/
        # retrieval paths never call self.gateway; only the explicitly opt-in semantic-review path
        # (draft.validate with semantic=True) may, and only after the gateway's fail-closed policy
        # allows it. `providers` is a test/operator injection seam (OVT bundles only a no-network
        # local provider); the gateway is rebuilt whenever gateway.configure changes policy.
        self._injected_gateway = gateway
        self._providers = providers
        self.gateway = gateway if gateway is not None else self._build_gateway()
        # Calibrated artifacts (function-word reference + calibrated band scales) are lazily loaded
        # from eval/calibration_report.json; absent report → empty artifacts (honest heuristic
        # fallback). Cached per service instance.
        self._calibration_artifacts: Optional[tuple[dict, dict]] = None

    def _calibration_reference(self) -> dict:
        if self._calibration_artifacts is None:
            from operator_voice.eval.calibrate import load_calibrated_artifacts

            try:
                self._calibration_artifacts = load_calibrated_artifacts()
            except Exception:
                self._calibration_artifacts = ({}, {})
        return self._calibration_artifacts[0]

    def _build_gateway(self) -> ModelGateway:
        """Construct the gateway from persisted operator policy, with a LIVE cancellation hook so a
        subsequently-flipped off switch closes egress mid-session."""
        cfg = store.get_gateway_config(self.conn)
        return gateway_from_config(cfg, providers=self._providers, is_off=lambda: is_off(self.conn))

    def _refresh_gateway(self) -> None:
        if self._injected_gateway is None:
            self.gateway = self._build_gateway()

    def _gateway_attempt(self, request: GatewayCallRequest) -> tuple[Any, Any]:
        """Run one gateway attempt and persist a metadata-only ModelCallRecord (zero payload
        retention — the signal is never written). Returns (result, decision)."""
        result, decision = self.gateway.attempt(request)
        store.insert_model_call_record(
            self.conn,
            ModelCallRecord(
                call_id=new_id("call"), provider=request.provider, model=request.model,
                data_class=request.data_class, purpose=request.purpose, outcome=result.outcome,
                duration_ms=int(result.metadata.get("duration_ms", 0)),
                cancelled=bool(result.metadata.get("cancelled", False)),
            ),
        )
        return result, decision

    # ---------------------------------------------------------------------------------
    # Multi-context synthesis + review-queue persistence (§13 M2 worklist 3)
    # ---------------------------------------------------------------------------------

    def _synthesize_and_review(
        self, conn: sqlite3.Connection, subject_id: str, facets: set[str], *, protect_only_corrected: bool
    ) -> tuple[list[dict[str, Any]], int]:
        """Synthesize one fact per (facet, context scope) group and persist any deterministic
        review items. Grouping by the observation's own normalized scope is what makes voice
        multi-context: Slack and email evidence become distinct facts, never blended (bleed is a
        retrieval-time concern handled in kernel.retrieval)."""
        contradictions: list[dict[str, Any]] = []
        reviews_created = 0
        retired_ids = {s.source_id for s in store.list_sources(conn, self.crypto, subject_id)
                       if s.adapter_type in RETIRED_ADAPTER_TYPES}
        repeated = store.repeated_document_ids(conn, subject_id)
        for facet in sorted(facets):
            observations = store.get_observations_for_facet(conn, self.crypto, subject_id, facet)
            source_map = store.document_source_map(conn, [o.document_id for o in observations])
            observations = [o for o in observations if source_map.get(o.document_id) not in retired_ids
                            and o.document_id not in repeated]
            groups: dict[str, tuple[ContextScope, list]] = {}
            for o in observations:
                nscope = taxonomy.normalize_scope(o.context)
                groups.setdefault(nscope.key(), (nscope, []))[1].append(o)
            for scope_key, (scope, group_obs) in groups.items():
                existing = store.get_fact_by_facet_scope(conn, self.crypto, subject_id, facet, scope_key)
                existing_arg = existing
                if (
                    protect_only_corrected
                    and existing is not None
                    and existing.state not in (FactState.CORRECTED, FactState.CONFIRMED)
                ):
                    existing_arg = None
                doc_sources = store.document_source_map(conn, list({o.document_id for o in group_obs}))
                rs = synthesize_fact(
                    subject_id=subject_id, facet=facet, scope=scope, observations=group_obs,
                    document_sources=doc_sources, existing_fact=existing_arg, calibration=DEFAULT_CALIBRATION,
                )
                if existing is not None and existing.fact_id == rs.fact.fact_id:
                    # Re-observing an unchanged fact does not restart its validity interval.
                    rs.fact.valid_from = existing.valid_from
                if existing is not None and existing.fact_id != rs.fact.fact_id:
                    store.supersede_fact(conn, existing.fact_id, rs.fact.fact_id)
                elif rs.superseded_fact_id:
                    store.supersede_fact(conn, rs.superseded_fact_id, rs.fact.fact_id)
                store.upsert_fact(conn, self.crypto, rs.fact)
                store.supersede_inferred_facts_for_scope(conn, rs.fact)
                reviews_created += self._persist_review_items(conn, subject_id, facet, scope, rs)
                if rs.contradiction:
                    contradictions.append(
                        {"facet": facet, "scope": scope.key(), "detail": rs.contradiction_detail}
                    )
        self._retire_unrepresented_facts(conn, subject_id)
        return contradictions, reviews_created

    def _persist_review_items(
        self, conn: sqlite3.Connection, subject_id: str, facet: str, scope: ContextScope, rs: SynthesisResult
    ) -> int:
        reasons: list[ReviewReason] = list(rs.review_reasons)
        if rs.contradiction:
            reasons.append(ReviewReason.CONTRADICTION)
        created = 0
        for reason in reasons:
            if store.has_open_review(conn, subject_id, facet, scope.key(), reason.value):
                continue  # de-dup: one open item per (subject, facet, scope, reason)
            detail = self._review_detail(reason, facet, scope, rs)
            store.insert_review_item(
                conn, self.crypto,
                ReviewItem(
                    review_id=new_id("rev"), subject_id=subject_id, reason=reason, detail=detail,
                    facet=facet, scope=scope, related_fact_id=rs.fact.fact_id,
                    related_ids=list(rs.fact.provenance_ids[:10]),
                ),
            )
            created += 1
        return created

    @staticmethod
    def _review_detail(reason: ReviewReason, facet: str, scope: ContextScope, rs: SynthesisResult) -> str:
        if reason == ReviewReason.CONTRADICTION:
            return f"New evidence for '{facet}' ({scope.key()}) contradicts your saved value: {rs.contradiction_detail}"
        if reason == ReviewReason.DRIFT:
            return f"Your '{facet}' voice in {scope.key()} has shifted materially; the previous reading was retired for review."
        if reason == ReviewReason.LOW_SOURCE_DIVERSITY:
            return f"'{facet}' ({scope.key()}) is supported by only one source, so its confidence is capped until a second source agrees."
        if reason == ReviewReason.LOW_CONFIDENCE:
            return f"'{facet}' ({scope.key()}) is below the trust floor and kept for inspection only."
        return f"'{facet}' ({scope.key()}) needs review."

    # ---------------------------------------------------------------------------------
    # Consequential-operation gate (§6)
    # ---------------------------------------------------------------------------------

    def _require_confirmation_or_raise(
        self, operation_name: str, targets: list[str], challenge_literal: Optional[str], generation_id: Optional[str] = None
    ) -> None:
        op = get_operation(operation_name)
        if op.posture != Posture.CONSEQUENTIAL:
            return
        existing = store.find_pending_challenge(self.conn, operation_name, targets)
        if challenge_literal is not None and existing is not None:
            ok, reason = verify_challenge(
                existing, operation_name=operation_name, targets=targets, provided_literal=challenge_literal
            )
            if ok:
                store.mark_challenge_used(self.conn, existing.challenge_id)
                return
            raise ServiceError(f"confirmation rejected: {reason}")
        challenge = existing or issue_challenge(op, targets, generation_id)
        if existing is None:
            store.insert_challenge(self.conn, challenge)
        consequence = compute_consequence(op)
        raise ConfirmationRequired(operation_name, challenge.literal, consequence.summary)

    # ---------------------------------------------------------------------------------
    # Lifecycle (CLI-only, §6/D13)
    # ---------------------------------------------------------------------------------

    def setup(self, *, display_label: str = "operator") -> dict[str, Any]:
        from operator_voice.runtime import local_jobs_enroll

        existing = store.list_subjects(self.conn)
        operator = next((s for s in existing if s.kind == SubjectKind.OPERATOR), None)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="setup", actor="operator", allow_while_off=True) as conn:
            if operator is None:
                operator = SubjectRegistration.new_operator(display_label)
                store.insert_subject(conn, operator)
            store.ensure_active_key_generation(conn, self.crypto, store.CONTENT_KEY_PURPOSE)
            if store.get_backend_config(conn).mode is None:
                store.set_backend_config(conn, ProfileBackendConfig())
        passive_curation = local_jobs_enroll.ensure_curation_schedule()
        slack_source = self._ensure_slack_source(operator.subject_id)
        drive_source = self._ensure_drive_source(operator.subject_id)
        gmail_source = self._ensure_gmail_source(operator.subject_id)
        return {
            "status": "ready",
            "subject_id": operator.subject_id,
            "backend": "LOCAL_ONLY",
            "passive_curation": passive_curation,
            "slack_source": slack_source,
            "drive_source": drive_source,
            "gmail_source": gmail_source,
        }

    def _ensure_slack_source(self, subject_id: str) -> dict[str, Any]:
        """Best-effort, idempotent ``slack_export`` source registration (§ OVT Slack Adapter 1c).
        Runs AFTER ``setup()``'s own transaction commits — like ``local_jobs_enroll.
        ensure_curation_schedule()``, it never nests a second ``staged_operation`` inside
        ``setup()``'s — and never raises, so a caller with no ``paths`` (e.g. a minimal test
        double) still completes setup. This is the default-install replacement for ad hoc manual
        harvesting: a fresh install registers the source for free; nothing from the old untracked
        ``local-sources/slack-voice-drops`` prototype needs to be ported by hand."""
        from operator_voice.domain.models import AdapterType

        if self.paths is None:
            return {"status": "skipped", "reason": "no_runtime_paths"}
        self.paths.ensure()
        canonical_root = str(self.paths.slack_export_dir)
        existing = store.list_sources(self.conn, self.crypto, subject_id)
        already = next(
            (s for s in existing if s.adapter_type == AdapterType.SLACK_EXPORT and s.canonical_root == canonical_root),
            None,
        )
        if already is not None:
            return {"status": "already_registered", "source_id": already.source_id, "active": already.active}
        try:
            added = self.source_add(subject_id=subject_id, adapter_type="slack_export", canonical_root=canonical_root)
        except (ServiceError, OperationRefused) as exc:
            return {"status": "failed", "detail": str(exc)}
        return {"status": "added", "source_id": added["source_id"], "active": added["active"]}

    def _ensure_drive_source(self, subject_id: str) -> dict[str, Any]:
        """Best-effort, idempotent ``drive_export`` source registration (§ docs/drive-adapter.md),
        the exact ``_ensure_slack_source`` pattern: runs AFTER ``setup()``'s own transaction commits
        (never nests a second ``staged_operation``) and never raises, so a caller with no ``paths``
        (e.g. a minimal test double) still completes setup. A fresh install registers the owner-only
        Drive source for free — the operator only has to ask an agent to refresh Drive voice."""
        from operator_voice.domain.models import AdapterType

        if self.paths is None:
            return {"status": "skipped", "reason": "no_runtime_paths"}
        self.paths.ensure()
        canonical_root = str(self.paths.drive_export_dir)
        existing = store.list_sources(self.conn, self.crypto, subject_id)
        already = next(
            (s for s in existing if s.adapter_type == AdapterType.DRIVE_EXPORT and s.canonical_root == canonical_root),
            None,
        )
        if already is not None:
            return {"status": "already_registered", "source_id": already.source_id, "active": already.active}
        try:
            added = self.source_add(subject_id=subject_id, adapter_type="drive_export", canonical_root=canonical_root)
        except (ServiceError, OperationRefused) as exc:
            return {"status": "failed", "detail": str(exc)}
        return {"status": "added", "source_id": added["source_id"], "active": added["active"]}

    def _ensure_gmail_source(self, subject_id: str) -> dict[str, Any]:
        """Best-effort, idempotent ``gmail_export`` source registration (§ docs/gmail-adapter.md),
        the exact ``_ensure_slack_source`` pattern: runs AFTER ``setup()``'s own transaction commits
        and never raises."""
        from operator_voice.domain.models import AdapterType

        if self.paths is None:
            return {"status": "skipped", "reason": "no_runtime_paths"}
        self.paths.ensure()
        canonical_root = str(self.paths.gmail_export_dir)
        existing = store.list_sources(self.conn, self.crypto, subject_id)
        already = next(
            (s for s in existing if s.adapter_type == AdapterType.GMAIL_EXPORT and s.canonical_root == canonical_root),
            None,
        )
        if already is not None:
            return {"status": "already_registered", "source_id": already.source_id, "active": already.active}
        try:
            added = self.source_add(subject_id=subject_id, adapter_type="gmail_export", canonical_root=canonical_root)
        except (ServiceError, OperationRefused) as exc:
            return {"status": "failed", "detail": str(exc)}
        return {"status": "added", "source_id": added["source_id"], "active": added["active"]}

    def repair(self) -> dict[str, Any]:
        from operator_voice.runtime import local_jobs_enroll

        compatible, detail = migrations.check_compatible(self.conn)
        if not compatible and "uninitialized" in detail:
            migrations.migrate(self.conn)
            result: dict[str, Any] = {"status": "repaired", "detail": "schema initialized"}
        else:
            result = {"status": "ok" if compatible else "needs_attention", "detail": detail}
        result["passive_curation"] = local_jobs_enroll.ensure_curation_schedule()
        return result

    def uninstall(self, *, challenge_literal: Optional[str] = None) -> dict[str, Any]:
        try:
            self._require_confirmation_or_raise("uninstall", ["runtime"], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        return {"status": "runtime_marked_for_removal", "note": "profile data, config, and keys are untouched"}

    def profile_remote_bind(self, *, remote_url: str, challenge_literal: Optional[str] = None) -> dict[str, Any]:
        try:
            self._require_confirmation_or_raise("profile.remote_bind", [remote_url], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="profile.remote_bind", actor="operator") as conn:
            store.ensure_active_key_generation(conn, self.profile_pack_crypto, store.PROFILE_PACK_KEY_PURPOSE)
            cfg = replace(store.get_backend_config(conn), mode=BackendMode.ENCRYPTED_GIT, active=True, remote_reference_token=remote_url)
            store.set_backend_config(conn, cfg)
            store.set_sync_state(conn, ProfileSyncState(publish_status=SyncStatus.PENDING_PUBLICATION))
        return {"status": "bound", "mode": "ENCRYPTED_GIT", "next_step": "profile.publish"}

    def profile_remote_remove(self) -> dict[str, Any]:
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="profile.remote_remove", actor="operator") as conn:
            cfg = replace(store.get_backend_config(conn), mode=BackendMode.LOCAL_ONLY, active=False, remote_reference_token=None)
            store.set_backend_config(conn, cfg)
        return {"status": "unbound", "mode": "LOCAL_ONLY", "note": "local generations are kept"}

    def key_recover(self, *, recovery_material: str) -> dict[str, Any]:
        # M1's automated coverage is the disposable-Keychain round trip in
        # tests/integration/test_persistence.py; a real clean-machine recovery for the operator's
        # own recovery destination is operator-only (cannot be exercised by an agent).
        if not recovery_material or len(recovery_material.strip()) < 8:
            raise ServiceError("recovery_material does not look like a usable recovery secret")
        return {"status": "not_yet_applicable", "detail": "no destroyed key generation pending recovery on this install"}

    def key_rotate(self, *, purpose: str = "content", challenge_literal: Optional[str] = None) -> dict[str, Any]:
        if purpose not in (store.CONTENT_KEY_PURPOSE, store.PROFILE_PACK_KEY_PURPOSE):
            raise ServiceError(f"unknown key purpose {purpose!r}")
        try:
            self._require_confirmation_or_raise("key.rotate", [purpose], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        crypto = self.profile_pack_crypto if purpose == store.PROFILE_PACK_KEY_PURPOSE else self.crypto
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="key.rotate", actor="operator") as conn:
            new_generation_id = store.rotate_key_generation(conn, crypto, purpose=purpose)
        return {
            "status": "rotated", "purpose": purpose, "new_generation_id": new_generation_id,
            "next_step": (
                "republish profile.publish to re-encrypt future generations under the new key; "
                "prior published generations referencing the old key are now permanently unreadable"
                if purpose == store.PROFILE_PACK_KEY_PURPOSE
                else "prior local content encrypted under the old key generation is now permanently unreadable"
            ),
        }

    # ---------------------------------------------------------------------------------
    # Read operations
    # ---------------------------------------------------------------------------------

    def help(self, *, request: str = "") -> dict[str, Any]:
        request_lower = request.lower()
        scored = []
        for op in public_operations():
            haystack = f"{op.name} {op.summary}".lower()
            score = sum(1 for word in request_lower.split() if word in haystack)
            scored.append((score, op))
        scored.sort(key=lambda t: -t[0])
        ranked = [op.name for score, op in scored if score > 0] or [op.name for _, op in scored[:5]]
        audit.record(self.conn, operation_id=new_id("op"), operation_type="help", actor="operator", consumer=None, result="success")
        return {"ranked_operations": ranked[:5], "note": "help never invokes an operation"}

    def _active_operator_subject_ids(self) -> list[str]:
        return [
            subject.subject_id
            for subject in store.list_subjects(self.conn)
            if subject.kind == SubjectKind.OPERATOR and subject.active
        ]

    def status(self) -> dict[str, Any]:
        cfg = store.get_backend_config(self.conn)
        cancel = store.get_cancellation_state(self.conn)
        subjects = store.list_subjects(self.conn)
        operator_subjects = [
            subject for subject in subjects if subject.kind == SubjectKind.OPERATOR
        ]
        operator_subject_ids = [
            subject.subject_id for subject in operator_subjects if subject.active
        ]
        if not subjects:
            next_step = "run 'operator-voice setup' to get started"
        elif cancel.off:
            next_step = "toolkit is off — run 'operator-voice on' to resume"
        elif operator_subject_ids:
            next_step = "ready"
        elif operator_subjects:
            next_step = _PAUSED_OPERATOR_GUIDANCE
        else:
            next_step = "run 'operator-voice setup' to get started"
        return {
            "state": backend_health_copy(cfg), "backend_mode": cfg.mode.value, "off": cancel.off, "next_step": next_step,
            "version": operator_voice.__version__,
            "brief": f"operator-voice {operator_voice.__version__}: {next_step}" + self._reextract_notice() + self._retired_notice(),
            "gateway_enabled": self.gateway.enabled,
            "operator_subject_ids": operator_subject_ids,
            "consumer_id_hint": _CONSUMER_ID_HINT,
        }

    def _reextract_notice(self) -> str:
        has_documents = any(store.count_documents_for_source(self.conn, source.source_id)
                            for source in store.list_sources(self.conn, self.crypto))
        latest = audit.latest_success(self.conn, "reextract")
        if has_documents and (latest is None or latest.versions.get("adapters") != ADAPTER_VERSION):
            return "; Your voice evidence needs a one-time refresh: run `operator-voice reextract`"
        return ""

    def _retired_notice(self) -> str:
        count = sum(
            1 for source in store.list_sources(self.conn, self.crypto)
            if source.adapter_type in RETIRED_ADAPTER_TYPES
            and store.list_document_ids_for_source(self.conn, source.source_id)
        )
        if not count:
            return ""
        return (f"; {count} retired sources (agent chats or local notes) are no longer read or used "
                "for your voice. They stay stored until you erase each one with "
                "`operator-voice erase --scope source --target <id>` (ids in `curation-status`).")

    def doctor(self) -> dict[str, Any]:
        compatible, schema_detail = migrations.check_compatible(self.conn)
        keychain_ok = True
        try:
            _ = self.crypto.kek
        except Exception as exc:  # pragma: no cover - real Keychain failure path
            keychain_ok = False
            schema_detail += f"; keychain error: {type(exc).__name__}"
        cfg = store.get_backend_config(self.conn)
        operator_subject_ids = self._active_operator_subject_ids()
        return {
            "schema_compatible": compatible,
            "schema_detail": schema_detail,
            "keychain_access": keychain_ok,
            "backend_mode": cfg.mode.value,
            "backend_health": backend_health_copy(cfg),
            "gateway_enabled": self.gateway.enabled,
            "operator_subject_ids": operator_subject_ids,
            "consumer_id_hint": _CONSUMER_ID_HINT,
        }

    def config_view(self) -> dict[str, Any]:
        cfg = store.get_backend_config(self.conn)
        gateway_cfg = store.get_gateway_config(self.conn)
        return {
            "backend_mode": cfg.mode.value,
            "backend_active": cfg.active,
            "gateway": "enabled" if gateway_cfg.operator_egress_enabled or gateway_cfg.external_egress_enabled else "disabled",
            "schema_version": migrations.CURRENT_SCHEMA_VERSION,
        }

    def subject_list(self) -> dict[str, Any]:
        subjects = store.list_subjects(self.conn)
        return {"subjects": [
            {"subject_id": s.subject_id, "kind": s.kind.value, "display_label": s.display_label, "active": s.active}
            for s in subjects
        ]}

    def profile_inspect(self, *, subject_id: str, facet: Optional[str] = None) -> dict[str, Any]:
        facts = store.list_facts(self.conn, self.crypto, subject_id)
        if facet:
            facts = [f for f in facts if f.facet == facet]
        generations = store.list_generations(self.conn, subject_id)
        return {
            "facts": [
                {"facet": f.facet, "value": f.value, "state": f.state.value, "confidence": f.confidence,
                 "scope": f.scope.key(), "document_count": f.document_count, "source_count": f.source_count}
                for f in facts
            ],
            "generation_count": len(generations),
            "latest_generation_id": generations[-1].generation_id if generations else None,
        }

    def profile_search(self, *, subject_id: str, query: str = "") -> dict[str, Any]:
        facts = store.list_facts(self.conn, self.crypto, subject_id)
        if query:
            facts = [f for f in facts if query.lower() in f.facet.lower()]
        return {"matches": [{"facet": f.facet, "state": f.state.value, "confidence": f.confidence} for f in facts]}

    def context_get(
        self, *, subject_id: Optional[str] = None, consumer_id: Optional[str] = None,
        channel: str = "general", audience: str = "general",
        purpose: str = "general", language: str = "en", output_type: str = "text", token_budget: int = 800,
        accepted_major_versions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        from operator_voice.domain.contracts import SchemaError, negotiate_bundle_version

        if type(token_budget) is not int or not retrieval.MIN_TOKEN_BUDGET <= token_budget <= retrieval.MAX_TOKEN_BUDGET:
            raise ServiceError(
                f"token_budget must be a whole number from {retrieval.MIN_TOKEN_BUDGET} to "
                f"{retrieval.MAX_TOKEN_BUDGET}; it bounds the whole emitted bundle"
            )
        subject_id = (subject_id or "").strip() or None
        if not consumer_id or not consumer_id.strip():
            raise ServiceError(f"consumer_id is required; {_CONSUMER_ID_HINT}.")
        if subject_id is None:
            operator_subject_ids = self._active_operator_subject_ids()
            if not operator_subject_ids:
                operator_subjects = [
                    subject
                    for subject in store.list_subjects(self.conn)
                    if subject.kind == SubjectKind.OPERATOR
                ]
                if operator_subjects:
                    raise ServiceError(
                        "no active OPERATOR subject is available because every registered OPERATOR "
                        f"subject is paused; {_PAUSED_OPERATOR_GUIDANCE}."
                    )
                raise ServiceError(
                    "no OPERATOR subject is registered; run 'operator-voice setup' to register one "
                    "before context-get."
                )
            if len(operator_subject_ids) > 1:
                available = ", ".join(sorted(operator_subject_ids))
                raise ServiceError(
                    "multiple active OPERATOR subjects are available; pass --subject-id explicitly "
                    f"using one of: {available}"
                )
            subject_id = operator_subject_ids[0]
        subject = store.get_subject(self.conn, subject_id)
        if subject is None:
            raise _unknown_subject_error(subject_id, needs_consumer_id=True)
        if subject.kind != SubjectKind.OPERATOR:
            raise ServiceError("context.get is OPERATOR-only; use subject.insights for EXTERNAL subjects")
        # Version negotiation (§6.3): fail closed BEFORE doing any work if the consumer cannot accept
        # the frozen v1 bundle major.
        try:
            negotiate_bundle_version(accepted_major_versions)
        except SchemaError as exc:
            raise ServiceError(str(exc)) from None
        facts = store.list_facts(self.conn, self.crypto, subject_id)
        generation = store.get_latest_generation(self.conn, subject_id)
        scope = ContextScope(channel=channel, audience=audience, purpose=purpose, language=language, output_type=output_type)
        request = BundleRequest(
            subject_id=subject_id, consumer_id=consumer_id,
            generation_id=generation.generation_id if generation else "no_generation_yet",
            scope=scope, token_budget=token_budget,
        )
        try:
            bundle = build_context_bundle(request, facts, warnings=self._refresh_offer_warnings(channel))
        except retrieval.BundleBudgetError as exc:
            raise ServiceError(str(exc)) from None
        from operator_voice.domain.contracts import voice_context_bundle_to_dict

        audit.record(self.conn, operation_id=new_id("op"), operation_type="context.get", actor="operator", consumer=consumer_id, result="success")
        return voice_context_bundle_to_dict(bundle)

    def _refresh_offer_warnings(self, channel):
        # Kept as a compatibility seam; daily maintenance owns freshness, never drafting.
        return []

    def _daily(self):
        from operator_voice.runtime.daily_cycle import DailyCycle
        if self.paths is None:
            raise ServiceError("daily cycle requires configured runtime paths")
        return DailyCycle(self.paths.state_dir, self.crypto)

    def _daily_call(self, method, **kwargs):
        from operator_voice.runtime.daily_cycle import CycleError
        try:
            return getattr(self._daily(), method)(**kwargs)
        except CycleError as exc:
            raise ServiceError(str(exc)) from exc

    def _completed_fetch_at(self, integration, imported_at):
        state = self._daily_call("read")
        if state.get("enabled"):
            return state["sources"][integration]["last_success_at"]
        return imported_at

    def cycle_status(self):
        if is_off(self.conn):
            return {"status": "off", "due": False, "attention": []}
        conflict = store.get_sync_state(self.conn).publish_status == SyncStatus.CONFLICT
        result = self._daily_call("status", conflict=conflict)
        if conflict:
            result.update(status="blocked_conflict", due=False)
        return result

    def cycle_configure(self, *, identities=None, file=None, timezone="America/Los_Angeles", hour=18, paused=False):
        if is_off(self.conn):
            raise OperationRefused("toolkit is off")
        if file:
            try:
                identities = json.loads(Path(file).read_text())["identities"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ServiceError("daily enrollment file must contain identities") from exc
        if not isinstance(identities, dict):
            raise ServiceError("daily enrollment requires all connected identities")
        return self._daily_call("configure", identities=identities, timezone=timezone, hour=hour, enabled=not paused)

    def cycle_identity(self, *, integration, identity):
        verified = self._daily_call("verify_identity", integration=integration, identity=identity)
        return {"status": "verified" if verified else "not_enrolled", "integration": integration}

    def cycle_begin(self, *, force=False):
        if is_off(self.conn):
            return {"status": "off"}
        if store.get_sync_state(self.conn).publish_status == SyncStatus.CONFLICT:
            return {"status": "blocked_conflict"}
        result = self._daily_call("begin", force=force)
        if result["status"] == "started":
            active = {s.adapter_type.value for s in store.list_active_sources(self.conn, self.crypto)}
            for integration in list(result["integrations"]):
                if integration + "_export" not in active:
                    self.cycle_record(run_id=result["run_id"], integration=integration, outcome="paused")
                    result["integrations"].remove(integration)
        return result

    def cycle_record(self, *, run_id, integration, outcome, counts=None, checkpoint=None):
        if is_off(self.conn):
            raise OperationRefused("toolkit is off")
        return self._daily_call("record", run_id=run_id, integration=integration, outcome=outcome,
                                counts=counts, checkpoint=checkpoint)

    def cycle_finish(self, *, run_id):
        # The control lock stays held through curation and publication, so another host
        # cannot start a replacement cycle during finalization even after lease expiry.
        return self._daily_call("finish", run_id=run_id, curation=lambda: self.curate(trigger="scheduled"))

    def cycle_acknowledge(self, *, notices):
        return self._daily_call("acknowledge", notices=notices,
                                conflict=store.get_sync_state(self.conn).publish_status == SyncStatus.CONFLICT)

    def capture_inventory(self, *, integration):
        """Private host inventory: ids/cursors only, no source prose; never print in reports."""
        if integration not in {"slack", "gmail", "drive"}:
            raise ServiceError("integration must be slack, gmail or drive")
        if self.paths is None:
            raise ServiceError("capture inventory requires runtime paths")
        from importlib import import_module
        module = import_module(f"operator_voice.{integration}.materialize")
        root = getattr(self.paths, integration + "_export_dir")
        records = {}
        for path in sorted(root.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if integration == "slack":
                for native, _ in module.parse_channel_file(text):
                    records[path.stem + ":" + native] = None
            else:
                for record in module.parse_export_file(text):
                    if integration == "gmail":
                        records[record["message_id"]] = record["internal_date"]
                    else:
                        native = record["file_id"]
                        records[native] = max(records.get(native, ""), record["modified_time"])
        sources = [s for s in store.list_sources(self.conn, self.crypto)
                   if s.adapter_type.value == integration + "_export" and Path(s.canonical_root).resolve() == root.resolve()]
        folders = sorted({f for s in sources for f in s.role_identity.get("registered_folders", [])})
        return {"integration": integration, "records": records, "registered_folders": folders,
                "sync_cursor": module.read_import_state(root).get("sync_cursor")}

    def refresh_offer(self, *, integration: str, answer: str) -> dict[str, Any]:
        if integration not in {"slack", "gmail", "drive"} or answer not in {"yes", "no"}:
            raise ServiceError("integration must be slack, gmail or drive; answer must be yes or no")
        with transaction(self.conn) as conn:
            audit.record(conn, operation_id=new_id("op"), operation_type=f"refresh.offer:{integration}",
                         actor="operator", consumer=None, result=answer)
        return {"status": "recorded", "integration": integration, "answer": answer}

    def subject_insights(self, *, subject_id: str, purpose: str) -> dict[str, Any]:
        """Return a ``subject-insight-bundle/v1`` for an explicitly-enrolled EXTERNAL subject
        (§4.3, §13 M4 worklist 2). Hard invariants enforced here:

        * OPERATOR subjects are refused (their surface is generation, not analysis).
        * Analysis REQUIRES prior explicit EXTERNAL enrollment (reviewed + approved purposes);
          an un-enrolled subject yields a refusal, never observations.
        * The requested purpose is gated by :func:`external_analysis.classify_purpose`; a
          generation/impersonation, future-forecast, sensitive-trait, or high-impact-decision
          purpose is REFUSED before any evidence is read.
        * The bundle is descriptive + evidence-bounded (uncertainty + counter-evidence) and ALWAYS
          carries the standing proxy-risk warning. It structurally cannot carry generation
          instructions (contract-enforced).
        * Any model assist is EXTERNAL egress — gated by the SEPARATE default-deny external switch.
          The call is attempted only to prove/record the boundary; a denial never blocks the
          deterministic local analysis, and no generation context is ever sent."""
        from operator_voice.domain.contracts import subject_insight_bundle_to_dict

        subject = store.get_subject(self.conn, subject_id)
        if subject is None:
            raise _unknown_subject_error(subject_id)
        if subject.kind != SubjectKind.EXTERNAL:
            raise ServiceError("subject.insights refuses OPERATOR subjects (§4.3)")

        def _refused(reason: str) -> dict[str, Any]:
            bundle = SubjectInsightBundle(
                bundle_id=new_id("bundle"), subject_id=subject_id, purpose=purpose, observations=[],
                warnings=[f"REFUSED: {reason}", external_analysis.PROXY_RISK_WARNING], expires_at=None,
            )
            audit.record(self.conn, operation_id=new_id("op"), operation_type="subject.insights",
                         actor="operator", consumer=None, result="refused")
            return subject_insight_bundle_to_dict(bundle)

        # Enrollment gate: analysis of a named non-operator requires explicit EXTERNAL enrollment.
        if subject.reviewed_at is None or not subject.approved_purposes:
            return _refused(
                "this EXTERNAL subject is not enrolled for analysis. Enroll first with an explicit "
                "analysis purpose (subject.add kind=EXTERNAL --purposes ...)."
            )
        verdict = external_analysis.classify_purpose(purpose)
        if not verdict.allowed:
            return _refused(verdict.reason)

        facts = store.list_facts(self.conn, self.crypto, subject_id)
        observations, warnings = external_analysis.build_insight_observations(facts)
        warnings.append(external_analysis.PROXY_RISK_WARNING)

        # EXTERNAL model egress — SEPARATE switch, default-deny even when operator egress is ON.
        # Attempt only when a provider/model is configured (nothing to attempt in the default
        # no-network posture). The signal is a content-free aggregate (never fact values, raw
        # text, or the subject's name), and a denial is recorded, not fatal.
        cfg = store.get_gateway_config(self.conn)
        if cfg.provider and cfg.model:
            signal = f"external_insight_summary facets={len(observations)} evidence_facts={len(facts)}"
            result, _decision = self._gateway_attempt(GatewayCallRequest(
                purpose="external_insight_summary", data_class=EXTERNAL_DATA_CLASS,
                provider=cfg.provider, model=cfg.model, signal=signal, is_external=True,
            ))
            if result.allowed:
                warnings.append("A model-assisted summary was permitted (EXTERNAL egress is enabled) "
                                "and used only to phrase the observations above; no generation context was sent.")
            else:
                warnings.append(f"EXTERNAL model egress denied ({result.outcome}); analysis is local-only. "
                                "EXTERNAL egress is a separate switch that stays disabled by default.")

        bundle = SubjectInsightBundle(
            bundle_id=new_id("bundle"), subject_id=subject_id, purpose=purpose,
            observations=observations, warnings=warnings, expires_at=None,
        )
        audit.record(self.conn, operation_id=new_id("op"), operation_type="subject.insights",
                     actor="operator", consumer=None, result="success")
        return subject_insight_bundle_to_dict(bundle)

    def draft_validate(
        self, *, subject_id: str, draft_text: str, source_brief: str = "",
        required_facts: Optional[list[str]] = None, forbidden_facts: Optional[list[str]] = None,
        semantic: bool = False,
    ) -> dict[str, Any]:
        """Deterministic validation always runs. When ``semantic=True`` (a high-stakes draft) AND the
        deterministic checks pass AND the gateway policy permits, an independent semantic/factual
        comparison runs; only a passing comparison upgrades the outcome to ``validated``. A material
        factual change, a forbidden/injected claim, or an unavailable review never yields
        ``validated`` — the absence of review is surfaced, not treated as a pass (§13 acceptance 6)."""
        facts = store.list_facts(self.conn, self.crypto, subject_id)
        run = validation.validate_draft(
            subject_id=subject_id, draft_text=draft_text, source_brief=source_brief, facts=facts,
            required_facts=required_facts, forbidden_facts=forbidden_facts,
        )
        semantic_info: dict[str, Any] = {"requested": bool(semantic), "performed": False, "verdict": None}
        checks = list(run.checks)
        outcome = run.outcome
        gateway_metadata = None

        if semantic and outcome == ValidationOutcome.DETERMINISTIC_ONLY:
            cfg = store.get_gateway_config(self.conn)
            signal = validation.build_semantic_signal(
                draft_text=draft_text, source_brief=source_brief,
                required_facts=required_facts or [], forbidden_facts=forbidden_facts or [],
            )
            result, _decision = self._gateway_attempt(GatewayCallRequest(
                purpose="semantic_review", data_class="operator",
                provider=cfg.provider or "", model=cfg.model or "", signal=signal, is_external=False,
            ))
            gateway_metadata = {"outcome": result.outcome, **result.metadata}
            semantic_info["performed"] = True
            semantic_info["gateway_outcome"] = result.outcome
            if result.allowed:
                verdict = validation.parse_semantic_verdict(result.text)
                semantic_info["verdict"] = verdict
                if verdict is True:
                    outcome = ValidationOutcome.VALIDATED
                    checks.append({"name": "semantic_fidelity", "passed": True,
                                   "detail": "configured semantic review judged factual fidelity preserved"})
                elif verdict is False:
                    outcome = ValidationOutcome.UNVALIDATED
                    checks.append({"name": "semantic_fidelity", "passed": False,
                                   "detail": "semantic review detected a material factual change"})
                else:
                    checks.append({"name": "semantic_fidelity", "passed": False,
                                   "detail": "semantic review was inconclusive; not treated as a pass"})
            else:
                checks.append({"name": "semantic_fidelity", "passed": False,
                               "detail": f"semantic review unavailable ({result.outcome}); not treated as a pass"})
        elif semantic and outcome == ValidationOutcome.UNVALIDATED:
            semantic_info["skipped_reason"] = "deterministic checks failed; a draft that fails them can never be validated"

        run = replace(run, outcome=outcome, checks=checks, gateway_metadata=gateway_metadata)
        store.insert_validation_run(self.conn, run)
        note = (
            "validated requires passing deterministic checks AND a passing configured semantic review; "
            "absence of that review is surfaced, never treated as a pass"
        )
        return {"outcome": run.outcome.value, "checks": run.checks, "semantic_review": semantic_info, "note": note}

    def audit_read(self, *, limit: int = 50) -> dict[str, Any]:
        events = audit.read(self.conn, limit=limit)
        return {"events": [
            {"operation_type": e.operation_type, "actor": e.actor, "result": e.result, "created_at": e.created_at}
            for e in events
        ]}

    def profile_backend_status(self) -> dict[str, Any]:
        cfg = store.get_backend_config(self.conn)
        return {"mode": cfg.mode.value, "active": cfg.active, "health": backend_health_copy(cfg)}

    def profile_sync_status(self) -> dict[str, Any]:
        state = store.get_sync_state(self.conn)
        return {
            "local_generation_id": state.local_generation_id, "remote_generation_id": state.remote_generation_id,
            "publish_status": state.publish_status.value, "conflict_count": len(state.conflict_set),
        }

    def review_list(self, *, subject_id: Optional[str] = None, status: str = "OPEN") -> dict[str, Any]:
        items = store.list_review_items(self.conn, self.crypto, subject_id=subject_id, status=status or None)
        return {
            "count": len(items),
            "items": [
                {
                    "review_id": it.review_id, "subject_id": it.subject_id, "reason": it.reason.value,
                    "detail": it.detail, "facet": it.facet,
                    "scope": it.scope.key() if it.scope else None,
                    "related_fact_id": it.related_fact_id, "status": it.status.value,
                }
                for it in items
            ],
        }

    def gateway_status(self) -> dict[str, Any]:
        cfg = store.get_gateway_config(self.conn)
        return {
            "operator_egress_enabled": cfg.operator_egress_enabled,
            "external_egress_enabled": cfg.external_egress_enabled,
            "provider": cfg.provider, "model": cfg.model,
            "allowed_data_classes": cfg.allowed_data_classes, "timeout_ms": cfg.timeout_ms,
            "runtime_gateway_enabled": self.gateway.enabled,
            "available_providers": sorted(self.gateway.providers.keys()),
            "note": "Model egress is disabled by default. EXTERNAL egress is a SEPARATE switch that "
                    "stays denied even when operator egress is enabled. The deterministic kernel "
                    "never needs a model.",
        }

    def gateway_calls(self, *, limit: int = 50) -> dict[str, Any]:
        """Operator-visible, content-free model-call ledger (§4.4). Metadata only — never any signal
        payload (zero payload retention)."""
        records = store.list_model_call_records(self.conn, limit=limit)
        return {
            "count": len(records),
            "calls": [
                {"provider": r.provider, "model": r.model, "data_class": r.data_class,
                 "purpose": r.purpose, "outcome": r.outcome, "duration_ms": r.duration_ms,
                 "cancelled": r.cancelled, "created_at": r.created_at}
                for r in records
            ],
        }

    def dashboard_data(self) -> dict[str, Any]:
        """Read-only, redacted, content-free status snapshot for the render-only Cursor dashboard
        (§13 M4 worklist "render-only Cursor dashboard"). This is a pure READ: it performs NO
        mutation and NO staged_operation. It surfaces counts/enums/timestamps only — never fact
        values, raw text, source paths, or an EXTERNAL subject's name (EXTERNAL labels are redacted
        so the dashboard/canvas can be shown or committed without leaking a named person)."""
        cfg = store.get_gateway_config(self.conn)
        backend = store.get_backend_config(self.conn)
        sync = store.get_sync_state(self.conn)
        subjects = store.list_subjects(self.conn)
        by_state: dict[str, int] = {}
        subject_rows: list[dict[str, Any]] = []
        total_facts = 0
        external_alias_count = 0
        for s in subjects:
            facts = store.list_facts(self.conn, self.crypto, s.subject_id)
            total_facts += len(facts)
            for f in facts:
                by_state[f.state.value] = by_state.get(f.state.value, 0) + 1
            if s.kind == SubjectKind.EXTERNAL:
                external_alias_count += len(store.list_subject_aliases(self.conn, self.crypto, s.subject_id))
            subject_rows.append({
                "subject_id": s.subject_id,
                "kind": s.kind.value,
                # Operator's own label is theirs to see; an EXTERNAL subject's name is redacted.
                "label": s.display_label if s.kind == SubjectKind.OPERATOR else "EXTERNAL subject",
                "active": s.active,
                "generation_permission": s.generation_permission,
                "fact_count": len(facts),
                "enrolled": s.reviewed_at is not None,
            })
        calls = store.list_model_call_records(self.conn, limit=20)
        external_denials = sum(
            1 for c in calls if c.data_class == EXTERNAL_DATA_CLASS and c.outcome != "SUCCESS"
        )
        return {
            "schema": "operator-voice-dashboard/v1",
            "generated_at": now_ts(),
            "runtime": {
                "off": is_off(self.conn),
                "backend_mode": backend.mode.value,
                "backend_active": backend.active,
                "operator_egress_enabled": cfg.operator_egress_enabled,
                "external_egress_enabled": cfg.external_egress_enabled,
                "provider": cfg.provider,
                "model": cfg.model,
            },
            "subjects": {
                "operator_count": sum(1 for s in subjects if s.kind == SubjectKind.OPERATOR),
                "external_count": sum(1 for s in subjects if s.kind == SubjectKind.EXTERNAL),
                "external_alias_count": external_alias_count,
                "items": subject_rows,
            },
            "facts": {"total": total_facts, "by_state": by_state},
            "reviews": {"open_count": store.count_open_review_items(self.conn)},
            "sync": {
                "publish_status": sync.publish_status.value,
                "local_generation_id": sync.local_generation_id,
                "remote_generation_id": sync.remote_generation_id,
                "conflict_count": len(sync.conflict_set),
            },
            "gateway": {
                "recent_calls": [
                    {"purpose": c.purpose, "data_class": c.data_class, "outcome": c.outcome}
                    for c in calls[:10]
                ],
                "external_egress_denials": external_denials,
            },
        }

    # ---------------------------------------------------------------------------------
    # Mutations
    # ---------------------------------------------------------------------------------

    def config_set(self, *, key: str, value: str) -> dict[str, Any]:
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="config.set", actor="operator") as conn:
            pass  # M1's declared config keys are all covered by dedicated operations (backend/retention);
            # this generic setter exists so the registry/CLI surface is complete for M2 keys.
        return {"status": "accepted", "key": key, "value": value}

    def subject_add(self, *, display_label: str, kind: str = "OPERATOR", purposes: Optional[list[str]] = None) -> dict[str, Any]:
        """Register a subject. EXTERNAL enrollment (§4.3, §13 M4 worklist 2) is explicit and
        constrained: it REQUIRES at least one approved purpose, every purpose must be an allowed
        ANALYSIS purpose (a generation/impersonation, future-forecast, sensitive-trait, or
        high-impact-decision purpose is refused at enrollment), the subject can NEVER hold
        generation permission, and the enrollment is stamped operator-attested + reviewed."""
        if kind == "EXTERNAL":
            cleaned = [p.strip() for p in (purposes or []) if p and p.strip()]
            if not cleaned:
                raise ServiceError(
                    "EXTERNAL enrollment requires at least one explicit approved analysis purpose "
                    "(§4.3). Example: --purposes '[\"communication_pattern_analysis\"]'."
                )
            for purpose in cleaned:
                verdict = external_analysis.classify_purpose(purpose)
                if not verdict.allowed:
                    raise ServiceError(
                        f"cannot enroll EXTERNAL subject for purpose {purpose!r}: {verdict.reason}"
                    )
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="subject.add", actor="operator") as conn:
            if kind == "EXTERNAL":
                subject = SubjectRegistration.new_external(display_label, cleaned)
                subject.consent_basis = "operator-attested"
                subject.reviewed_at = now_ts()
            else:
                subject = SubjectRegistration.new_operator(display_label)
            store.insert_subject(conn, subject)
        return {
            "status": "added", "subject_id": subject.subject_id, "kind": subject.kind.value,
            "generation_permission": subject.generation_permission,
            "approved_purposes": subject.approved_purposes,
        }

    def subject_alias_add(
        self, *, subject_id: str, source_type: str, source_native_id: str, confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Enroll a stable, source-native identifier for an EXTERNAL subject (§5 SubjectAlias,
        §13 M4 worklist 2). A display name alone is never authoritative — analysis of a named
        non-operator keys off operator-attested aliases. Deterministic collision handling: if the
        identifier already maps to a DIFFERENT subject, the new alias is stored quarantined
        (``verification_state='collision'`` + a review note) and NOT treated as verified, rather
        than silently re-pointing an identifier. Re-adding the same (subject, identifier) is
        idempotent."""
        subject = store.get_subject(self.conn, subject_id)
        if subject is None:
            raise _unknown_subject_error(subject_id)
        if subject.kind != SubjectKind.EXTERNAL:
            raise ServiceError(
                "subject.alias_add applies to EXTERNAL subjects only; the operator's own identity "
                "is established by source role authority, not operator-attested aliases (§4.3)."
            )
        native = (source_native_id or "").strip()
        if not native:
            raise ServiceError("source_native_id is required and must be non-empty")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="subject.alias_add", actor="operator") as conn:
            owner = store.find_alias_owner(conn, self.crypto, source_type, native)
            if owner == subject_id:
                return {"status": "exists", "subject_id": subject_id, "verification_state": "operator_attested"}
            collision = owner is not None and owner != subject_id
            alias = SubjectAlias(
                alias_id=new_id("alias"), subject_id=subject_id, source_type=source_type,
                source_native_id=native, confidence=float(confidence),
                verification_state="collision" if collision else "operator_attested",
                collision_review=(f"identifier already mapped to {owner}" if collision else None),
            )
            store.insert_subject_alias(conn, self.crypto, alias)
        return {
            "status": "collision" if collision else "added",
            "alias_id": alias.alias_id, "subject_id": subject_id,
            "verification_state": alias.verification_state,
            "collision_review": alias.collision_review,
        }

    def subject_pause(self, *, subject_id: str) -> dict[str, Any]:
        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="subject.pause", actor="operator") as conn:
            store.set_subject_active(conn, subject_id, False)
        return {"status": "paused", "subject_id": subject_id}

    def source_add(self, *, subject_id: str, adapter_type: str, canonical_root: str, approved_purpose: str = "voice_generation") -> dict[str, Any]:
        from operator_voice.domain.models import AdapterType

        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        if AdapterType(adapter_type) in RETIRED_ADAPTER_TYPES:
            raise ServiceError("Agent chats and local notes are no longer used for your voice. "
                               "Add Slack, Gmail or Google Docs instead.")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="source.add", actor="operator") as conn:
            subject_role = "user"  # §5/§4: every M1 adapter's authoritative "this is the operator" role is "user"
            source = SourceRegistration(
                source_id=new_id("src"), subject_id=subject_id, adapter_type=AdapterType(adapter_type),
                canonical_root=canonical_root, opted_in_at=now_ts(), approved_purpose=approved_purpose,
                active=True, role_identity={"subject_role": subject_role},
            )
            store.insert_source(conn, self.crypto, source)
        return {"status": "added", "source_id": source.source_id, "active": True}

    def source_pause(self, *, source_id: str) -> dict[str, Any]:
        if store.get_source(self.conn, self.crypto, source_id) is None:
            raise ServiceError(f"unknown source_id {source_id!r}")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="source.pause", actor="operator") as conn:
            store.set_source_paused(conn, source_id, True)
        return {"status": "paused", "source_id": source_id}

    def slack_import(
        self, *, author_id: Optional[str] = None, messages: Optional[list] = None, file: Optional[str] = None,
    ) -> dict[str, Any]:
        """Materialize an agent-submitted batch of the operator's OWN Slack messages (captured
        agent-side via the Slack MCP; this method itself never calls Slack — no network, no SDK,
        no token) into the fixed ``slack_export_dir`` (§ OVT Slack Adapter 1b) as per-channel
        Markdown the ``slack_export`` adapter can later scan. Accepts the ``{author_id,
        messages}`` envelope either inline (``author_id`` + ``messages`` directly — the natural
        shape for an MCP tool call) or via ``file`` (a path to that same JSON shape, mirroring
        ``portability_import``'s ``source`` pattern — the shape the skill overlay's documented
        workflow actually uses); the CLI additionally falls back to stdin when neither is given.

        The one hard security invariant: authorship is verified HERE, server-side, against each
        message's own ``author_id`` — never trusted from the calling agent's own "these are all
        mine" filtering (see ``operator_voice.slack.materialize``). A mismatch is dropped and
        counted under ``skipped_mismatched_author``, never silently accepted."""
        from operator_voice.slack import materialize as slack_materialize

        if self.paths is None:
            raise ServiceError("slack.import requires runtime paths (no export directory configured)")
        if file:
            path = Path(file)
            if not path.exists():
                raise ServiceError(f"slack import file not found: {file}")
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ServiceError(f"slack import file is not valid JSON: {exc}")
            if not isinstance(envelope, dict):
                raise ServiceError("slack import file must contain a JSON object with author_id/messages")
            author_id = envelope.get("author_id")
            messages = envelope.get("messages")
        if not author_id or not isinstance(author_id, str):
            raise ServiceError(
                "slack.import requires a top-level author_id (your own Slack user id, obtained fresh "
                "via slack_read_user_profile) — supply it directly, or via --file/stdin"
            )
        if not isinstance(messages, list):
            raise ServiceError(
                "slack.import requires a messages list — supply it directly, or via --file/stdin"
            )
        self._daily_call("verify_identity", integration="slack", identity=author_id)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="slack.import", actor="operator"):
            # No SQLite writes: this operation's mutation is the export-dir file write below.
            # `staged_operation` is still used for the off-switch check and the content-free
            # audit trail entry every other mutation gets, per §6.
            result = slack_materialize.materialize(self.paths.slack_export_dir, author_id=author_id, messages=messages)
            state = slack_materialize.read_import_state(self.paths.slack_export_dir)
            state["last_import_at"] = now_ts()
            slack_materialize.write_import_state(self.paths.slack_export_dir, state)
        return {"status": "ok", **result.as_dict()}

    def _coverage(self, adapter, root):
        sources = [s for s in store.list_sources(self.conn, self.crypto)
                   if s.adapter_type == adapter and Path(s.canonical_root).resolve() == root.resolve()
                   and store.get_subject(self.conn, s.subject_id).kind == SubjectKind.OPERATOR]
        learned = {(s.source_id, native) for s in sources for native in store.learned_native_ids(self.conn, s.source_id)}
        records = []
        for source in sources:
            if not source.active or source.paused or not root.exists():
                continue
            candidates, _, _ = self._full_scan(source, require_candidates=False)
            for native, candidate in candidates.items():
                state, _ = authorship.classify_role(candidate, str(source.role_identity.get("subject_role", "")))
                if state != AuthorshipState.SUBJECT:
                    continue
                own = authorship.own_text(candidate.raw_text)
                prose, _ = normalize.strip_non_prose(own)
                if not prose.strip() or (candidate.context or {}).get("below_analytic_floor", False):
                    continue
                records.append({"id": (source.source_id, native), "source_native_id": native,
                                "native_revision": candidate.context.get("modified_time"),
                                "adapter_type": adapter.value, "text_key": self._text_key(own) if own else None})
        repeated = store.repeated_evidence_ids(records)
        eligible = {record["id"] for record in records if record["id"] not in repeated}
        return {"ingested_count": len(learned & eligible), "eligible_count": len(eligible)}

    def slack_status(self) -> dict[str, Any]:
        """Content-free Slack-voice freshness snapshot (§ OVT Slack Adapter 1d) — per-channel
        message counts and a staleness verdict, never raw text. Every caller (CLI, MCP, direct)
        gets the same plain-language ``brief`` line in the result; the CLI's ``--brief`` flag is
        purely a presentation choice (print just that one line instead of the full JSON) for
        session-start hooks — it changes no computation here."""
        from operator_voice.slack import materialize as slack_materialize

        if self.paths is None:
            return {
                "ingested_count": 0, "eligible_count": 0,
                "last_import_at": None, "message_count": 0, "channels": {}, "stale": True,
                "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
                "brief": "slack-voice: not configured (no runtime paths)",
            }
        export_dir = self.paths.slack_export_dir
        state = slack_materialize.read_import_state(export_dir)
        last_import_at = self._completed_fetch_at("slack", state.get("last_import_at"))
        channels = slack_materialize.count_messages_by_channel(export_dir)
        message_count = sum(channels.values())
        if last_import_at is None:
            stale = True
            brief = "slack-voice: stale — ask agent to refresh Slack voice"
        else:
            age_hours = (now_ts() - float(last_import_at)) / 3600.0
            stale = age_hours >= _CHANNEL_STALE_AFTER_HOURS
            if stale:
                brief = "slack-voice: stale — ask agent to refresh Slack voice"
            else:
                when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(last_import_at)))
                brief = f"slack-voice: fresh ({message_count} messages, last import {when} UTC)"
        coverage = self._coverage(AdapterType.SLACK_EXPORT, export_dir)
        brief += f"; {coverage['ingested_count']} of {coverage['eligible_count']} messages learned from"
        return {
            **coverage,
            "last_import_at": last_import_at,
            "message_count": message_count,
            "channels": channels,
            "stale": stale,
            "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
            "brief": brief,
        }

    def _registered_drive_source(self) -> SourceRegistration | None:
        if self.paths is None:
            return None
        root = str(self.paths.drive_export_dir.resolve())
        matches = [source for source in store.list_sources(self.conn, self.crypto)
                   if source.adapter_type == AdapterType.DRIVE_EXPORT and source.canonical_root == root
                   and store.get_subject(self.conn, source.subject_id).kind == SubjectKind.OPERATOR]
        return matches[0] if len(matches) == 1 else None

    def _drive_folder_change(self, folder_id: str, *, add: bool) -> dict[str, Any]:
        source = self._registered_drive_source()
        if source is None:
            raise ServiceError("Drive source is not configured; run `operator-voice setup`.")
        if not isinstance(folder_id, str) or not folder_id.strip():
            raise ServiceError("A non-empty Drive folder id is required.")
        folders = set(source.role_identity.get("registered_folders", []))
        if add:
            folders.add(folder_id)
        else:
            folders.discard(folder_id)
        identity = {**source.role_identity, "registered_folders": sorted(folders)}
        operation = "drive.folder_add" if add else "drive.folder_remove"
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type=operation, actor="operator") as conn:
            store.set_source_role_identity(conn, source.source_id, identity)
        return {"status": "ok", "registered_folder_count": len(folders)}

    def drive_folder_add(self, *, folder_id: str) -> dict[str, Any]:
        return self._drive_folder_change(folder_id, add=True)

    def drive_folder_remove(self, *, folder_id: str) -> dict[str, Any]:
        return self._drive_folder_change(folder_id, add=False)

    def drive_import(
        self, *, owner_id: Optional[str] = None, files: Optional[list] = None,
        sync_cursor: Optional[dict] = None, file: Optional[str] = None,
    ) -> dict[str, Any]:
        """Materialize an agent-submitted batch of the operator's OWN, non-Shared-Drive Drive files
        (fetched agent-side via the operator's host Drive tools; this method itself never calls
        Google — no network, no SDK, no token, no OAuth) into the fixed ``drive_export_dir``
        (§ docs/drive-adapter.md) as immutable, timestamp-prefixed Markdown the ``drive_export``
        adapter can later scan. Accepts the ``{owner_id, sync_cursor, files}`` envelope either inline
        (the natural shape for an MCP tool call) or via ``file`` (mirroring ``portability_import``'s
        ``source`` pattern); the CLI additionally falls back to stdin when neither is given.

        The hard security invariant: ownership is verified HERE, server-side, per file — a Shared
        Drive (``drive_id`` present or missing), multi-owner (``owners != [owner_id]``), or mismatched
        (entry ``owner_id`` != top-level) file is dropped and counted, never silently accepted (see
        ``operator_voice.drive.materialize``). The agent-supplied ``sync_cursor`` (Drive Changes-API
        ``changes_page_token`` / ``new_start_page_token``) is persisted verbatim so the next refresh
        can resume incrementally (issue #37 full-sync-on-expiry is an agent-side fallback, documented
        in the adapter doc — this method just stores whatever token the agent supplies)."""
        from operator_voice.drive import materialize as drive_materialize

        if self.paths is None:
            raise ServiceError("drive.import requires runtime paths (no export directory configured)")
        if file:
            path = Path(file)
            if not path.exists():
                raise ServiceError(f"drive import file not found: {file}")
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ServiceError(f"drive import file is not valid JSON: {exc}")
            if not isinstance(envelope, dict):
                raise ServiceError("drive import file must contain a JSON object with owner_id/files")
            owner_id = envelope.get("owner_id")
            files = envelope.get("files")
            if sync_cursor is None:
                sync_cursor = envelope.get("sync_cursor")
        if not owner_id or not isinstance(owner_id, str):
            raise ServiceError(
                "drive.import requires a top-level owner_id (your own Drive user id, obtained fresh "
                "from your host Drive tools) — supply it directly, or via --file/stdin"
            )
        if not isinstance(files, list):
            raise ServiceError(
                "drive.import requires a files list — supply it directly, or via --file/stdin"
            )
        self._daily_call("verify_identity", integration="drive", identity=owner_id)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="drive.import", actor="operator"):
            # No SQLite writes: this operation's mutation is the export-dir file write below.
            # `staged_operation` is still used for the off-switch check and the content-free audit
            # trail entry every other mutation gets, per §6.
            source = self._registered_drive_source()
            folders = source.role_identity.get("registered_folders", []) if source else []
            result = drive_materialize.materialize(
                self.paths.drive_export_dir, owner_id=owner_id, files=files, registered_folders=folders,
            )
            state = drive_materialize.read_import_state(self.paths.drive_export_dir)
            state["last_import_at"] = now_ts()
            if isinstance(sync_cursor, dict):
                state["sync_cursor"] = sync_cursor
            drive_materialize.write_import_state(self.paths.drive_export_dir, state)
        return {"status": "ok", **result.as_dict()}

    def drive_status(self) -> dict[str, Any]:
        """Content-free Drive-voice freshness snapshot (§ docs/drive-adapter.md) — per-``file_id``
        revision counts, the persisted sync cursor to resume from, and a staleness verdict, never raw
        text. Every caller (CLI, MCP, direct) gets the same plain-language ``brief`` line; the CLI's
        ``--brief`` flag is purely a presentation choice for session-start hooks."""
        from operator_voice.drive import materialize as drive_materialize

        if self.paths is None:
            return {
                "ingested_count": 0, "eligible_count": 0,
                "registered_folder_count": 0, "last_import_at": None, "file_count": 0, "record_count": 0, "files": {},
                "sync_cursor": None, "stale": True, "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
                "brief": "drive-voice: not configured (no runtime paths)",
            }
        export_dir = self.paths.drive_export_dir
        state = drive_materialize.read_import_state(export_dir)
        last_import_at = self._completed_fetch_at("drive", state.get("last_import_at"))
        sync_cursor = state.get("sync_cursor")
        files = drive_materialize.count_records_by_file(export_dir)
        record_count = sum(files.values())
        file_count = len(files)
        if last_import_at is None:
            stale = True
            brief = "drive-voice: stale — ask agent to refresh Drive voice"
        else:
            age_hours = (now_ts() - float(last_import_at)) / 3600.0
            stale = age_hours >= _CHANNEL_STALE_AFTER_HOURS
            if stale:
                brief = "drive-voice: stale — ask agent to refresh Drive voice"
            else:
                when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(last_import_at)))
                brief = f"drive-voice: fresh ({file_count} files, {record_count} revisions, last import {when} UTC)"
        source = self._registered_drive_source()
        folder_count = len(source.role_identity.get("registered_folders", [])) if source else 0
        if folder_count == 0:
            brief += "; no registered folders — select folders containing your own writing"
        coverage = self._coverage(AdapterType.DRIVE_EXPORT, export_dir)
        if coverage["ingested_count"] < coverage["eligible_count"]:
            brief += f"; {coverage['ingested_count']} of {coverage['eligible_count']} Docs learned from"
        return {
            **coverage,
            "registered_folder_count": folder_count,
            "last_import_at": last_import_at,
            "file_count": file_count,
            "record_count": record_count,
            "files": files,
            "sync_cursor": sync_cursor,
            "stale": stale,
            "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
            "brief": brief,
        }

    def gmail_import(
        self, *, author_email: Optional[str] = None, messages: Optional[list] = None,
        sync_cursor: Optional[dict] = None, file: Optional[str] = None,
    ) -> dict[str, Any]:
        """Materialize an agent-submitted batch of the operator's OWN Sent Gmail messages (fetched
        agent-side via the operator's host Gmail tools; this method itself never calls Google) into
        the fixed ``gmail_export_dir`` (§ docs/gmail-adapter.md) as immutable, timestamp-prefixed
        Markdown the ``gmail_export`` adapter can later scan."""
        from operator_voice.gmail import materialize as gmail_materialize

        if self.paths is None:
            raise ServiceError("gmail.import requires runtime paths (no export directory configured)")
        if file:
            path = Path(file)
            if not path.exists():
                raise ServiceError(f"gmail import file not found: {file}")
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ServiceError(f"gmail import file is not valid JSON: {exc}")
            if not isinstance(envelope, dict):
                raise ServiceError("gmail import file must contain a JSON object with author_email/messages")
            author_email = envelope.get("author_email")
            messages = envelope.get("messages")
            if sync_cursor is None:
                sync_cursor = envelope.get("sync_cursor")
        if not author_email or not isinstance(author_email, str):
            raise ServiceError(
                "gmail.import requires a top-level author_email (your own address, obtained fresh "
                "from your host Gmail tools) — supply it directly, or via --file/stdin"
            )
        if not isinstance(messages, list):
            raise ServiceError(
                "gmail.import requires a messages list — supply it directly, or via --file/stdin"
            )
        enrolled = self._daily_call("verify_identity", integration="gmail", identity=author_email)
        if enrolled and any(not isinstance(message, dict) or not isinstance(message.get("labels"), list)
                            for message in messages):
            raise ServiceError("enrolled Gmail capture requires actual label ids on every message")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="gmail.import", actor="operator"):
            result = gmail_materialize.materialize(self.paths.gmail_export_dir, author_email=author_email, messages=messages)
            state = gmail_materialize.read_import_state(self.paths.gmail_export_dir)
            state["last_import_at"] = now_ts()
            if isinstance(sync_cursor, dict):
                state["sync_cursor"] = sync_cursor
            gmail_materialize.write_import_state(self.paths.gmail_export_dir, state)
        return {"status": "ok", **result.as_dict()}

    def gmail_status(self) -> dict[str, Any]:
        """Content-free Gmail-voice freshness snapshot (§ docs/gmail-adapter.md)."""
        from operator_voice.gmail import materialize as gmail_materialize

        if self.paths is None:
            return {
                "ingested_count": 0, "eligible_count": 0,
                "last_import_at": None, "message_count": 0, "sync_cursor": None,
                "stale": True, "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
                "brief": "gmail-voice: not configured (no runtime paths)",
            }
        export_dir = self.paths.gmail_export_dir
        state = gmail_materialize.read_import_state(export_dir)
        last_import_at = self._completed_fetch_at("gmail", state.get("last_import_at"))
        sync_cursor = state.get("sync_cursor")
        message_count = gmail_materialize.count_messages(export_dir)
        if last_import_at is None:
            stale = True
            brief = "gmail-voice: stale — ask agent to refresh Gmail voice"
        else:
            age_hours = (now_ts() - float(last_import_at)) / 3600.0
            stale = age_hours >= _CHANNEL_STALE_AFTER_HOURS
            if stale:
                brief = "gmail-voice: stale — ask agent to refresh Gmail voice"
            else:
                when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(last_import_at)))
                brief = f"gmail-voice: fresh ({message_count} messages, last import {when} UTC)"
        coverage = self._coverage(AdapterType.GMAIL_EXPORT, export_dir)
        if coverage["ingested_count"] < coverage["eligible_count"]:
            brief += f"; {coverage['ingested_count']} of {coverage['eligible_count']} messages learned from"
        return {
            **coverage,
            "last_import_at": last_import_at,
            "message_count": message_count,
            "sync_cursor": sync_cursor,
            "stale": stale,
            "stale_after_hours": _CHANNEL_STALE_AFTER_HOURS,
            "brief": brief,
        }

    def google_status(self) -> dict[str, Any]:
        """Combined Drive + Gmail freshness snapshot (§ gmail-drive-channel-adapters M8) — aggregates
        the existing ``drive_status`` and ``gmail_status`` local snapshots into one PM-friendly
        dashboard line. Still no OVT-side Google calls."""
        from operator_voice.google.status import aggregate_google_status

        drive = self.drive_status()
        gmail = self.gmail_status()
        return aggregate_google_status(
            drive=drive, gmail=gmail, stale_after_hours=_CHANNEL_STALE_AFTER_HOURS,
        )

    def _profile_digest(self, conn, subject_id):
        """Keyed digest of live retrieval-relevant values, not incidental row identities.

        Evidence counts and confidence matter; timestamps, random ids and provenance do not.
        A duplicate or an identical revision cannot inflate the measured profile change.
        """
        facts = [{key: value for key, value in _fact_to_portable(f).items()
                  if key not in {"fact_id", "subject_id", "provenance_ids", "valid_from",
                                 "valid_to", "superseded_by", "created_at", "updated_at"}}
                 for f in store.list_facts(conn, self.crypto, subject_id)]
        payload = json.dumps(sorted(facts, key=lambda f: json.dumps(f, sort_keys=True, separators=(",", ":"))),
                             sort_keys=True, separators=(",", ":"))
        return hmac.new(self.crypto.hmac_secret, b"profile-state/v1:" + payload.encode(), hashlib.sha256).hexdigest()

    def _stamp_generation(
        self, conn: sqlite3.Connection, subject_id: str, facets: set[str], *, reason: str, diff_summary: dict[str, Any],
        parent_generation_id: Optional[str] = None,
    ) -> str:
        """Create + persist one :class:`ProfileGeneration` for ``subject_id`` pinning the current
        method versions. Shared by ``ingest`` (per source), ``curate`` (one per subject per tick),
        ``reanalyze``, and ``profile_reconcile`` so the version bundle is stamped identically everywhere."""
        if parent_generation_id is None:
            parent = store.get_latest_generation(conn, subject_id)
            parent_generation_id = parent.generation_id if parent else None
        generation = ProfileGeneration(
            generation_id=new_id("gen"), subject_id=subject_id,
            schema_version="operator-voice-schema/v1", normalization_version=normalize.NORMALIZATION_VERSION,
            extraction_version=_EXTRACTION_VERSION, synthesis_version=synthesis.SYNTHESIS_VERSION,
            taxonomy_version=taxonomy.TAXONOMY_VERSION, policy_version="policy/v1",
            tokenizer_version="conservative-estimator/v1", feature_registry_version=_EXTRACTION_VERSION,
            content_digest=self._profile_digest(conn, subject_id), creation_reason=reason,
            parent_generation_id=parent_generation_id,
            diff_summary=diff_summary,
        )
        portable = profile_pack.build_portable_objects(
            facts=store.list_facts(conn, self.crypto, subject_id),
            feedback_events=store.list_feedback_events(conn, self.crypto, subject_id), generation=generation)
        generation.diff_summary = {**diff_summary, "publish_digest": hmac.new(
            self.crypto.hmac_secret, b"publish-state/v1:" + ",".join(sorted(o.digest for o in portable)).encode(),
            hashlib.sha256).hexdigest()}
        store.insert_generation(conn, generation)
        return generation.generation_id

    def _text_key(self, text):
        return hmac.new(self.crypto.hmac_secret, ("text_key/v1:" + " ".join(text.lower().split())).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _extract_document(self, conn, source, candidate, subject_role, *, replace=False):
        """The single authorship gate and observation-writing path for ingest and reextract."""
        reference = self._calibration_reference()
        new_documents = quarantined = new_observations = 0
        touched_facets = set()
        outer_state, reason = authorship.classify_role(candidate, subject_role)
        own = "\n".join(segment.text for segment in authorship.split_authored_segments(candidate.raw_text, outer_state)
                        if segment.state == AuthorshipState.SUBJECT)
        prose, _ = normalize.strip_non_prose(own)
        normalized = normalize.normalize_text(prose)
        words = len(normalize.tokenize_words(normalized.text))
        doc_context = ContextScope(
            channel=_canonical_channel(candidate.channel),
            output_type=_canonical_output_type(candidate.output_type),
        )
        # Drive modified_time and provider-supplied Slack edit time replace evidence only
        # when strictly newer. Stable native ids survive replacement. Legacy Slack rows use
        # their original timestamp as the comparison floor; Gmail stays insert-only.
        native_revision = candidate.context.get("modified_time") if candidate.context else None
        doc = SourceDocument(
            document_id=new_id("doc"), subject_id=source.subject_id, source_id=source.source_id,
            source_native_id=candidate.source_native_id, digest=candidate.digest, locator=candidate.locator,
            content=candidate.raw_text, context=doc_context, authorship_state=outer_state,
            quarantine_reason=reason if outer_state == AuthorshipState.AMBIGUOUS_QUARANTINED else None,
            native_revision=native_revision, words=words,
            text_key=self._text_key(own) if own and outer_state == AuthorshipState.SUBJECT else None,
        )
        if replace:
            document_id = store.document_ids_for_source(conn, source.source_id)[candidate.source_native_id]
            doc.document_id = document_id
            store.update_document_classification(conn, self.crypto, doc)
            is_new = True
        else:
            document_id, is_new = store.upsert_document(
                conn, self.crypto, doc, keep_content=False, supersede_if_newer=native_revision is not None,
                legacy_revision=(candidate.context or {}).get("initial_time") if source.adapter_type == AdapterType.SLACK_EXPORT else None,
            )
        if not is_new:
            return {"documents_new": 0, "documents_quarantined": 0, "observations_new": 0, "touched_facets": set()}
        new_documents += 1
        if outer_state == AuthorshipState.AMBIGUOUS_QUARANTINED:
            quarantined += 1
        if outer_state != AuthorshipState.SUBJECT:
            return {"documents_new": new_documents, "documents_quarantined": quarantined,
                    "observations_new": 0, "touched_facets": set()}

        if normalized.text.strip() and not (candidate.context or {}).get("below_analytic_floor", False):
            feat_obs = features_to_observations(
                secret=self.crypto.hmac_secret, subject_id=source.subject_id, document_id=document_id,
                segment_id=f"{document_id}:0", text=normalized.text, context=doc_context,
            )
            # Both method registries consume the same stripped operator prose.
            sig_obs = signals.signals_to_observations(
                secret=self.crypto.hmac_secret, subject_id=source.subject_id, document_id=document_id,
                segment_id=f"{document_id}:0", text=normalized.text, context=doc_context,
                reference=reference or None,
            )
            new_observations += store.upsert_observations(conn, self.crypto, feat_obs + sig_obs)
            touched_facets.update(o.facet for o in feat_obs + sig_obs)
        store.clear_document_content(conn, document_id)  # zero-day retention, same transaction

        return {"documents_new": new_documents, "documents_quarantined": quarantined,
                "observations_new": new_observations, "touched_facets": touched_facets}

    def _ingest_source_within(
        self, conn: sqlite3.Connection, source: SourceRegistration, *,
        limit: Optional[int] = None, create_generation: bool = True, checkpoint_prefix: str = "ingest",
    ) -> dict[str, Any]:
        """The per-source ingest body shared by ``ingest`` (one source, its own transaction) and
        ``curate`` (every active source, each in its own transaction). The CALLER owns the
        transaction and the off/precondition checks; this method never opens a ``staged_operation``.

        Idempotent by construction (§13 M3): documents dedup on (source_id, source_native_id) and
        the source cursor advances monotonically, so re-scanning the same input adds zero new
        documents/observations and re-synthesizes to byte-identical facts."""
        if source.adapter_type in RETIRED_ADAPTER_TYPES:
            raise ServiceError("This retired source is no longer read or used for your voice. "
                               "Erase it with `operator-voice erase --scope source --target <id>` "
                               "(ids in `curation-status`).")
        if not source.active or source.paused:
            raise ServiceError(f"source {source.source_id!r} is not active")
        scanner = get_scanner(source.adapter_type)
        before_digest = self._profile_digest(conn, source.subject_id)
        prior_facets = set(store.list_facets_for_subject(conn, source.subject_id))
        scan_cursor = source.cursor
        if scan_cursor and source.adapter_type in {AdapterType.DRIVE_EXPORT, AdapterType.GMAIL_EXPORT}:
            last_scan = store.get_source_curation_state(conn, source.source_id)
            last_success = last_scan.last_success_at if last_scan else None
            # Keep the compatible lexical cursor, but recover a backdated record written
            # after the preceding successful scan (including a crashed import). Stat only;
            # the adapter remains the sole parser and applies all normal safety filters.
            if last_success is None or any(
                str(path) <= scan_cursor and max(path.stat().st_mtime, path.stat().st_ctime) > last_success
                for path in Path(source.canonical_root).glob("*.md")
            ):
                scan_cursor = None
        result = scanner(source, scan_cursor, limit)
        subject_role = str(source.role_identity.get("subject_role", ""))

        new_documents = quarantined = new_observations = 0
        touched_facets: set[str] = set()
        for i, candidate in enumerate(result.candidates):
            checkpoint(conn, f"{checkpoint_prefix}:{source.source_id}:{i}")
            extracted = self._extract_document(conn, source, candidate, subject_role)
            new_documents += extracted["documents_new"]
            quarantined += extracted["documents_quarantined"]
            new_observations += extracted["observations_new"]
            touched_facets.update(extracted["touched_facets"])

        store.set_source_cursor(conn, source.source_id, result.next_cursor)

        # Multi-context synthesis: one fact per (facet, scope), plus deterministic review items.
        contradictions, _reviews_created = self._synthesize_and_review(
            conn, source.subject_id, touched_facets, protect_only_corrected=False
        )
        profile_changed = self._profile_digest(conn, source.subject_id) != before_digest
        if profile_changed:
            touched_facets.update(prior_facets)  # includes facts retired by an empty revision

        generation_id = None
        if create_generation and profile_changed:
            generation_id = self._stamp_generation(
                conn, source.subject_id, touched_facets,
                reason=f"ingest of source {source.source_id}",
                diff_summary={"touched_facets": sorted(touched_facets)},
            )

        return {
            "documents_new": new_documents, "documents_quarantined": quarantined,
            "observations_new": new_observations, "touched_facets": touched_facets,
            "contradictions": contradictions, "generation_id": generation_id,
            "has_more": result.has_more, "adapter_warnings": [w.reason for w in result.warnings],
        }

    def ingest(self, *, source_id: str) -> dict[str, Any]:
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="ingest", actor="operator") as conn:
            source = store.get_source(conn, self.crypto, source_id)
            if source is None:
                raise ServiceError(f"unknown source_id {source_id!r}")
            r = self._ingest_source_within(conn, source, limit=None, create_generation=True)
        return {
            "status": "ingested", "documents_new": r["documents_new"], "documents_quarantined": r["documents_quarantined"],
            "observations_new": r["observations_new"], "facets_touched": sorted(r["touched_facets"]),
            "contradictions": r["contradictions"], "generation_id": r["generation_id"],
            "adapter_warnings": r["adapter_warnings"],
        }

    # ---------------------------------------------------------------------------------
    # Continual curation (§13 M3) — the single scheduled tick, invoked by ONE local-jobs
    # command instance (trigger='scheduled') or by hand (trigger='manual').
    # ---------------------------------------------------------------------------------

    def _curation_learning_summary(self) -> dict[str, Any]:
        """Content-free correction-uptake snapshot (§13 M3 'correction-uptake metrics'): how many
        operator corrections were recorded and how many facts now carry an operator-authoritative
        state (operator feedback is P0 and must be visibly taken up), plus the open review count."""
        operator_subjects = [s for s in store.list_subjects(self.conn) if s.kind == SubjectKind.OPERATOR]
        corrections = corrected = confirmed = 0
        for s in operator_subjects:
            events = store.list_feedback_events(self.conn, self.crypto, s.subject_id)
            corrections += sum(
                1 for e in events
                if e.action in (FeedbackAction.CORRECT, FeedbackAction.BAN, FeedbackAction.CONFIRM)
            )
            facts = store.list_facts(self.conn, self.crypto, s.subject_id)
            corrected += sum(1 for f in facts if f.state == FactState.CORRECTED)
            confirmed += sum(1 for f in facts if f.state == FactState.CONFIRMED)
        open_reviews = len(store.list_review_items(self.conn, self.crypto, subject_id=None, status="OPEN"))
        uptake = round((corrected + confirmed) / corrections, 3) if corrections else None
        return {
            "operator_corrections": corrections, "corrected_facts": corrected,
            "confirmed_facts": confirmed, "open_reviews": open_reviews,
            "correction_uptake_ratio": uptake,
        }

    @staticmethod
    def _env_int(name: str) -> Optional[int]:
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def curate(self, *, trigger: Optional[str] = None, per_source_limit: Optional[int] = None) -> dict[str, Any]:
        from operator_voice.persistence.atomic import exclusive_file
        if self.paths is None:
            return self._curate_unlocked(trigger=trigger, per_source_limit=per_source_limit)
        try:
            with exclusive_file(self.paths.state_dir / ".curation.lock"):
                return self._curate_unlocked(trigger=trigger, per_source_limit=per_source_limit)
        except BlockingIOError as exc:
            raise OperationRefused("curation is already running") from exc

    def _curate_unlocked(self, *, trigger=None, per_source_limit=None):
        """One continual-curation tick (§13 M3). Every active source is ingested in its OWN atomic
        transaction (one source failing or crashing never rolls back another; a re-run never
        double-processes). A scheduled tick while the toolkit is off is an inert no-op, never an
        error. Publication is conditional: LOCAL_ONLY performs NO network I/O; ENCRYPTED_GIT reuses
        the M1 exact-parent encrypted-Git delivery, batched to the end of the tick.

        ``trigger``/``per_source_limit`` fall back to ``$OVT_CURATE_TRIGGER`` /
        ``$OVT_CURATE_PER_SOURCE_LIMIT`` so the single local-jobs command instance can pass its
        configuration via ``--env`` (the local-jobs ``--arg`` passthrough cannot carry ``--``-prefixed
        values). This env fallback is the one explicit, tested lifecycle exception (§13 M3 worklist 4)."""
        trig_str = trigger or os.environ.get("OVT_CURATE_TRIGGER", "manual")
        trig = CurationTrigger(trig_str) if trig_str in (t.value for t in CurationTrigger) else CurationTrigger.MANUAL
        if per_source_limit is None:
            per_source_limit = self._env_int("OVT_CURATE_PER_SOURCE_LIMIT")
        actor = "scheduler" if trig == CurationTrigger.SCHEDULED else "operator"
        run_id = new_id("crun")

        # A scheduled/any tick while OFF is inert: record one content-free SKIPPED_OFF row (via a
        # plain transaction, since staged_operation refuses while off) and return without error.
        if is_off(self.conn):
            run = CurationRun(run_id=run_id, trigger=trig, status=CurationRunStatus.SKIPPED_OFF, finished_at=now_ts())
            with transaction(self.conn):
                store.insert_curation_run(self.conn, run)
            return {"status": "skipped_off", "run_id": run_id, "reason": "toolkit is off"}

        started = now_ts()
        # Stale-operation recovery FIRST (§13 M3 worklist 3): reclaim any long-abandoned RUNNING row
        # from a prior crash/kill/long-sleep. Pure bookkeeping — the committed per-source work is
        # already durable and idempotent.
        with transaction(self.conn):
            recovered = store.reclaim_stale_curation_runs(self.conn, exclude_run_id=run_id)

        # Catch-up gap since the last completed pass (downtime/sleep). Informational; the incremental
        # per-source cursors do the actual catch-up, bounded by per_source_limit across ticks.
        last_completed = store.get_last_completed_curation_run(self.conn)
        catch_up_gap = (started - last_completed.finished_at) if (last_completed and last_completed.finished_at) else None

        run = CurationRun(
            run_id=run_id, trigger=trig, status=CurationRunStatus.RUNNING, started_at=started,
            recovered_runs=recovered, catch_up_gap_seconds=catch_up_gap,
        )
        # Durable RUNNING row BEFORE any source work, so a crash mid-tick leaves a recoverable trace.
        with transaction(self.conn):
            store.insert_curation_run(self.conn, run)

        sources = store.list_active_sources(self.conn, self.crypto)
        retired_sources = sum(s.adapter_type in RETIRED_ADAPTER_TYPES for s in sources)
        sources = [s for s in sources if s.adapter_type not in RETIRED_ADAPTER_TYPES]
        before_profiles = {s.subject_id: self._profile_digest(self.conn, s.subject_id) for s in sources}
        run.sources_total = len(sources)
        facets_by_subject: dict[str, set[str]] = {}
        contradictions_total = 0
        cancelled = False

        for source in sources:
            if is_off(self.conn):  # off flipped between sources → stop cleanly at a boundary
                cancelled = True
                break
            try:
                with staged_operation(
                    self.conn, operation_id=new_id("op"), operation_type="curate.source", actor=actor,
                ) as conn:
                    r = self._ingest_source_within(
                        conn, source, limit=per_source_limit, create_generation=False, checkpoint_prefix="curate",
                    )
                    st = store.get_source_curation_state(conn, source.source_id) or SourceCurationState(source_id=source.source_id)
                    st.last_curated_at = now_ts()
                    st.last_success_at = now_ts()
                    st.consecutive_failures = 0
                    st.last_error_class = None
                    st.last_run_id = run_id
                    st.pending_continuation = bool(r["has_more"])
                    store.upsert_source_curation_state(conn, st)
                run.sources_processed += 1
                run.documents_new += r["documents_new"]
                run.observations_new += r["observations_new"]
                contradictions_total += len(r["contradictions"])
                if r["touched_facets"]:
                    facets_by_subject.setdefault(source.subject_id, set()).update(r["touched_facets"])
                if r["has_more"]:
                    run.pending_continuation = True
            except (OperationCancelled, OperationRefused):
                cancelled = True
                break
            except Exception as exc:  # one source failing must never abort the sweep (§13 M3)
                run.sources_failed += 1
                with transaction(self.conn):
                    st = store.get_source_curation_state(self.conn, source.source_id) or SourceCurationState(source_id=source.source_id)
                    st.last_curated_at = now_ts()
                    st.consecutive_failures += 1
                    st.last_error_class = type(exc).__name__
                    st.last_run_id = run_id
                    store.upsert_source_curation_state(self.conn, st)
                continue

        # One generation per subject that changed this tick (stamped after the per-source ingests).
        generation_ids: list[str] = []
        if not cancelled:
            for subject_id, before_digest in before_profiles.items():
                current_digest = self._profile_digest(self.conn, subject_id)
                previous = store.get_latest_generation(self.conn, subject_id)
                if current_digest == before_digest and (previous is None or previous.content_digest == current_digest):
                    continue
                facets = facets_by_subject.get(subject_id, set())
                with staged_operation(
                    self.conn, operation_id=new_id("op"), operation_type="curate.generation", actor=actor,
                ) as conn:
                    generation_ids.append(self._stamp_generation(
                        conn, subject_id, facets,
                        reason=f"continual curation {run_id}",
                        diff_summary={"touched_facets": sorted(facets)},
                    ))

        # Conditional, batched publication (§13 M3 worklist 3). LOCAL_ONLY performs NO network I/O:
        # we never even enter the publish path. ENCRYPTED_GIT reuses M1 exact-parent delivery.
        published = False
        publish_status: Optional[str] = None
        if cancelled:
            publish_status = "skipped_cancelled"
        else:
            cfg = store.get_backend_config(self.conn)
            sync = store.get_sync_state(self.conn)
            # A crash after committed source learning, or before publication establishes a
            # pending PR, must still retry on the next unchanged pass.
            latest = [store.get_latest_generation(self.conn, sid) for sid in before_profiles]
            published_generation = store.get_generation(self.conn, sync.remote_generation_id) if sync.remote_generation_id else None
            published_digest = published_generation.diff_summary.get("publish_digest") if published_generation else None
            unpublished = any(g and (not published_digest or g.diff_summary.get("publish_digest") != published_digest)
                              for g in latest)
            should_publish = sync.publish_status == SyncStatus.PENDING_PUBLICATION or unpublished
            if sync.publish_status == SyncStatus.CONFLICT:
                publish_status = SyncStatus.CONFLICT.value
            elif not should_publish or (cfg.mode == BackendMode.LOCAL_ONLY and not generation_ids):
                publish_status = "skipped_no_changes"
            elif cfg.mode == BackendMode.ENCRYPTED_GIT and cfg.active:
                try:
                    pub = self.profile_publish(pr_wait_seconds=0)
                    publish_status = pub.get("status")
                    published = publish_status == SyncStatus.PUBLISHED.value
                except OperationRefused:
                    publish_status = "skipped_off"  # off flipped between the sweep and publish
                except Exception as exc:
                    # Publication is a best-effort ENCRYPTED_GIT replica of already-durable local
                    # work. A transient push/network error must NOT crash the tick or leave a
                    # dangling RUNNING row — the ingested generations are committed and profile_publish
                    # is exact-parent idempotent, so the next tick re-publishes. Record the failure
                    # class (content-free) and finalize the run normally.
                    publish_status = f"failed:{type(exc).__name__}"
                    published = False
            else:
                publish_status = "skipped_local_only"  # default posture: no private Git, no network

        run.finished_at = now_ts()
        run.contradictions = contradictions_total
        run.facets_touched = sum(len(f) for f in facets_by_subject.values())
        run.published = published
        run.publish_status = publish_status
        run.learning_summary = self._curation_learning_summary()
        if cancelled:
            run.status = CurationRunStatus.CANCELLED
        elif run.sources_total == 0:
            run.status = CurationRunStatus.NOOP
        else:
            run.status = CurationRunStatus.COMPLETED
        with transaction(self.conn):
            store.update_curation_run(self.conn, run)

        return {
            "status": run.status.value, "run_id": run_id, "trigger": trig.value,
            "sources_total": run.sources_total, "sources_processed": run.sources_processed,
            "sources_failed": run.sources_failed, "documents_new": run.documents_new,
            "retired_sources": retired_sources,
            "observations_new": run.observations_new, "facets_touched": run.facets_touched,
            "contradictions": contradictions_total, "recovered_runs": recovered,
            "catch_up_gap_seconds": catch_up_gap, "pending_continuation": run.pending_continuation,
            "generation_ids": generation_ids, "published": published, "publish_status": publish_status,
            "learning": run.learning_summary,
        }

    def curation_status(self, *, limit: int = 10) -> dict[str, Any]:
        runs = store.list_curation_runs(self.conn, limit=limit)
        states_by_id = {s.source_id: s for s in store.list_source_curation_states(self.conn)}
        last_completed = store.get_last_completed_curation_run(self.conn)
        sources: list[dict[str, Any]] = []
        for src in store.list_sources(self.conn, self.crypto):
            st = states_by_id.get(src.source_id)
            sources.append(
                {
                    "source_id": src.source_id,
                    "adapter_type": src.adapter_type.value,
                    "active": src.active,
                    "paused": src.paused,
                    "watermark": src.cursor,
                    "last_curated_at": st.last_curated_at if st else None,
                    "last_success_at": st.last_success_at if st else None,
                    "consecutive_failures": st.consecutive_failures if st else 0,
                    "last_error_class": st.last_error_class if st else None,
                    "pending_continuation": st.pending_continuation if st else False,
                }
            )
        return {
            "last_completed_run_id": last_completed.run_id if last_completed else None,
            "runs": [
                {
                    "run_id": r.run_id, "trigger": r.trigger.value, "status": r.status.value,
                    "started_at": r.started_at, "finished_at": r.finished_at,
                    "sources_total": r.sources_total, "sources_processed": r.sources_processed,
                    "sources_failed": r.sources_failed, "documents_new": r.documents_new,
                    "observations_new": r.observations_new, "facets_touched": r.facets_touched,
                    "contradictions": r.contradictions, "catch_up_gap_seconds": r.catch_up_gap_seconds,
                    "pending_continuation": r.pending_continuation, "recovered_runs": r.recovered_runs,
                    "published": r.published, "publish_status": r.publish_status,
                }
                for r in runs
            ],
            "sources": sources,
            "learning": self._curation_learning_summary(),
        }

    def learning_status(self) -> dict[str, Any]:
        summary = self._curation_learning_summary()
        return {
            "learning": summary,
            "note": (
                "operator feedback is P0 and outranks inference; corrected/confirmed facts are the "
                "operator's own words and are never overwritten by later passive curation"
            ),
        }

    @staticmethod
    def _resolve_local_jobs_sh() -> str:
        """Best-effort, read-only resolution of the operator's local-jobs skill entrypoint so the
        printed command is copy-pasteable. Never required — falls back to the bare script name."""
        candidates = [
            Path.home() / ".claude/skills/local-jobs/scripts/local-jobs.sh",
            Path.home() / ".cursor/skills/local-jobs/scripts/local-jobs.sh",
        ]
        for c in candidates:
            try:
                if c.exists():
                    return str(c)
            except OSError:
                continue
        return "local-jobs.sh"

    def schedule_plan(self, *, interval_seconds: int = 86400, per_source_limit: Optional[int] = None) -> dict[str, Any]:
        """§13 M3 worklist 2 — render the single-instance local-jobs registration for passive
        curation. Pure/read-only: OVT never installs a scheduler itself; local-jobs is the only
        scheduler. The instance is inert until a source is enrolled (a tick with no active source is
        a safe NOOP) and is cleanly removable with the printed remove command."""
        from operator_voice.runtime import scheduler

        plan = scheduler.plan_schedule(interval_seconds=interval_seconds, per_source_limit=per_source_limit)
        ljs = self._resolve_local_jobs_sh()
        return {
            "scheduler": "local-jobs",
            "execution_mode": "on_demand",
            "job_id": plan.job_id,
            "interval_seconds": plan.interval_seconds,
            "add_command": scheduler.render_command(plan.add_argv, local_jobs_sh=ljs),
            "update_command": scheduler.render_command(plan.update_argv, local_jobs_sh=ljs),
            "remove_command": scheduler.render_command(plan.remove_argv, local_jobs_sh=ljs),
            "run_now_command": scheduler.render_command(plan.run_now_argv, local_jobs_sh=ljs),
            "warnings": plan.warnings,
            "note": (
                "The connected host owns daily refresh. This local-jobs entry is on-demand only; "
                "setup/install/repair migrate the old timer while preserving its enabled setting. "
                "Enroll and verify the host cycle through the daily-maintenance runbook. "
                "LOCAL_ONLY performs no replica network I/O."
            ),
        }

    def feedback_add(self, *, subject_id: str, utterance: str, target_fact_id: Optional[str] = None) -> dict[str, Any]:
        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        classification = feedback_kernel.classify_feedback(utterance)
        if classification.action is None:
            return {"status": "clarifying_question", "question": classification.clarifying_question}
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="feedback.add", actor="operator") as conn:
            event = FeedbackEvent(
                feedback_id=new_id("fb"), subject_id=subject_id, utterance_digest=_digest(utterance),
                action=classification.action, reason=utterance, target_fact_id=target_fact_id,
                new_value=classification.extracted_value,
            )
            store.insert_feedback_event(conn, self.crypto, event)
            applied = False
            if target_fact_id and classification.action in (FeedbackAction.CORRECT, FeedbackAction.BAN, FeedbackAction.CONFIRM):
                fact = store.get_fact(conn, self.crypto, target_fact_id)
                if fact is not None:
                    new_state = FactState.CONFIRMED if classification.action == FeedbackAction.CONFIRM else FactState.CORRECTED
                    new_value = classification.extracted_value if classification.extracted_value is not None else fact.value
                    store.upsert_fact(conn, self.crypto, replace(fact, value=new_value, state=new_state, valid_from=now_ts()))
                    applied = True
        return {"status": "recorded", "action": classification.action.value, "applied_to_fact": applied}

    def fact_correct(self, *, subject_id: str, facet: str, new_value: Any, reason: str = "operator correction") -> dict[str, Any]:
        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="fact.correct", actor="operator") as conn:
            existing = store.get_fact_by_facet_scope(conn, self.crypto, subject_id, facet, GENERATION_DOC_SCOPE.key())
            fact_id = existing.fact_id if existing else new_id("fact")
            fact = ProfileFact(
                fact_id=fact_id, subject_id=subject_id, facet=facet, value=new_value, scope=GENERATION_DOC_SCOPE,
                state=FactState.CORRECTED, confidence=1.0,
                document_count=existing.document_count if existing else 0,
                source_count=existing.source_count if existing else 0,
                provenance_ids=existing.provenance_ids if existing else [], valid_from=now_ts(),
            )
            store.upsert_fact(conn, self.crypto, fact)
            store.insert_feedback_event(conn, self.crypto, FeedbackEvent(
                feedback_id=new_id("fb"), subject_id=subject_id, utterance_digest=_digest(reason),
                action=FeedbackAction.CORRECT, reason=reason, target_facet=facet, target_fact_id=fact_id,
                new_value=new_value,
            ))
        return {"status": "corrected", "fact_id": fact_id, "facet": facet}

    def fact_deprecate(self, *, fact_id: str, reason: str = "") -> dict[str, Any]:
        if store.get_fact(self.conn, self.crypto, fact_id) is None:
            raise ServiceError(f"unknown fact_id {fact_id!r}")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="fact.deprecate", actor="operator") as conn:
            store.deprecate_fact(conn, fact_id)
        return {"status": "deprecated", "fact_id": fact_id}

    def review_resolve(self, *, review_id: str, status: str = "RESOLVED", resolution: str = "") -> dict[str, Any]:
        if status not in (ReviewStatus.RESOLVED.value, ReviewStatus.DISMISSED.value):
            raise ServiceError(f"review.resolve status must be RESOLVED or DISMISSED, got {status!r}")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="review.resolve", actor="operator") as conn:
            changed = store.resolve_review_item(conn, review_id, status, resolution)
            if not changed:
                raise ServiceError(f"no OPEN review item with id {review_id!r}")
        return {"status": "resolved", "review_id": review_id, "resolution_status": status}

    def gateway_configure(
        self, *, provider: Optional[str] = None, model: Optional[str] = None,
        allowed_data_classes: Optional[list[str]] = None, enable_operator_egress: bool = False,
        enable_external_egress: bool = False, timeout_ms: int = 20000,
    ) -> dict[str, Any]:
        """Set the model-gateway policy (§13 M2 worklist 4). BOTH egress switches are explicit and
        default OFF here: ``enable_external_egress`` is a SEPARATE switch — enabling operator egress
        never implies EXTERNAL egress, and EXTERNAL egress requires its own explicit true. Raw and
        quarantined are rejected as allowed data classes (never eligible). Rebuilds the live
        gateway so the change takes effect immediately."""
        classes = list(allowed_data_classes or [])
        illegal = sorted(set(classes) & {"raw", "quarantined"})
        if illegal:
            raise ServiceError(f"data classes {illegal} are never eligible for egress and cannot be allowlisted")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="gateway.configure", actor="operator") as conn:
            cfg = GatewayConfig(
                operator_egress_enabled=bool(enable_operator_egress),
                external_egress_enabled=bool(enable_external_egress),
                provider=provider, model=model, allowed_data_classes=classes,
                timeout_ms=int(timeout_ms), updated_at=now_ts(),
            )
            store.set_gateway_config(conn, cfg)
        self._refresh_gateway()
        return self.gateway_status()

    def profile_publish(self, *, pr_wait_seconds: Optional[int] = None) -> dict[str, Any]:
        operation_id = new_id("op")
        cfg = store.get_backend_config(self.conn)
        if cfg.mode != BackendMode.ENCRYPTED_GIT or not cfg.active:
            audit.record(
                self.conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                consumer=None, result="skipped:local_only",
            )
            return {"status": "skipped", "reason": "backend is LOCAL_ONLY; nothing to publish"}
        if self.paths is None or self.profile_pack_crypto is None:
            raise ServiceError("profile.publish requires configured paths + profile_pack_crypto")

        if is_off(self.conn):
            raise OperationRefused("operation 'profile.publish' refused: toolkit is off")

        def _pr_wait_checkpoint() -> None:
            checkpoint(self.conn, "profile.publish:pr_wait")

        try:
            with transaction(self.conn) as conn:
                subjects = [s for s in store.list_subjects(conn) if s.kind == SubjectKind.OPERATOR]
                if not subjects:
                    audit.record(
                        conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                        consumer=None, result="skipped:no_subject",
                    )
                    return {"status": "skipped", "reason": "no operator subject registered"}
                subject = subjects[0]
                facts = store.list_facts(conn, self.crypto, subject.subject_id)
                feedback_events = store.list_feedback_events(conn, self.crypto, subject.subject_id)
                generation = store.get_latest_generation(conn, subject.subject_id)
                if generation is None:
                    audit.record(
                        conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                        consumer=None, result="skipped:no_generation",
                    )
                    return {"status": "skipped", "reason": "no generation to publish yet"}

                key_generation_id, dek = store.ensure_active_key_generation(
                    conn, self.profile_pack_crypto, store.PROFILE_PACK_KEY_PURPOSE,
                )
                objects = profile_pack.build_portable_objects(
                    facts=facts, feedback_events=feedback_events, generation=generation,
                )
                encrypted = profile_pack.encrypt_objects(self.profile_pack_crypto, dek, objects)

                clone_dir = self.paths.profile_pack_clone_dir
                remote_url = cfg.remote_reference_token
                profile_pack.ensure_clone(clone_dir, remote_url)
                profile_pack.sync_clone_to_remote(clone_dir)
                try:
                    remote_manifest = profile_pack.read_manifest(clone_dir)
                except profile_pack.ProfilePackError as exc:
                    sync_state = replace(store.get_sync_state(conn), publish_status=SyncStatus.CONFLICT)
                    store.set_sync_state(conn, sync_state)
                    audit.record(
                        conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                        consumer=None, result="success",
                    )
                    return {
                        "status": SyncStatus.CONFLICT.value,
                        "detail": str(exc),
                        "generation_id": generation.generation_id,
                    }
                if remote_manifest is not None:
                    remote_gen_id = remote_manifest["generation_id"]

                    def _parent_of(gen_id: str) -> Optional[str]:
                        gen = store.get_generation(conn, gen_id)
                        return gen.parent_generation_id if gen else None

                    if not profile_pack.local_advances_remote(
                        local_generation_id=generation.generation_id,
                        remote_generation_id=remote_gen_id,
                        parent_of=_parent_of,
                    ):
                        sync_state = replace(store.get_sync_state(conn), publish_status=SyncStatus.CONFLICT)
                        store.set_sync_state(conn, sync_state)
                        audit.record(
                            conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                            consumer=None, result="success",
                        )
                        return {
                            "status": SyncStatus.CONFLICT.value,
                            "detail": (
                                f"remote profile generation {remote_gen_id} is ahead of or divergent from "
                                f"local {generation.generation_id}; reconcile before publishing"
                            ),
                            "generation_id": generation.generation_id,
                        }
                expected_parent = profile_pack.current_remote_head(clone_dir)
                manifest = profile_pack.build_manifest(
                    generation=generation,
                    objects=objects,
                    key_generation_id=key_generation_id,
                    git_parent_sha=expected_parent,
                )
                pending_sync = store.get_sync_state(conn).publish_status
                pending_generation_id = store.get_sync_state(conn).local_generation_id

            outcome: profile_pack.PublishOutcome | None = None
            preserve_pending_on_conflict = False
            if pending_sync == SyncStatus.PENDING_PUBLICATION and pending_generation_id:
                resumed = profile_pack.try_finalize_pending_publication(
                    clone_dir,
                    generation_id=pending_generation_id,
                    pr_wait_seconds=pr_wait_seconds,
                    cancel_check=_pr_wait_checkpoint,
                )
                if pending_generation_id != generation.generation_id:
                    if resumed is not None and resumed.status == SyncStatus.PUBLISHED:
                        with transaction(self.conn) as conn:
                            current_sync = store.get_sync_state(conn)
                            store.set_sync_state(conn, replace(
                                current_sync,
                                remote_generation_id=pending_generation_id,
                                exact_parent_sha=resumed.pushed_sha,
                                local_generation_id=generation.generation_id,
                                publish_status=SyncStatus.PENDING_PUBLICATION,
                            ))
                        profile_pack.sync_clone_to_remote(clone_dir)
                        expected_parent = profile_pack.current_remote_head(clone_dir)
                        manifest = profile_pack.build_manifest(
                            generation=generation,
                            objects=objects,
                            key_generation_id=key_generation_id,
                            git_parent_sha=expected_parent,
                        )
                    else:
                        detail = (
                            resumed.detail
                            if resumed is not None
                            else f"waiting for pending publish PR for {pending_generation_id}"
                        )
                        status = (
                            resumed.status
                            if resumed is not None
                            else SyncStatus.PENDING_PUBLICATION
                        )
                        with transaction(self.conn) as conn:
                            current_sync = store.get_sync_state(conn)
                            store.set_sync_state(conn, replace(
                                current_sync,
                                local_generation_id=pending_generation_id,
                                publish_status=status,
                            ))
                        audit.record(
                            self.conn, operation_id=operation_id, operation_type="profile.publish",
                            actor="operator", consumer=None, result="success",
                        )
                        return {
                            "status": status.value,
                            "detail": detail,
                            "generation_id": pending_generation_id,
                            **({"pr_url": resumed.pr_url} if resumed and resumed.pr_url else {}),
                            **({"pr_number": resumed.pr_number} if resumed and resumed.pr_number else {}),
                        }
                elif resumed is not None:
                    if resumed.status in (SyncStatus.PUBLISHED, SyncStatus.PENDING_PUBLICATION):
                        outcome = resumed
                elif pending_generation_id == generation.generation_id:
                    preserve_pending_on_conflict = True

            if outcome is None:
                profile_pack.write_pack(
                    repo_path=clone_dir, encrypted_objects=encrypted, manifest=manifest,
                    object_types={o.digest: o.object_type for o in objects},
                )
                outcome = profile_pack.commit_and_push(
                    clone_dir,
                    commit_message=f"publish generation {generation.generation_id}",
                    expected_parent_sha=expected_parent,
                    generation_id=generation.generation_id,
                    pr_wait_seconds=pr_wait_seconds,
                    cancel_check=_pr_wait_checkpoint,
                )

            final_publish_status = outcome.status
            with transaction(self.conn) as conn:
                published = outcome.status == SyncStatus.PUBLISHED
                current_sync = store.get_sync_state(conn)
                if (
                    preserve_pending_on_conflict
                    and final_publish_status == SyncStatus.CONFLICT
                    and "divergent" not in outcome.detail.lower()
                ):
                    # Same-generation resume after a timed-out PR: do not erase in-flight PR state
                    # when the retry push reports a transient CAS conflict.
                    final_publish_status = SyncStatus.PENDING_PUBLICATION
                sync_state = replace(
                    current_sync,
                    local_generation_id=(
                        generation.generation_id
                        if published or final_publish_status == SyncStatus.PENDING_PUBLICATION
                        else current_sync.local_generation_id
                    ),
                    remote_generation_id=generation.generation_id if published else current_sync.remote_generation_id,
                    exact_parent_sha=(
                        outcome.pushed_sha if published and outcome.pushed_sha is not None else current_sync.exact_parent_sha
                    ),
                    publish_status=final_publish_status,
                )
                store.set_sync_state(conn, sync_state)

            audit.record(
                self.conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                consumer=None, result="success",
            )
        except OperationCancelled:
            audit.record(
                self.conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                consumer=None, result="cancelled",
            )
            raise
        except Exception as exc:
            audit.record(
                self.conn, operation_id=operation_id, operation_type="profile.publish", actor="operator",
                consumer=None, result=f"error:{type(exc).__name__}",
            )
            raise

        result: dict[str, Any] = {
            "status": final_publish_status.value,
            "detail": outcome.detail,
            "generation_id": generation.generation_id,
        }
        if outcome.pr_url is not None:
            result["pr_url"] = outcome.pr_url
        if outcome.pr_number is not None:
            result["pr_number"] = outcome.pr_number
        return result

    def profile_pull(self) -> dict[str, Any]:
        cfg = store.get_backend_config(self.conn)
        if cfg.mode != BackendMode.ENCRYPTED_GIT or not cfg.active or self.paths is None:
            return {"status": "skipped", "reason": "backend is LOCAL_ONLY"}
        profile_pack.ensure_clone(self.paths.profile_pack_clone_dir, cfg.remote_reference_token)
        head = profile_pack.current_remote_head(self.paths.profile_pack_clone_dir)
        state = store.get_sync_state(self.conn)
        if (state.publish_status == SyncStatus.PENDING_PUBLICATION and state.local_generation_id
                and head and state.exact_parent_sha != head):
            # A governed publish can merge between host wakes. Reuse the existing
            # acknowledgement path before treating our own merge as divergence.
            # This never creates a commit/PR or waits for an open PR to merge.
            resumed = profile_pack.try_finalize_pending_publication(
                self.paths.profile_pack_clone_dir, generation_id=state.local_generation_id,
                pr_wait_seconds=0,
            )
            head = profile_pack.current_remote_head(self.paths.profile_pack_clone_dir)
            if resumed is not None and resumed.status == SyncStatus.PUBLISHED and resumed.pushed_sha == head:
                state = replace(state, remote_generation_id=state.local_generation_id,
                                exact_parent_sha=head, publish_status=SyncStatus.PUBLISHED)
                with transaction(self.conn) as conn:
                    store.set_sync_state(conn, state)
        if state.exact_parent_sha and head and state.exact_parent_sha != head:
            with staged_operation(self.conn, operation_id=new_id("op"), operation_type="profile.pull", actor="operator") as conn:
                store.set_sync_state(conn, replace(state, publish_status=SyncStatus.CONFLICT))
            return {"status": "conflict", "detail": "remote head diverged from last known local publish"}
        return {"status": "up_to_date" if state.exact_parent_sha == head else "fetched", "remote_head": head}

    def profile_restore(self) -> dict[str, Any]:
        cfg = store.get_backend_config(self.conn)
        if cfg.mode != BackendMode.ENCRYPTED_GIT or self.paths is None:
            return {"status": "skipped", "reason": "no ENCRYPTED_GIT backend configured"}
        clone_dir = self.paths.profile_pack_clone_dir
        profile_pack.ensure_clone(clone_dir, cfg.remote_reference_token)
        profile_pack.sync_clone_to_remote(clone_dir)
        try:
            manifest_payload = profile_pack.read_manifest(clone_dir)
        except profile_pack.ProfilePackError as exc:
            return {"status": "error", "detail": str(exc)}
        if manifest_payload is None:
            return {"status": "empty", "detail": "remote profile pack has no manifest yet"}
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="profile.restore", actor="operator") as conn:
            store.set_sync_state(conn, replace(
                store.get_sync_state(conn), remote_generation_id=manifest_payload["generation_id"],
                publish_status=SyncStatus.RESTORED,
            ))
        return {"status": "restored", "generation_id": manifest_payload["generation_id"]}

    def profile_reconcile(self) -> dict[str, Any]:
        """Deterministic typed reconciliation of the ENCRYPTED_GIT profile replica across machines
        (§13 M4 worklist 5, D18). Read-mostly: it fetches the remote head, decrypts the remote
        profile-fact objects, and merges DISJOINT typed changes into the local operator profile;
        a conflicting correction or an identity change is NOT auto-merged — it becomes an operator
        review item and is recorded in the sync conflict set. It never pushes and never force-writes
        a shared ref (the no-force-push exact-parent CAS lives in ``profile.publish``); reconcile is
        exactly how an operator resolves a divergent head before publishing on top of it.
        LOCAL_ONLY operators are unaffected (skipped)."""
        cfg = store.get_backend_config(self.conn)
        if cfg.mode != BackendMode.ENCRYPTED_GIT or not cfg.active or self.paths is None or self.profile_pack_crypto is None:
            return {"status": "skipped", "reason": "backend is LOCAL_ONLY; nothing to reconcile"}
        clone_dir = self.paths.profile_pack_clone_dir
        profile_pack.ensure_clone(clone_dir, cfg.remote_reference_token)
        profile_pack.sync_clone_to_remote(clone_dir)
        remote_head = profile_pack.current_remote_head(clone_dir)
        try:
            manifest_payload = profile_pack.read_manifest(clone_dir)
        except profile_pack.ProfilePackError as exc:
            return {"status": "error", "detail": str(exc)}
        if manifest_payload is None:
            return {"status": "empty", "detail": "remote profile pack has no manifest yet"}
        key_generation_id = manifest_payload.get("key_generation_id")
        try:
            dek = store.dek_for_generation(self.conn, self.profile_pack_crypto, key_generation_id)
        except store.StoreError:
            return {
                "status": "key_unavailable",
                "detail": (
                    "the remote pack was published under a profile-pack key this machine does not "
                    "hold. Import the profile with portability.import (which carries the profile-pack "
                    "keys) before reconciling."
                ),
                "remote_generation_id": manifest_payload.get("generation_id"),
            }
        remote_views, remote_payloads = self._load_remote_profile_fact_views(clone_dir, manifest_payload, dek)

        operators = [s for s in store.list_subjects(self.conn) if s.kind == SubjectKind.OPERATOR]
        if not operators:
            return {"status": "skipped", "reason": "no operator subject registered"}
        subject = operators[0]
        local_facts = store.list_facts(self.conn, self.crypto, subject.subject_id)
        local_views = [
            FactView(facet=f.facet, scope_key=f.scope.key(), value=f.value, state=f.state,
                     confidence=f.confidence, fact_id=f.fact_id)
            for f in local_facts
        ]
        result = reconcile.reconcile_facts(local_views, remote_views)

        adopted_facets: list[str] = []
        conflict_records: list[dict[str, Any]] = []
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="profile.reconcile", actor="operator") as conn:
            for view in result.adopt:
                payload = remote_payloads[(view.facet, view.scope_key)]
                scope = ContextScope.from_dict(payload["scope"])
                ci = payload.get("confidence_interval")
                store.upsert_fact(conn, self.crypto, ProfileFact(
                    fact_id=new_id("fact"), subject_id=subject.subject_id, facet=view.facet,
                    value=view.value, scope=scope, state=view.state, confidence=view.confidence,
                    confidence_interval=tuple(ci) if ci else None,
                    document_count=int(payload.get("document_count", 0)),
                    source_count=int(payload.get("source_count", 0)),
                    provenance_ids=[], synthesis_version=payload.get("synthesis_version", "v1"),
                ))
                adopted_facets.append(view.facet)
            for c in result.conflicts:
                scope = ContextScope.from_dict(remote_payloads[(c.facet, c.scope_key)]["scope"])
                if not store.has_open_review(conn, subject.subject_id, c.facet, c.scope_key, ReviewReason.CONTRADICTION.value):
                    store.insert_review_item(conn, self.crypto, ReviewItem(
                        review_id=new_id("review"), subject_id=subject.subject_id,
                        reason=ReviewReason.CONTRADICTION,
                        detail=(f"multi-machine reconciliation: {c.reason} on '{c.facet}' "
                                f"(local={c.local_state}, remote={c.remote_state}). Resolve before it is trusted."),
                        facet=c.facet, scope=scope,
                    ))
                conflict_records.append(c.as_dict())
            reconciled_generation_id: Optional[str] = None
            if not conflict_records:
                remote_gen_id = manifest_payload["generation_id"]
                local_facts_after = store.list_facts(conn, self.crypto, subject.subject_id)
                reconciled_generation_id = self._stamp_generation(
                    conn, subject.subject_id, {f.facet for f in local_facts_after},
                    reason="profile.reconcile",
                    diff_summary={"reconciled_from": remote_gen_id, "adopted_facets": sorted(set(adopted_facets))},
                    parent_generation_id=remote_gen_id,
                )
            current_sync = store.get_sync_state(conn)
            store.set_sync_state(conn, replace(
                current_sync,
                local_generation_id=reconciled_generation_id or current_sync.local_generation_id,
                remote_generation_id=manifest_payload.get("generation_id"),
                exact_parent_sha=remote_head,
                publish_status=SyncStatus.CONFLICT if conflict_records else SyncStatus.RESTORED,
                conflict_set=conflict_records,
            ))
        return {
            "status": "conflict" if conflict_records else "reconciled",
            "merged_count": result.merged_count,
            "conflict_count": result.conflict_count,
            "unchanged": result.unchanged,
            "adopted_facets": sorted(set(adopted_facets)),
            "conflicts": conflict_records,
            "remote_generation_id": manifest_payload.get("generation_id"),
        }

    def _load_remote_profile_fact_views(
        self, clone_dir: Path, manifest_payload: dict[str, Any], dek: bytes
    ) -> tuple[list[FactView], dict[tuple[str, str], dict[str, Any]]]:
        """Decrypt the remote pack's ``profile_fact`` objects into reconcile FactViews + a
        ``(facet, scope_key) -> payload`` map (so an adopted view can be rebuilt into a full local
        fact). Ciphertext addressing/decryption reuses the publisher's own contract."""
        views: list[FactView] = []
        payloads: dict[tuple[str, str], dict[str, Any]] = {}
        for ref in manifest_payload.get("object_refs", []):
            if ref.get("object_type") != "profile_fact":
                continue
            digest = ref["digest"]
            obj_path = clone_dir / "profile" / "objects" / digest[:2] / f"{digest}.enc"
            if not obj_path.exists():
                continue
            payload = profile_pack.decrypt_object(dek, obj_path.read_bytes(), "profile_fact")
            scope_key = ContextScope.from_dict(payload["scope"]).key()
            view = FactView(
                facet=payload["facet"], scope_key=scope_key, value=payload["value"],
                state=FactState(payload["state"]), confidence=float(payload.get("confidence", 0.0)),
            )
            views.append(view)
            payloads[(view.facet, scope_key)] = payload
        return views, payloads

    def portability_export(
        self, *, destination: str, passphrase: str, subject_id: Optional[str] = None,
        challenge_literal: Optional[str] = None,
    ) -> dict[str, Any]:
        """Deterministic, passphrase-encrypted export of the profile for cross-machine portability
        (§13 M4 worklist 4). Sensitive export → requires a confirmation challenge. The archive is
        scrypt+AES-256-GCM sealed under the operator passphrase and carries the subjects, facts,
        corrections, aliases, generations, and the profile-pack key material a second machine needs
        to decrypt + reconcile the ENCRYPTED_GIT pack. The passphrase is never stored."""
        try:
            self._require_confirmation_or_raise("portability.export", [destination], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        if not passphrase or len(passphrase) < 8:
            raise ServiceError("portability.export requires a passphrase of at least 8 characters")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="portability.export", actor="operator") as conn:
            subjects = store.list_subjects(conn)
            if subject_id:
                subjects = [s for s in subjects if s.subject_id == subject_id]
                if not subjects:
                    raise _unknown_subject_error(subject_id)
            payload = self._build_portable_payload(conn, subjects)
            archive = portability.seal(passphrase, payload)
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(json.dumps(archive.to_dict(), indent=2, sort_keys=True) + "\n")
        return {
            "status": "exported", "destination": destination,
            "subjects": len(payload["subjects"]), "facts": len(payload["facts"]),
            "profile_pack_keys": len(payload["profile_pack_keys"]),
            "note": ("Encrypted with your passphrase (scrypt + AES-256-GCM). The passphrase is NOT "
                     "stored anywhere — keep it safe; without it the file cannot be opened."),
        }

    def _build_portable_payload(self, conn: sqlite3.Connection, subjects: list[SubjectRegistration]) -> dict[str, Any]:
        subj_out: list[dict[str, Any]] = []
        facts_out: list[dict[str, Any]] = []
        feedback_out: list[dict[str, Any]] = []
        aliases_out: list[dict[str, Any]] = []
        generations_out: list[dict[str, Any]] = []
        for s in subjects:
            subj_out.append(_subject_to_portable(s))
            for f in store.list_facts(conn, self.crypto, s.subject_id):
                facts_out.append(_fact_to_portable(f))
            for e in store.list_feedback_events(conn, self.crypto, s.subject_id):
                feedback_out.append(_feedback_to_portable(e))
            for a in store.list_subject_aliases(conn, self.crypto, s.subject_id):
                aliases_out.append(_alias_to_portable(a))
            for g in store.list_generations(conn, s.subject_id):
                generations_out.append(_generation_to_portable(g))
        keys_out: list[dict[str, Any]] = []
        if self.profile_pack_crypto is not None:
            for gen_id, created_at in store.list_key_generations(conn, store.PROFILE_PACK_KEY_PURPOSE):
                dek = store.dek_for_generation(conn, self.profile_pack_crypto, gen_id)
                keys_out.append({
                    "generation_id": gen_id, "dek_b64": base64.b64encode(dek).decode("ascii"),
                    "created_at": created_at, "purpose": store.PROFILE_PACK_KEY_PURPOSE,
                })
        return {
            "subjects": subj_out, "facts": facts_out, "feedback": feedback_out,
            "aliases": aliases_out, "generations": generations_out, "profile_pack_keys": keys_out,
        }

    def portability_import(self, *, source: str, passphrase: str) -> dict[str, Any]:
        """Import a passphrase-encrypted portable profile onto this machine (§13 M4 worklist 4).
        Additive + protective: operator-authoritative local facts (CORRECTED/CONFIRMED) are NEVER
        overwritten by the archive (operator feedback is P0). A wrong passphrase or a tampered
        archive is refused with a clear error (never a partial import). Profile-pack keys are
        re-wrapped under THIS machine's KEK so a pack published elsewhere becomes reconcilable
        here."""
        src_path = Path(source)
        if not src_path.exists():
            raise ServiceError(f"portable profile archive not found: {source}")
        try:
            archive = json.loads(src_path.read_text())
        except json.JSONDecodeError as exc:
            raise ServiceError(f"archive is not valid JSON: {exc}")
        try:
            payload = portability.open_archive(passphrase, archive)
        except portability.PortabilityError as exc:
            raise ServiceError(str(exc))
        counts = {
            "subjects_added": 0, "subjects_existing": 0, "facts_imported": 0,
            "facts_skipped_operator_authoritative": 0, "feedback_imported": 0,
            "aliases_imported": 0, "generations_imported": 0, "keys_imported": 0,
        }
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="portability.import", actor="operator") as conn:
            for sd in payload.get("subjects", []):
                if store.get_subject(conn, sd["subject_id"]) is None:
                    store.insert_subject(conn, _subject_from_portable(sd))
                    counts["subjects_added"] += 1
                else:
                    counts["subjects_existing"] += 1
            if self.profile_pack_crypto is not None:
                for kd in payload.get("profile_pack_keys", []):
                    if store.import_key_generation(
                        conn, self.profile_pack_crypto, kd["generation_id"],
                        base64.b64decode(kd["dek_b64"]),
                        purpose=kd.get("purpose", store.PROFILE_PACK_KEY_PURPOSE),
                        created_at=kd.get("created_at"),
                    ):
                        counts["keys_imported"] += 1
            for fd in payload.get("facts", []):
                scope = ContextScope.from_dict(fd["scope"])
                existing = store.get_fact_by_facet_scope(conn, self.crypto, fd["subject_id"], fd["facet"], scope.key())
                if existing is not None and existing.state in (FactState.CORRECTED, FactState.CONFIRMED):
                    counts["facts_skipped_operator_authoritative"] += 1
                    continue
                ci = fd.get("confidence_interval")
                store.upsert_fact(conn, self.crypto, ProfileFact(
                    fact_id=existing.fact_id if existing else new_id("fact"),
                    subject_id=fd["subject_id"], facet=fd["facet"], value=fd["value"], scope=scope,
                    state=FactState(fd["state"]), confidence=float(fd.get("confidence", 0.0)),
                    confidence_interval=tuple(ci) if ci else None,
                    document_count=int(fd.get("document_count", 0)), source_count=int(fd.get("source_count", 0)),
                    provenance_ids=[], synthesis_version=fd.get("synthesis_version", "v1"),
                    valid_from=float(fd.get("valid_from", now_ts())),
                ))
                counts["facts_imported"] += 1
            for gd in payload.get("generations", []):
                if store.get_generation(conn, gd["generation_id"]) is None:
                    store.insert_generation(conn, _generation_from_portable(gd))
                    counts["generations_imported"] += 1
            for ed in payload.get("feedback", []):
                if not store.feedback_event_exists(conn, ed["feedback_id"]):
                    store.insert_feedback_event(conn, self.crypto, _feedback_from_portable(ed))
                    counts["feedback_imported"] += 1
            for ad in payload.get("aliases", []):
                if store.find_alias_owner(conn, self.crypto, ad["source_type"], ad["source_native_id"]) is None:
                    store.insert_subject_alias(conn, self.crypto, _alias_from_portable(ad))
                    counts["aliases_imported"] += 1
        return {
            "status": "imported", **counts,
            "note": ("Operator-authoritative local facts (your corrections/confirmations) were "
                     "preserved, never overwritten."),
        }

    def export(self, *, subject_id: str, scope: str = "all", destination: str = "", challenge_literal: Optional[str] = None) -> dict[str, Any]:
        try:
            self._require_confirmation_or_raise("export", [subject_id, destination], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="export", actor="operator") as conn:
            facts = store.list_facts(conn, self.crypto, subject_id)
            if scope != "all":
                facts = [f for f in facts if f.facet == scope]
            manifest = ExportManifest(
                export_id=new_id("export"), subject_id=subject_id, scope=scope, destination=destination,
                sensitivity_disclosure="This file contains your voice profile facts in readable form.",
                facts=[{"facet": f.facet, "value": f.value, "state": f.state.value} for f in facts],
            )
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(json.dumps({
                "export_id": manifest.export_id, "scope": manifest.scope,
                "sensitivity_disclosure": manifest.sensitivity_disclosure, "facts": manifest.facts,
            }, indent=2))
            store.insert_export_record(conn, manifest)
        return {"status": "exported", "export_id": manifest.export_id, "destination": destination, "fact_count": len(manifest.facts)}

    def erase(self, *, scope: str, target: Optional[str] = None, challenge_literal: Optional[str] = None) -> dict[str, Any]:
        try:
            self._require_confirmation_or_raise("erase", [scope] + ([target] if target else []), challenge_literal, scope)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="erase", actor="operator", allow_while_off=True) as conn:
            if scope == "fact":
                report = erase.erase_fact(conn, target)
            elif scope == "source":
                report = erase.erase_source(conn, target)
            elif scope == "validation_set":
                report = erase.erase_validation_set(conn, target)
            elif scope == "model_call_payload":
                report = erase.erase_model_call_payloads(conn)
            elif scope == "export_under_control":
                report = erase.erase_export_under_control(conn, target)
            elif scope == "full_system":
                _, backups_dir = self._database_and_backups()
                clone_dir = self.paths.profile_pack_clone_dir if self.paths else None
                report = erase.erase_full_system(
                    conn, self.crypto, profile_pack_crypto=self.profile_pack_crypto,
                    backups_dir=backups_dir, profile_pack_clone_dir=clone_dir,
                )
            else:
                raise ServiceError(f"unknown erase scope {scope!r}")
        if scope in {"fact", "source"}:
            _, backups_dir = self._database_and_backups()
            if any(backups_dir.glob("operator-voice-*.sqlite3")):
                report.sinks_disclosed_unverifiable.append("local_backups")
                report.historical_ciphertext_note = "Pre-erase local backups are disclosed, not cleared; they still hold removed evidence."
        if scope == "full_system":
            erase.checkpoint_and_vacuum(self.conn)
        return {
            "status": "erased", "scope": report.scope, "sinks_cleared": report.sinks_cleared,
            "sinks_disclosed_unverifiable": report.sinks_disclosed_unverifiable,
            "deletion_counts": report.deletion_counts, "historical_ciphertext_note": report.historical_ciphertext_note,
        }

    def rebuild(self, *, generation_id: str) -> dict[str, Any]:
        generation = store.get_generation(self.conn, generation_id)
        if generation is None:
            raise ServiceError(f"unknown generation_id {generation_id!r}")
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="rebuild", actor="operator") as conn:
            facets = set(store.list_facets_for_subject(conn, generation.subject_id))
            self._synthesize_and_review(conn, generation.subject_id, facets, protect_only_corrected=True)
        return {"status": "rebuilt", "generation_id": generation_id, "pinned_versions": generation.version_bundle()}

    def _database_and_backups(self) -> tuple[Path, Path]:
        row = next((r for r in self.conn.execute("PRAGMA database_list") if r[1] == "main"), None)
        if row is None or not row[2]:
            raise ServiceError("A file-backed database is required for a verified backup.")
        database = Path(row[2]).resolve()
        return database, self.paths.backups_dir if self.paths else database.parent / "backups"

    def _full_scan(self, source, *, require_candidates=True):
        from operator_voice.adapters.base import AdapterError
        scanner = get_scanner(source.adapter_type)
        cursor = None
        seen_cursors = set()
        candidates = {}
        filters = {}
        while True:
            try:
                result = scanner(source, cursor, limit=None)
            except (AdapterError, OSError) as exc:
                raise ServiceError("Reextract stopped: source root is missing or unreadable.") from exc
            for candidate in result.candidates:
                previous = candidates.get(candidate.source_native_id)
                if previous is not None and source.adapter_type == AdapterType.DRIVE_EXPORT:
                    if not store._modified_time_is_strictly_newer(
                        previous.context.get("modified_time"), candidate.context.get("modified_time")
                    ):
                        continue
                candidates[candidate.source_native_id] = candidate
            for name, count in result.filter_counts.items():
                filters[name] = filters.get(name, 0) + count
            cursor = result.next_cursor
            if not result.has_more:
                break
            if cursor is None or cursor in seen_cursors:
                raise ServiceError("Reextract stopped: a full scan could not advance its cursor.")
            seen_cursors.add(cursor)
        if require_candidates and not candidates and store.list_document_ids_for_source(self.conn, source.source_id):
            raise ServiceError("Reextract stopped: a full scan found no candidates while the source holds documents.")
        return candidates, cursor, filters

    @staticmethod
    def _document_file_exists(source, document) -> bool:
        root = Path(source.canonical_root).resolve()
        locator = document.locator
        if source.adapter_type == AdapterType.SLACK_EXPORT and locator.startswith("slack:"):
            slug, _ = locator[6:].rsplit(":", 1)
            path = (root / f"{slug}.md").resolve()
            return path.is_relative_to(root) and path.is_file()
        if source.adapter_type == AdapterType.DRIVE_EXPORT and locator.startswith("drive:"):
            from operator_voice.drive.materialize import _safe_component
            native, revision = locator[6:].rsplit(":", 1)
            suffix = f"__{_safe_component(native)}__{_safe_component(revision)}.md"
        elif source.adapter_type == AdapterType.GMAIL_EXPORT and locator.startswith("gmail:"):
            from operator_voice.gmail.materialize import _safe_component
            suffix = f"__{_safe_component(locator.rsplit(':', 1)[1])}.md"
        else:
            return False
        return any(p.name.endswith(suffix) and p.resolve().is_relative_to(root) for p in root.glob("*.md"))

    def _reextract_plan(self, subject_id, *, scans=None):
        from operator_voice.adapters.base import iter_files_within
        from operator_voice.gmail.materialize import parse_export_file, trimmed_export_text
        plans, records = [], []
        counts = {"gmail_files_trimmed": 0, "header_shaped": 0, "repeated_documents": 0}
        current_versions = {FEATURE_REGISTRY_VERSION, signals.SIGNALS_VERSION}
        latest = audit.latest_success(self.conn, "reextract")
        current_authorship = latest is not None and latest.versions.get("authorship") == authorship.AUTHORSHIP_VERSION
        for source in store.list_sources(self.conn, self.crypto, subject_id):
            documents = {native: store.get_document(self.conn, self.crypto, doc_id)
                         for native, doc_id in store.document_ids_for_source(self.conn, source.source_id).items()}
            retired = source.adapter_type in RETIRED_ADAPTER_TYPES
            report = {"source_id": source.source_id, "adapter_type": source.adapter_type.value,
                      "paused": source.paused, "active": source.active, "retired": retired,
                      "new": 0, "kept": 0, "reextracted": 0, "dropped_now_filtered": 0,
                      "dropped_file_missing": 0, "filters": {}}
            plan = {"source": source, "report": report, "documents": documents, "reasons": {}}
            plans.append(plan)
            if retired or source.paused or not source.active:
                report["documents"] = len(documents)
                report["observations"] = self.conn.execute(
                    "SELECT COUNT(*) FROM observations o JOIN documents d ON o.document_id=d.document_id WHERE d.source_id=?",
                    (source.source_id,)).fetchone()[0]
                if retired:
                    report["erase_instruction"] = "operator-voice erase --scope source --target <id> (ids in curation-status)"
                continue
            candidates, cursor, filters = (scans[source.source_id] if scans and source.source_id in scans
                                           else self._full_scan(source))
            candidates, filters = dict(candidates), dict(filters)
            plan["scan"] = (dict(candidates), cursor, dict(filters))
            plan.update(candidates=candidates, cursor=cursor)
            report["filters"] = filters
            for native, candidate in candidates.items():
                state, _ = authorship.classify_role(candidate, str(source.role_identity.get("subject_role", "")))
                own = authorship.own_text(candidate.raw_text) if state == AuthorshipState.SUBJECT else ""
                words = len(normalize.tokenize_words(normalize.normalize_text(normalize.strip_non_prose(own)[0]).text))
                records.append({"id": (source.source_id, native), "source_native_id": native,
                                "native_revision": candidate.context.get("modified_time"),
                                "adapter_type": source.adapter_type.value, "words": words,
                                "text_key": self._text_key(own) if own else None})
            if source.adapter_type == AdapterType.GMAIL_EXPORT:
                plan["gmail_files"] = iter_files_within(Path(source.canonical_root), suffixes=(".md",), limit=None)
                for path in plan["gmail_files"]:
                    text = path.read_text(encoding="utf-8")
                    counts["gmail_files_trimmed"] += int(trimmed_export_text(text)[1])
                    for record in parse_export_file(text):
                        lines = authorship.own_text(record["body"]).splitlines()
                        shaped = any((line.lower().startswith("on ") and line.rstrip().lower().endswith("wrote:"))
                                     or (line.lower().startswith("from:") and any(
                                         following.lower().startswith("sent:") for following in lines[i + 1:i + 4]))
                                     for i, line in enumerate(lines))
                        counts["header_shaped"] += int(shaped)
        repeated = store.repeated_evidence_ids(records)
        counts["repeated_documents"] = len(repeated)
        for plan in plans:
            if "candidates" not in plan:
                continue
            source, documents, candidates = plan["source"], plan["documents"], plan["candidates"]
            for native in list(candidates):
                if (source.source_id, native) in repeated:
                    del candidates[native]
                    plan["report"]["filters"]["repeated"] = plan["report"]["filters"].get("repeated", 0) + 1
            for native in sorted(documents.keys() | candidates.keys()):
                doc, candidate = documents.get(native), candidates.get(native)
                if doc is None:
                    reason = "new"
                elif candidate is None:
                    reason = "dropped_now_filtered" if self._document_file_exists(source, doc) else "dropped_file_missing"
                else:
                    state, _ = authorship.classify_role(candidate, str(source.role_identity.get("subject_role", "")))
                    versions = store.observation_method_versions(self.conn, doc.document_id)
                    reason = "kept" if (doc.digest == candidate.digest and doc.authorship_state == state
                                        and versions.issubset(current_versions) and doc.words is not None
                                        and store.document_has_analysis_metadata(self.conn, doc.document_id) and current_authorship) else "reextracted"
                plan["reasons"][native] = reason
                plan["report"][reason] += 1
        return plans, counts

    def _retire_unrepresented_facts(self, conn, subject_id):
        retired = {s.source_id for s in store.list_sources(conn, self.crypto, subject_id)
                   if s.adapter_type in RETIRED_ADAPTER_TYPES}
        repeated = store.repeated_document_ids(conn, subject_id)
        for fact in store.list_facts(conn, self.crypto, subject_id):
            if fact.state in (FactState.CORRECTED, FactState.CONFIRMED):
                continue
            observations = store.get_observations_for_facet(conn, self.crypto, subject_id, fact.facet)
            sources = store.document_source_map(conn, [o.document_id for o in observations])
            if not any(sources.get(o.document_id) not in retired and o.document_id not in repeated
                       and taxonomy.normalize_scope(o.context).key() == fact.scope.key() for o in observations):
                store.retire_fact(conn, fact.fact_id)

    def reextract(self, *, subject_id: str, dry_run: bool = False,
                  challenge_literal: Optional[str] = None) -> dict[str, Any]:
        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        if not dry_run and is_off(self.conn):
            raise OperationRefused("reextract refused: toolkit is off")
        plans, counts = self._reextract_plan(subject_id)
        preview = {"status": "preview", "sources": [p["report"] for p in plans], **counts}
        if dry_run:
            return preview
        try:
            self._require_confirmation_or_raise("reextract", [subject_id], challenge_literal)
        except ConfirmationRequired as cr:
            return cr.to_dict()
        database, backups_dir = self._database_and_backups()
        snapshot = backup.create_backup(database, backups_dir)
        from operator_voice.gmail.materialize import trim_export_file
        for plan in plans:
            for path in plan.get("gmail_files", []):
                trim_export_file(path)
        # Recompute after trimming so persisted digests describe the files on disk.
        scans = {p["source"].source_id: p["scan"] for p in plans
                 if "scan" in p and p["source"].adapter_type != AdapterType.GMAIL_EXPORT}
        plans, _ = self._reextract_plan(subject_id, scans=scans)
        preview["sources"] = [p["report"] for p in plans]
        facets = set(store.list_facets_for_subject(self.conn, subject_id))
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="reextract", actor="operator",
                              versions={"adapters": ADAPTER_VERSION, "authorship": authorship.AUTHORSHIP_VERSION}) as conn:
            for plan in plans:
                if "candidates" not in plan:
                    continue
                source = plan["source"]
                for native, reason in plan["reasons"].items():
                    checkpoint(conn, "reextract")
                    if reason.startswith("dropped_"):
                        store.delete_document_evidence(conn, plan["documents"][native].document_id)
                    elif reason in {"new", "reextracted"}:
                        result = self._extract_document(
                            conn, source, plan["candidates"][native], str(source.role_identity.get("subject_role", "")),
                            replace=reason == "reextracted")
                        facets.update(result["touched_facets"])
                store.set_source_cursor(conn, source.source_id, plan["cursor"])
            self._synthesize_and_review(conn, subject_id, facets, protect_only_corrected=True)
            self._retire_unrepresented_facts(conn, subject_id)
            generation = self._stamp_generation(conn, subject_id, facets, reason="reextract with current methods",
                                                diff_summary={"touched_facets": sorted(facets)})
        return {**preview, "status": "reextracted", "backup_path": str(snapshot), "generation_id": generation,
                "disclosure": f"A backup taken before this change, at {snapshot}, still holds the removed evidence. "
                              "Backups are kept until ten newer backups exist or you run a full erase; nothing else removes them."}

    @staticmethod
    def _other_ovt_process_running() -> bool:
        import os
        import shlex
        import subprocess
        try:
            result = subprocess.run(["ps", "-axo", "pid=,command="], check=True,
                                    capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ServiceError("Cannot verify whether another OVT process is running.") from exc
        # Command lines are inspected privately and never returned or logged.
        for line in result.stdout.splitlines():
            fields = line.strip().split(None, 1)
            if len(fields) != 2 or int(fields[0]) == os.getpid():
                continue
            try:
                args = shlex.split(fields[1])
            except ValueError:
                continue
            if any(Path(arg).name == "operator-voice"
                   or Path(arg).name.endswith("-tool-operator-voice") for arg in args):
                return True
            if any(arg == "-m" and i + 1 < len(args) and args[i + 1].startswith("operator_voice")
                   for i, arg in enumerate(args)):
                return True
        return False

    def _check_restore_idle(self):
        if self._other_ovt_process_running():
            raise ServiceError("Stop the other operator-voice process before restoring a backup.")
        if self.conn.in_transaction:
            raise ServiceError("The database is locked by an active operation.")
        timeout = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        try:
            self.conn.execute("PRAGMA busy_timeout=0")
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            raise ServiceError("The database is locked; stop other operations before restoring.") from exc
        finally:
            self.conn.execute(f"PRAGMA busy_timeout={int(timeout)}")

    def backup_restore(self, *, backup_path: Optional[str] = None, dry_run: bool = False,
                       challenge_literal: Optional[str] = None,
                       erased_evidence_literal: Optional[str] = None) -> dict[str, Any]:
        database, backups_dir = self._database_and_backups()
        directory = backups_dir.resolve()
        if backup_path is None:
            choices = [p for p in directory.glob("operator-voice-*.sqlite3") if p.is_file() and not p.is_symlink()]
            if not choices:
                raise ServiceError("No local backup is available.")
            selected = max(choices, key=lambda p: (p.stat().st_mtime_ns, p.name))
        else:
            selected = Path(backup_path).expanduser()
        if (selected.is_symlink() or selected.resolve().parent != directory
                or not selected.name.startswith("operator-voice-") or selected.suffix != ".sqlite3"
                or not selected.is_file()):
            raise ServiceError("Choose an operator-voice-*.sqlite3 file directly inside the backups directory.")
        selected = selected.resolve()
        self._check_restore_idle()
        ok, detail = backup.verify_backup(selected)
        if not ok:
            raise ServiceError(f"Backup verification failed: {detail}")
        last_erase = audit.latest_success(self.conn, "erase")
        stat = selected.stat()
        erased = last_erase is not None and stat.st_mtime < last_erase.created_at
        preview = {"status": "preview", "backup_path": str(selected),
                   "age_seconds": max(0, now_ts() - stat.st_mtime), "erased_evidence_literal_required": erased}
        if dry_run:
            return preview
        targets = [str(selected), f"{stat.st_mtime_ns}:{stat.st_size}"]
        challenges = []
        for kind, provided, argument in [("restore", challenge_literal, "challenge_literal")] + (
            [("erased-evidence", erased_evidence_literal, "erased_evidence_literal")] if erased else []
        ):
            bound = targets + [kind]
            challenge = store.find_pending_challenge(self.conn, "backup.restore", bound)
            if challenge is None:
                challenge = issue_challenge(get_operation("backup.restore"), bound, None)
                store.insert_challenge(self.conn, challenge)
            if provided is None:
                warning = ("This restores erased evidence. " if kind == "erased-evidence" else
                           "This replaces the local database with the verified backup. ")
                return {**preview, "status": "confirmation_required", "operation": "backup.restore",
                        "instructions": warning + f"Re-run with {argument}={challenge.literal!r} to confirm."}
            ok, reason = verify_challenge(challenge, operation_name="backup.restore", targets=bound,
                                          provided_literal=provided)
            if not ok:
                raise ServiceError(f"confirmation rejected: {reason}")
            challenges.append(challenge)
        self._check_restore_idle()
        for challenge in challenges:
            store.mark_challenge_used(self.conn, challenge.challenge_id)
        # The SQLite backup API restores into the existing connection; no open-handle unlink.
        backup.restore_backup(selected, database, live_connection=self.conn)
        audit.record(self.conn, operation_id=new_id("op"), operation_type="backup.restore", actor="operator",
                     consumer=None, result="success")
        return {**preview, "status": "restored"}

    def reanalyze(self, *, subject_id: str) -> dict[str, Any]:
        if store.get_subject(self.conn, subject_id) is None:
            raise _unknown_subject_error(subject_id)
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="reanalyze", actor="operator") as conn:
            facets = set(store.list_facets_for_subject(conn, subject_id))
            self._synthesize_and_review(conn, subject_id, facets, protect_only_corrected=True)
            parent = store.get_latest_generation(conn, subject_id)
            generation = ProfileGeneration(
                generation_id=new_id("gen"), subject_id=subject_id, schema_version="operator-voice-schema/v1",
                normalization_version=normalize.NORMALIZATION_VERSION, extraction_version=_EXTRACTION_VERSION,
                synthesis_version=synthesis.SYNTHESIS_VERSION, taxonomy_version=taxonomy.TAXONOMY_VERSION, policy_version="policy/v1",
                tokenizer_version="conservative-estimator/v1", feature_registry_version=_EXTRACTION_VERSION,
                content_digest=_digest(",".join(sorted(facets))), creation_reason="reanalyze with current method versions",
                parent_generation_id=parent.generation_id if parent else None,
                diff_summary={"reanalyzed_facets": sorted(facets)},
            )
            store.insert_generation(conn, generation)
        return {"status": "reanalyzed", "generation_id": generation.generation_id, "facets": sorted(facets)}

    def retention_set(self, *, policy_name: str, days: int) -> dict[str, Any]:
        with staged_operation(self.conn, operation_id=new_id("op"), operation_type="retention.set", actor="operator") as conn:
            pass  # M1 ships a single zero-day default (retention.py); named policies are recorded
            # via audit for forward compatibility, not yet enforced per-policy.
        return {"status": "accepted", "policy_name": policy_name, "days": days}

    def off(self, *, reason: str = "") -> dict[str, Any]:
        state = set_off(self.conn, reason)
        audit.record(self.conn, operation_id=new_id("op"), operation_type="off", actor="operator", consumer=None, result="success")
        return {"status": "off", "reason": state.reason}

    def on(self) -> dict[str, Any]:
        set_on(self.conn)
        audit.record(self.conn, operation_id=new_id("op"), operation_type="on", actor="operator", consumer=None, result="success")
        return {"status": "on", "note": "previously erased data is never restored by turning back on"}
