"""Canonical schema v1 — build plan v3 §5 ("Canonical schema (data model, not code)").

Every dataclass here maps 1:1 to a bullet in §5. Fields marked *provisional* in a docstring are
frozen/additive-exempt per §5's closing paragraph: "Fields for concepts no milestone has yet
exercised ... are marked provisional in v1 and may be revised via a documented v1.x addendum
when M4 first exercises them."

This module is pure data: dataclasses, enums, and construction helpers. No I/O, no persistence,
no kernel logic. The deterministic kernel (``operator_voice.kernel``) and application service
(``operator_voice.application.service``) are the only code that interprets these fields.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "operator-voice-schema/v1"


def new_id(prefix: str) -> str:
    """Opaque local ID. Never derived from, or reversible to, content."""
    return f"{prefix}_{uuid.uuid4().hex}"


def now_ts() -> float:
    return time.time()


# --------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------


class SubjectKind(str, enum.Enum):
    OPERATOR = "OPERATOR"
    # provisional in v1 per §5 closing paragraph: product exposure waits for M4 (§13 M4;
    # decision D17), but the discriminator itself must exist so M1 storage never has to migrate
    # the subject_kind column later.
    EXTERNAL = "EXTERNAL"


class BackendMode(str, enum.Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    ENCRYPTED_GIT = "ENCRYPTED_GIT"


class FactState(str, enum.Enum):
    """§4.2. Precedence: CORRECTED > CONFIRMED > SUPPORTED > OBSERVED; MODEL_HYPOTHESIS never
    outranks deterministic evidence without operator confirmation. DEPRECATED is excluded from
    retrieval entirely."""

    OBSERVED = "OBSERVED"
    SUPPORTED = "SUPPORTED"
    MODEL_HYPOTHESIS = "MODEL_HYPOTHESIS"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    DEPRECATED = "DEPRECATED"


# Higher number = higher precedence. MODEL_HYPOTHESIS is deliberately below OBSERVED: it must
# never silently outrank *any* deterministic evidence state without an explicit CONFIRMED action
# (§4.2: "MODEL_HYPOTHESIS never outranks deterministic evidence without operator confirmation").
FACT_STATE_PRECEDENCE: dict[FactState, int] = {
    FactState.CORRECTED: 5,
    FactState.CONFIRMED: 4,
    FactState.SUPPORTED: 3,
    FactState.OBSERVED: 2,
    FactState.MODEL_HYPOTHESIS: 1,
    FactState.DEPRECATED: 0,
}

# States eligible for normal retrieval (context_get). DEPRECATED and bare OBSERVED are excluded
# by default (§4.2: OBSERVED is "Hidden unless explicitly requested for inspection").
RETRIEVAL_ELIGIBLE_STATES = frozenset(
    {FactState.SUPPORTED, FactState.CONFIRMED, FactState.CORRECTED}
)


class AuthorshipState(str, enum.Enum):
    """Kernel identity/authorship decision — §4 "kernel identity/authorship decision"."""

    SUBJECT = "SUBJECT"
    AI = "AI"
    OTHER = "OTHER"
    AMBIGUOUS_QUARANTINED = "AMBIGUOUS_QUARANTINED"


class AdapterType(str, enum.Enum):
    MANUAL = "manual"
    CLAUDE_EXPORT = "claude_export"
    CHATGPT_EXPORT = "chatgpt_export"
    MARKDOWN = "markdown"
    # M3 (§13 M3 worklist 1): read-only Cursor transcript + approved-artifact adapters. Both keep
    # role adapter-authoritative and apply source-specific redaction/quarantine (code/tool blocks,
    # quoted third-party text) so only genuinely operator-authored prose becomes evidence.
    CURSOR_TRANSCRIPT = "cursor_transcript"
    APPROVED_ARTIFACT = "approved_artifact"
    # OVT Slack Adapter (agent-driven, MCP-sourced, no token): reads the per-channel Markdown
    # files `slack.import` materializes after server-side author verification (§ slack.import).
    SLACK_EXPORT = "slack_export"
    # OVT Drive Adapter (agent-delegated fetch, owner-only, zero OVT credentials): reads the
    # timestamp-prefixed, one-file-per-revision Markdown `drive.import` materializes after
    # server-side owner + not-shared-drive verification (§ docs/drive-adapter.md; ADR 0002).
    DRIVE_EXPORT = "drive_export"
    # OVT Gmail Adapter (agent-delegated fetch, Sent-only, zero OVT credentials): reads the
    # timestamp-prefixed, one-file-per-message Markdown `gmail.import` materializes after
    # server-side author verification (§ docs/gmail-adapter.md; ADR 0001).
    GMAIL_EXPORT = "gmail_export"


RETIRED_ADAPTER_TYPES = frozenset({
    AdapterType.CURSOR_TRANSCRIPT, AdapterType.CHATGPT_EXPORT, AdapterType.CLAUDE_EXPORT,
    AdapterType.MANUAL, AdapterType.MARKDOWN, AdapterType.APPROVED_ARTIFACT,
})


class FeedbackAction(str, enum.Enum):
    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    BAN = "ban"
    SCOPE = "scope"
    IDENTITY = "identity"
    SOURCE = "source"


class ValidationOutcome(str, enum.Enum):
    VALIDATED = "validated"
    DETERMINISTIC_ONLY = "deterministic_only"
    UNVALIDATED = "unvalidated"


class ReviewReason(str, enum.Enum):
    """§13 M2 worklist 3 "operator review queues". Why a profile change needs a human look before it
    is trusted. Deterministic — assigned by the kernel, never by a model."""

    CONTRADICTION = "CONTRADICTION"          # new evidence contradicts a CORRECTED/CONFIRMED fact
    DRIFT = "DRIFT"                          # a supported fact materially drifted and was superseded
    LOW_SOURCE_DIVERSITY = "LOW_SOURCE_DIVERSITY"  # promoted on a single source (confidence capped)
    LOW_CONFIDENCE = "LOW_CONFIDENCE"        # below the trust floor but retained for inspection
    AMBIGUOUS_AUTHORSHIP = "AMBIGUOUS_AUTHORSHIP"  # quarantined authorship needing a decision


class ReviewStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class SyncStatus(str, enum.Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING_PUBLICATION = "PENDING_PUBLICATION"
    PUBLISHED = "PUBLISHED"
    CONFLICT = "CONFLICT"
    RESTORED = "RESTORED"


# --------------------------------------------------------------------------------------
# Context scope (minimal M1 slice of the full MYNAH-derived ContextTaxonomy — full
# taxonomy-as-data lands in M2 per build plan §13 M2 worklist; M1 needs only "one-context
# VoiceContextBundle/v1", build plan §13 M1 "Likely modules"/acceptance evidence).
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContextScope:
    """§5 ``ContextTaxonomy`` (M1 slice) — channel/audience/purpose/language/output_type used to
    disambiguate signals, facts, and retrieval requests. M1 ships a small closed vocabulary;
    unknown values are accepted but never silently merged with a known bucket (no fuzzy match)."""

    channel: str = "general"
    audience: str = "general"
    purpose: str = "general"
    language: str = "en"
    output_type: str = "text"

    def key(self) -> str:
        return f"{self.channel}|{self.audience}|{self.purpose}|{self.language}|{self.output_type}"

    def as_dict(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "audience": self.audience,
            "purpose": self.purpose,
            "language": self.language,
            "output_type": self.output_type,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ContextScope":
        return ContextScope(
            channel=str(d.get("channel", "general")),
            audience=str(d.get("audience", "general")),
            purpose=str(d.get("purpose", "general")),
            language=str(d.get("language", "en")),
            output_type=str(d.get("output_type", "text")),
        )


# --------------------------------------------------------------------------------------
# Subject / source / document
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class SubjectRegistration:
    """§5 ``SubjectRegistration``."""

    subject_id: str
    kind: SubjectKind
    display_label: str
    approved_purposes: list[str] = field(default_factory=list)
    consent_basis: str = "operator-attested"
    generation_permission: bool = True
    retention_policy: str = "default"
    active: bool = True
    created_at: float = field(default_factory=now_ts)
    reviewed_at: Optional[float] = None

    @staticmethod
    def new_operator(display_label: str) -> "SubjectRegistration":
        return SubjectRegistration(
            subject_id=new_id("subj"),
            kind=SubjectKind.OPERATOR,
            display_label=display_label,
            approved_purposes=["voice_generation", "validation", "analysis_of_own_text"],
            generation_permission=True,
        )

    @staticmethod
    def new_external(display_label: str, purposes: list[str]) -> "SubjectRegistration":
        # §4.3: EXTERNAL subjects never get generation_permission.
        return SubjectRegistration(
            subject_id=new_id("subj"),
            kind=SubjectKind.EXTERNAL,
            display_label=display_label,
            approved_purposes=list(purposes),
            generation_permission=False,
        )


@dataclass(slots=True)
class SubjectAlias:
    """§5 ``SubjectAlias``. ``source_native_id`` is sensitive (encrypted at the persistence
    layer); a display name alone is never authoritative (§4.3)."""

    alias_id: str
    subject_id: str
    source_type: str
    source_native_id: str
    confidence: float
    verification_state: str = "unverified"
    valid_from: float = field(default_factory=now_ts)
    valid_to: Optional[float] = None
    collision_review: Optional[str] = None


@dataclass(slots=True)
class SourceRegistration:
    """§5 ``SourceRegistration``. No source ships enabled."""

    source_id: str
    subject_id: str
    adapter_type: AdapterType
    canonical_root: str
    opted_in_at: float
    approved_purpose: str
    active: bool = False
    paused: bool = False
    retention_policy: str = "default"
    limits: dict[str, int] = field(default_factory=dict)
    role_identity: dict[str, Any] = field(default_factory=dict)
    cursor: Optional[str] = None


@dataclass(slots=True)
class SourceDocument:
    """§5 ``SourceDocument``. Content-bearing; local-only and erasable. ``content`` holds
    plaintext in memory only — the persistence layer is the sole place it is ever encrypted or
    written to disk (``operator_voice.persistence.crypto``)."""

    document_id: str
    subject_id: str
    source_id: str
    source_native_id: str
    digest: str
    locator: str
    content: str
    created_at: float = field(default_factory=now_ts)
    context: ContextScope = field(default_factory=ContextScope)
    sensitivity: str = "standard"
    authorship_state: AuthorshipState = AuthorshipState.AMBIGUOUS_QUARANTINED
    quarantine_reason: Optional[str] = None
    expires_at: Optional[float] = None
    # Opaque native-revision comparator (Drive's file ``modified_time``, ISO-8601 — lexically
    # ordered) threaded from the adapter candidate's ``context`` so the persistence layer's
    # Drive-only supersede-if-newer path can order revisions of the SAME ``source_native_id``
    # (``file_id`` alone — ADR 0002 Decision 2). ``None`` for every adapter that does not model
    # revisions (all pre-Drive sources), which keeps ``upsert_document`` on its insert-only path.
    native_revision: Optional[str] = None
    words: int | None = None
    text_key: str | None = None


@dataclass(slots=True)
class ObservationCandidate:
    """§4 "candidate with authoritative metadata" — the sole output type of every adapter's
    ``scan()``. Adapters populate ``role``/``author_id`` from the SOURCE FORMAT's own authoritative
    metadata (never inferred from text content); the kernel's identity/authorship stage is the
    only place that turns this into an :class:`AuthorshipState` decision."""

    candidate_id: str
    claimed_subject_id: str
    source_id: str
    source_native_id: str
    role: str  # adapter-authoritative: "user" | "assistant" | "system" | "other" | "unknown"
    raw_text: str
    digest: str
    locator: str
    author_id: Optional[str] = None
    channel: str = "general"
    # Retrieval-facing output form (e.g. doc/slide/email), adapter-authoritative exactly like
    # ``channel`` and threaded into the persisted ``ContextScope`` by
    # ``application.service._ingest_source_within``. Defaults to ``"text"`` so every existing adapter
    # that does not tag an output form keeps its prior scope unchanged.
    output_type: str = "text"
    timestamp: float = field(default_factory=now_ts)
    context: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Signals / evidence / facts
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class SignalObservation:
    """§5 ``SignalObservation``. ``observation_key`` is a stable keyed-HMAC idempotency key
    (see ``kernel.features.observation_key``) so duplicate ingestion of the same
    document+segment+facet never double-counts (quality gate §10.3)."""

    observation_id: str
    observation_key: str
    subject_id: str
    document_id: str
    segment_id: str
    facet: str
    value: Any
    distribution: Optional[dict[str, float]] = None
    context: ContextScope = field(default_factory=ContextScope)
    sensitivity: str = "standard"
    method_version: str = "v1"
    created_at: float = field(default_factory=now_ts)
    quality_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Provenance:
    """Provenance pin — §5 ``EvidenceRecord``: "Git-backed sources pin {path_token, commit,
    blob}; other sources pin native revision/ID plus digest."."""

    source_id: str
    document_id: str
    digest: str
    path_token: Optional[str] = None
    commit: Optional[str] = None
    blob: Optional[str] = None
    native_revision: Optional[str] = None


