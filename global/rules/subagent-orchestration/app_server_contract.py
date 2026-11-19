#!/usr/bin/env python3
"""Closed, bounded records for the unqualified app-server stdio surface.

No processes, network, credentials, installed configuration, or model actions.
The caller owns native provenance; these records are not security capabilities.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SURFACE = "local-macos-app-server-stdio"
EFFORTS = set("none minimal low medium high xhigh max ultra".split())
WARNINGS = set("raised fallback step-down same-provider-review explicit-override review-provider-unverified".split())
LIMITATIONS = set("execution-identity-unverified native-rejection-unobserved native-failure-unobserved catalog-only provider-profile-unverified host-provenance-unverified cleanup-unverified rerouted reroute-target-unmapped".split())
REASONS = set("invalid-schema unsupported-surface invalid-request context-mismatch source-changed profile-mismatch invalid-provenance incomplete-pagination stale-evidence invalid-model-row no-eligible-choice override-unavailable off retry-wait retry-exhausted prelaunch-rejection acceptance-unknown post-start-failure native-reroute cleanup-unverified".split())
CONTEXT = "host surface session_id host_build server_binary_sha256 protocol_schema_sha256 server_instance_ref contract_sha256 launch_or_provider_profile_sha256 initialize_profile_sha256"
PROFILE = "schema profile_id host_build server_binary_sha256 protocol_schema_sha256 launch_descriptor initialize_profile_sha256 model_bindings override_bindings acknowledgement_methods prelaunch_codes"
MAX_BYTES, MAX_MODELS = 1048576, 1024

class Refusal(ValueError):
    def __init__(self, code="invalid-schema"):
        super().__init__(code if code in REASONS else "invalid-schema")

def require(condition, code="invalid-schema"):
    if not condition:
        raise Refusal(code)

def closed(obj, keys):
    require(type(obj) is dict and set(obj) == set(keys.split()))

def label(value):
    require(type(value) is str and 0 < len(value) <= 200)
    # No trimming/case normalization. Reject control characters and surrogate bytes.
    require(not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value))

def enum(value, options):
    require(type(value) is str and value in options)

def sha(value):
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None)

def integer(value, low, high):
    require(type(value) is int and low <= value <= high)

def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise Refusal() from None

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def load(path):
    data = Path(path).read_bytes()
    require(len(data) <= MAX_BYTES)
    def unique(pairs):
        row = {}
        for key, value in pairs:
            require(key not in row)
            row[key] = value
        return row
    def no_number(_):
        raise Refusal()
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                          parse_float=no_number, parse_constant=no_number)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal() from None

def stamp(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value) is not None)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise Refusal() from None

def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()

def context(row):
    closed(row, CONTEXT)
    for k, v in row.items():
        (sha if k.endswith("sha256") else label)(v)
    require(row["host"] == "codex" and row["surface"] == SURFACE, "unsupported-surface")

def stable_context(row):
    return {k: v for k, v in row.items() if k != "contract_sha256"}

def choice(row):
    closed(row, "provider family effort fixed_behavior")
    label(row["provider"]); label(row["family"])
    if row["effort"] is None:
        label(row["fixed_behavior"])
    else:
        enum(row["effort"], EFFORTS)
        require(row["fixed_behavior"] is None)

def models(rows):
    require(type(rows) is list and 0 < len(rows) <= MAX_MODELS, "invalid-model-row")
    result, seen = [], set()
    for row in rows:
        closed(row, "model efforts fixed_behavior")
        label(row["model"])
        require(row["model"] != "inherit" and row["model"] not in seen, "invalid-model-row")
        seen.add(row["model"])
        if row["efforts"] is None:
            label(row["fixed_behavior"])
            efforts = None
        else:
            require(type(row["efforts"]) is list and 0 < len(row["efforts"]) <= len(EFFORTS), "invalid-model-row")
            for e in row["efforts"]: enum(e, EFFORTS)
            require(len(set(row["efforts"])) == len(row["efforts"]) and row["fixed_behavior"] is None, "invalid-model-row")
            efforts = sorted(row["efforts"])
        result.append(dict(model=row["model"], efforts=efforts, fixed_behavior=row["fixed_behavior"]))
    result.sort(key=lambda r: r["model"])
    require(len(canonical(result)) <= MAX_BYTES, "invalid-model-row")
    return result

def profile(row):
    closed(row, PROFILE)
    require(row["schema"] == "app-server-host-profile/v1")
    for key in ("profile_id", "host_build"): label(row[key])
    for key in ("server_binary_sha256", "protocol_schema_sha256", "initialize_profile_sha256"): sha(row[key])
    d = row["launch_descriptor"]
    closed(d, "schema profile_id provider_id transport source_revision offer_semantics")
    require(d["schema"] == "app-server-provider-profile/v1" and d["transport"] == "stdio")
    for key in ("profile_id", "provider_id", "source_revision"): label(d[key])
    require(d["profile_id"] == row["profile_id"])
    enum(d["offer_semantics"], {"qualified-native-offers", "catalog-only", "unknown"})
    require(type(row["model_bindings"]) is dict and len(row["model_bindings"]) <= MAX_MODELS)
    for key, value in row["model_bindings"].items():
        label(key)
        if value is not None: label(value)
    require(type(row["override_bindings"]) is list and len(row["override_bindings"]) <= MAX_MODELS)
    seen = set()
    for b in row["override_bindings"]:
        closed(b, "provider family model mode fixed_behavior")
        for key in ("provider", "family", "model"): label(b[key])
        enum(b["mode"], {"effort", "fixed"})
        if b["mode"] == "effort": require(b["fixed_behavior"] is None)
        else: label(b["fixed_behavior"])
        require((b["provider"], b["family"]) not in seen)
        seen.add((b["provider"], b["family"]))
    for key in ("acknowledgement_methods", "prelaunch_codes"):
        require(type(row[key]) is list and len(row[key]) <= 64)
        for value in row[key]: label(value)
        require(len(set(row[key])) == len(row[key]))

def registry(rows):
    closed(rows, "schema profiles")
    require(rows["schema"] == "app-server-bindings/v1" and type(rows["profiles"]) is list)
    seen = set()
    for row in rows["profiles"]:
        profile(row)
        identity = (row["host_build"], row["server_binary_sha256"], row["protocol_schema_sha256"],
                    digest(row["launch_descriptor"]), row["initialize_profile_sha256"])
        require(identity not in seen)
        seen.add(identity)

def match_profile(ctx, rows):
    context(ctx); registry(rows)
    found = [p for p in rows["profiles"] if all(p[k] == ctx[k] for k in
             ("host_build", "server_binary_sha256", "protocol_schema_sha256", "initialize_profile_sha256"))
             and digest(p["launch_descriptor"]) == ctx["launch_or_provider_profile_sha256"]]
    require(len(found) == 1, "profile-mismatch")
    require(found[0]["launch_descriptor"]["offer_semantics"] == "qualified-native-offers", "invalid-provenance")
    return found[0]

def worker(row):
    closed(row, "server_instance_ref thread_id turn_id")
    for v in row.values(): label(v)

def pending(row):
    closed(row, "server_instance_ref thread_id request_id")
    for v in row.values(): label(v)

def ack(row, p):
    if row is None: return
    closed(row, "provider family model effort fixed_behavior origin evidence_method")
    require(row["origin"] == "native-execution")
    label(row["evidence_method"])
    require(row["evidence_method"] in p["acknowledgement_methods"], "invalid-provenance")
    for key in ("provider", "family", "model", "fixed_behavior"):
        if row[key] is not None: label(row[key])
    if row["effort"] is not None:
        enum(row["effort"], EFFORTS); require(row["fixed_behavior"] is None)

def reroute(row):
    closed(row, "worker from_model to_model reason_class reason_code")
    worker(row["worker"]); label(row["from_model"]); label(row["to_model"])
    # No arbitrary server reason text is accepted by this initial codec.
    require(row["reason_class"] == "unknown" and row["reason_code"] is None)


def normalize_pages(pages, ctx):
    """Decode bounded *projections* of version-validated model/list responses.

    The caller validates the pinned native response schema first, projects only
    the fields below, and discards descriptions, account values and raw pages.
    This function proves pagination/normalization, never native provenance.
    """
    context(ctx)
    require(type(pages) is list and 0 < len(pages) <= MAX_MODELS, 'incomplete-pagination')
    require(len(canonical(pages)) <= MAX_BYTES, 'invalid-model-row')
    expected, cursors, rows = None, set(), []
    for index, page in enumerate(pages):
        closed(page, 'context cursor includeHidden data nextCursor')
        require(page['context'] == stable_context(ctx), 'context-mismatch')
        require(page['includeHidden'] is False and page['cursor'] == expected, 'incomplete-pagination')
        require(type(page['data']) is list and len(page['data']) <= MAX_MODELS, 'invalid-model-row')
        for row in page['data']:
            closed(row, 'model hidden supportedReasoningEfforts')
            label(row['model'])
            require(row['hidden'] is False, 'incomplete-pagination')
            require(type(row['supportedReasoningEfforts']) is list, 'invalid-model-row')
            efforts = []
            for option in row['supportedReasoningEfforts']:
                closed(option, 'reasoningEffort')
                enum(option['reasoningEffort'], EFFORTS)
                efforts.append(option['reasoningEffort'])
            # Native model/list currently supplies effort options; absence does
            # not prove a fixed behavior. A future fixed-mode decoder needs its
            # own qualified schema mapping, never a default or slug heuristic.
            require(bool(efforts), 'invalid-model-row')
            rows.append(dict(model=row['model'], efforts=efforts, fixed_behavior=None))
        expected = page['nextCursor']
        if expected is None:
            require(index == len(pages) - 1, 'incomplete-pagination')
        else:
            label(expected)
            require(expected not in cursors, 'incomplete-pagination')
            cursors.add(expected)
    require(expected is None, 'incomplete-pagination')
    return models(rows)
