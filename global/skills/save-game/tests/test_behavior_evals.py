"""Plain-language receipt behavioral evals (plan: M4 gate "plain-language
receipt behavioral evals"; verification strategy "Behavioral evals": ...
plain-language receipts...).

Scripted scenarios feed representative state through `engine.behavior`'s
functions and assert that whatever they return for surfacing to an operator
(`.plain_language()` / `.reason`) reads in plain language: no internal
jargon/schema-field tokens, and no overclaim implying Git delivery,
compaction, or worktree retention from what is, at most, a private save.
Cross-checked at the end against a REAL Flush receipt's own `negative_claims`
(plan: SKILL.md tone -- "jargon-free, honest about confidence, no bare
status claims")."""

from __future__ import annotations

import re
import unittest

import _support

from engine import behavior, flush, identity as identity_mod

# Raw internal/schema tokens that must never leak into operator-facing plain
# language (they are fine in schema DICTS, which are machine-readable, but
# not in `.plain_language()`/`.reason` strings). Matched with a word boundary
# so e.g. "CAS" doesn't false-positive on "case".
BANNED_JARGON_TERMS = [
    "unclassified_delta", "marginal_scope_budget", "workstream_key", "consumed_minutes",
    "estimate_source", "operator_set", "agent_estimated", "operator_attested_unverifiable",
    "decision_id", "checkpoint_id", "receipt_id", "O_EXCL", "F_FULLFSYNC", "fsync", "flock",
    r"\bCAS\b", "canonical_bytes", "current\\.json", r"\bschema\b",
]

# Phrases that would overclaim beyond what a private save-only operation
# means (plan: Flush contract "negative_claims"; pre-mortem "Operators stop
# trusting receipts").
BANNED_OVERCLAIM_PHRASES = [
    "git-delivered", "git delivered", "pushed to", "committed to", "pull request",
    "merged", "cross-machine", "compacted", "compaction occurred", "compaction completed",
    "compaction ran", "worktree-retained", "worktree retained", "retained",
]


class PlainLanguageTestCase(unittest.TestCase):
    def assert_plain_language(self, text: str, *, context: str = ""):
        self.assertTrue(text and text.strip(), f"empty plain-language text ({context})")
        lowered = text.lower()
        for term in BANNED_JARGON_TERMS:
            self.assertIsNone(
                re.search(term, text, re.IGNORECASE),
                f"jargon term {term!r} leaked into plain-language text ({context}): {text!r}",
            )
        for phrase in BANNED_OVERCLAIM_PHRASES:
            self.assertNotIn(phrase, lowered, f"overclaiming phrase {phrase!r} found in plain-language text ({context}): {text!r}")


def _budget(**overrides):
    defaults = dict(consumed_minutes=0, estimate_source="agent_estimated", remaining_minutes_estimate=200)
    defaults.update(overrides)
    return behavior.MarginalScopeBudget(**defaults)


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


def _clear_hygiene():
    return behavior.evaluate_hygiene(
        transactions_finalized=True, temp_files_clear=True, spawned_process_state_known=True,
        spawned_process_evidence="no background processes were started this session",
        repo_status_observed=True, required_checks_run=True, no_unclassified_delta=True,
    )


class TestMarginalScopeScenarios(PlainLanguageTestCase):
    def test_scenario_small_item_absorbed_reads_plainly(self):
        decision = behavior.evaluate_marginal_scope(_candidate(summary="fix a typo in a log message"), _budget())
        text = decision.plain_language()
        self.assert_plain_language(text, context="marginal-scope accept")
        self.assertIn("fix a typo in a log message", text)

    def test_scenario_stacked_item_refused_at_the_cap_reads_plainly_and_does_not_overclaim(self):
        budget = _budget(remaining_minutes_estimate=10_000)
        for _ in range(3):
            decision = behavior.evaluate_marginal_scope(_candidate(estimated_minutes=5), budget)
            budget = decision.updated_budget
        refused = behavior.evaluate_marginal_scope(_candidate(summary="one more small cleanup", estimated_minutes=5), budget)
        text = refused.plain_language()
        self.assert_plain_language(text, context="marginal-scope stacked refusal")
        self.assertIn("surfacing for your decision", text)


