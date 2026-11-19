#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
GLOBAL = SKILL.parents[1]
AGENT_ROOT = GLOBAL / "sub-agents"
MODEL_CATALOG_PATH = (
    GLOBAL / "rules" / "subagent-orchestration" / "model-tiers.json"
)
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import swarm_cli  # noqa: E402
import swarm_helper as helper  # noqa: E402

INERT = (
    "INERT: this internal swarm agent requires a complete instantiated "
    "role-specific charter from the swarm orchestrator. No review performed."
)
AGENTS = ("swarm-probe", "swarm-reviewer", "swarm-verifier")
ROLE_CHARTER = {
    "swarm-probe": "probe.md",
    "swarm-reviewer": "SKELETON.md",
    "swarm-verifier": "verifier.md",
}
# Phase 1A collapsed the modular contract engine into a single helper plus the
# lone CLI entry point. Nothing else may live in scripts/.
HELPER_MODULES = {"swarm_helper.py", "swarm_cli.py"}
# Acceptance canaries (SKILL.md §Proportionality guarantees; evals/evals.json).
ACCEPTANCE_EVALS = {
    "trivial-fast-path",
    "small-targeted",
    "standard-specialist",
    "deep-gated-verifier",
    "critical-redundancy",
    "waiver-visibility",
    "dedup-fix-groups",
    "budget-guard",
    "fan-out-guard",
    "routing-no-inheritance",
    "prompt-architect-coupling",
    "runaway-regression",
}

# Progressive-disclosure composition (Phase 1B). charters/ holds 13 dispatchable
# templates (probe + verifier + 11 reviewer deltas) PLUS three non-template
# support files that must be excluded from any template enumeration/count.
CHARTERS_DIR = SKILL / "references" / "charters"
NON_TEMPLATE_CHARTERS = {"SKELETON.md", "INDEX.md", "PROVENANCE.md"}
STANDALONE_TEMPLATES = {"probe.md", "verifier.md"}
REVIEWER_CHARTER_STEMS = {
    "generic-surface", "api-contract-compat", "data-integrity-migration",
    "security-authz", "privacy-secrets", "reliability-failure",
    "concurrency-ordering", "performance", "testing-evidence",
    "architecture-maintainability", "policy-governance",
}
# The five just-in-time decision verbs the lean router queries instead of
# pre-loading doctrine prose, plus the pre-existing deterministic verbs.
JIT_CLI_VERBS = {"route-probe", "route", "gate-verifier", "gate-second-pass", "plan"}
BASE_CLI_VERBS = {
    "risk", "size", "validate-finding", "budget", "account", "fingerprint",
    "render",
}
# Shared contract fragments single-sourced in protocol.md that must appear in NO
# charter body (the anti-duplication win). Each is ASCII-safe and distinctive.
SINGLE_SOURCE_MARKERS = (
    '"finding_id":',   # conformed finding shape (JSON)
    '"root_cause":',   # conformed finding shape (JSON)
    "round(20",         # risk formula
    "0.40",             # risk formula weight
    "16 KiB",           # reviewer-return cap
    "6 findings",       # reviewer-return cap
)


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path}: missing opening frontmatter")
    end = lines.index("---", 1)
    result = {}
    for line in lines[1:end]:
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