@dataclass(slots=True)
class EvidenceRecord:
    """§5 ``EvidenceRecord``."""

    evidence_id: str
    subject_id: str
    facet: str
    context: ContextScope
    observation_ids: list[str]
    document_diversity: int
    source_diversity: int
    contradiction: bool = False
    outlier: bool = False
    confidence_inputs: dict[str, float] = field(default_factory=dict)
    method_versions: dict[str, str] = field(default_factory=dict)
    valid_from: float = field(default_factory=now_ts)
    valid_to: Optional[float] = None
    provenance: list[Provenance] = field(default_factory=list)


@dataclass(slots=True)
class ProfileFact:
    """§5 ``ProfileFact``."""

    fact_id: str
    subject_id: str
    facet: str
    value: Any
    scope: ContextScope
    state: FactState
    confidence: float
    confidence_interval: Optional[tuple[float, float]] = None
    document_count: int = 0
    source_count: int = 0
    provenance_ids: list[str] = field(default_factory=list)
    synthesis_version: str = "v1"
    valid_from: float = field(default_factory=now_ts)
    valid_to: Optional[float] = None
    superseded_by: Optional[str] = None


@dataclass(slots=True)
class FeedbackEvent:
    """§5 ``FeedbackEvent``. Explicit feedback is durable profile memory (§4.2, D15)."""

    feedback_id: str
    subject_id: str
    utterance_digest: str
    action: FeedbackAction
    reason: str
    target_fact_id: Optional[str] = None
    target_facet: Optional[str] = None
    prior_value: Any = None
    new_value: Any = None
    actor: str = "operator"
    resulting_generation_id: Optional[str] = None
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class ProfileGeneration:
    """§5 ``ProfileGeneration``. The pinned version bundle referenced by ``rebuild`` (§8)."""

    generation_id: str
    subject_id: str
    schema_version: str
    normalization_version: str
    extraction_version: str
    synthesis_version: str
    taxonomy_version: str
    policy_version: str
    tokenizer_version: str
    feature_registry_version: str
    content_digest: str
    creation_reason: str
    parent_generation_id: Optional[str] = None
    diff_summary: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now_ts)

    def version_bundle(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "normalization_version": self.normalization_version,
            "extraction_version": self.extraction_version,
            "synthesis_version": self.synthesis_version,
            "taxonomy_version": self.taxonomy_version,
            "policy_version": self.policy_version,
            "tokenizer_version": self.tokenizer_version,
            "feature_registry_version": self.feature_registry_version,
        }


