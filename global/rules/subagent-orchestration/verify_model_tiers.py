#!/usr/bin/env python3
"""Validate the shared subagent model-tier catalog and plan launches from it.

With no arguments, checks the catalog's structure and that no backup is weaker
than its tier. With --runtime-models (the concrete model names Cursor offers
subagents this session), also prints the model each tier resolves to, warns on
a fallback, and fails only when a tier has no match. The plan subcommand names
the models to launch for one kind of work and the order to try them in. The
catalog content is owned by model-tiers.json alone; nothing here names a model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "cursor-model-tiers/v2"
TIERS = ("deep", "critical", "standard", "economy")
STRENGTH = {"deep": 3, "critical": 3, "standard": 2, "economy": 1}
WORK_KINDS = {
    "find": ("economy", "search, reading, log summaries"),
    "run": ("economy", "running checks, polling, mechanical edits"),
    "build": ("standard", "well-specified builds, moderate refactors, tests, docs"),
    "review": ("standard", "routine review"),
    "design": (
        "deep",
        "architecture, planning, ambiguous or cross-system work, complex or "
        "security-sensitive work, anything irreversible or shipping",
    ),
    "sign-off": (
        "critical",
        "independent review and sign-off of deep work, merge and release gates, "
        "/swarm adjudication",
    ),
}
REVIEW_KINDS = frozenset({"review", "sign-off"})
# Cursor chooses these subagent types' model itself and ignores the model argument.
PINNED_SUBAGENT_TYPES = frozenset({"bugbot"})
RETRY_WAIT_SECONDS = 60
REVISION_PREFIX = "cursor-subagent-model-enum/"
ROOT_KEYS = {"schema", "verified_against", "tiers"}
TIER_KEYS = {"candidates"}
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+(?:\.[a-z0-9]+)*)+$")
PROVIDER_RE = re.compile(r"^[a-z][a-z0-9]*$")


class CatalogError(ValueError):
    """A deterministic catalog contract failure."""


class PlanError(ValueError):
    """A plan request that must launch nothing."""


def provider(name: str) -> str:
    """The vendor prefix before the first hyphen."""
    return name.split("-", 1)[0]


def family(name: str) -> str:
    """The model without its final level suffix; other levels share a family."""
    return name.rsplit("-", 1)[0]


def _closed(value: Mapping[str, Any], keys: set[str], where: str) -> None:
    missing = keys - set(value)
    extra = set(value) - keys
    if missing:
        raise CatalogError(f"{where}: missing keys {sorted(missing)}")
    if extra:
        raise CatalogError(f"{where}: unknown keys {sorted(extra)}")


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError("catalog: expected object")
    return value


def _check_verified_against(value: Any) -> None:
    """Informational "last checked against the live list" date; no age limit."""
    if not isinstance(value, str) or not value.startswith(REVISION_PREFIX):
        raise CatalogError(
            f"catalog.verified_against: expected {REVISION_PREFIX}YYYY-MM-DD"
        )
    try:
        date.fromisoformat(value[len(REVISION_PREFIX):])
    except ValueError as exc:
        raise CatalogError(
            f"catalog.verified_against: unparseable date in {value!r}"
        ) from exc


def validate_catalog(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError("catalog: expected object")
    _closed(value, ROOT_KEYS, "catalog")
    if value["schema"] != SCHEMA:
        raise CatalogError(f"catalog.schema: expected {SCHEMA}")
    _check_verified_against(value["verified_against"])
    tiers = value["tiers"]
    if not isinstance(tiers, dict) or set(tiers) != set(TIERS):
        raise CatalogError(f"catalog.tiers: expected exactly {sorted(TIERS)}")

    normalized: dict[str, list[str]] = {}
    for tier in TIERS:
        spec = tiers[tier]
        where = f"catalog.tiers.{tier}"
        if not isinstance(spec, dict):
            raise CatalogError(f"{where}: expected object")
        _closed(spec, TIER_KEYS, where)
        candidates = spec["candidates"]
        if not isinstance(candidates, list) or not candidates:
            raise CatalogError(f"{where}.candidates: expected a non-empty list")
        for name in candidates:
            if not isinstance(name, str) or not NAME_RE.match(name):
                raise CatalogError(f"{where}.candidates: malformed name {name!r}")
        if len(candidates) != len(set(candidates)):
            raise CatalogError(f"{where}.candidates: duplicate name")
        if len({provider(name) for name in candidates}) < 2:
            raise CatalogError(f"{where}.candidates: needs at least two providers")
        normalized[tier] = list(candidates)
    _check_backups_never_weaker(normalized)
    return {
        "schema": value["schema"],
        "verified_against": value["verified_against"],
        "tiers": normalized,
    }


def _check_backups_never_weaker(tiers: Mapping[str, Sequence[str]]) -> None:
    """Reject a backup whose family leads only tiers weaker than the backup's tier.

    Other levels of a tier's own first family pass (plans report them as
    step-downs). A family that leads no tier has no declared strength to
    compare, so it passes too.
    """
    led: dict[str, int] = {}
    for tier in TIERS:
        lead = family(tiers[tier][0])
        led[lead] = max(led.get(lead, 0), STRENGTH[tier])
    for tier in TIERS:
        for name in tiers[tier][1:]:
            strength = led.get(family(name))
            if strength is not None and strength < STRENGTH[tier]:
                raise CatalogError(
                    f"catalog.tiers.{tier}.candidates: backup {name!r} is weaker "
                    f"than the {tier} tier; its family leads only weaker tiers"
                )


def parse_runtime_models(value: Any) -> frozenset[str]:
    """Validate the live list of concrete model names."""
    if not isinstance(value, list) or not value:
        raise CatalogError("runtime-models: expected a non-empty JSON array")
    if any(not isinstance(name, str) or not name for name in value):
        raise CatalogError("runtime-models: expected non-empty strings")
    if "inherit" in value:
        raise CatalogError("runtime-models: 'inherit' is not a concrete model")
    return frozenset(value)


def resolve_tiers(
    checked: Mapping[str, Any], live: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """First live candidate per tier; a fallback leaves the first candidate's family."""
    live_set = frozenset(live)
    routes = {}
    for tier in TIERS:
        candidates = checked["tiers"][tier]
        model = next((name for name in candidates if name in live_set), None)
        routes[tier] = {
            "model": model,
            "first": candidates[0],
            "fallback": model is None or family(model) != family(candidates[0]),
        }
    return routes


