#!/usr/bin/env python3
"""Tiny CLI façade for the proportional swarm helper.

Exposes the deterministic verbs — `fingerprint`, `size`, `risk`,
`validate-finding`, `budget`, `account`, `render` — plus the just-in-time
decision verbs the orchestrator queries instead
of pre-loading doctrine prose: `route-probe`, `route`, `gate-verifier`,
`gate-second-pass`, and `plan`. Every verb is a thin wrapper over a pure function
in `swarm_helper`. This is the sole script entry point; the retired 16-module
engine and its contract adapter are gone.

Every verb accepts inline JSON, `@path`, or `-` (stdin) where a document is
required, prints JSON to stdout on success, and exits non-zero with a
`swarm: <message>` diagnostic on any validation failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import swarm_helper as helper


def _load_json(source: str) -> Any:
    if source == "-":
        return json.loads(sys.stdin.read())
    if source.startswith("@"):
        return json.loads(Path(source[1:]).read_text(encoding="utf-8"))
    return json.loads(source)


def _runtime_models(source: str) -> frozenset[str]:
    value = _load_json(source)
    if not isinstance(value, list):
        raise helper.ContractError("runtime-models: expected a JSON array")
    return helper._runtime_model_set(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Proportional swarm helper")
    sub = parser.add_subparsers(dest="command", required=True)

    risk = sub.add_parser("risk", help="weighted risk score + priority from four 1..5 factors")
    for name in ("impact", "likelihood", "exposure", "irreversibility"):
        risk.add_argument(f"--{name}", type=int, required=True)
    risk.add_argument("--unsafe-to-ship", action="store_true")

    size = sub.add_parser("size", help="probe JSON -> band + cohort plan")
    size.add_argument("probe", help="probe JSON, @path, or - for stdin")

    validate = sub.add_parser("validate-finding", help="validate a lean finding, or a full reviewer return")
    validate.add_argument("finding", help="finding JSON, @path, or - for stdin")
    validate.add_argument("--reviewer-return", action="store_true",
                         help="validate a full conformed reviewer/verifier return (<=6 findings, <=16 KiB)")
    validate.add_argument(
        "--expected-candidate-ids",
        help="authoritative parent-supplied JSON array (required for verifier returns)",
    )
    validate.add_argument(
        "--authorized-accepted-risk-ids",
        help="authoritative parent-supplied JSON array (required for verifier returns; use [])",
    )
    validate.add_argument(
        "--expected-candidate-id",
        help="authoritative exact-byte candidate id (required for full returns)",
    )
    validate.add_argument(
        "--expected-assignment-id",
        help="authoritative assignment id (required for full returns)",
    )
    validate.add_argument(
        "--coverage-state",
        help="authoritative parent-observed coverage JSON (required for verifier returns)",
    )

    budget = sub.add_parser("budget", help="validate accepted workers against the §5 ceilings")
    budget.add_argument("plan", help='{"band": <band>, "events": [...]} as JSON, @path, or -')

    account = sub.add_parser(
        "account",
        help="replay resolution, transport, acceptance, and completion accounting",
    )
    account.add_argument(
        "run",
        help='{"band": <band>, "window": {...}, "events": [...]} as JSON, @path, or -',
    )

    render = sub.add_parser("render", help="curated operator report from a result object")
    render.add_argument("result", help="result JSON, @path, or - for stdin")

    fingerprint = sub.add_parser(
        "fingerprint",
        help="exact revision + in-scope file bytes -> candidate identity",
    )
    fingerprint.add_argument("--root", default=".")
    fingerprint.add_argument("--revision", required=True)
    fingerprint.add_argument("paths", nargs="+")

    route_probe = sub.add_parser("route-probe", help="pre-probe facts -> probe model slug + rigor")
    route_probe.add_argument("--roots", type=int, required=True)
    route_probe.add_argument("--files-changed", type=int, required=True)
    route_probe.add_argument("--lines-changed", type=int, required=True)
    route_probe.add_argument("--protected-paths", action="store_true")
    route_probe.add_argument(
        "--runtime-models",
        required=True,
        help="live concrete Cursor enum as a JSON array or @path",
    )

    route = sub.add_parser("route", help="role + severity -> model slug + rigor")
    route.add_argument("--role", choices=["reviewer", "verifier"], required=True)
    route.add_argument("--score", type=int, help="driving dimension score 0..100 (reviewer role)")
    route.add_argument("--priority", help="gate priority P0..P4 (verifier role)")
    route.add_argument(
        "--runtime-models",
        required=True,
        help="live concrete Cursor enum as a JSON array or @path",
    )

    gate_verifier = sub.add_parser("gate-verifier", help="findings -> run a verifier? (§7 gate)")
    gate_verifier.add_argument("findings", help="findings JSON array (or reviewer return), @path, or -")
    gate_verifier.add_argument("--critical-change", action="store_true")
    gate_verifier.add_argument("--clearance-request", action="store_true")

    gate_second_pass = sub.add_parser("gate-second-pass", help="state -> allow a second pass? (§8 gate)")
    gate_second_pass.add_argument("state", help="state JSON, @path, or - for stdin")

    plan = sub.add_parser("plan", help="probe JSON -> band + cohort + charter ids + slugs + budget")
    plan.add_argument("probe", help="probe JSON, @path, or - for stdin")
    plan.add_argument(
        "--runtime-models",
        required=True,
        help="live concrete Cursor enum as a JSON array or @path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "risk":
            score = helper.calculate_risk(args.impact, args.likelihood, args.exposure, args.irreversibility)
            result: Any = {"risk_score": score, "priority": helper.priority_for(score, args.unsafe_to_ship)}
        elif args.command == "size":
            result = helper.size_cohort(_load_json(args.probe))
        elif args.command == "validate-finding":
            payload = _load_json(args.finding)
            if args.reviewer_return:
                expected = (
                    _load_json(args.expected_candidate_ids)
                    if args.expected_candidate_ids is not None
                    else None
                )
                authorized = (
                    _load_json(args.authorized_accepted_risk_ids)
                    if args.authorized_accepted_risk_ids is not None
                    else None
                )
                coverage_state = (
                    _load_json(args.coverage_state)
                    if args.coverage_state is not None
                    else None
                )
                result = helper.validate_reviewer_return(
                    payload,
                    expected_candidate_id=args.expected_candidate_id,
                    expected_assignment_id=args.expected_assignment_id,
                    expected_candidate_ids=expected,
                    authorized_accepted_risk_ids=authorized,
                    coverage_state=coverage_state,
                )
            else:
                if (
                    args.expected_candidate_ids is not None
                    or args.authorized_accepted_risk_ids is not None
                    or args.expected_candidate_id is not None
                    or args.expected_assignment_id is not None
                    or args.coverage_state is not None
                ):
                    raise helper.ContractError(
                        "return binding/scope/authority arguments require --reviewer-return"
                    )
                result = helper.validate_finding(payload)
        elif args.command == "budget":
            plan = _load_json(args.plan)
            if not isinstance(plan, dict) or "band" not in plan:
                raise helper.ContractError("budget: expected an object with 'band' and 'events'")
            result = helper.evaluate_budget(plan["band"], plan.get("events", []))
        elif args.command == "account":
            run = _load_json(args.run)
            if not isinstance(run, dict) or "band" not in run:
                raise helper.ContractError(
                    "account: expected an object with 'band', 'window', and 'events'"
                )
            result = helper.evaluate_accounting(
                run["band"], run.get("window", {}), run.get("events", [])
            )
        elif args.command == "render":
            sys.stdout.write(helper.render_report(_load_json(args.result)))
            return 0
        elif args.command == "fingerprint":
            result = helper.fingerprint_candidate(
                args.root, args.revision, args.paths
            )
        elif args.command == "route-probe":
            route = helper.route_probe(
                roots=args.roots, files_changed=args.files_changed,
                lines_changed=args.lines_changed, protected_paths=args.protected_paths,
                runtime_models=_runtime_models(args.runtime_models),
            )
            result = {
                "model_class": route["model_class"],
                "slug": route["slug"],
                "rigor": route["rigor"],
                "fallbacks": route["fallbacks"],
                "filtered_models": route["filtered_out"],
            }
        elif args.command == "route":
            runtime_models = _runtime_models(args.runtime_models)
            if args.role == "reviewer":
                if args.score is None:
                    raise helper.ContractError("route --role reviewer requires --score")
                route = helper.route_reviewer(
                    score=args.score, runtime_models=runtime_models
                )
            else:  # verifier
                if args.priority is None:
                    raise helper.ContractError("route --role verifier requires --priority")
                route = helper.route_verifier(
                    priority=args.priority, runtime_models=runtime_models
                )
            result = {
                "model_class": route["model_class"],
                "slug": route["slug"],
                "rigor": route["rigor"],
                "fallbacks": route["fallbacks"],
                "filtered_models": route["filtered_out"],
            }
        elif args.command == "gate-verifier":
            result = helper.gate_verifier(
                _load_json(args.findings),
                critical_change=args.critical_change,
                clearance_request=args.clearance_request,
            )
        elif args.command == "gate-second-pass":
            result = helper.gate_second_pass(_load_json(args.state))
        elif args.command == "plan":
            result = helper.plan_run(
                _load_json(args.probe),
                runtime_models=_runtime_models(args.runtime_models),
            )
        else:  # pragma: no cover - argparse enforces the verb set
            raise helper.ContractError(f"unsupported command {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (helper.ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"swarm: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