# --------------------------------------------------------------------------------------
# Bundles (frozen wire contracts live in ``domain.contracts``; these are the in-process
# construction types the kernel/service populate before contract serialization).
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class RankedFact:
    facet: str
    value: Any
    state: FactState
    confidence: float
    scope: ContextScope
    provenance_ids: list[str] = field(default_factory=list)
    document_count: Optional[int] = None


@dataclass(slots=True)
class VoiceContextBundle:
    """§5 / §6.3 ``VoiceContextBundle``: ``voice-context-bundle/v1``. No raw samples by
    default (§6, §7 quality gate 11)."""

    bundle_id: str
    subject_id: str
    consumer_id: str
    generation_id: str
    request_scope: ContextScope
    ranked_facts: list[RankedFact]
    instructions: dict[str, Any]
    warnings: list[str]
    provenance_refs: list[str]
    budget_tokens: int
    actual_tokens: int
    confidence: float
    abstained: bool
    schema: str = "voice-context-bundle/v1"
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class SubjectInsight:
    facet: str
    observation: str
    uncertainty: str
    counter_evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SubjectInsightBundle:
    """§5 / §4.3 ``SubjectInsightBundle``: ``subject-insight-bundle/v1``. Contains no
    generative instructions (hard architectural invariant, quality gate §10.16)."""

    bundle_id: str
    subject_id: str
    purpose: str
    observations: list[SubjectInsight]
    warnings: list[str]
    expires_at: Optional[float]
    schema: str = "subject-insight-bundle/v1"
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class ReviewItem:
    """§13 M2 worklist 3 "operator review queues". A deterministic, operator-facing item flagging a
    profile change that needs a human decision. ``detail`` is plain-language and MAY reference a
    fact value, so the store encrypts it (``detail_enc``) exactly like other sensitive derived
    content. ``related_ids`` carries opaque fact/observation IDs (never raw text)."""

    review_id: str
    subject_id: str
    reason: "ReviewReason"
    detail: str
    facet: Optional[str] = None
    scope: Optional[ContextScope] = None
    related_fact_id: Optional[str] = None
    related_ids: list[str] = field(default_factory=list)
    status: "ReviewStatus" = None  # set in __post_init__ to OPEN (avoids enum default import order)
    created_at: float = field(default_factory=now_ts)
    resolved_at: Optional[float] = None
    resolution: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = ReviewStatus.OPEN


