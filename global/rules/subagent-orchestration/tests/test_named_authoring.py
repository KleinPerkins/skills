import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("named_authoring", ROOT / "named_authoring.py")
lane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lane)


class NamedAuthoringTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.turn, self.child, self.child_turn = (str(uuid4()) for _ in range(4))
        self.role = "gsd-plan-checker"
        self.settings = {
            "client_version": lane.CLIENT_VERSION,
            "client_digest": lane.CLIENT_SHA256,
            "package_digest": lane.PACKAGE_SHA256,
            "role_config": b"fixture /private/tmp/isolated/bundle/role",
            "bundle_root": Path("/private/tmp/isolated/bundle"),
        }
        self.report = "## VERIFICATION PASSED\nPrivate checker content."
        self.message_id = str(uuid4())
        self.args = {
            "spawn_offer": self.spawn_offer(),
            "parent_result": {
                "sandbox": {"type": "readOnly", "networkAccess": False},
                "model": lane.MODEL,
                "thread": {"id": self.parent},
            },
            "parent_turn": self.turn,
            "events": [
                self.event("started", model=lane.MODEL, reasoningEffort=lane.EFFORT),
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": self.child,
                        "turnId": self.child_turn,
                        "item": self.message(self.report),
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {"threadId": self.child, "turn": {
                        "id": self.child_turn, "status": "completed", "items": [self.message(self.report)],
                    }},
                },
                self.event("completed"),
                {
                    "method": "turn/completed",
                    "params": {"threadId": self.parent, "turn": {"id": self.turn, "status": "completed"}},
                },
            ],
            "child_result": {"id": self.child, "agentRole": self.role, "parentThreadId": self.parent,
                             "ephemeral": True, "status": {"type": "idle"}, "turns": []},
        }

    def message(self, text):
        return {"type": "agentMessage", "id": self.message_id, "text": text}

    def event(self, kind, **kwargs):
        return {
            "method": "item/completed",
            "params": {
                "threadId": self.parent,
                "turnId": self.turn,
                "item": {"type": "subAgentActivity", "kind": kind, "agentThreadId": self.child, **kwargs},
            },
        }

    def observe(self, inputs=None):
        with patch.dict(lane.ROLE_DIGESTS, {self.role: lane._digest(b"fixture ${PACKAGE_OPERATION}/bundle/role")}):
            return lane.observe_role(self.role, **self.settings, **(self.args if inputs is None else inputs))

    def test_actual_child_report_is_kept_separate_from_closed_evidence(self):
        observed = self.observe()
        self.assertEqual(observed.evidence["verdict"], "VERIFICATION PASSED")
        self.assertEqual(observed.evidence["role"], self.role)
        self.assertEqual(observed.report, self.report.encode())
        self.assertNotIn("Private checker content", repr(observed.evidence))
        self.assertNotIn(self.child, repr(observed.evidence))

    def test_refuses_parent_echo_as_child_report(self):
        self.args["events"][1]["params"]["threadId"] = self.parent
        with self.assertRaisesRegex(ValueError, "child_incomplete"):
            self.observe()

    def test_native_child_terminal_notifications_may_arrive_in_either_order(self):
        events = self.args["events"]
        events[2], events[3] = events[3], events[2]
        self.assertEqual(self.observe().report, self.report.encode())
        events.pop(3)
        with self.assertRaisesRegex(ValueError, "parent_incomplete"):
            self.observe()

    def test_reports_closed_issues_verdict(self):
        message = self.args["events"][1]["params"]["item"]
        terminal_message = self.args["events"][2]["params"]["turn"]["items"][0]
        message["text"] = terminal_message["text"] = "## ISSUES FOUND\nPrivate checker content."
        self.assertEqual(self.observe().evidence["verdict"], "ISSUES FOUND")
        message["text"] = terminal_message["text"] = "I think the review passed."
        with self.assertRaisesRegex(ValueError, "checker_verdict_invalid"):
            self.observe()

    def test_refuses_other_settings_or_incomplete_run(self):
        for changes, error in (
            ({"agentThreadId": str(uuid4())}, "foreign_child"),
            ({"model": "different"}, "child_model_or_effort_changed"),
            ({"reasoningEffort": "low"}, "child_model_or_effort_changed"),
        ):
            with self.subTest(changes=changes):
                inputs = copy.deepcopy(self.args)
                inputs["events"][0]["params"]["item"].update(changes)
                with self.assertRaisesRegex(ValueError, error):
                    self.observe(inputs)
        self.args["events"].pop()
        with self.assertRaisesRegex(ValueError, "parent_incomplete"):
            self.observe()

    def test_wrong_named_role_and_permissions_refuse(self):
        self.args["child_result"]["agentRole"] = "default"
        with self.assertRaisesRegex(ValueError, "child_identity_changed"):
            self.observe()
        self.args["parent_result"]["sandbox"]["networkAccess"] = True
        with self.assertRaisesRegex(ValueError, "parent_permissions_changed"):
            self.observe()

    def test_native_permission_callback_refuses(self):
        self.args["events"].insert(1, {"method": "item/commandExecution/requestApproval", "id": 40})
        with self.assertRaisesRegex(ValueError, "unexpected_client_request"):
            self.observe()

    def test_owner_pins_reject_changed_role_or_build(self):
        with self.assertRaisesRegex(ValueError, "role_changed"):
            lane.verify_role_input(self.role, **self.settings)
        self.settings["client_version"] = "0.171.1"
        with self.assertRaisesRegex(ValueError, "client_unqualified"):
            self.observe()

    def test_foreign_child_items_turns_and_starts_refuse(self):
        foreign = str(uuid4())
        for event in (
            {"method": "item/completed", "params": {
                "threadId": foreign, "item": {"type": "agentMessage", "text": "other"}}},
            {"method": "turn/completed", "params": {
                "threadId": foreign, "turn": {"id": str(uuid4()), "status": "completed"}}},
            {"method": "thread/started", "params": {"thread": {"id": foreign}}},
        ):
            with self.subTest(method=event["method"]):
                inputs = copy.deepcopy(self.args)
                inputs["events"].insert(1, event)
                with self.assertRaisesRegex(ValueError, "foreign_child"):
                    self.observe(inputs)

    def spawn_offer(self):
        props = {name: {"type": "string", "description": name} for name in lane.SPAWN_PROPERTIES}
        props["message"]["encrypted"] = True
        props["agent_type"]["description"] = (
            "Role selector.\nAvailable roles:\ngsd-plan-checker: {\nFixture\n}\ndefault: {\nGeneral\n}"
        )
        schema = {"type": "object", "properties": props, "required": ["task_name", "message"],
                  "additionalProperties": False}
        return {"type": "function", "name": "spawn_agent", "strict": False,
                "description": "Fixture", "parameters": schema}

    def test_observation_binds_the_offer_and_terminal_message(self):
        first = self.observe()
        self.assertEqual(first.evidence["selector_sha256"], lane.verify_spawn_offer(self.spawn_offer(), self.role))
        self.args["spawn_offer"]["parameters"]["additionalProperties"] = True
        with self.assertRaisesRegex(ValueError, "selector_unavailable"):
            self.observe()
        self.args["spawn_offer"] = self.spawn_offer()
        terminal = self.args["events"][2]["params"]["turn"]
        terminal["items"][0]["text"] = "## VERIFICATION PASSED\nUnrelated report."
        with self.assertRaisesRegex(ValueError, "terminal_report_changed"):
            self.observe()

    def test_selector_requires_closed_native_schema_and_top_level_named_role(self):
        tool = self.spawn_offer()
        props = tool["parameters"]["properties"]
        lane.verify_spawn_offer(tool, self.role)

        for key, value in (("required", ["task_name"]), ("additionalProperties", True)):
            with self.subTest(key=key):
                invalid = copy.deepcopy(tool)
                invalid["parameters"][key] = value
                with self.assertRaisesRegex(ValueError, "selector_unavailable"):
                    lane.verify_spawn_offer(invalid, self.role)
        for other in (
            "gsd-plan-checker mentioned but unavailable",
            "Types.\nAvailable roles:\ndefault: {\nCalls gsd-plan-checker\n}",
            "Types.\nAvailable roles:\ngsd-plan-checker-other: {\nOther\n}",
        ):
            props["agent_type"]["description"] = other
            with self.assertRaisesRegex(ValueError, "selector_unavailable"):
                lane.verify_spawn_offer(tool, self.role)
        del props["agent_type"]
        with self.assertRaisesRegex(ValueError, "selector_unavailable"):
            lane.verify_spawn_offer(tool, self.role)


if __name__ == "__main__":
    unittest.main()
