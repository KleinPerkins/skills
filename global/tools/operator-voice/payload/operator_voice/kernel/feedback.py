"""Deterministic feedback classification — build plan v3 §8: "The kernel classifies it into
confirm/correct/reject/ban/scope/identity/source actions, shows the interpreted change ... ;
ambiguous feedback asks one focused question."

Direct feedback is P0 (D15) and takes precedence over inference (§4.2 precedence order). This
module never calls a model: classification is rule-based pattern matching over a small, tested
set of English phrasings. Anything outside that set returns ``action=None`` plus one focused
clarifying question rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from operator_voice.domain.models import FeedbackAction

FEEDBACK_VERSION = "feedback/v1"

_BAN_RE = re.compile(
    r"\b(don'?t|never|stop) (say|use|writing?)\b.*?['\"]?([\w\s-]{1,40})['\"]?$", re.IGNORECASE
)
_CORRECT_RE = re.compile(
    r"\b(actually|i (?:meant|prefer|said|write))\b|instead of .+ use\b|it'?s not .+, ?it'?s\b",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(
    r"^(yes|yep|correct|exactly|that'?s (right|accurate|it)|spot on)\b", re.IGNORECASE
)
_REJECT_RE = re.compile(
    r"^(no|nope|that'?s (wrong|not right|incorrect)|not quite)\b", re.IGNORECASE
)
_SCOPE_RE = re.compile(
    r"\b(only|just) (in|for|when)\b|only when writing\b", re.IGNORECASE
)
_IDENTITY_RE = re.compile(r"\bthat'?s not (me|my voice|how i)\b", re.IGNORECASE)
_SOURCE_RE = re.compile(r"\b(don'?t (use|read|learn from)|stop (reading|watching))\b.*\bsource\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FeedbackClassification:
    action: Optional[FeedbackAction]
    extracted_value: Optional[str]
    clarifying_question: Optional[str]


def classify_feedback(utterance: str) -> FeedbackClassification:
    text = utterance.strip()
    if not text:
        return FeedbackClassification(None, None, "What would you like me to change?")

    m = _BAN_RE.search(text)
    if m:
        return FeedbackClassification(FeedbackAction.BAN, m.group(3).strip(), None)

    if _SOURCE_RE.search(text):
        return FeedbackClassification(FeedbackAction.SOURCE, None, None)

    if _IDENTITY_RE.search(text):
        return FeedbackClassification(FeedbackAction.IDENTITY, None, None)

    if _SCOPE_RE.search(text):
        return FeedbackClassification(FeedbackAction.SCOPE, None, None)

    if _CORRECT_RE.search(text):
        return FeedbackClassification(FeedbackAction.CORRECT, text, None)

    if _CONFIRM_RE.search(text):
        return FeedbackClassification(FeedbackAction.CONFIRM, None, None)

    if _REJECT_RE.search(text):
        return FeedbackClassification(FeedbackAction.REJECT, None, None)

    return FeedbackClassification(
        None,
        None,
        "I'm not sure what to change — could you tell me specifically what was wrong "
        "(e.g. 'don't say X', 'I actually prefer Y', or 'that's correct')?",
    )
