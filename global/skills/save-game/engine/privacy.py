"""Privacy gate: blocks or redacts secrets/PII before persistence.

Structural non-collection (closed schemas with `additionalProperties: false`) is
Phase 1's job and already refuses raw source/transcript/log fields outright — a
field like `raw_transcript_excerpt` cannot exist in a schema-valid document at
all. This module covers the remaining risk: sensitive content pasted INTO an
otherwise-legitimate free-text field (e.g. `objective`, `statement`, `summary`).

v2-hardened minimal documented customer-data starter set: PAN/card-like digit
sequences, email addresses, phone numbers — plus generic secret/high-entropy
patterns and corporate-confidentiality markers, per the plan's crash-consistency
section. This is explicitly NOT claimed to be complete DLP (the plan disclaims
that too); it is defense-in-depth on top of structural non-collection.

Scanner absence/error fails closed: any exception during scanning is raised as
`PrivacyGateError`, which callers must map to `PRIVACY_BLOCK`, never to a silent
skip-and-proceed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SCANNER_RULESET_VERSION = "save-game-privacy/v2-hardened-4"

# Fields that are themselves structurally constrained (hex digests, ISO timestamps,
# our own generated IDs) are exempt from content scanning when the ENTIRE value
# matches one of these — a full-string match only, so a free-text field that merely
# CONTAINS a digest-like substring is still fully scanned.
_STRUCTURAL_WHOLE_VALUE = re.compile(
    r"^(?:[a-f0-9]{64}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z|[A-Za-z0-9][A-Za-z0-9_.-]{0,127})$"
)

_REDACTION_TEMPLATE = "[REDACTED:{rule_id}]"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    sample: str  # already-redacted preview, never the raw match


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _shannon_entropy_bits_per_char(s: str) -> float:
    if not s:
        return 0.0
    import math

    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


_PAN_CANDIDATE_RE = re.compile(r"(?:\d[ -]?){13,19}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# US-centric heuristic on purpose (matches the plan's own "not complete DLP" disclaimer).
_PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_KNOWN_SECRET_MARKER_RE = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}"
)
_HIGH_ENTROPY_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
# Lowercase word segments, each with an OPTIONAL short trailing numeric suffix
# (0-4 digits, letters always precede digits, never interleaved), joined by
# hyphen/underscore/slash -- kebab-case, snake_case, and path-qualified
# natural-language identifiers (repo/skill/capability names, and versioned or
# milestone-numbered paths like "docs/plans/gen3-m2-control-plane-v1", this
# repo's own naming convention). Supersedes the narrower #87 pure-letters-only
# shape (`^[a-z]+(?:[-_][a-z]+)+$`): every string that pattern matched also
# matches this one (0 trailing digits and `-`/`_` separators both still
# allowed), so it fully replaces that check below rather than running both.
# The letters-run-then-digits-run-then-separator structure (never digit-first,
# never interleaved) is the safety property: it structurally rejects
# UUID-shaped and random hex/base64 tokens, which mix letters and digits in no
# fixed order and can't be consumed by an alternating "word[digits]" grammar,
# regardless of the digit-count cap. Real secret formats this rule targets
# (generic API keys/tokens, base64/hex blobs, UUIDs) are near-uniformly random
# over a mixed-case/digit/symbol alphabet and essentially never take this
# shape, so the exemption stays narrow and leaves real detection untouched.
#
# Deliberately NOT covered here (confirmed still redacted, not a regression):
#   - Bare digit-led segments with no leading letter, e.g. ADR-style filenames
#     ("0007-use-postgres-for-storage") or ISO-date-embedded notes
#     ("notes-2026-08-02-summary"). A blanket digit-segment allowance would
#     risk exempting real numeric-heavy secret formats; needs its own
#     narrower rule if this actually reproduces in practice.
#   - Dotted semver / Docker image tags / build metadata ("v1.2.3-alpha.1")
#     -- not even reachable today since `_HIGH_ENTROPY_TOKEN_RE`'s charset
#     has no `.`; would need its own rule, not a widened separator set here.
#
# KNOWN, ACCEPTED RESIDUAL RISK (security-review finding on this PR, verified
# and knowingly kept, not silently dropped): this is a SHAPE check, not a
# content/dictionary check, so a token that happens to be built from
# word-like, letters-then-digits segments can still carry high Shannon
# entropy (e.g. every letter of the alphabet used once, or several distinct
# short "word+digits" segments) and would be exempted like any other match.
# This is not a new class of risk introduced here -- the identical tradeoff
# already existed, unconditionally, in #87's original `_PURE_WORDLIKE_RE`
# (e.g. "abcdefghijklmnopqrstuvwxyz-abcdefghijklmnopqrstuvwxyz" was already
# exempt before this PR). Accepted because: (1) this scanner's threat model
# is accidental self-paste of a REAL generated secret into a free-text
# field, and real secret generators (CSPRNG-based API keys/tokens, base64,
# hex, UUIDs) never emit coherent letters-before-digits word segments --
# they interleave randomly, which this shape structurally cannot consume,
# per the safety property above; (2) closing this fully would require either
# an entropy ceiling tuned to a razor-thin, fragile numeric gap (~4.27 vs
# ~4.36 bits/char between the real bug token and a constructed adversarial
# example) or an actual dictionary/word-frequency check, both of which
# contradict this module's stdlib-only, narrow-shape-filter design and its
# own "not complete DLP" disclaimer; (3) `_KNOWN_SECRET_MARKER_RE` still
# catches common real-world formats (AKIA, ghp_, xox*, PEM headers)
# regardless of this exemption. See `TestStructuredIdentifierExemption`'s
# `*_known_residual_risk` tests for the concrete pathological examples this
# was verified against.
_STRUCTURED_IDENTIFIER_RE = re.compile(r"^[a-z]+[0-9]{0,4}(?:[-_/][a-z]+[0-9]{0,4})+$")
# A bare git commit SHA (full 40-char SHA-1 hex) embedded in prose — e.g. a
# "next_action" note referencing a commit — has ~4 bits/char entropy (log2(16))
# and clears the 3.5 threshold, so it previously false-positived as a secret.
# Exempt ONLY the exact 40-char lowercase-hex shape: that is the sole git-SHA
# length reachable here (the 7-char abbreviated form never reaches this rule's
# 24-char floor on its own, so it needs no handling). This is deliberately NOT
# a blanket hex exemption of arbitrary length — that would carve out real
# hex-encoded secrets (HMAC digests, API keys) too broadly. It is also
# case-sensitive on purpose: git never emits uppercase SHAs, so a mixed- or
# upper-case 40-char hex-shaped token is not exempted and still gets scanned.
_GIT_SHA_SHAPE_RE = re.compile(r"^[a-f0-9]{40}$")
_CONFIDENTIALITY_RE = re.compile(
    r"\b(confidential|proprietary and confidential|internal use only|do not distribute)\b",
    re.IGNORECASE,
)


def _find_pan_matches(text: str):
    for m in _PAN_CANDIDATE_RE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            yield m.span(), "pan_like_digit_sequence"


def _find_high_entropy_matches(text: str):
    for m in _HIGH_ENTROPY_TOKEN_RE.finditer(text):
        token = m.group(0)
        if _STRUCTURED_IDENTIFIER_RE.match(token) or _GIT_SHA_SHAPE_RE.match(token):
            continue
        if _shannon_entropy_bits_per_char(token) >= 3.5:
            yield m.span(), "high_entropy_secret"


def _all_matches(text: str):
    matches = []
    matches.extend(_find_pan_matches(text))
    for m in _EMAIL_RE.finditer(text):
        matches.append((m.span(), "email_address"))
    for m in _PHONE_RE.finditer(text):
        matches.append((m.span(), "phone_number"))
    for m in _KNOWN_SECRET_MARKER_RE.finditer(text):
        matches.append((m.span(), "known_secret_marker"))
    matches.extend(_find_high_entropy_matches(text))
    for m in _CONFIDENTIALITY_RE.finditer(text):
        matches.append((m.span(), "confidentiality_marker"))
    # Longest-first, non-overlapping so a redaction can't partially eat another match's span.
    matches.sort(key=lambda item: (item[0][0], -(item[0][1] - item[0][0])))
    accepted = []
    last_end = -1
    for span, rule_id in matches:
        if span[0] < last_end:
            continue
        accepted.append((span, rule_id))
        last_end = span[1]
    return accepted


def redact_text(text: str, path: str) -> tuple[str, list[Finding]]:
    if _STRUCTURAL_WHOLE_VALUE.match(text):
        return text, []
    matches = _all_matches(text)
    if not matches:
        return text, []
    findings = []
    out = []
    cursor = 0
    for (start, end), rule_id in matches:
        out.append(text[cursor:start])
        placeholder = _REDACTION_TEMPLATE.format(rule_id=rule_id)
        out.append(placeholder)
        findings.append(Finding(rule_id=rule_id, path=path, sample=placeholder))
        cursor = end
    out.append(text[cursor:])
    return "".join(out), findings


def _walk_redact(value: Any, path: str) -> tuple[Any, list[Finding]]:
    if isinstance(value, str):
        return redact_text(value, path)
    if isinstance(value, dict):
        findings: list[Finding] = []
        new_dict = {}
        for k, v in value.items():
            new_v, sub_findings = _walk_redact(v, f"{path}.{k}")
            new_dict[k] = new_v
            findings.extend(sub_findings)
        return new_dict, findings
    if isinstance(value, list):
        findings = []
        new_list = []
        for i, v in enumerate(value):
            new_v, sub_findings = _walk_redact(v, f"{path}[{i}]")
            new_list.append(new_v)
            findings.extend(sub_findings)
        return new_list, findings
    return value, []


class PrivacyGateError(RuntimeError):
    """Scanner failure. Callers MUST fail closed (map to PRIVACY_BLOCK), never skip."""


def scan_and_redact_document(doc: dict) -> tuple[dict, list[Finding]]:
    try:
        redacted, findings = _walk_redact(doc, "$")
    except Exception as exc:  # fail closed on any scanner error, per the plan
        raise PrivacyGateError(f"privacy scanner failed: {exc}") from exc
    return redacted, findings


def classification_for(findings: list[Finding]) -> str:
    return "redacted" if findings else "clean"
