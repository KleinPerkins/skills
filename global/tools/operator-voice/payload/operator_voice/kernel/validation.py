"""Deterministic draft validation — build plan v3 §6 "draft_validate accepts a draft and source
brief as data. Deterministic checks always run; optional semantic comparison runs only when
policy permits." (§13 M2 worklist 5).

This module is the PURE, deterministic half: it never calls a model gateway (kernel purity, §D7).
It reaches only ``DETERMINISTIC_ONLY`` (all deterministic checks passed) or ``UNVALIDATED`` (a
deterministic check failed — including a forbidden/injected fact present, or a required fact
missing). ``VALIDATED`` is reachable ONLY when the application layer additionally obtains a
passing semantic/factual gateway comparison on top of passing deterministic checks — a
high-stakes draft is never marked ``validated`` without BOTH (§13 acceptance 6). The application
upgrade path uses :func:`parse_semantic_verdict` to read a provider verdict deterministically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from operator_voice.domain.models import ProfileFact, ValidationOutcome, ValidationRun, new_id

VALIDATION_VERSION = "validation/v2"

# Semantic verdict tokens a configured review provider must emit (case-insensitive). A provider that
# emits neither is INCONCLUSIVE — it can never grant `validated` (absence of review is surfaced, not
# treated as a pass, §13 acceptance 6). The bundled local-deterministic provider is inconclusive by
# design; a real semantic judge is operator-configured.
SEMANTIC_FIDELITY_OK = "FIDELITY_OK"
SEMANTIC_MATERIAL_CHANGE = "MATERIAL_CHANGE"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_semantic_verdict(text: Optional[str]) -> Optional[bool]:
    """Deterministically read a provider's semantic-comparison verdict. Returns True (fidelity
    preserved), False (material factual change detected), or None (inconclusive / no clear verdict).
    Material-change wins over fidelity if both tokens somehow appear (fail-safe)."""
    if not text:
        return None
    upper = text.upper()
    if SEMANTIC_MATERIAL_CHANGE in upper:
        return False
    if SEMANTIC_FIDELITY_OK in upper:
        return True
    return None


def build_semantic_signal(
    *, draft_text: str, source_brief: str, required_facts: list[str], forbidden_facts: list[str]
) -> str:
    """Assemble the minimum-necessary, escaped signal for a semantic/factual comparison. Contains
    ONLY the draft under review and the operator-supplied brief/curated facts — never raw operator
    evidence, never third-party/quarantined text (§6 "typed, escaped, minimum-necessary signal
    envelopes")."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("\n", "\\n")

    lines = [
        "TASK: judge whether DRAFT preserves the facts in BRIEF. Reply with exactly one token: "
        f"{SEMANTIC_FIDELITY_OK} or {SEMANTIC_MATERIAL_CHANGE}.",
        f"DRAFT: {esc(draft_text)}",
    ]
    if source_brief.strip():
        lines.append(f"BRIEF: {esc(source_brief)}")
    if required_facts:
        lines.append("REQUIRED: " + " | ".join(esc(f) for f in required_facts))
    if forbidden_facts:
        lines.append("FORBIDDEN: " + " | ".join(esc(f) for f in forbidden_facts))
    return "\n".join(lines)


def check_banned_phrases(draft_text: str, facts: list[ProfileFact]) -> CheckResult:
    lowered = draft_text.lower()
    violations = []
    for fact in facts:
        if fact.facet == "banned_phrase" and fact.state.value == "CORRECTED":
            phrase = str(fact.value).lower().strip()
            if phrase and phrase in lowered:
                violations.append(phrase)
    if violations:
        return CheckResult("banned_phrases", False, f"draft contains banned phrase(s): {violations}")
    return CheckResult("banned_phrases", True, "no banned phrases present")


def check_required_facts(
    draft_text: str, source_brief: str, required_facts: Optional[list[str]] = None
) -> CheckResult:
    """Best-effort deterministic factual-preservation check (§9 "deterministic claim checks
    where possible"): every capitalized multi-word phrase and every number in the brief, PLUS every
    explicitly curated required fact, must still appear verbatim in the draft. Intentionally
    conservative — a false "fail" is safer than a false "pass" for a fact-preservation gate."""
    tokens = _extract_required_tokens(source_brief) + [f for f in (required_facts or []) if f.strip()]
    if not tokens:
        return CheckResult("required_facts", True, "no source brief or required facts supplied")
    missing = [t for t in tokens if t not in draft_text]
    if missing:
        return CheckResult("required_facts", False, f"missing required fact token(s): {missing}")
    return CheckResult("required_facts", True, "all required fact tokens present")


def check_forbidden_facts(draft_text: str, forbidden_facts: Optional[list[str]] = None) -> CheckResult:
    """Injected-fact block (§13 M2 worklist 5 / acceptance "injected factual changes are blocked"):
    a curated brief may forbid specific claims (a hallucinated number, an unapproved commitment, a
    fabricated name). If any forbidden claim appears in the draft, validation fails closed — such a
    draft can never be marked ``validated``. Case-insensitive substring match."""
    forbidden = [f for f in (forbidden_facts or []) if f.strip()]
    if not forbidden:
        return CheckResult("forbidden_facts", True, "no forbidden facts supplied")
    lowered = draft_text.lower()
    present = [f for f in forbidden if f.lower() in lowered]
    if present:
        return CheckResult("forbidden_facts", False, f"draft contains forbidden/injected claim(s): {present}")
    return CheckResult("forbidden_facts", True, "no forbidden claims present")


def _extract_required_tokens(brief: str) -> list[str]:
    import re

    numbers = re.findall(r"\b\d[\d,.]*%?\b", brief)
    proper_nouns = re.findall(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,3}\b", brief)
    seen: list[str] = []
    for tok in numbers + proper_nouns:
        if tok not in seen:
            seen.append(tok)
    return seen


def check_sentence_length_fit(draft_text: str, facts: list[ProfileFact]) -> CheckResult:
    from operator_voice.kernel.normalize import split_sentences, tokenize_words

    target = next((f for f in facts if f.facet == "sentence_length"), None)
    if target is None:
        return CheckResult("sentence_length_fit", True, "no sentence-length fact to compare against")
    sentences = split_sentences(draft_text)
    if not sentences:
        return CheckResult("sentence_length_fit", True, "draft has no sentences to compare")
    lengths = [len(tokenize_words(s)) for s in sentences]
    mean = sum(lengths) / len(lengths)
    target_mean = float(target.value)
    # Generous band: within 3x or +/-8 words, whichever is larger, avoids over-fitting M1's
    # small calibration corpus.
    band = max(target_mean * 2.0, 8.0)
    if abs(mean - target_mean) > band:
        return CheckResult(
            "sentence_length_fit",
            False,
            f"draft average sentence length {mean:.1f} is far from observed {target_mean:.1f}",
        )
    return CheckResult("sentence_length_fit", True, f"draft average sentence length {mean:.1f} fits observed profile")


def validate_draft(
    *, subject_id: str, draft_text: str, source_brief: str, facts: list[ProfileFact],
    required_facts: Optional[list[str]] = None, forbidden_facts: Optional[list[str]] = None,
) -> ValidationRun:
    """Pure deterministic validation. Reaches DETERMINISTIC_ONLY (all checks pass) or UNVALIDATED
    (any check fails). The application layer may upgrade a DETERMINISTIC_ONLY result to VALIDATED
    only via a passing semantic gateway comparison; this function never touches the gateway."""
    checks = [
        check_banned_phrases(draft_text, facts),
        check_required_facts(draft_text, source_brief, required_facts),
        check_forbidden_facts(draft_text, forbidden_facts),
        check_sentence_length_fit(draft_text, facts),
    ]
    passed_all = all(c.passed for c in checks)
    outcome = ValidationOutcome.DETERMINISTIC_ONLY if passed_all else ValidationOutcome.UNVALIDATED
    digest = hashlib.sha256(draft_text.encode()).hexdigest()
    return ValidationRun(
        run_id=new_id("val"),
        subject_id=subject_id,
        draft_digest=digest,
        checks=[{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
        outcome=outcome,
        versions={"validation_version": VALIDATION_VERSION},
        gateway_metadata=None,
        expires_at=None,
    )
