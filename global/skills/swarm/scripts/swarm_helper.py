#!/usr/bin/env python3
"""Proportional /swarm helper — the whole engine in one small module.

Replaces the retired 16-module deterministic engine. Exposes only what the
proportional methodology needs: risk-score math, the D01-D16 dimension catalog,
a lean finding-shape validator, a probe->band cohort sizer, a model+rigor
routing catalog/resolver, accepted-worker accounting, exact-byte candidate
fingerprinting, coverage-first planning with bounded evidence packs, a curated
report renderer, and the section-7/section-8 decision gates. State is in-memory;
the only I/O helpers read candidate bytes or invoke read-only `git`.
"""

from __future__ import annotations

import decimal
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class ContractError(ValueError):
    """A deterministic validation failure surfaced to the orchestrator/operator."""


class CapacityError(ContractError):
    """Preflight refusal when required coverage cannot fit bounded capacity."""


# --- Primitive validators ---

def _object(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{where}: expected object")
    return value


def _list(value: Any, where: str, *, max_items: int = 500) -> list:
    if not isinstance(value, list):
        raise ContractError(f"{where}: expected array")
    if len(value) > max_items:
        raise ContractError(f"{where}: exceeds {max_items} items")
    return value


def _text(value: Any, where: str, *, allow_empty: bool = False, max_bytes: int = 4096) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{where}: expected string")
    if len(value.encode("utf-8")) > max_bytes:
        raise ContractError(f"{where}: exceeds {max_bytes} bytes")
    if not allow_empty and not value.strip():
        raise ContractError(f"{where}: must not be empty")
    return value


def _int(value: Any, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{where}: expected integer")
    if not low <= value <= high:
        raise ContractError(f"{where}: expected {low}..{high}")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{where}: expected boolean")
    return value


def _closed(obj: Mapping[str, Any], keys: set, where: str) -> None:
    missing = keys - set(obj)
    extra = set(obj) - keys
    if missing:
        raise ContractError(f"{where}: missing keys {sorted(missing)}")
    if extra:
        raise ContractError(f"{where}: unknown keys {sorted(extra)}")


def _text_list(value: Any, where: str) -> list:
    return [_text(v, f"{where}[{i}]", allow_empty=True) for i, v in enumerate(_list(value, where))]


# --- Exact-byte candidate identity ---

CANDIDATE_ID_PATTERN = r"sha256:[0-9a-f]{64}"
CANDIDATE_KEYS = {"candidate_id", "revision", "files"}
CANDIDATE_FILE_KEYS = {"path", "sha256", "bytes", "lines"}


def _relative_path(value: Any, where: str) -> str:
    text = _text(value, where)
    path = Path(text)
    if path.is_absolute() or text in {".", ".."} or ".." in path.parts:
        raise ContractError(f"{where}: expected a normalized relative path")
    normalized = path.as_posix()
    if normalized != text or normalized.startswith("./"):
        raise ContractError(f"{where}: expected normalized POSIX form")
    return normalized


def build_candidate_identity(
    revision: str, files: Sequence[Mapping[str, Any]]
) -> dict:
    """Build a deterministic identity from revision plus exact file-byte digests."""
    revision = _text(revision, "candidate.revision")
    normalized_files: list[dict] = []
    for index, raw in enumerate(_list(list(files), "candidate.files")):
        item = _object(raw, f"candidate.files[{index}]")
        _closed(item, CANDIDATE_FILE_KEYS, f"candidate.files[{index}]")
        digest = _text(item["sha256"], f"candidate.files[{index}].sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContractError(
                f"candidate.files[{index}].sha256: expected 64 lowercase hex characters"
            )
        normalized_files.append(
            {
                "path": _relative_path(
                    item["path"], f"candidate.files[{index}].path"
                ),
                "sha256": digest,
                "bytes": _int(
                    item["bytes"], f"candidate.files[{index}].bytes", 0, 10**12
                ),
                "lines": _int(
                    item["lines"], f"candidate.files[{index}].lines", 0, 10**9
                ),
            }
        )
    normalized_files.sort(key=lambda entry: entry["path"])
    paths = [entry["path"] for entry in normalized_files]
    if len(paths) != len(set(paths)):
        raise ContractError("candidate.files: duplicate path")
    payload = {"revision": revision, "files": normalized_files}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "candidate_id": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        **payload,
    }


def validate_candidate_identity(value: Any, where: str = "candidate") -> dict:
    item = _object(value, where)
    _closed(item, CANDIDATE_KEYS, where)
    rebuilt = build_candidate_identity(item["revision"], item["files"])
    supplied = _text(item["candidate_id"], f"{where}.candidate_id")
    if not re.fullmatch(CANDIDATE_ID_PATTERN, supplied):
        raise ContractError(
            f"{where}.candidate_id: expected sha256:<64 lowercase hex>"
        )
    if supplied != rebuilt["candidate_id"]:
        raise ContractError(
            f"{where}.candidate_id: does not match revision and file-byte manifest"
        )
    return rebuilt


def fingerprint_candidate(root: str, revision: str, paths: Sequence[str]) -> dict:
    """Read exact in-scope bytes and return a deterministic candidate manifest."""
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise ContractError(f"candidate root is not a directory: {root}")
    records: list[dict] = []
    for index, raw in enumerate(_list(list(paths), "paths")):
        relative = _relative_path(raw, f"paths[{index}]")
        source = root_path / relative
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(root_path)
        except (OSError, ValueError) as exc:
            raise ContractError(
                f"paths[{index}]: outside root, missing, or unreadable: {relative}"
            ) from exc
        if source.is_symlink() or not resolved.is_file():
            raise ContractError(
                f"paths[{index}]: expected a regular non-symlink file: {relative}"
            )
        data = resolved.read_bytes()
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "lines": data.count(b"\n")
                + int(bool(data) and not data.endswith(b"\n")),
            }
        )
    if not records:
        raise ContractError("paths: at least one in-scope file is required")
    return build_candidate_identity(revision, records)


# --- D01-D16 dimension catalog (the map, not 16 review obligations) ---

DIMENSION_NAMES = {
    "D01": "Functional correctness and domain logic",
    "D02": "Interfaces, APIs, protocols, schemas, and contracts",
    "D03": "Data integrity, persistence, migrations, and state transitions",
    "D04": "Security, authorization, trust boundaries, and abuse resistance",
    "D05": "Privacy, secrets, PII, logging, and information exposure",
    "D06": "Reliability, lifecycle, failure handling, recovery, and rollback",
    "D07": "Concurrency, ordering, idempotency, races, and distributed behavior",
    "D08": "Performance, resource bounds, scalability, and degradation",
    "D09": "Backward compatibility, interoperability, and upgrade behavior",
    "D10": "Dependency, integration, supply-chain, and external-service risk",
    "D11": "Testing quality, negative coverage, and evidence strength",
    "D12": "Observability, diagnostics, auditability, and operational readiness",
    "D13": "User experience, accessibility, internationalization, operator clarity",
    "D14": "Architecture, maintainability, coupling, and technical debt",
    "D15": "Policy, governance, compliance, ownership, and repository rules",
    "D16": "Build, packaging, configuration, release, deployment, and cleanup",
}
DIMENSIONS = tuple(sorted(DIMENSION_NAMES))  # ("D01", ..., "D16")

# Protected axes referenced by band selection and probe routing.
PROTECTED_AXES = {
    "state_migration_D03": ("D03",),
    "security_privacy_D04_D05": ("D04", "D05"),
    "concurrency_D07": ("D07",),
    "reliability_release_D06_D16": ("D06", "D16"),
}

EVIDENCE_LINEAGES = {"source-confirmed", "parent-test-confirmed", "externally-supplied", "unverified"}
CONFIRMED_LINEAGES = {"source-confirmed", "parent-test-confirmed"}
FINDING_STATUSES = {
    "open", "fixed", "verified", "duplicate",
    "false-positive", "deferred", "accepted-risk", "insufficient-evidence",
}
PRIORITIES = ("P0", "P1", "P2", "P3", "P4")
FINDING_ID_PATTERN = r"[a-z][a-z0-9-]{2,127}"


# --- Risk-score math (salvaged verbatim: weighted 0.40/0.30/0.15/0.15 x 20) ---

