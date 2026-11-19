"""Tests for the Compact Decision contract: the ORDERED rule set (plan: "Rules,
in order") over hard gates, operator request, and verified pressure/continuation
signals — not a scored heuristic. Each test isolates exactly one rule."""

from __future__ import annotations

import unittest

from engine.compact_decision import CompactDecisionInputs, evaluate


class TestRuleOrder(unittest.TestCase):
    def test_rule1_task_completed_wins_even_with_high_pressure(self):
        inputs = CompactDecisionInputs(task_completed_or_topic_change=True, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "NEW_CHAT_RECOMMENDED")

    def test_rule1_wins_even_over_explicit_no_compact(self):
        inputs = CompactDecisionInputs(task_completed_or_topic_change=True, operator_request="no_compact")
        result = evaluate(inputs)
        self.assertEqual(result.status, "NEW_CHAT_RECOMMENDED")

    def test_rule2_explicit_no_compact_wins_over_high_pressure(self):
        inputs = CompactDecisionInputs(operator_request="no_compact", pressure_source="client_metric", pressure_percent=99, continuation_count=10)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_rule3_explicit_compact_after_hard_gates_pass(self):
        inputs = CompactDecisionInputs(operator_request="compact")
        result = evaluate(inputs)
        self.assertEqual(result.status, "COMPACTION_REQUIRED")

    def test_rule3_explicit_compact_blocked_by_failed_hard_gate(self):
        inputs = CompactDecisionInputs(operator_request="compact", active_tool_or_action=True)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_hard_gate_privacy_failure_forces_save_only(self):
        inputs = CompactDecisionInputs(privacy_failure=True, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_hard_gate_incomplete_transaction_forces_save_only(self):
        inputs = CompactDecisionInputs(incomplete_transaction=True, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_hard_gate_authority_conflict_forces_save_only(self):
        inputs = CompactDecisionInputs(authority_conflict=True, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_hard_gate_flush_and_index_not_finalized_forces_save_only(self):
        inputs = CompactDecisionInputs(flush_and_index_finalized=False, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_hard_gate_different_logical_task_forces_save_only(self):
        inputs = CompactDecisionInputs(same_logical_task=False, pressure_source="client_metric", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_rule4_verified_pressure_at_80_with_two_actions_requires_compaction(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=80, continuation_count=2)
        result = evaluate(inputs)
        self.assertEqual(result.status, "COMPACTION_REQUIRED")

    def test_rule4_pressure_above_80_with_only_one_action_does_not_require(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=90, continuation_count=1)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")  # below rule 4's continuation floor and outside rule 5's 60-79 band

    def test_rule5_pressure_60_to_79_with_four_actions_recommends(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=65, continuation_count=4)
        result = evaluate(inputs)
        self.assertEqual(result.status, "RECOMMEND_COMPACTION")

    def test_rule5_pressure_60_to_79_with_explicit_cross_session_continuation_recommends(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=70, continuation_count=1, explicit_cross_session_continuation=True)
        result = evaluate(inputs)
        self.assertEqual(result.status, "RECOMMEND_COMPACTION")

    def test_rule5_pressure_60_to_79_with_short_continuation_and_no_cross_session_is_save_only(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=65, continuation_count=1)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_rule6_unknown_pressure_source_is_save_only_even_if_percent_given(self):
        inputs = CompactDecisionInputs(pressure_source="unknown", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")
        self.assertIsNone(result.pressure_percent)  # never invent/pass through a percentage for unknown source

    def test_rule6_below_every_threshold_is_save_only(self):
        inputs = CompactDecisionInputs(pressure_source="client_metric", pressure_percent=10, continuation_count=0)
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_invalid_pressure_source_is_normalized_to_unknown(self):
        inputs = CompactDecisionInputs(pressure_source="made_up_source", pressure_percent=95, continuation_count=5)
        result = evaluate(inputs)
        self.assertEqual(result.pressure_source, "unknown")
        self.assertEqual(result.status, "SAVE_ONLY")

    def test_invalid_operator_request_is_normalized_to_unspecified(self):
        inputs = CompactDecisionInputs(operator_request="made_up_request")
        result = evaluate(inputs)
        self.assertEqual(result.status, "SAVE_ONLY")  # falls through to rule 6, not treated as compact/no_compact


class TestCheckpointCompactionProjection(unittest.TestCase):
    def test_as_checkpoint_compaction_lowercases_status_and_keeps_enum_values_valid(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact"))
        doc = result.as_checkpoint_compaction()
        self.assertEqual(doc["status"], "compaction_required")
        self.assertEqual(doc["pressure_source"], "unknown")
        self.assertNotIn("pressure_percent", doc)

    def test_as_checkpoint_compaction_includes_pressure_percent_when_verified(self):
        result = evaluate(CompactDecisionInputs(pressure_source="client_metric", pressure_percent=65, continuation_count=4))
        doc = result.as_checkpoint_compaction()
        self.assertEqual(doc["status"], "recommend_compaction")
        self.assertEqual(doc["pressure_percent"], 65)

    def test_every_status_lowercases_to_a_valid_checkpoint_enum_value(self):
        valid = {"unknown", "save_only", "recommend_compaction", "compaction_required", "new_chat_recommended"}
        cases = [
            CompactDecisionInputs(task_completed_or_topic_change=True),
            CompactDecisionInputs(operator_request="no_compact"),
            CompactDecisionInputs(operator_request="compact"),
            CompactDecisionInputs(pressure_source="client_metric", pressure_percent=80, continuation_count=2),
            CompactDecisionInputs(pressure_source="client_metric", pressure_percent=65, continuation_count=4),
            CompactDecisionInputs(),
        ]
        for inputs in cases:
            doc = evaluate(inputs).as_checkpoint_compaction()
            self.assertIn(doc["status"], valid)


class TestClientCapabilityWiring(unittest.TestCase):
    """Plan verification gates "exact manual command" and "unsupported client
    capability": `adapters.py` is consulted for enrichment, but per the module
    docstring, capability never changes WHICH status is returned — only the
    manual command / hook-capability class attached to the result."""

    def test_known_client_id_resolves_exact_manual_command_and_capability_class(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id="claude"))
        self.assertEqual(result.manual_compaction_command, "/compact")
        self.assertEqual(result.pre_compaction_capability, "can_block")
        self.assertTrue(result.client_capability_known)
        self.assertEqual(result.client_id, "claude")

    def test_cursor_resolves_summarize_command_and_observational_only_capability(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id="cursor"))
        self.assertEqual(result.manual_compaction_command, "/summarize")
        self.assertEqual(result.pre_compaction_capability, "observational_only")

    def test_codex_resolves_compact_command_and_halt_only_no_block_capability(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id="codex"))
        self.assertEqual(result.manual_compaction_command, "/compact")
        self.assertEqual(result.pre_compaction_capability, "halt_only_no_block")

    def test_no_client_id_leaves_capability_fields_unresolved_not_crashed(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact"))
        self.assertIsNone(result.client_id)
        self.assertIsNone(result.manual_compaction_command)
        self.assertIsNone(result.pre_compaction_capability)
        self.assertFalse(result.client_capability_known)

    def test_unsupported_client_id_degrades_safely_instead_of_raising(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id="some-future-client"))
        self.assertEqual(result.status, "COMPACTION_REQUIRED")  # the rule set still ran normally
        self.assertEqual(result.client_id, "some-future-client")  # caller's literal input is preserved for the receipt
        self.assertIsNone(result.manual_compaction_command)
        self.assertIsNone(result.pre_compaction_capability)
        self.assertFalse(result.client_capability_known)

    def test_capability_enrichment_never_changes_the_status_outcome(self):
        # Same inputs, only client_id varies across every known + unknown +
        # absent case -- status and pressure fields must be identical throughout.
        base = dict(pressure_source="client_metric", pressure_percent=65, continuation_count=4)
        statuses = {
            client_id: evaluate(CompactDecisionInputs(client_id=client_id, **base)).status
            for client_id in (None, "cursor", "claude", "codex", "unrecognized")
        }
        self.assertEqual(len(set(statuses.values())), 1)
        self.assertEqual(next(iter(statuses.values())), "RECOMMEND_COMPACTION")

    def test_capability_enrichment_is_stripped_from_the_persisted_checkpoint_projection(self):
        # checkpoint.v1's `compaction` field is closed (status/pressure_source/
        # pressure_percent only) -- enrichment is CLI/receipt-facing, never
        # written to the immutable schema.
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id="claude"))
        doc = result.as_checkpoint_compaction()
        self.assertEqual(set(doc), {"status", "pressure_source"})

    def test_client_id_is_case_and_whitespace_insensitive_like_adapters_get_client(self):
        result = evaluate(CompactDecisionInputs(operator_request="compact", client_id=" Claude "))
        self.assertTrue(result.client_capability_known)
        self.assertEqual(result.manual_compaction_command, "/compact")


if __name__ == "__main__":
    unittest.main()
