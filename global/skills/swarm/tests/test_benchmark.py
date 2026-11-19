#!/usr/bin/env python3
"""Execute an offline deterministic marker-scanner fixture.

This is not an agent-quality, token-cost, or orchestration benchmark. It checks
only fixture integrity, monotonic marker coverage, and non-mutation.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "benchmark_cases.json"
REPORT = Path(__file__).parents[1] / "evals" / "offline-fixture-report.json"
SCANNER_COHORTS = (0, 1, 4, 8, 12)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def scan(root: Path, patterns: list[str], known: dict[str, dict]) -> list[dict]:
    findings = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in text:
                defect = known[pattern]
                findings.append(
                    {
                        "id": defect["id"],
                        "dimension": defect["dimension"],
                        "evidence": f"{path.name}:{pattern}",
                        "priority": "P1",
                    }
                )
    return findings


def offline_fixture_run() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    known = {item["marker"]: item for item in data["material_defects"]}
    expected_ids = {item["id"] for item in data["material_defects"]}
    rows = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for name, content in data["files"].items():
            (root / name).write_text(content, encoding="utf-8")
        pristine = tree_digest(root)
        for scanner_count in SCANNER_COHORTS:
            started = time.perf_counter_ns()
            scans = [
                {
                    "scanner": "baseline",
                    "findings": scan(root, data["baseline_markers"], known),
                }
            ]
            for index, patterns in enumerate(
                data["scanner_lenses"][:scanner_count], start=1
            ):
                scans.append(
                    {
                        "scanner": f"marker-set-{index}",
                        "findings": scan(root, patterns, known),
                    }
                )
            confirmed = {
                finding["id"]
                for response in scans
                for finding in response["findings"]
            }
            serialized = json.dumps(
                scans, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            rows.append(
                {
                    "name": "baseline-only"
                    if scanner_count == 0
                    else f"{scanner_count}-scanner-sets",
                    "scanner_sets": scanner_count,
                    "matched_material_markers": sorted(confirmed),
                    "material_marker_recall": round(
                        len(confirmed) / len(expected_ids), 4
                    ),
                    "fixture_mutations": int(tree_digest(root) != pristine),
                    "observed_runtime_ms": round(
                        (time.perf_counter_ns() - started) / 1_000_000, 4
                    ),
                    "serialized_scan_bytes": len(serialized),
                }
            )
    return {
        "schema": "swarm-offline-fixture-result/v1",
        "classification": "offline-deterministic",
        "agent_evaluation": False,
        "semantics": (
            "Marker-scanner fixture only; runtime and serialized bytes are "
            "local harness measurements, not agent latency or token cost."
        ),
        "fixture": FIXTURE.name,
        "cohorts": rows,
    }


class OfflineFixtureTests(unittest.TestCase):
    def test_offline_fixture_is_monotonic_and_non_mutating(self) -> None:
        result = offline_fixture_run()
        rows = result["cohorts"]
        self.assertFalse(result["agent_evaluation"])
        self.assertEqual(
            [row["scanner_sets"] for row in rows],
            list(SCANNER_COHORTS),
        )
        baseline = rows[0]["material_marker_recall"]
        for row in rows:
            self.assertEqual(row["fixture_mutations"], 0)
            self.assertGreaterEqual(
                row["material_marker_recall"], baseline
            )
            self.assertGreater(row["observed_runtime_ms"], 0)
            self.assertGreater(row["serialized_scan_bytes"], 0)

    def test_recorded_artifact_preserves_offline_fixture_results(self) -> None:
        observed = offline_fixture_run()["cohorts"]
        recorded = json.loads(REPORT.read_text(encoding="utf-8"))["cohorts"]
        self.assertEqual(
            [
                (
                    row["scanner_sets"],
                    row["material_marker_recall"],
                    row["fixture_mutations"],
                )
                for row in recorded
            ],
            [
                (
                    row["scanner_sets"],
                    row["material_marker_recall"],
                    row["fixture_mutations"],
                )
                for row in observed
            ],
        )


if __name__ == "__main__":
    result = offline_fixture_run()
    print(json.dumps(result, indent=2, sort_keys=True))
    unittest.main(verbosity=2)
