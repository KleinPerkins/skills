# Dispatch and finding protocol

Read this before dispatching a role or reading a role's response. Subagents are
**read-only analytical workers**. The parent owns authority interpretation, git
and runtime evidence, tests, mutations, and delivery.

There is no on-disk ledger. A dispatch is a charter instantiated from a
committed template, and a response is a plain JSON object validated with
`validate-finding`. The response stays lean, but candidate binding is exact:
parent-run `fingerprint` hashes every in-scope file's bytes and combines those
digests with the revision into `candidate_id`.

This file is the **single authored source** for the shared shapes below. The
charter templates (`charters/`) and the three sub-agent role files reference them
through the `{{finding_contract}}` and `{{probe_schema}}` substitution blocks
(see *Charter substitution blocks* at the end) instead of re-copying them, so the
section headings below are stable substitution targets — do not rename them.

## Dispatch (what the parent sends)

Instantiate a charter template from `charters/` by substitution and dispatch it
to the native role with the resolved catalog slug (`routing.md`). A dispatch
carries, in prose the subagent can act on:

- `run_id` and a stable `charter_id`;
- authoritative `candidate_id`, `assignment_id`, and `territory_id`;
- the resolved **model slug** and the **rigor obligation** (from `routing.md`);
- the exact **territory**: surfaces, dimensions (D01–D16), flows, and edge cases
  this charter owns — and the explicit omissions it does not;
- bounded neutral **evidence packs**: file/line sections, exact candidate
  identity, flow map, and overlap IDs; never probe conclusions;
- **evidence already supplied** by the parent versus evidence the reviewer may
  **request** the parent gather (never gather it itself);
- for a critical charter, `blind_to_probe: true` when it must not see probe
  conclusions;
- the required **return shape** below.

A role invoked without an orchestrator charter is inert: it returns a short
refusal and performs no review. Subagents never infer authority, never mutate,
never run shell/tests/network, and never delegate.

## Probe output (the intelligence source)

The one probe returns lean JSON — a *map* plus the sizing intelligence the
orchestrator needs to pick a band. No reviewer-count recommendation.

```json
{
  "candidate": {
    "candidate_id": "sha256:<64 lowercase hex>",
    "revision": "<revision>",
    "files": [
      { "path": "path/to/file.py", "sha256": "<64 hex>",
        "bytes": 1234, "lines": 74 }
    ]
  },
  "surface": {
    "roots": 1,
    "files_changed": 3,
    "lines_changed": 74,
    "impacted_surfaces": ["path/to/file.py:fn"],
    "flows": ["<critical flow, or none>"],
    "sections": [
      { "section_id": "auth-flow", "path": "path/to/file.py",
        "start_line": 1, "end_line": 74, "flows": ["authorize"] }
    ],
    "integration_points": [
      { "id": "auth-to-state", "territory_ids": ["auth", "state"],
        "section_ids": ["auth-flow"], "flow": "authorize then persist",
        "requires_reviewer": false }
    ]
  },
  "scores": { "D01": { "score": 22, "confidence": 85, "hotspot": false }, "…": "…all 16…" },
  "complexity": { "size_band": "trivial|small|moderate|large",
                  "depth": "shallow|deep",
                  "novelty": "familiar|novel" },
  "fix_character": "cosmetic|mixed|intrinsic",
  "protected_axes": { "state_migration_D03": false, "security_privacy_D04_D05": false,
                      "concurrency_D07": false, "reliability_release_D06_D16": false },
  "territories": [ { "id": "t1", "focus_area": "generic-surface",
                     "surfaces": ["…"], "section_ids": ["auth-flow"],
                     "dimensions": ["D01"], "why": "…" } ],
  "top_risks": [ { "dimension": "D04", "why": "…" } ],
  "unknowns": ["<bounded, or none>"],
  "recommended_band": "trivial|small|standard|deep|critical"
}
```

For source scopes above 2,000 lines, each territory names bounded
`section_ids`; the section map covers every in-scope file line.
`fix_character`, `complexity.size_band`, `protected_axes`, and `recommended_band`
are the decisive additions: they let the orchestrator justify **one** reviewer,
not only add reviewers. The orchestrator selects the final band itself
(`dimensions.md`) — `recommended_band` is advice, and `python3
scripts/swarm_cli.py size` recomputes it from the scores.