class TestDecisionReversalScenarios(PlainLanguageTestCase):
    def _original(self):
        return behavior.Decision(
            decision_id="dec-original01",
            statement="Ship v1 with private-only storage.",
            status="accepted",
            authority=behavior.AuthorityPointer(kind="accepted_plan", locator="plan:save-game-v2#scope", observed_at="2026-08-01T00:00:00Z"),
            revision="rev-1",
        )

    def test_scenario_accepted_reversal_reads_plainly(self):
        original = self._original()
        request = behavior.DecisionReversalRequest(
            target_decision_id=original.decision_id, new_statement="Ship v1 with tracked projections instead.",
            new_revision="rev-2", new_authority=behavior.AuthorityPointer(locator="plan:save-game-v2#scope", observed_at="2026-08-01T01:00:00Z"),
        )
        result = behavior.apply_decision_reversal([original], request)
        text = result.plain_language()
        self.assert_plain_language(text, context="decision reversal accepted")

    def test_scenario_rejected_reversal_reads_plainly(self):
        request = behavior.DecisionReversalRequest(
            target_decision_id="dec-not-real", new_statement="x", new_revision="rev-9",
            new_authority=behavior.AuthorityPointer(locator="plan:x"),
        )
        result = behavior.apply_decision_reversal([self._original()], request)
        text = result.plain_language()
        self.assert_plain_language(text, context="decision reversal rejected")

    def test_scenario_unverifiable_reversal_plain_language_omits_the_raw_marker_even_though_the_schema_dict_carries_it(self):
        original = self._original()
        request = behavior.DecisionReversalRequest(
            target_decision_id=original.decision_id, new_statement="Reverse on the operator's word alone.",
            new_revision="rev-2", new_authority=behavior.AuthorityPointer(), session_or_turn_id="turn-7",
        )
        result = behavior.apply_decision_reversal([original], request)
        text = result.plain_language()
        self.assert_plain_language(text, context="unverifiable decision reversal")
        # The machine-readable schema dict legitimately carries the internal
        # marker; the operator-facing text must not.
        self.assertIn("operator_attested_unverifiable", result.new_decision.to_schema_dict()["authority"]["locator"])
        self.assertNotIn("operator_attested_unverifiable", text)


class TestBlockerScenarios(PlainLanguageTestCase):
    def test_scenario_ordinary_difficulty_reads_plainly_and_signals_continuation(self):
        result = behavior.classify_blocker(behavior.DifficultySignal(description="three integration tests are failing on a timing edge case"))
        text = result.plain_language()
        self.assert_plain_language(text, context="ordinary difficulty")
        self.assertIn("Not a blocker", text)

    def test_scenario_true_blocker_names_the_problem_in_plain_words(self):
        result = behavior.classify_blocker(behavior.DifficultySignal(description="the deploy credential was rejected", definitive_access_denial=True))
        text = result.plain_language()
        self.assert_plain_language(text, context="true blocker")
        self.assertIn("access", text.lower())


class TestHygieneScenarios(PlainLanguageTestCase):
    def test_scenario_all_clear_reads_plainly_and_does_not_overclaim_delivery_or_compaction(self):
        text = _clear_hygiene().plain_language()
        self.assert_plain_language(text, context="hygiene all clear")

    def test_scenario_unknown_process_state_reads_plainly(self):
        report = behavior.evaluate_hygiene(
            transactions_finalized=True, temp_files_clear=True, spawned_process_state_known=False,
            spawned_process_evidence="a background watcher's exit was never confirmed from this session's own tool calls",
            repo_status_observed=True, required_checks_run=True, no_unclassified_delta=True,
        )
        text = report.plain_language()
        self.assert_plain_language(text, context="hygiene unknown process state")
        self.assertIn("background processes", text)


