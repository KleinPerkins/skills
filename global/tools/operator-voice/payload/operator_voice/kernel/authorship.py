"""Authorship integrity — build plan v3 §4.4 threat model row 1 and §9 "Authorship/contamination".

Two independent decisions, both deterministic:

1. **Role-based identity** (:func:`classify_role`): adapters emit an authoritative ``role`` field
   from the source format's own structure (never inferred from text). Combined with the source
   registration's ``role_identity`` pin, this decides SUBJECT vs AI vs OTHER vs
   AMBIGUOUS_QUARANTINED for the *whole* candidate.
2. **Block-level quote/forward detection** (:func:`split_authored_segments`): even a message
   authoritatively authored by the subject can *contain* quoted/forwarded third-party or AI text
   (a reply that includes the original message below a "-----Original Message-----" marker, or a
   ">" quoted block). Those segments are excluded from operator evidence regardless of the
   outer message's role.

Quality gate (§10.2): "Ambiguous authorship is quarantined; correctly identified third-party text
contributes zero operator evidence and cannot be analyzed without EXTERNAL enrollment."
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from operator_voice.domain.models import AuthorshipState, ObservationCandidate

AUTHORSHIP_VERSION = "authorship/v2"

# Authoritative AI/assistant role labels across the three M1 adapters plus manual free text.
_AI_ROLES = {"assistant", "ai", "model", "chatgpt", "claude", "bot"}
_OTHER_ROLES = {"system", "tool", "other", "third_party"}

# Forward/reply headers that introduce a third-party body with NO per-line marker. Each is anchored
# to a whole line so a legitimate operator sentence that merely mentions "forwarded message" mid-text
# is never demoted. Covers the dashed Gmail/Outlook "----- Forwarded message -----" and
# "----- Original Message -----" forms plus Apple Mail's "Begin forwarded message:".
_FORWARD_HEADER_RE = re.compile(
    r"^\s*-{2,}\s*(original message|forwarded message)\s*-{2,}\s*$", re.IGNORECASE | re.MULTILINE
)
_BEGIN_FORWARDED_RE = re.compile(
    r"^\s*begin forwarded message:\s*$", re.IGNORECASE | re.MULTILINE
)
_QUOTE_BLOCK_LINE_RE = re.compile(r"^\s*>")


def _is_forward_header(line: str) -> bool:
    return bool(
        _FORWARD_HEADER_RE.match(line)
        or _BEGIN_FORWARDED_RE.match(line)
    )


@dataclass(frozen=True, slots=True)
class AuthoredSegment:
    text: str
    state: AuthorshipState
    reason: str


def classify_role(candidate: ObservationCandidate, subject_role: str) -> tuple[AuthorshipState, str]:
    """Whole-candidate role decision. ``subject_role`` comes from the owning
    :class:`~operator_voice.domain.models.SourceRegistration.role_identity` — a stable,
    source-native role label the operator pinned when adding the source (never a display name;
    §4.3 "A display name alone can never merge identities")."""
    role = (candidate.role or "").strip().lower()
    if not role:
        return AuthorshipState.AMBIGUOUS_QUARANTINED, "empty/unknown role from adapter"
    if role == subject_role.strip().lower():
        return AuthorshipState.SUBJECT, f"role '{role}' matches pinned subject_role"
    if role in _AI_ROLES:
        return AuthorshipState.AI, f"role '{role}' is an assistant/model role"
    if role in _OTHER_ROLES:
        return AuthorshipState.OTHER, f"role '{role}' is a system/other role"
    return (
        AuthorshipState.AMBIGUOUS_QUARANTINED,
        f"role '{role}' does not match pinned subject_role '{subject_role}' and is not a "
        "recognized AI/other role",
    )


def split_authored_segments(text: str, outer_state: AuthorshipState) -> list[AuthoredSegment]:
    """Split ``text`` into segments, demoting quoted/forwarded blocks to OTHER (or leaving them
    AMBIGUOUS if the outer message was already ambiguous) regardless of the outer role decision.
    A SUBJECT-authored reply that quotes someone else still yields zero operator evidence for the
    quoted portion (§4.3 last paragraph)."""
    lines = text.split("\n")
    segments: list[AuthoredSegment] = []
    current: list[str] = []
    current_state = outer_state
    current_reason = "outer role decision"

    def flush() -> None:
        block = "\n".join(current).strip()
        if block:
            segments.append(AuthoredSegment(text=block, state=current_state, reason=current_reason))
        current.clear()

    # Two independent demotion mechanisms:
    #   * a forward/reply HEADER ("-----Original Message-----", "On <date> wrote:") has NO per-line
    #     marker on the body it introduces — everything after it, to EOF, is third-party. This is a
    #     STICKY tail: it never flips back to SUBJECT (top-posting reality; fail closed). Not treating
    #     it as sticky is a real contamination bug — the first non-blank forwarded line would
    #     otherwise be misread as operator text and the whole quoted body would follow it.
    #   * a ">"-prefixed QUOTE run is per-line: it ends when an unquoted line reappears, so genuine
    #     operator text written below a short inline quote is still counted.
    in_forward_tail = False
    in_quote_run = False
    for index, line in enumerate(lines):
        is_quote_marker = bool(_QUOTE_BLOCK_LINE_RE.match(line))
        is_forward_header = _is_forward_header(line) or _wrapped_reply_header(lines, index)

        if in_forward_tail:
            current.append(_QUOTE_BLOCK_LINE_RE.sub("", line) if is_quote_marker else line)
            continue

        if is_forward_header:
            flush()
            current_state = AuthorshipState.OTHER
            current_reason = "forward/reply header detected; remainder is third-party (sticky)"
            in_forward_tail = True
            in_quote_run = False
            continue
        if is_quote_marker and not in_quote_run:
            flush()
            current_state = AuthorshipState.OTHER
            current_reason = "quoted ('>') block detected"
            in_quote_run = True
        elif not is_quote_marker and in_quote_run and line.strip() == "":
            # a single blank line doesn't necessarily end a quoted run; keep going
            pass
        elif not is_quote_marker and in_quote_run:
            flush()
            current_state = outer_state
            current_reason = "outer role decision (post-quote)"
            in_quote_run = False
        current.append(_QUOTE_BLOCK_LINE_RE.sub("", line) if is_quote_marker else line)
    flush()
    return segments


def _wrapped_reply_header(lines: list[str], index: int) -> bool:
    if not lines[index].lower().startswith("on "):
        return False
    for count in range(1, 4):
        block = "\n".join(lines[index:index + count])
        if len(block) > 300:
            return False
        if block.rstrip().lower().endswith("wrote:"):
            return True
    return False


def own_text(text: str) -> str:
    """Return only operator segments; never the sticky quoted reply/forward tail."""
    return "\n".join(s.text for s in split_authored_segments(text, AuthorshipState.SUBJECT)
                     if s.state == AuthorshipState.SUBJECT)
