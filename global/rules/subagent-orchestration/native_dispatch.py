#!/usr/bin/env python3
"""Opt-in native model planning. Pure JSON in/out; never launches or installs.

The legacy Cursor entrypoint stays active. This module reads its ordered policy,
but uses explicit identities and native bindings, never slug decomposition.
Evidence is supplied by the caller observing the current native tool. It is not
authentication or authorization, and a plan is not proof of execution identity.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

VERSION = "native-dispatch/v1"
ROOT = Path(__file__).resolve().parent
KINDS = {"find": "economy", "run": "economy", "build": "standard",
         "review": "standard", "design": "deep", "sign-off": "critical"}
STRENGTH = {"economy": 1, "standard": 2, "deep": 3, "critical": 3}
TOOLS = {"codex": "collaboration.spawn_agent", "cursor": "Task"}
SURFACES = {"codex": "local-macos-desktop", "cursor": "local-macos-agents"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
MAX_AGE_SECONDS = 900
WAIT_SECONDS = 60


class Unavailable(ValueError):
    """Fail closed with no executable request."""


def closed(obj, keys, where):
    if not isinstance(obj, dict) or set(obj) != set(keys.split()):
        raise Unavailable(where + ": invalid fields")


def label(value, where):
    if not isinstance(value, str) or not value or len(value) > 200:
        raise Unavailable(where + ": invalid identifier")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise Unavailable("duplicate JSON key")
            obj[key] = value
        return obj
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def source_digest(policy, bindings):
    return digest({"policy": policy, "bindings": bindings,
                   "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def request_digest(request):
    stable = copy.deepcopy(request)
    # A not-offered rejection requires observing a new list without resetting
    # the task's rejected-launch budget. All other context remains bound.
    stable["context"].pop("contract_sha256", None)
    return digest(stable)


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError):
        raise Unavailable("UTC timestamp required") from None


def choice_key(choice):
    return choice["provider"], choice["family"]


def validate_sources(policy, bindings):
    closed(policy, "schema verified_against tiers", "policy")
    if policy["schema"] != "cursor-model-tiers/v2":
        raise Unavailable("unknown policy schema")
    if not isinstance(policy["tiers"], dict) or set(policy["tiers"]) != set(STRENGTH):
        raise Unavailable("invalid tiers")
    closed(bindings, "schema choices override_models", "bindings")
    if bindings["schema"] != "native-model-bindings/v1":
        raise Unavailable("unknown bindings schema")
    if not isinstance(bindings["choices"], dict):
        raise Unavailable("invalid choices")
    native_identities = {}

    def bind(host, model, choice, mode):
        if model is None:
            return
        identity = (*choice_key(choice), mode, choice["fixed_behavior"])
        if host == "cursor":
            identity += (choice.get("effort"),)
        key = host, model
        if key in native_identities and native_identities[key] != identity:
            raise Unavailable("contradictory native token identity")
        native_identities[key] = identity
    for identity, choice in bindings["choices"].items():
        label(identity, "choice")
        closed(choice, "provider family effort fixed_behavior models", "choice")
        label(choice["provider"], "provider")
        label(choice["family"], "family")
        validate_behavior(choice)
        if not isinstance(choice["models"], dict) or set(choice["models"]) != set(TOOLS):
            raise Unavailable("invalid host mappings")
        for host, model in choice["models"].items():
            if model is not None:
                label(model, "model")
                bind(host, model, choice, "effort" if choice["effort"] is not None else "fixed")
    leads = {}
    for tier, spec in policy["tiers"].items():
        closed(spec, "candidates", "tier")
        names = spec["candidates"]
        if not isinstance(names, list) or not names or any(
                not isinstance(n, str) or n not in bindings["choices"] for n in names):
            raise Unavailable("unknown candidate identity")
        if len(names) != len(set(names)):
            raise Unavailable("duplicate candidate")
        choices = [bindings["choices"][n] for n in names]
        if len({c["provider"] for c in choices}) < 2:
            raise Unavailable("tier requires two explicit providers")
        key = choice_key(choices[0])
        leads[key] = max(leads.get(key, 0), STRENGTH[tier])
    for tier, spec in policy["tiers"].items():
        for name in spec["candidates"][1:]:
            strength = leads.get(choice_key(bindings["choices"][name]))
            if strength is not None and strength < STRENGTH[tier]:
                raise Unavailable("weaker backup family")
    if not isinstance(bindings["override_models"], dict) or set(bindings["override_models"]) != set(TOOLS):
        raise Unavailable("invalid override hosts")
    for host, rows in bindings["override_models"].items():
        if not isinstance(rows, list):
            raise Unavailable("invalid override bindings")
        if host == "cursor" and rows:
            raise Unavailable("Cursor overrides require an exact choice binding")
        keys = set()
        for row in rows:
            closed(row, "provider family model mode fixed_behavior", "override binding")
            for field in ("provider", "family", "model"):
                label(row[field], field)
            if choice_key(row) in keys:
                raise Unavailable("ambiguous override family")
            keys.add(choice_key(row))
            if row["mode"] not in {"effort", "fixed"}:
                raise Unavailable("invalid override mode")
            if row["mode"] == "effort" and row["fixed_behavior"] is not None:
                raise Unavailable("fictional fixed behavior")
            if row["mode"] == "fixed":
                label(row["fixed_behavior"], "fixed behavior")
            bind(host, row["model"], row, row["mode"])


def validate_behavior(choice):
    if choice["effort"] is None:
        label(choice["fixed_behavior"], "fixed behavior")
    elif choice["effort"] not in EFFORTS or choice["fixed_behavior"] is not None:
        raise Unavailable("invalid effort or fixed behavior")


def validate_evidence(evidence, context, expected_source, now):
    closed(context, "host surface session_id contract_sha256 host_build", "context")
    host = context["host"]
    if host not in TOOLS or context["surface"] != SURFACES[host]:
        raise Unavailable("unsupported host/surface")
    for field in ("session_id", "contract_sha256"):
        label(context[field], field)
    closed(evidence, "schema host surface session_id contract_sha256 tool origin observed_at host_build source_sha256 models", "evidence")
    if evidence["schema"] != "native-offers/v1" or evidence["origin"] != "native-tool":
        raise Unavailable("current native tool evidence required")
    if any(evidence[k] != v for k, v in context.items()) or evidence["tool"] != TOOLS[host]:
        raise Unavailable("evidence context mismatch")
    if evidence["source_sha256"] != expected_source:
        raise Unavailable("source or adapter changed")
    age = now - timestamp(evidence["observed_at"])
    if age < 0 or age > MAX_AGE_SECONDS:
        raise Unavailable("native evidence absent or stale")
    if evidence["host_build"] is not None:
        label(evidence["host_build"], "host build")
    models = evidence["models"]
    if not isinstance(models, list) or not models:
        raise Unavailable("native offered models absent")
    seen = set()
    for row in models:
        closed(row, "model efforts fixed_behavior", "native model")
        label(row["model"], "native model")
        if row["model"] in seen or row["model"] == "inherit":
            raise Unavailable("duplicate or inherited model")
        seen.add(row["model"])
        efforts = row["efforts"]
        if efforts is not None and (not isinstance(efforts, list) or not efforts or
                any(not isinstance(e, str) or e not in EFFORTS for e in efforts) or
                len(efforts) != len(set(efforts))):
            raise Unavailable("unknown effort support")
        if efforts is not None and row["fixed_behavior"] is not None:
            raise Unavailable("ambiguous native behavior")
        if host == "cursor" and (efforts is not None or row["fixed_behavior"] is not None):
            raise Unavailable("Cursor evidence offers opaque tokens, not separate behavior")
        if host == "codex" and efforts is None:
            label(row["fixed_behavior"], "native fixed behavior")
    if digest(models) != context["contract_sha256"]:
        raise Unavailable("offered contract digest mismatch")


def encode(choice, host, evidence):
    """Encode only after the explicit family and its attributes were selected."""
    model = choice["models"][host]
    row = next((r for r in evidence["models"] if r["model"] == model), None)
    if row is None:
        return None
    if host == "cursor":
        # Cursor's opaque offered slug embodies the picker choice. No effort arg.
        return {"model": model}
    if choice["effort"] is not None:
        if row["efforts"] is None or choice["effort"] not in row["efforts"]:
            return None
        return {"model": model, "reasoning_effort": choice["effort"], "fork_turns": "none"}
    if row["efforts"] is not None or row["fixed_behavior"] != choice["fixed_behavior"]:
        return None
    return {"model": model, "fork_turns": "none"}


def forced_choice(selection, host, bindings):
    closed(selection, "provider family effort fixed_behavior", "forced selection")
    for field in ("provider", "family"):
        label(selection[field], field)
    validate_behavior(selection)
    exact = [c for c in bindings["choices"].values() if all(c[k] == v for k, v in selection.items())]
    if exact:
        return exact[0]
    # A separate-effort host can encode a forced attribute for a known family.
    # Cursor still needs an exact explicit opaque binding for its picker level.
    if host == "codex":
        matches = [c for c in bindings["choices"].values()
                   if choice_key(c) == choice_key(selection) and c["models"][host]
                   and (c["effort"] is None) == (selection["effort"] is None)]
        models = {c["models"][host] for c in matches}
        if len(models) == 1 and selection["effort"] is not None:
            return {**selection, "models": {h: next(iter(models)) if h == host else None for h in TOOLS}}
    rows = [r for r in bindings["override_models"][host] if choice_key(r) == choice_key(selection)]
    if len(rows) != 1:
        raise Unavailable("unknown forced family/behavior")
    row = rows[0]
    if ((row["mode"] == "effort") != (selection["effort"] is not None) or
            row["fixed_behavior"] != selection["fixed_behavior"]):
        raise Unavailable("unsupported forced behavior")
    return {**selection, "models": {h: row["model"] if h == host else None for h in TOOLS}}


def unavailable(reason):
    return {"schema": VERSION, "status": "unavailable", "reason": reason,
            "dispatch": None, "acknowledged": None}


def resolve(request, evidence, policy, bindings, *, now=None, continuation=None):
    """Plan one launch. A continuation retains the bounded rejected-launch budget."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    try:
        return _resolve(request, evidence, policy, bindings, now, continuation)
    except (Unavailable, TypeError, KeyError) as exc:
        return unavailable(str(exc))