def calculate_risk(impact: int, likelihood: int, exposure: int, irreversibility: int) -> int:
    """Weighted 1..100 finding risk from four 1..5 factors (deterministic)."""
    for name, value in (("impact", impact), ("likelihood", likelihood),
                        ("exposure", exposure), ("irreversibility", irreversibility)):
        _int(value, name, 1, 5)
    weighted = decimal.Decimal(20) * (
        decimal.Decimal("0.40") * impact
        + decimal.Decimal("0.30") * likelihood
        + decimal.Decimal("0.15") * exposure
        + decimal.Decimal("0.15") * irreversibility
    )
    return int(weighted.quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def priority_for(risk_score: int, unsafe_to_ship: bool = False) -> str:
    """Map a 1..100 risk score (or an unsafe-to-ship flag) to P0..P4."""
    _int(risk_score, "risk_score", 1, 100)
    if unsafe_to_ship or risk_score >= 90:
        return "P0"
    if risk_score >= 70:
        return "P1"
    if risk_score >= 40:
        return "P2"
    if risk_score >= 10:
        return "P3"
    return "P4"


# --- Lean finding shape (§4.4): no essays; evidence by reference ---

EVIDENCE_KEYS = {"ref", "lineage"}
IMPACT_KEYS = {"priority", "risk_score", "confidence"}
FINDING_KEYS = {"finding_id", "focus_area", "dimension", "root_cause", "evidence", "impact", "correction", "status"}
REVIEWER_RETURN_KEYS = {
    "role",
    "charter_id",
    "candidate_id",
    "assignment_id",
    "territory_id",
    "territory",
    "findings",
    "no_finding_evidence",
    "residual_uncertainty",
}
VERIFIER_RETURN_KEYS = REVIEWER_RETURN_KEYS | {
    "clearance_checks", "shipping_clearance",
}
CLEARANCE_CHECK_KEYS = {
    "critical_coverage_complete",
    "critical_probe_blind_review_complete",
    "revision_matches",
    "partial_rollout",
    "blockers",
}
VERIFIER_FINDING_STATUSES = {
    "verified", "open", "duplicate", "false-positive",
    "insufficient-evidence", "accepted-risk",
}
VERIFIER_RESOLVED_STATUSES = {
    "verified", "duplicate", "false-positive", "accepted-risk",
}
MAX_REVIEWER_FINDINGS = 6
MAX_REVIEWER_BYTES = 16 * 1024
COVERAGE_STATE_KEYS = {
    "candidate_id",
    "current_candidate_id",
    "required_territories",
    "completed_territories",
    "failed_territories",
    "partial_territories",
    "required_probe_blind_territories",
    "completed_probe_blind_territories",
}


def _finding_id_list(value: Any, where: str) -> list[str]:
    ids = [
        _text(item, f"{where}[{i}]")
        for i, item in enumerate(_list(value, where))
    ]
    for finding_id in ids:
        if not re.fullmatch(FINDING_ID_PATTERN, finding_id):
            raise ContractError(f"{where}: invalid finding id {finding_id!r}")
    if len(ids) != len(set(ids)):
        raise ContractError(f"{where}: duplicate finding id")
    return ids


def _stable_id(value: Any, where: str) -> str:
    identifier = _text(value, where)
    if not re.fullmatch(FINDING_ID_PATTERN, identifier):
        raise ContractError(f"{where}: expected lowercase hyphenated id")
    return identifier


def _stable_id_list(value: Any, where: str) -> list[str]:
    identifiers = [
        _stable_id(item, f"{where}[{index}]")
        for index, item in enumerate(_list(value, where))
    ]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError(f"{where}: duplicate id")
    return identifiers


def validate_coverage_state(
    value: Any,
    *,
    expected_candidate_id: str,
    where: str = "coverage_state",
) -> dict:
    """Validate parent-observed coverage used by the fail-closed verifier gate."""
    item = _object(value, where)
    _closed(item, COVERAGE_STATE_KEYS, where)
    candidate_id = _text(item["candidate_id"], f"{where}.candidate_id")
    current_candidate_id = _text(
        item["current_candidate_id"], f"{where}.current_candidate_id"
    )
    if candidate_id != expected_candidate_id:
        raise ContractError(
            f"{where}.candidate_id: expected {expected_candidate_id!r}, "
            f"got {candidate_id!r}"
        )
    fields = {
        key: _stable_id_list(item[key], f"{where}.{key}")
        for key in (
            "required_territories",
            "completed_territories",
            "failed_territories",
            "partial_territories",
            "required_probe_blind_territories",
            "completed_probe_blind_territories",
        )
    }
    return {
        "candidate_id": candidate_id,
        "current_candidate_id": current_candidate_id,
        **fields,
    }


def _validate_evidence(value: Any, where: str) -> dict:
    item = _object(value, where)
    _closed(item, EVIDENCE_KEYS, where)
    lineage = _text(item["lineage"], f"{where}.lineage")
    if lineage not in EVIDENCE_LINEAGES:
        raise ContractError(f"{where}.lineage: unsupported lineage {lineage!r}")
    return {"ref": _text(item["ref"], f"{where}.ref"), "lineage": lineage}


def validate_finding(
    value: Any, where: str = "finding", *, role: str = "review"
) -> dict:
    """Validate and normalize one lean finding object (§4.4)."""
    if role not in {"review", "verify"}:
        raise ContractError(f"{where}.role: expected 'review' or 'verify'")
    item = _object(value, where)
    _closed(item, FINDING_KEYS, where)
    finding_id = _text(item["finding_id"], f"{where}.finding_id")
    if not re.fullmatch(FINDING_ID_PATTERN, finding_id):
        raise ContractError(f"{where}.finding_id: expected lowercase hyphenated id")
    dimension = _text(item["dimension"], f"{where}.dimension")
    if dimension not in DIMENSION_NAMES:
        raise ContractError(f"{where}.dimension: unknown dimension {dimension!r}")
    evidence = [_validate_evidence(e, f"{where}.evidence[{i}]")
                for i, e in enumerate(_list(item["evidence"], f"{where}.evidence"))]
    if not evidence:
        raise ContractError(f"{where}.evidence: at least one entry required")
    impact = _object(item["impact"], f"{where}.impact")
    _closed(impact, IMPACT_KEYS, f"{where}.impact")
    risk = _int(impact["risk_score"], f"{where}.impact.risk_score", 1, 100)
    confidence = _int(impact["confidence"], f"{where}.impact.confidence", 1, 100)
    priority = _text(impact["priority"], f"{where}.impact.priority")
    if priority not in PRIORITIES:
        raise ContractError(f"{where}.impact.priority: expected one of {PRIORITIES}")
    if priority != priority_for(risk):
        raise ContractError(f"{where}.impact.priority: expected {priority_for(risk)} for risk {risk}")
    status = _text(item["status"], f"{where}.status")
    if status not in FINDING_STATUSES:
        raise ContractError(f"{where}.status: unsupported status {status!r}")
    if role == "review" and status == "accepted-risk":
        raise ContractError(f"{where}: reviewers cannot accept risk")
    lineages = {e["lineage"] for e in evidence}
    if (lineages & CONFIRMED_LINEAGES) and confidence < 70:
        raise ContractError(f"{where}: a confirmed-lineage finding requires confidence >= 70")
    verified_lineages = (
        {"source-confirmed", "parent-test-confirmed"}
        if role == "verify"
        else {"parent-test-confirmed"}
    )
    if status == "verified" and (
        not (lineages & verified_lineages) or confidence < 70
    ):
        evidence_rule = (
            "independent source-confirmed or parent-test-confirmed"
            if role == "verify"
            else "parent-test-confirmed"
        )
        raise ContractError(
            f"{where}: verified status requires {evidence_rule} evidence "
            "and confidence >= 70"
        )
    if role == "verify" and status in {"duplicate", "false-positive"} and (
        not (lineages & CONFIRMED_LINEAGES) or confidence < 70
    ):
        raise ContractError(
            f"{where}: verifier {status} status requires confirmed evidence "
            "and confidence >= 70"
        )
    return {
        "finding_id": finding_id,
        "focus_area": _text(item["focus_area"], f"{where}.focus_area"),
        "dimension": dimension,
        "root_cause": _text(item["root_cause"], f"{where}.root_cause"),
        "evidence": evidence,
        "impact": {"priority": priority, "risk_score": risk, "confidence": confidence},
        "correction": _text(item["correction"], f"{where}.correction"),
        "status": status,
    }


def validate_reviewer_return(
    value: Any,
    where: str = "reviewer_return",
    *,
    expected_candidate_id: str | None = None,
    expected_assignment_id: str | None = None,
    expected_candidate_ids: Sequence[str] | None = None,
    authorized_accepted_risk_ids: Sequence[str] | None = None,
    coverage_state: Mapping[str, Any] | None = None,
) -> dict:
    """Validate a full conformed reviewer/verifier return (§4.4 caps: <=6 findings, <=16 KiB)."""
    size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if size > MAX_REVIEWER_BYTES:
        raise ContractError(f"{where}: exceeds {MAX_REVIEWER_BYTES} bytes ({size})")
    item = _object(value, where)
    role = _text(item.get("role"), f"{where}.role")
    if role not in {"review", "verify"}:
        raise ContractError(f"{where}.role: expected 'review' or 'verify'")
    _closed(item, VERIFIER_RETURN_KEYS if role == "verify" else REVIEWER_RETURN_KEYS, where)
    if expected_candidate_id is None:
        raise ContractError(f"{where}: parent must supply expected_candidate_id")
    if not re.fullmatch(CANDIDATE_ID_PATTERN, expected_candidate_id):
        raise ContractError(
            "expected_candidate_id: expected sha256:<64 lowercase hex>"
        )
    if expected_assignment_id is None:
        raise ContractError(f"{where}: parent must supply expected_assignment_id")
    expected_assignment_id = _stable_id(
        expected_assignment_id, "expected_assignment_id"
    )
    candidate_id = _text(item["candidate_id"], f"{where}.candidate_id")
    assignment_id = _stable_id(
        item["assignment_id"], f"{where}.assignment_id"
    )
    if candidate_id != expected_candidate_id:
        raise ContractError(
            f"{where}.candidate_id: expected {expected_candidate_id!r}, "
            f"got {candidate_id!r}"
        )
    if assignment_id != expected_assignment_id:
        raise ContractError(
            f"{where}.assignment_id: expected {expected_assignment_id!r}, "
            f"got {assignment_id!r}"
        )
    findings_in = _list(item["findings"], f"{where}.findings")
    if len(findings_in) > MAX_REVIEWER_FINDINGS:
        raise ContractError(f"{where}.findings: at most {MAX_REVIEWER_FINDINGS} findings")
    findings = [
        validate_finding(f, f"{where}.findings[{i}]", role=role)
        for i, f in enumerate(findings_in)
    ]
    accepted_risk = [
        finding for finding in findings if finding["status"] == "accepted-risk"
    ]
    if role == "review" and (
        expected_candidate_ids is not None
        or authorized_accepted_risk_ids is not None
        or coverage_state is not None
    ):
        raise ContractError(
            f"{where}: verifier scope/authority/coverage arguments require role 'verify'"
        )
    result = {
        "role": role,
        "charter_id": _text(item["charter_id"], f"{where}.charter_id"),
        "candidate_id": candidate_id,
        "assignment_id": assignment_id,
        "territory_id": _stable_id(
            item["territory_id"], f"{where}.territory_id"
        ),
        "territory": _text(item["territory"], f"{where}.territory"),
        "findings": findings,
        "no_finding_evidence": _text_list(item["no_finding_evidence"], f"{where}.no_finding_evidence"),
        "residual_uncertainty": _text_list(item["residual_uncertainty"], f"{where}.residual_uncertainty"),
    }
    if role == "verify":
        if expected_candidate_ids is None:
            raise ContractError(
                f"{where}: parent must supply expected_candidate_ids"
            )
        if authorized_accepted_risk_ids is None:
            raise ContractError(
                f"{where}: parent must supply authorized_accepted_risk_ids"
            )
        if coverage_state is None:
            raise ContractError(
                f"{where}: parent must supply coverage_state"
            )
        observed_coverage = validate_coverage_state(
            coverage_state,
            expected_candidate_id=expected_candidate_id,
        )
        candidate_ids = _finding_id_list(
            list(expected_candidate_ids), "expected_candidate_ids"
        )
        authorized_ids = _finding_id_list(
            list(authorized_accepted_risk_ids),
            "authorized_accepted_risk_ids",
        )
        unauthorized_scope = sorted(set(authorized_ids) - set(candidate_ids))
        if unauthorized_scope:
            raise ContractError(
                "authorized_accepted_risk_ids: outside expected candidate scope "
                f"{unauthorized_scope}"
            )
        finding_ids = [finding["finding_id"] for finding in findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ContractError(f"{where}.findings: duplicate adjudication finding_id")
        missing = sorted(set(candidate_ids) - set(finding_ids))
        extra = sorted(set(finding_ids) - set(candidate_ids))
        if missing or extra:
            raise ContractError(
                f"{where}.findings: adjudication scope mismatch "
                f"(missing={missing}, extra={extra})"
            )
        invalid_statuses = [
            finding["finding_id"]
            for finding in findings
            if finding["status"] not in VERIFIER_FINDING_STATUSES
        ]
        if invalid_statuses:
            raise ContractError(
                f"{where}.findings: verifier status unsupported for "
                f"{invalid_statuses}"
            )
        for finding in accepted_risk:
            lineages = {entry["lineage"] for entry in finding["evidence"]}
            if finding["finding_id"] not in authorized_ids:
                raise ContractError(
                    f"{where}.findings: accepted-risk is not authorized for "
                    f"{finding['finding_id']!r}"
                )
            if (
                not (lineages & CONFIRMED_LINEAGES)
                or finding["impact"]["confidence"] < 70
            ):
                raise ContractError(
                    f"{where}.findings: accepted-risk requires confirmed evidence "
                    f"and confidence >= 70 for {finding['finding_id']!r}"
                )
        checks = _object(item["clearance_checks"], f"{where}.clearance_checks")
        _closed(checks, CLEARANCE_CHECK_KEYS, f"{where}.clearance_checks")
        normalized_checks = {
            "critical_coverage_complete": _bool(
                checks["critical_coverage_complete"],
                f"{where}.clearance_checks.critical_coverage_complete",
            ),
            "critical_probe_blind_review_complete": _bool(
                checks["critical_probe_blind_review_complete"],
                f"{where}.clearance_checks.critical_probe_blind_review_complete",
            ),
            "revision_matches": _bool(
                checks["revision_matches"],
                f"{where}.clearance_checks.revision_matches",
            ),
            "partial_rollout": _bool(
                checks["partial_rollout"],
                f"{where}.clearance_checks.partial_rollout",
            ),
            "blockers": _text_list(
                checks["blockers"],
                f"{where}.clearance_checks.blockers",
            ),
        }
        clearance = _text(item["shipping_clearance"], f"{where}.shipping_clearance")
        if clearance not in {"approved", "failed"}:
            raise ContractError(
                f"{where}.shipping_clearance: expected 'approved' or 'failed'"
            )
        unresolved = [
            finding["finding_id"]
            for finding in findings
            if finding["status"] not in VERIFIER_RESOLVED_STATUSES
        ]
        failed_checks = [
            name
            for name in (
                "critical_coverage_complete",
                "critical_probe_blind_review_complete",
                "revision_matches",
            )
            if not normalized_checks[name]
        ]
        if normalized_checks["partial_rollout"]:
            failed_checks.append("partial_rollout")
        required = set(observed_coverage["required_territories"])
        completed = set(observed_coverage["completed_territories"])
        required_blind = set(
            observed_coverage["required_probe_blind_territories"]
        )
        completed_blind = set(
            observed_coverage["completed_probe_blind_territories"]
        )
        parent_coverage_failures = {
            "candidate_mismatch": (
                observed_coverage["current_candidate_id"]
                != observed_coverage["candidate_id"]
            ),
            "uncovered": sorted(required - completed),
            "failed": observed_coverage["failed_territories"],
            "partial": observed_coverage["partial_territories"],
            "probe_blind_uncovered": sorted(required_blind - completed_blind),
        }
        if parent_coverage_failures["candidate_mismatch"]:
            failed_checks.append("parent_candidate_identity")
        if parent_coverage_failures["uncovered"]:
            failed_checks.append("parent_critical_coverage")
        if parent_coverage_failures["failed"]:
            failed_checks.append("parent_failed_workers")
        if parent_coverage_failures["partial"]:
            failed_checks.append("parent_partial_outputs")
        if parent_coverage_failures["probe_blind_uncovered"]:
            failed_checks.append("parent_probe_blind_coverage")
        if clearance == "approved" and (
            unresolved
            or failed_checks
            or normalized_checks["blockers"]
        ):
            raise ContractError(
                f"{where}.shipping_clearance: approved with blockers "
                f"(unresolved={unresolved}, "
                f"failed_checks={failed_checks}, "
                f"blockers={normalized_checks['blockers']}, "
                f"parent_coverage={parent_coverage_failures})"
            )
        result["clearance_checks"] = normalized_checks
        result["parent_coverage"] = observed_coverage
        result["shipping_clearance"] = clearance
    return result


# --- Bands, cohort sizing (§4.2), and budgets (§5): one source of truth ---

BANDS = ("trivial", "small", "standard", "deep", "critical")
BAND_DISPLAY = {b: b.capitalize() for b in BANDS}
BASE_MAX_REVIEWERS = 5

BAND_SPEC = {
    "trivial":  {"reviewers": (1, 1), "max_dispatches": 2, "concurrency": 1, "wall_clock_min": 3,
                 "verifier": "no",    "second_pass": "no",    "coverage": "the one impacted surface"},
    "small":    {"reviewers": (1, 2), "max_dispatches": 3, "concurrency": 2, "wall_clock_min": 6,
                 "verifier": "no",    "second_pass": "no",    "coverage": "targeted inspection of hotspots"},
    "standard": {"reviewers": (2, 3), "max_dispatches": 4, "concurrency": 2, "wall_clock_min": 10,
                 "verifier": "gated", "second_pass": "no",    "coverage": "specialist on the driving axis"},
    "deep":     {"reviewers": (3, 4), "max_dispatches": 6, "concurrency": 3, "wall_clock_min": 15,
                 "verifier": "gated", "second_pass": "gated", "coverage": "specialist + strong, explicit evidence paths"},
    "critical": {"reviewers": (4, 5), "max_dispatches": 8, "concurrency": 3, "wall_clock_min": 20,
                 "verifier": "yes",   "second_pass": "gated", "coverage": "redundancy only on the >=90 axis; specialist elsewhere"},
}

# Absolute ceilings across all bands (§5).
ABSOLUTE_MAX_DISPATCHES = 9
START_NEW_WORK_CUTOFF_SECONDS = 20 * 60
NO_NEW_DISPATCH_SECONDS = START_NEW_WORK_CUTOFF_SECONDS
MIN_COMPLETION_ALLOWANCE_SECONDS = 25 * 60
MAX_COMPLETION_ALLOWANCE_SECONDS = 60 * 60
STALL_INSPECTION_SECONDS = 5 * 60
MAX_PASSES = 2
MAX_ROUTING_FALLBACK_ATTEMPTS = 1
MAX_TRANSPORT_FALLBACK_ATTEMPTS = 1
MAX_CHARTER_RETRIES_PER_ASSIGNMENT = 1


def _score_map(probe: Mapping[str, Any]) -> dict:
    scores = _object(probe.get("scores", {}), "probe.scores")
    out = {}
    for dim in DIMENSIONS:
        if dim not in scores:
            raise ContractError(f"probe.scores: missing {dim}")
        entry = scores[dim]
        raw = entry.get("score") if isinstance(entry, dict) else entry
        out[dim] = _int(raw, f"probe.scores.{dim}.score", 0, 100)
    return out


def _protected_axes(probe: Mapping[str, Any]) -> dict:
    declared = probe.get("protected_axes")
    if isinstance(declared, dict):
        return {k: bool(declared.get(k, False)) for k in PROTECTED_AXES}
    return {k: False for k in PROTECTED_AXES}


def _territory_focus_count(probe: Mapping[str, Any]) -> tuple:
    territories = probe.get("territories") or []
    _list(territories, "probe.territories")
    focus = set()
    for i, t in enumerate(territories):
        t = _object(t, f"probe.territories[{i}]")
        focus.add(str(t.get("focus_area") or t.get("id") or f"t{i}"))
    return len(territories), len(focus)


def select_band(probe: Mapping[str, Any]) -> dict:
    """First-match Critical -> Trivial band selection from probe intelligence (§4.2)."""
    probe = _object(probe, "probe")
    d = _score_map(probe)
    surface = _object(probe.get("surface", {}), "probe.surface")
    roots = _int(surface.get("roots", 1), "probe.surface.roots", 1, 100_000)
    files = _int(surface.get("files_changed", 0), "probe.surface.files_changed", 0, 100_000_000)
    lines = _int(surface.get("lines_changed", 0), "probe.surface.lines_changed", 0, 1_000_000_000)
    impacted = surface.get("impacted_surfaces") or []
    n_impacted = len(impacted) if isinstance(impacted, list) else 0
    n_territories, n_focus = _territory_focus_count(probe)
    fix_character = probe.get("fix_character", "mixed")
    protected = _protected_axes(probe)
    max_score = max(d.values())
    multi_repo = roots > 1
    migration = d["D03"] >= 60
    # The strict trivial fast path; Small excludes it so Trivial stays reachable
    # as the last-checked, cheapest band (§4.2 first-match, Trivial fallback).
    is_trivial = (
        roots == 1 and files <= 5 and lines <= 100 and max_score < 40
        and fix_character == "cosmetic" and not any(protected.values())
    )

    if (max_score >= 90
            or d["D04"] >= 80 or d["D05"] >= 80 or d["D07"] >= 80
            or (multi_repo and migration and max_score >= 80)):
        band = "critical"
        reason = "dimension >=90, protected axis D04/D05/D07 >=80, or multi-repo migration with score >=80"
    elif (80 <= max_score <= 89
            or 60 <= d["D04"] <= 79 or 60 <= d["D05"] <= 79 or 60 <= d["D07"] <= 79
            or (multi_repo and not migration and max_score >= 60)):
        band = "deep"
        reason = "max score 80-89, protected axis D04/D05/D07 in 60-79, or multi-repo (no migration) with max >=60"
    elif 60 <= max_score <= 79 or 3 <= n_impacted <= 5 or n_focus >= 2:
        band = "standard"
        reason = "max score 60-79, 3-5 impacted surfaces, or >=2 distinct focus areas"
    elif 40 <= max_score <= 59 or (roots == 1 and files <= 15 and n_focus <= 2 and not is_trivial):
        band = "small"
        reason = "max score 40-59, or single root with <=15 files and <=2 focus areas"
    elif is_trivial:
        band = "trivial"
        reason = "single root, <=5 files/<=100 lines, max score <40, cosmetic, no protected-axis hotspot"
    else:
        band = "small"
        reason = "low-risk single-root change below all higher-band thresholds"

    return {
        "band": band,
        "reason": reason,
        "max_score": max_score,
        "signals": {
            "roots": roots, "files_changed": files, "lines_changed": lines,
            "impacted_surfaces": n_impacted, "territories": n_territories, "focus_areas": n_focus,
            "migration": migration, "fix_character": fix_character,
            "protected_axis_max_D04_D05_D07": max(d["D04"], d["D05"], d["D07"]),
            "protected_axes": protected,
        },
    }


def size_cohort(probe: Mapping[str, Any]) -> dict:
    """Probe JSON -> band + concrete cohort plan (§4.2 + §5). Floor 1, base max 5."""
    selection = select_band(probe)
    band = selection["band"]
    spec = BAND_SPEC[band]
    low, high = spec["reviewers"]
    high = min(high, BASE_MAX_REVIEWERS)
    n_territories = selection["signals"]["territories"]
    reviewers = max(1, min(high, max(low, n_territories or low)))  # floor 1, capped to band
    plan = {
        "band": band,
        "band_display": BAND_DISPLAY[band],
        "reviewers": reviewers,
        "reviewer_range": [low, high],
        "verifier": spec["verifier"],
        "second_pass": spec["second_pass"],
        "coverage": spec["coverage"],
        "max_dispatches": spec["max_dispatches"],
        "concurrency": spec["concurrency"],
        "target_wall_clock_min": spec["wall_clock_min"],
        "absolute_max_dispatches": ABSOLUTE_MAX_DISPATCHES,
        "reason": selection["reason"],
        "signals": selection["signals"],
    }
    recommended = probe.get("recommended_band")
    if isinstance(recommended, str) and recommended.strip():
        rec = recommended.strip().lower()
        plan["probe_recommended_band"] = rec
        plan["matches_probe_recommendation"] = rec == band
    return plan


# --- Accepted-worker budget and attempt accounting (§5) ---

DISPATCH_KINDS = {"probe", "reviewer", "verifier", "escalation"}
_BASE_KINDS = {"probe", "reviewer", "verifier"}
COMPLETION_OUTCOMES = {
    "valid",
    "malformed",
    "partial",
    "stalled",
    "errored",
    "cancelled",
    "timed-out",
}


def execution_window(
    *,
    band: str,
    lines_changed: int,
    territory_count: int,
    depth: str,
) -> dict:
    """Separate the fixed start cutoff from a scope-aware completion allowance."""
    if band not in BAND_SPEC:
        raise ContractError(f"band: expected one of {BANDS}")
    _int(lines_changed, "lines_changed", 0, 1_000_000_000)
    _int(territory_count, "territory_count", 0, 100_000)
    if depth not in {"shallow", "deep"}:
        raise ContractError("depth: expected 'shallow' or 'deep'")
    extra_minutes = (
        math.ceil(max(0, lines_changed - 1000) / 2500) * 4
        + min(10, max(0, territory_count - 2) * 2)
        + (5 if depth == "deep" else 0)
    )
    completion_seconds = min(
        MAX_COMPLETION_ALLOWANCE_SECONDS,
        MIN_COMPLETION_ALLOWANCE_SECONDS + extra_minutes * 60,
    )
    return {
        "target_wall_clock_seconds": BAND_SPEC[band]["wall_clock_min"] * 60,
        "start_new_work_cutoff_seconds": START_NEW_WORK_CUTOFF_SECONDS,
        "healthy_completion_allowance_seconds": completion_seconds,
        "stall_inspection_seconds": STALL_INSPECTION_SECONDS,
    }


class BudgetCounter:
    """Running accepted-worker counter enforcing band and absolute ceilings.

    `batch` is a concurrency-wave index; accepted workers sharing a batch run at
    once. Preflight/model and rejected-before-worker transport attempts are
    accounted separately by `RunAccounting` and never consume this capacity.
    """

    def __init__(self, band: str):
        if band not in BAND_SPEC:
            raise ContractError(f"band: expected one of {BANDS}")
        self.band = band
        self.spec = BAND_SPEC[band]
        self.events: list = []

    def _validated(self, events: Sequence[Mapping[str, Any]]) -> None:
        if len(events) > ABSOLUTE_MAX_DISPATCHES:
            raise ContractError(
                f"dispatch: accepted workers exceed the absolute ceiling of "
                f"{ABSOLUTE_MAX_DISPATCHES}"
            )
        base = sum(event["kind"] in _BASE_KINDS for event in events)
        if base > self.spec["max_dispatches"]:
            raise ContractError(
                f"dispatch: {self.band} accepted base cohort exceeds its ceiling "
                f"of {self.spec['max_dispatches']}"
            )
        if sum(event["kind"] == "probe" for event in events) > 1:
            raise ContractError("dispatch: more than one accepted probe")
        if sum(event["kind"] == "verifier" for event in events) > 1:
            raise ContractError("dispatch: more than one accepted verifier")
        per_batch: dict[int, int] = {}
        for event in events:
            per_batch[event["batch"]] = per_batch.get(event["batch"], 0) + 1
            if per_batch[event["batch"]] > self.spec["concurrency"]:
                raise ContractError(
                    f"dispatch: batch {event['batch']} exceeds "
                    f"{self.band} concurrency of {self.spec['concurrency']}"
                )

    def record(
        self,
        kind: str,
        *,
        batch: int = 0,
        at_seconds: int = 0,
        pass_index: int = 1,
        attempt_index: int = 0,
    ) -> dict:
        if kind not in DISPATCH_KINDS:
            raise ContractError(
                f"dispatch kind: unsupported {kind!r} "
                "(only accepted workers consume dispatch capacity)"
            )
        _int(batch, "batch", 0, 100_000)
        _int(at_seconds, "at_seconds", 0, 100_000_000)
        _int(pass_index, "pass_index", 1, 100_000)
        _int(
            attempt_index,
            "attempt_index",
            0,
            MAX_CHARTER_RETRIES_PER_ASSIGNMENT,
        )
        if pass_index > MAX_PASSES:
            raise ContractError(f"dispatch: never start a third pass (pass_index {pass_index} > {MAX_PASSES})")
        if at_seconds > START_NEW_WORK_CUTOFF_SECONDS:
            raise ContractError(
                f"dispatch: no new accepted worker after "
                f"{START_NEW_WORK_CUTOFF_SECONDS // 60} min ({at_seconds}s)"
            )
        candidate = [
            *self.events,
            {
                "kind": kind,
                "batch": batch,
                "at_seconds": at_seconds,
                "pass_index": pass_index,
                "attempt_index": attempt_index,
            },
        ]
        self._validated(candidate)
        self.events = candidate
        return self.snapshot()

    def snapshot(self) -> dict:
        base = sum(e["kind"] in _BASE_KINDS for e in self.events)
        return {
            "band": self.band,
            "dispatches": len(self.events),
            "base_dispatches": base,
            "max_dispatches": self.spec["max_dispatches"],
            "absolute_max_dispatches": ABSOLUTE_MAX_DISPATCHES,
            "remaining_band": max(0, self.spec["max_dispatches"] - base),
            "remaining_absolute": max(0, ABSOLUTE_MAX_DISPATCHES - len(self.events)),
            "concurrency": self.spec["concurrency"],
            "passes": max((e["pass_index"] for e in self.events), default=0),
            "max_passes": MAX_PASSES,
            "start_new_work_cutoff_seconds": START_NEW_WORK_CUTOFF_SECONDS,
        }


def evaluate_budget(band: str, events: Sequence[Mapping[str, Any]]) -> dict:
    """Validate a full dispatch plan against §5 ceilings; raise on violation, else return the snapshot."""
    counter = BudgetCounter(band)
    for i, ev in enumerate(_list(list(events), "events")):
        ev = _object(ev, f"events[{i}]")
        counter.record(
            _text(ev.get("kind"), f"events[{i}].kind"),
            batch=ev.get("batch", 0),
            at_seconds=ev.get("at_seconds", 0),
            pass_index=ev.get("pass_index", 1),
            attempt_index=ev.get("attempt_index", 0),
        )
    return counter.snapshot()


class RunAccounting:
    """Distinguish resolution/transport attempts from accepted worker coverage."""

    def __init__(self, band: str, window: Mapping[str, Any]):
        self.counter = BudgetCounter(band)
        self.window = dict(window)
        self.routing_rejections: dict[str, list[dict]] = {}
        self.transport_rejections: dict[str, list[dict]] = {}
        self.workers: dict[str, dict] = {}

    def _rejection(
        self,
        store: dict[str, list[dict]],
        *,
        assignment_id: str,
        model_slug: str,
        reason: str,
        limit: int,
        failure_class: str,
    ) -> dict:
        assignment_id = _stable_id(assignment_id, "assignment_id")
        model_slug = _text(model_slug, "model_slug")
        reason = _text(reason, "reason")
        attempts = [
            *store.get(assignment_id, []),
            {"model_slug": model_slug, "reason": reason},
        ]
        if len(attempts) > limit:
            raise ContractError(
                f"{failure_class}: assignment {assignment_id!r} exceeds "
                f"the bounded fallback-attempt limit of {limit}"
            )
        store[assignment_id] = attempts
        return self.snapshot()

    def record_preflight_rejection(
        self, assignment_id: str, model_slug: str, reason: str
    ) -> dict:
        return self._rejection(
            self.routing_rejections,
            assignment_id=assignment_id,
            model_slug=model_slug,
            reason=reason,
            limit=MAX_ROUTING_FALLBACK_ATTEMPTS,
            failure_class="preflight model resolution",
        )

    def record_transport_rejection(
        self, assignment_id: str, model_slug: str, reason: str
    ) -> dict:
        return self._rejection(
            self.transport_rejections,
            assignment_id=assignment_id,
            model_slug=model_slug,
            reason=reason,
            limit=MAX_TRANSPORT_FALLBACK_ATTEMPTS,
            failure_class="rejected-before-worker transport",
        )

    def accept_worker(
        self,
        *,
        worker_id: str,
        kind: str,
        assignment_id: str,
        territory_id: str,
        model_slug: str,
        blind_to_probe: bool = False,
        batch: int = 0,
        at_seconds: int = 0,
        pass_index: int = 1,
        attempt_index: int = 0,
    ) -> dict:
        worker_id = _stable_id(worker_id, "worker_id")
        assignment_id = _stable_id(assignment_id, "assignment_id")
        territory_id = _stable_id(territory_id, "territory_id")
        model_slug = _text(model_slug, "model_slug")
        if model_slug == "inherit":
            raise ContractError("model_slug: inherit is never a concrete launch model")
        worker = {
            "worker_id": worker_id,
            "kind": kind,
            "assignment_id": assignment_id,
            "territory_id": territory_id,
            "model_slug": model_slug,
            "blind_to_probe": _bool(blind_to_probe, "blind_to_probe"),
            "batch": batch,
            "at_seconds": at_seconds,
            "pass_index": pass_index,
            "attempt_index": attempt_index,
            "outcome": None,
            "completed_at_seconds": None,
        }
        existing = self.workers.get(worker_id)
        if existing is not None:
            immutable_keys = set(worker) - {"outcome", "completed_at_seconds"}
            if all(existing[key] == worker[key] for key in immutable_keys):
                return self.snapshot()
            raise ContractError(
                f"worker_id {worker_id!r}: conflicting duplicate acceptance"
            )
        _int(
            attempt_index,
            "attempt_index",
            0,
            MAX_CHARTER_RETRIES_PER_ASSIGNMENT,
        )
        accepted_attempts = [
            accepted["attempt_index"]
            for accepted in self.workers.values()
            if accepted["assignment_id"] == assignment_id
        ]
        expected_attempt = len(accepted_attempts)
        if (
            expected_attempt > MAX_CHARTER_RETRIES_PER_ASSIGNMENT
            or attempt_index != expected_attempt
        ):
            raise ContractError(
                f"accepted worker retry: assignment {assignment_id!r} "
                f"expected attempt_index {expected_attempt} after "
                f"{accepted_attempts!r}, got {attempt_index}; base launch plus "
                f"at most {MAX_CHARTER_RETRIES_PER_ASSIGNMENT} retry allowed"
            )
        self.counter.record(
            kind,
            batch=batch,
            at_seconds=at_seconds,
            pass_index=pass_index,
            attempt_index=attempt_index,
        )
        self.workers[worker_id] = worker
        return self.snapshot()

    def complete_worker(
        self, worker_id: str, *, outcome: str, completed_at_seconds: int
    ) -> dict:
        worker_id = _stable_id(worker_id, "worker_id")
        if worker_id not in self.workers:
            raise ContractError(
                f"worker completion without accepted worker: {worker_id!r}"
            )
        if outcome not in COMPLETION_OUTCOMES:
            raise ContractError(
                f"outcome: expected one of {sorted(COMPLETION_OUTCOMES)}"
            )
        _int(
            completed_at_seconds,
            "completed_at_seconds",
            0,
            100_000_000,
        )
        worker = self.workers[worker_id]
        existing = worker["outcome"]
        if existing is not None:
            if (
                existing == outcome
                and worker["completed_at_seconds"] == completed_at_seconds
            ):
                return self.snapshot()
            raise ContractError(
                f"worker_id {worker_id!r}: conflicting duplicate completion"
            )
        allowance = _int(
            self.window.get("healthy_completion_allowance_seconds"),
            "window.healthy_completion_allowance_seconds",
            MIN_COMPLETION_ALLOWANCE_SECONDS,
            MAX_COMPLETION_ALLOWANCE_SECONDS,
        )
        if outcome == "valid" and completed_at_seconds > allowance:
            outcome = "timed-out"
        worker["outcome"] = outcome
        worker["completed_at_seconds"] = completed_at_seconds
        return self.snapshot()

    def snapshot(self) -> dict:
        valid = [
            worker for worker in self.workers.values()
            if worker["outcome"] == "valid"
        ]
        failed = [
            worker for worker in self.workers.values()
            if worker["outcome"] not in {None, "valid"}
        ]
        pending = [
            worker for worker in self.workers.values()
            if worker["outcome"] is None
        ]
        return {
            "budget": self.counter.snapshot(),
            "accepted_workers": len(self.workers),
            "routing_rejections": {
                key: list(value)
                for key, value in sorted(self.routing_rejections.items())
            },
            "transport_rejections": {
                key: list(value)
                for key, value in sorted(self.transport_rejections.items())
            },
            "completed_assignment_ids": sorted(
                {worker["assignment_id"] for worker in valid}
            ),
            "completed_probe_blind_assignment_ids": sorted(
                {
                    worker["assignment_id"]
                    for worker in valid
                    if worker["blind_to_probe"]
                }
            ),
            "failed_workers": [
                {
                    key: worker[key]
                    for key in (
                        "worker_id",
                        "assignment_id",
                        "territory_id",
                        "outcome",
                    )
                }
                for worker in failed
            ],
            "pending_workers": [worker["worker_id"] for worker in pending],
        }


def coverage_state_from(
    plan: Mapping[str, Any],
    accounting: Mapping[str, Any],
    *,
    current_candidate_id: str,
) -> dict:
    """Project parent-observed worker outcomes into verifier coverage input."""
    candidate = validate_candidate_identity(
        _object(plan, "plan").get("candidate"), "plan.candidate"
    )
    coverage = _object(plan.get("coverage"), "plan.coverage")
    required = _stable_id_list(
        coverage.get("required_assignment_ids"),
        "plan.coverage.required_assignment_ids",
    )
    required_blind = _stable_id_list(
        coverage.get("required_probe_blind_assignment_ids"),
        "plan.coverage.required_probe_blind_assignment_ids",
    )
    observed = _object(accounting, "accounting")
    completed = _stable_id_list(
        observed.get("completed_assignment_ids") or [],
        "accounting.completed_assignment_ids",
    )
    completed_blind = _stable_id_list(
        observed.get("completed_probe_blind_assignment_ids") or [],
        "accounting.completed_probe_blind_assignment_ids",
    )
    failed_workers = _list(
        observed.get("failed_workers") or [], "accounting.failed_workers"
    )
    failed: set[str] = set()
    partial: set[str] = set()
    for index, raw in enumerate(failed_workers):
        worker = _object(raw, f"accounting.failed_workers[{index}]")
        assignment_id = _stable_id(
            worker.get("assignment_id"),
            f"accounting.failed_workers[{index}].assignment_id",
        )
        if worker.get("outcome") == "partial":
            partial.add(assignment_id)
        else:
            failed.add(assignment_id)
    return validate_coverage_state(
        {
            "candidate_id": candidate["candidate_id"],
            "current_candidate_id": current_candidate_id,
            "required_territories": required,
            "completed_territories": completed,
            "failed_territories": sorted(failed),
            "partial_territories": sorted(partial),
            "required_probe_blind_territories": required_blind,
            "completed_probe_blind_territories": completed_blind,
        },
        expected_candidate_id=candidate["candidate_id"],
    )


def evaluate_accounting(
    band: str,
    window: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> dict:
    """Replay a deterministic worker-attempt lifecycle for tests and CLI use."""
    accounting = RunAccounting(band, window)
    for index, raw in enumerate(_list(list(events), "events")):
        event = _object(raw, f"events[{index}]")
        event_type = _text(event.get("type"), f"events[{index}].type")
        if event_type == "preflight-rejected":
            accounting.record_preflight_rejection(
                event.get("assignment_id"),
                event.get("model_slug"),
                event.get("reason"),
            )
        elif event_type == "transport-rejected":
            accounting.record_transport_rejection(
                event.get("assignment_id"),
                event.get("model_slug"),
                event.get("reason"),
            )
        elif event_type == "accepted":
            accounting.accept_worker(
                worker_id=event.get("worker_id"),
                kind=event.get("kind"),
                assignment_id=event.get("assignment_id"),
                territory_id=event.get("territory_id"),
                model_slug=event.get("model_slug"),
                blind_to_probe=event.get("blind_to_probe", False),
                batch=event.get("batch", 0),
                at_seconds=event.get("at_seconds", 0),
                pass_index=event.get("pass_index", 1),
                attempt_index=event.get("attempt_index", 0),
            )
        elif event_type == "completed":
            accounting.complete_worker(
                event.get("worker_id"),
                outcome=event.get("outcome"),
                completed_at_seconds=event.get("completed_at_seconds"),
            )
        else:
            raise ContractError(
                f"events[{index}].type: unsupported {event_type!r}"
            )
    return accounting.snapshot()


# --- Model + rigor routing (§4.3): one shared catalog, no inheritance ---

MODEL_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "subagent-orchestration"
    / "model-tiers.json"
)
# Review-rigor obligation stated in each charter. Cursor fixes a model's runtime
# effort by its picker level, so rigor is swarm policy per tier, not catalog data.
TIER_RIGOR = {
    "economy": "light",
    "standard": "standard",
    "deep": "deep",
    "critical": "max",
}


def _catalog_paths() -> tuple[Path, Path]:
    """Return source/quiver and installed-rule catalog candidates in precedence order."""
    installed_rule = Path.home() / ".cursor" / "rules" / "subagent-orchestration.mdc"
    try:
        installed_source = installed_rule.resolve(strict=True)
    except OSError:
        installed_source = installed_rule.resolve(strict=False)
    return MODEL_CATALOG_PATH, installed_source.with_name("model-tiers.json")


def _load_model_catalog(path: Path | None = None) -> tuple[dict, dict]:
    """Lazily load tier candidates from the shared rule, paired with tier rigor."""
    attempted = (path,) if path is not None else _catalog_paths()
    selected = next((candidate for candidate in attempted if candidate.is_file()), None)
    if selected is None:
        tried = "; ".join(str(candidate) for candidate in attempted)
        raise ContractError(
            "shared model-tier catalog not found; tried "
            f"{tried}. Install the subagent-orchestration rule or use the co-located rule payload."
        )
    try:
        data = json.loads(selected.read_text(encoding="utf-8"))
        tiers = data["tiers"]
        if data["schema"] != "cursor-model-tiers/v2" or not isinstance(tiers, dict):
            raise ValueError("unsupported catalog shape")
        models = {}
        for tier in TIER_RIGOR:
            candidates = tiers[tier]["candidates"]
            if not isinstance(candidates, list) or not candidates:
                raise ValueError(f"{tier}: candidates must be non-empty")
            if not all(isinstance(slug, str) and slug for slug in candidates):
                raise ValueError(f"{tier}: candidates must be non-empty strings")
            models[tier] = list(candidates)
        return models, dict(TIER_RIGOR)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError(f"shared model-tier catalog invalid at {selected}: {exc}") from exc


def _runtime_model_set(available: Iterable[str]) -> frozenset[str]:
    if isinstance(available, (str, bytes)):
        raise ContractError(
            "runtime_models: expected an iterable of concrete model slugs"
        )
    models = frozenset(available)
    if not models:
        raise ContractError("runtime_models: must not be empty")
    if any(not isinstance(slug, str) or not slug for slug in models):
        raise ContractError("runtime_models: expected non-empty strings")
    if "inherit" in models:
        raise ContractError(
            "runtime_models: 'inherit' is not a concrete launch model"
        )
    return models


def resolve_tier(model_class: str, runtime_models: Iterable[str]) -> dict:
    """Filter ordered catalog policy through the executing runtime before launch."""
    catalog, obligations = _load_model_catalog()
    if model_class not in catalog:
        raise ContractError(f"model class: unknown {model_class!r}")
    configured = list(catalog[model_class])
    supported = _runtime_model_set(runtime_models)
    candidates = [slug for slug in configured if slug in supported]
    filtered_out = [slug for slug in configured if slug not in supported]
    if not candidates:
        raise ContractError(
            "preflight model resolution: no runtime-supported configured model "
            f"for tier {model_class!r}; configured={configured!r}; "
            f"runtime_supported={sorted(supported)!r}; zero launches"
        )
    return {
        "model_class": model_class,
        "rigor": obligations[model_class],
        "slug": candidates[0],
        "fallbacks": candidates[1:],
        "candidates": candidates,
        "configured_candidates": configured,
        "filtered_out": filtered_out,
    }


def _route(
    model_class: str,
    descriptor: str,
    *,
    runtime_models: Iterable[str],
    obligation: str | None = None,
) -> dict:
    route = resolve_tier(model_class, runtime_models)
    route["route"] = descriptor
    if obligation is not None:
        route["rigor"] = obligation
    return route


def route_probe(
    *,
    roots: int,
    files_changed: int,
    lines_changed: int,
    protected_paths: bool,
    runtime_models: Iterable[str],
) -> dict:
    """Probe routing off PRE-PROBE facts only (never off probe scores — no circular routing)."""
    _int(roots, "roots", 1, 100_000)
    _int(files_changed, "files_changed", 0, 100_000_000)
    _int(lines_changed, "lines_changed", 0, 1_000_000_000)
    _bool(protected_paths, "protected_paths")
    if roots > 1 and protected_paths:
        return _route(
            "deep",
            "probe:pre-probe-heavy (multi-root + protected/security/release surface)",
            runtime_models=runtime_models,
        )
    if roots == 1 and files_changed <= 5 and lines_changed <= 100 and not protected_paths:
        return _route(
            "economy",
            "probe:pre-probe-trivial (1 root, <=5 files, <=100 lines, no protected paths)",
            runtime_models=runtime_models,
            obligation="light",
        )
    return _route("standard", "probe:default", runtime_models=runtime_models)


def route_reviewer(*, score: int, runtime_models: Iterable[str]) -> dict:
    """Reviewer routing off the driving territory/dimension score."""
    _int(score, "score", 0, 100)
    if score >= 90:
        return _route(
            "critical",
            "reviewer:critical (score >=90)",
            runtime_models=runtime_models,
        )
    if score >= 60:
        return _route(
            "deep",
            "reviewer:specialist/strong (score 60-89)",
            runtime_models=runtime_models,
        )
    if score >= 40:
        return _route(
            "standard",
            "reviewer:targeted (score 40-59)",
            runtime_models=runtime_models,
        )
    return _route(
        "economy",
        "reviewer:basic (score <40, bundled)",
        runtime_models=runtime_models,
        obligation="light",
    )


def route_verifier(*, priority: str, runtime_models: Iterable[str]) -> dict:
    """Verifier routing off the gate severity (P0/unsafe vs P1/critical)."""
    priority = _text(priority, "priority")
    if priority not in PRIORITIES:
        raise ContractError(f"priority: expected one of {PRIORITIES}")
    if priority == "P0":
        return _route(
            "critical",
            "verifier:P0/unsafe-to-ship",
            runtime_models=runtime_models,
        )
    return _route(
        "deep",
        "verifier:P1/critical shipping gate",
        runtime_models=runtime_models,
    )


def resolve_model(role: str, **facts: Any) -> dict:
    """Single resolver dispatching to the role catalog tables."""
    if role == "probe":
        return route_probe(**facts)
    if role in ("reviewer", "review"):
        return route_reviewer(**facts)
    if role in ("verifier", "verify"):
        return route_verifier(**facts)
    raise ContractError(f"role: expected probe/reviewer/verifier, got {role!r}")


def select_slug(model_class: str, available: Iterable[str]) -> str:
    """Compatibility wrapper returning the preflight-resolved concrete slug."""
    return resolve_tier(model_class, available)["slug"]


# --- JIT planning (§4.2 + §4.3): probe -> band + routed cohort + charter ids ---

# focus_area -> committed reviewer charter id (references/charters/<id>.md). The
# probe emits a focus_area per territory; this is the one-line "which charter"
# index the orchestrator would otherwise read as prose. Every value is a real
# committed charter, so a plan never surfaces a charter file that does not exist.
FOCUS_AREA_CHARTER = {
    "generic-surface": "generic-surface",
    "api-contract": "api-contract-compat",
    "data-integrity": "data-integrity-migration",
    "security": "security-authz",
    "privacy": "privacy-secrets",
    "reliability": "reliability-failure",
    "concurrency": "concurrency-ordering",
    "performance": "performance",
    "testing": "testing-evidence",
    "architecture": "architecture-maintainability",
    "policy": "policy-governance",
}
CHARTER_IDS = frozenset(FOCUS_AREA_CHARTER.values())


def charter_for(focus_area: Any) -> str:
    """Map a probe focus_area to its committed reviewer charter id.

    Accepts the short focus name ("security") or an already-resolved charter id
    ("security-authz"); an unknown focus falls back to the safe generic-surface
    charter so a plan never names a charter file that is not committed.
    """
    key = str(focus_area or "").strip()
    if key in FOCUS_AREA_CHARTER:
        return FOCUS_AREA_CHARTER[key]
    if key in CHARTER_IDS:
        return key
    return "generic-surface"


MAX_EVIDENCE_PACK_LINES = 3000
LARGE_SCOPE_LINES = 2000
SECTION_KEYS = {
    "section_id",
    "path",
    "start_line",
    "end_line",
    "flows",
}
INTEGRATION_POINT_KEYS = {
    "id",
    "territory_ids",
    "section_ids",
    "flow",
    "requires_reviewer",
}


def _generated_id(prefix: str, *parts: Any) -> str:
    raw = "-".join(str(part) for part in (prefix, *parts))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"{prefix}-{slug}".strip("-")
    if len(slug) > 110:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        slug = f"{slug[:97].rstrip('-')}-{digest}"
    return _stable_id(slug, "generated_id")


def _normalize_sections(probe: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[dict]:
    surface = _object(probe.get("surface", {}), "probe.surface")
    supplied = surface.get("sections")
    files = {entry["path"]: entry for entry in candidate["files"]}
    sections: list[dict] = []
    if supplied is None:
        for file_entry in candidate["files"]:
            start = 1
            while start <= file_entry["lines"]:
                end = min(
                    file_entry["lines"],
                    start + MAX_EVIDENCE_PACK_LINES - 1,
                )
                sections.append(
                    {
                        "section_id": _generated_id(
                            "section", file_entry["path"], start, end
                        ),
                        "path": file_entry["path"],
                        "start_line": start,
                        "end_line": end,
                        "flows": [],
                    }
                )
                start = end + 1
        return sections

    for index, raw in enumerate(_list(supplied, "probe.surface.sections")):
        item = _object(raw, f"probe.surface.sections[{index}]")
        _closed(item, SECTION_KEYS, f"probe.surface.sections[{index}]")
        section_id = _stable_id(
            item["section_id"],
            f"probe.surface.sections[{index}].section_id",
        )
        path = _relative_path(
            item["path"], f"probe.surface.sections[{index}].path"
        )
        if path not in files:
            raise ContractError(
                f"probe.surface.sections[{index}].path: not in candidate manifest"
            )
        start = _int(
            item["start_line"],
            f"probe.surface.sections[{index}].start_line",
            1,
            max(1, files[path]["lines"]),
        )
        end = _int(
            item["end_line"],
            f"probe.surface.sections[{index}].end_line",
            start,
            max(start, files[path]["lines"]),
        )
        if end - start + 1 > MAX_EVIDENCE_PACK_LINES:
            raise ContractError(
                f"probe.surface.sections[{index}]: exceeds "
                f"{MAX_EVIDENCE_PACK_LINES} lines; split it before planning"
            )
        sections.append(
            {
                "section_id": section_id,
                "path": path,
                "start_line": start,
                "end_line": end,
                "flows": _text_list(
                    item["flows"],
                    f"probe.surface.sections[{index}].flows",
                ),
            }
        )
    ids = [section["section_id"] for section in sections]
    if len(ids) != len(set(ids)):
        raise ContractError("probe.surface.sections: duplicate section_id")
    for path, file_entry in files.items():
        if file_entry["lines"] == 0:
            continue
        intervals = sorted(
            (
                section["start_line"],
                section["end_line"],
            )
            for section in sections
            if section["path"] == path
        )
        cursor = 1
        for start, end in intervals:
            if start > cursor:
                break
            cursor = max(cursor, end + 1)
        if cursor <= file_entry["lines"]:
            raise ContractError(
                f"probe.surface.sections: {path!r} leaves line {cursor} "
                "outside the neutral section map"
            )
    return sections


def _section_packs(sections: Sequence[Mapping[str, Any]]) -> list[list[dict]]:
    packs: list[list[dict]] = []
    current: list[dict] = []
    current_lines = 0
    for section in sections:
        lines = section["end_line"] - section["start_line"] + 1
        if current and current_lines + lines > MAX_EVIDENCE_PACK_LINES:
            packs.append(current)
            current = []
            current_lines = 0
        current.append(dict(section))
        current_lines += lines
    if current:
        packs.append(current)
    return packs


def _territory_sections(
    territory: Mapping[str, Any],
    *,
    sections: Sequence[Mapping[str, Any]],
    source_lines: int,
    where: str,
) -> list[dict]:
    by_id = {section["section_id"]: section for section in sections}
    supplied_ids = territory.get("section_ids")
    selected: list[dict] = []
    if supplied_ids is not None:
        ids = _stable_id_list(supplied_ids, f"{where}.section_ids")
        unknown = sorted(set(ids) - set(by_id))
        if unknown:
            raise ContractError(f"{where}.section_ids: unknown {unknown}")
        selected = [dict(by_id[section_id]) for section_id in ids]
    else:
        surfaces = territory.get("surfaces") or []
        if not isinstance(surfaces, list):
            raise ContractError(f"{where}.surfaces: expected array")
        for section in sections:
            if any(
                isinstance(surface, str)
                and (
                    surface == section["path"]
                    or surface.startswith(f"{section['path']}:")
                )
                for surface in surfaces
            ):
                selected.append(dict(section))
        if not selected and source_lines <= LARGE_SCOPE_LINES:
            selected = [dict(section) for section in sections]
    if not selected and source_lines > LARGE_SCOPE_LINES:
        raise ContractError(
            f"{where}: large-scope territory must name bounded section_ids"
        )
    return selected


def plan_run(
    probe: Mapping[str, Any],
    *,
    runtime_models: Iterable[str],
) -> dict:
    """Coverage-first preflight plan with runtime-valid routes and bounded packs."""
    probe = _object(probe, "probe")
    supported = _runtime_model_set(runtime_models)
    candidate = validate_candidate_identity(probe.get("candidate"), "probe.candidate")
    sizing = size_cohort(probe)
    band = sizing["band"]
    spec = BAND_SPEC[band]
    scores = _score_map(probe)
    max_score = max(scores.values())
    score_entries = _object(probe.get("scores", {}), "probe.scores")
    sections = _normalize_sections(probe, candidate)
    source_lines = sum(file_entry["lines"] for file_entry in candidate["files"])
    protected_dims = {
        dimension
        for axis, dimensions in PROTECTED_AXES.items()
        if _protected_axes(probe).get(axis)
        for dimension in dimensions
    }
    critical_dimensions = {
        dimension
        for dimension, score in scores.items()
        if score >= 90
        or (
            dimension in {"D04", "D05", "D07"}
            and score >= 80
        )
        or dimension in protected_dims
    }
    raw_territories = _list(
        probe.get("territories") or [], "probe.territories"
    )
    territories: list[dict] = []
    seen_territory_ids: set[str] = set()
    for index, raw in enumerate(raw_territories):
        item = _object(raw, f"probe.territories[{index}]")
        territory_id = _stable_id(
            item.get("id") or _generated_id("territory", index + 1),
            f"probe.territories[{index}].id",
        )
        if territory_id in seen_territory_ids:
            raise ContractError(
                f"probe.territories: duplicate id {territory_id!r}"
            )
        seen_territory_ids.add(territory_id)
        focus = str(
            item.get("focus_area") or item.get("id") or "generic-surface"
        )
        dimensions = _text_list(
            item.get("dimensions") or [],
            f"probe.territories[{index}].dimensions",
        )
        unknown_dimensions = sorted(set(dimensions) - set(DIMENSIONS))
        if unknown_dimensions:
            raise ContractError(
                f"probe.territories[{index}].dimensions: unknown "
                f"{unknown_dimensions}"
            )
        driving = max(
            (scores[dimension] for dimension in dimensions),
            default=max_score,
        )
        hotspot = False
        low_confidence = False
        for dimension in dimensions:
            entry = score_entries[dimension]
            if isinstance(entry, dict):
                hotspot = hotspot or bool(entry.get("hotspot"))
                confidence = entry.get("confidence", 100)
                if isinstance(confidence, int) and not isinstance(confidence, bool):
                    low_confidence = low_confidence or confidence < 70
        critical = bool(
            set(dimensions) & protected_dims
            or any(scores[dimension] >= 90 for dimension in dimensions)
            or any(
                dimension in {"D04", "D05", "D07"}
                and scores[dimension] >= 80
                for dimension in dimensions
            )
        )
        required = critical or hotspot or low_confidence or driving >= 40
        territory_sections = _territory_sections(
            item,
            sections=sections,
            source_lines=source_lines,
            where=f"probe.territories[{index}]",
        )
        territories.append(
            {
                "territory_id": territory_id,
                "focus_area": focus,
                "charter_id": charter_for(focus),
                "dimensions": dimensions,
                "driving_score": driving,
                "critical": critical,
                "required": required,
                "hotspot": hotspot,
                "low_confidence": low_confidence,
                "sections": territory_sections,
            }
        )

    if not territories:
        territories.append(
            {
                "territory_id": "generic-surface",
                "focus_area": "generic-surface",
                "charter_id": "generic-surface",
                "dimensions": sorted(critical_dimensions),
                "driving_score": max_score,
                "critical": band == "critical",
                "required": True,
                "hotspot": False,
                "low_confidence": False,
                "sections": [dict(section) for section in sections],
            }
        )
    if band == "critical" and raw_territories:
        mapped_critical_dimensions = {
            dimension
            for territory in territories
            for dimension in territory["dimensions"]
            if territory["critical"]
        }
        missing_critical_dimensions = sorted(
            critical_dimensions - mapped_critical_dimensions
        )
        if missing_critical_dimensions:
            raise CapacityError(
                "critical coverage mapping: named territories do not cover "
                f"{missing_critical_dimensions!r}; zero reviewer launches"
            )

    assignments: list[dict] = []

    def add_territory(
        territory: Mapping[str, Any],
        *,
        blind_to_probe: bool = False,
        purpose: str = "territory",
    ) -> None:
        packs = _section_packs(territory["sections"])
        if not packs:
            packs = [[]]
        for pack_index, pack_sections in enumerate(packs, start=1):
            assignment_id = _generated_id(
                "blind" if blind_to_probe else "review",
                territory["territory_id"],
                pack_index,
                len(assignments) + 1,
            )
            assignments.append(
                {
                    "assignment_id": assignment_id,
                    "territory_id": territory["territory_id"],
                    "focus_area": territory["focus_area"],
                    "charter_id": territory["charter_id"],
                    "dimensions": list(territory["dimensions"]),
                    "driving_score": territory["driving_score"],
                    "critical": territory["critical"],
                    "blind_to_probe": blind_to_probe,
                    "purpose": purpose,
                    "evidence_pack": {
                        "pack_id": _generated_id("pack", assignment_id),
                        "candidate_id": candidate["candidate_id"],
                        "sections": pack_sections,
                        "line_count": sum(
                            section["end_line"] - section["start_line"] + 1
                            for section in pack_sections
                        ),
                    },
                }
            )

    required_territories = [
        territory for territory in territories if territory["required"]
    ]
    for territory in required_territories:
        add_territory(territory)
    optional_reviewed: set[str] = set()
    low, high = spec["reviewers"]
    for territory in territories:
        if len(assignments) >= low:
            break
        if territory["required"]:
            continue
        add_territory(territory, purpose="proportional-band-floor")
        optional_reviewed.add(territory["territory_id"])
    waived_territories = [
        {
            "territory_id": territory["territory_id"],
            "why": "all driving dimensions below 40 with no hotspot or low-confidence signal",
        }
        for territory in territories
        if not territory["required"]
        and territory["territory_id"] not in optional_reviewed
    ]

    if band == "critical":
        critical = [
            territory for territory in territories if territory["critical"]
        ]
        if not critical:
            critical = [max(territories, key=lambda item: item["driving_score"])]
        blind_territory = max(
            critical, key=lambda item: item["driving_score"]
        )
        add_territory(
            blind_territory,
            blind_to_probe=True,
            purpose="critical-independent-redundancy",
        )

    surface = _object(probe.get("surface", {}), "probe.surface")
    integration_points = surface.get("integration_points") or []
    if not isinstance(integration_points, list):
        raise ContractError("probe.surface.integration_points: expected array")
    by_section_id = {section["section_id"]: section for section in sections}
    neutral_integrations: list[dict] = []
    for index, raw in enumerate(integration_points):
        item = _object(raw, f"probe.surface.integration_points[{index}]")
        _closed(
            item,
            INTEGRATION_POINT_KEYS,
            f"probe.surface.integration_points[{index}]",
        )
        point_id = _stable_id(
            item["id"], f"probe.surface.integration_points[{index}].id"
        )
        territory_ids = _stable_id_list(
            item["territory_ids"],
            f"probe.surface.integration_points[{index}].territory_ids",
        )
        section_ids = _stable_id_list(
            item["section_ids"],
            f"probe.surface.integration_points[{index}].section_ids",
        )
        unknown_territories = sorted(
            set(territory_ids) - seen_territory_ids
        )
        unknown_sections = sorted(set(section_ids) - set(by_section_id))
        if unknown_territories or unknown_sections:
            raise ContractError(
                f"probe.surface.integration_points[{index}]: "
                f"unknown territories={unknown_territories}, "
                f"unknown sections={unknown_sections}"
            )
        neutral_integrations.append(
            {
                "id": point_id,
                "territory_ids": territory_ids,
                "section_ids": section_ids,
                "flow": _text(
                    item["flow"],
                    f"probe.surface.integration_points[{index}].flow",
                ),
            }
        )
        if _bool(
            item["requires_reviewer"],
            f"probe.surface.integration_points[{index}].requires_reviewer",
        ):
            add_territory(
                {
                    "territory_id": point_id,
                    "focus_area": "architecture-maintainability",
                    "charter_id": "architecture-maintainability",
                    "dimensions": ["D14"],
                    "driving_score": max_score,
                    "critical": band == "critical",
                    "sections": [
                        dict(by_section_id[section_id])
                        for section_id in section_ids
                    ],
                },
                purpose="explicit-cross-territory-integration",
            )

    assigned_section_ids = {
        section["section_id"]
        for assignment in assignments
        for section in assignment["evidence_pack"]["sections"]
    }
    unassigned_sections = [
        dict(section)
        for section in sections
        if section["section_id"] not in assigned_section_ids
    ]
    if source_lines > LARGE_SCOPE_LINES and unassigned_sections:
        add_territory(
            {
                "territory_id": "unassigned-source-scope",
                "focus_area": "generic-surface",
                "charter_id": "generic-surface",
                "dimensions": ["D01"],
                "driving_score": scores["D01"],
                "critical": False,
                "sections": unassigned_sections,
            },
            purpose="large-scope-completeness",
        )

    while len(assignments) < low:
        source = assignments[0] if assignments else None
        pack_sections = (
            [dict(section) for section in source["evidence_pack"]["sections"]]
            if source
            else []
        )
        add_territory(
            {
                "territory_id": _generated_id(
                    "supporting-review", len(assignments) + 1
                ),
                "focus_area": "generic-surface",
                "charter_id": "generic-surface",
                "dimensions": ["D11"],
                "driving_score": max_score,
                "critical": False,
                "sections": pack_sections,
            },
            purpose="band-depth-support",
        )

    verifier_planned = spec["verifier"] != "no"
    verifier_reserved = spec["verifier"] == "yes"
    reviewer_capacity = min(
        BASE_MAX_REVIEWERS,
        high,
        spec["max_dispatches"] - 1 - int(verifier_reserved),
    )
    if len(assignments) > reviewer_capacity:
        required_ids = [assignment["assignment_id"] for assignment in assignments]
        critical_ids = sorted(
            {
                assignment["territory_id"]
                for assignment in assignments
                if assignment["critical"]
            }
        )
        raise CapacityError(
            "coverage capacity: required bounded reviewer assignments "
            f"{len(assignments)} exceed capacity {reviewer_capacity} for "
            f"{band!r}; critical_territories={critical_ids!r}; "
            f"required_assignments={required_ids!r}; zero reviewer launches"
        )

    section_owners: dict[str, list[str]] = {}
    for assignment in assignments:
        for section in assignment["evidence_pack"]["sections"]:
            section_owners.setdefault(section["section_id"], []).append(
                assignment["assignment_id"]
            )
    for assignment in assignments:
        assignment["overlap_section_ids"] = sorted(
            section["section_id"]
            for section in assignment["evidence_pack"]["sections"]
            if len(section_owners[section["section_id"]]) > 1
        )
        route = route_reviewer(
            score=assignment.pop("driving_score"),
            runtime_models=supported,
        )
        assignment.update(
            {
                "model_class": route["model_class"],
                "slug": route["slug"],
                "rigor": route["rigor"],
                "fallbacks": route["fallbacks"],
                "filtered_models": route["filtered_out"],
                "candidate_id": candidate["candidate_id"],
                "neutral_flow_map": {
                    "flows": _text_list(
                        surface.get("flows") or [],
                        "probe.surface.flows",
                    ),
                    "integration_points": neutral_integrations,
                },
            }
        )

    verifier = None
    if verifier_planned:
        verifier_route = route_verifier(
            priority="P0" if band == "critical" else "P1",
            runtime_models=supported,
        )
        verifier = {
            "assignment_id": "verifier",
            "required": spec["verifier"] == "yes",
            "conditional": spec["verifier"] == "gated",
            "reserved": verifier_reserved,
            "candidate_id": candidate["candidate_id"],
            "model_class": verifier_route["model_class"],
            "slug": verifier_route["slug"],
            "rigor": verifier_route["rigor"],
            "fallbacks": verifier_route["fallbacks"],
            "filtered_models": verifier_route["filtered_out"],
        }

    concurrency = spec["concurrency"]
    waves = [
        [
            assignment["assignment_id"]
            for assignment in assignments[index:index + concurrency]
        ]
        for index in range(0, len(assignments), concurrency)
    ]
    if verifier is not None and verifier["reserved"]:
        waves.append(["verifier"])
    depth = str(
        _object(probe.get("complexity", {}), "probe.complexity").get(
            "depth", "shallow"
        )
    )
    window = execution_window(
        band=band,
        lines_changed=max(
            source_lines,
            sizing["signals"]["lines_changed"],
        ),
        territory_count=len(territories),
        depth=depth,
    )
    charter_ids = list(
        dict.fromkeys(assignment["charter_id"] for assignment in assignments)
    )
    critical_territory_ids = sorted(
        {
            assignment["territory_id"]
            for assignment in assignments
            if assignment["critical"]
        }
    )
    blind_assignment_ids = sorted(
        assignment["assignment_id"]
        for assignment in assignments
        if assignment["blind_to_probe"]
    )
    return {
        "schema": "swarm-preflight-plan/v2",
        "preflight": {"status": "ready", "reviewer_launches": 0},
        "band": band,
        "candidate": candidate,
        "cohort": assignments,
        "verifier": verifier,
        "waves": waves,
        "budget": {
            "max_accepted_workers": spec["max_dispatches"],
            "absolute_max_accepted_workers": ABSOLUTE_MAX_DISPATCHES,
            "reviewer_capacity": reviewer_capacity,
            "concurrency": concurrency,
            **window,
        },
        "coverage": {
            "required_assignment_ids": sorted(
                assignment["assignment_id"] for assignment in assignments
            ),
            "required_critical_territory_ids": critical_territory_ids,
            "required_probe_blind_assignment_ids": blind_assignment_ids,
            "waived_territories": waived_territories,
            "uncovered": [],
        },
        "charter_ids": charter_ids,
    }


# --- JIT decision gates (§7 verifier gate, §8 second-pass gate) ---

# Protected axes whose blocking findings force the §7 verifier gate.
GATE_BLOCKING_DIMENSIONS = {"D03", "D04", "D05", "D07"}
GATE_BLOCKING_FOCUS = {
    "security", "privacy", "data-integrity", "concurrency",
    "security-authz", "privacy-secrets", "data-integrity-migration", "concurrency-ordering",
}
# A finding curated into one of these states is no longer a live verifier candidate.
_GATE_DISMISSED_STATUSES = {"false-positive", "duplicate"}


def _finding_field(finding: Mapping[str, Any], name: str) -> Any:
    """Read a finding field from the conformed shape (nested impact) or a flat curated dict."""
    impact = finding.get("impact")
    if name in ("priority", "risk_score", "confidence") and isinstance(impact, dict) and name in impact:
        return impact.get(name)
    return finding.get(name)


def gate_verifier(findings: Any, *, critical_change: bool = False, clearance_request: bool = False) -> dict:
    """SKILL.md §7 verifier gate: findings (+ change flags) -> run exactly one verifier?

    Band-independent. Fires on a candidate P0, an unresolved P1 contradiction, a
    blocking security/privacy/data-integrity/concurrency finding, or an explicit
    shipping-clearance request on a critical change. Returns every reason that
    fired; `run` is true iff any fired. Accepts a bare findings array or a reviewer
    return object with a `findings` key; each finding may be the conformed shape
    (priority under `impact`) or a flat curated dict (top-level `priority`).
    """
    if isinstance(findings, dict) and "findings" in findings:
        findings = findings["findings"]
    findings = _list(findings, "findings")
    reasons: list = []
    for i, raw in enumerate(findings):
        finding = _object(raw, f"findings[{i}]")
        status = str(_finding_field(finding, "status") or "open")
        if status in _GATE_DISMISSED_STATUSES:
            continue
        priority = _finding_field(finding, "priority")
        fid = finding.get("finding_id") or f"findings[{i}]"
        if priority == "P0":
            reasons.append(f"candidate P0 {fid} needs independent adjudication")
        if priority == "P1" and (finding.get("contradicts") or finding.get("contradicted")):
            reasons.append(f"unresolved P1 contradiction on {fid}")
        dimension = _finding_field(finding, "dimension")
        focus = _finding_field(finding, "focus_area")
        on_protected_axis = dimension in GATE_BLOCKING_DIMENSIONS or focus in GATE_BLOCKING_FOCUS
        blocks_shipping = bool(finding.get("blocks_shipping")) or priority in ("P0", "P1")
        if on_protected_axis and blocks_shipping:
            reasons.append(f"blocking {dimension or focus} finding {fid} would block shipping")
    if clearance_request and critical_change:
        reasons.append("explicit shipping-clearance request on a critical change")
    return {"run": bool(reasons), "reasons": reasons}


def gate_second_pass(state: Mapping[str, Any]) -> dict:
    """SKILL.md §8 second-pass gate: state -> allow a scoped second pass?

    Allowed only when ALL hold: (1) a §8 trigger fires — a candidate P0/P1 lacks
    independent evidence, two material findings contradict, a named critical
    territory is uncovered, or a fix changed a reviewed critical boundary; (2) the
    exact unresolved question + territory are stated; (3) at most two existing
    charter IDs are reused; (4) the dispatch/time budget still allows NEW work.

    A second pass launches new work, so its binding time budget is the
    20-minute start-new-work cutoff. Healthy accepted workers may finish inside
    their separately planned scope-aware completion allowance. An optional
    `band` signal, when supplied, refuses a second pass for a band whose spec
    forbids one (trivial/small/standard), preserving "single pass by default."
    """
    state = _object(state, "state")
    triggers = {
        "candidate_without_evidence": bool(state.get("candidate_without_evidence")),
        "contradiction": bool(state.get("contradiction")),
        "uncovered_critical_territory": bool(state.get("uncovered_critical_territory")),
        "fix_changed_critical_boundary": bool(state.get("fix_changed_critical_boundary")),
    }
    fired = [name for name, hit in triggers.items() if hit]

    question = str(state.get("unresolved_question") or "").strip()
    territory = str(state.get("territory") or "").strip()
    stated = bool(question and territory)

    reused = state.get("reused_charter_ids") or []
    if not isinstance(reused, list):
        raise ContractError("state.reused_charter_ids: expected array")
    reuse_ok = len(reused) <= 2

    dispatches_used = _int(state.get("dispatches_used", 0), "state.dispatches_used", 0, 100_000)
    minutes = state.get("minutes_elapsed", 0)
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
        raise ContractError("state.minutes_elapsed: expected number")
    remaining_dispatches = ABSOLUTE_MAX_DISPATCHES - dispatches_used
    seconds = minutes * 60
    budget_remains = (
        remaining_dispatches >= 1
        and seconds <= NO_NEW_DISPATCH_SECONDS
    )

    band = state.get("band")
    band_ok = True
    if isinstance(band, str) and band.strip():
        key = band.strip().lower()
        if key not in BAND_SPEC:
            raise ContractError(f"state.band: expected one of {BANDS}")
        band_ok = BAND_SPEC[key]["second_pass"] != "no"

    allowed = bool(fired) and stated and reuse_ok and budget_remains and band_ok
    if allowed:
        reason = (f"second pass allowed ({fired[0]}); "
                  f"{remaining_dispatches} of {ABSOLUTE_MAX_DISPATCHES} dispatches free, "
                  f"{int(minutes)} min elapsed")
    else:
        why: list = []
        if not fired:
            why.append("no second-pass trigger holds")
        if not stated:
            why.append("exact unresolved question + territory not both stated")
        if not reuse_ok:
            why.append(f"reuses more than 2 charter ids ({len(reused)})")
        if not band_ok:
            why.append(f"{band} band does not permit a second pass")
        if not budget_remains:
            if remaining_dispatches < 1:
                why.append(f"dispatch budget exhausted ({dispatches_used} of {ABSOLUTE_MAX_DISPATCHES} used)")
            else:
                why.append(
                    f"past the start-new-work cutoff ({int(minutes)} min, "
                    f"limit {NO_NEW_DISPATCH_SECONDS // 60})"
                )
        reason = "second pass denied: " + "; ".join(why)
    return {"allowed": allowed, "reason": reason}


# --- Curated report (§4.5): <=10 findings; P3/P4 summarized by count ---

MAX_REPORT_FINDINGS = 10
_PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}


def _md(value: Any) -> str:
    text = str(value if value not in (None, "") else "None")
    return text.replace("|", "\\|").replace("\n", "<br>")


def _finding_priority(f: Mapping[str, Any]) -> str:
    return (f.get("impact") or {}).get("priority", "P4")


def _finding_risk(f: Mapping[str, Any]) -> int:
    return (f.get("impact") or {}).get("risk_score", 0)


def render_report(result: Mapping[str, Any]) -> str:
    """Render a thin curated operator report from a curated result object."""
    result = _object(result, "result")
    band = result.get("band", "unknown")
    findings = _list(result.get("findings", []), "result.findings")
    rev = result.get("subject_revision") or {}
    ranked = sorted(findings, key=lambda f: (_PRIORITY_RANK.get(_finding_priority(f), 99), -_finding_risk(f)))
    majors = [f for f in ranked if _finding_priority(f) in ("P0", "P1", "P2")]
    shown = majors[:MAX_REPORT_FINDINGS]
    minor = [f for f in ranked if _finding_priority(f) in ("P3", "P4")]
    p3 = sum(_finding_priority(f) == "P3" for f in minor)
    p4 = sum(_finding_priority(f) == "P4" for f in minor)

    lines = [
        "### BLUF",
        f"- Band: {_md(BAND_DISPLAY.get(band, band))}",
        f"- Verdict: {_md(result.get('verdict', 'None recorded'))}",
        f"- Shipping clearance: {_md(result.get('shipping_clearance', 'not_evaluated'))}",
        f"- Dispatches: {_md(result.get('dispatches', 'n/a'))}",
        f"- Subject revision: {_md(rev.get('head', 'unknown'))}" + (" (dirty)" if rev.get("dirty") else ""),
        f"- Candidate: {_md(result.get('candidate_id', 'unknown'))}",
        "",
        "### CURATED FINDINGS",
        "| ID | Priority | Risk | Dim | Focus | Root cause | Correction | Status |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for f in shown:
        imp = f.get("impact", {})
        lines.append("| " + " | ".join(_md(v) for v in (
            f.get("finding_id"), imp.get("priority"), imp.get("risk_score"),
            f.get("dimension"), f.get("focus_area"), f.get("root_cause"),
            f.get("correction"), f.get("status"),
        )) + " |")
    if not shown:
        lines.append("| None | P4 | 1 | - | - | No P0-P2 findings | - | open |")
    if len(majors) > len(shown):
        lines.append(f"\n_+{len(majors) - len(shown)} more P0-P2 findings truncated at {MAX_REPORT_FINDINGS}._")
    lines += ["", f"_Minor findings summarized: P3 x {p3}, P4 x {p4}._"]

    coverage = result.get("coverage") or {}
    if coverage:
        lines += ["", "### COVERAGE", f"- Reviewers: {_md(coverage.get('reviewers', 'n/a'))}"]
        for failure in coverage.get("failed_dispatches") or []:
            lines.append(
                f"- Failed dispatch ({_md(failure.get('failure_class', 'unknown'))}): "
                f"assignment={_md(failure.get('assignment_id', 'unknown assignment'))}; "
                f"territory={_md(failure.get('territory', 'unknown territory'))}"
            )
        for w in coverage.get("waived") or []:
            lines.append(f"- Waived {_md(w.get('dimension'))}: {_md(w.get('why'))} (evidence: {_md(w.get('evidence'))})")
        uncovered = coverage.get("uncovered") or []
        if uncovered:
            lines.append(f"- Uncovered: {_md('; '.join(str(u) for u in uncovered))}")
    lines.append("")
    return "\n".join(lines)


# --- Subject revision (simplified: git rev-parse HEAD + dirty flag) ---

def subject_revision(root: str = ".") -> dict:
    """Return {head, dirty, root} using read-only git. No schema version, no ceremony."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}

    def _git(args: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env,
        )

    head = _git(["rev-parse", "HEAD"])
    if head.returncode != 0:
        if _git(["rev-parse", "--show-toplevel"]).returncode != 0:
            raise ContractError(f"subject_revision: not a git repository: {root}")
        return {"head": "UNBORN", "dirty": True, "root": str(root)}
    status = _git(["status", "--porcelain"])
    return {
        "head": head.stdout.decode("ascii", "replace").strip(),
        "dirty": bool(status.stdout.strip()),
        "root": str(root),
    }
