"""Slack-export adapter — OVT Slack Adapter v1. Scans the per-channel Markdown files
``slack.import`` already materialized under the operator's fixed ``slack_export_dir``
(§ ``operator_voice.slack.materialize``); a completely ordinary file-tree scan, using the shared adapter safety checks.

Every message in a materialized file has ALREADY passed server-side author verification at
``slack.import`` time (a mismatched ``author_id`` never reaches disk in the first place), so this
adapter hardcodes ``role="user"``: there is no other author possible in a
``slack_export`` tree by construction. ``channel`` is likewise a fixed literal ``"slack"`` (the
communication MEDIUM, matching the closed retrieval taxonomy's canonical ``"slack"`` channel value
— see ``kernel/taxonomy.py``), never the individual Slack channel/DM name; the per-channel slug is
only a materialization-time file-grouping detail, carried in ``locator``/``source_native_id`` for
traceability and dedup, not in the candidate's retrieval-facing ``channel``.

Cursor: a change-ordered watermark using max(mtime_ns, ctime_ns) and path. Appended messages
and new files sorting before a previous path are revisited. A legacy path cursor causes one full
rescan; stable message identities keep the service's deduplication idempotent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from operator_voice.adapters.base import (
    ADAPTER_VERSION,
    AdapterQuarantine,
    AdapterScanResult,
    ScanWarning,
    FileWatermark,
    files_changed_since,
    make_candidate,
    read_capped,
    registration_guard,
    resolve_within_root,
)
from operator_voice.domain.models import SourceRegistration
from operator_voice.slack.materialize import parse_channel_file, read_message_versions

SLACK_EXPORT_ROLE = "user"
SLACK_EXPORT_CHANNEL = "slack"
_SUFFIXES = (".md",)


def keep_for_features_v1(text: str) -> bool:
    """Ported ``keep()`` heuristic: skip ultra-short casual replies unless multi-line."""
    if not text:
        return False
    if len(text) >= 25:
        return True
    return "\n" in text and len(text) >= 12


def _parse_timestamp(message_ts: str) -> float | None:
    try:
        return float(message_ts)
    except ValueError:
        return None


def scan(registration: SourceRegistration, cursor: str | None, limit: int | None = None) -> AdapterScanResult:
    registration_guard(registration)
    root = resolve_within_root(registration.canonical_root)
    files, has_more = files_changed_since(
        root, suffixes=_SUFFIXES, watermark=FileWatermark.decode(cursor),
    )

    if limit is not None and len(files) > limit:
        files = files[:limit]
        has_more = True

    candidates = []
    versions = read_message_versions(root)
    warnings: list[ScanWarning] = []
    for change_ns, path in files:
        try:
            text = read_capped(path)
        except AdapterQuarantine as exc:
            warnings.append(ScanWarning(locator=str(path), reason=str(exc)))
            continue
        channel_slug = path.stem
        try:
            messages = parse_channel_file(text)
        except Exception as exc:  # defensive: a hand-edited file must never abort the whole scan
            warnings.append(ScanWarning(locator=str(path), reason=f"unparseable slack export file: {exc}"))
            continue
        for message_ts, message_text in messages:
            revision = versions.get(channel_slug + ":" + message_ts)
            short = not keep_for_features_v1(message_text)
            if short and (revision is None or revision == message_ts):
                continue
            candidate = make_candidate(
                    subject_id=registration.subject_id,
                    source_id=registration.source_id,
                    source_native_id=f"{channel_slug}:{message_ts}",
                    role=SLACK_EXPORT_ROLE,
                    raw_text=message_text,
                    locator=f"slack:{channel_slug}:{message_ts}",
                    channel=SLACK_EXPORT_CHANNEL,
                    timestamp=_parse_timestamp(message_ts),
                )
            if revision is not None:
                candidate.context = {
                    "modified_time": datetime.fromtimestamp(float(revision), timezone.utc).isoformat(),
                    "initial_time": datetime.fromtimestamp(float(message_ts), timezone.utc).isoformat(),
                    "below_analytic_floor": short,
                }
            candidates.append(candidate)

    next_cursor = FileWatermark(files[-1][0], str(files[-1][1])).encode() if files else cursor
    return AdapterScanResult(
        candidates=candidates,
        next_cursor=next_cursor,
        warnings=warnings,
        files_scanned=len(files),
        records_scanned=len(candidates),
        has_more=has_more,
    )


__all__ = ["scan", "ADAPTER_VERSION", "SLACK_EXPORT_ROLE", "SLACK_EXPORT_CHANNEL"]
