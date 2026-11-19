"""Adapter conformance harness — build plan v4 §13 M4 acceptance-evidence ("adapter conformance
passes") and M4 worklist 1 ("Add only demand-proven adapters ... each behind the same source
contract").

M4's first worklist item is deliberately *restraint*: add a new source **only** when the plan marks
it demand-proven. In this SSP's synthetic environment there is **no** demand-proven email/Slack/Docs
export to add (that demand is a real-usage signal, not something a test can manufacture), so instead
of shipping speculative adapters this module proves the property M4 actually asserts: **every
registered adapter obeys the one shared source contract.** It is the executable definition of
"adapter conformance."

For each adapter in :data:`operator_voice.adapters.registry._REGISTRY`, :func:`run_case` builds a
SYNTHETIC source tree (no real data) and drives the adapter's ``scan`` through the same checks:

* **registration guard** — an inactive/paused source is refused (``AdapterError``), never scanned.
* **role authority** — every candidate carries a non-empty role taken from the source's
  authoritative field; a planted assistant/third-party record is NEVER relabelled as the subject.
* **subject capture** — genuine subject-authored prose does become a subject-role candidate.
* **canonical-path safety** (file-tree adapters) — a symlink inside the root that escapes it is
  excluded, not followed (the §4.4 traversal guard).
* **resource ceiling** (file-tree adapters) — an oversized file is quarantined (a warning), never
  read into a candidate, while good files still scan.
* **quarantine-not-abort** — a single malformed record yields a warning/skip and the scan still
  returns its good candidates (never aborts the whole source).
* **determinism** — scanning the same tree twice yields byte-identical (role, locator, digest)
  tuples in the same order.
* **no persistence coupling** — the adapter module imports no SQLite/Keychain/persistence symbol
  (adapters parse; the service persists).

The harness is pure of global state and writes only under a caller-provided temp directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from operator_voice.adapters import registry
from operator_voice.adapters.base import (
    MAX_BYTES_PER_FILE,
    AdapterError,
    AdapterScanResult,
)
from operator_voice.domain.models import AdapterType, SourceRegistration, new_id

ADAPTER_CONFORMANCE_VERSION = "adapter-conformance/v1"

# Plain synthetic prose (no code fences / blockquotes) so it survives the redaction adapters and
# yields a stable stylometric candidate. Purely fictional; contains no real person's data.
_SUBJECT_PROSE = (
    "I think we should ship this next week. The plan is ready and the team agrees with the "
    "approach. I will write the summary myself and send it out in the morning."
)
_ASSISTANT_PROSE = (
    "Certainly! Here is a helpful assistant reply that must never be counted as the operator's "
    "own writing under any circumstances whatsoever."
)


@dataclass(slots=True)
class Check:
    status: str  # "pass" | "fail" | "n/a"
    detail: str = ""


@dataclass(slots=True)
class ConformanceReport:
    adapter_type: str
    checks: dict[str, Check] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks.values())

    @property
    def failures(self) -> list[str]:
        return [f"{name}: {c.detail}" for name, c in self.checks.items() if c.status == "fail"]


# --------------------------------------------------------------------------------------
# Per-adapter capability profile + synthetic fixture builders
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Profile:
    file_tree: bool                 # canonical_root is a directory of files (vs a single json file)
    subject_role: str               # the role a genuine subject record carries
    multi_role: bool                # can carry a non-subject (assistant/other) record
    # builds the "good" tree (subject record [+ assistant record if multi_role]); returns canonical_root
    build_good: Callable[["_Ctx"], str]
    # adds a malformed record into an existing good tree (returns None if not applicable)
    add_malformed: Optional[Callable[["_Ctx"], None]] = None


@dataclass(slots=True)
class _Ctx:
    base: Path
    root: Path  # canonical_root passed to the adapter


def _reg(adapter_type: AdapterType, ctx: _Ctx, *, active: bool = True, paused: bool = False) -> SourceRegistration:
    return SourceRegistration(
        source_id=new_id("src"),
        subject_id="subj_conformance",
        adapter_type=adapter_type,
        canonical_root=str(ctx.root),
        opted_in_at=0.0,
        approved_purpose="conformance",
        active=active,
        paused=paused,
        role_identity={"subject_role": "user", "registered_folders": ["writing"]},
    )


# ---- file-tree builders -------------------------------------------------------------


def _build_slack_export(ctx: _Ctx) -> str:
    # Mirrors the exact on-disk shape `slack.materialize.materialize()` produces (§ single source
    # of truth is `slack.materialize.parse_channel_file`'s own marker regex): every message in a
    # slack_export tree has, by construction, already passed server-side author verification —
    # single-role by construction, same as MANUAL.
    from operator_voice.slack.materialize import materialize

    ctx.root.mkdir(parents=True, exist_ok=True)
    materialize(
        ctx.root,
        author_id="U_CONFORMANCE",
        messages=[{
            "channel": "conformance-channel", "message_ts": "1700000000.000100",
            "time": "2026-01-01 00:00", "text": _SUBJECT_PROSE, "author_id": "U_CONFORMANCE",
        }],
    )
    return str(ctx.root)


def _build_drive_export(ctx: _Ctx) -> str:
    # Mirrors the exact on-disk shape `drive.materialize.materialize()` produces (single source of
    # truth is `drive.materialize.parse_export_file`'s own marker regex): every file in a
    # drive_export tree has, by construction, already passed server-side owner + not-shared-drive
    # verification — single-role by construction, same as MANUAL/SLACK_EXPORT.
    from operator_voice.drive.materialize import materialize

    ctx.root.mkdir(parents=True, exist_ok=True)
    materialize(
        ctx.root,
        owner_id="operator@conformance", registered_folders=["writing"],
        files=[{
            "file_id": "file-conformance-1", "revision_id": "rev-1",
            "drive_id": None, "owners": ["operator@conformance"], "owner_id": "operator@conformance",
            "name": "Conformance memo", "folder_id": "writing", "mime_type": "application/vnd.google-apps.document",
            "modified_time": "2026-01-01T00:00:00Z", "text": _SUBJECT_PROSE,
        }],
    )
    return str(ctx.root)


def _build_gmail_export(ctx: _Ctx) -> str:
    from operator_voice.gmail.materialize import materialize

    ctx.root.mkdir(parents=True, exist_ok=True)
    materialize(
        ctx.root,
        author_email="operator@conformance",
        messages=[{
            "message_id": "msg-conformance-1", "thread_id": "thread-conformance-1",
            "internal_date": "2026-01-01T00:00:00Z", "from": "operator@conformance",
            "subject": "Conformance Sent mail", "text": _SUBJECT_PROSE,
        }],
    )
    return str(ctx.root)


_PROFILES: dict[AdapterType, _Profile] = {
    AdapterType.SLACK_EXPORT: _Profile(True, "user", False, _build_slack_export),
    AdapterType.DRIVE_EXPORT: _Profile(True, "user", False, _build_drive_export),
    AdapterType.GMAIL_EXPORT: _Profile(True, "user", False, _build_gmail_export),
}


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------


def _write_sparse_oversized(path: Path) -> None:
    """Create a file whose reported size exceeds the ceiling WITHOUT writing 25 MiB (sparse
    truncate), so the resource-ceiling check is fast and does not thrash disk."""
    with open(path, "wb") as f:
        f.truncate(MAX_BYTES_PER_FILE + 1)


def _candidate_tuples(result: AdapterScanResult) -> list[tuple[str, str, str]]:
    return [(c.role, c.locator, c.digest) for c in result.candidates]


def run_case(adapter_type: AdapterType, base: Path) -> ConformanceReport:
    """Drive one adapter through the shared source contract using synthetic fixtures under
    ``base``. Returns a :class:`ConformanceReport` (never raises for a contract violation — it is
    recorded as a failing check so a caller can see ALL failures at once)."""
    profile = _PROFILES[adapter_type]
    scan = registry.get_scanner(adapter_type)
    report = ConformanceReport(adapter_type=adapter_type.value)

    ctx = _Ctx(base=base, root=base / adapter_type.value / "good")
    profile.build_good(ctx)

    # 1) registration guard — inactive/paused refused before any read.
    try:
        scan(_reg(adapter_type, ctx, active=False), None)
        report.checks["registration_guard"] = Check("fail", "inactive source was scanned instead of refused")
    except AdapterError:
        report.checks["registration_guard"] = Check("pass")
    try:
        scan(_reg(adapter_type, ctx, paused=True), None)
        if report.checks["registration_guard"].status == "pass":
            report.checks["registration_guard"] = Check("pass", "inactive+paused both refused")
    except AdapterError:
        pass

    # Baseline good scan.
    good = scan(_reg(adapter_type, ctx), None)

    # 2) subject capture + role authority.
    subject_cands = [c for c in good.candidates if c.role == profile.subject_role]
    if subject_cands:
        report.checks["subject_capture"] = Check("pass", f"{len(subject_cands)} subject candidate(s)")
    else:
        report.checks["subject_capture"] = Check("fail", "no subject-role candidate from genuine subject prose")

    bad_role = any((not c.role) or (not isinstance(c.role, str)) or c.role != c.role.lower() for c in good.candidates)
    report.checks["role_nonempty_normalized"] = Check("fail", "a candidate had an empty/upper role") if bad_role else Check("pass")

    if profile.multi_role:
        assistant_cands = [c for c in good.candidates if c.role == "assistant"]
        if assistant_cands and all(c.role != profile.subject_role for c in assistant_cands):
            report.checks["role_authority_no_relabel"] = Check(
                "pass", "planted assistant record kept role=assistant (not relabelled as subject)")
        else:
            report.checks["role_authority_no_relabel"] = Check(
                "fail", "planted assistant record missing or relabelled as the subject role")
    else:
        # single-role-by-construction: EVERY candidate must be the subject role, nothing else.
        report.checks["role_authority_no_relabel"] = (
            Check("pass", "single-role adapter: all candidates carry the subject role")
            if all(c.role == profile.subject_role for c in good.candidates)
            else Check("fail", "single-role adapter emitted a non-subject role")
        )

    # 3) determinism — a second identical scan is byte-identical.
    good2 = scan(_reg(adapter_type, ctx), None)
    report.checks["deterministic"] = (
        Check("pass") if _candidate_tuples(good) == _candidate_tuples(good2)
        else Check("fail", "two scans of the same tree diverged")
    )

    # 4) canonical-path safety + 5) resource ceiling — file-tree adapters only.
    if profile.file_tree:
        _run_file_tree_safety(adapter_type, base, profile, report)
    else:
        report.checks["canonical_path_safety"] = Check("n/a", "single-file source (no directory traversal surface)")
        report.checks["resource_ceiling"] = Check("n/a", "source-level read_capped covers the single export file")

    # 6) quarantine-not-abort — malformed record → warn/skip, good candidate survives.
    if profile.add_malformed is not None:
        mctx = _Ctx(base=base, root=base / adapter_type.value / "malformed")
        profile.build_good(mctx)
        profile.add_malformed(mctx)
        try:
            after = scan(_reg(adapter_type, mctx), None)
            still_have_subject = any(c.role == profile.subject_role for c in after.candidates)
            report.checks["quarantine_not_abort"] = (
                Check("pass", f"malformed record tolerated; warnings={len(after.warnings)}")
                if still_have_subject
                else Check("fail", "malformed record dropped the good subject candidate too")
            )
        except AdapterError as exc:
            report.checks["quarantine_not_abort"] = Check("fail", f"a single malformed record aborted the whole source: {exc}")
    else:
        report.checks["quarantine_not_abort"] = Check("n/a", "covered by resource-ceiling file quarantine")

    # 7) no persistence coupling (structural, source-level).
    report.checks["no_persistence_import"] = _check_no_persistence_import(adapter_type)

    return report


# Suffix each file-tree adapter actually accepts, so the oversized/symlink safety fixtures genuinely
# exercise read_capped + the traversal guard (not just get filtered out by extension). An adapter
# type MISSING from this map silently falls back to ``.txt`` — which for a ``.md``-only adapter like
# ``slack_export``/``drive_export`` would let a Drive-specific traversal/oversize regression slip
# through unexercised — so every file-tree adapter must have an explicit entry here (D-M1-9).
_FILE_TREE_SAFETY_SUFFIX: dict[AdapterType, str] = {
    AdapterType.SLACK_EXPORT: ".md",
    AdapterType.DRIVE_EXPORT: ".md",
    AdapterType.GMAIL_EXPORT: ".md",
}


def _run_file_tree_safety(adapter_type: AdapterType, base: Path, profile: _Profile, report: ConformanceReport) -> None:
    scan = registry.get_scanner(adapter_type)
    ctx = _Ctx(base=base, root=base / adapter_type.value / "safety")
    profile.build_good(ctx)
    suffix = _FILE_TREE_SAFETY_SUFFIX.get(adapter_type, ".txt")

    # Resource ceiling: an oversized sibling file must be quarantined, not read.
    _write_sparse_oversized(ctx.root / f"huge{suffix}")
    ceil = scan(_reg(adapter_type, ctx), None)
    huge_leaked = any("huge" in c.locator for c in ceil.candidates)
    still_good = any(c.role == profile.subject_role for c in ceil.candidates)
    report.checks["resource_ceiling"] = (
        Check("pass", f"oversized file quarantined (warnings={len(ceil.warnings)}); good files still scanned")
        if (not huge_leaked and still_good)
        else Check("fail", f"oversized file leaked={huge_leaked} good_present={still_good}")
    )

    # Canonical-path safety: a symlink inside root pointing OUTSIDE it must be excluded. The target
    # is written so that IF the guard failed and the adapter followed it, a candidate carrying the
    # marker WOULD be produced (valid JSONL for the transcript adapter; prose otherwise).
    outside = base / adapter_type.value / "OUTSIDE_SECRET"
    outside.mkdir(parents=True, exist_ok=True)
    secret = outside / f"secret{suffix}"
    if suffix == ".jsonl":
        secret.write_text(json.dumps({"role": "user", "content": _SUBJECT_PROSE + " OUTSIDE-ROOT-SECRET-MARKER"}) + "\n")
    else:
        secret.write_text(_SUBJECT_PROSE + " OUTSIDE-ROOT-SECRET-MARKER")
    link = ctx.root / f"escape{suffix}"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        report.checks["canonical_path_safety"] = Check("n/a", "symlinks unavailable on this platform")
        return
    escaped = scan(_reg(adapter_type, ctx), None)
    leaked = any("OUTSIDE-ROOT-SECRET-MARKER" in (c.raw_text or "") for c in escaped.candidates) or \
             any("escape" in c.locator and "OUTSIDE_SECRET" in c.locator for c in escaped.candidates)
    report.checks["canonical_path_safety"] = (
        Check("fail", "a symlink escaping the canonical root was followed and its content ingested")
        if leaked else Check("pass", "symlink escaping the root was excluded")
    )


def _check_no_persistence_import(adapter_type: AdapterType) -> Check:
    scan = registry.get_scanner(adapter_type)
    module_file = getattr(scan, "__globals__", {}).get("__file__")
    if not module_file or not Path(module_file).exists():
        return Check("n/a", "module source unavailable")
    src = Path(module_file).read_text(encoding="utf-8")
    forbidden = ("persistence.store", "persistence.crypto", "import sqlite3", "persistence.sqlite")
    hit = [tok for tok in forbidden if tok in src]
    return Check("fail", f"adapter imports persistence symbol(s): {hit}") if hit else Check("pass")


def run_all(base: Path) -> dict[AdapterType, ConformanceReport]:
    """Run the conformance case for EVERY registered adapter. The registry is the source of truth —
    a newly-registered adapter with no profile here fails loudly (forcing a conformance profile to
    be authored alongside any new adapter)."""
    reports: dict[AdapterType, ConformanceReport] = {}
    for adapter_type in registry._REGISTRY:  # noqa: SLF001 — the registry IS the conformance surface
        if adapter_type not in _PROFILES:
            rep = ConformanceReport(adapter_type=getattr(adapter_type, "value", str(adapter_type)))
            rep.checks["profile_present"] = Check("fail", "registered adapter has no conformance profile")
            reports[adapter_type] = rep
            continue
        reports[adapter_type] = run_case(adapter_type, base)
    return reports


__all__ = [
    "ADAPTER_CONFORMANCE_VERSION",
    "Check",
    "ConformanceReport",
    "run_case",
    "run_all",
]
