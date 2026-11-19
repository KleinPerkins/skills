import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import privacy  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "privacy"
CURRENT_V1_ADVERSARIAL_DIR = Path(__file__).resolve().parent / "fixtures" / "current.v1"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


class TestPanDetection(unittest.TestCase):
    def test_luhn_valid_pan_is_redacted(self):
        doc = _load("adversarial-pan.json")
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("pan_like_digit_sequence", rule_ids)
        self.assertNotIn("4111", redacted["objective"])
        self.assertNotIn("1111 1111 1111", redacted["objective"])

    def test_non_luhn_digit_run_is_not_flagged_as_pan(self):
        # 16 digits, deliberately NOT a valid Luhn number -> must not false-positive.
        doc = {"objective": "Reference number 1234567890123456 for the internal ledger."}
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertNotIn("pan_like_digit_sequence", {f.rule_id for f in findings})


class TestEmailAndPhoneDetection(unittest.TestCase):
    def test_email_and_phone_both_redacted(self):
        doc = _load("adversarial-email-phone.json")
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("email_address", rule_ids)
        self.assertIn("phone_number", rule_ids)
        text = redacted["current_action"]["description"]
        self.assertNotIn("jane.doe@example.com", text)
        self.assertNotIn("415-555-0132", text)


class TestSecretAndConfidentialityMarkers(unittest.TestCase):
    def test_known_secret_marker_redacted(self):
        doc = _load("adversarial-secret-marker.json")
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("known_secret_marker", {f.rule_id for f in findings})
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redacted["notes"])

    def test_confidentiality_marker_redacted(self):
        doc = _load("adversarial-confidentiality-marker.json")
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("confidentiality_marker", {f.rule_id for f in findings})


