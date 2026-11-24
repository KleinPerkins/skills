"""Source-owner tests for a guarded refresh and paired receipt."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

from test_index import Fixture
from lib import engine
from lib.checkout_admission import CheckoutAdmission
from lib.contracts import Refusal, encode, fail
from lib.deadline import bound_until, deadline
from lib.io_safe import Publisher
from lib.receipt_store import (RECEIPT_INPUT_KEY, append_receipt_input, load_qualified_snapshot,
                               receipt_input, receipt_name)


class AdmittedCheckoutRefresh(Fixture):
    def setUp(self):
        super().setUp()
        self.authority = ("example-policy", 1, "a" * 64)
        self.revision = "b" * 40
        self.reads = []
        self.commits = []

    def admission(self):
        def probe(version, checkout, locations, read):
            self.assertEqual(version, self.authority)
            self.reads.append((checkout, locations))
            return read()

        def commit(version, checkouts, publish):
            self.assertEqual(version, self.authority)
            self.commits.append(checkouts)
            return publish()

        raw = self.cfgpath.read_bytes()
        return CheckoutAdmission(self.authority, sha256(raw).hexdigest(),
                                 "c" * 64, self.revision, probe, commit, config_bytes=raw)

    def refresh(self, admission=None, **kwargs):
        return engine.refresh_admitted(str(self.cfgpath), str(self.cache), admission or self.admission(), **kwargs)

    def test_exact_authority_at_reads_and_publication_matches_receipt(self):
        admission = self.admission()
        receipt = self.refresh(admission)
        self.assertEqual(self.reads, [(str(self.root), (("checkout", str(self.root)),)),
                                      (str(self.root), (("source", str(self.source)),))])
        self.assertEqual(self.commits, [(str(self.root),)])
        value, readback = load_qualified_snapshot(str(self.cache), admission)
        self.assertEqual(readback, receipt)
        self.assertEqual(receipt["snapshot_generation"], value["generation"])
        self.assertEqual(receipt["snapshot_digest"], sha256(self.cache.read_bytes()).hexdigest())
        self.assertNotIn("admitted_receipt_digest", value)
        self.assertEqual([item for item in value["inputs"] if item["key"] == RECEIPT_INPUT_KEY],
                         [receipt_input(admission, receipt)])
        self.assertEqual(receipt["inventory_digest"], self.authority[2])

    def test_config_mismatch_and_failed_final_gate_preserve_completed_snapshot(self):
        admission = self.admission()
        self.refresh(admission)
        original = self.cache.read_bytes()
        self.reads.clear()
        with self.assertRaises(Refusal) as mismatched:
            self.refresh(replace(admission, config_digest="0" * 64))
        self.assertEqual(mismatched.exception.code, "invalid_input")
        self.assertEqual(self.reads, [])

        def unavailable(*_):
            fail("unavailable", 3)

        with self.assertRaises(Refusal):
            self.refresh(replace(admission, commit=unavailable))
        self.assertEqual(self.cache.read_bytes(), original)

    def test_no_current_receipt_and_wrong_authority_refuse(self):
        admission = self.admission()
        latest = self.refresh(admission)
        wrong = replace(admission, inventory_version=(self.authority[0], 2, self.authority[2]))
        with self.assertRaises(Refusal):
            load_qualified_snapshot(str(self.cache), wrong)
        file = self.cache.with_name(receipt_name(self.cache.name, admission, latest["snapshot_digest"]))
        file.unlink()
        with self.assertRaises(Refusal):
            load_qualified_snapshot(str(self.cache), admission)
        after = self.refresh(admission)
        self.assertEqual(load_qualified_snapshot(str(self.cache), admission)[1], after)

    def test_probe_deadline_interrupts_a_read_without_ending_the_refresh_budget(self):
        with deadline(2):
            with self.assertRaises(Refusal) as expired:
                with bound_until(time.monotonic() + 0.01):
                    time.sleep(0.2)
            self.assertEqual(expired.exception.code, "bound_exceeded")
            with bound_until(time.monotonic() + 0.2):
                self.assertEqual(1 + 1, 2)

    def test_later_checkout_cannot_erase_an_identity_conflict_for_the_same_repository(self):
        remote = "https://code.example/team/project"
        self.cfg["roots"][0]["identity"] = {"provider": "github:901", "remote": remote}
        conflicting = self.base / "different-origin"
        git = conflicting / ".git"
        git.mkdir(parents=True)
        (git / "config").write_text('[remote "origin"]\n url = https://code.example/team/different.git\n')
        root = self.root_record()
        root.update(key="conflicting", path=str(conflicting), sources=[],
                    git={"common_dir": str(git), "git_dir": str(git)},
                    identity={"provider": "github:901", "remote": remote})
        self.cfg["roots"].append(root)
        self.write_config()
        receipt = self.refresh()
        value, _ = load_qualified_snapshot(str(self.cache), self.admission())
        repository, = [entity for entity in value["entities"] if entity["kind"] == "repository"]
        self.assertEqual(receipt["result"]["status"], "partial")
        self.assertIn("identity", repository["conflicts"])
        self.assertEqual(receipt["input_diagnostics"]["inventory/conflicting"],
                         {"state": "conflict", "reason": "source_failed"})

    def test_first_source_failure_distinguishes_absence_from_an_intentional_omission(self):
        data = dict(self.cfg["roots"][0]["sources"][0], path="blocked.json")
        self.cfg["roots"][0]["sources"].append(data)
        self.cfg["exclude_paths"] = [str(self.root / "blocked.json")]
        self.source.write_text("{malformed")
        self.write_config()
        receipt = self.refresh()
        value, stored = load_qualified_snapshot(str(self.cache), self.admission())
        self.assertEqual(receipt, stored)
        self.assertEqual(stored["input_diagnostics"], {
            "inventory/fixture/eligible.json": {"state": "unavailable", "reason": "invalid_input"},
            "inventory/fixture/blocked.json": {"state": "omitted", "reason": "excluded"},
        })
        self.assertEqual([row["key"] for row in value["inputs"]], ["inventory/fixture", RECEIPT_INPUT_KEY])

    def test_repeat_source_failure_retains_stale_reason_and_refuses_mismatched_receipt(self):
        admission = self.admission()
        self.refresh(admission)
        self.source.write_text("{malformed")
        report = self.refresh(admission)
        evidence = report["input_diagnostics"]
        self.assertEqual(evidence, {"inventory/fixture/eligible.json": {"state": "stale", "reason": "invalid_input"}})
        current = self.cache.with_name(receipt_name(self.cache.name, admission, report["snapshot_digest"]))
        changed = json.loads(current.read_bytes())
        changed["input_diagnostics"]["inventory/fixture/eligible.json"]["state"] = "omitted"
        current.write_text(json.dumps(changed))
        with self.assertRaises(Refusal):
            load_qualified_snapshot(str(self.cache), admission)

    def test_same_aggregate_failure_is_attributed_to_the_correct_checkout(self):
        unrelated = self.base / "unrelated"
        unrelated.mkdir()
        row = self.root_record()
        row.update(key="unrelated", path=str(unrelated), identity={"provider": None,
                   "remote": "https://code.example/team/unrelated.git"})
        self.cfg["roots"].append(row)
        self.write_config()
        other = unrelated / "eligible.json"
        original = self.source.read_bytes()
        other.write_bytes(original.replace(b"capability:sample", b"capability:unrelated"))
        self.source.write_text("{broken")
        selected_failed = self.refresh()
        self.source.write_bytes(original)
        other.write_text("{broken")
        unrelated_failed = self.refresh()
        self.assertEqual(selected_failed["result"]["reasons"], unrelated_failed["result"]["reasons"])
        self.assertEqual(selected_failed["input_diagnostics"], {
            "inventory/fixture/eligible.json": {"state": "unavailable", "reason": "invalid_input"}})
        self.assertEqual(unrelated_failed["input_diagnostics"], {
            "inventory/unrelated/eligible.json": {"state": "stale", "reason": "invalid_input"}})

    def test_readback_refuses_unknown_or_missing_input_diagnostics(self):
        self.source.write_text("{malformed")
        admission = self.admission()
        report = self.refresh(admission)
        receipt = self.cache.with_name(receipt_name(self.cache.name, admission, report["snapshot_digest"]))
        original = receipt.read_bytes()
        for key, state, reason in (
            ("inventory/fixture/not-configured.json", "unavailable", "invalid_input"),
            ("inventory/unknown", "omitted", "excluded"),
        ):
            with self.subTest(key=key):
                changed = json.loads(original)
                changed["input_diagnostics"][key] = {"state": state, "reason": reason}
                receipt.write_text(json.dumps(changed))
                with self.assertRaisesRegex(Refusal, "unavailable"):
                    load_qualified_snapshot(str(self.cache), admission)
        changed = json.loads(original)
        changed["input_diagnostics"].clear()
        receipt.write_text(json.dumps(changed))
        with self.assertRaisesRegex(Refusal, "unavailable"):
            load_qualified_snapshot(str(self.cache), admission)
        receipt.write_bytes(original)
        self.assertEqual(load_qualified_snapshot(str(self.cache), admission)[1], report)

    def test_ordinary_and_admitted_writers_keep_distinct_locks(self):
        admission = self.admission()
        with Publisher(str(self.cache)):
            with self.assertRaises(Refusal) as blocked:
                self.refresh(admission)
            self.assertEqual(blocked.exception.code, "busy")
        self.refresh(admission)
        with self.assertRaises(Refusal) as blocked:
            self.build()
        self.assertEqual(blocked.exception.code, "busy")

    def test_readback_refuses_changed_counts_and_failure_reasons(self):
        self.source.write_text("{malformed")
        admission = self.admission()
        report = self.refresh(admission)
        receipt = self.cache.with_name(receipt_name(self.cache.name, admission, report["snapshot_digest"]))
        original = receipt.read_bytes()
        for key in ("parsed", "reused"):
            with self.subTest(count=key):
                changed = json.loads(original)
                changed["result"]["counts"][key] += 1
                receipt.write_text(json.dumps(changed))
                with self.assertRaisesRegex(Refusal, "unavailable"):
                    load_qualified_snapshot(str(self.cache), admission)
        changed = json.loads(original)
        changed["input_diagnostics"]["inventory/fixture/eligible.json"]["reason"] = "source_failed"
        receipt.write_text(json.dumps(changed))
        with self.assertRaisesRegex(Refusal, "unavailable"):
            load_qualified_snapshot(str(self.cache), admission)
        receipt.write_bytes(original)
        self.assertEqual(load_qualified_snapshot(str(self.cache), admission)[1], report)

    def test_readback_accepts_earlier_commitment_and_refuses_mixed_forms(self):
        admission = self.admission()
        report = self.refresh(admission)
        value = json.loads(self.cache.read_bytes())
        commitment = receipt_input(admission, report)
        value["admitted_receipt_digest"] = commitment["digest"]

        def publish_fixture():
            raw = encode(value)
            self.cache.write_bytes(raw)
            snapshot_digest = sha256(raw).hexdigest()
            result = {**report["result"], "snapshot_digest": snapshot_digest}
            expected = admission.receipt(result, value["observed_at"], report["input_diagnostics"])
            destination = self.cache.with_name(receipt_name(self.cache.name, admission, snapshot_digest))
            destination.write_bytes(encode(expected))
            destination.chmod(0o600)
            return expected

        publish_fixture()
        with self.assertRaisesRegex(Refusal, "unavailable"):
            load_qualified_snapshot(str(self.cache), admission)
        value["inputs"].remove(commitment)
        expected = publish_fixture()
        self.assertEqual(load_qualified_snapshot(str(self.cache), admission), (value, expected))

    def test_receipt_commitment_does_not_overwrite_an_existing_input(self):
        admission = self.admission()
        report = self.refresh(admission)
        existing = receipt_input(admission, report)
        inputs = [existing]
        with self.assertRaisesRegex(Refusal, "unavailable"):
            append_receipt_input(inputs, admission, report)
        self.assertEqual(inputs, [existing])

    def test_real_process_exit_after_pair_install_releases_admitted_lock(self):
        admission = self.admission()
        old = self.refresh(admission)
        code = '''
import hashlib, os, sys
from lib import engine
from lib.checkout_admission import CheckoutAdmission
from lib.receipt_store import AdmittedPublisher
config, cache = sys.argv[1:]
with open(config, 'rb') as stream:
    raw = stream.read()
digest = hashlib.sha256(raw).hexdigest()
admission = CheckoutAdmission(('example-policy', 1, 'a'*64), digest, 'c'*64, 'b'*40,
    lambda version, checkout, paths, read: read(), lambda version, paths, publish: publish(),
    config_bytes=raw)
publish = AdmittedPublisher.publish
def stop(self, *args, **kwargs):
    publish(self, *args, **kwargs)
    os._exit(78)
AdmittedPublisher.publish = stop
engine.refresh_admitted(config, cache, admission)
'''
        child = subprocess.run([sys.executable, "-B", "-c", code, str(self.cfgpath), str(self.cache)],
                               cwd=Path(engine.__file__).resolve().parents[1],
                               capture_output=True, check=False, timeout=10)
        self.assertEqual(child.returncode, 78, child.stderr)
        value, receipt = load_qualified_snapshot(str(self.cache), admission)
        self.assertEqual(value["generation"], old["snapshot_generation"] + 1)
        self.assertEqual(value["generation"], receipt["snapshot_generation"])
        self.assertEqual(self.refresh(admission)["snapshot_generation"], value["generation"] + 1)
