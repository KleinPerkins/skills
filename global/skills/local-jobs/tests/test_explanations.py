"""Test job explanations against their inspected program and persisted cache."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import explain_cache
import explain_inspect


class CommandExplanations(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.root = Path(area.name).resolve()
        change = patch.dict(os.environ, {"LOCAL_JOBS_STATE": str(self.root / "state")})
        change.start()
        self.addCleanup(change.stop)
        self.script = self.root / "refresh-reference-metadata.sh"
        self.script.write_text("#!/bin/sh\n# Refreshes the selected reference metadata\nexit 99\n")
        self.job = {
            "id": "maintain",
            "type": "command",
            "program": "/bin/sh",
            "args": [str(self.script)],
            "execution_mode": "on_demand",
        }

    def inspect(self):
        with (patch.object(explain_inspect.registry, "load_registry", return_value={}),
              patch.object(explain_inspect.registry, "collect_instances", return_value=[self.job]),
              patch.object(explain_inspect.registry, "build_list_types", return_value=[])):
            return explain_inspect.inspect_job(self.job["id"], queue_agent=False)

    def test_maintain_uses_script_description_and_preserves_operator_description(self):
        result = self.inspect()
        self.assertIn("Refreshes the selected reference metadata", result["narrative"][0])
        self.assertNotIn("agent-route", " ".join(result["narrative"]))
        self.assertIn("on demand", result["narrative"][1])
        self.job["description"] = "Keep my selected reference metadata current."
        self.assertEqual(self.inspect()["narrative"][0], self.job["description"])

    def test_script_name_does_not_imply_routing_or_a_timer(self):
        script = self.root / "archive-agent-route-history.sh"
        script.write_text("#!/bin/sh\nexit 99\n")
        self.job.update(id="archive", args=[str(script)])
        narrative = self.inspect()["narrative"]
        self.assertIn(script.name, narrative[0])
        self.assertNotIn("timer", narrative[0])
        self.assertIn("on demand", narrative[1])

    def test_old_synthesized_cache_is_ignored_but_an_agent_explanation_is_preserved(self):
        cache = explain_cache.cache_path(self.job["id"])
        cache.parent.mkdir(parents=True)
        old = {
            "schema": explain_cache.SCHEMA,
            "fingerprint": explain_cache.fingerprint(self.job),
            "source": "synthesize",
            "narrative": ["This maintains the agent-route capability."],
        }
        cache.write_text(json.dumps(old))
        self.assertIsNone(explain_cache.load_for_instance(self.job))
        self.assertEqual(json.loads(cache.read_text()), old)
        updated = self.inspect()
        explain_cache.write(self.job["id"], updated)
        self.assertEqual(explain_cache.load_for_instance(self.job)["narrative"], updated["narrative"])
        cache.write_text(json.dumps({**old, "source": "agent", "narrative": ["Reviewed agent explanation."]}))
        self.assertEqual(self.inspect()["narrative"], ["Reviewed agent explanation."])


if __name__ == "__main__":
    unittest.main()