class StaticContractTests(unittest.TestCase):
    def test_routing_uses_the_shared_catalog(self) -> None:
        self.assertTrue(MODEL_CATALOG_PATH.is_file())
        helper_text = (SKILL / "scripts" / "swarm_helper.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MODEL_CATALOG_PATH", helper_text)
        self.assertNotIn('MODEL_CATALOG = {', helper_text)

    def test_skill_progressive_disclosure_and_trigger_description(self) -> None:
        path = SKILL / "SKILL.md"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 500)
        metadata = frontmatter(path)
        self.assertEqual(metadata["name"], "swarm")
        for phrase in (
            "launch the swarm",
            "dispatch the swarm",
            "swarm this",
            "Docker Swarm",
        ):
            self.assertIn(phrase, metadata["description"])
        for reference in (
            "dimensions.md",
            "routing.md",
            "protocol.md",
            "authority.md",
            "report.md",
            "fallback.md",
        ):
            self.assertTrue((SKILL / "references" / reference).is_file())
            self.assertIn(reference, "\n".join(lines))

    def test_agents_are_internal_read_only_and_protocol_aligned(self) -> None:
        for agent in AGENTS:
            path = AGENT_ROOT / agent / f"{agent}.md"
            text = path.read_text(encoding="utf-8")
            metadata = frontmatter(path)
            self.assertEqual(metadata["name"], agent)
            # Shared payloads carry no model default; every native dispatch must
            # pass its routed model explicitly.
            self.assertNotIn("model", metadata, agent)
            self.assertEqual(metadata["tools"], "Read, Glob, Grep")
            self.assertIn("Internal read-only", metadata["description"])
            self.assertNotIn("swarm-dispatch/v1", text)
            self.assertNotIn("envelope", text.lower())
            self.assertIn(INERT, text)
            self.assertRegex(text, r"Do not run shell commands or tests")
            self.assertRegex(text, r"Do not .*mutate")

    def test_role_guards_require_their_own_charter_substitutions(self) -> None:
        for agent, charter_name in ROLE_CHARTER.items():
            role_text = (AGENT_ROOT / agent / f"{agent}.md").read_text(
                encoding="utf-8"
            )
            charter_text = (CHARTERS_DIR / charter_name).read_text(
                encoding="utf-8"
            )
            declaration = next(
                line for line in charter_text.splitlines()
                if line.startswith("substitution_vars:")
            )
            variables = re.findall(r"\{\{([a-z_]+)\}\}", declaration)
            self.assertTrue(variables, charter_name)
            guard = re.search(
                r"It must supply\s+(.*?)with no\s+unresolved",
                role_text,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(guard, agent)
            guard_variables = re.findall(r"`([a-z_]+)`", guard.group(1))
            self.assertEqual(set(guard_variables), set(variables), agent)
            self.assertRegex(
                role_text,
                r"no\s+unresolved `\{\{\.\.\.\}\}` or\s+`\[\[\.\.\.\]\]` placeholders",
            )
            body = charter_text.split("-->", 1)[1]
            assignment = body.split("ASSIGNMENT:", 1)[1].split(
                "\n\nINSTRUCTIONS:", 1
            )[0]
            rendered = re.findall(
                r"^([a-z_]+) = \{\{([a-z_]+)\}\}$",
                assignment,
                flags=re.MULTILINE,
            )
            self.assertTrue(all(name == token for name, token in rendered), agent)
            self.assertEqual({name for name, _ in rendered}, set(variables), agent)

    def test_retry_and_fallback_failure_classes_stay_distinct(self) -> None:
        routing = (SKILL / "references" / "routing.md").read_text(encoding="utf-8")
        self.assertIn("Resolution precedes launch", routing)
        self.assertIn("Transport fallback is separately bounded", routing)
        self.assertIn("rejected-before-worker", routing)
        self.assertIn("retry the same assigned model", routing)
        self.assertIn("never triggers model fallback", routing)

    def test_host_model_bindings_are_explicit(self) -> None:
        routing = (SKILL / "references" / "routing.md").read_text(encoding="utf-8")
        fallback = (SKILL / "references" / "fallback.md").read_text(encoding="utf-8")
        self.assertIn("**Cursor:** pass the returned concrete `slug`", routing)
        self.assertIn("**Claude:** pass this explicit host-native alias", routing)
        for row in (
            "| `economy` | `haiku` | `sonnet` |",
            "| `standard` | `sonnet` | `opus` |",
            "| `deep` | `sonnet` | `opus` |",
            "| `critical` | `opus` | `sonnet` |",
        ):
            self.assertIn(row, routing)
        self.assertIn("**Codex:** native swarm roles are unavailable", routing)
        self.assertIn("parent-led fallback", routing)
        self.assertIn("Shared role payloads intentionally have no `model:` default", routing)
        self.assertIn("omission\nand `inherit` are invalid", routing)
        self.assertIn("--runtime-models", routing)
        self.assertIn("never emits one", routing)
        self.assertIn("Preserve each route's returned `model_class` and `rigor`", fallback)
        self.assertIn("model_slug = parent-led-fallback:<returned-slug>", fallback)

    def test_role_specific_markers(self) -> None:
        expected = {
            "swarm-probe": ("D01\u2013D16", "cartographer", "recommended_band"),
            "swarm-reviewer": ("probe-blind", "`role` is `review`"),
            "swarm-verifier": ("adjudicator", "`shipping_clearance` to `failed`"),
        }
        for agent, markers in expected.items():
            text = (AGENT_ROOT / agent / f"{agent}.md").read_text(encoding="utf-8")
            for marker in markers:
                self.assertIn(marker, text, f"{agent}: missing {marker!r}")

    def test_twelve_acceptance_evals_are_present(self) -> None:
        data = json.loads((SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], "swarm")
        names = [item["name"] for item in data["evals"]]
        self.assertEqual(len(names), len(set(names)), "duplicate eval name")
        self.assertEqual(set(names), ACCEPTANCE_EVALS)
        for item in data["evals"]:
            self.assertGreaterEqual(len(item["assertions"]), 3, item["name"])
            self.assertTrue(item["prompt"].strip(), item["name"])
            self.assertTrue(item["expected_output"].strip(), item["name"])

    def test_scripts_are_helper_and_cli_only(self) -> None:
        scripts = SKILL / "scripts"
        modules = {p.name for p in scripts.glob("*.py")}
        self.assertEqual(modules, HELPER_MODULES)
        for name in HELPER_MODULES:
            path = scripts / name
            self.assertTrue(path.is_file(), name)
            head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
            self.assertIn('"""', head, f"{name}: missing module docstring")
        cli_text = (scripts / "swarm_cli.py").read_text(encoding="utf-8")
        self.assertIn("__main__", cli_text, "swarm_cli.py must be the entry point")

    def test_global_payload_has_no_environment_specific_paths(self) -> None:
        forbidden = (
            "/" + "Users/",
            "~/" + "dev/",
            "affirm/" + "src",
            "affirm/" + "vendor",
            "card-" + "platform-product",
        )
        roots = [SKILL, *(AGENT_ROOT / agent for agent in AGENTS)]
        for root in roots:
            for path in root.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    text = path.read_text(encoding="utf-8")
                    self.assertFalse(
                        any(marker.lower() in text.lower() for marker in forbidden),
                        str(path),
                    )

    def test_offline_fixture_does_not_claim_agent_benchmark_semantics(self) -> None:
        report = json.loads(
            (SKILL / "evals" / "offline-fixture-report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["classification"], "offline-deterministic")
        self.assertFalse(report["agent_evaluation"])
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("estimated_protocol_tokens", serialized)
        self.assertNotIn('"reviewers"', serialized)
        self.assertIn("not agent latency or token cost", report["semantics"])

    # --- Progressive-disclosure composition (Phase 1B) ---

    def _charter_templates(self) -> list[Path]:
        """The dispatchable charter templates: SKELETON/INDEX/PROVENANCE excluded."""
        return sorted(
            p for p in CHARTERS_DIR.glob("*.md")
            if p.name not in NON_TEMPLATE_CHARTERS
        )

    def test_charter_enumeration_excludes_support_files(self) -> None:
        # The three support files exist, but are NOT dispatchable templates.
        for name in NON_TEMPLATE_CHARTERS:
            self.assertTrue((CHARTERS_DIR / name).is_file(), name)
        template_names = {p.name for p in self._charter_templates()}
        self.assertEqual(len(template_names), 13, sorted(template_names))
        self.assertEqual(
            {p.stem for p in self._charter_templates()},
            REVIEWER_CHARTER_STEMS | {"probe", "verifier"},
        )
        # SKELETON/INDEX/PROVENANCE are never counted as templates.
        self.assertTrue(NON_TEMPLATE_CHARTERS.isdisjoint(template_names))

    def test_reviewer_charters_carry_the_finding_contract_token(self) -> None:
        # Every reviewer charter (and the verifier) carries the substitution token
        # instead of a hand-copied finding block; the probe carries the probe
        # schema instead (it returns a map, not findings).
        for stem in REVIEWER_CHARTER_STEMS:
            text = (CHARTERS_DIR / f"{stem}.md").read_text(encoding="utf-8")
            self.assertIn("{{finding_contract}}", text, stem)
        for name in ("SKELETON.md", "verifier.md"):
            self.assertIn(
                "{{finding_contract}}",
                (CHARTERS_DIR / name).read_text(encoding="utf-8"), name,
            )
        probe = (CHARTERS_DIR / "probe.md").read_text(encoding="utf-8")
        self.assertIn("{{probe_schema}}", probe)
        self.assertNotIn("{{finding_contract}}", probe)

    def test_shared_contract_is_single_sourced_in_protocol(self) -> None:
        protocol = (SKILL / "references" / "protocol.md").read_text(encoding="utf-8")
        for marker in SINGLE_SOURCE_MARKERS:
            self.assertIn(marker, protocol, f"protocol.md must own {marker!r}")
        # Zero hand-copies: no charter body re-states the finding shape, caps, or
        # risk formula — they carry the {{finding_contract}} token instead.
        for path in CHARTERS_DIR.glob("*.md"):
            body = path.read_text(encoding="utf-8")
            for marker in SINGLE_SOURCE_MARKERS:
                self.assertNotIn(
                    marker, body, f"{path.name} re-copies {marker!r} (must use a token)"
                )

    def test_cli_exposes_the_jit_decision_verbs(self) -> None:
        parser = swarm_cli._build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        verbs = set(sub.choices)
        self.assertTrue(JIT_CLI_VERBS <= verbs, f"missing JIT verbs: {JIT_CLI_VERBS - verbs}")
        self.assertTrue(BASE_CLI_VERBS <= verbs, f"missing base verbs: {BASE_CLI_VERBS - verbs}")

    def test_probe_focus_area_forms_route_to_their_specialist_charter(self) -> None:
        # Flag #1 reconciliation: the probe emits territories[].focus_area in the
        # LONG charter-name form (INDEX.md routing keys, e.g. "security-authz").
        # The CLI map must route each to its OWN specialist charter — never
        # silently to generic-surface — or specialist coverage is lost.
        index = (CHARTERS_DIR / "INDEX.md").read_text(encoding="utf-8")
        routing_keys = set()
        for line in index.splitlines():
            stripped = line.strip()
            if "swarm-reviewer" in stripped and stripped.startswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                routing_keys.add(cells[0])
        # INDEX's reviewer routing keys == exactly the committed charter ids.
        self.assertEqual(routing_keys, set(helper.CHARTER_IDS))
        # Every emitted form routes to its own specialist (identity map), so a
        # specialist territory is never downgraded to generic-surface.
        for key in routing_keys:
            self.assertEqual(helper.charter_for(key), key, key)

    def test_skill_spine_numbering_is_load_bearing(self) -> None:
        # protocol.md references SKILL.md §5/§7 and authority.md references §8; the
        # numbered spine anchors must stay put (flag #5 — do not renumber).
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for anchor in ("## 5.", "## 7.", "## 8."):
            self.assertIn(anchor, skill, anchor)

    def test_authority_second_pass_matches_code_binding(self) -> None:
        # The second pass is bound by the 20-min start-new-work cutoff, not
        # framed as a literal completion deadline.
        authority = (SKILL / "references" / "authority.md").read_text(encoding="utf-8")
        self.assertIn("start-new-work", authority)
        self.assertNotIn("25-minute budget remains", authority)

    def test_v2_preflight_and_clearance_doctrine_is_explicit(self) -> None:
        protocol = (SKILL / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        dimensions = (SKILL / "references" / "dimensions.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "candidate_id",
            "bounded neutral **evidence packs**",
            "Worker accounting and time",
            "parent-observed",
        ):
            self.assertIn(marker, protocol)
        self.assertIn("3,000 lines", dimensions)
        self.assertRegex(dimensions, r"capacity\s+refusal")
        self.assertIn("never use one as a", dimensions)

    def test_token_budget_regression(self) -> None:
        # Locks the progressive-disclosure win: the always-loaded router stays lean
        # and the shared contract stays de-duplicated. Bites if a future edit
        # re-bloats SKILL.md or re-copies the finding contract into charters.
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        words = len(skill_text.split())
        line_count = len(skill_text.splitlines())
        self.assertLessEqual(words, 900, f"SKILL.md grew to {words} words (router must stay lean)")
        self.assertLess(line_count, 500, f"SKILL.md grew to {line_count} lines")
        duplicated = 0
        for path in CHARTERS_DIR.glob("*.md"):
            body = path.read_text(encoding="utf-8")
            duplicated += sum(body.count(marker) for marker in SINGLE_SOURCE_MARKERS)
        self.assertEqual(duplicated, 0, "shared contract re-duplicated into charters/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