def _resolve(request, evidence, policy, bindings, now, continuation):
    closed(request, "context work_kind difficulty tier raise_reason mode selection author_provider require_different_provider", "request")
    if request["mode"] not in {"auto", "force", "off"}:
        raise Unavailable("unknown routing mode")
    if request["mode"] == "off":
        raise Unavailable("routing explicitly off")
    validate_sources(policy, bindings)
    validate_evidence(evidence, request["context"], source_digest(policy, bindings), now)
    host = request["context"]["host"]
    kind, difficulty = request["work_kind"], request["difficulty"]
    if kind not in KINDS or difficulty not in {"normal", "raised"}:
        raise Unavailable("unknown work classification/difficulty")
    base = KINDS[kind]
    tier = base
    warnings = []
    if difficulty == "raised":
        tier = request["tier"]
        if tier not in STRENGTH or STRENGTH[tier] <= STRENGTH[base]:
            raise Unavailable("tier can only be raised")
        label(request["raise_reason"], "raise reason")
        warnings.append("raised")
    elif request["tier"] is not None or request["raise_reason"] is not None:
        raise Unavailable("normal difficulty cannot override tier")
    if not isinstance(request["require_different_provider"], bool):
        raise Unavailable("invalid review requirement")
    author = request["author_provider"]
    if kind in {"review", "sign-off"}:
        label(author, "author provider (use none for human, unknown if unavailable)")
        providers = {c["provider"] for c in bindings["choices"].values()}
        providers.update(row["provider"] for rows in bindings["override_models"].values() for row in rows)
        if author not in providers | {"none", "unknown"}:
            raise Unavailable("unrecognized author provider; use canonical identity or unknown")
    elif author is not None or request["require_different_provider"]:
        raise Unavailable("review fields on non-review work")
    names = policy["tiers"][tier]["candidates"]
    choices = [bindings["choices"][n] for n in names]
    if request["mode"] == "force":
        choices = [forced_choice(request["selection"], host, bindings)]
        names = ["explicit-override"]
        warnings.append("explicit-override")
    elif request["selection"] is not None:
        raise Unavailable("selection requires force mode")
    if author not in {None, "none", "unknown"}:
        # Stable partition keeps catalog family/attribute preference within each group.
        pairs = list(zip(names, choices))
        pairs.sort(key=lambda p: p[1]["provider"] == author)
        names, choices = map(list, zip(*pairs))
    ideal = choices[0]
    eligible = []
    for identity, choice in zip(names, choices):
        dispatch = encode(choice, host, evidence)
        if dispatch is not None:
            eligible.append({"identity": identity, "choice": copy.deepcopy(choice), "dispatch": dispatch})
    if request["require_different_provider"]:
        if author in {None, "unknown"}:
            raise Unavailable("author provider unknown")
        eligible = [e for e in eligible if e["choice"]["provider"] != author]
    if not eligible:
        raise Unavailable("forced choice unavailable" if request["mode"] == "force" else "no policy candidate offered with supported behavior")
    primary = eligible[0]
    secondary = next((e for e in eligible if e["choice"]["provider"] != primary["choice"]["provider"]), None)
    pool = [primary] + ([secondary] if secondary else [])
    pool_sha256 = digest(pool)
    used, limit, retry_at, slot = 0, len(pool) * 2, None, 0
    if continuation is not None:
        closed(continuation, "schema request_sha256 source_sha256 used limit retry_at previous_evidence refresh_required pool_sha256 next_slot", "continuation")
        if (continuation["schema"] != "native-retry/v1" or
                continuation["request_sha256"] != request_digest(request) or
                continuation["source_sha256"] != evidence["source_sha256"]):
            raise Unavailable("retry context changed")
        used, limit, retry_at = continuation["used"], continuation["limit"], continuation["retry_at"]
        if type(used) is not int or type(limit) is not int or not 0 < used <= limit <= 4 or limit not in {2, 4}:
            raise Unavailable("invalid retry budget")
        if type(continuation["refresh_required"]) is not bool:
            raise Unavailable("invalid refresh flag")
        for key in ("previous_evidence", "pool_sha256"):
            if not isinstance(continuation[key], str) or not re.fullmatch("[0-9a-f]{64}", continuation[key]):
                raise Unavailable("invalid retry digest")
        if type(continuation["next_slot"]) is not int or continuation["next_slot"] not in {0, 1}:
            raise Unavailable("invalid retry slot")
        if used == limit // 2 and retry_at is None:
            raise Unavailable("mandatory retry wait missing")
        if retry_at is not None:
            timestamp(retry_at)
        # Replan changed offerings from the first remaining policy preference;
        # the consumed budget stays fixed, so refresh never grants more attempts.
        if continuation["pool_sha256"] == pool_sha256:
            slot = continuation["next_slot"] % len(pool)
        if continuation["refresh_required"] and continuation["previous_evidence"] == digest(evidence):
            raise Unavailable("native not-offered rejection requires fresh evidence")
    if used >= limit:
        raise Unavailable("bounded fallback exhausted")
    if retry_at is not None and now < timestamp(retry_at):
        return {"schema": VERSION, "status": "waiting", "dispatch": None,
                "retry_at": retry_at, "continuation": continuation, "acknowledged": None}
    selected = pool[slot]
    choice = selected["choice"]
    if choice_key(choice) != choice_key(ideal):
        warnings.append("fallback")
    family_first = next((c for c in choices if choice_key(c) == choice_key(choice)), choice)
    if choice != family_first:
        warnings.append("step-down")
    if author == choice["provider"]:
        warnings.append("same-provider-review")
    if author == "unknown":
        warnings.append("review-provider-unverified")
    return {"schema": VERSION, "status": "ready", "dispatch": selected["dispatch"],
            "requested": {k: choice[k] for k in ("provider", "family", "effort", "fixed_behavior")},
            "acknowledged": None, "work_kind": kind, "difficulty": difficulty, "tier": tier,
            "warnings": warnings, "context": copy.deepcopy(request["context"]),
            "request_sha256": request_digest(request), "source_sha256": evidence["source_sha256"],
            "evidence_sha256": digest(evidence), "used": used, "limit": limit,
            "pool_sha256": pool_sha256, "slot": slot,
            "host_build": evidence["host_build"], "worker_id": None,
            "limitations": ["execution-identity-unverified"] + (["host-build-unavailable"] if evidence["host_build"] is None else [])}


