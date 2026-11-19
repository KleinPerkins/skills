"""Deterministic normalization — build plan v3 §3.2 "Pure deterministic functions with
golden/property tests" and §4 kernel responsibility "normalization/deduplication".

Every function here is a pure function of its input: same text in, same text out, forever
(pinned by ``normalization_version`` in :class:`operator_voice.domain.models.ProfileGeneration`).
Changing behavior requires bumping ``NORMALIZATION_VERSION`` (§8: "It never silently switches
extraction methods").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NORMALIZATION_VERSION = "normalize/v1"

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_SIGNATURE_DELIM_RE = re.compile(r"\n-- ?\n.*\Z", re.DOTALL)
_MOBILE_SIGNATURE_RE = re.compile(
    r"\n?\s*(sent from my \w+.*|get outlook for \w+.*)\s*\Z", re.IGNORECASE
)

# Sentence splitter: split on ., !, ? followed by whitespace + capital/quote, but not after a
# short list of common abbreviations. Deterministic and stdlib-only (no NLP dependency) per §7
# "Core extraction is deterministic and stdlib-first."
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "e.g", "i.e", "inc", "ltd", "co",
    "st", "ave", "no", "vol", "fig", "approx", "dept", "u.s", "u.k",
}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\u201c])")


@dataclass(frozen=True, slots=True)
class NormalizedText:
    text: str
    code_blocks: tuple[str, ...]


def normalize_text(raw: str) -> NormalizedText:
    """NFC-normalize, strip trailing whitespace, collapse excess blank lines, remove a trailing
    signature block, and extract fenced code (excluded from stylometric signals — code is not
    operator prose voice)."""
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    code_blocks: list[str] = []

    def _capture(m: re.Match[str]) -> str:
        code_blocks.append(m.group(0))
        return ""

    text = _CODE_FENCE_RE.sub(_capture, text)
    text = _SIGNATURE_DELIM_RE.sub("", text)
    text = _MOBILE_SIGNATURE_RE.sub("", text)
    text = _TRAILING_WS_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    text = text.strip("\n")
    return NormalizedText(text=text, code_blocks=tuple(code_blocks))


def split_sentences(text: str) -> list[str]:
    """Deterministic, abbreviation-aware sentence splitter. Never raises; worst case returns the
    whole text as one sentence."""
    if not text.strip():
        return []
    # Protect abbreviations by temporarily gluing them to the next token.
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = re.sub(
            rf"(?i)\b{re.escape(abbr)}\.\s+", f"{abbr}.\u0000", protected
        )
    raw_sentences = _SENTENCE_SPLIT_RE.split(protected)
    sentences = [s.replace("\u0000", " ").strip() for s in raw_sentences]
    return [s for s in sentences if s]


def tokenize_words(text: str) -> list[str]:
    """Lowercase word tokens, stripping punctuation. Deterministic, stdlib-only."""
    return re.findall(r"[a-zA-Z']+", text.lower())


def strip_quoted_and_signature_lines(text: str) -> tuple[str, list[str]]:
    """Return (remaining_text, removed_quoted_lines) — a conservative line-level pass that
    removes obvious quote markers ('>' prefixed lines). Block-level quote/forward detection
    (headers like 'On ... wrote:') lives in :mod:`operator_voice.kernel.authorship`, which is the
    single source of truth for authorship *decisions*; this helper only removes leftover quote
    marker characters once a block has already been classified as quoted."""
    kept: list[str] = []
    removed: list[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith(">"):
            removed.append(line)
        else:
            kept.append(line)
    return "\n".join(kept), removed


_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>]+", re.IGNORECASE)
_PATH_RE = re.compile(r"(?<!\w)(?:~?/|\.{1,2}/|[A-Za-z]:[\\/])[^\s<>]+|\b(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+")
_LOG_LINE_RE = re.compile(
    r"^\s*(?:\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d\b|"
    r"\[?(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]?(?:\s|:)|"
    r"Traceback \(most recent call last\):|File [\"'].*[\"'], line \d+|"
    r"at \S+\s*\([^\n]*:\d+(?::\d+)?\)|\w+(?:Error|Exception):)"
)


def strip_non_prose(text: str) -> tuple[str, int]:
    """Strip code, diagnostics and non-prose tokens while retaining ordinary short replies."""
    kept = []
    removed = 0
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence is not None:
            removed += 1
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if marker:
            fence = marker[1]
            removed += 1
            continue
        if (_LOG_LINE_RE.match(line) or line.lstrip().startswith("$ ")
                or re.fullmatch(r"\s*`+[^`\n]*`+\s*", line)):
            removed += 1
            continue
        cleaned = _INLINE_CODE_RE.sub("", _PATH_RE.sub("", _URL_RE.sub("", line)))
        if cleaned != line and len(tokenize_words(cleaned)) < 3:
            removed += 1
            continue
        kept.append(cleaned)
    return "\n".join(kept), removed


def is_link_digest(text: str) -> bool:
    return (sum(bool(_URL_RE.search(line)) for line in text.splitlines()) >= 20
            and len(tokenize_words(strip_non_prose(text)[0])) >= 1000)
