"""Shared adapter contract + safety helpers — build plan v3 §4.4 threat model row "Malicious or
malformed source content": "Strict parsers, size/record caps, path canonicalization, sandboxed
adapters, resource ceilings, quarantine on parse failure."

Every adapter module exposes exactly one entrypoint, ``scan(registration, cursor) ->
AdapterScanResult``, matching this shape. No adapter reads or writes SQLite/Keychain — the
application service owns all persistence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from operator_voice.domain.models import ObservationCandidate, SourceRegistration, new_id

ADAPTER_VERSION = "adapters/v2"

# §4.4: hard resource ceilings so a malicious/huge export can never exhaust memory/disk in one
# ingest call. Deliberately generous for real chat exports, deliberately finite.
MAX_FILES_PER_SCAN = 5_000
MAX_RECORDS_PER_SCAN = 50_000
MAX_BYTES_PER_FILE = 25 * 1024 * 1024  # 25 MiB
MAX_TEXT_CHARS_PER_CANDIDATE = 200_000


class AdapterError(RuntimeError):
    """Raised for a source-level failure (bad path, unreadable file). The caller (application
    service) is responsible for quarantining the source, never crashing the whole ingest run."""


class AdapterQuarantine(RuntimeError):
    """Raised for a single malformed RECORD inside an otherwise-good source (bad JSON, missing
    required field). Distinguished from :class:`AdapterError` so the service can quarantine one
    bad record/file and continue the rest of the scan (§4.4: 'quarantine on parse failure', not
    'abort the whole ingest')."""


@dataclass(slots=True)
class ScanWarning:
    locator: str
    reason: str


@dataclass(slots=True)
class AdapterScanResult:
    candidates: list[ObservationCandidate]
    next_cursor: Optional[str]
    warnings: list[ScanWarning] = field(default_factory=list)
    files_scanned: int = 0
    records_scanned: int = 0
    # §13 M3 worklist 3 "bounded continuation": True when this scan stopped at a caller-supplied
    # ``limit`` with more work still available past ``next_cursor``. The curation engine reads this
    # to schedule a continuation on the next tick; it defaults False so every M1/M2 adapter that
    # never sets it keeps its exact prior (unbounded) behavior.
    has_more: bool = False
    filter_counts: dict[str, int] = field(default_factory=dict)


def resolve_within_root(canonical_root: str, *, must_exist: bool = True) -> Path:
    """Canonicalizes ``canonical_root`` and refuses anything that isn't a real, readable path.
    This is the ONLY path adapters accept from a :class:`SourceRegistration` — never a raw,
    un-resolved string — closing the symlink/`..`-traversal escape named in §4.4."""
    root = Path(canonical_root).expanduser().resolve()
    if must_exist and not root.exists():
        raise AdapterError(f"canonical_root does not exist: {canonical_root!r}")
    return root


def iter_files_within(
    root: Path, *, suffixes: tuple[str, ...], limit: int | None = MAX_FILES_PER_SCAN,
) -> list[Path]:
    """Every yielded path is verified (via ``resolve()`` + ``is_relative_to``) to still be inside
    ``root`` after symlink resolution — a symlink inside the root that points outside it is
    excluded rather than followed."""
    if root.is_file():
        candidates = [root]
    else:
        candidates = sorted(p for p in root.rglob("*") if p.is_file())
    out: list[Path] = []
    for p in candidates:
        if suffixes and p.suffix.lower() not in suffixes:
            continue
        try:
            resolved = p.resolve()
        except OSError:
            continue
        if not _is_relative_to(resolved, root):
            continue
        if limit is not None and len(out) >= limit:
            break
        out.append(p)
    return out


WATERMARK_PREFIX = "change-v1\x1f"


@dataclass(frozen=True, slots=True)
class FileWatermark:
    change_ns: int
    path: str
    line: int = -1  # -1: the whole file was consumed; >= 0: resume after this line (line-oriented adapters)

    def encode(self) -> str:
        return f"{WATERMARK_PREFIX}{self.change_ns}\x1f{self.line}\x1f{self.path}"

    @classmethod
    def decode(cls, cursor: str | None) -> "FileWatermark | None":
        if not cursor or not cursor.startswith(WATERMARK_PREFIX):
            return None
        change_ns, line, path = cursor[len(WATERMARK_PREFIX):].split("\x1f", 2)
        return cls(int(change_ns), path, int(line))


def files_changed_since(root, *, suffixes, watermark, exclude_parts=frozenset()):
    keyed = []
    for path in iter_files_within(root, suffixes=suffixes, limit=None):
        if exclude_parts and exclude_parts.intersection(path.parts):
            continue
        st = path.stat()
        key = (max(st.st_mtime_ns, st.st_ctime_ns), str(path))
        if watermark is not None:
            mark = (watermark.change_ns, watermark.path)
            if key < mark or (key == mark and watermark.line < 0):
                continue
        keyed.append((key[0], path))
    keyed.sort(key=lambda item: (item[0], str(item[1])))
    return keyed[:MAX_FILES_PER_SCAN], len(keyed) > MAX_FILES_PER_SCAN


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def read_capped(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_BYTES_PER_FILE:
        # No path in this message: every caller already carries the same path separately as the
        # ScanWarning's own `locator` field. Embedding it a second time here just duplicated an
        # absolute filesystem path (which can reveal the operator's home-directory username) into
        # a second, easy-to-forget-about field with no offsetting benefit (M1 P2-4, closed M5-B).
        raise AdapterQuarantine(f"exceeds MAX_BYTES_PER_FILE ({size} > {MAX_BYTES_PER_FILE})")
    return path.read_text(encoding="utf-8", errors="replace")


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_candidate(
    *,
    subject_id: str,
    source_id: str,
    source_native_id: str,
    role: str,
    raw_text: str,
    locator: str,
    author_id: Optional[str] = None,
    channel: str = "general",
    output_type: str = "text",
    timestamp: float | None = None,
) -> ObservationCandidate:
    text = raw_text[:MAX_TEXT_CHARS_PER_CANDIDATE]
    from operator_voice.domain.models import now_ts

    return ObservationCandidate(
        candidate_id=new_id("cand"),
        claimed_subject_id=subject_id,
        source_id=source_id,
        source_native_id=source_native_id,
        role=role,
        raw_text=text,
        digest=digest_text(text),
        locator=locator,
        author_id=author_id,
        channel=channel,
        output_type=output_type,
        timestamp=timestamp if timestamp is not None else now_ts(),
    )


def registration_guard(registration: SourceRegistration) -> None:
    """§5 'No source ships enabled': every adapter's ``scan`` must refuse a source that is not
    both ``active`` and not ``paused`` — this is re-checked here (not just by the service) so a
    unit test can call an adapter directly and still get the safety guarantee."""
    if not registration.active or registration.paused:
        raise AdapterError(f"source {registration.source_id} is not active (active={registration.active}, paused={registration.paused})")
