#!/usr/bin/env python3
"""Pure text operations for continual-learning consolidation.

The module has no filesystem, process, network, git, or GitHub behavior.  It
parses the two marketplace-plugin machine sections, conservatively deduplicates
their bullets, renders the canonical projection, and scans the final bytes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

THRESHOLD = 0.5

_STOP = set(
    "a an the of to and or for in on with is are be this that it its as by via not "
    "no do your you their they we our own only per each any all can may than then "
    "so if when what which who whom into over under out up down at from about".split()
)
_MACHINE_HEADINGS = {
    "learned user preferences": "Learned User Preferences",
    "learned workspace facts": "Learned Workspace Facts",
}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+")


def learned_bullets(text: str) -> list[tuple[str, str]]:
    """Extract bullets directly under the two exact machine headings."""
    out: list[tuple[str, str]] = []
    section: str | None = None
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            section = _MACHINE_HEADINGS.get(heading.group(2).strip().lower())
            continue
        if section is None or not line.strip():
            continue
        if _BULLET_RE.match(line):
            bullet = _BULLET_RE.sub("", line, count=1).strip()
            if bullet:
                out.append((section, bullet))
            continue
        section = None
    return out


def render_learned(bullets: Iterable[tuple[str, str]]) -> str:
    """Render learned bullets in stable first-seen section order."""
    order: list[str] = []
    groups: dict[str, list[str]] = {}
    for section, text in bullets:
        if section not in groups:
            order.append(section)
            groups[section] = []
        groups[section].append(text)

    parts: list[str] = []
    for section in order:
        parts.append(f"## {section}")
        parts.extend(f"- {text}" for text in groups[section])
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n" if parts else ""


def _wordset(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in _STOP and len(word) > 2
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def near_duplicate(left: str, right: str) -> bool:
    """Return true only for a conservative semantic duplicate.

    Short bullets require exact content-word equality. Longer bullets require
    both the historical Jaccard threshold and at least three shared content
    words. Uncertainty therefore keeps both bullets.
    """
    left_words = _wordset(left)
    right_words = _wordset(right)
    if len(left_words) < 3 or len(right_words) < 3:
        return bool(left_words) and left_words == right_words
    return (
        _jaccard(left_words, right_words) >= THRESHOLD
        and len(left_words & right_words) >= 3
    )


def consolidate(bullets: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Deduplicate in input order; first occurrence wins."""
    kept: list[tuple[str, str]] = []
    for section, text in bullets:
        if any(near_duplicate(text, previous) for _, previous in kept):
            continue
        kept.append((section, text))
    return kept


_BLOCK_PATTERNS = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----"
        ),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA)[0-9A-Z]{16}\b"),
    ),
    (
        "aws_secret_key",
        re.compile(
            r"(?i)aws.{0,20}(?:secret|access).{0,20}[:=]\s*"
            r"['\"]?[A-Za-z0-9/+]{40}\b"
        ),
    ),
    ("github_token", re.compile(r"\bgh[opsur]_[A-Za-z0-9]{20,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    (
        "provider_key",
        re.compile(r"\b(?:sk-(?:ant-|proj-)?|xai-)[A-Za-z0-9_\-]{20,}\b"),
    ),
    ("stripe_key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."
            r"[A-Za-z0-9_\-]{10,}\b"
        ),
    ),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b([a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|"
            r"access[_-]?key|private[_-]?key|client[_-]?secret|auth[_-]?token|"
            r"bearer))\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}"
        ),
    ),
    (
        "corporate_email",
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@"
            r"(?!users\.noreply\.github\.com\b)"
            r"(?!(?:[a-z0-9-]+\.)*example\.(?:com|org|net)\b)"
            r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ),
    ),
]
_WARN_PATTERNS = [
    (
        "work_context",
        re.compile(
            r"(?i)\b(confidential|internal[- ]only|do not distribute|proprietary)\b"
        ),
    )
]


def _redact(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return value[:1] + "***"
    return value[:4] + "***" + value[-2:]


def scan(text: str) -> tuple[list[dict[str, str]], bool]:
    """Return scanner findings and whether the final projection is blocked."""
    findings: list[dict[str, str]] = []
    for name, pattern in _BLOCK_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                {"rule": name, "severity": "BLOCK", "match": _redact(match.group(0))}
            )
    for name, pattern in _WARN_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                {"rule": name, "severity": "WARN", "match": _redact(match.group(0))}
            )
    return findings, any(item["severity"] == "BLOCK" for item in findings)