class TestNaturalStoppingScenarios(PlainLanguageTestCase):
    def test_all_five_outcomes_read_plainly(self):
        scenarios = [
            behavior.determine_stopping(operator_requested_stop=True, blockers=[], acceptance_complete=False, hygiene=_clear_hygiene(), next_actions=[]),
            behavior.determine_stopping(
                operator_requested_stop=False,
                blockers=[behavior.classify_blocker(behavior.DifficultySignal(description="need a canonical-source decision", canonical_source_conflict=True))],
                acceptance_complete=False, hygiene=_clear_hygiene(), next_actions=[],
            ),
            behavior.determine_stopping(operator_requested_stop=False, blockers=[], acceptance_complete=True, hygiene=_clear_hygiene(), next_actions=[]),
            behavior.determine_stopping(operator_requested_stop=False, blockers=[], acceptance_complete=False, hygiene=_clear_hygiene(), next_actions=[]),
            behavior.determine_stopping(
                operator_requested_stop=False, blockers=[], acceptance_complete=False, hygiene=_clear_hygiene(),
                next_actions=[{"description": "keep going"}],
            ),
        ]
        outcomes = {s.outcome for s in scenarios}
        self.assertEqual(outcomes, set(behavior.STOPPING_OUTCOMES))
        for scenario in scenarios:
            self.assert_plain_language(scenario.plain_language(), context=f"natural stopping: {scenario.outcome}")


class TestCrossCheckAgainstFlushNegativeClaims(PlainLanguageTestCase):
    """Ties this module's own plain language to a REAL Flush receipt's public
    `negative_claims` field rather than a sibling module's private constants
    -- if flush.py's negative-claims wording ever changes, this test reads
    the live receipt, not a copy."""

    def setUp(self):
        self._xdg = _support.isolated_xdg_roots()
        self.tmp = self._xdg.__enter__()
        self.repo = _support.make_git_repo(self.tmp, branch="main")
        self.identity = identity_mod.resolve_root_identity(str(self.repo))
        self.repo_key = identity_mod.repo_key_for(self.identity)
        self.clone_key = identity_mod.clone_key_for(self.identity)
        self.workstream_key = identity_mod.workstream_key_for(self.repo_key, self.clone_key, "task-eval-crosscheck", self.identity)

    def tearDown(self):
        self._xdg.__exit__(None, None, None)

    def test_save_only_scenario_plain_language_is_consistent_with_the_real_receipts_negative_claims(self):
        def build(_current_doc):
            return {
                "schema": "save-game-current/v1",
                "task_id": "task-eval-crosscheck",
                "workstream_key": self.workstream_key,
                "root": identity_mod.root_snapshot_dict(self.identity),
                "objective": "Prove the private save-only status never overclaims.",
                "scope": {"in_scope": [], "non_scope": [], "deferred": []},
                "hygiene": {
                    "transactions_finalized": True, "temp_artifacts_clear": True, "repo_status_observed": True,
                    "required_checks_run": True, "unclassified_delta": False,
                },
                "blockers": [],
                "next_actions": [{"description": "Write the next behavioral eval"}],
                "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
                "status": "active",
            }

        receipt = flush.run_flush(
            self.repo_key, self.clone_key, self.workstream_key, identity=self.identity, build_candidate_fn=build,
        )
        self.assertIn(receipt["status"], ("SAVED", "SAVED_PRIVATE_UNADOPTED"))
        negative_claims_text = " ".join(receipt["negative_claims"]).lower()
        # Sanity that there is a real negative claim to be consistent WITH.
        # Note the real receipt's own negative-claims text legitimately NAMES
        # "delivered"/"compacted"/etc. in order to DENY them (e.g. "it never
        # means Git-delivered...") -- that sentence is exempt from the
        # banned-phrase filter below, which instead guards THIS module's own
        # operator-facing output, which must not assert them at all, denial
        # or otherwise.
        self.assertIn("never means", negative_claims_text)

        stopping = behavior.determine_stopping(
            operator_requested_stop=False, blockers=[], acceptance_complete=True, hygiene=_clear_hygiene(), next_actions=[],
        )
        text = stopping.plain_language()
        self.assert_plain_language(text, context="cross-check stopping narrative")
        self.assertNotIn("saved", text.lower())  # doesn't even claim the narrow SAVED status itself


if __name__ == "__main__":
    unittest.main()
