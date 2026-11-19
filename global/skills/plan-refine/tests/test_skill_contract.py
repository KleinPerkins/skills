from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = re.sub(
    r"\s+",
    " ",
    (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8"),
)


def must_have(case: unittest.TestCase, pattern: str) -> None:
    case.assertRegex(SKILL, re.compile(pattern, re.MULTILINE | re.DOTALL))


def must_not_have(case: unittest.TestCase, pattern: str) -> None:
    case.assertNotRegex(SKILL, re.compile(pattern, re.MULTILINE | re.DOTALL))


class PlanRefineDoctrineContractTests(unittest.TestCase):
    """These tests pin the written contract in SKILL.md.

    They do NOT claim to validate model runtime behavior. They only ensure the
    doctrine text covering the reviewed scenarios remains present and mutually
    consistent.
    """

    def test_scenario_mutable_draft_and_versioned_plan_edit_in_place(self):
        must_have(self, r"Draft/mutable plan: edit in place")
        must_have(self, r"advance the in-file version marker")
        must_not_have(self, r"advance it one version")
        must_not_have(self, r"edit the plan in place")
        must_not_have(self, r"edit-in-place")

    def test_scenario_accepted_plan_is_immutable_and_requires_successor_file(self):
        must_have(self, r"Accepted/immutable plan")
        must_have(self, r"create the next convention-required successor file")
        must_have(self, r"update the README index row")
        must_not_have(self, r"may mutate only the governed target plan artifact")
        must_not_have(self, r"the only file you may write is the target plan itself")
        must_not_have(self, r"it is the only artifact this skill may mutate")
        must_not_have(self, r"correction per issue(?:\*\*)? to the plan in place")

    def test_scenario_assessment_only_request_is_read_only(self):
        must_have(self, r'Assessment-only requests such as "review" or "is this ready\?" must not silently edit')
        must_have(self, r"return findings and proposed changes without mutating")
        must_have(
            self,
            r"Mode A — Standalone.*For assessment-only intent, return findings and proposed changes without mutation",
        )

    def test_scenario_implementation_started_routes_elsewhere(self):
        must_have(self, r"Verify the target plan is still pre-implementation")
        must_have(self, r"If implementation has already started, stop this workflow")

    def test_scenario_policy_denies_access_despite_approval(self):
        must_have(self, r"authorization model stated plainly and derived from project policy")
        must_have(self, r"approval never substitutes for actual authorization")
        must_have(self, r"least privilege")

    def test_scenario_retention_copy_is_narrow_and_parallel_forks_stay_forbidden(self):
        must_have(self, r"narrow retention-copy exception")
        must_have(self, r"byte-identical prior version")
        must_have(self, r"DON'T fork unrelated or divergent parallel plan branches")

    def test_multiple_plausible_target_plans_require_a_question(self):
        must_have(self, r"If multiple plausible target plans exist, ask rather than ranking by recency")

    def test_mode_vocabulary_and_thresholds_are_explicit_and_mutually_exclusive(self):
        must_have(self, r"Mode A / Standalone")
        must_have(self, r"Mode B / Swarm-stacked")
        must_have(self, r"Stay STANDALONE when all hold")
        must_have(self, r"`0-2` impacted surfaces")
        must_have(self, r"`0 or 1` specialist domain")
        must_have(self, r"Escalate to /SWARM when any hold")
        must_have(self, r"`2\+` specialist domains")
        must_have(self, r"`3\+` impacted surfaces")
        must_not_have(self, r"<=2 specialist domains")

    def test_no_trustworthy_prior_audit_is_a_tiebreak_not_an_automatic_trigger(self):
        must_have(self, r'Treat "no trustworthy prior audit" as a tie-break or risk signal, not an automatic swarm trigger')
        must_not_have(self, r"cross-repo/\s*multi-team surface; no trustworthy prior audit")

    def test_swarm_recommendation_without_explicit_request_requires_consent(self):
        must_have(self, r"If the agent recommends Swarm but the operator did not explicitly request it, ask for confirmation before dispatch")
        must_have(self, r"Pass the target plan path, exact authoritative baseline/ref, project conventions, and the four-test overlay into the swarm request")
        must_have(self, r"strict read-only reviewer authority")
        must_have(self, r"Reviewers return findings only")
        must_have(self, r"A verifier runs only when `/swarm`'s own gate conditions select one\. Never promise a verifier by default")
        must_have(self, r"`plan-refine` orchestrator alone edits")
        must_have(self, r"plan-lifecycle discipline from section 7")

    def test_residual_uncertainty_and_report_fields_are_explicit(self):
        must_have(self, r"Assessment-only requests return findings and proposed changes without mutation")
        must_have(
            self,
            r"Under explicit harden/edit authority, \*\*Updated plan presented for approval\*\* "
            r"applies only when no material unknowns remain",
        )
        must_have(self, r"otherwise readiness is blocked and the missing evidence is named")
        must_have(self, r"In every path, nothing gets implemented until the operator confirms")
        must_have(
            self,
            r"\*\*Mode and target:\*\*.*"
            r"\*\*Baseline and evidence status:\*\*.*"
            r"\*\*Changes made or proposed:\*\*.*"
            r"\*\*Considered but not acted on:\*\*.*"
            r"\*\*Residual uncertainty:\*\*.*"
            r"\*\*Outcome and approval gate:\*\*",
        )
        must_have(
            self,
            r"\*\*Baseline and evidence status:\*\* "
            r"the exact baseline/ref used for verification and whether the working tree matched it or diverged",
        )
        must_have(self, r"Material unknowns block a ready-for-approval verdict")
        must_not_have(self, r"\*\*Updated plan presented for approval:\*\* state plainly")


if __name__ == "__main__":
    unittest.main()
