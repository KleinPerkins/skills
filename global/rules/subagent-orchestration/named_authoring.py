"""Validate observations from the owned Codex GSD authoring process.

The caller owns process, sandbox, staged files and report custody. Neither a
tool offer nor a decoded observation grants consent, settles plan authority, or
authorizes use in another process. The ordinary dispatch profiles are separate.
"""

from dataclasses import dataclass
from hashlib import sha256
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
             and len(bundle_root.parts) > 2 and ".." not in bundle_root.parts,
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
    _require(isinstance(tool, dict) and tool.get("name") == "spawn_agent",
             "named_authoring_selector_unavailable")
    parameters = tool.get("parameters")
    props = parameters.get("properties") if isinstance(parameters, dict) else None
    _require(isinstance(props, dict) and set(props) == SPAWN_PROPERTIES,
             "named_authoring_selector_unavailable")
    for name in SPAWN_PROPERTIES:
        field = props[name]
        _require(isinstance(field, dict) and field.get("type") == "string",
                 "named_authoring_selector_unavailable")
    description = props["agent_type"].get("description")
    _require(type(description) is str and len(description) <= MAX_REPORT
             and re.search(r"(?<![\w-])" + re.escape(role) + r"(?![\w-])", description),
             "named_authoring_selector_unavailable")


@dataclass(frozen=True)
class Observation:
    """Closed source evidence and private report bytes from one settled run."""

    evidence: dict
    report: bytes


def observe_role(role, *, client_version, client_digest, package_digest, role_config, bundle_root,
                 parent_result, parent_turn, events, child_result):
    """Decode only the supplied controller's live native, same-process events.

    The caller passes completed item events from the current process and its
    direct thread/start, turn/start (ID) and thread/read responses. Reports are
    private. Only the digest and closed status may be projected by this decoder.
    """
    role_digest = verify_role_input(role, client_version=client_version, client_digest=client_digest,
                                    package_digest=package_digest, role_config=role_config, bundle_root=bundle_root)
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
             and child_result["id"] != parent_id and child_result.get("agentRole") == role,
             "named_authoring_child_identity_changed")
    child_id = child_result["id"]

    _require(isinstance(events, (list, tuple)) and len(events) <= MAX_EVENT_COUNT,
             "named_authoring_events_invalid")
    activities = []
    report = None
    child_turn = None
    child_completed = False
    settled = False
    for event in events:
        _require(isinstance(event, dict) and "id" not in event, "named_authoring_unexpected_client_request")
        method = event.get("method")
        if method not in ("item/completed", "turn/completed"):
            continue
        params = event.get("params")
        _require(isinstance(params, dict), "named_authoring_events_invalid")
        thread = params.get("threadId")
        if method == "turn/completed":
            if thread == child_id:
                turn = params.get("turn")
                _require(not child_completed and activities == ["started"] and child_turn is not None
                         and isinstance(turn, dict) and turn.get("id") == child_turn
                         and turn.get("status") == "completed", "named_authoring_child_incomplete")
                child_completed = True
            if thread == parent_id:
                turn = params.get("turn")
                _require(not settled and activities == ["started", "completed"] and report is not None
                         and isinstance(turn, dict) and turn.get("id") == parent_turn
                         and turn.get("status") == "completed", "named_authoring_parent_incomplete")
                settled = True
            continue

        item = params.get("item")
        _require(isinstance(item, dict), "named_authoring_events_invalid")
        if item.get("type") == "subAgentActivity":
            _require(not settled and thread == parent_id and params.get("turnId") == parent_turn
                     and item.get("agentThreadId") == child_id, "named_authoring_foreign_child")
            phase = item.get("kind")
            if phase == "started":
                _require(not activities and item.get("model") == MODEL and item.get("reasoningEffort") == EFFORT,
                         "named_authoring_child_model_or_effort_changed")
            else:
                _require(phase == "completed" and activities == ["started"] and child_completed and report is not None,
                         "named_authoring_child_incomplete")
            activities.append(phase)
        elif item.get("type") == "agentMessage" and thread == child_id:
            turn = params.get("turnId")
            _require(not settled and not child_completed and activities == ["started"]
                     and _thread_id(turn) and (child_turn is None or child_turn == turn)
                     and isinstance(item.get("text"), str), "named_authoring_report_invalid")
            child_turn = turn
            try:
                raw = item["text"].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("named_authoring_report_invalid") from exc
            _require(0 < len(raw) <= MAX_REPORT, "named_authoring_report_invalid")
            report = raw
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
            "tool": TOOL, "model": MODEL, "effort": EFFORT,
            "verdict": verdict, "report_sha256": _digest(report),
        },
        report=report,
    )


def source_digest():
    """The consumer pins the exact owner file and the protocol it supplies."""
    return _digest(Path(__file__).read_bytes())