## Conformed finding shape (reviewer and verifier)

Every reviewer and the verifier share the **same lean base shape** so curation
is mechanical. The verifier adds only the clearance fields defined below. No
essays.

```json
{
  "role": "review",
  "charter_id": "t1-security",
  "candidate_id": "sha256:<exact candidate id>",
  "assignment_id": "review-auth-1",
  "territory_id": "auth",
  "territory": "auth surface",
  "findings": [
    {
      "finding_id": "authz-missing-owner-check",
      "focus_area": "security", "dimension": "D04",
      "root_cause": "one sentence",
      "evidence": [{ "ref": "file.py:42", "lineage": "source-confirmed" }],
      "impact": { "priority": "P1", "risk_score": 68, "confidence": 82 },
      "correction": "smallest sufficient fix",
      "status": "open"
    }
  ],
  "no_finding_evidence": ["paths examined with no issue"],
  "residual_uncertainty": ["bounded, or none"]
}
```

`role` maps by dispatch: reviewer → `review`, verifier → `verify`. A reviewer has
exactly the keys shown above. A verifier uses that base shape and adds these keys
inside the same JSON object:

```json
{
  "clearance_checks": {
    "critical_coverage_complete": true,
    "critical_probe_blind_review_complete": true,
    "revision_matches": true,
    "partial_rollout": false,
    "blockers": []
  },
  "shipping_clearance": "approved|failed"
}
```

The verifier does not self-attest scope, coverage, or accepted-risk authority.
The parent passes expected candidate/assignment IDs,
`expected_candidate_ids`, `authorized_accepted_risk_ids`, and parent-observed
`coverage_state` out-of-band. Coverage binds planned and current candidate IDs
and names required/completed/failed/partial assignments plus required/completed
probe-blind assignments. `findings` contains exactly one adjudication for every
expected finding ID and no extra ID.
`approved` is invalid if any adjudication is unresolved (`open` or
`insufficient-evidence`), any required check fails, `partial_rollout` is true, or
`blockers` is non-empty. It is also invalid on candidate drift, uncovered
required coverage, a failed/stalled/errored worker, malformed or partial output,
or missing required probe-blind coverage.
The two `critical_*_complete` booleans are true when their requirement is
satisfied or not applicable to this run, and false only when required but unmet.

Caps and rules:

- **≤6 findings and ≤16 KiB per reviewer.** One root cause per finding.
- Evidence **by reference, not excerpt** (`ref` = `path:line` or symbol); no
  source dumps, no repeated background.
- `finding_id` is a stable lowercase kebab id matching `[a-z][a-z0-9-]{2,127}`.
- `lineage ∈ {source-confirmed, parent-test-confirmed, externally-supplied,
  unverified}`. Only the parent may attach `parent-test-confirmed` after
  observing a real result. Never upgrade `unverified` to confirmed.
- `status ∈ {open, fixed, verified, duplicate, false-positive,
  insufficient-evidence, deferred, accepted-risk}`.
- Reviewers cannot return `accepted-risk`. A verifier may return it only for an
  ID in the parent's authoritative `authorized_accepted_risk_ids`, with
  confirmed evidence and confidence ≥70.
- A reviewer may set `verified` only with `parent-test-confirmed` evidence. A
  verifier may set it with independent `source-confirmed` evidence or
  `parent-test-confirmed` evidence.
- A verifier may use clearance-resolving `duplicate` or `false-positive` only
  with confirmed evidence and confidence ≥70; reviewer handling of those
  statuses is unchanged.
- **Confidence <70 can never be a "confirmed" finding.** 90–100 = reproduced or
  proven; 70–89 = strong code-path evidence; 40–69 = plausible, incomplete;
  1–39 = speculative.

## Risk and priority (the salvaged math)

`risk_score` is deterministic and comparable across reviewers:

```text
risk_score = round(20 × (
    0.40 × impact
  + 0.30 × likelihood
  + 0.15 × exposure
  + 0.15 × irreversibility))
```

where `impact`, `likelihood`, `exposure`, `irreversibility` are integers 1–5.
The lean shape carries the derived `priority`, `risk_score`, and `confidence`; a
reviewer includes the four calibration inputs only when a finding is contested.
`python3 scripts/swarm_cli.py risk` computes and validates the score.

