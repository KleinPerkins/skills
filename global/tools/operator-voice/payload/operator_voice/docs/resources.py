"""Typed, versioned resource registry — build plan v3 §6: "Resources and prompts are not inferred
from operation names. They live in separate typed, versioned ``ResourceSpec`` ... registries."

M1 ships only the **core** guidance/status subset named in its worklist ("core guidance/status
resources"); the remaining static resources (`/context-bundle`, `/external-subjects`,
`/template-integration`) and the `/learning` dynamic resource are M2 scope (richer calibrated
signals + frozen bundle contract) and are declared here with ``tier="m2"`` so the registry is
already complete, but :data:`M1_RESOURCE_URIS` is what M1's MCP server actually exposes.

No resource exposes raw text, profile values, keys, secrets, or source paths (§6) — every dynamic
resource builder below returns only counts, enums, booleans, and timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

RESOURCES_VERSION = "resources/v1"

Tier = Literal["m1", "m2", "m3", "m4"]


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    title: str
    description: str
    dynamic: bool  # False = static guidance text; True = built per-request from live (redacted) state
    tier: Tier


STATIC_RESOURCES: tuple[ResourceSpec, ...] = (
    ResourceSpec(
        "ovt://guidance/getting-started",
        "Getting started",
        "How to run setup, add a source, ingest, and request a voice-matched draft.",
        dynamic=False,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://guidance/safety",
        "Safety model",
        "LOCAL_ONLY default, consequence challenges, off/erase, and what OVT never does automatically.",
        dynamic=False,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://guidance/continual-learning",
        "How OVT learns",
        "Direct feedback beats inference; sources are opt-in; third-party text is never operator evidence.",
        dynamic=False,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://guidance/feedback",
        "Giving feedback",
        "How to say 'that's wrong' / 'I'd say it differently' in plain language and what happens next.",
        dynamic=False,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://guidance/context-bundle",
        "VoiceContextBundle guide",
        "Fields, token budgeting, and abstention behavior of the bundle returned by `context.get`.",
        dynamic=False,
        tier="m2",
    ),
    ResourceSpec(
        "ovt://guidance/external-subjects",
        "External-subject analysis",
        "Why external-person analysis requires explicit enrollment and never produces authoring instructions.",
        dynamic=False,
        tier="m2",
    ),
    ResourceSpec(
        "ovt://guidance/template-integration",
        "Template Framework integration",
        "How a consuming template contract consumes a bundle without importing OVT internals.",
        dynamic=False,
        tier="m2",
    ),
)

DYNAMIC_RESOURCES: tuple[ResourceSpec, ...] = (
    ResourceSpec(
        "ovt://status/profile",
        "Profile status",
        "Redacted subject/fact counts and generation state.",
        dynamic=True,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://status/sources",
        "Source status",
        "Redacted per-source adapter type, active/paused state, and last-ingest time.",
        dynamic=True,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://status/sync",
        "Backend sync status",
        "LOCAL_ONLY vs ENCRYPTED_GIT, and (if configured) local/remote generation parity.",
        dynamic=True,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://status/environment",
        "Environment/capability status",
        "Redacted capability flags, schema version, and gateway posture (never a raw path or key).",
        dynamic=True,
        tier="m1",
    ),
    ResourceSpec(
        "ovt://status/learning",
        "Learning status",
        "Calibration/drift summary across contexts plus correction-uptake (M3: how many operator "
        "corrections were recorded and taken up).",
        dynamic=True,
        tier="m2",
    ),
    ResourceSpec(
        "ovt://status/curation",
        "Continual-curation status",
        "Recent passive-curation tick history (status/counts/catch-up gap/recovered runs) and "
        "per-source watermarks. Content-free — counts, enums, and timestamps only.",
        dynamic=True,
        tier="m3",
    ),
    ResourceSpec(
        "ovt://status/dashboard",
        "Dashboard snapshot",
        "Redacted, content-free status snapshot backing the render-only Cursor dashboard: runtime "
        "posture, subject/fact/review counts, sync + EXTERNAL-egress state. Never a fact value, raw "
        "text, or an EXTERNAL subject's name.",
        dynamic=True,
        tier="m4",
    ),
)

ALL_RESOURCES: tuple[ResourceSpec, ...] = STATIC_RESOURCES + DYNAMIC_RESOURCES
RESOURCES_BY_URI: dict[str, ResourceSpec] = {r.uri: r for r in ALL_RESOURCES}
M1_RESOURCE_URIS: frozenset[str] = frozenset(r.uri for r in ALL_RESOURCES if r.tier == "m1")
# M2 activates the full registry (build plan §13 M2 worklist 2 "full resources/prompts/generated
# docs"). Every resource now has backing text (static) or a builder (dynamic); the MCP server
# exposes exactly this set.
ACTIVE_RESOURCE_URIS: frozenset[str] = frozenset(r.uri for r in ALL_RESOURCES)

_STATIC_TEXT: dict[str, str] = {
    "ovt://guidance/getting-started": (
        "1. `operator-voice setup` — creates local encrypted state; starts LOCAL_ONLY.\n"
        "2. Import your own writing through Slack, Gmail or Google Drive; use "
        "`operator-voice source-add --subject-id <id> --adapter-type slack_export --canonical-root <dir>` "
        "for an existing Slack export. Agent chats and local notes are retired.\n"
        "3. `operator-voice ingest --source-id <id>` — run one scan + pipeline pass.\n"
        "4. `operator-voice context-get --subject-id <id> --consumer-id <name>` — get a bounded "
        "VoiceContextBundle to draft from.\n"
        "5. `operator-voice draft-validate ...` — mechanically check a draft against the profile.\n"
        "6. Say what's wrong in plain language (`feedback.add`) — direct correction always wins."
    ),
    "ovt://guidance/safety": (
        "Every install starts LOCAL_ONLY: nothing leaves the machine by default. Destructive, "
        "irreversible, shared-reference, or sensitive-export operations (erase, export, "
        "profile_remote_bind, uninstall) require a preview + a one-use, short plain-language "
        "challenge literal before they execute — this is enforced by the kernel, not by CLI/MCP "
        "wording. `off` disables collection/egress and cancels active operations at their next "
        "checkpoint; it never deletes data. `erase` is the only irreversible path, and it is scoped "
        "explicitly (fact | source | validation_set | model_call_payload | export_under_control | "
        "full_system)."
    ),
    "ovt://guidance/continual-learning": (
        "Direct feedback (`feedback.add`, `fact.correct`) always outranks anything OVT infers from "
        "ingested content. Sources are opt-in per adapter (`source.add`) and can be paused "
        "individually. Text correctly identified as written by someone other than the operator "
        "(quoted, forwarded, an assistant reply) never becomes operator voice evidence, even if it "
        "appears inside an otherwise-eligible document."
    ),
    "ovt://guidance/feedback": (
        "Tell OVT what's wrong in your own words — e.g. \"that's wrong, I never say it that way\" — "
        "via `feedback.add`. It is classified deterministically into confirm/correct/reject/ban/"
        "scope/identity/source. An explicit correction (`fact.correct`) has the highest precedence "
        "and supersedes prior inferred states for that facet/scope immediately."
    ),
    "ovt://guidance/context-bundle": (
        "`context.get` returns a VoiceContextBundle/v1: a bounded, ranked set of voice facts plus "
        "compact generative/corrective instructions. The token budget bounds the whole compact JSON "
        "payload (minimum 200). Corrections and confirmations precede inferred facts, with one value "
        "per facet except distinct banned phrases. Provenance ids are not inlined; inspect the "
        "generation through `profile-inspect --facet`. Exact and more-general context facts may be "
        "selected together; every selected relaxation is reported in `warnings`. If authoritative "
        "facts cannot fit, the bundle abstains with `minimum_budget_tokens:<n>`; retry once at that "
        "budget. Thin evidence also produces an abstention rather than a guess. Consumers "
        "may send `accepted_major_versions` (e.g. [\"v1\"]); an incompatible consumer is refused."
    ),
    "ovt://guidance/external-subjects": (
        "Analyzing someone who is NOT the operator requires registering that person as an EXTERNAL "
        "subject with an approved purpose and authoritative-authorship sources first — a display name "
        "alone never merges identities. EXTERNAL analysis returns only a SubjectInsightBundle "
        "(evidence-bounded observations with uncertainty and counter-evidence); OVT will NEVER emit a "
        "VoiceContextBundle or generation/authoring instructions for an EXTERNAL subject. EXTERNAL "
        "model egress is a SEPARATE switch that stays denied even when operator egress is enabled. "
        "Text identified as third-party, quoted, forwarded, AI-authored, or ambiguous contributes "
        "zero operator voice evidence."
    ),
    "ovt://guidance/template-integration": (
        "A template/authoring framework may consume VoiceContextBundle/v1 as transient authoring "
        "input at its authoring step only. The bundle is the ONLY shared artifact: the consumer reads "
        "the frozen JSON contract and never imports OVT internals, and OVT never imports template "
        "code, reads template IDs/storage, influences intent routing, or enters deterministic "
        "render/projection. Adoption is an independent, additive, removable cross-plan follow-on; "
        "neither system owns the other's state."
    ),
}


def render_resources_md() -> str:
    lines = ["<!-- GENERATED by operator_voice.docs.resources — do not hand-edit. -->\n",
             "# OVT MCP resources\n"]
    lines.append(
        "The full registry is active as of M2. No resource exposes raw text, profile values, keys, "
        "secrets, or paths — every dynamic resource returns only counts, enums, booleans, and "
        "timestamps.\n"
    )
    lines.append("| uri | kind | tier | description |")
    lines.append("|---|---|---|---|")
    for r in ALL_RESOURCES:
        kind = "dynamic" if r.dynamic else "static"
        lines.append(f"| `{r.uri}` | {kind} | {r.tier} | {r.description} |")
    return "\n".join(lines).rstrip() + "\n"


DynamicResourceBuilder = Callable[..., dict]


def build_status_profile(service) -> dict:
    return service.status()


def build_status_sources(service) -> dict:
    # M1 has no dedicated `source.list` operation; report what IS visible without a raw path or
    # adapter config — the registered-subject count is a safe, redacted proxy for "is anything set up."
    subjects = service.subject_list()["subjects"]
    return {"registered_subject_count": len(subjects), "active_subject_count": sum(1 for s in subjects if s["active"])}


def build_status_sync(service) -> dict:
    return service.profile_sync_status()


def build_status_environment(service) -> dict:
    return service.config_view()


def build_status_learning(service) -> dict:
    """M2 calibration/drift summary — redacted numbers and enums ONLY, never a fact value or raw
    text. Surfaces the open-review backlog by reason (low source diversity, drift, contradiction,
    …) so an agent can see where the profile is uncertain without ever reading profile content."""
    from operator_voice.eval.calibration_manifest import CALIBRATION_MANIFEST_VERSION

    reviews = service.review_list(status="OPEN")
    by_reason: dict[str, int] = {}
    for item in reviews.get("items", []):
        by_reason[item["reason"]] = by_reason.get(item["reason"], 0) + 1
    return {
        "open_review_count": reviews.get("count", 0),
        "open_reviews_by_reason": dict(sorted(by_reason.items())),
        "calibration_manifest_version": CALIBRATION_MANIFEST_VERSION,
        # M3 correction-uptake (operator feedback is P0 and must be visibly taken up).
        "correction_uptake": service.learning_status()["learning"],
    }


def build_status_curation(service) -> dict:
    """M3 continual-curation health — recent tick history + per-source watermarks, all content-free."""
    return service.curation_status()


def build_status_dashboard(service) -> dict:
    """M4 render-only dashboard snapshot — the exact read-only status source the `.canvas.tsx`
    dashboard renders. Content-free by construction (see ``service.dashboard_data``)."""
    return service.dashboard_data()


DYNAMIC_BUILDERS: dict[str, DynamicResourceBuilder] = {
    "ovt://status/profile": build_status_profile,
    "ovt://status/sources": build_status_sources,
    "ovt://status/sync": build_status_sync,
    "ovt://status/environment": build_status_environment,
    "ovt://status/learning": build_status_learning,
    "ovt://status/curation": build_status_curation,
    "ovt://status/dashboard": build_status_dashboard,
}


def read_resource(uri: str, service) -> str:
    """Returns the resource body as text (JSON for dynamic resources, plain text for static
    guidance). Raises ``KeyError`` for an unknown uri. The full registry is active in M2."""
    import json

    spec = RESOURCES_BY_URI.get(uri)
    if spec is None or spec.uri not in ACTIVE_RESOURCE_URIS:
        raise KeyError(f"unknown resource: {uri!r}")
    if not spec.dynamic:
        return _STATIC_TEXT[uri]
    builder = DYNAMIC_BUILDERS[uri]
    return json.dumps(builder(service), indent=2, default=str)


__all__ = [
    "ResourceSpec",
    "STATIC_RESOURCES",
    "DYNAMIC_RESOURCES",
    "ALL_RESOURCES",
    "RESOURCES_BY_URI",
    "M1_RESOURCE_URIS",
    "ACTIVE_RESOURCE_URIS",
    "render_resources_md",
    "read_resource",
]
