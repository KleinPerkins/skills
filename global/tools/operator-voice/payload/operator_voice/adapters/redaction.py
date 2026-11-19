"""Source-specific redaction — build plan v4 §13 M3 worklist 1: the Cursor-transcript and
approved-artifact adapters apply "source-specific redaction/quarantine" before a candidate ever
reaches the kernel.

The kernel's authorship stage (:mod:`operator_voice.kernel.authorship`) already strips *quoted /
forwarded third-party* prose from an otherwise operator-authored message. These two M3 sources
carry a second class of not-operator-voice text the authorship kernel does not know to drop:
fenced **code blocks**, inline code spans, and tool/command output pasted into a transcript or an
approved doc. Those are not "someone else's prose" — they are machine text — so they must be
redacted at the adapter boundary so they never inflate stylometric signal.

Pure, deterministic string surgery only: no I/O, no model, no network. Returns the cleaned text
plus a count of redactions so the adapter can emit an honest ScanWarning when it removed content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTION_VERSION = "redaction/v1"

# A fenced code block: ```lang\n...\n``` or ~~~ ... ~~~ (multiline, non-greedy).
_FENCED_CODE_RE = re.compile(r"(?:```|~~~).*?(?:```|~~~)", re.DOTALL)
# An inline code span: `code` (single backtick pair, no newline inside).
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# A leading blockquote marker on a line (Markdown quote / pasted reply). The authorship kernel
# also handles reply/forward blocks, but a lone ``>`` quote in an approved doc is redacted here too.
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s{0,3}>.*$", re.MULTILINE)


@dataclass(slots=True)
class RedactionResult:
    text: str
    redaction_count: int


def redact_machine_text(raw: str, *, drop_blockquotes: bool = True) -> RedactionResult:
    """Remove fenced code blocks, inline code spans, and (optionally) blockquote lines. Collapses
    the whitespace left behind so a redacted paragraph does not masquerade as unusual spacing/
    punctuation to the stylometric extractors."""
    count = 0

    def _sub(pattern: re.Pattern[str], s: str) -> str:
        nonlocal count
        new, n = pattern.subn(" ", s)
        count += n
        return new

    text = _sub(_FENCED_CODE_RE, raw)
    text = _sub(_INLINE_CODE_RE, text)
    if drop_blockquotes:
        text = _sub(_BLOCKQUOTE_LINE_RE, text)

    # Normalize the holes the redactions left: collapse runs of blank lines and trailing spaces so
    # the residual operator prose is clean (never invents punctuation/whitespace signal).
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return RedactionResult(text=text.strip(), redaction_count=count)


__all__ = ["redact_machine_text", "RedactionResult", "REDACTION_VERSION"]
