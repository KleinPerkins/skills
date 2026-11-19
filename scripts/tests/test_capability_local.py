#!/usr/bin/env python3
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "capability-local.py"
spec = importlib.util.spec_from_file_location("capability_local", SCRIPT)
capability_local = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = capability_local
spec.loader.exec_module(capability_local)


class CapabilityLocalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Path(self.tmp.name) / "capability-local.yml"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_registry_is_not_opted_out(self) -> None:
        self.assertFalse(capability_local.is_opted_out("keep-awake", self.registry))

    def test_record_and_query_opt_out(self) -> None:
        capability_local.record_opt_out("keep-awake", self.registry)
        self.assertTrue(capability_local.is_opted_out("keep-awake", self.registry))
        self.assertFalse(capability_local.is_opted_out("other", self.registry))
        text = self.registry.read_text(encoding="utf-8")
        self.assertIn("schema: kp-capability-local/v1", text)
        self.assertIn("- keep-awake", text)
        mode = self.registry.stat().st_mode
        self.assertEqual(mode & 0o777, 0o600)

    def test_record_is_idempotent(self) -> None:
        capability_local.record_opt_out("keep-awake", self.registry)
        capability_local.record_opt_out("keep-awake", self.registry)
        _schema, items = capability_local.load_registry(self.registry)
        self.assertEqual(items, ["keep-awake"])

    def test_clear_opt_out_removes_file_when_empty(self) -> None:
        capability_local.record_opt_out("keep-awake", self.registry)
        capability_local.clear_opt_out("keep-awake", self.registry)
        self.assertFalse(self.registry.exists())

    def test_reset_removes_registry(self) -> None:
        capability_local.record_opt_out("keep-awake", self.registry)
        capability_local.reset_registry(self.registry)
        self.assertFalse(self.registry.exists())

    def test_unknown_schema_ignored_for_reads(self) -> None:
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(
            "schema: kp-capability-local/v99\nopt_out:\n  - keep-awake\n",
            encoding="utf-8",
        )
        self.assertFalse(capability_local.is_opted_out("keep-awake", self.registry))

    def test_parse_warnings_preserve_valid_opt_outs(self) -> None:
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(
            "schema: kp-capability-local/v1\nopt_out:\n  - keep-awake\nnotes: stray\n",
            encoding="utf-8",
        )
        self.assertTrue(capability_local.is_opted_out("keep-awake", self.registry))

    def test_cli_is_opted_out_exit_codes(self) -> None:
        capability_local.record_opt_out("keep-awake", self.registry)
        self.assertEqual(
            capability_local.main(["is-opted-out", "keep-awake", "--registry", str(self.registry)]),
            0,
        )
        self.assertEqual(
            capability_local.main(["is-opted-out", "other", "--registry", str(self.registry)]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
