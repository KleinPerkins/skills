"""Drive-export adapter — OVT Drive Adapter v1. Scans the immutable, timestamp-prefixed Markdown
files ``drive.import`` already materialized under the operator's fixed ``drive_export_dir``
(§ :mod:`operator_voice.drive.materialize`); a completely ordinary, network-free file-tree scan,
using the shared adapter safety checks.

Every file in a materialized tree has ALREADY passed server-side owner + not-shared-drive
verification at ``drive.import`` time (a non-owned or Shared-Drive item never reaches disk), so this
adapter — like ``slack_export`` — hardcodes ``role="user"``: there is no other author possible in a
``drive_export`` tree by construction.

Only Google Docs with sidecar membership in a currently registered folder become candidates,
with ``channel="docs"`` and ``output_type="doc"``. Old Slides and unregistered Docs are counted
as filtered, and their existing stored evidence remains until an explicit reextract or erase.

**Identity is ``file_id`` ALONE** (ADR 0002 Decision 2): ``source_native_id`` is the bare ``file_id``,
never ``file_id:revision_id`` — one Drive file is one evolving voice-evidence unit, not a stream of
independent utterances. ``revision_id`` + ``modified_time`` ride along in the candidate's ``context``
so the service's single, Drive-only supersede-if-newer persistence path can order revisions of the
same file (``modified_time`` is the authoritative comparator; ``revision_id`` is opaque provenance).

Cursor: a simple lexicographic file-path cursor retained for immutable Drive records. Because each
record file is named ``<modified_time_iso>__<file_id>__<revision_id>.md`` (ADR 0002 Decision 1),
lexicographic filename order IS chronological order, and every file is immutable once written — so
there is no append-in-place to detect. Slack uses a separate change-ordered watermark.
The only residual (documented, accepted) risk is an agent submitting records out of strict timestamp
order across two imports; a full rescan (cursor reset) always recovers them.
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
from operator_voice.drive.materialize import GOOGLE_DOC_MIME, parse_export_file, read_folder_membership

DRIVE_EXPORT_ROLE = "user"
_SUFFIXES = (".md",)


def _parse_timestamp(modified_time: str) -> float | None:
    """Best-effort ISO-8601 ``modified_time`` -> epoch seconds (Drive's own RFC-3339 timestamp, e.g.
    ``2026-07-30T14:02:00Z``). A trailing ``Z`` is normalized to ``+00:00``; anything unparseable
    returns None (the candidate simply falls back to ``now_ts`` in ``make_candidate``)."""
    if not modified_time:
        return None
    try:
        return datetime.fromisoformat(modified_time.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan(registration: SourceRegistration, cursor: str | None, limit: int | None = None) -> AdapterScanResult:
    registration_guard(registration)
    root = resolve_within_root(registration.canonical_root)
    files = iter_files_within(root, suffixes=_SUFFIXES, limit=None)

    # Cursor is the last-processed file's path; simple lexical resume. Because record filenames are
    # ISO-timestamp-prefixed and immutable, lexical order is chronological order (ADR 0002 §1) — the
    # immutable-record ordering is retained while the cap follows the cursor filter.
    if cursor:
        files = [f for f in files if str(f) > cursor]

    has_more = len(files) > base.MAX_FILES_PER_SCAN
    files = files[:base.MAX_FILES_PER_SCAN]
    if limit is not None and len(files) > limit:
        files = files[:limit]
        has_more = True

    candidates = []
    filters = {"not_google_doc": 0, "unregistered_folder": 0}
    membership = read_folder_membership(root)
    registered = set(registration.role_identity.get("registered_folders", []))
    warnings: list[ScanWarning] = []
    for path in files:
        try:
            text = read_capped(path)
        except AdapterQuarantine as exc:
            warnings.append(ScanWarning(locator=str(path), reason=str(exc)))
            continue
        try:
            records = parse_export_file(text)
        except Exception as exc:  # defensive: a hand-edited file must never abort the whole scan
            warnings.append(ScanWarning(locator=str(path), reason=f"unparseable drive export file: {exc}"))
            continue
        for record in records:
            if record["mime_type"] != GOOGLE_DOC_MIME:
                filters["not_google_doc"] += 1
                continue
            if membership.get(record["file_id"], {}).get("folder_id") not in registered:
                filters["unregistered_folder"] += 1
                continue
            body = record["body"]
            # An emptied revision must replace its older observations too.
            file_id = record["file_id"]
            revision_id = record["revision_id"]
            modified_time = record["modified_time"]
            candidate = make_candidate(
                subject_id=registration.subject_id,
                source_id=registration.source_id,
                # Identity is file_id ALONE (ADR 0002 Decision 2) — never file_id:revision_id.
                source_native_id=file_id,
                role=DRIVE_EXPORT_ROLE,
                raw_text=body,
                locator=f"drive:{file_id}:{revision_id}",
                channel="docs",
                output_type="doc",
                timestamp=_parse_timestamp(modified_time),
            )
            # Provenance carrier for the store's Drive-only supersede-if-newer path: modified_time is
            # the authoritative (time-ordinal) comparator; revision_id is opaque provenance only.
            candidate.context = {"modified_time": modified_time, "revision_id": revision_id}
            candidates.append(candidate)

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


__all__ = ["scan", "ADAPTER_VERSION", "DRIVE_EXPORT_ROLE"]