def validate_observation_plan(plan):
    keys = ("schema status dispatch requested acknowledged work_kind difficulty tier warnings context "
            "request_sha256 source_sha256 evidence_sha256 used limit pool_sha256 slot host_build worker_id limitations")
    if not isinstance(plan, dict) or plan.get("status") not in {"ready", "running"}:
        raise Unavailable("invalid lifecycle transition; never re-route a started worker")
    if plan["status"] == "running":
        keys += " execution_matches_request"
    closed(plan, keys, "observation plan")
    if plan["schema"] != VERSION:
        raise Unavailable("invalid plan schema")
    closed(plan["context"], "host surface session_id contract_sha256 host_build", "plan context")
    host = plan["context"]["host"]
    if host not in TOOLS or plan["context"]["surface"] != SURFACES[host]:
        raise Unavailable("invalid plan host")
    closed(plan["requested"], "provider family effort fixed_behavior", "requested identity")
    validate_behavior(plan["requested"])
    for key in ("provider", "family"):
        label(plan["requested"][key], key)
    for key in ("request_sha256", "source_sha256", "evidence_sha256", "pool_sha256"):
        if not isinstance(plan[key], str) or not re.fullmatch("[0-9a-f]{64}", plan[key]):
            raise Unavailable("invalid plan digest")
    if (type(plan["used"]) is not int or type(plan["limit"]) is not int
            or plan["limit"] not in {2, 4} or not 0 <= plan["used"] < plan["limit"]
            or type(plan["slot"]) is not int or plan["slot"] not in {0, 1}):
        raise Unavailable("invalid plan budget/slot")
    if plan["status"] == "ready":
        dispatch_keys = "model"
        if host == "codex":
            dispatch_keys += " fork_turns"
            if plan["requested"]["effort"] is not None:
                dispatch_keys += " reasoning_effort"
        closed(plan["dispatch"], dispatch_keys, "native dispatch")
        label(plan["dispatch"]["model"], "model")
        if host == "codex" and (plan["dispatch"]["fork_turns"] != "none" or
                plan["dispatch"].get("reasoning_effort") != plan["requested"]["effort"]):
            raise Unavailable("native dispatch differs from requested behavior")
        if plan["worker_id"] is not None or plan["acknowledged"] is not None:
            raise Unavailable("ready plan cannot claim a worker")
    else:
        label(plan["worker_id"], "started worker handle")
        if plan["dispatch"] is not None:
            raise Unavailable("started worker cannot have pending dispatch")
        if plan["execution_matches_request"] is not None and type(plan["execution_matches_request"]) is not bool:
            raise Unavailable("invalid execution identity state")


