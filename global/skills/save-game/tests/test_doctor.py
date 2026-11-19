"""Engine doctor and real temporary symlink-fixture tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _support

from engine import adapters, doctor


def _link_for(home: Path, capability: adapters.ClientCapability) -> Path:
    link = capability.resolved_discovery_path(home)
    link.parent.mkdir(parents=True, exist_ok=True)
    return link


class TestClientLinkChecks(unittest.TestCase):
    def test_correct_symlink_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            capability = adapters.get_client("cursor")
            link = _link_for(home, capability)
            link.symlink_to(_support.SKILL_DIR)

            result = doctor.check_client_link(
                capability, skill_dir=_support.SKILL_DIR, home=home
            )
            self.assertEqual(result.status, doctor.PASS)
            self.assertIn("owned symlink", result.detail)

    def test_broken_symlink_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            capability = adapters.get_client("claude")
            link = _link_for(home, capability)
            link.symlink_to(Path(temp) / "missing-target")

            result = doctor.check_client_link(
                capability, skill_dir=_support.SKILL_DIR, home=home
            )
            self.assertEqual(result.status, doctor.FAIL)
            self.assertIn("broken symlink", result.detail)

    def test_missing_symlink_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            capability = adapters.get_client("codex")

            result = doctor.check_client_link(
                capability, skill_dir=_support.SKILL_DIR, home=home
            )
            self.assertEqual(result.status, doctor.FAIL)
            self.assertIn("missing discovery link", result.detail)

    def test_real_directory_at_discovery_path_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            capability = adapters.get_client("cursor")
            _link_for(home, capability).mkdir()

            result = doctor.check_client_link(
                capability, skill_dir=_support.SKILL_DIR, home=home
            )
            self.assertEqual(result.status, doctor.FAIL)
            self.assertIn("not a symlink", result.detail)


class TestEngineDoctor(unittest.TestCase):
    def test_full_doctor_passes_disk_prerequisites_with_fixture_links(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            for capability in adapters.list_clients():
                _link_for(home, capability).symlink_to(_support.SKILL_DIR)

            report = doctor.run_doctor(
                skill_dir=_support.SKILL_DIR,
                home=home,
            )

        self.assertEqual(report["disk_prerequisite_status"], doctor.PASS)
        checks = {item["name"]: item for item in report["checks"]}

        schema_checks = [
            item for name, item in checks.items() if name.startswith("schema:")
        ]
        self.assertEqual(len(schema_checks), 11)
        self.assertTrue(all(item["status"] == doctor.PASS for item in schema_checks))

        self.assertEqual(
            checks["import:engine.schemas_validate"]["status"], doctor.PASS
        )
        self.assertEqual(checks["import:engine.adapters"]["status"], doctor.PASS)
        self.assertEqual(checks["import:engine.doctor"]["status"], doctor.PASS)

        runtime_checks = [
            item for name, item in checks.items() if name.startswith("runtime:")
        ]
        self.assertEqual(len(runtime_checks), 8)
        self.assertTrue(all(item["status"] == doctor.PASS for item in runtime_checks))

        for client_id in adapters.client_ids():
            self.assertEqual(
                checks[f"client-link:{client_id}"]["status"], doctor.PASS
            )
            self.assertEqual(
                checks[f"live-acceptance:{client_id}"]["status"], doctor.UNKNOWN
            )

        acceptance = report["live_cross_client_acceptance"]
        self.assertEqual(acceptance["status"], doctor.UNKNOWN)
        self.assertIn("not proved by this doctor", acceptance["statement"])

    def test_schema_inventory_constant_is_exact(self):
        self.assertEqual(len(doctor.EXPECTED_SCHEMA_FILES), 11)
        self.assertEqual(
            set(doctor.EXPECTED_SCHEMA_FILES),
            {
                path.name
                for path in (_support.SKILL_DIR / "engine" / "schemas").glob(
                    "*.schema.json"
                )
            },
        )


if __name__ == "__main__":
    unittest.main()
