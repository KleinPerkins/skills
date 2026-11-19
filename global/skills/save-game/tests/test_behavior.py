"""Mechanical tests for `engine.behavior`: marginal-scope stacking, decision
reversal/scope-change, blocker classification, hygiene evaluation, next-action
determination, and natural stopping. Plain-language behavioral evals live in
`test_behavior_evals.py`."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import _support  # noqa: F401  (adds the skill dir to sys.path)

from engine import behavior, schemas_validate as sv

_CURRENT_SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "engine" / "schemas" / "current.v1.schema.json").read_text())


def _candidate(**overrides):
    defaults = dict(
        summary="tighten an error message",
        estimated_minutes=5,
        estimate_source="agent_estimated",
        local_and_reversible_in_one_patch=True,
        uses_already_authorized_surface=True,
        verification_command="make test",
    )
    defaults.update(overrides)
    return behavior.MarginalScopeCandidate(**defaults)


def _budget(**overrides):
    defaults = dict(consumed_minutes=0, estimate_source="agent_estimated", remaining_minutes_estimate=200)
    defaults.update(overrides)
    return behavior.MarginalScopeBudget(**defaults)


class TestMarginalScope(unittest.TestCase):
    def test_a_clean_small_item_is_accepted_and_budget_is_incremented(self):
        decision = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=5), _budget())
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.updated_budget.consumed_minutes, 5)

    def test_repeated_small_items_stack_and_eventually_get_refused_at_the_flat_cap(self):
        # Three 5-minute items land exactly at the 15-minute cap and must all
        # be accepted; a fourth must be refused because 20 > 15. This is the
        # P2 stacking regression: checking one item in isolation would wrongly
        # accept the fourth too, since 5 <= 15 on its own.
        budget = _budget(remaining_minutes_estimate=10_000)  # large enough that the 10% cap never binds here
        for _ in range(3):
            decision = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=5), budget)
            self.assertTrue(decision.accepted, decision.reasons)
            budget = decision.updated_budget
        self.assertEqual(budget.consumed_minutes, 15)

        fourth = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=5), budget)
        self.assertFalse(fourth.accepted)
        self.assertTrue(any("15-minute cap" in r for r in fourth.reasons), fourth.reasons)
        # Refusal must not mutate the budget further.
        self.assertEqual(fourth.updated_budget.consumed_minutes, 15)

    def test_repeated_small_items_stack_and_eventually_get_refused_at_the_percent_cap(self):
        # remaining_minutes_estimate=40 -> 10% cap is 4 minutes, binding well
        # before the flat 15-minute cap would.
        budget = _budget(remaining_minutes_estimate=40)
        first = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=3), budget)
        self.assertTrue(first.accepted, first.reasons)
        second = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=3), first.updated_budget)
        self.assertFalse(second.accepted)
        self.assertTrue(any("10%" in r for r in second.reasons), second.reasons)

    def test_unknown_item_estimate_fails_closed(self):
        decision = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=None, estimate_source="unknown"), _budget())
        self.assertFalse(decision.accepted)
        self.assertTrue(any("time estimate is not known" in r for r in decision.reasons))

    def test_unknown_remaining_effort_estimate_fails_closed(self):
        decision = behavior.evaluate_marginal_scope(_candidate(), _budget(remaining_minutes_estimate=None, estimate_source="unknown"))
        self.assertFalse(decision.accepted)
        self.assertTrue(any("remaining authorized effort estimate is not known" in r for r in decision.reasons))

    def test_touching_a_named_scope_dimension_is_always_refused(self):
        decision = behavior.evaluate_marginal_scope(_candidate(touches=frozenset({"security"})), _budget())
        self.assertFalse(decision.accepted)
        self.assertTrue(any("security" in r for r in decision.reasons))

    def test_not_local_and_reversible_is_refused(self):
        decision = behavior.evaluate_marginal_scope(_candidate(local_and_reversible_in_one_patch=False), _budget())
        self.assertFalse(decision.accepted)

    def test_no_verification_command_is_refused(self):
        decision = behavior.evaluate_marginal_scope(_candidate(verification_command=None), _budget())
        self.assertFalse(decision.accepted)

    def test_unauthorized_surface_is_refused(self):
        decision = behavior.evaluate_marginal_scope(_candidate(uses_already_authorized_surface=False), _budget())
        self.assertFalse(decision.accepted)

    def test_accepted_budget_dict_is_schema_valid(self):
        decision = behavior.evaluate_marginal_scope(_candidate(), _budget())
        behavior.validate_marginal_scope_budget_dict(decision.updated_budget.to_schema_dict())

    def test_estimate_sources_match_the_frozen_schema_enum(self):
        schema_enum = set(_CURRENT_SCHEMA["properties"]["marginal_scope_budget"]["properties"]["estimate_source"]["enum"])
        self.assertEqual(behavior.ESTIMATE_SOURCES, schema_enum)


class TestDecisionReversal(unittest.TestCase):
    def _decision(self, **overrides):
        defaults = dict(
            decision_id="dec-original01",
            statement="Ship v1 with private-only storage.",
            status="accepted",
            authority=behavior.AuthorityPointer(kind="accepted_plan", locator="plan:save-game-v2#scope", observed_at="2026-08-01T00:00:00Z"),
            revision="rev-1",
        )
        defaults.update(overrides)
        return behavior.Decision(**defaults)

    def test_valid_reversal_replaces_target_with_a_superseding_decision(self):
        original = self._decision()
        request = behavior.DecisionReversalRequest(
            target_decision_id=original.decision_id,
            new_statement="Ship v1 with tracked projections after all.",
            new_revision="rev-2",
            new_authority=behavior.AuthorityPointer(kind="accepted_plan", locator="plan:save-game-v2#scope", observed_at="2026-08-01T01:00:00Z"),
        )
        result = behavior.apply_decision_reversal([original], request)
        self.assertTrue(result.accepted)
        self.assertEqual(result.new_decision.supersedes, original.decision_id)
        self.assertEqual([d.decision_id for d in result.decisions], [result.new_decision.decision_id])

    def test_reversal_against_unknown_decision_id_is_rejected(self):
        request = behavior.DecisionReversalRequest(
            target_decision_id="dec-doesnotexist",
            new_statement="Whatever.",
            new_revision="rev-2",
            new_authority=behavior.AuthorityPointer(locator="plan:x"),
        )
        result = behavior.apply_decision_reversal([self._decision()], request)
        self.assertFalse(result.accepted)
        self.assertIsNone(result.new_decision)

    def test_reversal_against_an_already_superseded_decision_is_rejected(self):
        superseded = self._decision(status="superseded")
        request = behavior.DecisionReversalRequest(
            target_decision_id=superseded.decision_id,
            new_statement="Whatever.",
            new_revision="rev-3",
            new_authority=behavior.AuthorityPointer(locator="plan:x"),
        )
        result = behavior.apply_decision_reversal([superseded], request)
        self.assertFalse(result.accepted)

    def test_reversal_with_no_canonical_source_is_marked_operator_attested_unverifiable(self):
        original = self._decision()
        request = behavior.DecisionReversalRequest(
            target_decision_id=original.decision_id,
            new_statement="Reverse on my word alone.",
            new_revision="rev-2",
            new_authority=behavior.AuthorityPointer(),  # no locator named
            session_or_turn_id="turn-42",
        )
        result = behavior.apply_decision_reversal([original], request)
        self.assertTrue(result.accepted)
        doc = result.new_decision.to_schema_dict()
        self.assertEqual(doc["authority"]["kind"], "other")
        self.assertIn("operator_attested_unverifiable", doc["authority"]["locator"])
        self.assertIn("turn-42", doc["authority"]["locator"])

    def test_new_decision_dict_is_schema_valid(self):
        original = self._decision()
        request = behavior.DecisionReversalRequest(
            target_decision_id=original.decision_id, new_statement="New statement.", new_revision="rev-2",
            new_authority=behavior.AuthorityPointer(locator="plan:x", observed_at="2026-08-01T02:00:00Z"),
        )
        result = behavior.apply_decision_reversal([original], request)
        behavior.validate_decision_dict(result.new_decision.to_schema_dict())

    def test_decision_statuses_match_the_frozen_schema_enum(self):
        schema_enum = set(_CURRENT_SCHEMA["properties"]["decisions"]["items"]["properties"]["status"]["enum"])
        self.assertEqual(behavior.DECISION_STATUSES, schema_enum)


class TestPlanRevisionAndScopeChange(unittest.TestCase):
    def test_no_successor_is_match(self):
        self.assertEqual(behavior.classify_plan_revision("rev-1", []), "MATCH")

    def test_single_valid_successor_with_unchanged_authority_is_advanced(self):
        self.assertEqual(behavior.classify_plan_revision("rev-1", ["rev-2"]), "ADVANCED")

    def test_two_competing_successors_is_conflict(self):
        self.assertEqual(behavior.classify_plan_revision("rev-1", ["rev-2", "rev-3"]), "CONFLICT")

    def test_changed_authority_is_unknown_not_conflict(self):
        self.assertEqual(behavior.classify_plan_revision("rev-1", ["rev-2"], authority_unchanged=False), "UNKNOWN")

    def test_scope_removal_moves_to_deferred_without_operator_authority(self):
        result = behavior.apply_scope_change(behavior.ScopeChangeRequest(kind="removal", summary="drop the CSV export idea"), _budget())
        self.assertTrue(result.accepted)
        self.assertTrue(result.moves_to_deferred)
        self.assertFalse(result.requires_operator_authority)

    def test_scope_expansion_within_marginal_budget_is_accepted_without_asking(self):
        request = behavior.ScopeChangeRequest(kind="expansion", summary="add a docstring", marginal_candidate=_candidate())
        result = behavior.apply_scope_change(request, _budget())
        self.assertTrue(result.accepted)
        self.assertFalse(result.requires_operator_authority)
        self.assertIsNotNone(result.updated_budget)

    def test_scope_expansion_outside_marginal_budget_requires_operator_authority(self):
        request = behavior.ScopeChangeRequest(kind="expansion", summary="add a new endpoint", marginal_candidate=_candidate(touches=frozenset({"public_api"})))
        result = behavior.apply_scope_change(request, _budget())
        self.assertFalse(result.accepted)
        self.assertTrue(result.requires_operator_authority)

    def test_scope_expansion_with_no_candidate_supplied_requires_operator_authority(self):
        result = behavior.apply_scope_change(behavior.ScopeChangeRequest(kind="expansion", summary="mystery work"), _budget())
        self.assertTrue(result.requires_operator_authority)


class TestBlockerClassification(unittest.TestCase):
    def test_each_named_blocker_kind_is_classified_as_a_true_blocker(self):
        flag_names = [attr for attr, _kind in behavior._SIGNAL_TO_KIND]
        for attr, kind in behavior._SIGNAL_TO_KIND:
            signal = behavior.DifficultySignal(description="something happened", **{attr: True})
            result = behavior.classify_blocker(signal)
            self.assertEqual(result.classification, "true_blocker")
            self.assertEqual(result.kind, kind)
            self.assertFalse(result.continue_autonomously)
        self.assertEqual(len(flag_names), len(behavior.BLOCKER_KINDS))

    def test_ordinary_difficulty_with_no_blocker_flags_continues_autonomously(self):
        signal = behavior.DifficultySignal(description="a unit test is failing on an edge case")
        result = behavior.classify_blocker(signal)
        self.assertEqual(result.classification, "ordinary_difficulty")
        self.assertIsNone(result.kind)
        self.assertTrue(result.continue_autonomously)

    def test_true_blocker_to_schema_dict_is_schema_valid(self):
        signal = behavior.DifficultySignal(description="the API token was rejected", definitive_access_denial=True)
        result = behavior.classify_blocker(signal)
        doc = result.to_schema_dict()
        self.assertEqual(doc["kind"], "access_denial")
        behavior.validate_blocker_dict(doc)

    def test_ordinary_difficulty_to_schema_dict_is_none(self):
        result = behavior.classify_blocker(behavior.DifficultySignal(description="fine"))
        self.assertIsNone(result.to_schema_dict())

    def test_transient_failure_sequence_retry_then_alternative_then_escalate(self):
        self.assertEqual(behavior.transient_failure_next_step(0, False), "retry_same_operation")
        self.assertEqual(behavior.transient_failure_next_step(1, False), "try_materially_different_alternative")
        self.assertEqual(behavior.transient_failure_next_step(1, True), "escalate_or_reclassify")

    def test_exhausting_retry_and_alternative_does_not_by_itself_become_a_blocker(self):
        # Plan: failing tests/implementation difficulty/discoverable unknowns/
        # recoverable tool errors remain executable work, not blockers -- even
        # after "escalate_or_reclassify", classify_blocker alone never invents
        # a blocker kind that wasn't independently signaled.
        self.assertEqual(behavior.transient_failure_next_step(1, True), "escalate_or_reclassify")
        result = behavior.classify_blocker(behavior.DifficultySignal(description="the flaky integration test failed again"))
        self.assertEqual(result.classification, "ordinary_difficulty")

    def test_blocker_kinds_match_the_frozen_schema_enum(self):
        schema_enum = set(_CURRENT_SCHEMA["properties"]["blockers"]["items"]["properties"]["kind"]["enum"])
        self.assertEqual(set(behavior.BLOCKER_KINDS), schema_enum)

    def test_blocker_classification_from_persisted_reconstructs_every_kind(self):
        for _attr, kind in behavior._SIGNAL_TO_KIND:
            reconstructed = behavior.blocker_classification_from_persisted({"description": "waiting on you", "kind": kind})
            self.assertEqual(reconstructed.classification, "true_blocker")
            self.assertEqual(reconstructed.kind, kind)
            self.assertFalse(reconstructed.continue_autonomously)
            self.assertEqual(reconstructed.description, "waiting on you")

    def test_blocker_classification_from_persisted_round_trips_through_to_schema_dict(self):
        original = behavior.classify_blocker(behavior.DifficultySignal(description="the API token was rejected", definitive_access_denial=True))
        persisted = original.to_schema_dict()
        reconstructed = behavior.blocker_classification_from_persisted(persisted)
        self.assertEqual(reconstructed, original)

    def test_blocker_classification_from_persisted_rejects_an_unrecognized_kind(self):
        with self.assertRaises(ValueError):
            behavior.blocker_classification_from_persisted({"description": "?", "kind": "not_a_real_kind"})


class TestHygieneEvaluation(unittest.TestCase):
    def _all_clear_kwargs(self, **overrides):
        defaults = dict(
            transactions_finalized=True,
            temp_files_clear=True,
            spawned_process_state_known=True,
            spawned_process_evidence="no background processes were started this session",
            repo_status_observed=True,
            required_checks_run=True,
            no_unclassified_delta=True,
        )
        defaults.update(overrides)
        return defaults

    def test_all_clear_report_is_all_clear(self):
        report = behavior.evaluate_hygiene(**self._all_clear_kwargs())
        self.assertTrue(report.all_clear)
        self.assertEqual(report.failing(), [])

    def test_pending_transaction_fails_hygiene(self):
        report = behavior.evaluate_hygiene(**self._all_clear_kwargs(transactions_finalized=False))
        self.assertFalse(report.all_clear)
        self.assertIn("transactions_finalized", [c.condition for c in report.failing()])

    def test_unknown_spawned_process_state_fails_hygiene_even_if_temp_files_are_clear(self):
        report = behavior.evaluate_hygiene(
            **self._all_clear_kwargs(spawned_process_state_known=False, spawned_process_evidence="a background watcher's exit was never confirmed")
        )
        self.assertFalse(report.all_clear)
        self.assertIn("spawned_process_state_known", [c.condition for c in report.failing()])
        # And it must fold into the SCHEMA's single temp_artifacts_clear flag as false,
        # even though temp_files_clear itself is true -- the schema has no separate slot.
        self.assertFalse(report.to_schema_dict()["temp_artifacts_clear"])

    def test_unclassified_delta_polarity_is_inverted_in_the_schema_dict(self):
        clear = behavior.evaluate_hygiene(**self._all_clear_kwargs(no_unclassified_delta=True))
        self.assertFalse(clear.to_schema_dict()["unclassified_delta"])
        dirty = behavior.evaluate_hygiene(**self._all_clear_kwargs(no_unclassified_delta=False))
        self.assertTrue(dirty.to_schema_dict()["unclassified_delta"])

    def test_every_condition_the_plan_defines_is_enumerated(self):
        report = behavior.evaluate_hygiene(**self._all_clear_kwargs())
        self.assertEqual(tuple(c.condition for c in report.conditions), behavior.HYGIENE_CONDITIONS)

    def test_all_clear_schema_dict_is_schema_valid(self):
        report = behavior.evaluate_hygiene(**self._all_clear_kwargs())
        behavior.validate_hygiene_dict(report.to_schema_dict())

    def test_failing_report_still_produces_a_schema_valid_dict(self):
        report = behavior.evaluate_hygiene(**self._all_clear_kwargs(required_checks_run=False, required_checks_evidence="make test not yet run"))
        behavior.validate_hygiene_dict(report.to_schema_dict())

    def test_hygiene_report_from_persisted_round_trips_an_all_clear_document(self):
        original = behavior.evaluate_hygiene(**self._all_clear_kwargs())
        reconstructed = behavior.hygiene_report_from_persisted(original.to_schema_dict())
        self.assertTrue(reconstructed.all_clear)
        self.assertEqual(reconstructed.to_schema_dict(), original.to_schema_dict())

    def test_hygiene_report_from_persisted_round_trips_a_dirty_document(self):
        original = behavior.evaluate_hygiene(**self._all_clear_kwargs(required_checks_run=False, no_unclassified_delta=False))
        reconstructed = behavior.hygiene_report_from_persisted(original.to_schema_dict())
        self.assertFalse(reconstructed.all_clear)
        self.assertEqual(reconstructed.to_schema_dict(), original.to_schema_dict())

    def test_hygiene_report_from_persisted_collapses_temp_and_process_bits_together(self):
        # Documented lossy projection: the persisted document has only ONE bit
        # (temp_artifacts_clear) for what evaluate_hygiene tracks as two
        # separate conditions -- reconstruction mirrors that one bit onto both.
        doc = {
            "transactions_finalized": True, "temp_artifacts_clear": False,
            "repo_status_observed": True, "required_checks_run": True, "unclassified_delta": False,
        }
        reconstructed = behavior.hygiene_report_from_persisted(doc)
        failing_names = {c.condition for c in reconstructed.failing()}
        self.assertEqual(failing_names, {"temp_files_clear", "spawned_process_state_known"})


class TestNextActions(unittest.TestCase):
    def test_bounded_to_three(self):
        candidates = [behavior.CandidateAction(description=f"do thing {i}") for i in range(5)]
        result = behavior.determine_next_actions(candidates, hygiene_required=False)
        self.assertEqual(len(result), 3)

    def test_hygiene_candidates_precede_feature_work_when_hygiene_required(self):
        candidates = [
            behavior.CandidateAction(description="ship the feature"),
            behavior.CandidateAction(description="finalize the pending save transaction", is_hygiene=True),
        ]
        result = behavior.determine_next_actions(candidates, hygiene_required=True)
        self.assertEqual(result[0]["description"], "finalize the pending save transaction")

    def test_hygiene_ordering_not_applied_when_hygiene_not_required(self):
        candidates = [
            behavior.CandidateAction(description="ship the feature"),
            behavior.CandidateAction(description="finalize the pending save transaction", is_hygiene=True),
        ]
        result = behavior.determine_next_actions(candidates, hygiene_required=False)
        self.assertEqual(result[0]["description"], "ship the feature")

    def test_unauthorized_and_dependency_unsatisfied_candidates_are_excluded(self):
        candidates = [
            behavior.CandidateAction(description="not authorized yet", authorized=False),
            behavior.CandidateAction(description="blocked on something else", dependency_satisfied=False),
            behavior.CandidateAction(description="ready to go"),
        ]
        result = behavior.determine_next_actions(candidates, hygiene_required=False)
        self.assertEqual(result, [{"description": "ready to go"}])

    def test_result_is_schema_valid(self):
        candidates = [behavior.CandidateAction(description="write more tests", owner="agent", completion_test="make test passes")]
        result = behavior.determine_next_actions(candidates, hygiene_required=False)
        behavior.validate_next_actions_list(result)


class TestNaturalStopping(unittest.TestCase):
    def _clear_hygiene(self):
        return behavior.evaluate_hygiene(
            transactions_finalized=True, temp_files_clear=True, spawned_process_state_known=True,
            spawned_process_evidence="none started", repo_status_observed=True, required_checks_run=True,
            no_unclassified_delta=True,
        )

    def test_operator_stop_takes_precedence(self):
        result = behavior.determine_stopping(
            operator_requested_stop=True, blockers=[], acceptance_complete=True, hygiene=self._clear_hygiene(), next_actions=[{"description": "x"}]
        )
        self.assertEqual(result.outcome, "operator_stop")

    def test_genuine_blocker_reported_when_present(self):
        blocker = behavior.classify_blocker(behavior.DifficultySignal(description="need a decision", operator_decision_required=True))
        result = behavior.determine_stopping(
            operator_requested_stop=False, blockers=[blocker], acceptance_complete=False, hygiene=self._clear_hygiene(), next_actions=[]
        )
        self.assertEqual(result.outcome, "genuine_blocker")

    def test_acceptance_and_hygiene_complete(self):
        result = behavior.determine_stopping(
            operator_requested_stop=False, blockers=[], acceptance_complete=True, hygiene=self._clear_hygiene(), next_actions=[]
        )
        self.assertEqual(result.outcome, "acceptance_and_hygiene_complete")

    def test_no_authorized_action_remains(self):
        dirty_hygiene = behavior.evaluate_hygiene(
            transactions_finalized=True, temp_files_clear=True, spawned_process_state_known=True,
            spawned_process_evidence="none started", repo_status_observed=True, required_checks_run=False,
            required_checks_evidence="not run yet", no_unclassified_delta=True,
        )
        result = behavior.determine_stopping(
            operator_requested_stop=False, blockers=[], acceptance_complete=False, hygiene=dirty_hygiene, next_actions=[]
        )
        self.assertEqual(result.outcome, "no_authorized_action_remains")

    def test_continue_when_a_next_action_remains(self):
        result = behavior.determine_stopping(
            operator_requested_stop=False, blockers=[], acceptance_complete=False, hygiene=self._clear_hygiene(),
            next_actions=[{"description": "keep going"}],
        )
        self.assertEqual(result.outcome, "continue")

    def test_outcomes_are_exactly_the_five_named_by_the_plan(self):
        self.assertEqual(
            set(behavior.STOPPING_OUTCOMES),
            {"acceptance_and_hygiene_complete", "genuine_blocker", "operator_stop", "no_authorized_action_remains", "continue"},
        )


class TestSchemaFragmentHelper(unittest.TestCase):
    def test_unknown_field_path_raises_rather_than_silently_passing(self):
        with self.assertRaises(KeyError):
            behavior.validate_current_fragment({}, "properties", "not_a_real_field")

    def test_validator_actually_rejects_a_bad_instance(self):
        with self.assertRaises(sv.SchemaValidationError):
            behavior.validate_hygiene_dict({"transactions_finalized": "not-a-bool"})


if __name__ == "__main__":
    unittest.main()
