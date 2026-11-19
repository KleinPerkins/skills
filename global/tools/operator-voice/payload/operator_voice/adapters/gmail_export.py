"""Gmail-export adapter — OVT Gmail Adapter v1. Scans the immutable, timestamp-prefixed Markdown
files ``gmail.import`` already materialized under the operator's fixed ``gmail_export_dir``
(§ :mod:`operator_voice.gmail.materialize`); a completely ordinary, network-free file-tree scan,
structurally identical to ``slack_export``/``drive_export``.

Every file in a materialized tree has ALREADY passed server-side author verification at
``gmail.import`` time (a mismatched ``from`` never reaches disk), so this adapter — like
``slack_export`` — hardcodes ``role="user"``: there is no other author possible in a
``gmail_export`` tree by construction. ``channel`` is the fixed literal ``"email"`` and
``output_type`` is ``"email"`` (canonical ``kernel/taxonomy.py`` values).

**Identity is ``message_id`` ALONE:** each Sent message is a genuinely independent, immutable
utterance — unlike Drive's revisable files.

Cursor: Slack's exact, unmodified lexicographic file-path algorithm. Because each record file is
named ``<internal_date_iso>__<message_id>.md`` (ADR 0002 Decision 1), lexicographic filename order
IS chronological order, and each file is immutable once written — no growable-file blind spot.
"""

from __future__ import annotations

from datetime import datetime

from operator_voice.adapters import base
from operator_voice.adapters.base import (
    ADAPTER_VERSION,
    AdapterQuarantine,
    AdapterScanResult,
    ScanWarning,
    iter_files_within,
    make_candidate,
    read_capped,
    registration_guard,
    resolve_within_root,
)
from operator_voice.domain.models import SourceRegistration
from operator_voice.gmail.materialize import parse_export_file
from operator_voice.kernel.authorship import own_text
from operator_voice.kernel.normalize import is_link_digest

GMAIL_EXPORT_ROLE = "user"
GMAIL_EXPORT_CHANNEL = "email"
GMAIL_EXPORT_OUTPUT_TYPE = "email"
_SUFFIXES = (".md",)


def _parse_timestamp(internal_date: str) -> float | None:
    if not internal_date:
        return None
    try:
        return datetime.fromisoformat(internal_date.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan(registration: SourceRegistration, cursor: str | None, limit: int | None = None) -> AdapterScanResult:
    registration_guard(registration)
    root = resolve_within_root(registration.canonical_root)
    files = iter_files_within(root, suffixes=_SUFFIXES, limit=None)

    if cursor:
        files = [f for f in files if str(f) > cursor]

    has_more = len(files) > base.MAX_FILES_PER_SCAN
    files = files[:base.MAX_FILES_PER_SCAN]
    if limit is not None and len(files) > limit:
        files = files[:limit]
        has_more = True

    candidates = []
    filters = {"no_own_text": 0, "digest": 0}
    warnings: list[ScanWarning] = []
    for path in files:
        try:
            text = read_capped(path)
        except AdapterQuarantine as exc:
            warnings.append(ScanWarning(locator=str(path), reason=str(exc)))
            continue
        try:
            records = parse_export_file(text)
        except Exception as exc:
            warnings.append(ScanWarning(locator=str(path), reason=f"unparseable gmail export file: {exc}"))
            continue
        for record in records:
            body = record["body"]
            own = own_text(body)
            if not own:
                filters["no_own_text"] += 1
                continue
            if is_link_digest(own):
                filters["digest"] += 1
                continue
            message_id = record["message_id"]
            thread_id = record["thread_id"]
            internal_date = record["internal_date"]
            candidates.append(
                make_candidate(
                    subject_id=registration.subject_id,
                    source_id=registration.source_id,
                    source_native_id=message_id,
                    role=GMAIL_EXPORT_ROLE,
                    raw_text=body,
                    locator=f"gmail:{thread_id}:{message_id}",
                    channel=GMAIL_EXPORT_CHANNEL,
                    output_type=GMAIL_EXPORT_OUTPUT_TYPE,
                    timestamp=_parse_timestamp(internal_date),
                )
            )

    next_cursor = str(files[-1]) if files else cursor
    return AdapterScanResult(
        candidates=candidates,
        next_cursor=next_cursor,
        warnings=warnings,
        files_scanned=len(files),
        records_scanned=len(candidates),
        has_more=has_more,
        filter_counts=filters,
    )


__all__ = [
    "scan",
    "ADAPTER_VERSION",
    "GMAIL_EXPORT_ROLE",
    "GMAIL_EXPORT_CHANNEL",
    "GMAIL_EXPORT_OUTPUT_TYPE",
]
