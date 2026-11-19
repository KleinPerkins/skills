"""Codex economy data-pair checks. Offline only; no native worker is launched."""
import copy
from datetime import datetime, timezone
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native", ROOT / "native_dispatch.py")
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
NOW = datetime(2026, 10, 31, tzinfo=timezone.utc).timestamp()


def read(name):
    return n.read_json(ROOT / name)


class CodexEconomyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.base_p = read("model-tiers.json")
        self.base_b = read("native-model-bindings.json")
        self.p = read("codex-model-tiers.json")
        self.b = read("codex-native-model-bindings.json")
        added = set(self.b["choices"]) - set(self.base_b["choices"])
        self.assertEqual(len(added), 1)
        self.identity = next(iter(added))
        self.choice = self.b["choices"][self.identity]
        self.models = [{"model": self.choice["models"]["codex"],
                        "efforts": [self.choice["effort"]], "fixed_behavior": None}]
        self.ctx = dict(host="codex", surface="local-macos-desktop", session_id="fixture",
                        contract_sha256=n.digest(self.models), host_build="fixture-build")
        self.ev = dict(schema="native-offers/v1", **self.ctx,
                       tool="collaboration.spawn_agent", origin="native-tool",
                       observed_at=datetime.fromtimestamp(NOW, timezone.utc).isoformat(),
                       source_sha256=n.source_digest(self.p, self.b), models=self.models)
        self.req = dict(context=self.ctx, work_kind="run", difficulty="normal", tier=None,
                        raise_reason=None, mode="auto", selection=None,
                        author_provider=None, require_different_provider=False)

    def resolve(self, now=NOW, continuation=None):
        return n.resolve(self.req, self.ev, self.p, self.b, now=now, continuation=continuation)

    def refuse(self, result):
        self.assertEqual(result["status"], "unavailable", result)
        self.assertIsNone(result["dispatch"])

    def offers(self, models):
        self.ev["models"] = models
        self.ctx["contract_sha256"] = self.ev["contract_sha256"] = n.digest(models)

    def test_owner_decision_pins_identity_and_complete_semantic_choice(self):
        # Narrow content-specific exception accepted by ADR 0009; legacy catalog
        # tests remain content-agnostic. Changing this tuple needs a new decision.
        self.assertEqual(self.identity, "codex-economy-luna-low")
        self.assertEqual(self.choice, {
            "provider": "openai", "family": "gpt-6-luna", "effort": "low",
            "fixed_behavior": None,
            "models": {"cursor": None, "codex": "gpt-6-luna"},
        })

    def test_only_one_appended_economy_choice_and_binding(self):
        n.validate_sources(self.p, self.b)
        expected = copy.deepcopy(self.base_p)
        expected["verified_against"] = self.p["verified_against"]
        expected["tiers"]["economy"]["candidates"].append(self.identity)
        self.assertEqual(self.p, expected)
        expected_b = copy.deepcopy(self.base_b)
        expected_b["choices"][self.identity] = self.choice
        self.assertEqual(self.b, expected_b)
        self.assertIsNone(self.choice["models"]["cursor"])
        self.assertIsNotNone(self.choice["effort"])
        self.assertIsNone(self.choice["fixed_behavior"])
        for old in self.base_p["tiers"]["economy"]["candidates"]:
            self.assertIsNone(self.b["choices"][old]["models"]["codex"])

    def test_semantic_binding_agrees_with_existing_explicit_family(self):
        rows = [x for x in self.base_b["override_models"]["codex"]
                if (x["provider"], x["family"]) ==
                (self.choice["provider"], self.choice["family"])]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], self.choice["models"]["codex"])
        self.assertEqual(rows[0]["mode"], "effort")

    def test_real_choice_and_reported_fallback(self):
        p = self.resolve()
        self.assertEqual(p["status"], "ready")
        self.assertEqual(p["tier"], "economy")
        self.assertEqual(p["dispatch"], dict(model=self.choice["models"]["codex"],
                         reasoning_effort=self.choice["effort"], fork_turns="none"))
        self.assertIn("fallback", p["warnings"])
        self.assertIsNone(p["acknowledged"])
        self.assertEqual(p["limit"], 2)

    def test_both_economy_work_kinds(self):
        for kind in ("find", "run"):
            self.req["work_kind"] = kind
            self.assertEqual(self.resolve()["dispatch"]["model"], self.choice["models"]["codex"])

    def test_unavailable_model(self):
        self.offers([dict(model="unrelated", efforts=["low"], fixed_behavior=None)])
        self.refuse(self.resolve())

    def test_unsupported_effort_no_substitution(self):
        other = "high" if self.choice["effort"] != "high" else "low"
        self.offers([dict(model=self.choice["models"]["codex"], efforts=[other], fixed_behavior=None)])
        self.refuse(self.resolve())

    def test_stale_and_future_evidence(self):
        for seconds in (901, -1):
            self.refuse(self.resolve(now=NOW + seconds))

    def test_tool_host_surface_session_source_and_contract_mismatch(self):
        for field, value in (("tool", "mcp__codex_app__send_message_to_thread"),
                             ("host", "cursor"), ("surface", "remote"),
                             ("session_id", "another"), ("source_sha256", "0" * 64),
                             ("contract_sha256", "0" * 64)):
            with self.subTest(field=field):
                previous = self.ev[field]
                self.ev[field] = value
                self.refuse(self.resolve())
                self.ev[field] = previous

    def test_base_dataset_evidence_does_not_authorize_new_pair(self):
        self.ev["source_sha256"] = n.source_digest(self.base_p, self.base_b)
        self.refuse(self.resolve())

    def test_no_implicit_effort_inheritance(self):
        self.offers([dict(model=self.choice["models"]["codex"], efforts=None, fixed_behavior=None)])
        self.refuse(self.resolve())

    def test_off_and_invalid_classification(self):
        for key, value in (("mode", "off"), ("work_kind", "invented"), ("tier", "standard")):
            prior = self.req[key]
            self.req[key] = value
            self.refuse(self.resolve())
            self.req[key] = prior

    def test_explicit_force_never_falls_back(self):
        self.req["mode"] = "force"
        self.req["selection"] = {k: self.choice[k] for k in ("provider", "family", "effort", "fixed_behavior")}
        self.offers([dict(model="unrelated", efforts=["low"], fixed_behavior=None)])
        self.refuse(self.resolve())

    def test_prelaunch_one_retry_after_wait_then_exhausted(self):
        p = self.resolve()
        rejected = n.observe(p, "prelaunch-rejected", now=NOW)
        self.assertEqual(self.resolve(continuation=rejected["continuation"])["status"], "waiting")
        again = self.resolve(now=NOW + 60, continuation=rejected["continuation"])
        self.assertEqual(again["dispatch"], p["dispatch"])
        rejected2 = n.observe(again, "prelaunch-rejected", now=NOW + 60)
        self.refuse(self.resolve(now=NOW + 60, continuation=rejected2["continuation"]))

    def test_not_offered_requires_refreshed_evidence(self):
        rejected = n.observe(self.resolve(), "not-offered", now=NOW)
        self.refuse(self.resolve(now=NOW + 60, continuation=rejected["continuation"]))

    def test_invalid_request_is_repair_not_availability_retry(self):
        result = n.observe(self.resolve(), "invalid-request", now=NOW)
        self.assertEqual(result["status"], "invalid-request")
        self.assertNotIn("continuation", result)
        self.assertIsNone(result["dispatch"])

    def test_started_failure_never_replans(self):
        running = n.observe(self.resolve(), "started", worker_id="synthetic-worker", acknowledged=None)
        self.assertIsNone(running["acknowledged"])
        self.assertIsNone(running["execution_matches_request"])
        for event in ("succeeded", "failed", "terminated"):
            result = n.observe(running, event)
            self.assertEqual(result["status"], event)
            self.assertNotIn("continuation", result)
        self.refuse(n.observe(running, "prelaunch-rejected"))

    def test_acknowledgement_mismatch_not_hidden(self):
        p = self.resolve()
        ack = dict(p["requested"], model="different-native-model", origin="native-tool")
        running = n.observe(p, "started", worker_id="synthetic-worker", acknowledged=ack)
        self.assertFalse(running["execution_matches_request"])

    def test_non_economy_codex_selections_unchanged(self):
        # Include all current semantic bindings; names and effort values are derived.
        rows = {}
        for choice in self.b["choices"].values():
            model = choice["models"]["codex"]
            if model:
                row = rows.setdefault(model, dict(model=model, efforts=[], fixed_behavior=None))
                if choice["effort"] not in row["efforts"]:
                    row["efforts"].append(choice["effort"])
        self.offers(list(rows.values()))
        for kind in ("build", "review", "design", "sign-off"):
            self.req["work_kind"] = kind
            self.req["author_provider"] = "openai" if kind in ("review", "sign-off") else None
            new = self.resolve()
            old_ev = dict(self.ev, source_sha256=n.source_digest(self.base_p, self.base_b))
            old = n.resolve(self.req, old_ev, self.base_p, self.base_b, now=NOW)
            for key in ("status", "dispatch", "requested", "warnings", "tier", "limit"):
                self.assertEqual(new.get(key), old.get(key), (kind, key))

    def test_cursor_all_offer_subsets_preserve_selection_and_warnings(self):
        models = sorted({c["models"]["cursor"] for c in self.base_b["choices"].values()
                         if c["models"]["cursor"]})
        for bits in itertools.product((False, True), repeat=len(models)):
            offered = [dict(model=m, efforts=None, fixed_behavior=None)
                       for m, keep in zip(models, bits) if keep]
            for kind in n.KINDS:
                ctx = dict(self.ctx, host="cursor", surface="local-macos-agents",
                           contract_sha256=n.digest(offered))
                ev = dict(self.ev, **ctx, tool="Task", models=offered)
                req = dict(self.req, context=ctx, work_kind=kind,
                           author_provider="openai" if kind in ("review", "sign-off") else None)
                new = n.resolve(req, ev, self.p, self.b, now=NOW)
                old_ev = dict(ev, source_sha256=n.source_digest(self.base_p, self.base_b))
                old = n.resolve(req, old_ev, self.base_p, self.base_b, now=NOW)
                for key in ("status", "dispatch", "requested", "warnings", "tier", "limit"):
                    self.assertEqual(new.get(key), old.get(key), (bits, kind, key))


if __name__ == "__main__":
    unittest.main()
