"""Deterministic policy, native adapter and lifecycle acceptance tests."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("codex_dispatch", ROOT / "codex_dispatch.py")
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
NOW = 1793664000

def assessment(level=0, kind="inspect"):
    return dict(schema="codex-work-assessment/v1", objective="Answer a synthetic task",
        deliverable="A checked answer", scope="Synthetic inputs only", work_class=kind,
        ratings={d: dict(level=level, evidence="Fixture facts justify this level") for d in n.DIMS},
        effects={e: False for e in n.EFFECTS}, reversibility="read-only",
        verification=dict(method="automated", checks=[dict(id="correct", criterion="Matches the expected answer")]),
        unknowns=[], review=dict(author_model=None, requirement="none"))

def envelope(level=0, kind="inspect"):
    ctx = dict(host="codex", surface="local-macos-desktop", session_id="test", host_build="test-build")
    models = []
    for model in dict.fromkeys(r["model"] for r in n.policy()["routes"]):
        models.append(dict(model=model, efforts=["low", "medium", "high", "xhigh", "max"]))
    ev = dict(schema="codex-native-offers/v1", context=copy.deepcopy(ctx), tool=n.TOOL,
        origin="native-tool", observed_at=datetime.fromtimestamp(NOW, timezone.utc).isoformat(),
        source_sha256=n.source_digest(), contract=dict(model="string", reasoning_effort="string", fork_context="boolean", ordinary_agent=True), models=models)
    return dict(assessment=assessment(level, kind), target="worker", context=ctx,
                evidence=ev, override=None, continuation=None)

def observation(record, event, **kwargs):
    return dict(record=record, event=event, worker_id=record.get("worker_id"), acknowledged=None,
                checks=None, cleanup_verified=False, diagnosis=None, **kwargs)

def collaboration_envelope(level=0, kind="inspect"):
    req = envelope(level, kind)
    req["evidence"].update(tool="collaboration.spawn_agent", contract={
        "model": "string", "reasoning_effort": "string", "fork_turns": "string",
        "fork_turns_fresh_value": "none", "task_name": "string", "message": "string",
        "ordinary_agent": True})
    return req

class DispatchTests(unittest.TestCase):
    def plan(self, req=None, now=NOW):
        return n.plan(envelope() if req is None else req, now=now)

    def observe(self, r, event, **kw):
        ev = observation(r, event)
        ev.update(kw)
        return n.observe(ev, now=NOW)

    def completed(self, req=None, correct=False):
        r = self.observe(self.plan(req), "started", worker_id="worker")
        return self.observe(r, "completed", checks={"correct": correct}, cleanup_verified=True)

    def test_owner_policy_exact_initial_routes(self):
        self.assertEqual(n.policy()["routes"], [
            {"model": "gpt-6-luna", "effort": "low"},
            {"model": "gpt-6.1-sol", "effort": "medium"},
            {"model": "gpt-6.1-sol", "effort": "high"},
            {"model": "gpt-6-astra", "effort": "high"},
            {"model": "gpt-6-astra", "effort": "xhigh"}])

    def test_all_classes_bands_and_floors(self):
        for kind in n.KINDS:
            for level in range(4):
                with self.subTest(kind=kind, level=level):
                    r = self.plan(envelope(level, kind))
                    band = max(level, 2 if kind == "assure" else 1 if kind == "build" else 0)
                    self.assertEqual(r["band"], band)
                    self.assertEqual(r["selected"], n.policy()["routes"][band])

    def test_each_dimension_dominates(self):
        for dim in n.DIMS:
            for level in range(4):
                req = envelope()
                req["assessment"]["ratings"][dim]["level"] = level
                self.assertEqual(self.plan(req)["band"], level)

    def test_source_security_review_and_signoff_floors(self):
        for effect in ("source_edits", "security_judgment", "independent_review", "sign_off"):
            req = envelope()
            req["assessment"]["effects"][effect] = True
            self.assertEqual(self.plan(req)["band"], 1 if effect == "source_edits" else 2)

    def test_length_urgency_and_consequence_not_difficulty(self):
        req = envelope()
        req["assessment"]["objective"] = "URGENT " * 1000
        req["assessment"]["effects"]["consequential"] = True
        req["assessment"]["reversibility"] = "irreversible"
        r = self.plan(req)
        self.assertEqual(r["band"], 0)
        self.assertIn("applicable-authorization", r["required_checks"])
        self.assertIn("independent-review", r["required_checks"])

    def test_unknown_or_missing_evidence_never_easy(self):
        for field in ("unknowns", "null", "empty"):
            req = envelope()
            a = req["assessment"]
            if field == "unknowns":
                a["unknowns"] = ["Scope could cross systems"]
            else:
                a["ratings"]["ambiguity"]["level" if field == "null" else "evidence"] = None if field == "null" else ""
            r = self.plan(req)
            self.assertEqual(r["status"], "needs-assessment")
            self.assertIsNone(r["dispatch"])

    def test_closed_assessment_no_tier_bypass(self):
        for key, value in (("tier", "economy"), ("difficulty", 0)):
            req = envelope()
            req["assessment"][key] = value
            with self.assertRaises(n.Invalid):
                self.plan(req)

    def test_reject_bool_rating_and_empty_checks(self):
        req = envelope()
        req["assessment"]["ratings"]["ambiguity"]["level"] = True
        with self.assertRaises(n.Invalid): self.plan(req)
        req = envelope()
        req["assessment"]["verification"]["checks"] = []
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_exact_native_dispatch_and_determinism(self):
        r = self.plan()
        self.assertEqual(r, self.plan())
        self.assertEqual(r["dispatch"], dict(tool=n.TOOL, arguments=dict(model="gpt-6-luna", reasoning_effort="low", fork_context=False, agent_type="default")))
        self.assertIsNone(r["acknowledged"])

    def test_parent_advice_has_no_dispatch(self):
        req = envelope(2)
        req["target"] = "parent"
        r = self.plan(req)
        self.assertEqual(r["status"], "advice")
        self.assertIsNone(r["dispatch"])
        with self.assertRaises(n.Invalid): self.observe(r, "started", worker_id="w")

    def test_evidence_binding_and_staleness(self):
        for change in ("tool", "context", "origin", "source_sha256", "contract", "models"):
            req = envelope()
            req["evidence"][change] = {} if change in ("context", "contract") else [] if change == "models" else "wrong"
            with self.subTest(change=change), self.assertRaises(n.Invalid): self.plan(req)
        for time in (NOW - 1, NOW + 901):
            with self.assertRaises(n.Invalid): self.plan(now=time)
        self.assertEqual(self.plan(now=NOW + 900)["status"], "ready")

    def test_no_effort_or_model_substitution(self):
        req = envelope()
        req["evidence"]["models"] = req["evidence"]["models"][1:]
        with self.assertRaises(n.Invalid): self.plan(req)
        req = envelope()
        req["evidence"]["models"][0]["efforts"] = ["high"]
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_duplicate_offers_refused(self):
        req = envelope()
        req["evidence"]["models"].append(copy.deepcopy(req["evidence"]["models"][0]))
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_override_no_downgrade_or_invented_pair(self):
        req = envelope(2)
        req["override"] = dict(model="gpt-6-luna", effort="low", reason="explicit request")
        with self.assertRaises(n.Invalid): self.plan(req)
        req["override"] = dict(model="gpt-6-astra", effort="high", reason="explicit request")
        self.assertEqual(self.plan(req)["selected"]["model"], "gpt-6-astra")
        req["override"]["effort"] = "made-up"
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_review_independence_and_stricter_requirements(self):
        req = envelope(2, "assure")
        req["assessment"]["review"] = dict(author_model="gpt-6.1-sol", requirement="separate-context")
        self.assertEqual(self.plan(req)["selected"]["model"], "gpt-6-astra")
        req["evidence"]["models"] = [m for m in req["evidence"]["models"] if m["model"] != "gpt-6-astra"]
        self.assertEqual(self.plan(req)["selected"]["model"], "gpt-6.1-sol")
        req["assessment"]["review"]["requirement"] = "different-model"
        with self.assertRaises(n.Invalid): self.plan(req)
        req = envelope(2, "assure")
        req["assessment"]["review"]["requirement"] = "different-provider"
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_availability_one_retry_wait_no_budget_reset(self):
        req = envelope()
        rejected = self.observe(self.plan(req), "prelaunch-rejected")
        req["continuation"] = rejected
        self.assertEqual(self.plan(req)["status"], "waiting")
        retry = self.plan(req, NOW + 60)
        self.assertEqual(retry["selected"], rejected["selected"])
        terminal = self.observe(retry, "prelaunch-rejected")
        self.assertEqual(terminal["status"], "unavailable")
        req["continuation"] = terminal
        with self.assertRaises(n.Invalid): self.plan(req, NOW + 120)

    def test_not_offered_requires_new_evidence(self):
        req = envelope()
        req["continuation"] = self.observe(self.plan(req), "not-offered")
        with self.assertRaises(n.Invalid): self.plan(req, NOW + 60)
        req["evidence"]["observed_at"] = datetime.fromtimestamp(NOW+60, timezone.utc).isoformat()
        self.assertEqual(self.plan(req, NOW + 60)["status"], "ready")

    def test_started_failure_not_availability(self):
        r = self.observe(self.plan(), "started", worker_id="w")
        with self.assertRaises(n.Invalid): self.observe(r, "prelaunch-rejected")
        failure = self.observe(r, "infrastructure-failed", cleanup_verified=True)
        req = envelope()
        req["continuation"] = failure
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_explicit_quality_escalation_all_bands_once(self):
        for band in range(4):
            req = envelope(band)
            failure = self.observe(self.completed(req), "quality-failed", cleanup_verified=True, diagnosis="The answer violates the predefined criterion")
            req["continuation"] = failure
            retry = self.plan(req)
            self.assertEqual(retry["selected"], n.policy()["routes"][band+1])
            finished = self.observe(self.observe(retry, "started", worker_id="next"), "completed", checks={"correct": False}, cleanup_verified=True)
            final = self.observe(finished, "quality-failed", cleanup_verified=True, diagnosis="Still fails")
            self.assertEqual(final["status"], "quality-exhausted")
            req["continuation"] = final
            with self.assertRaises(n.Invalid): self.plan(req)

    def test_reassessment_can_require_stronger_route(self):
        req = envelope()
        req["continuation"] = self.observe(self.completed(req), "quality-failed", cleanup_verified=True, diagnosis="Coupling underestimated")
        req["assessment"]["ratings"]["coupling"]["level"] = 3
        self.assertEqual(self.plan(req)["selected"], n.policy()["routes"][3])

    def test_quality_requires_failed_checks_diagnosis_and_cleanup(self):
        with self.assertRaises(n.Invalid):
            self.observe(self.completed(correct=True), "quality-failed", cleanup_verified=True, diagnosis="No failure")
        with self.assertRaises(n.Invalid):
            self.observe(self.completed(), "quality-failed", cleanup_verified=False, diagnosis="Failed")
        with self.assertRaises(n.Invalid):
            self.observe(self.completed(), "quality-failed", cleanup_verified=True)
        r = self.observe(self.plan(), "started", worker_id="w")
        with self.assertRaises(n.Invalid): self.observe(r, "completed", checks={"invented": False})

    def test_escalation_cannot_change_acceptance_or_review(self):
        req = envelope()
        req["continuation"] = self.observe(self.completed(req), "quality-failed", cleanup_verified=True, diagnosis="Failed")
        req["assessment"]["verification"]["checks"][0]["criterion"] = "Easier"
        with self.assertRaises(n.Invalid): self.plan(req)

    def test_retry_cannot_change_assessment(self):
        req = envelope()
        req["continuation"] = self.observe(self.plan(req), "prelaunch-rejected")
        req["assessment"]["ratings"]["ambiguity"]["level"] = 1
        with self.assertRaises(n.Invalid): self.plan(req, NOW+60)

    def test_identity_unknown_partial_mismatch(self):
        for ack, expected in ((None, None), (dict(model="gpt-6-luna", effort=None, origin="native-tool"), None), (dict(model="other", effort="low", origin="native-tool"), False)):
            r = self.observe(self.plan(), "started", worker_id="w", acknowledged=ack)
            self.assertIs(r["execution_matches_request"], expected)
        r = self.observe(r, "completed", checks={"correct": False}, cleanup_verified=True)
        with self.assertRaises(n.Invalid): self.observe(r, "quality-failed", cleanup_verified=True, diagnosis="Wrong result")

    def test_record_corruption_and_foreign_worker_rejected(self):
        r = self.plan()
        r["selected"]["effort"] = "max"
        with self.assertRaises(n.Invalid): self.observe(r, "started", worker_id="w")
        r = self.observe(self.plan(), "started", worker_id="w")
        with self.assertRaises(n.Invalid): self.observe(r, "completed", worker_id="other", checks={"correct": True})

    def test_refresh_is_proposal_only(self):
        req = envelope()
        r = n.refresh({k:req[k] for k in ("context", "evidence")}, now=NOW)
        self.assertEqual(r["status"], "proposal-only")
        self.assertIsNone(r["dispatch"])

    def test_cli_digest(self):
        r = subprocess.run([sys.executable, str(ROOT / "codex_dispatch.py"), "source-digest"], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["source_sha256"], n.source_digest())

class CollaborationTests(unittest.TestCase):
    def plan(self, req=None, now=NOW):
        return n.plan(collaboration_envelope() if req is None else req, now=now)

    observe = DispatchTests.observe
    completed = DispatchTests.completed

    def assert_profile(self, r):
        self.assertEqual(r["schema"], "codex-work-decision/v2")
        self.assertEqual(r["native_tool"], "collaboration.spawn_agent")

    def test_exact_current_arguments_and_all_band_routes(self):
        expected = [("gpt-6-luna", "low"), ("gpt-6.1-sol", "medium"),
                    ("gpt-6.1-sol", "high"), ("gpt-6-astra", "high")]
        for band, (model, effort) in enumerate(expected):
            with self.subTest(band=band):
                r = self.plan(collaboration_envelope(band))
                self.assert_profile(r)
                self.assertEqual(r["status"], "ready")
                self.assertEqual(r["dispatch"], {
                    "tool": "collaboration.spawn_agent",
                    "arguments": {"model": model, "reasoning_effort": effort, "fork_turns": "none"},
                    "caller_fields": ["task_name", "message"]})
                self.assertIsNone(r["acknowledged"])
                self.assertIsNone(r["execution_matches_request"])

    def test_current_profile_keeps_assessment_floors(self):
        for effect, band in (("source_edits", 1), ("security_judgment", 2),
                             ("independent_review", 2), ("sign_off", 2)):
            req = collaboration_envelope()
            req["assessment"]["effects"][effect] = True
            self.assertEqual(self.plan(req)["band"], band)
        req = collaboration_envelope(2, "assure")
        req["assessment"]["review"] = dict(author_model="gpt-6.1-sol", requirement="different-model")
        self.assertEqual(self.plan(req)["selected"], {"model": "gpt-6-astra", "effort": "high"})

    def test_parent_and_refresh_never_dispatch_or_adopt(self):
        req = collaboration_envelope(2)
        req["target"] = "parent"
        advice = self.plan(req)
        self.assert_profile(advice)
        self.assertEqual(advice["status"], "advice")
        self.assertIsNone(advice["dispatch"])
        with self.assertRaises(n.Invalid): self.observe(advice, "started", worker_id="w")
        proposal = n.refresh({k: req[k] for k in ("context", "evidence")}, now=NOW)
        self.assert_profile(proposal)
        self.assertEqual(proposal["status"], "proposal-only")
        self.assertTrue(proposal["adoption_required"])
        self.assertIsNone(proposal["dispatch"])

    def test_legacy_output_shape_preserved(self):
        legacy = n.plan(envelope(), now=NOW)
        self.assertEqual(legacy["schema"], "codex-work-decision/v1")
        self.assertNotIn("native_tool", legacy)
        self.assertEqual(legacy["dispatch"], {"tool": "multi_agent_v1.spawn_agent", "arguments": {
            "model": "gpt-6-luna", "reasoning_effort": "low", "fork_context": False, "agent_type": "default"}})
        self.assertNotIn("caller_fields", legacy["dispatch"])

    def test_contract_closed_and_each_observation_required(self):
        contract = collaboration_envelope()["evidence"]["contract"]
        for key in contract:
            req = collaboration_envelope()
            del req["evidence"]["contract"][key]
            with self.subTest(missing=key), self.assertRaisesRegex(n.Invalid, "unsupported native contract"):
                self.plan(req)
        for key, value in (("fork_turns_fresh_value", "all"), ("fork_turns", "boolean"),
                           ("task_name", None), ("ordinary_agent", False),
                           ("ordinary_agent", 1), ("agent_type", "default"),
                           ("fork_context", "boolean")):
            req = collaboration_envelope()
            req["evidence"]["contract"][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(n.Invalid, "unsupported native contract"):
                self.plan(req)

    def test_exact_native_name_not_aliases_or_other_shapes(self):
        for tool in ("spawn_agent", "collaboration.spawn", "multi_agent_v1.spawn_agent", None, []):
            req = collaboration_envelope()
            req["evidence"]["tool"] = tool
            with self.subTest(tool=tool), self.assertRaises(n.Invalid): self.plan(req)
        req = envelope()
        req["evidence"]["tool"] = "collaboration.spawn_agent"
        with self.assertRaisesRegex(n.Invalid, "unsupported native contract"): self.plan(req)
        req = envelope()
        req["evidence"]["contract"]["ordinary_agent"] = 1
        with self.assertRaisesRegex(n.Invalid, "unsupported native contract"): self.plan(req)

    def test_evidence_context_source_origin_and_freshness_required(self):
        for key, value in (("context", {}), ("origin", "worker-report"), ("source_sha256", "wrong")):
            req = collaboration_envelope()
            req["evidence"][key] = value
            with self.subTest(key=key), self.assertRaises(n.Invalid): self.plan(req)
        for now in (NOW - 1, NOW + 901):
            with self.assertRaises(n.Invalid): self.plan(now=now)
        self.assertEqual(self.plan(now=NOW + 900)["status"], "ready")

    def test_no_model_or_effort_substitution(self):
        req = collaboration_envelope()
        req["evidence"]["models"] = req["evidence"]["models"][1:]
        with self.assertRaisesRegex(n.Invalid, "no substitution"): self.plan(req)
        req = collaboration_envelope()
        req["evidence"]["models"][0]["efforts"] = ["high"]
        with self.assertRaisesRegex(n.Invalid, "no substitution"): self.plan(req)

    def test_current_availability_retry_waits_and_cannot_reset(self):
        req = collaboration_envelope()
        rejected = self.observe(self.plan(req), "prelaunch-rejected")
        self.assert_profile(rejected)
        req["continuation"] = rejected
        waiting = self.plan(req)
        self.assert_profile(waiting)
        self.assertEqual(waiting["status"], "waiting")
        self.assertIsNone(waiting["dispatch"])
        self.assertEqual(waiting["continuation"], rejected)
        retry = self.plan(req, NOW + 60)
        self.assert_profile(retry)
        self.assertEqual(retry["selected"], rejected["selected"])
        self.assertEqual(retry["availability_used"], 1)
        unavailable = self.observe(retry, "prelaunch-rejected")
        self.assert_profile(unavailable)
        self.assertEqual(unavailable["status"], "unavailable")
        req["continuation"] = unavailable
        with self.assertRaises(n.Invalid): self.plan(req, NOW + 120)

    def test_current_not_offered_requires_refreshed_evidence(self):
        req = collaboration_envelope()
        req["continuation"] = self.observe(self.plan(req), "not-offered")
        with self.assertRaisesRegex(n.Invalid, "fresh native evidence"): self.plan(req, NOW + 60)
        req["evidence"]["observed_at"] = datetime.fromtimestamp(NOW + 60, timezone.utc).isoformat()
        self.assertEqual(self.plan(req, NOW + 60)["status"], "ready")

    def test_cross_profile_availability_and_quality_continuations_refused(self):
        for original, changed in ((envelope, collaboration_envelope), (collaboration_envelope, envelope)):
            req = original()
            ready = n.plan(req, now=NOW)
            retryable = self.observe(ready, "not-offered")
            started = self.observe(ready, "started", worker_id="w")
            failed = self.observe(started, "completed", checks={"correct": False}, cleanup_verified=True)
            escalatable = self.observe(failed, "quality-failed", cleanup_verified=True, diagnosis="Incorrect synthetic answer")
            for continuation in (retryable, escalatable):
                nxt = changed()
                nxt["continuation"] = continuation
                nxt["evidence"]["observed_at"] = datetime.fromtimestamp(NOW + 60, timezone.utc).isoformat()
                with self.subTest(original=req["evidence"]["tool"], status=continuation["status"]), self.assertRaisesRegex(n.Invalid, "native profile changed"):
                    self.plan(nxt, NOW + 60)

    def test_current_quality_escalation_all_bands_once(self):
        expected = [("gpt-6.1-sol", "medium"), ("gpt-6.1-sol", "high"),
                    ("gpt-6-astra", "high"), ("gpt-6-astra", "xhigh")]
        for band, (model, effort) in enumerate(expected):
            req = collaboration_envelope(band)
            failed = self.observe(self.completed(req), "quality-failed", cleanup_verified=True, diagnosis="Fails the frozen synthetic check")
            self.assert_profile(failed)
            req["continuation"] = failed
            retry = self.plan(req)
            self.assert_profile(retry)
            self.assertEqual(retry["selected"], {"model": model, "effort": effort})
            self.assertEqual(retry["dispatch"]["arguments"]["fork_turns"], "none")
            self.assertEqual(retry["quality_used"], 1)
            finished = self.observe(self.observe(retry, "started", worker_id="next"), "completed", checks={"correct": False}, cleanup_verified=True)
            final = self.observe(finished, "quality-failed", cleanup_verified=True, diagnosis="Still fails")
            self.assert_profile(final)
            self.assertEqual(final["status"], "quality-exhausted")
            req["continuation"] = final
            with self.assertRaises(n.Invalid): self.plan(req)

    def test_current_quality_needs_failed_checks_diagnosis_and_cleanup(self):
        for correct, cleanup, diagnosis in ((True, True, "No failure"), (False, False, "Failed"), (False, True, None)):
            with self.subTest(correct=correct, cleanup=cleanup, diagnosis=diagnosis), self.assertRaises(n.Invalid):
                self.observe(self.completed(correct=correct), "quality-failed", cleanup_verified=cleanup, diagnosis=diagnosis)

    def test_all_current_observations_preserve_profile_and_remove_dispatch(self):
        for event in ("invalid-request", "prelaunch-rejected", "not-offered"):
            record = self.observe(self.plan(), event)
            self.assert_profile(record)
            self.assertIsNone(record["dispatch"])
        for event in ("completed", "infrastructure-failed", "terminated"):
            started = self.observe(self.plan(), "started", worker_id="w")
            self.assert_profile(started)
            self.assertIsNone(started["dispatch"])
            record = self.observe(started, event, checks={"correct": True} if event == "completed" else None, cleanup_verified=True)
            self.assert_profile(record)
            self.assertIsNone(record["dispatch"])

    def test_resealed_schema_and_profile_mismatches_still_refused(self):
        for schema, tool in (("codex-work-decision/v1", "collaboration.spawn_agent"),
                             ("codex-work-decision/v2", "multi_agent_v1.spawn_agent"),
                             ("codex-work-decision/v2", None), ("codex-work-decision/v3", "collaboration.spawn_agent")):
            record = self.plan()
            record.update(schema=schema, native_tool=tool)
            with self.subTest(schema=schema, tool=tool), self.assertRaises(n.Invalid):
                self.observe(n.seal(record), "started", worker_id="w")
        record = n.plan(envelope(), now=NOW)
        record["schema"] = "codex-work-decision/v2"
        with self.assertRaises(n.Invalid): self.observe(n.seal(record), "started", worker_id="w")

    def test_current_acknowledgement_never_inferred(self):
        for ack, expected in ((None, None), (dict(model="gpt-6-luna", effort=None, origin="native-tool"), None),
                              (dict(model="other", effort="low", origin="native-tool"), False)):
            started = self.observe(self.plan(), "started", worker_id="w", acknowledged=ack)
            self.assert_profile(started)
            self.assertIs(started["execution_matches_request"], expected)
        completed = self.observe(started, "completed", checks={"correct": False}, cleanup_verified=True)
        with self.assertRaises(n.Invalid): self.observe(completed, "quality-failed", cleanup_verified=True, diagnosis="Wrong identity")

    def test_override_retains_fresh_context_and_blocks_auto_escalation(self):
        req = collaboration_envelope()
        req["override"] = {"model": "gpt-6-astra", "effort": "high", "reason": "Scoped user approval"}
        ready = self.plan(req)
        self.assertEqual(ready["dispatch"]["arguments"], {"model": "gpt-6-astra", "reasoning_effort": "high", "fork_turns": "none"})
        finished = self.observe(self.observe(ready, "started", worker_id="w"), "completed", checks={"correct": False}, cleanup_verified=True)
        terminal = self.observe(finished, "quality-failed", cleanup_verified=True, diagnosis="Frozen check failed")
        self.assertEqual(terminal["status"], "quality-exhausted")

    def test_cli_current_profile_and_unknown_contract_fail_closed(self):
        req = collaboration_envelope()
        req["evidence"]["observed_at"] = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.json"
            for invalid in (False, True):
                if invalid:
                    req["evidence"]["contract"]["fork_turns_fresh_value"] = "all"
                path.write_text(json.dumps(req))
                cli = subprocess.run([sys.executable, str(ROOT / "codex_dispatch.py"), "plan", "--input", str(path)], text=True, capture_output=True)
                r = json.loads(cli.stdout)
                self.assertEqual(cli.returncode, 2 if invalid else 0, cli.stderr)
                if invalid:
                    self.assertEqual(r["status"], "unavailable")
                    self.assertIsNone(r["dispatch"])
                else:
                    self.assert_profile(r)
                    self.assertEqual(r["dispatch"]["arguments"]["fork_turns"], "none")

if __name__ == "__main__":
    unittest.main()
