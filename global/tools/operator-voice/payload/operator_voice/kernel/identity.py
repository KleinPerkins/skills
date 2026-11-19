"""Subject identity binding — build plan v3 §4.4 threat model row "Subject collision or
cross-profile bleed": "Stable source-native identifiers, alias confidence, manual collision
review ... Name-only matching is forbidden."

M1 ships only the ``OPERATOR`` product surface (§4.3, D17), so the only binding path exercised
is: a :class:`~operator_voice.domain.models.SourceRegistration` pins exactly one authoritative
source-native role label (``role_identity["subject_role"]``) to its ``subject_id`` at source-add
time (an explicit operator action, never inferred). :class:`SubjectAlias`-based resolution (for
future near-deterministic EXTERNAL identifiers, §4.3) is implemented as a pure function so it has
test coverage and a frozen contract, even though M1's own call sites never need more than the
role pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from operator_voice.domain.models import ObservationCandidate, SourceRegistration, SubjectAlias


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    subject_id: Optional[str]
    confidence: float
    needs_review: bool
    reason: str


def resolve_via_source_role(
    candidate: ObservationCandidate, source: SourceRegistration
) -> IdentityDecision:
    """The M1 binding path: trust the source registration's pinned role for its own subject."""
    if candidate.source_id != source.source_id:
        return IdentityDecision(None, 0.0, True, "candidate/source mismatch")
    subject_role = str(source.role_identity.get("subject_role", "")).strip().lower()
    role = (candidate.role or "").strip().lower()
    if subject_role and role == subject_role:
        return IdentityDecision(source.subject_id, 1.0, False, "source role_identity pin matched")
    return IdentityDecision(None, 0.0, True, "role does not match source's pinned subject_role")


def resolve_via_alias(
    candidate: ObservationCandidate, aliases: list[SubjectAlias]
) -> IdentityDecision:
    """Deterministic exact-match alias resolution for a *stable source-native identifier*
    (never a display name — §4.3). Reserved for future EXTERNAL-subject enrollment (M4); kept
    here, tested, and schema-stable so M1's ``SubjectAlias`` rows never need a shape migration."""
    if not candidate.author_id:
        return IdentityDecision(None, 0.0, True, "candidate has no author_id to match")
    matches = [
        a
        for a in aliases
        if a.source_type == candidate.role and a.source_native_id == candidate.author_id
    ]
    if len(matches) == 1:
        m = matches[0]
        return IdentityDecision(m.subject_id, m.confidence, m.confidence < 0.99, "exact alias match")
    if len(matches) > 1:
        return IdentityDecision(None, 0.0, True, "ambiguous: multiple subjects share this alias")
    return IdentityDecision(None, 0.0, True, "no alias match (name-only matching is forbidden)")
