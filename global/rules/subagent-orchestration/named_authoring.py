"""Validate observations from the owned Codex GSD authoring process.

The caller owns process, sandbox, staged files and report custody. Neither a
tool offer nor a decoded observation grants consent, settles plan authority, or
authorizes use in another process. The ordinary dispatch profiles are separate.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import uuid


CLIENT_VERSION = "0.171.0-alpha.13"
CLIENT_SHA256 = "3b6d00deea5fabc50ad34be1872b8e4ead1638d23c68fabb7837edc07f0cf1e0"
PACKAGE_SHA256 = "b7ed2186d397b270a52db5e9816a9fd88a240466b356b1f4a28823f93cb8fd9d"
MODEL = "gpt-6.2-sol"
EFFORT = "high"
TOOL = "collaboration.spawn_agent"
ROLE_DIGESTS = {
    "gsd-advisor-researcher": "72235ec0a7fd898930f174eb080c9d33632054aa739e33ffd5d91c880f656988",
    "gsd-nyquist-auditor": "064465f9194763a8e355c84a44a62f6f2c2eb2926f810aa2cc79231446845754",
    "gsd-pattern-mapper": "48a17baa3d7d142c18814f5b0ab67912b6f3cbada209e7e42ffe6fc1d770dc56",
    "gsd-phase-researcher": "9d9d82cb785e0c7b0e814fa76aab0799dc5f02fe379992285393f76e5b73fe32",
    "gsd-plan-checker": "48320fd246635977cd7979c46809f70eb96588028905fa60e94e515e133eccc9",
    "gsd-planner": "e5cc36440fccf07d87f215a74d14c6f7baf35f00e26ddfdf666c86cf2c91fd36",
    "gsd-project-researcher": "1241fb9066f2a8a9ed368d1ec252ae07d813685ef45f2f4f4371efad473fbb47",
    "gsd-research-synthesizer": "d38378cf68449220e6678c9d709a0b7c991d7c70d628d9ff761c09be58e7dc05",
    "gsd-roadmapper": "b549d03eba170684380eecc6114c861e07c28214629946bb26dbb96b5d773a7c",
}
SPAWN_PROPERTIES = {"agent_type", "fork_turns", "message", "model", "reasoning_effort", "task_name"}
MAX_REPORT = 128 * 1024
MAX_EVENT_COUNT = 4096


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _digest(data):
    _require(isinstance(data, bytes), "named_authoring_input_invalid")
    return sha256(data).hexdigest()


def _thread_id(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def verify_role_input(role, *, client_version, client_digest, package_digest, role_config, bundle_root):
    """Check pinned inputs before offering or observing a named route."""
    _require(client_version == CLIENT_VERSION and client_digest == CLIENT_SHA256,
             "named_authoring_client_unqualified")
    _require(package_digest == PACKAGE_SHA256, "named_authoring_package_changed")
    _require(type(role) is str and role in ROLE_DIGESTS, "named_authoring_role_unqualified")
    _require(isinstance(bundle_root, Path) and bundle_root.is_absolute()
             and len(bundle_root.parts) > 2
             and all(re.fullmatch(r"[a-zA-Z0-9._-]+", part) and part not in (".", "..")
                     for part in bundle_root.parts[1:]),
             "named_authoring_bundle_root_invalid")
    config_digest = _digest(role_config)
    # The verified upstream emitter inserts the absolute operation/bundle path.
    # Replace only that exact, delimited prefix before comparing all role bytes.
    marker = b"${PACKAGE_OPERATION}/bundle/"
    prefix = (str(bundle_root) + "/").encode()
    _require(marker not in role_config, "named_authoring_role_changed")
    normalized = role_config.replace(prefix, marker)
    _require(_digest(normalized) == ROLE_DIGESTS[role], "named_authoring_role_changed")
    return config_digest


def verify_spawn_offer(tool, role):
    """Check the exact native function schema observed by the controller."""
    _require(type(role) is str and role in ROLE_DIGESTS, "named_authoring_role_unqualified")
    unavailable = "named_authoring_selector_unavailable"
    _require(isinstance(tool, dict) and set(tool) == {"type", "name", "description", "strict", "parameters"}
             and tool["type"] == "function" and tool["name"] == "spawn_agent"
             and tool["strict"] is False and type(tool["description"]) is str, unavailable)
    parameters = tool["parameters"]
    _require(isinstance(parameters, dict)
             and set(parameters) == {"type", "properties", "required", "additionalProperties"}
             and parameters["type"] == "object" and parameters["additionalProperties"] is False
             and parameters["required"] == ["task_name", "message"], unavailable)
    props = parameters["properties"]
    _require(isinstance(props, dict) and set(props) == SPAWN_PROPERTIES, unavailable)
    for name, field in props.items():
        expected = {"type", "description", "encrypted"} if name == "message" else {"type", "description"}
        _require(isinstance(field, dict) and set(field) == expected and field["type"] == "string"
                 and type(field["description"]) is str
                 and (name != "message" or field["encrypted"] is True), unavailable)
    description = props["agent_type"]["description"]
    _, separator, roster = description.partition("\nAvailable roles:\n")
    # This pinned build publishes a string selector and role roster, with no
    # enum. The actual child's machine-readable agentRole proves selection.
    names = []
    _require(len(description) <= MAX_REPORT and separator and roster.endswith("\n}"), unavailable)
    for stanza in roster.split("\n}"):
        if not stanza:
            continue
        entry = re.fullmatch(r"([a-z0-9_-]+): \{\n.*", stanza.removeprefix("\n"), re.DOTALL)
        _require(entry is not None, unavailable)
        names.append(entry[1])
    _require(len(set(names)) == len(names) and role in names, unavailable)
    encoded = json.dumps(tool, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    _require(len(encoded) <= MAX_REPORT, unavailable)
    return _digest(encoded)


@dataclass(frozen=True)
class Observation:
    """Closed source evidence and private report bytes from one settled run."""

    evidence: dict
    report: bytes


def observe_role(role, *, client_version, client_digest, package_digest, role_config, bundle_root,
                 spawn_offer, parent_result, parent_turn, events, child_result):
    """Decode only the supplied controller's live native, same-process events.

    The caller passes the actual same-configuration function offer, live completed
    events, and direct thread/start, turn/start and thread/read responses. Reports are
    private. Only the digest and closed status may be projected by this decoder.
    """
    role_digest = verify_role_input(role, client_version=client_version, client_digest=client_digest,
                                    package_digest=package_digest, role_config=role_config, bundle_root=bundle_root)
    selector_digest = verify_spawn_offer(spawn_offer, role)
    _require(isinstance(parent_result, dict) and parent_result.get("model") == MODEL,
             "named_authoring_parent_changed")
    sandbox = parent_result.get("sandbox")
    _require(isinstance(sandbox, dict) and sandbox.get("type") == "readOnly"
             and sandbox.get("networkAccess", False) is False,
             "named_authoring_parent_permissions_changed")
    parent = parent_result.get("thread")
    _require(isinstance(parent, dict) and _thread_id(parent.get("id")) and _thread_id(parent_turn),
             "named_authoring_parent_changed")
    parent_id = parent["id"]
    _require(isinstance(child_result, dict) and _thread_id(child_result.get("id"))
             and child_result["id"] != parent_id and child_result.get("agentRole") == role
             and child_result.get("parentThreadId") == parent_id and child_result.get("ephemeral") is True
             and child_result.get("status") == {"type": "idle"} and child_result.get("turns") == [],
             "named_authoring_child_identity_changed")
    child_id = child_result["id"]

    _require(isinstance(events, (list, tuple)) and len(events) <= MAX_EVENT_COUNT,
             "named_authoring_events_invalid")
    activities = []
    report = None
    report_item = None
    child_turn = None
    child_completed = False
    settled = False
    for event in events:
        _require(isinstance(event, dict) and "id" not in event, "named_authoring_unexpected_client_request")
        method = event.get("method")
        params = event.get("params")
        if isinstance(params, dict):
            if "threadId" in params:
                _require(params["threadId"] in (parent_id, child_id), "named_authoring_foreign_child")
            if method == "thread/started":
                started = params.get("thread")
                _require(isinstance(started, dict) and started.get("id") in (parent_id, child_id),
                         "named_authoring_foreign_child")
        if method not in ("item/completed", "turn/completed"):
            continue
        _require(isinstance(params, dict) and "threadId" in params, "named_authoring_events_invalid")
        thread = params["threadId"]
        if method == "turn/completed":
            if thread == child_id:
                turn = params.get("turn")
                _require(not child_completed and not settled and activities and child_turn is not None
                         and isinstance(turn, dict) and turn.get("id") == child_turn
                         and turn.get("status") == "completed" and turn.get("error") is None,
                         "named_authoring_child_incomplete")
                # Ephemeral thread/read has no history. The native terminal
                # turn payload is a second readback of its completed message.
                items = turn.get("items")
                _require(isinstance(items, list) and all(isinstance(item, dict) for item in items),
                         "named_authoring_terminal_report_changed")
                messages = [item for item in items if item.get("type") == "agentMessage"]
                _require(messages and messages[-1].get("id") == report_item
                         and messages[-1].get("text") == report.decode("utf-8"),
                         "named_authoring_terminal_report_changed")
                child_completed = True
            if thread == parent_id:
                turn = params.get("turn")
                _require(not settled and child_completed and activities == ["started", "completed"] and report is not None
                         and isinstance(turn, dict) and turn.get("id") == parent_turn
                         and turn.get("status") == "completed" and turn.get("error") is None,
                         "named_authoring_parent_incomplete")
                settled = True
            continue

        item = params.get("item")
        _require(isinstance(item, dict), "named_authoring_events_invalid")
        if item.get("type") == "subAgentActivity":
            phase = item.get("kind")
            peer = item.get("agentThreadId")
            if phase == "interacted":
                # The app-server can report a message from either participant
                # about the other. This does not create or settle a child.
                _require(not settled and activities == ["started"]
                         and (thread, peer) in ((parent_id, child_id), (child_id, parent_id)),
                         "named_authoring_foreign_child")
                turn = params.get("turnId")
                if thread == parent_id:
                    _require(turn == parent_turn, "named_authoring_parent_changed")
                else:
                    _require(not child_completed and _thread_id(turn)
                             and (child_turn is None or child_turn == turn), "named_authoring_child_incomplete")
                    child_turn = turn
                continue
            _require(not settled and thread == parent_id and params.get("turnId") == parent_turn
                     and peer == child_id, "named_authoring_foreign_child")
            if phase == "started":
                _require(not activities and item.get("model") == MODEL and item.get("reasoningEffort") == EFFORT,
                         "named_authoring_child_model_or_effort_changed")
            else:
                _require(phase == "completed" and activities == ["started"] and report is not None,
                         "named_authoring_child_incomplete")
            activities.append(phase)
        elif item.get("type") == "agentMessage" and thread == child_id:
            turn = params.get("turnId")
            _require(not settled and not child_completed and activities == ["started"]
                     and _thread_id(turn) and (child_turn is None or child_turn == turn)
                     and type(item.get("id")) is str and 0 < len(item["id"]) <= 128
                     and isinstance(item.get("text"), str), "named_authoring_report_invalid")
            child_turn = turn
            try:
                raw = item["text"].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("named_authoring_report_invalid") from exc
            _require(0 < len(raw) <= MAX_REPORT, "named_authoring_report_invalid")
            report = raw
            report_item = item["id"]
    _require(settled and report is not None, "named_authoring_parent_incomplete")
    first_line = report.strip().split(b"\n", 1)[0]
    verdict = None
    if role == "gsd-plan-checker":
        verdict = {
            b"## VERIFICATION PASSED": "VERIFICATION PASSED",
            b"## ISSUES FOUND": "ISSUES FOUND",
        }.get(first_line)
        _require(verdict is not None, "named_authoring_checker_verdict_invalid")
    return Observation(
        evidence={
            "schema": "skills/gsd-named-authoring-observation/v1",
            "client_version": client_version, "client_sha256": client_digest,
            "package_sha256": package_digest, "role": role, "role_sha256": role_digest,
            "tool": TOOL, "selector_sha256": selector_digest, "model": MODEL, "effort": EFFORT,
            "verdict": verdict, "report_sha256": _digest(report),
        },
        report=report,
    )
