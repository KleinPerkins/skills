#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from capability_meta import (  # noqa: E402
    ALLOWED_KEYS,
    MetadataError,
    PLAN_MAGIC,
    QUOTABLE_KEYS,
    build_action_plan,
    discover_metadata,
    parse_metadata,
    render_action_plan,
)

BASE_METADATA = b"""schema: kp-capability/v1
id: fixture
kind: skill
flavor: 1
scope: global
owner: test
install: install.sh
"""


class CapabilityMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, payload: bytes) -> Path:
        path = self.root / "meta.yml"
        path.write_bytes(payload)
        return path

    def assert_invalid(self, payload: bytes) -> None:
        with self.assertRaises(MetadataError):
            parse_metadata(self.write(payload))

    def make_skill(
        self,
        root: Path,
        capability_id: str,
        *,
        scope: str = "global",
        shelf: str = "skills",
        extra: str = "",
    ) -> Path:
        capability = root / scope / shelf / capability_id
        capability.mkdir(parents=True)
        (capability / "meta.yml").write_text(
            "\n".join(
                [
                    "schema: kp-capability/v1",
                    f"id: {capability_id}",
                    "kind: skill",
                    "flavor: 1",
                    f"scope: {scope}",
                    "owner: test",
                    "install: install.sh",
                    extra.rstrip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (capability / "SKILL.md").write_text(
            f"---\nname: {capability_id}\ndescription: Fixture.\n---\n",
            encoding="utf-8",
        )
        installer = capability / "install.sh"
        installer.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        installer.chmod(0o755)
        return capability

    def test_real_manifest_inventory_matches_explicit_allowlist(self) -> None:
        paths = discover_metadata(REPO)
        self.assertEqual(len(paths), 39)
        observed = set()
        observed_quoted = set()
        runtime_contracts = []
        for path in paths:
            values = parse_metadata(path)
            observed.update(values)
            for raw in path.read_bytes().splitlines():
                if b":" not in raw or raw.startswith(b"#"):
                    continue
                key, value = raw.split(b":", 1)
                if value.strip(b" \t")[:1] in (b'"', b"'"):
                    observed_quoted.add(key.decode("ascii"))
            if "runtime_contract" in values:
                runtime_contracts.append((path, values["runtime_contract"]))
        self.assertEqual(observed, set(ALLOWED_KEYS))
        self.assertEqual(
            observed_quoted,
            set(QUOTABLE_KEYS) - {"runtime_contract"},
        )
        self.assertEqual(
            runtime_contracts,
            [
                (
                    REPO / "local/skills/isokit/meta.yml",
                    "installer-doctor/v1",
                )
            ],
        )

    def test_runtime_contract_is_optional_and_has_three_lexical_forms(self) -> None:
        omitted = parse_metadata(self.write(BASE_METADATA))
        self.assertNotIn("runtime_contract", omitted)
        for scalar in (
            b"installer-doctor/v1",
            b"'installer-doctor/v1'",
            b'"installer-doctor/v1"',
        ):
            with self.subTest(scalar=scalar):
                values = parse_metadata(
                    self.write(
                        BASE_METADATA + b"runtime_contract:\t" + scalar + b"\t\n"
                    )
                )
                self.assertEqual(values["runtime_contract"], "installer-doctor/v1")

    def test_empty_quoted_generic_values_remain_valid(self) -> None:
        values = parse_metadata(
            self.write(
                BASE_METADATA
                + b'provenance_source: ""\n'
                + b"provenance_ref: ''\n"
            )
        )
        self.assertEqual(values["provenance_source"], "")
        self.assertEqual(values["provenance_ref"], "")

    def test_malformed_unknown_and_confusable_keys_are_rejected(self) -> None:
        cases = (
            b"runtime:contract: installer-doctor/v1\n",
            b'"runtime:contract": installer-doctor/v1\n',
            b"'runtime:contract': installer-doctor/v1\n",
            b"runtime#contract: installer-doctor/v1\n",
            b"runtime_ contract: installer-doctor/v1\n",
            b"runtime contract: installer-doctor/v1\n",
            b"runtime\tcontract: installer-doctor/v1\n",
            b"runtime_\tcontract: installer-doctor/v1\n",
            b"runtime\x1bcontract: installer-doctor/v1\n",
            b"runtime_\x0ccontract: installer-doctor/v1\n",
            b"runtime_\x7fcontract: installer-doctor/v1\n",
            b"runtime\x00contract: installer-doctor/v1\n",
            b"Runtime_contract: installer-doctor/v1\n",
            b"RUNTIME_CONTRACT: installer-doctor/v1\n",
            b"runtime-contract: installer-doctor/v1\n",
            b"runtime.contract: installer-doctor/v1\n",
            b"runtime/contract: installer-doctor/v1\n",
            b"runtime\\contract: installer-doctor/v1\n",
            b'"runtime_contract": installer-doctor/v1\n',
            b"'runtime_contract': installer-doctor/v1\n",
            b"runtimecontract: installer-doctor/v1\n",
            b"runtime__contract: installer-doctor/v1\n",
            b"runtimec_ontract: installer-doctor/v1\n",
            "runtimé_contract: installer-doctor/v1\n".encode(),
            b"future_key: value\n",
            b" runtime_contract: installer-doctor/v1\n",
            b"runtime_contract : installer-doctor/v1\n",
            b'expose: "cursor"\n',
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assert_invalid(payload)

    def test_duplicate_known_keys_are_rejected(self) -> None:
        self.assert_invalid(b"owner: one\nowner: two\n")

    def test_missing_required_keys_are_rejected(self) -> None:
        self.assert_invalid(b"id: incomplete\n")

    def test_scalar_comments_colons_quotes_and_controls_are_rejected(self) -> None:
        cases = (
            b"runtime_contract: installer-doctor/v1 # comment\n",
            b"runtime_contract:: installer-doctor/v1\n",
            b"runtime_contract: unsupported/v9\n",
            b'runtime_contract: ""\n',
            b"runtime_contract: installer - doctor/v1\n",
            b"runtime_contract: installer\t-\tdoctor/v1\n",
            b"runtime_contract: installer   -   doctor/v1\n",
            b"runtime_contract: xinstaller-doctor/v1\n",
            b"runtime_contract: installer-doctor/v1-extra\n",
            b'runtime_contract: "installer-doctor/v1\n',
            b"runtime_contract: installer-doctor/v1'\n",
            b'runtime_contract: "installer-"doctor/v1"\n',
            b'runtime_contract: " installer-doctor/v1 "\n',
            b"runtime_contract: installer-\x1bdoctor/v1\n",
            b"runtime_contract: installer-doctor/v1\x00\n",
            b"owner: invalid\xff\n",
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assert_invalid(payload)

    def test_column_zero_utf8_comments_are_valid_but_indented_comments_are_not(self) -> None:
        values = parse_metadata(
            self.write(
                "# punctuation: — allowed in comments\n".encode() + BASE_METADATA
            )
        )
        self.assertEqual(values["id"], "fixture")
        self.assert_invalid(b" # indented comment\nid: fixture\n")

    def test_symlink_metadata_path_is_rejected(self) -> None:
        target = self.root / "target.yml"
        target.write_bytes(BASE_METADATA)
        link = self.root / "meta.yml"
        link.symlink_to(target)
        with self.assertRaises(MetadataError):
            parse_metadata(link)

    def test_tree_discovery_rejects_stale_or_unknown_shelf_layouts(self) -> None:
        stale = self.root / "global" / "stale" / "meta.yml"
        stale.parent.mkdir(parents=True)
        stale.write_text("id: stale\n", encoding="utf-8")
        with self.assertRaises(MetadataError):
            discover_metadata(self.root)

        stale.unlink()
        unknown = self.root / "global" / "unknown-shelf" / "fixture" / "meta.yml"
        unknown.parent.mkdir(parents=True)
        unknown.write_text("id: fixture\n", encoding="utf-8")
        with self.assertRaises(MetadataError):
            discover_metadata(self.root)

    def test_action_plan_is_deterministic_complete_and_space_safe(self) -> None:
        manifests = build_action_plan(REPO)
        self.assertEqual(len(manifests), 39)
        self.assertEqual(
            [manifest.directory for manifest in manifests],
            sorted(manifest.directory for manifest in manifests),
        )
        isokit = next(
            manifest for manifest in manifests if manifest.capability_id == "isokit"
        )
        self.assertEqual(isokit.runtime_contract, "installer-doctor/v1")
        self.assertEqual(
            (isokit.expose_cursor, isokit.expose_claude, isokit.expose_codex),
            ("1", "1", "1"),
        )
        self.assertEqual(render_action_plan(REPO), render_action_plan(REPO))
        self.assertTrue(
            render_action_plan(REPO).startswith(f"{PLAN_MAGIC}\0".encode("utf-8"))
        )

        spaced_root = self.root / "repository with spaces"
        capability = self.make_skill(spaced_root, "space-safe")
        payload = render_action_plan(spaced_root)
        self.assertIn(f"{capability}\0".encode("utf-8"), payload)

    def test_action_plan_rejects_semantic_ambiguity(self) -> None:
        cases = {
            "unknown expose": "expose: cursor future",
            "mixed none": "expose: none cursor",
            "duplicate expose": "expose: cursor cursor",
            "unsafe install": "install: ../install.sh",
        }
        for name, extra in cases.items():
            with self.subTest(name=name):
                root = self.root / name.replace(" ", "-")
                capability = self.make_skill(root, "fixture", extra=extra)
                if name == "unsafe install":
                    metadata = capability / "meta.yml"
                    metadata.write_text(
                        metadata.read_text(encoding="utf-8").replace(
                            "install: install.sh\n", ""
                        ),
                        encoding="utf-8",
                    )
                with self.assertRaises(MetadataError):
                    build_action_plan(root)

        missing_root = self.root / "missing-payload"
        missing = self.make_skill(missing_root, "missing")
        (missing / "SKILL.md").unlink()
        with self.assertRaises(MetadataError):
            build_action_plan(missing_root)

        duplicate_root = self.root / "duplicate-id"
        self.make_skill(duplicate_root, "duplicate", scope="global")
        self.make_skill(duplicate_root, "duplicate", scope="local")
        with self.assertRaises(MetadataError):
            build_action_plan(duplicate_root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
