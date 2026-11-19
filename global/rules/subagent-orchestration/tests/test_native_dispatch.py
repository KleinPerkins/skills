"""MOD-01/02: outcomes, compatibility and native evidence refusal contracts."""
import copy
from datetime import datetime, timezone
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


n = module("native_dispatch")
legacy = module("verify_model_tiers")
NOW = datetime(2026, 10, 27, 20, tzinfo=timezone.utc).timestamp()


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def sources():
    # Semantic identity is deliberately unrelated to the opaque native tokens.
    identities = [
        ("alpha-big-9-max", "alpha", "large", "max", None, "opaque-17"),
        ("alpha-big-9-high", "alpha", "large", "high", None, "opaque-17"),
        ("beta-pro-2-max", "beta", "reasoner", "max", None, "opaque-low"),
        ("alpha-mid-9-high", "alpha", "middle", "high", None, "token.max"),
        ("gamma-1.5-fast", "gamma", "fixed", None, "fast", "opaque/42"),
    ]
    choices = {i: dict(provider=p, family=f, effort=e, fixed_behavior=b,
                      models={"cursor": i, "codex": m}) for i, p, f, e, b, m in identities}
    policy = {"schema": "cursor-model-tiers/v2", "verified_against": "cursor-subagent-model-enum/2000-01-01",
              "tiers": {"deep": {"candidates": [identities[i][0] for i in (0, 1, 2)]},
                        "critical": {"candidates": [identities[i][0] for i in (2, 0)]},
                        "standard": {"candidates": [identities[i][0] for i in (3, 2)]},
                        "economy": {"candidates": [identities[i][0] for i in (4, 3)]}}}
    bindings = {"schema": "native-model-bindings/v1", "choices": choices,
                "override_models": {"cursor": [], "codex": []}}
    return policy, bindings


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.bindings = sources()
        models = [dict(model=m, efforts=e, fixed_behavior=f) for m, e, f in (
            ("opaque-17", ["high", "max"], None), ("opaque-low", ["max"], None),
            ("token.max", ["high"], None), ("opaque/42", None, "fast"))]
        self.context = dict(host="codex", surface="local-macos-desktop", session_id="synthetic-session",
                            contract_sha256=n.digest(models), host_build="test-build")
        self.evidence = dict(schema="native-offers/v1", **self.context, tool="collaboration.spawn_agent",
                             origin="native-tool", observed_at=iso(NOW),
                             source_sha256=n.source_digest(self.policy, self.bindings), models=models)
        self.request = dict(context=self.context, work_kind="design", difficulty="normal", tier=None,
                            raise_reason=None, mode="auto", selection=None, author_provider=None,
                            require_different_provider=False)

    def resolve(self, now=NOW, continuation=None):
        return n.resolve(self.request, self.evidence, self.policy, self.bindings,
                         now=now, continuation=continuation)

    def offered(self, models):
        self.evidence["models"] = models
        self.context["contract_sha256"] = self.evidence["contract_sha256"] = n.digest(models)

    def refused(self, result):
        self.assertEqual(result["status"], "unavailable", result)
        self.assertIsNone(result["dispatch"])
        self.assertIsNone(result["acknowledged"])

    def test_explicit_semantics_precede_opaque_dispatch(self):
        p = self.resolve()
        self.assertEqual(p["requested"], dict(provider="alpha", family="large", effort="max", fixed_behavior=None))
        self.assertEqual(p["dispatch"], dict(model="opaque-17", reasoning_effort="max", fork_turns="none"))
        self.assertIsNone(p["acknowledged"])

    def test_classification_and_difficulty_matrix(self):
        for kind, tier in n.KINDS.items():
            with self.subTest(kind=kind):
                self.request.update(work_kind=kind, author_provider="none" if kind in {"review", "sign-off"} else None)
                self.assertEqual(self.resolve()["tier"], tier)
        self.request.update(work_kind="build", author_provider=None, difficulty="raised", tier="deep", raise_reason="architecture")
        self.assertEqual(self.resolve()["tier"], "deep")
        self.assertIn("raised", self.resolve()["warnings"])
        for tier in ("economy", "standard", None):
            self.request["tier"] = tier
            self.refused(self.resolve())

    def test_absent_unknown_non_native_and_wrong_context_refused(self):
        for field, value in (("host", "claude"), ("surface", "cloud"), ("session_id", "another"),
                             ("host_build", "another-build"), ("tool", "models-api"),
                             ("origin", "account-api"), ("source_sha256", "stale"), ("schema", "v0")):
            with self.subTest(field=field):
                old = self.evidence[field]
                self.evidence[field] = value
                self.refused(self.resolve())
                self.evidence[field] = old
        self.evidence = None
        self.refused(self.resolve())

    def test_freshness_boundary_and_future(self):
        self.assertEqual(self.resolve(now=NOW + n.MAX_AGE_SECONDS)["status"], "ready")
        self.refused(self.resolve(now=NOW + n.MAX_AGE_SECONDS + 1))
        self.refused(self.resolve(now=NOW - 1))

    def test_source_and_adapter_binding(self):
        self.policy["verified_against"] = "cursor-subagent-model-enum/2001-01-01"
        self.refused(self.resolve())

    def test_conflicting_native_provider_or_family_is_invalid(self):
        for field, value in (("provider", "other"), ("family", "other")):
            _, bindings = sources()
            bindings["choices"]["alpha-big-9-high"][field] = value
            with self.subTest(field=field), self.assertRaises(n.Unavailable):
                n.validate_sources(self.policy, bindings)

    def test_conflicting_override_token_identity_is_invalid(self):
        self.bindings["override_models"]["codex"] = [dict(provider="other", family="other", model="opaque-17", mode="effort", fixed_behavior=None)]
        with self.assertRaises(n.Unavailable):
            n.validate_sources(self.policy, self.bindings)

    def test_same_identity_separate_effort_variants_are_valid(self):
        n.validate_sources(self.policy, self.bindings)

    def test_native_list_tamper_absent_and_duplicate(self):
        self.evidence["models"].pop()
        self.refused(self.resolve())
        self.offered([])
        self.refused(self.resolve())
        self.offered([dict(model="opaque-17", efforts=["max"], fixed_behavior=None)] * 2)
        self.refused(self.resolve())

    def test_family_attributes_follow_policy_order_not_max_default(self):
        self.request["work_kind"] = "build"
        p = self.resolve()
        self.assertEqual(p["requested"]["effort"], "high")
        self.offered([dict(model="opaque-17", efforts=["high"], fixed_behavior=None)])
        self.request["work_kind"] = "design"
        p = self.resolve()
        self.assertEqual(p["requested"]["effort"], "high")
        self.assertIn("step-down", p["warnings"])

    def test_supported_fixed_behavior_has_no_fictional_effort(self):
        self.request["work_kind"] = "run"
        p = self.resolve()
        self.assertIsNone(p["requested"]["effort"])
        self.assertEqual(p["requested"]["fixed_behavior"], "fast")
        self.assertEqual(p["dispatch"], dict(model="opaque/42", fork_turns="none"))

    def test_cursor_evidence_cannot_claim_separate_behavior(self):
        self.context.update(host="cursor", surface="local-macos-agents")
        self.evidence.update(host="cursor", surface="local-macos-agents", tool="Task")
        self.request["work_kind"] = "run"
        self.offered([dict(model="gamma-1.5-fast", efforts=None, fixed_behavior="slow")])
        self.refused(self.resolve())

    def test_no_cross_tier_substitution(self):
        self.offered([dict(model="opaque/42", efforts=None, fixed_behavior="fast")])
        self.refused(self.resolve())

    def test_unknown_support_and_missing_mapping_refused(self):
        self.offered([dict(model="opaque-17", efforts=None, fixed_behavior=None)])
        self.refused(self.resolve())
        del self.bindings["choices"]["alpha-big-9-max"]
        self.refused(self.resolve())

    def test_forced_unavailable_does_not_substitute(self):
        self.request.update(mode="force", selection=dict(provider="alpha", family="large", effort="low", fixed_behavior=None))
        self.refused(self.resolve())
        self.request["selection"]["effort"] = "high"
        p = self.resolve()
        self.assertEqual(p["requested"]["effort"], "high")
        self.assertIn("explicit-override", p["warnings"])
        self.request["selection"]["family"] = "unknown"
        self.refused(self.resolve())

    def test_fixed_override_rejects_effort(self):
        self.request.update(mode="force", selection=dict(provider="gamma", family="fixed", effort="high", fixed_behavior=None))
        self.refused(self.resolve())

    def test_off_and_auto_with_override_never_launch(self):
        self.request["mode"] = "off"
        self.refused(self.resolve())
        self.request.update(mode="auto", selection={})
        self.refused(self.resolve())

    def test_override_does_not_rewrite_sources(self):
        before = copy.deepcopy((self.policy, self.bindings))
        self.request.update(mode="force", selection=dict(provider="beta", family="reasoner", effort="max", fixed_behavior=None))
        self.assertEqual(self.resolve()["requested"]["provider"], "beta")
        self.assertEqual((self.policy, self.bindings), before)

    def test_review_provider_semantics(self):
        self.request.update(work_kind="sign-off", author_provider="beta")
        self.assertEqual(self.resolve()["requested"]["provider"], "alpha")
        self.offered([dict(model="opaque-low", efforts=["max"], fixed_behavior=None)])
        self.assertIn("same-provider-review", self.resolve()["warnings"])
        self.request["require_different_provider"] = True
        self.refused(self.resolve())
        self.request["author_provider"] = "unknown"
        self.refused(self.resolve())

    def test_unknown_or_legacy_provider_cannot_qualify_independence(self):
        self.request.update(work_kind="review", require_different_provider=True)
        for provider in ("banana", "gpt", "claude"):
            self.request["author_provider"] = provider
            self.refused(self.resolve())

    def test_unknown_host_build_explicit(self):
        self.context["host_build"] = self.evidence["host_build"] = None
        self.assertIn("host-build-unavailable", self.resolve()["limitations"])

    def test_not_offered_requires_refresh_and_keeps_budget(self):
        plan = self.resolve()
        rejected = n.observe(plan, "not-offered", now=NOW)
        self.refused(self.resolve(continuation=rejected["continuation"]))
        self.offered([dict(model="opaque-low", efforts=["max"], fixed_behavior=None)])
        self.evidence["observed_at"] = iso(NOW + 1)
        next_plan = self.resolve(now=NOW + 1, continuation=rejected["continuation"])
        self.assertEqual(next_plan["used"], 1)
        self.assertEqual(next_plan["limit"], 4)
        self.assertEqual(next_plan["dispatch"]["model"], "opaque-low")

    def test_refresh_keeps_original_secondary_before_new_provider(self):
        self.policy["tiers"]["deep"]["candidates"].append("delta-choice")
        self.bindings["choices"]["delta-choice"] = dict(provider="delta", family="third",
            effort="high", fixed_behavior=None, models={"cursor": "delta-choice", "codex": "third-token"})
        self.evidence["source_sha256"] = n.source_digest(self.policy, self.bindings)
        third = dict(model="third-token", efforts=["high"], fixed_behavior=None)
        self.offered(self.evidence["models"] + [third])
        rejected = n.observe(self.resolve(), "not-offered", now=NOW)
        self.offered([r for r in self.evidence["models"] if r["model"] != "opaque-17"])
        self.evidence["observed_at"] = iso(NOW + 1)
        plan = self.resolve(now=NOW + 1, continuation=rejected["continuation"])
        self.assertEqual(plan["dispatch"]["model"], "opaque-low")
        self.assertEqual((plan["used"], plan["limit"]), (1, 4))

    def test_malformed_continuation_is_unavailable(self):
        rejected = n.observe(self.resolve(), "prelaunch-rejected", now=NOW)
        for key, value in (("refresh_required", []), ("previous_evidence", {}), ("used", True), ("retry_at", 17)):
            bad = copy.deepcopy(rejected["continuation"])
            bad[key] = value
            with self.subTest(key=key):
                self.refused(self.resolve(continuation=bad))

    def test_second_cycle_cannot_omit_wait(self):
        rejected = n.observe(self.resolve(), "prelaunch-rejected", now=NOW)
        plan = self.resolve(continuation=rejected["continuation"])
        rejected = n.observe(plan, "prelaunch-rejected", now=NOW)
        rejected["continuation"]["retry_at"] = None
        self.refused(self.resolve(continuation=rejected["continuation"]))

    def test_bounded_rejections_with_wait(self):
        plan = self.resolve()
        selected = []
        clock = NOW
        for i in range(4):
            selected.append(plan["dispatch"]["model"])
            rejected = n.observe(plan, "prelaunch-rejected", now=clock)
            plan = self.resolve(now=clock, continuation=rejected["continuation"])
            if i == 1:
                self.assertEqual(plan["status"], "waiting")
                self.assertIsNone(plan["dispatch"])
                clock += 60
                plan = self.resolve(now=clock, continuation=rejected["continuation"])
        self.assertEqual(selected, ["opaque-17", "opaque-low", "opaque-17", "opaque-low"])
        self.refused(plan)

    def test_single_provider_only_two_attempts(self):
        self.offered([dict(model="opaque-17", efforts=["max"], fixed_behavior=None)])
        plan = self.resolve()
        self.assertEqual(plan["limit"], 2)
        rejected = n.observe(plan, "prelaunch-rejected", now=NOW)
        self.assertEqual(self.resolve(continuation=rejected["continuation"])["status"], "waiting")
        next_plan = self.resolve(now=NOW + 60, continuation=rejected["continuation"])
        rejected = n.observe(next_plan, "prelaunch-rejected", now=NOW + 60)
        self.refused(self.resolve(now=NOW + 60, continuation=rejected["continuation"]))

    def test_started_failure_never_becomes_model_rejection(self):
        plan = n.observe(self.resolve(), "started", worker_id="native-worker")
        self.assertEqual(plan["status"], "running")
        self.assertIsNone(plan["dispatch"])
        self.assertIsNone(plan["acknowledged"])
        self.assertIsNone(plan["execution_matches_request"])
        failed = n.observe(plan, "failed")
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn("continuation", failed)
        self.refused(n.observe(failed, "prelaunch-rejected"))

    def test_acknowledgement_mismatch_preserved(self):
        ack = dict(provider="beta", family="other", model="other-model", effort="high", fixed_behavior=None, origin="native-tool")
        plan = n.observe(self.resolve(), "started", worker_id="native-worker", acknowledged=ack)
        self.assertEqual(plan["acknowledged"], ack)
        self.assertFalse(plan["execution_matches_request"])
        ack["transcript"] = "forbidden"
        self.refused(n.observe(self.resolve(), "started", worker_id="native-worker", acknowledged=ack))

    def test_incomplete_behavior_acknowledgement_stays_unknown(self):
        ack = dict(provider="alpha", family="large", model="opaque-17", effort=None, fixed_behavior=None, origin="native-tool")
        plan = n.observe(self.resolve(), "started", worker_id="native-worker", acknowledged=ack)
        self.assertIsNone(plan["execution_matches_request"])

    def test_malformed_observation_never_creates_execution(self):
        for plan, event in ((dict(schema=n.VERSION, status="ready"), "prelaunch-rejected"),
                            (dict(schema=n.VERSION, status="running"), "succeeded")):
            self.refused(n.observe(plan, event))
        plan = self.resolve()
        plan["used"] = True
        self.refused(n.observe(plan, "prelaunch-rejected"))
        running = n.observe(self.resolve(), "started", worker_id="native-worker")
        running["worker_id"] = ""
        self.refused(n.observe(running, "succeeded"))

    def test_invalid_request_has_no_retry(self):
        p = n.observe(self.resolve(), "invalid-request")
        self.assertEqual(p["status"], "invalid-request")
        self.assertNotIn("continuation", p)

    def test_retries_cannot_move_to_another_task_or_session(self):
        rejected = n.observe(self.resolve(), "prelaunch-rejected", now=NOW)
        self.request["work_kind"] = "build"
        self.refused(self.resolve(continuation=rejected["continuation"]))

    def test_refresh_proposal_is_not_adoption(self):
        before = copy.deepcopy((self.policy, self.bindings, self.evidence))
        proposal = n.refresh_proposal(self.policy, self.bindings, self.evidence)
        self.assertFalse(proposal["adopted"])
        self.assertEqual((self.policy, self.bindings, self.evidence), before)

    def test_all_cursor_offer_subsets_preserve_legacy_primary(self):
        names = list(self.bindings["choices"])
        checked = legacy.validate_catalog(self.policy)
        self.context.update(host="cursor", surface="local-macos-agents")
        self.evidence.update(host="cursor", surface="local-macos-agents", tool="Task")
        for bits in itertools.product((False, True), repeat=len(names)):
            live = [name for name, enabled in zip(names, bits) if enabled]
            if not live:
                continue
            self.offered([dict(model=name, efforts=None, fixed_behavior=None) for name in live])
            for kind in n.KINDS:
                self.request.update(work_kind=kind, author_provider="none" if kind in {"review", "sign-off"} else None)
                with self.subTest(live=live, kind=kind):
                    try:
                        old = legacy.plan_launch(checked, live, kind, author_provider="none")
                    except legacy.PlanError:
                        self.refused(self.resolve())
                    else:
                        self.assertEqual(self.resolve()["dispatch"], {"model": old["primary"]})


class SourceTests(unittest.TestCase):
    def test_current_policy_mapping_complete_without_adopting_preferences(self):
        policy = n.read_json(ROOT / "model-tiers.json")
        bindings = n.read_json(ROOT / "native-model-bindings.json")
        n.validate_sources(policy, bindings)
        names = {c for row in policy["tiers"].values() for c in row["candidates"]}
        self.assertEqual(names, set(bindings["choices"]))
        self.assertFalse(names & {r["model"] for r in bindings["override_models"]["codex"]})

    def test_cli_source_digest_and_closed_json(self):
        command = [sys.executable, str(ROOT / "native_dispatch.py")]
        result = subprocess.run(command + ["source-digest"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["source_sha256"]), 64)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text('{"request":{},"request":{}}')
            result = subprocess.run(command + ["plan", "--input", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIsNone(json.loads(result.stdout)["dispatch"])


if __name__ == "__main__":
    unittest.main()
