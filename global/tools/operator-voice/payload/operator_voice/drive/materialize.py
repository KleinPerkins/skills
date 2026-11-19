"""Drive export materialization — OVT Drive Adapter v2 (agent-delegated fetch, owner-only, no token).

Turns an agent-submitted JSON envelope of the operator's own Google Drive files (fetched agent-side
via the operator's host Drive tools; this module never calls Google — no network, no SDK, no token,
no OAuth) into immutable, timestamp-prefixed **one-file-per-revision** Markdown under the operator's
fixed ``drive_export_dir``, ready for the ``drive_export`` adapter to scan like any other file-tree
source.

**The hard security invariants** (all enforced HERE, server-side, fail-closed — never trusted from
the calling agent's own "these are all mine, all My-Drive" filtering; ADR 0002 Decision 3):

* **Owner-only.** Each file's ``owners`` list must be exactly ``[owner_id]`` (the operator's own,
  self-asserted Drive id for this call) AND the entry's own ``owner_id`` must match it — a
  multi-owner / co-authored file is dropped under ``skipped_shared_ownership`` /
  ``skipped_mismatched_owner``, never counted.
* **Not a Shared Drive.** ``drive_id`` must be present-and-null (My Drive). A non-null ``drive_id``
  — OR a MISSING ``drive_id`` key — is dropped under ``skipped_shared_drive`` (a missing key is never
  read as proof of My Drive).
* **Fail-closed on any missing required key.** A missing key is rejected exactly like a
  present-but-disqualifying value; nothing is inferred.

**Identity vs. provenance (ADR 0002 Decision 2):** persisted document identity is ``file_id`` ALONE
(the ``source_native_id`` the store dedups on). ``revision_id`` + ``modified_time`` are carried as
provenance — ``modified_time`` is the authoritative supersede-if-newer comparator in
``persistence/store.py`` (``revision_id`` is opaque/non-ordinal, never used to order). Each revision
is written as its OWN immutable file named ``<modified_time_iso>__<file_id>__<revision_id>.md`` (ADR
0002 Decision 1) so plain lexicographic filename order is chronological order — letting the
``drive_export`` adapter retain its lexical cursor. Folder membership is recorded separately
so the record format remains compatible with 0.1.9.
"""

from __future__ import annotations

from operator_voice.persistence.atomic import atomic_text

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MATERIALIZE_VERSION = "drive-materialize/v2"

_MIN_CHARS = 25  # skip ultra-short bodies unless multi-line (retained analytic heuristic)
_STATE_FILENAME = ".import-state.json"
_MEMBERSHIP_FILENAME = ".folder-membership.json"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"

# Every materialized record starts with a machine-parseable HTML-comment marker carrying Drive's own
# opaque ``file_id``/``revision_id`` (never re-derived, never guessed), the authoritative
# ``modified_time`` supersede comparator, and the agent-supplied ``mime_type`` (which the
# ``drive_export`` adapter maps to a taxonomy channel/output_type at scan time). The human-readable
# "## <name>" heading beneath it is cosmetic and is never parsed back.
_RECORD_BLOCK_RE = re.compile(
    r"<!-- ovt:drive file=(?P<file>\S+) rev=(?P<rev>\S+) modified=(?P<modified>\S+) mime=(?P<mime>\S+) -->"
    r"\n##[^\n]*\n\n(?P<body>.*?)(?=\n<!-- ovt:drive |\Z)",
    re.DOTALL,
)

