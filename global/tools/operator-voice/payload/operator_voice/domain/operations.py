"""The one operation registry — build plan v3 §6: "One typed operation registry generates CLI
commands, MCP tools, JSON schemas, operation cards, examples, error taxonomy, posture
annotations, and deterministic help. Adding a verb edits the registry and service once, never
each surface separately."

Naming follows the snow-kit precedent cited in §6.1 ("dotted operation names in the registry,
sanitized MCP names"): the registry key is a dotted verb (``profile.publish``); the CLI derives a
dashed subcommand (``profile-publish``); MCP derives a sanitized underscore name
(``profile_publish``); the application-service handler is the same name with dots replaced by
underscores (``OperatorVoiceService.profile_publish``).

This module holds ONLY declarative metadata. All behavior lives in
``operator_voice.application.service.OperatorVoiceService``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ArgType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"  # arbitrary JSON-decodable value (dict/list/scalar)


class Posture(str, Enum):
    """Live-consequence posture (§6): drives whether ``preview``/challenge is mandatory."""

    SAFE = "safe"  # pure read, or a mutation with no destructive/irreversible/shared/export impact
    REVERSIBLE = "reversible"  # mutates state but is itself reversible (e.g. deprecate, pause)
    CONSEQUENTIAL = "consequential"  # destructive, irreversible, shared-reference, or sensitive export


class Group(str, Enum):
    READ = "read"
    MUTATION = "mutation"
    LIFECYCLE = "lifecycle"  # CLI-only; §6: "remain CLI-only because exposing them to an agent
    # tool is unnecessary authority"


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type: ArgType
    required: bool = True
    default: Any = None
    help: str = ""
    choices: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class Operation:
    name: str  # dotted registry key, e.g. "profile.publish"
    group: Group
    posture: Posture
    summary: str
    args: tuple[ArgSpec, ...] = ()
    examples: tuple[str, ...] = ()
    mcp_exposed: bool = True  # False for Group.LIFECYCLE (§6)
    mutation_tool: bool = False  # True hides it from MCP unless mutations are explicitly enabled

    @property
    def handler_name(self) -> str:
        return self.name.replace(".", "_")

    @property
    def cli_name(self) -> str:
        return self.name.replace(".", "-")

    @property
    def mcp_name(self) -> str:
        return self.name.replace(".", "_")


def _is_mutation(group: Group) -> bool:
    return group in (Group.MUTATION, Group.LIFECYCLE)


def _op(
    name: str,
    group: Group,
    posture: Posture,
    summary: str,
    args: tuple[ArgSpec, ...] = (),
    examples: tuple[str, ...] = (),
) -> Operation:
    return Operation(
        name=name,
        group=group,
        posture=posture,
        summary=summary,
        args=args,
        examples=examples,
        mcp_exposed=(group != Group.LIFECYCLE),
        mutation_tool=_is_mutation(group),
    )


A = ArgSpec

OPERATIONS: tuple[Operation, ...] = (
    # ---- Public read groups (§6) -----------------------------------------------------
    _op(
        "help",
        Group.READ,
        Posture.SAFE,
        "Rank operations/workflows for a plain-English request. Never invokes an operation.",
        args=(A("request", ArgType.STR, help="Plain-English description of what you want to do"),),
        examples=("operator-voice help --request \"make this slack message sound like me\"",),
    ),
    _op(
        "status",
        Group.READ,
        Posture.SAFE,
        "Redacted runtime/profile status with active operator subject ids, consumer-id hint, state, and next step.",
    ),
    _op(
        "doctor",
        Group.READ,
        Posture.SAFE,
        "Verify runtime health and surface active operator subject ids plus the required consumer-id hint.",
    ),
    _op(
        "config.view",
        Group.READ,
        Posture.SAFE,
        "View redacted capability flags, policy versions, provider/write posture, registration health.",
    ),
    _op(
        "subject.list",
        Group.READ,
        Posture.SAFE,
        "List registered subjects (operator + any enrolled external subjects) with redacted state.",
    ),
    _op(
        "profile.inspect",
        Group.READ,
        Posture.SAFE,
        "Explain a subject's fact states and generation history in plain language.",
        args=(
            A("subject_id", ArgType.STR),
            A("facet", ArgType.STR, required=False, help="Limit to one facet"),
        ),
    ),
    _op(
        "profile.search",
        Group.READ,
        Posture.SAFE,
        "Search profile facts by facet/scope/state.",
        args=(
            A("subject_id", ArgType.STR),
            A("query", ArgType.STR, required=False, default=""),
        ),
    ),
    _op(
        "context.get",
        Group.READ,
        Posture.SAFE,
        "Return a bounded VoiceContextBundle/v1 for an OPERATOR subject. Never raw samples by default.",
        args=(
            A(
                "subject_id", ArgType.STR, required=False, default=None,
                help="Opaque subj_* id; defaults only when exactly one active OPERATOR subject exists",
            ),
            A("consumer_id", ArgType.STR, help="Required agent/tool name used for audit provenance"),
            A("channel", ArgType.STR, required=False, default="general"),
            A("audience", ArgType.STR, required=False, default="general"),
            A("purpose", ArgType.STR, required=False, default="general"),
            A("language", ArgType.STR, required=False, default="en"),
            A("output_type", ArgType.STR, required=False, default="text"),
            A("token_budget", ArgType.INT, required=False, default=800,
              help="Estimated token limit for the whole compact JSON payload; whole number from 200 to 999999999999"),
            A("accepted_major_versions", ArgType.JSON, required=False, default=None,
              help="JSON list of bundle majors the consumer accepts (e.g. [\"v1\"]); negotiation fails closed if none match"),
        ),
        examples=("operator-voice context-get --consumer-id demo-cli",),
    ),
    _op(
        "subject.insights",
        Group.READ,
        Posture.SAFE,
        "Return a SubjectInsightBundle/v1 for an EXTERNAL subject. Refuses for OPERATOR subjects.",
        args=(A("subject_id", ArgType.STR), A("purpose", ArgType.STR)),
    ),
    _op(
        "draft.validate",
        Group.READ,
        Posture.SAFE,
        "Validate a draft against a subject's profile. Deterministic checks (banned phrases, "
        "required/forbidden facts, style fit) always run; with semantic=true a high-stakes draft "
        "also gets an independent semantic/factual comparison — only a passing one yields validated.",
        args=(
            A("subject_id", ArgType.STR),
            A("draft_text", ArgType.STR),
            A("source_brief", ArgType.STR, required=False, default=""),
            A("required_facts", ArgType.JSON, required=False, default=None, help="JSON list of facts that MUST appear verbatim"),
            A("forbidden_facts", ArgType.JSON, required=False, default=None, help="JSON list of claims that must NOT appear (injected-fact block)"),
            A("semantic", ArgType.BOOL, required=False, default=False, help="Request a high-stakes semantic/factual review via the gateway"),
        ),
    ),
    _op(
        "audit.read",
        Group.READ,
        Posture.SAFE,
        "Read the content-free metadata audit journal.",
        args=(A("limit", ArgType.INT, required=False, default=50),),
    ),
    _op(
        "profile.backend_status",
        Group.READ,
        Posture.SAFE,
        "Report LOCAL_ONLY vs ENCRYPTED_GIT backend configuration and health.",
    ),
    _op(
        "profile.sync_status",
        Group.READ,
        Posture.SAFE,
        "Report local/remote generation and publish status (ENCRYPTED_GIT only).",
    ),
    _op(
        "review.list",
        Group.READ,
        Posture.SAFE,
        "List deterministic operator review items (contradictions, drift, single-source, low "
        "confidence) that need a human decision before a profile change is trusted.",
        args=(
            A("subject_id", ArgType.STR, required=False, default=None),
            A("status", ArgType.STR, required=False, default="OPEN", choices=("OPEN", "RESOLVED", "DISMISSED")),
        ),
    ),
    _op(
        "curation.status",
        Group.READ,
        Posture.SAFE,
        "Report continual-curation health: recent tick history (status/counts/catch-up gap/recovered "
        "runs), per-source watermarks and consecutive-failure counts, and the learning snapshot. "
        "Content-free — counts, enums, and timestamps only.",
        args=(A("limit", ArgType.INT, required=False, default=10, help="How many recent runs to include"),),
    ),
    _op(
        "learning.status",
        Group.READ,
        Posture.SAFE,
        "Plain-language 'is the toolkit still learning me?' snapshot: operator corrections recorded, "
        "how many were taken up (correction-uptake), and the open plain-language review queue.",
    ),
    _op(
        "schedule.plan",
        Group.READ,
        Posture.SAFE,
        "Print supported local-jobs commands to retain local curation on demand and retire its independent timer. "
        "The connected host owns the daily cycle. This operation is read-only.",
        args=(
            A("interval_seconds", ArgType.INT, required=False, default=86400,
              help="Deprecated compatibility input; no passive timer is created."),
            A("per_source_limit", ArgType.INT, required=False, default=None,
              help="Optional bounded per-source candidate cap for large catch-up backlogs."),
        ),
        examples=("operator-voice schedule-plan",),
    ),
    _op(
        "gateway.status",
        Group.READ,
        Posture.SAFE,
        "Report model-gateway policy: BOTH egress switches (operator + separate EXTERNAL), "
        "provider/model, allowed data classes. Disabled by default; the kernel never needs it.",
    ),
    _op(
        "gateway.calls",
        Group.READ,
        Posture.SAFE,
        "Read the content-free model-call ledger (provider/model/data-class/outcome/duration). "
        "Metadata only — never any signal payload (zero payload retention).",
        args=(A("limit", ArgType.INT, required=False, default=50),),
    ),
    _op(
        "dashboard.data",
        Group.READ,
        Posture.SAFE,
        "Return a redacted, content-free status snapshot (runtime posture, subject/fact/review "
        "counts, sync + EXTERNAL-egress state) for the render-only Cursor dashboard. Pure read: "
        "never mutates OVT state, never surfaces fact values, raw text, or an EXTERNAL subject's name.",
    ),
    # ---- Public mutation groups (§6) --------------------------------------------------
    _op(
        "config.set",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Set a machine-local configuration value (never profile-pack or governed-repo data).",
        args=(A("key", ArgType.STR), A("value", ArgType.STR)),
    ),
    _op(
        "subject.add",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Register a new subject (OPERATOR or, with explicit purposes, EXTERNAL).",
        args=(
            A("display_label", ArgType.STR),
            A("kind", ArgType.STR, required=False, default="OPERATOR", choices=("OPERATOR", "EXTERNAL")),
            A("purposes", ArgType.JSON, required=False, default=None, help="JSON list of approved purposes"),
        ),
    ),
    _op(
        "subject.pause",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Pause a subject (reversible).",
        args=(A("subject_id", ArgType.STR),),
    ),
    _op(
        "subject.alias_add",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Enroll a stable source-native identifier (operator-attested) for an EXTERNAL subject so "
        "analysis keys off a verified identifier, not a display name. Collisions with another "
        "subject are quarantined for review, never silently re-pointed.",
        args=(
            A("subject_id", ArgType.STR),
            A("source_type", ArgType.STR, help="Source the identifier comes from (e.g. slack_export, gmail_export)"),
            A("source_native_id", ArgType.STR, help="The source's own stable identifier for this person"),
            A("confidence", ArgType.FLOAT, required=False, default=1.0),
        ),
    ),
    _op(
        "source.add",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Register a source. No source ships enabled — this call is the explicit opt-in.",
        args=(
            A("subject_id", ArgType.STR),
            A("adapter_type", ArgType.STR, choices=(
                "slack_export", "drive_export", "gmail_export",
            )),
            A("canonical_root", ArgType.STR),
            A("approved_purpose", ArgType.STR, required=False, default="voice_generation"),
        ),
    ),
    _op(
        "source.pause",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Pause a source (reversible; per-source off switch).",
        args=(A("source_id", ArgType.STR),),
    ),
    _op(
        "slack.import",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Materialize an agent-submitted batch of your OWN Slack messages (captured agent-side "
        "via the Slack MCP; never called from here) into the local slack_export directory. "
        "Authorship is verified server-side per message against the top-level author_id — a "
        "mismatch is dropped, never accepted. Accepts the {author_id, messages} envelope inline "
        "or via --file; the CLI also falls back to stdin if neither is given.",
        args=(
            A("author_id", ArgType.STR, required=False, default=None,
              help="Your own Slack user id (self-asserted; verified per-message server-side)"),
            A("messages", ArgType.JSON, required=False, default=None,
              help="JSON list of {channel, message_ts, time, text, author_id} — alternative to --file"),
            A("file", ArgType.STR, required=False, default=None,
              help="Path to a JSON file containing {author_id, messages} (CLI convenience)"),
        ),
        examples=("operator-voice slack-import --file /tmp/slack-envelope.json",),
    ),
    _op(
        "slack.status",
        Group.READ,
        Posture.SAFE,
        "Content-free Slack-voice freshness snapshot: message counts by channel, when you last "
        "ran slack.import, and a stale/fresh verdict. CLI-only: pass --brief for one plain-text "
        "line suited to a session-start hook instead of full JSON.",
        examples=("operator-voice slack-status", "operator-voice slack-status --brief"),
    ),
    _op(
        "drive.folder_add", Group.MUTATION, Posture.REVERSIBLE,
        "Register a Drive folder containing your own writing. Google Docs in its subfolders are included; folder shortcuts are never followed.",
        args=(A("folder_id", ArgType.STR, help="The operator-selected Drive folder id"),),
        examples=("operator-voice drive-folder_add --folder-id <id>",),
    ),
    _op(
        "drive.folder_remove", Group.MUTATION, Posture.REVERSIBLE,
        "Stop learning from a registered Drive folder. Stored evidence remains until reextract or explicit erasure.",
        args=(A("folder_id", ArgType.STR, help="The registered Drive folder id"),),
        examples=("operator-voice drive-folder_remove --folder-id <id>",),
    ),
    _op(
        "drive.import",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Materialize your own Google Docs from registered folders and their subfolders, including "
        "resolved Doc shortcut targets (never folder shortcuts). "
        "(fetched agent-side via your host Drive tools; never called from here — no OVT Google "
        "credentials) into the local drive_export directory. Ownership is verified server-side per "
        "file: it must be a My-Drive item (drive_id null) owned solely by you (owners == [your "
        "owner_id]) — a Shared-Drive, multi-owner, or mismatched file is dropped, never accepted. "
        "Each revision is stored as its own immutable file (identity is file_id alone; revision is "
        "provenance). Accepts the {owner_id, sync_cursor, files} envelope inline or via --file; the "
        "CLI also falls back to stdin if neither is given.",
        args=(
            A("owner_id", ArgType.STR, required=False, default=None,
              help="Your own Drive user id (self-asserted; verified per-file server-side)"),
            A("files", ArgType.JSON, required=False, default=None,
              help="JSON list of {file_id, revision_id, drive_id, owners, mime_type, modified_time, "
                   "owner_id, text, folder_id, via_shortcut?} — folder_id is the registered ancestor; "
                   "shortcut entries carry the target's own metadata and text — alternative to --file"),
            A("sync_cursor", ArgType.JSON, required=False, default=None,
              help="Opaque Drive Changes sync token {changes_page_token, new_start_page_token} to "
                   "persist for the next incremental refresh (read back from drive.status)"),
            A("file", ArgType.STR, required=False, default=None,
              help="Path to a JSON file containing {owner_id, sync_cursor, files} (CLI convenience)"),
        ),
        examples=("operator-voice drive-import --file /tmp/drive-envelope.json",),
    ),
    _op(
        "drive.status",
        Group.READ,
        Posture.SAFE,
        "Content-free Drive-voice freshness snapshot: file/revision counts, the persisted sync "
        "cursor to resume from, when you last ran drive.import, and a stale/fresh verdict. CLI-only: "
        "pass --brief for one plain-text line suited to a session-start hook instead of full JSON.",
        examples=("operator-voice drive-status", "operator-voice drive-status --brief"),
    ),
    _op(
        "gmail.import",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Materialize an agent-submitted batch of your OWN Sent Gmail messages (fetched agent-side "
        "via your host Gmail tools; never called from here — no OVT Google credentials) into the "
        "local gmail_export directory. Authorship is verified server-side per message: each message's "
        "from and any Sender address must match author_email ignoring case; labels must include SENT "
        "and exclude DRAFT/CHAT, and Auto-Submitted must be no when present. Only own text is stored. Accepts "
        "the {author_email, sync_cursor, messages} envelope inline or via --file; the CLI also falls "
        "back to stdin if neither is given.",
        args=(
            A("author_email", ArgType.STR, required=False, default=None,
              help="Your own email address (self-asserted; verified per-message server-side)"),
            A("messages", ArgType.JSON, required=False, default=None,
              help="JSON list of {message_id, thread_id, internal_date, from, subject, text, labels, sender, auto_submitted}; include label ids, Sender and Auto-Submitted headers when present"),
            A("sync_cursor", ArgType.JSON, required=False, default=None,
              help="Agent-side Gmail historyId cursor to persist for the next incremental refresh"),
            A("file", ArgType.STR, required=False, default=None,
              help="Path to a JSON file containing {author_email, sync_cursor, messages}"),
        ),
        examples=("operator-voice gmail-import < sent-envelope.json",),
    ),
    _op("cycle.status", Group.READ, Posture.SAFE,
        "Daily refresh due state, per-source completion and actionable aggregate notices; no fetch."),
    _op("cycle.configure", Group.MUTATION, Posture.SAFE,
        "Enroll the authorized daily host workflow and pin connected account identities by HMAC. "
        "Does not create a timer, fetch writing, or silently replace an enrolled account.",
        args=(A("identities", ArgType.JSON, required=False, help="Fresh slack/gmail/drive identities; keep private"),
              A("file", ArgType.STR, required=False, help="Private JSON file containing identities"),
              A("timezone", ArgType.STR, required=False, default="America/Los_Angeles", help="IANA timezone"),
              A("hour", ArgType.INT, required=False, default=18, help="Daily local hour, 0..23"),
              A("paused", ArgType.BOOL, required=False, default=False, help="Pause the enrolled cycle"))),
    _op("cycle.identity", Group.READ, Posture.SAFE,
        "Verify the fresh connector identity against daily enrollment before fetching; never print identifiers.",
        args=(A("integration", ArgType.STR), A("identity", ArgType.STR))),
    _op("cycle.begin", Group.MUTATION, Posture.SAFE,
        "Claim one daily refresh or due retry; return private paging checkpoints. Busy/off/not-due is inert.",
        args=(A("force", ArgType.BOOL, required=False, default=False, help="Explicit refresh now"),)),
    _op("cycle.record", Group.MUTATION, Posture.SAFE,
        "Record one host-attested source outcome after durable import. Success requires exhaustive paging; "
        "incomplete results never advance a successful fetch checkpoint.",
        args=(A("run_id", ArgType.STR), A("integration", ArgType.STR), A("outcome", ArgType.STR),
              A("counts", ArgType.JSON, required=False, help="Fetched/imported/duplicates/filtered/pages counts"),
              A("checkpoint", ArgType.JSON, required=False, help="Opaque private provider continuation, never text"))),
    _op("cycle.finish", Group.MUTATION, Posture.SAFE,
        "Curate durable imports under the cycle lock, publish changed or pending evidence, and schedule bounded recovery.",
        args=(A("run_id", ArgType.STR),)),
    _op("cycle.acknowledge", Group.MUTATION, Posture.SAFE,
        "Acknowledge only notices actually delivered, preventing repeat notifications for the same episode.",
        args=(A("notices", ArgType.JSON),)),
    _op("capture.inventory", Group.READ, Posture.SAFE,
        "Private text-free imported record identities, revisions and registered Drive folders for incremental host fetch. "
        "Contains operational identifiers: capture privately, report aggregates only.",
        args=(A("integration", ArgType.STR),)),
    _op(
        "refresh.offer",
        Group.MUTATION,
        Posture.SAFE,
        "Legacy answer audit only. Weekly offers are retired by daily-cycle policy; this never fetches evidence.",
        args=(
            A("integration", ArgType.STR, required=True, help="slack, gmail or drive"),
            A("answer", ArgType.STR, required=True, help="yes or no"),
        ),
        examples=("operator-voice refresh-offer --integration slack --answer no",),
    ),
    _op(
        "gmail.status",
        Group.READ,
        Posture.SAFE,
        "Content-free Gmail-voice freshness and coverage snapshot: stored and eligible message counts, the persisted historyId cursor "
        "to resume from, when you last ran gmail.import, and a stale/fresh verdict. CLI-only: pass "
        "--brief for one plain-text line suited to a session-start hook instead of full JSON.",
        examples=("operator-voice gmail-status", "operator-voice gmail-status --brief"),
    ),
    _op(
        "google.status",
        Group.READ,
        Posture.SAFE,
        "Content-free combined Drive + Gmail freshness snapshot: aggregates the local drive.status "
        "and gmail.status snapshots into one stale/fresh verdict and dashboard line. Still no OVT-side "
        "Google calls — reads only persisted import state already on disk. CLI-only: pass --brief for "
        "one plain-text line suited to a session-start hook instead of full JSON.",
        examples=("operator-voice google-status", "operator-voice google-status --brief"),
    ),
    _op(
        "ingest",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Run one adapter scan + kernel pipeline over a registered, active source.",
        args=(A("source_id", ArgType.STR),),
    ),
    _op(
        "curate",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Run one continual-curation tick over every active source: incremental (per-source cursor) "
        "ingest, catch-up after downtime, strict idempotency, stale-run recovery, then a conditional "
        "ENCRYPTED_GIT publish (LOCAL_ONLY performs no network). This is the single verb the one "
        "local-jobs command instance invokes on a schedule; it is also safe to run by hand.",
        args=(
            A("trigger", ArgType.STR, required=False, default=None, choices=("manual", "scheduled"),
              help="Who invoked this tick. Defaults to $OVT_CURATE_TRIGGER (set by the local-jobs "
                   "instance) else 'manual'."),
            A("per_source_limit", ArgType.INT, required=False, default=None,
              help="Max candidates ingested per source this tick (bounded continuation for large "
                   "catch-up backlogs). Defaults to $OVT_CURATE_PER_SOURCE_LIMIT else unbounded."),
        ),
        examples=(
            "operator-voice curate",
            "operator-voice curate --trigger scheduled --per-source-limit 500",
        ),
    ),
    _op(
        "feedback.add",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Record plain-language feedback; classified into confirm/correct/reject/ban/scope/identity/source.",
        args=(
            A("subject_id", ArgType.STR),
            A("utterance", ArgType.STR),
            A("target_fact_id", ArgType.STR, required=False, default=None),
        ),
    ),
    _op(
        "fact.correct",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Explicit correction/ban. Highest precedence; supersedes prior states for this facet/scope.",
        args=(
            A("subject_id", ArgType.STR),
            A("facet", ArgType.STR),
            A("new_value", ArgType.JSON),
            A("reason", ArgType.STR, required=False, default="operator correction"),
        ),
    ),
    _op(
        "fact.deprecate",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Reversibly supersede/disable a fact. Evidence remains.",
        args=(A("fact_id", ArgType.STR), A("reason", ArgType.STR, required=False, default="")),
    ),
    _op(
        "review.resolve",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Resolve or dismiss an operator review item. Records the operator's decision; does not "
        "itself mutate any fact (use fact.correct/fact.deprecate for that).",
        args=(
            A("review_id", ArgType.STR),
            A("status", ArgType.STR, required=False, default="RESOLVED", choices=("RESOLVED", "DISMISSED")),
            A("resolution", ArgType.STR, required=False, default=""),
        ),
    ),
    _op(
        "gateway.configure",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Set model-gateway policy (provider/model/data-class allowlist, timeout). BOTH egress "
        "switches are explicit and default OFF; enabling operator egress never enables EXTERNAL "
        "egress — that is a separate explicit switch. Raw/quarantined can never be allowlisted.",
        args=(
            A("provider", ArgType.STR, required=False, default=None),
            A("model", ArgType.STR, required=False, default=None),
            A("allowed_data_classes", ArgType.JSON, required=False, default=None, help="JSON list of allowed data classes"),
            A("enable_operator_egress", ArgType.BOOL, required=False, default=False),
            A("enable_external_egress", ArgType.BOOL, required=False, default=False,
              help="A separate switch from operator egress; it must be turned on explicitly and stays off by default."),
            A("timeout_ms", ArgType.INT, required=False, default=20000),
        ),
    ),
    _op(
        "profile.publish",
        Group.MUTATION,
        Posture.SAFE,
        "Validate/encrypt/deliver the latest local generation to the configured ENCRYPTED_GIT backend.",
    ),
    _op(
        "profile.pull",
        Group.MUTATION,
        Posture.SAFE,
        "Fetch the configured remote's head; refuses on divergent conflicting heads.",
    ),
    _op(
        "profile.restore",
        Group.MUTATION,
        Posture.SAFE,
        "Clone the configured remote and rebuild local sync state from its published manifest.",
    ),
    _op(
        "profile.reconcile",
        Group.MUTATION,
        Posture.SAFE,
        "Reconcile the ENCRYPTED_GIT profile replica against the remote head: merge disjoint typed "
        "changes deterministically; a conflicting correction or identity change is queued for "
        "review, never auto-merged. Never force-pushes. LOCAL_ONLY is unaffected (skipped).",
    ),
    _op(
        "export",
        Group.MUTATION,
        Posture.CONSEQUENTIAL,
        "Produce a human-readable ExportManifest of minimum-necessary facts. Sensitive export: requires challenge.",
        args=(
            A("subject_id", ArgType.STR),
            A("scope", ArgType.STR, required=False, default="all"),
            A("destination", ArgType.STR),
            A("challenge_literal", ArgType.STR, required=False, default=None),
        ),
    ),
    _op(
        "erase",
        Group.MUTATION,
        Posture.CONSEQUENTIAL,
        "Irreversibly erase a scope (fact|source|validation_set|model_call_payload|export_under_control|full_system).",
        args=(
            A("scope", ArgType.STR, choices=(
                "fact", "source", "validation_set", "model_call_payload",
                "export_under_control", "full_system",
            )),
            A("target", ArgType.STR, required=False, default=None),
            A("challenge_literal", ArgType.STR, required=False, default=None),
        ),
    ),
    _op(
        "rebuild",
        Group.MUTATION,
        Posture.SAFE,
        "Recreate a ProfileGeneration from retained evidence using its pinned version bundle.",
        args=(A("generation_id", ArgType.STR),),
    ),
    _op(
        "reextract", Group.MUTATION, Posture.CONSEQUENTIAL,
        "Preview or reextract stored writing using current methods. A verified backup precedes changes; corrections remain authoritative.",
        args=(A("subject_id", ArgType.STR), A("dry_run", ArgType.BOOL, required=False, default=False),
              A("challenge_literal", ArgType.STR, required=False)),
    ),
    _op(
        "backup.restore", Group.MUTATION, Posture.CONSEQUENTIAL,
        "Restore a verified local database snapshot while other OVT processes are stopped. Older snapshots may restore erased evidence and require an additional literal.",
        args=(A("backup_path", ArgType.STR, required=False), A("dry_run", ArgType.BOOL, required=False, default=False),
              A("challenge_literal", ArgType.STR, required=False), A("erased_evidence_literal", ArgType.STR, required=False)),
    ),
    _op(
        "reanalyze",
        Group.MUTATION,
        Posture.SAFE,
        "Apply the current (newer) method to retained source content; creates a new generation + diff.",
        args=(A("subject_id", ArgType.STR),),
    ),
    _op(
        "retention.set",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Set a retention policy value.",
        args=(A("policy_name", ArgType.STR), A("days", ArgType.INT)),
    ),
    _op(
        "off",
        Group.MUTATION,
        Posture.REVERSIBLE,
        "Persist disabled mode, close model egress, cancel active operations at checkpoints.",
        args=(A("reason", ArgType.STR, required=False, default=""),),
    ),
    _op(
        "on",
        Group.MUTATION,
        Posture.SAFE,
        "Re-enable. Never restores previously erased data.",
    ),
    # ---- CLI-only lifecycle exceptions (§6, D13) --------------------------------------
    _op(
        "setup",
        Group.LIFECYCLE,
        Posture.SAFE,
        "First-run setup: create local encrypted state, KEK in Keychain, and best-effort registration "
        "of the single on-demand curation local-jobs instance when that skill is installed. Fresh installs "
        "start LOCAL_ONLY.",
        args=(A("display_label", ArgType.STR, required=False, default="operator"),),
    ),
    _op(
        "profile.remote_bind",
        Group.LIFECYCLE,
        Posture.CONSEQUENTIAL,
        "Bind an encrypted private-Git backend so your profile can be published for backup and "
        "cross-machine use. This does not itself run a recovery drill: separately do one clean-machine "
        "recovery with your real recovery key before you rely on this backend to survive machine loss.",
        args=(
            A("remote_url", ArgType.STR),
            A("challenge_literal", ArgType.STR, required=False, default=None),
        ),
    ),
    _op(
        "profile.remote_remove",
        Group.LIFECYCLE,
        Posture.REVERSIBLE,
        "Unbind the remote backend and return to LOCAL_ONLY. Local generations are kept.",
    ),
    _op(
        "key.recover",
        Group.LIFECYCLE,
        Posture.SAFE,
        "Restore the profile-pack wrapping key from the operator-controlled recovery destination.",
        args=(A("recovery_material", ArgType.STR),),
    ),
    _op(
        "portability.export",
        Group.LIFECYCLE,
        Posture.CONSEQUENTIAL,
        "Write a passphrase-encrypted (scrypt + AES-256-GCM) portable copy of the profile — "
        "subjects, facts, corrections, aliases, generations, and profile-pack keys — for moving to "
        "another machine. Sensitive export: requires confirmation. The passphrase is never stored.",
        args=(
            A("destination", ArgType.STR, help="File path to write the encrypted archive to"),
            A("passphrase", ArgType.STR, help="Operator passphrase (>=8 chars); not stored anywhere"),
            A("subject_id", ArgType.STR, required=False, default=None, help="Limit to one subject (default: all)"),
            A("challenge_literal", ArgType.STR, required=False, default=None),
        ),
        examples=(
            "operator-voice portability-export --destination ./my-profile.ovtpack "
            "--passphrase 'correct-horse-battery-staple'",
        ),
    ),
    _op(
        "portability.import",
        Group.LIFECYCLE,
        Posture.REVERSIBLE,
        "Import a passphrase-encrypted portable profile onto this machine. Additive and protective: "
        "your operator corrections/confirmations are never overwritten; a wrong passphrase or "
        "tampered archive is refused. Profile-pack keys are re-wrapped under this machine's key.",
        args=(
            A("source", ArgType.STR, help="Path to the encrypted archive produced by portability.export"),
            A("passphrase", ArgType.STR, help="The passphrase used at export time"),
        ),
    ),
    _op(
        "key.rotate",
        Group.LIFECYCLE,
        Posture.CONSEQUENTIAL,
        (
            "Mint a fresh data-encryption key for the given purpose and destroy the previous one. "
            "Anything still encrypted under the old key (for example an already-published profile "
            "copy) becomes permanently unreadable — this is the intended 'crypto-shredding' effect "
            "of rotating/destroying a key."
        ),
        args=(
            A("purpose", ArgType.STR, required=False, default="content", choices=("content", "profile_pack")),
            A("challenge_literal", ArgType.STR, required=False, default=None),
        ),
    ),
    _op(
        "repair",
        Group.LIFECYCLE,
        Posture.SAFE,
        "Verify/replace the runtime payload only. Never touches config, state, backend, or keys.",
    ),
    _op(
        "uninstall",
        Group.LIFECYCLE,
        Posture.CONSEQUENTIAL,
        "Remove the installed runtime payload. Profile data/config/keys are untouched.",
        args=(A("challenge_literal", ArgType.STR, required=False, default=None),),
    ),
)

OPERATIONS_BY_NAME: dict[str, Operation] = {op.name: op for op in OPERATIONS}


def get_operation(name: str) -> Operation:
    try:
        return OPERATIONS_BY_NAME[name]
    except KeyError:
        raise KeyError(f"unknown operation: {name!r}") from None


def public_operations() -> list[Operation]:
    return [op for op in OPERATIONS if op.group != Group.LIFECYCLE]


def mcp_operations(mutations_enabled: bool) -> list[Operation]:
    """§6: 'Agent-facing MCP registration is read-only by default. Mutation tools are hidden
    unless explicitly enabled.'"""
    return [
        op
        for op in OPERATIONS
        if op.mcp_exposed and (not op.mutation_tool or mutations_enabled)
    ]