@dataclass(slots=True)
class ValidationRun:
    """§5 ``ValidationRun``. Draft text is transient/erasable."""

    run_id: str
    subject_id: str
    draft_digest: str
    checks: list[dict[str, Any]]
    outcome: ValidationOutcome
    versions: dict[str, str]
    gateway_metadata: Optional[dict[str, Any]] = None
    expires_at: Optional[float] = None
    created_at: float = field(default_factory=now_ts)


# --------------------------------------------------------------------------------------
# Profile backend / pack / sync
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class ProfileBackendConfig:
    """§5 ``ProfileBackendConfig``. ``LOCAL_ONLY`` is the default (D11). Remote URL/credentials
    are machine-local config — never profile-pack or governed-repo data."""

    mode: BackendMode = BackendMode.LOCAL_ONLY
    active: bool = False
    remote_reference_token: Optional[str] = None
    key_generation_ref: Optional[str] = None
    last_verified_durability: Optional[dict[str, Any]] = None
    health: str = "This profile stays on this computer"


@dataclass(slots=True)
class GatewayConfig:
    """§13 M2 worklist 4 — persisted, operator-configured model-gateway policy. BOTH egress
    switches default to False (disabled): the deterministic kernel never needs a model, and
    D7/D17 make model egress opt-in. ``external_egress_enabled`` is a SEPARATE switch from
    ``operator_egress_enabled`` and stays denied even when operator egress is on."""

    operator_egress_enabled: bool = False
    external_egress_enabled: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    allowed_data_classes: list[str] = field(default_factory=list)
    timeout_ms: int = 20000
    updated_at: Optional[float] = None


