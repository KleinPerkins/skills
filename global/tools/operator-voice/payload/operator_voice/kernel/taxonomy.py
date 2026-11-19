"""Context taxonomy as data — build plan v4 §5 (``ContextTaxonomy``: "structured adaptation of
MYNAH — channel, audience class, purpose, output type, language, disambiguation rules, sensitivity
floor, and retrieval policy") and §13 M2 worklist item 1 ("Encode the adapted MYNAH taxonomy as
data; add language variants, context disambiguation, multi-context synthesis, ranking, and bleed
tests").

Provenance (forensic audit §6, take-table row "Context taxonomy"): MYNAH's ten-context
channel/audience segmentation and its per-context "watch for" disambiguation heuristics are
**re-authored here as structured data**, never as prose or copied source (NOTICE / audit
"Adapt — reuse the taxonomy ... re-author as structured data, not prose"). This module is pure
data + pure functions: no I/O, no model, no network (kernel purity, §7/D7).

The single hard retrieval-safety invariant this module encodes (build plan §13 M2 acceptance:
"Multi-context/language retrieval has no unreported bleed"):

  * A fact may satisfy a request scope EXACTLY, or via an explicitly-enumerated *relaxation*
    (a more-general value on a relaxable dimension, or a base-language fallback for a language
    variant). Every relaxation is reported to the caller as a named warning — there is no silent
    fallback.
  * Language NEVER bleeds across base languages. An ``es`` fact can never satisfy an ``en``
    request and vice-versa; only same-base-language variant fallback (``en-GB`` → ``en``) is
    permitted, and even that is reported.
  * Any fact whose scope is neither the exact request nor one of the enumerated relaxations is
    excluded as cross-context bleed — never blended in silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from operator_voice.domain.models import ContextScope

TAXONOMY_VERSION = "taxonomy/v2"

# --------------------------------------------------------------------------------------
# Canonical closed vocabularies (re-authored MYNAH segmentation). Unknown values are always
# ACCEPTED (never rejected) but never silently merged into a known bucket — see normalize_scope.
# --------------------------------------------------------------------------------------

# The "general" (least-specific) value each relaxable dimension relaxes toward. Language is
# deliberately absent: it is never relaxed to a generic bucket, only to its own base variant.
GENERAL_VALUES: dict[str, str] = {
    "channel": "general",
    "audience": "general",
    "purpose": "general",
    "output_type": "text",
}

# Dimensions that may relax toward their GENERAL_VALUES during retrieval, in the fixed priority
# order below (least-identity-bearing first). Channel is preserved longest because "how the
# operator writes" varies most by channel; output_type is relaxed first because it is the most
# interchangeable. This ordering is the deterministic ranking the acceptance criteria require.
RELAXATION_PRIORITY: tuple[str, ...] = ("output_type", "purpose", "audience", "channel")

CANONICAL: dict[str, frozenset[str]] = {
    "channel": frozenset(
        {"general", "slack", "email", "docs", "slides", "sms", "chat", "code_review", "issue"}
    ),
    "audience": frozenset(
        {"general", "peer", "report", "manager", "exec", "customer", "team", "public", "self"}
    ),
    "purpose": frozenset(
        {
            "general", "update", "decision", "persuasion", "announcement", "feedback",
            "brainstorm", "apology", "request", "explainer",
        }
    ),
    "output_type": frozenset(
        {"text", "message", "email", "doc", "slide", "comment", "summary", "reply"}
    ),
    "language": frozenset(
        {"en", "en-GB", "en-US", "es", "es-ES", "es-419", "fr", "de", "pt", "pt-BR", "it", "nl"}
    ),
}

# Conservative synonym -> canonical maps. Deliberately small and unambiguous (audit §6: reuse
# MYNAH's "explicit disambiguation heuristics"). A synonym only maps when there is exactly one
# obvious canonical target; anything genuinely ambiguous is left as-is for the operator to pin.
LEGACY_CHANNEL_LABELS = frozenset({"cursor", "artifact"})
SET_VALUED_FACETS = frozenset({"banned_phrase"})

SYNONYMS: dict[str, dict[str, str]] = {
    "channel": {
        "im": "slack", "dm": "slack", "e-mail": "email", "mail": "email", "gmail": "email",
        "document": "docs", "gdoc": "docs", "gdocs": "docs", "google_docs": "docs",
        "deck": "slides", "presentation": "slides", "text_message": "sms", "imessage": "sms",
        "pr": "code_review", "pull_request": "code_review", "mr": "code_review", "ticket": "issue",
        # Legacy adapter labels (M3) stored stylometric facts under source-type names; map to
        # the cross-context bucket retrieval actually considers for channel relaxation.
        "cursor": "general", "artifact": "general",
    },
    "audience": {
        "colleague": "peer", "coworker": "peer", "teammate": "peer", "direct_report": "report",
        "reports": "report", "boss": "manager", "leadership": "exec", "executive": "exec",
        "execs": "exec", "client": "customer", "customers": "customer", "external": "public",
        "everyone": "public", "myself": "self",
    },
    "purpose": {
        "status": "update", "status_update": "update", "decide": "decision", "proposal": "persuasion",
        "persuade": "persuasion", "convince": "persuasion", "announce": "announcement",
        "review": "feedback", "critique": "feedback", "ideate": "brainstorm", "sorry": "apology",
        "ask": "request", "explain": "explainer", "teach": "explainer",
    },
    "output_type": {
        "msg": "message", "chat_message": "message", "mail": "email", "document": "doc",
        "slide_deck": "slide", "deck": "slide", "comment": "comment", "tl;dr": "summary",
        "tldr": "summary", "response": "reply",
    },
    "language": {
        "english": "en", "en_us": "en-US", "en_gb": "en-GB", "spanish": "es", "es_es": "es-ES",
        "es_mx": "es-419", "french": "fr", "german": "de", "portuguese": "pt", "pt_br": "pt-BR",
        "italian": "it", "dutch": "nl",
    },
}

# Sensitivity floor per (dimension, value) — a minimum sensitivity classification that a context
# imposes regardless of the document's own sensitivity. Contexts that commonly carry regulated or
# personal content float their observations up to "elevated" so downstream policy (e.g. gateway
# data-class gating, M2.4) can treat them accordingly. Absent entries mean "standard".
SENSITIVITY_FLOOR: dict[tuple[str, str], str] = {
    ("audience", "customer"): "elevated",
    ("audience", "public"): "elevated",
    ("purpose", "apology"): "elevated",
    ("channel", "issue"): "elevated",
}


def disambiguate(dimension: str, value: str) -> str:
    """Map a raw value to its canonical form for ``dimension``. Case-folded synonym match first,
    then canonical passthrough; an unknown value is returned unchanged and lower-cased (never
    fuzzy-merged into a known bucket — ContextScope's own contract, §5)."""
    if not value:
        return GENERAL_VALUES.get(dimension, "en" if dimension == "language" else "general")
    raw = value.strip()
    folded = raw.lower()
    syn = SYNONYMS.get(dimension, {})
    if folded in syn:
        return syn[folded]
    canon = CANONICAL.get(dimension, frozenset())
    # Language canonical values are case-mixed (en-GB); match case-insensitively then return the
    # canonical spelling.
    for c in canon:
        if c.lower() == folded:
            return c
    return folded


def normalize_scope(scope: ContextScope) -> ContextScope:
    """Return a scope with every dimension disambiguated to canonical form. Unknown values pass
    through (lower-cased) unchanged."""
    return ContextScope(
        channel=disambiguate("channel", scope.channel),
        audience=disambiguate("audience", scope.audience),
        purpose=disambiguate("purpose", scope.purpose),
        language=disambiguate("language", scope.language),
        output_type=disambiguate("output_type", scope.output_type),
    )


def base_language(language: str) -> str:
    """Base-language family for a variant tag: ``en-GB`` -> ``en``, ``pt-BR`` -> ``pt``,
    ``es-419`` -> ``es``. A bare base tag returns itself."""
    canon = disambiguate("language", language)
    return canon.split("-", 1)[0].lower()


def language_compatible(fact_language: str, request_language: str) -> bool:
    """True iff a fact in ``fact_language`` may EVER be considered for a ``request_language``
    request. Same base language only — this is the hard no-cross-language-bleed rule."""
    return base_language(fact_language) == base_language(request_language)


def sensitivity_floor(scope: ContextScope) -> str:
    """The strictest sensitivity floor any dimension of ``scope`` imposes ("standard" or
    "elevated"). Used by the gateway data-class policy (M2.4) so a customer/public/apology context
    can never be silently treated as low-sensitivity."""
    norm = normalize_scope(scope)
    floors = {
        SENSITIVITY_FLOOR.get(("channel", norm.channel), "standard"),
        SENSITIVITY_FLOOR.get(("audience", norm.audience), "standard"),
        SENSITIVITY_FLOOR.get(("purpose", norm.purpose), "standard"),
    }
    return "elevated" if "elevated" in floors else "standard"


@dataclass(frozen=True, slots=True)
class ScopeCandidate:
    """One scope worth considering for a request, plus the human-readable relaxations that got us
    there. ``relaxations`` is empty for the exact request scope; every non-empty entry MUST be
    surfaced to the caller as a warning (no unreported bleed)."""

    scope: ContextScope
    relaxations: tuple[str, ...]

    @property
    def is_exact(self) -> bool:
        return not self.relaxations


def _relaxation_chain(scope: ContextScope) -> list[tuple[ContextScope, tuple[str, ...]]]:
    """Progressively relax the non-language dimensions toward their general values, in
    RELAXATION_PRIORITY order. Returns (scope, relaxations) pairs from exact to most-general.
    Deterministic and total-ordered."""
    chain: list[tuple[ContextScope, tuple[str, ...]]] = [(scope, ())]
    current = scope
    applied: list[str] = []
    for dim in RELAXATION_PRIORITY:
        general = GENERAL_VALUES[dim]
        if getattr(current, dim) == general:
            continue  # already general on this dimension; relaxing it changes nothing
        current = _replace_dim(current, dim, general)
        applied = applied + [f"context_fallback:{dim}={general}"]
        chain.append((current, tuple(applied)))
    return chain


def _replace_dim(scope: ContextScope, dim: str, value: str) -> ContextScope:
    d = scope.as_dict()
    d[dim] = value
    return ContextScope.from_dict(d)


def candidate_scopes(request_scope: ContextScope) -> list[ScopeCandidate]:
    """The ordered set of scopes a retrieval MAY draw facts from for ``request_scope``, most
    specific first. Ordering (the deterministic ranking §13 M2 requires):

    1. exact request scope (no relaxation);
    2. base-language fallback of the exact scope (if the request language is a variant);
    3. context-relaxed scopes at the request language;
    4. context-relaxed scopes at the base language.

    Every candidate past #1 carries the exact relaxation(s) that produced it, so the caller can
    report them. Cross-base-language scopes NEVER appear here."""
    norm = normalize_scope(request_scope)
    req_lang = norm.language
    base = base_language(req_lang)
    languages: list[tuple[str, tuple[str, ...]]] = [(req_lang, ())]
    if base != req_lang.lower() and base != req_lang:
        languages.append((base, (f"language_variant_fallback:{base}",)))

    chain = _relaxation_chain(norm)
    seen: set[str] = set()
    out: list[ScopeCandidate] = []
    # Outer loop over the context-relaxation chain, inner over language, so that keeping the
    # exact context but falling back a language variant is preferred over relaxing the context.
    for ctx_scope, ctx_relax in chain:
        for lang, lang_relax in languages:
            scoped = _replace_dim(ctx_scope, "language", lang)
            key = scoped.key()
            if key in seen:
                continue
            seen.add(key)
            out.append(ScopeCandidate(scope=scoped, relaxations=ctx_relax + lang_relax))
    return out


def classify_fact_scope(fact_scope: ContextScope, request_scope: ContextScope) -> tuple[bool, tuple[str, ...]]:
    """Decide whether ``fact_scope`` may serve ``request_scope``.

    Returns ``(usable, relaxations)``:
      * ``(True, ())`` — exact match, no bleed;
      * ``(True, ("context_fallback:...","language_variant_fallback:..."))`` — usable via an
        explicitly-reported relaxation;
      * ``(False, ("bleed:...",))`` — must be excluded (cross-context / cross-language bleed).
    """
    norm_fact = normalize_scope(fact_scope)
    if not language_compatible(norm_fact.language, request_scope.language):
        return False, (f"bleed:language={base_language(norm_fact.language)}",)
    for cand in candidate_scopes(request_scope):
        if cand.scope.key() == norm_fact.key():
            return True, cand.relaxations
    return False, (f"bleed:scope={norm_fact.key()}",)


__all__ = [
    "TAXONOMY_VERSION",
    "CANONICAL",
    "SYNONYMS",
    "GENERAL_VALUES",
    "RELAXATION_PRIORITY",
    "SENSITIVITY_FLOOR",
    "ScopeCandidate",
    "disambiguate",
    "normalize_scope",
    "base_language",
    "language_compatible",
    "sensitivity_floor",
    "candidate_scopes",
    "classify_fact_scope",
]