def _load_runtime_models(source: str) -> frozenset[str]:
    try:
        raw = (
            Path(source[1:]).read_text(encoding="utf-8")
            if source.startswith("@")
            else source
        )
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"runtime-models: {exc}") from exc
    return parse_runtime_models(value)


def _lead(names: Sequence[str], author: str | None) -> str:
    """The first name, preferring one whose provider is not the author's."""
    return next((name for name in names if provider(name) != author), names[0])


def plan_launch(
    checked: Mapping[str, Any],
    live: Iterable[str],
    work_kind: str,
    *,
    tier: str | None = None,
    raise_reason: str | None = None,
    author_provider: str | None = None,
    subagent_type: str | None = None,
) -> dict[str, Any]:
    """The models to launch for one kind of work, their order, and the warnings."""
    if work_kind not in WORK_KINDS:
        raise PlanError(f"work kind: expected one of {', '.join(WORK_KINDS)}")
    base = WORK_KINDS[work_kind][0]
    if tier is None:
        if raise_reason is not None:
            raise PlanError("--raise-reason needs --tier")
        tier = base
    elif tier not in STRENGTH:
        raise PlanError(f"tier: expected one of {', '.join(TIERS)}")
    elif STRENGTH[tier] <= STRENGTH[base]:
        raise PlanError(
            f"--tier {tier} is not stronger than {base}, the {work_kind} tier; "
            "a tier can only be raised"
        )
    elif not (raise_reason or "").strip():
        raise PlanError("--tier needs --raise-reason")
    author = None
    if work_kind in REVIEW_KINDS:
        if author_provider is None:
            raise PlanError(
                f"{work_kind} needs --author-provider (none when a human did the work)"
            )
        if author_provider != "none":
            if not PROVIDER_RE.match(author_provider):
                raise PlanError(
                    "--author-provider: expected a provider (a model name before "
                    "its first hyphen) or none"
                )
            author = author_provider

    candidates = checked["tiers"][tier]
    live_set = frozenset(live)
    offered = [name for name in candidates if name in live_set]
    if not offered:
        raise PlanError(
            f"no {tier} candidate is on the live list; launch nothing for this "
            "tier, report it, and update model-tiers.json from the live list"
        )
    primary = _lead(offered, author)
    secondary = next((n for n in offered if provider(n) != provider(primary)), None)
    ideal = _lead(candidates, author)

    warnings = []
    if tier != base:
        reason = raise_reason.strip()
        warnings.append(
            ("raised", f"{work_kind} work raised from {base} to {tier}: {reason}")
        )
    if family(primary) != family(ideal):
        warnings.append((
            "fallback",
            f"{primary} stands in for {ideal}, the {tier} tier's choice when every "
            "candidate is offered; report this fallback",
        ))
    for name in (primary, secondary):
        if name is None:
            continue
        first = next(c for c in candidates if family(c) == family(name))
        if name != first:
            warnings.append((
                "step-down",
                f"{name} is a lower effort level than {first}, the {tier} tier's "
                "first choice in its family; the operator's picker level is below "
                "the catalog's first choice",
            ))
        if provider(name) == author:
            warnings.append((
                "not-independent",
                f"{name} shares the author's provider ({author}), so a review on it "
                "is not independent",
            ))

    pinned = None
    if subagent_type is not None and subagent_type.lower() in PINNED_SUBAGENT_TYPES:
        kind = subagent_type.lower()
        pinned = {
            "subagent_type": kind,
            "note": (
                f"Cursor chooses {kind}'s model and ignores --model, so it cannot "
                f"satisfy the {tier} tier or a different-provider review requirement "
                "and never counts as this tier's review; if its launch is rejected, "
                "launch generalPurpose with this plan"
            ),
        }

    order = [("primary", primary)] + ([("secondary", secondary)] if secondary else [])
    launches = [{"action": "launch", "role": r, "model": m} for r, m in order]
    attempts = launches + [{"action": "wait", "seconds": RETRY_WAIT_SECONDS}]
    attempts += [dict(step) for step in launches] + [{"action": "fatal"}]
    return {
        "tier": tier,
        "work_kind": work_kind,
        "primary": primary,
        "secondary": secondary,
        "attempts": attempts,
        "warnings": [{"kind": kind, "message": text} for kind, text in warnings],
        "pinned": pinned,
    }