def observe(plan, event, *, now=None, worker_id=None, acknowledged=None):
    try:
        validate_observation_plan(plan)
        return _observe(plan, event, now=now, worker_id=worker_id, acknowledged=acknowledged)
    except (Unavailable, TypeError, KeyError, ValueError) as exc:
        return unavailable(str(exc))


def _observe(plan, event, *, now=None, worker_id=None, acknowledged=None):
    """Record native feedback without pretending requested identity was acknowledged.

    Only model availability/transport rejection permits bounded replanning. An
    invalid request needs caller repair; a started failure never switches models.
    """
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    result = copy.deepcopy(plan)
    result["dispatch"] = None
    if event != "started" and (worker_id is not None or acknowledged is not None):
        raise Unavailable("unexpected start acknowledgement")
    if plan.get("status") == "ready":
        if event in {"prelaunch-rejected", "not-offered"}:
            used = plan["used"] + 1
            retry_at = None
            if used == plan["limit"] // 2:
                retry_at = datetime.fromtimestamp(now + WAIT_SECONDS, timezone.utc).isoformat()
            result.update(status="rejected", continuation={"schema": "native-retry/v1",
                "request_sha256": plan["request_sha256"], "source_sha256": plan["source_sha256"],
                "used": used, "limit": plan["limit"], "retry_at": retry_at,
                "previous_evidence": plan["evidence_sha256"], "refresh_required": event == "not-offered",
                "pool_sha256": plan["pool_sha256"], "next_slot": (plan["slot"] + 1) % 2})
        elif event == "invalid-request":
            result.update(status="invalid-request", reason="repair request; no model fallback")
        elif event == "started" and isinstance(worker_id, str) and worker_id:
            if acknowledged is not None:
                try:
                    closed(acknowledged, "provider family model effort fixed_behavior origin", "acknowledgement")
                    if acknowledged["origin"] != "native-tool":
                        raise Unavailable("native acknowledgement required")
                    for field in ("provider", "family", "model", "effort", "fixed_behavior"):
                        if acknowledged[field] is not None:
                            label(acknowledged[field], field)
                except Unavailable as exc:
                    return unavailable(str(exc))
            result.update(status="running", worker_id=worker_id, acknowledged=acknowledged)
            # The native tool may acknowledge only a worker handle. Missing
            # identity stays unknown; even a full acknowledgement can disagree.
            result["execution_matches_request"] = None
            if acknowledged is not None:
                expected = {**plan["requested"], "model": plan["dispatch"]["model"]}
                if any(acknowledged[k] is not None and acknowledged[k] != v for k, v in expected.items()):
                    result["execution_matches_request"] = False
                elif all(acknowledged[k] is not None for k, v in expected.items() if v is not None):
                    result["execution_matches_request"] = True
        else:
            return unavailable("invalid pre-launch observation")
    elif plan.get("status") == "running" and event in {"succeeded", "failed", "terminated"}:
        result.update(status=event)
    else:
        return unavailable("invalid lifecycle transition; never re-route a started worker")
    return result


