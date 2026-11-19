"""Client capability registry tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _support  # noqa: F401

from engine import adapters


class TestClientCapabilityRegistry(unittest.TestCase):
    def test_registry_has_exact_supported_clients(self):
        self.assertEqual(adapters.client_ids(), ("cursor", "claude", "codex"))
        self.assertEqual(
            tuple(item.client_id for item in adapters.list_clients()),
            adapters.client_ids(),
        )

    def test_cursor_facts(self):
        capability = adapters.get_client("cursor")
        self.assertEqual(capability.discovery_path, "~/.cursor/skills/save-game")
        self.assertEqual(capability.explicit_invocation, "/save-game")
        self.assertEqual(capability.manual_compaction_command, "/summarize")
        self.assertEqual(
            capability.pre_compaction_capability, adapters.OBSERVATIONAL_ONLY
        )

    def test_claude_facts(self):
        capability = adapters.get_client("claude")
        self.assertEqual(capability.discovery_path, "~/.claude/skills/save-game")
        self.assertEqual(capability.explicit_invocation, "/save-game")
        self.assertEqual(capability.manual_compaction_command, "/compact")
        self.assertEqual(capability.pre_compaction_capability, adapters.CAN_BLOCK)

    def test_codex_facts_and_honest_acceptance_status(self):
        capability = adapters.get_client("codex")
        self.assertEqual(capability.discovery_path, "~/.codex/skills/save-game")
        self.assertEqual(
            capability.documented_discovery_path, "~/.agents/skills/save-game"
        )
        self.assertEqual(capability.explicit_invocation, "$save-game")
        self.assertEqual(capability.manual_compaction_command, "/compact")
        self.assertEqual(
            capability.pre_compaction_capability, adapters.HALT_ONLY_NO_BLOCK
        )
        self.assertEqual(
            adapters.codex_acceptance_status(),
            "exposed via legacy path, acceptance unverified — pending live discovery canary",
        )
        self.assertEqual(
            capability.acceptance_status, adapters.codex_acceptance_status()
        )

    def test_discovery_path_resolves_under_supplied_home(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            self.assertEqual(
                adapters.discovery_path_for("cursor", home),
                home / ".cursor" / "skills" / "save-game",
            )

    def test_client_lookup_normalizes_case_and_rejects_unknown(self):
        self.assertEqual(adapters.get_client(" Cursor ").client_id, "cursor")
        with self.assertRaisesRegex(KeyError, "unsupported save-game client"):
            adapters.get_client("other")

    def test_hook_capability_classes_are_closed(self):
        observed = {
            capability.pre_compaction_capability
            for capability in adapters.list_clients()
        }
        self.assertEqual(
            observed,
            {
                adapters.OBSERVATIONAL_ONLY,
                adapters.CAN_BLOCK,
                adapters.HALT_ONLY_NO_BLOCK,
            },
        )
        self.assertEqual(observed, adapters.PRE_COMPACTION_CAPABILITY_CLASSES)


if __name__ == "__main__":
    unittest.main()
