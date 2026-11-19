#!/usr/bin/env python3
"""The handler contract for local-jobs: describe/instance validation, a typed
``HandlerError`` with a quarantine projection, and schema-driven arg parsing.

This is the "scaffolding of requirements" that makes every job uniform. The
registry validates handler output against it (failure → one quarantine row, not
an aborted view), and the CLI builds ``add``/``update`` entries from each type's
declared ``add_schema`` so new types never edit the core.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
ROLES = {"instance", "global_scheduler", "error"}
CARDINALITIES = {"singleton", "multi"}
SCHEMA_KINDS = {
    "bool",
    "flag",
    "id",
    "int",
    "interval_seconds",
    "list",
    "map",
    "scalar",
    "schedule",
}


class HandlerError(Exception):
    """A typed handler failure that the registry can quarantine + attribute."""

    def __init__(self, job_type: str, verb: str, rc: int, reason: str, stderr_tail: str = "") -> None:
        super().__init__(f"{job_type} {verb}: {reason}")
        self.job_type = job_type
        self.verb = verb
        self.rc = rc
        self.reason = reason
        self.stderr_tail = (stderr_tail or "").strip()

    def quarantine_row(self) -> dict[str, Any]:
        return quarantine_row(self.job_type, self.reason, self.stderr_tail, verb=self.verb, rc=self.rc)


def quarantine_row(
    job_type: str,
    reason: str,
    stderr_tail: str = "",
    verb: str = "discover",
    rc: int | None = None,
) -> dict[str, Any]:
    """One uniform row representing a quarantined (broken) type.

    Carries ``role:"error"`` so views/dashboards render it as degraded rather
    than crashing, and never claims an agent is loaded.
    """
    return {
        "id": f"{job_type} (error)",
        "type": job_type,
        "role": "error",
        "enabled": False,
        "schedule": None,
        "launchd_label": None,
        "launchd_loaded": None,
        "error": {"verb": verb, "rc": rc, "reason": reason, "stderr_tail": (stderr_tail or "")[-500:]},
    }


def validate_describe(desc: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(desc, dict):
        return ["describe did not return a JSON object"]
    if not desc.get("type"):
        errs.append("describe.type is required")
    if desc.get("cardinality") not in CARDINALITIES:
        errs.append("describe.cardinality must be 'singleton' or 'multi'")
    if not desc.get("label_token"):
        errs.append("describe.label_token is required")
    if not isinstance(desc.get("add_schema"), list):
        errs.append("describe.add_schema must be a list")
    else:
        seen_flags: set[str] = set()
        groups: dict[str, int] = {}
        for i, field in enumerate(desc["add_schema"]):
            if not isinstance(field, dict) or "flag" not in field:
                errs.append(f"add_schema[{i}] must be an object with a 'flag'")
                continue
            flag = field.get("flag")
            if not isinstance(flag, str) or not flag.startswith("--"):
                errs.append(f"add_schema[{i}].flag must start with '--'")
            elif flag in seen_flags:
                errs.append(f"add_schema[{i}].flag is duplicated: {flag}")
            else:
                seen_flags.add(flag)
            kind = field.get("kind", "scalar")
            if kind not in SCHEMA_KINDS:
                errs.append(f"add_schema[{i}].kind is unsupported: {kind}")
            group = field.get("required_one_of")
            if group is not None:
                if not isinstance(group, str) or not group.strip():
                    errs.append(f"add_schema[{i}].required_one_of must be a non-empty string")
                else:
                    groups[group] = groups.get(group, 0) + 1
                if field.get("required"):
                    errs.append(
                        f"add_schema[{i}] cannot combine required and required_one_of"
                    )
        for group, count in groups.items():
            if count < 2:
                errs.append(f"required_one_of group {group!r} must contain at least two fields")
    sv = desc.get("schema_version", 1)
    if not isinstance(sv, int) or sv < 1:
        errs.append("describe.schema_version must be a positive integer")
    return errs


def validate_instance(inst: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(inst, dict):
        return ["instance is not a JSON object"]
    role = inst.get("role", "instance")
    if role not in ROLES:
        errs.append(f"role must be one of {sorted(ROLES)}")
    if role == "error":
        return errs  # quarantine rows are intentionally minimal
    for key in ("id", "type", "launchd_label"):
        if not inst.get(key):
            errs.append(f"instance.{key} is required")
    if not isinstance(inst.get("enabled", True), bool):
        errs.append("instance.enabled must be a bool")
    loaded = inst.get("launchd_loaded")
    if loaded is not None and not isinstance(loaded, bool):
        errs.append("instance.launchd_loaded must be bool or null")
    iid = inst.get("id")
    if isinstance(iid, str) and iid not in ("__global__",) and not ID_PATTERN.match(iid):
        errs.append(f"instance.id is not sanitary (^[A-Za-z0-9._-]+$): {iid!r}")
    return errs


def sanitize_id(value: str) -> str:
    if not value or not ID_PATTERN.match(value):
        raise ValueError(f"invalid id (must match ^[A-Za-z0-9._-]+$): {value!r}")
    return value


def _coerce(kind: str, value: str) -> Any:
    if kind == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")
    if kind == "int":
        return int(value)
    if kind == "interval_seconds":
        if isinstance(value, bool) or not str(value).strip().lstrip("+-").isdigit():
            raise ValueError("interval seconds must be an integer")
        return {"kind": "interval", "seconds": int(value)}
    return value


def build_entry(
    add_schema: list[dict[str, Any]],
    argv: list[str],
    seed_defaults: bool = True,
    check_required: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """Build a store entry from CLI flags, driven entirely by ``add_schema``.

    Each schema field may declare ``field`` (target key; defaults to the flag
    without dashes), ``kind`` (``scalar``|``list``|``map``|``bool``|``int``|
    ``id``|``schedule``|``interval_seconds``; default ``scalar``), ``required``,
    ``required_one_of`` (a named, mutually-exclusive required group), and
    ``default``.
    Supports ``--flag value``, ``--flag=value`` and repeated flags for lists/maps.

    With ``seed_defaults=False`` / ``check_required=False`` this builds a partial
    patch (only the explicitly-provided fields) for ``update``.
    """
    by_flag: dict[str, dict[str, Any]] = {f["flag"]: f for f in add_schema if isinstance(f, dict) and "flag" in f}
    entry: dict[str, Any] = {}
    errors: list[str] = []

    if seed_defaults:
        for field in add_schema:
            if isinstance(field, dict) and "default" in field:
                entry[_field_name(field)] = field["default"]

    i = 0
    seen: set[str] = set()
    while i < len(argv):
        tok = argv[i]
        flag, inline_val = (tok.split("=", 1) + [None])[:2] if tok.startswith("--") and "=" in tok else (tok, None)
        spec = by_flag.get(flag)
        if spec is None:
            errors.append(f"unknown flag: {flag}")
            i += 1
            continue
        kind = spec.get("kind", "scalar")
        name = _field_name(spec)
        if kind == "flag":  # boolean presence flag
            entry[name] = True
            seen.add(flag)
            i += 1
            continue
        if inline_val is not None:
            value = inline_val
        else:
            if i + 1 >= len(argv):
                errors.append(f"{flag} requires a value")
                break
            value = argv[i + 1]
            i += 1
        i += 1
        seen.add(flag)
        try:
            if kind == "list":
                entry.setdefault(name, [])
                entry[name].append(value)
            elif kind == "map":
                if "=" not in value:
                    errors.append(f"{flag} expects K=V, got: {value}")
                else:
                    k, v = value.split("=", 1)
                    entry.setdefault(name, {})
                    entry[name][k] = v
            elif kind == "id":
                entry[name] = sanitize_id(value)
            else:
                coerced = _coerce(kind, value)
                choices = spec.get("choices")
                if choices and coerced not in choices:
                    errors.append(f"{flag} must be one of: {', '.join(map(str, choices))}")
                entry[name] = coerced
        except ValueError as exc:
            errors.append(str(exc))

    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in add_schema:
        if isinstance(spec, dict) and spec.get("required_one_of"):
            groups.setdefault(str(spec["required_one_of"]), []).append(spec)
    for members in groups.values():
        chosen = [spec["flag"] for spec in members if spec.get("flag") in seen]
        flags = ", ".join(str(spec["flag"]) for spec in members)
        if len(chosen) > 1:
            errors.append(f"flags are mutually exclusive: {flags}")
        elif check_required and not chosen and not any(_unless_waived(spec, entry) for spec in members):
            errors.append(f"missing one of: {flags}")

    if check_required:
        for spec in add_schema:
            if (
                isinstance(spec, dict)
                and spec.get("required")
                and spec["flag"] not in seen
                and _field_name(spec) not in entry
                and not _unless_waived(spec, entry)
            ):
                errors.append(f"missing required flag: {spec['flag']}")
    return entry, errors


def _field_name(spec: dict[str, Any]) -> str:
    if spec.get("field"):
        return spec["field"]
    return spec["flag"].lstrip("-").replace("-", "_")


def _field_help(spec: dict[str, Any]) -> str:
    return str(spec.get("help") or spec.get("description") or spec.get("flag", ""))


def _unless_waived(spec: dict[str, Any], values: dict[str, Any]) -> bool:
    """True when a field's requirement is waived by ``required_unless``.

    ``required_unless`` is ``{"field": <name>, "equals": <value>}``: the field
    (or its ``required_one_of`` group) is not required when the referenced field
    already equals the given value. This lets a type make a field conditionally
    required (e.g. a schedule required only for ``execution_mode: scheduled``)
    with no core edit — absent the key, behavior is unchanged.
    """
    cond = spec.get("required_unless")
    if not isinstance(cond, dict):
        return False
    return values.get(cond.get("field")) == cond.get("equals")


def _argv_values(add_schema: list[dict[str, Any]], argv: list[str]) -> dict[str, Any]:
    """Best-effort scalar field values from raw argv + declared defaults.

    Used only to evaluate ``required_unless`` in the CLI pre-check
    (``missing_required``); it seeds the same defaults ``build_entry`` does so an
    omitted conditional field resolves to its declared default.
    """
    values: dict[str, Any] = {}
    for spec in add_schema:
        if isinstance(spec, dict) and "default" in spec:
            values[_field_name(spec)] = spec["default"]
    by_flag = {f["flag"]: f for f in add_schema if isinstance(f, dict) and "flag" in f}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and "=" in tok:
            flag, inline = tok.split("=", 1)
        else:
            flag, inline = tok, None
        spec = by_flag.get(flag)
        if spec is None:
            i += 1
            continue
        name = _field_name(spec)
        if spec.get("kind") == "flag":
            values[name] = True
            i += 1
            continue
        if inline is not None:
            values[name] = inline
            i += 1
            continue
        if i + 1 < len(argv):
            values[name] = argv[i + 1]
            i += 2
            continue
        i += 1
    return values


def missing_required(add_schema: list[dict[str, Any]], argv: list[str]) -> list[dict[str, str]]:
    """Return missing required flags as ``{flag, help}`` objects for operator UX."""
    present = set()
    for tok in argv:
        if tok.startswith("--"):
            present.add(tok.split("=", 1)[0])
    values = _argv_values(add_schema, argv)
    out: list[dict[str, str]] = []
    for spec in add_schema:
        if not isinstance(spec, dict) or not spec.get("required"):
            continue
        flag = spec["flag"]
        if flag not in present and not _unless_waived(spec, values):
            out.append({"flag": flag, "help": _field_help(spec)})
    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in add_schema:
        if isinstance(spec, dict) and spec.get("required_one_of"):
            groups.setdefault(str(spec["required_one_of"]), []).append(spec)
    for members in groups.values():
        if any(spec.get("flag") in present for spec in members):
            continue
        if any(_unless_waived(spec, values) for spec in members):
            continue
        flags = ", ".join(str(spec["flag"]) for spec in members)
        out.append(
            {
                "flag": f"one of {flags}",
                "help": "choose one schedule form",
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="contract.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate-describe")  # describe JSON on stdin
    p_inst = sub.add_parser("validate-instances")  # instance array on stdin
    p_inst.add_argument("--allow-empty", action="store_true")
    p_build = sub.add_parser("build-entry")
    p_build.add_argument("--schema", required=True, help="add_schema JSON")
    p_build.add_argument("rest", nargs=argparse.REMAINDER)
    p_patch = sub.add_parser("build-patch")
    p_patch.add_argument("--schema", required=True, help="add_schema JSON")
    p_patch.add_argument("rest", nargs=argparse.REMAINDER)
    p_miss = sub.add_parser("missing-required")
    p_miss.add_argument("--schema", required=True, help="add_schema JSON")
    p_miss.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    if args.cmd == "validate-describe":
        errs = validate_describe(json.loads(sys.stdin.read() or "null"))
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 2
        print("ok")
        return 0
    if args.cmd == "validate-instances":
        data = json.loads(sys.stdin.read() or "[]")
        if not isinstance(data, list):
            print("instances payload must be a JSON array", file=sys.stderr)
            return 2
        all_errs = []
        for inst in data:
            all_errs += validate_instance(inst)
        if all_errs:
            print("\n".join(all_errs), file=sys.stderr)
            return 2
        print("ok")
        return 0
    if args.cmd in ("build-entry", "build-patch"):
        schema = json.loads(args.schema)
        rest = list(args.rest)
        if rest and rest[0] == "--":
            rest = rest[1:]
        is_patch = args.cmd == "build-patch"
        entry, errors = build_entry(
            schema, rest, seed_defaults=not is_patch, check_required=not is_patch
        )
        if errors:
            print(json.dumps({"errors": errors}), file=sys.stderr)
            return 2
        print(json.dumps(entry))
        return 0
    if args.cmd == "missing-required":
        schema = json.loads(args.schema)
        rest = list(args.rest)
        if rest and rest[0] == "--":
            rest = rest[1:]
        miss = missing_required(schema, rest)
        if miss:
            print(json.dumps(miss), file=sys.stderr)
            return 2
        print("ok")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