class TestHighEntropySecret(unittest.TestCase):
    def test_high_entropy_token_flagged(self):
        doc = {"notes": "token=aK9$mZ2pQwX7vR4tL8sN1cJ6dF3hB0gY5uE order confirmed"}
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})

    def test_low_entropy_repeated_string_not_flagged(self):
        doc = {"notes": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertNotIn("high_entropy_secret", {f.rule_id for f in findings})


class TestKebabCaseExemption(unittest.TestCase):
    def test_kebab_case_identifier_passes_clean(self):
        doc = {
            "objective": "Coordinate with the pr-automation-controller service before the next release window."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertNotIn("high_entropy_secret", rule_ids)
        self.assertIn("pr-automation-controller", redacted["objective"])

    def test_kebab_case_identifier_generalizes(self):
        doc = {
            "next_action": "Sync the continual-learning-consolidate output before the review."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertNotIn("high_entropy_secret", rule_ids)
        self.assertIn("continual-learning-consolidate", redacted["next_action"])

    def test_hex_digest_in_prose_still_redacted(self):
        digest = "eef8f44c81200799f76ac61c4c7d554256665e510c5f1ae84848f49eb818304b"
        doc = {
            "objective": f"Reference commit {digest} in the changelog."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("high_entropy_secret", rule_ids)
        self.assertNotIn(digest, redacted["objective"])

    def test_case_mixed_kebab_identifier_still_redacted(self):
        doc = {
            "objective": "Coordinate with the PR-Automation-Controller service before release."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn("PR-Automation-Controller", redacted["objective"])


class TestStructuredIdentifierExemption(unittest.TestCase):
    def test_reported_bug_token_path_qualified_milestone_id_passes_clean(self):
        # The exact reported false positive: a versioned/milestone-numbered doc
        # path. `_HIGH_ENTROPY_TOKEN_RE`'s charset includes '/' but not '.', so
        # the match stops before ".md" -- the 35-char token that reaches the
        # entropy check is "docs/plans/gen3-m2-control-plane-v1" itself.
        doc = {
            "next_action": "Update docs/plans/gen3-m2-control-plane-v1.md before the review."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertNotIn("high_entropy_secret", rule_ids)
        self.assertIn("docs/plans/gen3-m2-control-plane-v1.md", redacted["next_action"])

    def test_four_digit_version_suffix_passes_clean(self):
        # Proves the widened {0,4} digit-suffix cap: "gen1024" is a segment
        # with a 4-digit trailing run, still letters-then-digits, never
        # digit-first or interleaved.
        doc = {
            "objective": "See docs/plans/gen1024-milestone-summary for the full writeup."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertNotIn("high_entropy_secret", rule_ids)
        self.assertIn("docs/plans/gen1024-milestone-summary", redacted["objective"])

    def test_uuid_shaped_token_still_redacted(self):
        # Critical anti-regression guard: a UUID mixes letters and digits in
        # no fixed order within each hyphen-separated group (e.g. "e5f6",
        # "47a8"), so it can never be consumed by the "word-run then
        # digit-run" grammar -- it must remain fully detected regardless of
        # the {0,4} digit cap.
        token = "a1b2c3d4-e5f6-47a8-9b2c-1d3e4f5a6b7c"
        doc = {"objective": f"Session token {token} rotated at 09:00."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(token, redacted["objective"])

    def test_base64_secret_with_slash_still_redacted(self):
        # Same critical base64/'/' regression guard as #88, re-asserted
        # against the new, broader exemption (which also allows '/' as a
        # separator) to confirm it didn't accidentally widen scope here.
        secret = "xJ8k2/Rp9vQmZ7Lw+Yc3Ht6Nb0Fd4Sg1MjKz5Wo="
        doc = {"objective": f"Rotate AUTH_TOKEN={secret} immediately."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(secret, redacted["objective"])

    def test_mixed_case_digit_high_entropy_token_still_redacted(self):
        token = "aK9mZ2pQwX7vR4tL8sN1cJ6dF3hB0gY5uE1nC8xP"
        doc = {"objective": f"Rotate secret {token} before Friday."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(token, redacted["objective"])

    def test_maximally_varied_letters_token_exempted_known_residual_risk(self):
        # KNOWN, ACCEPTED RESIDUAL RISK (surfaced by Security Review on this
        # PR, verified and knowingly kept -- see the long comment above
        # `_STRUCTURED_IDENTIFIER_RE`): a shape check can't distinguish a
        # word-like segment that happens to use every letter of the alphabet
        # (high Shannon entropy) from a normal identifier. This exact
        # tradeoff already existed unconditionally in #87's original
        # `_PURE_WORDLIKE_RE` before this PR -- not a new class of risk.
        doc = {
            "objective": "See abcdefghijklmnopqrstuvwxyz/abcdefghijklmnopqrstuvwxyz for details."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertNotIn("high_entropy_secret", {f.rule_id for f in findings})

    def test_digit_suffixed_word_like_token_exempted_known_residual_risk(self):
        # KNOWN, ACCEPTED RESIDUAL RISK (same Security Review finding): the
        # digit-suffix widening this PR adds means a constructed, word-like,
        # digit-suffixed multi-segment token can also carry high entropy
        # (~4.36 bits/char here) and gets exempted. Real CSPRNG-generated
        # secrets don't spell recognizable words like this -- see the
        # comment above `_STRUCTURED_IDENTIFIER_RE` for the full reasoning
        # on why this is accepted rather than patched with a fragile
        # entropy-ceiling threshold.
        doc = {
            "objective": "Rotate session8392-token4821-key1234-backup5678 before Friday."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertNotIn("high_entropy_secret", {f.rule_id for f in findings})

    def test_bare_digit_led_segment_still_redacted_known_deferred_gap(self):
        # KNOWN DEFERRED GAP, not a regression: ADR-style filenames with a
        # bare digit-led segment (no leading letter, e.g. "0007") don't match
        # `_STRUCTURED_IDENTIFIER_RE` (which requires letters before any
        # digit run) and are still redacted. Deliberately deferred rather
        # than folded into this fix -- a blanket digit-segment allowance
        # would risk exempting real numeric-heavy secret formats. Needs its
        # own narrower rule if this ever reproduces in practice.
        doc = {
            "next_action": "Review 0007-use-postgres-for-storage before merging."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn("0007-use-postgres-for-storage", redacted["next_action"])


class TestGitShaExemption(unittest.TestCase):
    def test_real_git_sha_in_prose_passes_clean(self):
        # An actual commit SHA from this repo's own history, embedded in a
        # realistic next_action note — this must survive redaction untouched.
        sha = "5526691bdd48ce2585ea16099729cde2d149f9ff"
        doc = {
            "next_action": f"Verify commit {sha} merged cleanly before starting the next phase."
        }
        redacted, findings = privacy.scan_and_redact_document(doc)
        rule_ids = {f.rule_id for f in findings}
        self.assertNotIn("high_entropy_secret", rule_ids)
        self.assertIn(sha, redacted["next_action"])

    def test_short_abbreviated_sha_is_not_even_a_candidate_token(self):
        # A 7-char abbreviated SHA never reaches the 24-char floor of
        # _HIGH_ENTROPY_TOKEN_RE on its own, so it was never reachable via
        # this rule in the first place -- no dedicated exemption is needed.
        doc = {"next_action": "See commit 5526691 for context on this change."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertNotIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertIn("5526691", redacted["next_action"])

    def test_uppercase_hex40_token_still_redacted(self):
        # Git never emits uppercase SHAs -- the exemption is case-sensitive,
        # so an uppercase 40-char hex-shaped token is not a real git SHA and
        # must remain fully detected, same as before this fix.
        token = "5526691BDD48CE2585EA16099729CDE2D149F9FF"
        doc = {"objective": f"Reference token {token} in the audit log."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(token, redacted["objective"])

    def test_mixed_alnum_40_length_token_still_redacted(self):
        # Same length as a git SHA but not pure lowercase hex -- must still
        # be flagged so the shape exemption stays narrowly scoped to SHAs.
        token = "aK9mZ2pQwX7vR4tL8sN1cJ6dF3hB0gY5uE1nC8xP"
        doc = {"objective": f"Rotate secret {token} before Friday."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(token, redacted["objective"])

    def test_base64_secret_with_slash_still_fully_redacted(self):
        # Critical regression guard: this fix must not touch the shared
        # _HIGH_ENTROPY_TOKEN_RE character class (which still needs '/' for
        # real base64 secrets), so a realistic base64 secret containing a
        # slash must still be detected as ONE token and fully removed --
        # not merely split at the '/' into a leaked, partially-redacted
        # remnant on either side.
        secret = "xJ8k2/Rp9vQmZ7Lw+Yc3Ht6Nb0Fd4Sg1MjKz5Wo="
        doc = {"objective": f"Rotate AUTH_TOKEN={secret} immediately."}
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIn("high_entropy_secret", {f.rule_id for f in findings})
        self.assertNotIn(secret, redacted["objective"])
        self.assertNotIn("xJ8k2", redacted["objective"])
        self.assertNotIn("Rp9vQmZ7Lw", redacted["objective"])
        self.assertEqual(len(findings), 1)


class TestStructuralExemption(unittest.TestCase):
    def test_whole_value_hex64_digest_is_never_scanned(self):
        doc = _load("clean.json")
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertEqual(findings, [])
        self.assertEqual(redacted["workstream_key"], doc["workstream_key"])

    def test_whole_value_timestamp_is_never_scanned(self):
        doc = {"created_at": "2026-08-01T09:00:00Z"}
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertEqual(findings, [])

    def test_reuses_phase1_adversarial_current_fixture_without_crashing(self):
        # Phase 1's oversized-field adversarial fixture (long repeated "x" objective).
        doc = json.loads((CURRENT_V1_ADVERSARIAL_DIR / "adversarial-oversized-field.json").read_text())
        redacted, findings = privacy.scan_and_redact_document(doc)
        self.assertIsInstance(redacted, dict)
        self.assertIsInstance(findings, list)


class TestClassification(unittest.TestCase):
    def test_clean_document_classifies_clean(self):
        doc = _load("clean.json")
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertEqual(privacy.classification_for(findings), "clean")

    def test_document_with_findings_classifies_redacted(self):
        doc = _load("adversarial-pan.json")
        _, findings = privacy.scan_and_redact_document(doc)
        self.assertEqual(privacy.classification_for(findings), "redacted")

    def test_findings_never_carry_the_raw_match(self):
        doc = _load("adversarial-pan.json")
        _, findings = privacy.scan_and_redact_document(doc)
        for f in findings:
            self.assertNotIn("4111", f.sample)


class TestFailsClosed(unittest.TestCase):
    def test_scanner_exception_raises_privacy_gate_error(self):
        with mock.patch("engine.privacy._walk_redact", side_effect=RuntimeError("scanner exploded")):
            with self.assertRaises(privacy.PrivacyGateError):
                privacy.scan_and_redact_document({"objective": "x"})


if __name__ == "__main__":
    unittest.main()