_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def clean_text(text: str) -> str:
    """Normalize an agent-exported plain-text Drive body. Deliberately light — a Google Doc is
    already prose (no Slack-style markup to strip), so this only normalizes newlines and trims outer
    whitespace, never mangling the operator's own words."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _keep(text: str) -> bool:
    """Skip near-empty exports; keep any real document body (retained analytic heuristic:
    >= _MIN_CHARS, or multi-line and >= 12 chars)."""
    if not text:
        return False
    if len(text) >= _MIN_CHARS:
        return True
    return "\n" in text and len(text) >= 12


def _safe_component(value: str) -> str:
    """Filesystem-safe filename component. The RAW opaque id is preserved verbatim inside the record
    marker (recovered as ``source_native_id`` by the adapter); this only sanitizes the on-disk NAME,
    whose sole jobs are chronological sorting and uniqueness."""
    return _UNSAFE_FILENAME_RE.sub("-", value.strip()) or "unknown"


def _record_filename(modified_time: str, file_id: str, revision_id: str) -> str:
    """``<modified_time_iso>__<file_id>__<revision_id>.md`` with colons replaced by ``-`` (ADR 0002
    Decision 1) so the timestamp always sorts first and lexicographic order is chronological order."""
    ts_safe = _safe_component(modified_time.replace(":", "-"))
    return f"{ts_safe}__{_safe_component(file_id)}__{_safe_component(revision_id)}.md"


@dataclass(slots=True)
class MaterializeResult:
    imported: int = 0
    skipped_duplicate: int = 0
    skipped_mismatched_owner: int = 0
    skipped_shared_drive: int = 0
    skipped_shared_ownership: int = 0
    skipped_not_google_doc: int = 0
    skipped_unregistered_folder: int = 0
    skipped_short: int = 0
    skipped_invalid: int = 0
    files: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_mismatched_owner": self.skipped_mismatched_owner,
            "skipped_shared_drive": self.skipped_shared_drive,
            "skipped_shared_ownership": self.skipped_shared_ownership,
            "skipped_not_google_doc": self.skipped_not_google_doc,
            "skipped_unregistered_folder": self.skipped_unregistered_folder,
            "skipped_short": self.skipped_short,
            "skipped_invalid": self.skipped_invalid,
            "files": sorted(self.files),
        }


def _format_block(file_id: str, revision_id: str, modified_time: str, mime_type: str, name: str, body: str) -> str:
    heading = (name or file_id).replace("\n", " ").strip() or file_id
    return (
        f"<!-- ovt:drive file={file_id} rev={revision_id} modified={modified_time} mime={mime_type} -->\n"
        f"## {heading}\n\n{body}\n"
    )


def _record_header() -> str:
    return (
        "# Drive voice capture\n\n"
        "Operator-owned, non-Shared-Drive files only. Server-verified ownership "
        "(see `operator_voice.drive.materialize`). Generated by `operator-voice drive-import`.\n\n"
    )


def materialize(
    export_dir: Path, *, owner_id: str, files: list[Any],
    registered_folders: list[str] | None = None,
) -> MaterializeResult:
    """Write server-verified, owner-only Drive files into ``export_dir`` as immutable, timestamp-
    prefixed Markdown (one file per revision — ADR 0002 Decision 1).

    ``owner_id`` is the operator's own Drive user id, self-asserted for THIS call (never persisted;
    re-supplied fresh every time — see ``domain/operations.py``'s ``drive.import`` docstring, same
    pattern as Slack's ``author_id``). Every entry in ``files`` is verified server-side, fail-closed
    (ADR 0002 Decision 3):

    * ``drive_id`` — required key; present-and-null = My Drive. Non-null/non-empty, or the key
      missing, → ``skipped_shared_drive``.
    * ``owners`` — required list; must be exactly ``[owner_id]``. ``len != 1``, ``owners[0] !=
      owner_id``, or the key missing, → ``skipped_shared_ownership``.
    * entry ``owner_id`` — must equal the top-level ``owner_id``, else ``skipped_mismatched_owner``.
    * Google Docs only, with ``folder_id`` naming a registered ancestor; resolved shortcut targets
      use their own metadata and ``via_shortcut: true``. Folder shortcuts are never accepted.
    * ``file_id`` / ``revision_id`` / ``modified_time`` (non-empty strings), ``text`` (a string),
      ``mime_type`` (non-empty string) — any missing/ill-typed → ``skipped_invalid``.

    Idempotent: a record whose ``(modified_time, file_id, revision_id)`` filename already exists on
    disk (or repeats within this same batch) is counted under ``skipped_duplicate`` — the immutable
    per-revision file is never rewritten."""
    result = MaterializeResult()
    export_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    seen_filenames: set[str] = set()
    registered = set(registered_folders or [])
    membership = read_folder_membership(export_dir)

    for raw in files:
        if not isinstance(raw, dict):
            result.skipped_invalid += 1
            continue

        # 1) Not-a-Shared-Drive (fail-closed: the key MUST be present, and present-and-null = My Drive).
        if "drive_id" not in raw:
            result.skipped_shared_drive += 1
            continue
        drive_id = raw["drive_id"]
        if drive_id is not None and str(drive_id).strip() != "":
            result.skipped_shared_drive += 1
            continue

        # 2) Sole-ownership (owners must be exactly [owner_id]; missing/oversized list is fail-closed).
        owners = raw.get("owners")
        if not isinstance(owners, list) or len(owners) != 1 or str(owners[0]).strip() != owner_id:
            result.skipped_shared_ownership += 1
            continue

        # 3) Entry owner_id must match the top-level self-asserted owner_id (per-adapter vocabulary:
        #    skipped_mismatched_owner, never slack's skipped_mismatched_author).
        entry_owner = str(raw.get("owner_id") or "").strip()
        if not entry_owner or entry_owner != owner_id:
            result.skipped_mismatched_owner += 1
            continue

        # 4) Structural required fields (fail-closed on any missing/ill-typed key).
        file_id = str(raw.get("file_id") or "").strip()
        revision_id = str(raw.get("revision_id") or "").strip()
        modified_time = str(raw.get("modified_time") or "").strip()
        mime_type = str(raw.get("mime_type") or "").strip()
        text = raw.get("text")
        if not file_id or not revision_id or not modified_time or not mime_type or not isinstance(text, str):
            result.skipped_invalid += 1
            continue

        if mime_type != GOOGLE_DOC_MIME:
            result.skipped_not_google_doc += 1
            continue
        folder_id = raw.get("folder_id")
        if not isinstance(folder_id, str) or folder_id not in registered:
            result.skipped_unregistered_folder += 1
            continue
        if not isinstance(raw.get("via_shortcut", False), bool):
            result.skipped_invalid += 1
            continue

        cleaned = clean_text(text)
        if not _keep(cleaned) and file_id not in membership:
            result.skipped_short += 1
            continue

        # Backfill membership even when the immutable record already exists.
        membership[file_id] = {"folder_id": folder_id, "via_shortcut": raw.get("via_shortcut", False)}
        filename = _record_filename(modified_time, file_id, revision_id)
        path = export_dir / filename
        if filename in seen_filenames or path.exists():
            result.skipped_duplicate += 1
            continue
        seen_filenames.add(filename)

        name = str(raw.get("name") or "").strip()
        block = _format_block(file_id, revision_id, modified_time, mime_type, name, cleaned)
        atomic_text(path, _record_header() + block)
        result.imported += 1
        result.files.add(file_id)

    write_folder_membership(export_dir, membership)
    return result


def read_folder_membership(export_dir: Path) -> dict[str, dict[str, Any]]:
    """Text-free membership only. Missing or malformed sidecars fail closed for learning."""
    try:
        data = json.loads((export_dir / _MEMBERSHIP_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {file_id: {"folder_id": entry["folder_id"], "via_shortcut": entry["via_shortcut"]}
            for file_id, entry in data.items()
            if isinstance(entry, dict) and isinstance(entry.get("folder_id"), str)
            and isinstance(entry.get("via_shortcut"), bool)}


def write_folder_membership(export_dir: Path, membership: dict[str, dict[str, Any]]) -> None:
    export_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_text(export_dir / _MEMBERSHIP_FILENAME, json.dumps(membership, sort_keys=True))


def parse_export_file(text: str) -> list[dict[str, str]]:
    """Parse a materialized Drive record file back into ``{file_id, revision_id, modified_time,
    mime_type, body}`` dicts, in file order. The single on-disk-format parser, shared by the
    ``drive_export`` adapter (scan) and ``drive.status`` (counts). A record file holds exactly one
    marker by construction, but the parser is general (returns every marker it finds) and simply
    yields nothing for a hand-edited/markerless file rather than raising."""
    out: list[dict[str, str]] = []
    for m in _RECORD_BLOCK_RE.finditer(text):
        out.append({
            "file_id": m.group("file"),
            "revision_id": m.group("rev"),
            "modified_time": m.group("modified"),
            "mime_type": m.group("mime"),
            "body": m.group("body").strip(),
        })
    return out


def count_records_by_file(export_dir: Path) -> dict[str, int]:
    """Content-free per-``file_id`` revision counts for ``drive.status`` — reads only counts, never
    surfaces text. Missing ``export_dir`` (setup not yet run) is an empty result, not an error."""
    if not export_dir.exists():
        return {}
    counts: dict[str, int] = {}
    for path in sorted(export_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for record in parse_export_file(text):
            counts[record["file_id"]] = counts.get(record["file_id"], 0) + 1
    return counts


def read_import_state(export_dir: Path) -> dict[str, Any]:
    """Lean sidecar (not a SQLite table — a cosmetic freshness + sync-cursor signal for
    ``drive.status``, co-located with the content it describes). Missing/corrupt is empty, never an
    error — status reporting must never fail because of its own watermark file."""
    path = export_dir / _STATE_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_import_state(export_dir: Path, state: dict[str, Any]) -> None:
    export_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = export_dir / _STATE_FILENAME
    atomic_text(path, json.dumps(state))


__all__ = [
    "MATERIALIZE_VERSION",
    "MaterializeResult",
    "materialize",
    "parse_export_file",
    "count_records_by_file",
    "read_import_state",
    "write_import_state",
    "clean_text",
]