def _plan_lines(plan: Mapping[str, Any]) -> list[str]:
    lines = [
        f"model-tier-plan: OK ({plan['work_kind']} work on the {plan['tier']} tier)"
    ]
    if plan["pinned"]:
        lines.append(f"  pinned: {plan['pinned']['note']}")
    lines.append(f"  primary: {plan['primary']}")
    if plan["secondary"]:
        lines.append(
            f"  secondary: {plan['secondary']} "
            "(a launch that runs on it is a fallback; report it)"
        )
    else:
        lines.append("  secondary: none (no other provider is offered)")
    lines.append(
        "  try in order, moving on only when a launch is rejected before the "
        "subagent starts:"
    )
    for number, step in enumerate(plan["attempts"], 1):
        if step["action"] == "launch":
            text = f"launch {step['model']}"
        elif step["action"] == "wait":
            text = f"wait {step['seconds']} seconds"
        else:
            text = "FATAL: launch nothing more for this tier; stop and report"
        lines.append(f"    {number}. {text}")
    lines.extend(f"WARN  {w['kind']}: {w['message']}" for w in plan["warnings"])
    return lines


def _plan_main(args: argparse.Namespace) -> int:
    stream = sys.stderr if args.json else sys.stdout
    try:
        plan = plan_launch(
            validate_catalog(load_catalog(args.catalog)),
            _load_runtime_models(args.runtime_models),
            args.work_kind,
            tier=args.tier,
            raise_reason=args.raise_reason,
            author_provider=args.author_provider,
            subagent_type=args.subagent_type,
        )
    except (CatalogError, PlanError) as exc:
        print(f"model-tier-plan: FAIL: {exc}", file=stream)
        return 1
    if not args.json:
        print("\n".join(_plan_lines(plan)))
        return 0
    print(json.dumps(plan, indent=2))
    for warning in plan["warnings"]:
        print(f"WARN  {warning['kind']}: {warning['message']}", file=sys.stderr)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("model-tiers.json"),
    )
    parser.add_argument(
        "--runtime-models",
        help="live concrete model names as a JSON array or @path",
    )
    commands = parser.add_subparsers(dest="command")
    plan = commands.add_parser(
        "plan",
        help="name the models to launch for one kind of work",
        description=(
            "Name the models to launch for one kind of work and the order to try\n"
            "them in. Exit 0 is a launchable plan; exit 1 means launch nothing,\n"
            "for the reason printed; exit 2 is a usage error."
        ),
        epilog="work kinds (tier: what they cover):\n" + "\n".join(
            f"  {kind:<9}{tier}: {covers}"
            for kind, (tier, covers) in WORK_KINDS.items()
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    plan.add_argument("--catalog", type=Path, default=argparse.SUPPRESS)
    plan.add_argument("--work-kind", required=True, choices=list(WORK_KINDS))
    plan.add_argument(
        "--runtime-models",
        required=True,
        help="model names the subagent tool offers this session (not inherit), "
        "as a JSON array or @path",
    )
    plan.add_argument(
        "--tier",
        choices=TIERS,
        help="raise to a stronger tier than the work kind's; needs --raise-reason",
    )
    plan.add_argument("--raise-reason", help="why this work needs the stronger tier")
    plan.add_argument(
        "--author-provider",
        help="provider of the model that did the work under review (its name "
        "before the first hyphen), or none for a human; required for review and "
        "sign-off, no effect on other work kinds",
    )
    plan.add_argument(
        "--subagent-type",
        help="subagent type to launch; Cursor picks the model of pinned types ("
        + ", ".join(sorted(PINNED_SUBAGENT_TYPES))
        + "), so the plan says so and gives the generalPurpose plan; other types "
        "do not change the plan",
    )
    plan.add_argument(
        "--json",
        action="store_true",
        help="print one JSON object; warnings also go to stderr",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        return _plan_main(args)
    try:
        checked = validate_catalog(load_catalog(args.catalog))
        live = (
            None
            if args.runtime_models is None
            else _load_runtime_models(args.runtime_models)
        )
    except CatalogError as exc:
        print(f"model-tier-catalog: FAIL: {exc}")
        return 1
    slots = sum(len(names) for names in checked["tiers"].values())
    checked_on = checked["verified_against"][len(REVISION_PREFIX):]
    print(
        f"model-tier-catalog: OK ({len(TIERS)} tiers, {slots} candidate slots; "
        f"last checked against the live list {checked_on})"
    )
    if live is None:
        return 0
    status = 0
    for tier, route in resolve_tiers(checked, live).items():
        if route["model"] is None:
            print(
                f"FAIL  {tier}: no candidate is on the live list; launch nothing "
                "for this role and update model-tiers.json from the live list"
            )
            status = 1
            continue
        print(f"  {tier}: {route['model']}")
        if route["fallback"]:
            print(
                f"WARN  {tier}: fallback from {route['first']} to {route['model']}; "
                "report it and update model-tiers.json from the live list"
            )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