@dataclass(slots=True)
class ProfilePackObjectRef:
    digest: str
    object_type: str


@dataclass(slots=True)
class ProfilePackManifest:
    """§5 ``ProfilePackManifest``. Redacted by construction: no fact values, aliases, paths, or
    raw titles (quality gate §10.14)."""

    generation_id: str
    parent_generation_id: Optional[str]
    object_refs: list[ProfilePackObjectRef]
    redacted_counts: dict[str, int]
    key_generation_id: str
    publisher_version: str
    git_parent_sha: Optional[str] = None
    schema: str = "profile-pack-manifest/v1"
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class ProfileSyncState:
    """§5 ``ProfileSyncState`` — present only for ``ENCRYPTED_GIT``. The ``conflict_set`` field
    is *provisional* in v1 (§5 closing paragraph: full typed reconciliation is M4, D18)."""

    local_generation_id: Optional[str] = None
    remote_generation_id: Optional[str] = None
    exact_parent_sha: Optional[str] = None
    publish_status: SyncStatus = SyncStatus.NOT_CONFIGURED
    conflict_set: list[dict[str, Any]] = field(default_factory=list)  # provisional (M4)
    last_verified_clean_room: Optional[float] = None


# --------------------------------------------------------------------------------------
# Metadata-only records (§5, §5.1 no-content rule)
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class ModelCallRecord:
    call_id: str
    provider: str
    model: str
    data_class: str
    purpose: str
    outcome: str
    duration_ms: int
    cancelled: bool = False
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class AuditEvent:
    """§5 ``AuditEvent`` — append-only, content-free (§5.1, §8)."""

    event_id: str
    operation_id: str
    operation_type: str
    actor: str
    consumer: Optional[str]
    result: str
    versions: dict[str, str] = field(default_factory=dict)
    deletion_counts: Optional[dict[str, int]] = None
    created_at: float = field(default_factory=now_ts)


