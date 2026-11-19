#!/usr/bin/env python3
"""Codex assessment and dispatch planning. No launches, writes, or authorization.

Evidence and lifecycle records are caller observations, not signed attestations.
Checksums prevent accidental record mixing, not dishonest same-user fabrication.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SCHEMA = "codex-work-decision/v1"
TOOL = "multi_agent_v1.spawn_agent"
COLLABORATION_SCHEMA = "codex-work-decision/v2"
COLLABORATION_TOOL = "collaboration.spawn_agent"
NATIVE_PROFILES = {
    TOOL: {
        "schema": SCHEMA,
        "contract": {"model": "string", "reasoning_effort": "string",
                     "fork_context": "boolean", "ordinary_agent": True},
        "arguments": {"fork_context": False, "agent_type": "default"},
    },
    COLLABORATION_TOOL: {
        "schema": COLLABORATION_SCHEMA,
        "contract": {"model": "string", "reasoning_effort": "string",
                     "fork_turns": "string", "fork_turns_fresh_value": "none",
                     "task_name": "string", "message": "string", "ordinary_agent": True},
        "arguments": {"fork_turns": "none"},
    },
}
DIMS = ("ambiguity", "reasoning", "coupling")
EFFECTS = ("source_edits", "security_judgment", "sign_off", "consequential", "independent_review")
KINDS = {"inspect", "operate", "build", "design", "assure"}
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}

class Invalid(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise Invalid(message)

def closed(value, keys, where):
    require(isinstance(value, dict) and set(value) == set(keys.split()), where + ": invalid fields")

def label(value, where):
    require(isinstance(value, str) and bool(value.strip()), where + ": nonempty text required")

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def read(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "duplicate JSON key")
            result[k] = v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)

def policy():
    p = read(ROOT / "codex-work-policy.json")
    closed(p, "schema routes bands escalations", "policy")
    require(p["schema"] == "codex-work-policy/v1", "unknown policy")
    require(p["bands"] == [0, 1, 2, 3] and p["escalations"] == [1, 2, 3, 4], "invalid policy bands")
    require(isinstance(p["routes"], list) and len(p["routes"]) == 5, "invalid routes")
    for r in p["routes"]:
        closed(r, "model effort", "route")
        label(r["model"], "model")
        require(r["effort"] in EFFORTS, "unknown effort")
    return p

def source_digest():
    return digest({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in ("codex_dispatch.py", "codex-work-policy.json", "CODEX-DISPATCH.md")})

def result(status, **fields):
    return {"schema": SCHEMA, "status": status, "dispatch": None, **fields}

def profile_result(tool, status, **fields):
    record = result(status, **fields)
    if tool == COLLABORATION_TOOL:
        record.update(schema=COLLABORATION_SCHEMA, native_tool=COLLABORATION_TOOL)
    return record

def assess(a):
    closed(a, "schema objective deliverable scope work_class ratings effects reversibility verification unknowns review", "assessment")
    require(a["schema"] == "codex-work-assessment/v1", "unknown assessment schema")
    for key in ("objective", "deliverable", "scope"):
        label(a[key], key)
    require(a["work_class"] in KINDS, "unknown work class")
    closed(a["ratings"], " ".join(DIMS), "ratings")
    incomplete = []
    levels = []
    reasons = []
    for dim in DIMS:
        r = a["ratings"][dim]
        closed(r, "level evidence", dim)
        require(r["level"] is None or type(r["level"]) is int and 0 <= r["level"] <= 3, "invalid rating")
        require(isinstance(r["evidence"], str), "invalid rating evidence")
        if r["level"] is None or not r["evidence"].strip():
            incomplete.append(dim)
        else:
            levels.append(r["level"])
            reasons.append(f"{dim}: D{r['level']}: {r['evidence']}")
    closed(a["effects"], " ".join(EFFECTS), "effects")
    require(all(type(v) is bool for v in a["effects"].values()), "effects must be booleans")
    require(a["reversibility"] in {"reversible", "irreversible", "read-only"}, "unknown reversibility")
    v = a["verification"]
    closed(v, "method checks", "verification")
    require(v["method"] in {"automated", "inspection", "mixed"}, "unknown verification method")
    require(isinstance(v["checks"], list) and bool(v["checks"]), "predefined checks required")
    ids = []
    for c in v["checks"]:
        closed(c, "id criterion", "check")
        label(c["id"], "check id")
        label(c["criterion"], "criterion")
        ids.append(c["id"])
    require(len(ids) == len(set(ids)), "duplicate check id")
    require(isinstance(a["unknowns"], list), "unknowns must be a list")
    for u in a["unknowns"]:
        label(u, "unknown")
    closed(a["review"], "author_model requirement", "review")
    if a["review"]["author_model"] is not None:
        label(a["review"]["author_model"], "author model")
    require(a["review"]["requirement"] in {"none", "separate-context", "different-model", "different-provider"}, "unknown review requirement")
    if incomplete or a["unknowns"]:
        return result("needs-assessment", missing=incomplete, unknowns=a["unknowns"])
    floor = 0
    e = a["effects"]
    if e["source_edits"] or a["work_class"] == "build":
        floor = 1
        reasons.append("source edits/build: D1 floor")
    if e["security_judgment"] or e["sign_off"] or e["independent_review"] or a["work_class"] == "assure" or a["review"]["requirement"] != "none":
        floor = 2
        reasons.append("security judgment/review/sign-off: D2 floor")
    required = ["predefined-acceptance-checks"]
    if e["consequential"] or a["reversibility"] == "irreversible":
        required += ["applicable-authorization", "independent-review"]
    if floor == 2:
        required.append("fresh-review-context" if a["work_class"] == "assure" or e["independent_review"] or a["review"]["requirement"] != "none" else "applicable-review")
    band = max([floor] + levels)
    return result("assessed", band=band, reasons=reasons, required_checks=required,
                  assessment_sha256=digest(a))

def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(dt.utcoffset() == timezone.utc.utcoffset(dt), "UTC time required")
        return dt.timestamp()
    except (ValueError, AttributeError, TypeError):
        raise Invalid("UTC time required") from None

def evidence(ev, ctx, now):
    closed(ctx, "host surface session_id host_build", "context")
    require(ctx["host"] == "codex" and ctx["surface"] == "local-macos-desktop", "unsupported host/surface")
    label(ctx["session_id"], "session")
    if ctx["host_build"] is not None:
        label(ctx["host_build"], "host build")
    closed(ev, "schema context tool origin observed_at source_sha256 contract models", "native evidence")
    require(ev["schema"] == "codex-native-offers/v1" and ev["context"] == ctx, "evidence context mismatch")
    require(isinstance(ev["tool"], str) and ev["tool"] in NATIVE_PROFILES and ev["origin"] == "native-tool", "native tool observation required")
    require(ev["source_sha256"] == source_digest(), "source changed")
    require(0 <= now - stamp(ev["observed_at"]) <= 900, "native evidence stale or future")
    # Exact JSON comparison also distinguishes boolean true from integer 1.
    require(digest(ev["contract"]) == digest(NATIVE_PROFILES[ev["tool"]]["contract"]), "unsupported native contract")
    require(isinstance(ev["models"], list) and bool(ev["models"]), "native offers absent")
    names = []
    for m in ev["models"]:
        closed(m, "model efforts", "native model")
        label(m["model"], "model")
        require(isinstance(m["efforts"], list) and bool(m["efforts"]) and all(isinstance(x, str) and x in EFFORTS for x in m["efforts"]) and len(m["efforts"]) == len(set(m["efforts"])), "invalid native efforts")
        names.append(m["model"])
    require(len(names) == len(set(names)), "duplicate model")

def offered(route, ev):
    return any(m["model"] == route["model"] and route["effort"] in m["efforts"] for m in ev["models"])

def seal(record):
    record = copy.deepcopy(record)
    record.pop("record_sha256", None)
    record["record_sha256"] = digest(record)
    return record

def verify_record(record):
    require(isinstance(record, dict), "record required")
    r = copy.deepcopy(record)
    signature = r.pop("record_sha256", None)
    require(signature == digest(r), "record checksum mismatch")
    require(r.get("schema") in {SCHEMA, COLLABORATION_SCHEMA} and r.get("source_sha256") == source_digest(), "record source/schema mismatch")
    require((r["schema"] == SCHEMA and "native_tool" not in r) or
            (r["schema"] == COLLABORATION_SCHEMA and r.get("native_tool") == COLLABORATION_TOOL),
            "record native profile mismatch")
    return r

def plan(envelope, now=None):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    closed(envelope, "assessment target context evidence override continuation", "plan")
    a, ctx, ev = envelope["assessment"], envelope["context"], envelope["evidence"]
    assessment = assess(a)
    if assessment["status"] != "assessed":
        return assessment
    require(envelope["target"] in {"worker", "parent"}, "unsupported target")
    evidence(ev, ctx, now)
    p = policy()
    band = assessment["band"]
    rank = p["bands"][band]
    selected = copy.deepcopy(p["routes"][rank])
    warnings = []
    if ctx["host_build"] is None:
        warnings.append("host-build-unknown")
    override = envelope["override"]
    if override is not None:
        closed(override, "model effort reason", "override")
        label(override["reason"], "explicit override reason")
        selected = {k: override[k] for k in ("model", "effort")}
        require(selected in p["routes"], "override must be an approved policy pair")
        rank = p["routes"].index(selected)
        require(rank >= band, "override cannot weaken assessed requirements")
        warnings.append("explicit-override")
    quality_used, availability_used = 0, 0
    old = envelope["continuation"]
    if old is not None:
        old = verify_record(old)
        require(old["context"] == ctx and old["target"] == envelope["target"], "continuation context changed")
        require(old.get("native_tool", TOOL) == ev["tool"], "continuation native profile changed")
        require(old["override"] == override, "continuation override changed")
        if old["status"] == "retryable":
            require(old["assessment"] == a, "retry assessment changed")
            availability_used = old["availability_used"]
            quality_used = old["quality_used"]
            require(availability_used == 1, "availability budget exhausted")
            if old["refresh_required"]:
                require(digest(ev) != old["evidence_sha256"], "fresh native evidence required")
            if now < old["retry_at"]:
                return profile_result(ev["tool"], "waiting", retry_at=old["retry_at"], continuation=seal(old))
            rank, selected = old["rank"], old["selected"]
        elif old["status"] == "escalatable":
            require(override is None, "explicit override cannot auto-escalate")
            require(old["quality_used"] == 0, "quality budget exhausted")
            for key in ("objective", "deliverable", "scope", "verification", "effects", "reversibility", "review"):
                require(old["assessment"][key] == a[key], "escalation changed task or acceptance")
            rank = max(rank, min(old["rank"] + 1, 4), p["escalations"][old["band"]])
            selected = copy.deepcopy(p["routes"][rank])
            quality_used = 1
            warnings.append("quality-escalation")
        else:
            raise Invalid("continuation not retryable or escalatable")
    author = a["review"]["author_model"]
    reviewing = a["work_class"] == "assure" or a["effects"]["independent_review"] or a["review"]["requirement"] != "none"
    if reviewing:
        require(a["review"]["requirement"] != "different-provider", "different-provider review unavailable on this route")
        if selected["model"] == author and old is None and override is None:
            alternate = next(((i, r) for i, r in enumerate(p["routes"]) if i >= rank and r["model"] != author and offered(r, ev)), None)
            if alternate:
                rank, selected = alternate[0], copy.deepcopy(alternate[1])
                warnings.append("different-model-review")
        if a["review"]["requirement"] == "different-model":
            require(author is not None and selected["model"] != author, "different-model review unavailable or author unknown")
        warnings.append("same-provider-review; separate-context-only")
    require(offered(selected, ev), "selected model/effort unavailable; no substitution")
    record = profile_result(ev["tool"], "advice" if envelope["target"] == "parent" else "ready",
        source_sha256=source_digest(), policy_sha256=digest(p), context=ctx,
        target=envelope["target"], assessment=copy.deepcopy(a), band=band,
        reasons=assessment["reasons"], required_checks=assessment["required_checks"],
        selected=selected, rank=rank, warnings=warnings, override=override,
        quality_used=quality_used, availability_used=availability_used,
        evidence_sha256=digest(ev), acknowledged=None, execution_matches_request=None,
        worker_id=None, cleanup_verified=False, checks=None, diagnosis=None)
    if record["status"] == "ready":
        arguments = {"model": selected["model"], "reasoning_effort": selected["effort"],
                     **NATIVE_PROFILES[ev["tool"]]["arguments"]}
        record["dispatch"] = {"tool": ev["tool"], "arguments": arguments}
        if ev["tool"] == COLLABORATION_TOOL:
            record["dispatch"]["caller_fields"] = ["task_name", "message"]
    return seal(record)

def observe(envelope, now=None):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    closed(envelope, "record event worker_id acknowledged checks cleanup_verified diagnosis", "observation")
    r = verify_record(envelope["record"])
    event = envelope["event"]
    require(type(envelope["cleanup_verified"]) is bool, "cleanup must be boolean")
    status = r["status"]
    require(event in {"prelaunch-rejected", "not-offered", "invalid-request", "started", "completed", "quality-failed", "infrastructure-failed", "terminated"}, "unknown event")
    if event in {"prelaunch-rejected", "not-offered", "invalid-request"}:
        require(status == "ready" and envelope["worker_id"] is None, "not a proven prelaunch rejection")
        require(envelope["acknowledged"] is None and envelope["checks"] is None, "prelaunch event has execution data")
        if event == "invalid-request":
            r["status"] = "invalid-request"
        elif r["availability_used"] >= 1:
            r["status"] = "unavailable"
        else:
            r.update(status="retryable", availability_used=1, retry_at=now + 60,
                     refresh_required=event == "not-offered")
    elif event == "started":
        require(status == "ready", "worker already started or not ready")
        label(envelope["worker_id"], "worker handle")
        require(envelope["checks"] is None and not envelope["cleanup_verified"], "started event has terminal data")
        r.update(status="started", worker_id=envelope["worker_id"])
        ack = envelope["acknowledged"]
        if ack is not None:
            closed(ack, "model effort origin", "acknowledgement")
            require(ack["origin"] == "native-tool", "native acknowledgement required")
            for key in ("model", "effort"):
                if ack[key] is not None:
                    label(ack[key], key)
            r["acknowledged"] = ack
            mismatch = any(ack[k] is not None and ack[k] != r["selected"][k] for k in ("model", "effort"))
            r["execution_matches_request"] = False if mismatch else (True if all(ack[k] is not None for k in ("model", "effort")) else None)
    else:
        require(envelope["worker_id"] == r["worker_id"] and r["worker_id"] is not None, "worker mismatch")
        require(envelope["acknowledged"] is None, "identity acknowledgement belongs to started event")
        require(status == ("completed" if event == "quality-failed" else "started"), "invalid lifecycle transition")
        r["cleanup_verified"] = envelope["cleanup_verified"]
        if event == "completed":
            checks = envelope["checks"]
            require(isinstance(checks, dict) and set(checks) == {c["id"] for c in r["assessment"]["verification"]["checks"]}, "exact predefined check results required")
            require(all(type(x) is bool for x in checks.values()), "check outcomes must be booleans")
            r.update(status="completed", checks=checks)
        elif event == "quality-failed":
            require(envelope["checks"] is None and r["checks"] and not all(r["checks"].values()), "no failed completed acceptance checks")
            require(r["cleanup_verified"], "cleanup must be verified before escalation")
            label(envelope["diagnosis"], "quality failure diagnosis")
            require(r["execution_matches_request"] is not False, "execution identity mismatch is not quality evidence")
            r.update(status="escalatable" if r["quality_used"] == 0 and r["override"] is None else "quality-exhausted", diagnosis=envelope["diagnosis"])
        else:
            require(envelope["checks"] is None, "infrastructure/termination cannot claim quality checks")
            r["status"] = event
    r["dispatch"] = None
    return seal(r)

def refresh(envelope, now=None):
    closed(envelope, "context evidence", "refresh")
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    evidence(envelope["evidence"], envelope["context"], now)
    return profile_result(envelope["evidence"]["tool"], "proposal-only", policy_sha256=digest(policy()),
                  available=[r for r in policy()["routes"] if offered(r, envelope["evidence"])],
                  adoption_required=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("assess", "plan", "observe", "refresh", "source-digest"))
    parser.add_argument("--input")
    args = parser.parse_args()
    try:
        if args.command == "source-digest":
            out = {"source_sha256": source_digest()}
        else:
            require(args.input is not None, "--input required")
            out = globals()[args.command](read(args.input))
    except (Invalid, ValueError, TypeError, KeyError, OSError) as exc:
        out = result("unavailable", reason=str(exc))
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
    return 0 if out.get("status") not in {"unavailable", "needs-assessment"} else 2

if __name__ == "__main__":
    sys.exit(main())