Priority bands: **P0** = 90–100 or an independently verified unsafe-to-ship
state; **P1** = 70–89; **P2** = 40–69; **P3** = 10–39; **P4** = 1–9 or a
non-defect improvement note (all four inputs at 1).

## Evidence is parent-run only (the fan-out fix)

Reviewers **do not gather evidence.** When a reviewer needs git history, a test
run, runtime behavior, network, or an external fact, it names the need in
`residual_uncertainty` (or an inline evidence request) and the **parent answers
it by reading files or running tests in the parent context** — labeling any
runtime result `parent-test-confirmed` only after observing it.

**The swarm never dispatches a subagent to fulfill an evidence request.**
Evidence packs contain only neutral identity/file/section/flow facts. A
probe-blind reviewer receives that neutral map, not probe scores or conclusions.
Integration review appears only for an explicit cross-territory integration
point whose `requires_reviewer` is true.

## Worker accounting and time

`account` distinguishes preflight model rejection, rejected-before-worker
transport, accepted worker, and completion. Only accepted workers consume
band/absolute capacity, exactly once. Routing and transport fallback attempts
are separately bounded to one per assignment. A malformed, partial, stalled,
errored, cancelled, or timed-out completion is failed coverage.

New work stops after 20 minutes. This is not a completion kill switch: `plan`
computes a bounded 25–60 minute healthy completion allowance from source lines,
territory count, and depth. Inspect after five minutes without progress and stop
workers confirmed stalled; a healthy large review may continue past a
small-task target within its allowance.

## Verifier payload

A verifier runs only through the SKILL.md §7 gate. Its dispatch includes exact
candidate identity, planned and parent-observed coverage, collected
probe/reviewer JSON verbatim, candidate P0/P1 IDs, and accepted-risk
authorizations.
It independently:

- reproduces or traces independent evidence for each candidate P0/P1, returning
  exactly one adjudication per candidate under the same `finding_id`;
- checks contradictions between material findings (by evidence, not by vote);
- confirms required critical coverage and the probe-blind review on the Critical
  axis;
- confirms revision identity and flags partial rollout.

It decides `shipping_clearance` inside its single JSON return object; it never
performs shipping. If no verifier ran, the orchestrator records
`shipping_clearance = not_evaluated` — a verifier never emits that value. It
may emit `approved` only when every candidate has exactly one resolved
adjudication and all `clearance_checks` are clear.

The parent validates a verifier return with both authoritative arrays supplied
separately from the return:

```text
validate-finding --reviewer-return \
  --expected-candidate-id 'sha256:…' \
  --expected-assignment-id 'verifier' \
  --expected-candidate-ids '<JSON array>' \
  --authorized-accepted-risk-ids '<JSON array, [] when none>' \
  --coverage-state '<parent-observed JSON object>'
```

## Charter substitution blocks

Charters and role files never re-copy the shapes above. Instead they carry two
substitution tokens the orchestrator fills **verbatim from this file** at
instantiation. This is the anti-duplication rule: exactly one authored copy of
each shape lives here, each charter carries one token, and each role file carries
a pointer (not a copy).

- **`{{finding_contract}}`** expands to the §Conformed finding shape *with* its
  caps and lineage/status enums, together with the §Risk and priority formula and
  bands. Every reviewer charter (through `charters/SKELETON.md`) and the verifier
  charter carry this token in place of a hand-copied finding block. The
  orchestrator fills `charter_id`, `candidate_id`, `assignment_id`,
  `territory_id`, `territory`, and each finding's focus/dimension from the
  authoritative plan. Reviewers set `role` = `review`; the verifier sets `role` = `verify`,
  includes `clearance_checks` and `shipping_clearance` in the same object, and
  returns exactly the parent-supplied adjudication scope.
- **`{{probe_schema}}`** expands to the §Probe output JSON above. The probe
  charter (`charters/probe.md`) carries this token in place of a hand-copied
  schema; the probe also carries its own D01–D16 map because it is the only actor
  that scores all sixteen dimensions.

`charters/SKELETON.md` holds the shared reviewer RISEN scaffold (the eleven
reviewer charters are that skeleton plus a per-focus delta), and
`charters/INDEX.md` maps each territory `focus_area` to its charter file so only
the surfaced charters (1–4 of 13) are ever loaded.