@dataclass(slots=True)
class ConsequenceDescriptor:
    """§6: preview is mandatory when live consequences indicate destruction, irreversibility,
    shared-reference impact, OR sensitive export — four independent triggers, not three."""

    destructive: bool
    irreversible: bool
    shared_reference: bool
    sensitive_export: bool
    summary: str

    @property
    def requires_challenge(self) -> bool:
        return self.destructive or self.irreversible or self.shared_reference or self.sensitive_export


@dataclass(slots=True)
class OperationChallenge:
    """§5 ``OperationChallenge``. §6: preview returns a one-use operation/target/generation-bound
    challenge; the literal is a short plain-language word/phrase, never an ID/digest/nonce."""

    challenge_id: str
    operation: str
    targets: list[str]
    literal: str
    consequence: ConsequenceDescriptor
    issued_at: float = field(default_factory=now_ts)
    expires_at: float = 0.0
    used: bool = False


@dataclass(slots=True)
class ExportManifest:
    """§5 ``ExportManifest``. Exempt from the no-content rule (§5.1): intentionally
    human-readable and minimum-necessary; never written to Git or logs."""

    export_id: str
    subject_id: str
    scope: str
    destination: str
    sensitivity_disclosure: str
    facts: list[dict[str, Any]]
    created_at: float = field(default_factory=now_ts)
    expires_at: Optional[float] = None


@dataclass(slots=True)
class CancellationState:
    """Persisted "off" flag checked before every unit of work (§8, §10.10)."""

    off: bool = False
    reason: Optional[str] = None
    set_at: Optional[float] = None
    checkpoints: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Continual curation (§13 M3) — passive scheduled observation records. Content-free by
# construction (§5.1): counts, enums, timestamps only, never a fact value or raw text.
# --------------------------------------------------------------------------------------


class CurationTrigger(str, enum.Enum):
    SCHEDULED = "scheduled"  # invoked by the single local-jobs command instance
    MANUAL = "manual"        # invoked directly by the operator / an agent


class CurationRunStatus(str, enum.Enum):
    """Lifecycle of one continual-curation tick. A ``RUNNING`` row that outlives the process
    (crash / kill / sleep-during-run) is detected on the next tick and marked ``RECOVERED`` —
    the stale-operation recovery required by §13 M3 worklist 3."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"          # finished a full pass (may have per-source failures recorded)
    NOOP = "NOOP"                    # no active source enrolled — safe/inert tick
    SKIPPED_OFF = "SKIPPED_OFF"      # toolkit is off; scheduled tick is a no-op, never an error
    CANCELLED = "CANCELLED"          # off flipped mid-run; stopped at a checkpoint
    RECOVERED = "RECOVERED"          # a prior RUNNING row reclaimed after an interrupted run
    FAILED = "FAILED"                # unexpected top-level error (per-source errors do NOT set this)


@dataclass(slots=True)
class CurationRun:
    """§13 M3 "continual curation" — one durable, content-free record per curation tick. Every
    field is a count, enum, boolean, or timestamp; no facet name, fact value, or raw text ever
    appears here (§5.1 no-content rule)."""

    run_id: str
    trigger: CurationTrigger
    status: CurationRunStatus
    started_at: float = field(default_factory=now_ts)
    finished_at: Optional[float] = None
    sources_total: int = 0
    sources_processed: int = 0
    sources_failed: int = 0
    documents_new: int = 0
    observations_new: int = 0
    facets_touched: int = 0
    contradictions: int = 0
    catch_up_gap_seconds: Optional[float] = None
    pending_continuation: bool = False
    published: bool = False
    publish_status: Optional[str] = None
    recovered_runs: int = 0
    learning_summary: dict[str, Any] = field(default_factory=dict)
    error_class: Optional[str] = None
    notes: Optional[str] = None


@dataclass(slots=True)
class SourceCurationState:
    """Per-source watermark/health for continual curation. The incremental cursor itself lives on
    :class:`SourceRegistration` (``sources.cursor``); this row tracks scheduling health so a
    persistently-failing source can be surfaced without ever blocking the other sources."""

    source_id: str
    last_curated_at: Optional[float] = None
    last_success_at: Optional[float] = None
    consecutive_failures: int = 0
    last_error_class: Optional[str] = None
    last_run_id: Optional[str] = None
    pending_continuation: bool = False