def refresh_proposal(policy, bindings, evidence):
    """Observations only: no preference changes, adoption or file writes."""
    mapped = {m for c in bindings["choices"].values() for m in c["models"].values() if m}
    offered = {r["model"] for r in evidence["models"]}
    return {"schema": "native-catalog-proposal/v1", "adopted": False,
            "policy_sha256": digest(policy), "unmapped_offers": sorted(offered - mapped),
            "missing_policy_models": sorted({c["models"][evidence["host"]] for c in bindings["choices"].values()
                if c["models"][evidence["host"]]} - offered)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("source-digest", "plan", "observe", "refresh"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--policy", type=Path, default=ROOT / "model-tiers.json")
    parser.add_argument("--bindings", type=Path, default=ROOT / "native-model-bindings.json")
    args = parser.parse_args(argv)
    try:
        policy, bindings = read_json(args.policy), read_json(args.bindings)
        validate_sources(policy, bindings)
        if args.operation == "source-digest":
            result = {"source_sha256": source_digest(policy, bindings)}
        else:
            payload = read_json(args.input)
            if args.operation == "plan":
                closed(payload, "request evidence continuation", "input")
                result = resolve(payload["request"], payload["evidence"], policy, bindings, continuation=payload["continuation"])
            elif args.operation == "observe":
                closed(payload, "plan event worker_id acknowledged", "input")
                result = observe(**payload)
            else:
                closed(payload, "context evidence", "input")
                validate_evidence(payload["evidence"], payload["context"], source_digest(policy, bindings), datetime.now(timezone.utc).timestamp())
                result = refresh_proposal(policy, bindings, payload["evidence"])
    except (Unavailable, ValueError, OSError, TypeError, KeyError) as exc:
        result = unavailable(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("status") in {"unavailable", "waiting", "invalid-request"} else 0


if __name__ == "__main__":
    sys.exit(main())
