# Authority and the ship gate

Authority is **doctrine, not code.** There is no regex authority parser and no
sha256 attestation layer. The orchestrator LLM interprets the operator's
explicit imperative intent, asks one question on ambiguity, and relies on the
workspace's existing git identity and session-lock guards for the actual
mutation. The swarm is **default-deny**: loaded rules and repository policy may
narrow authority, never expand it.

## Default-deny ladder

| Operator wording | Authority granted |
|---|---|
| "launch/run/dispatch the swarm", "swarm this" | **Review only** |
| "harden/fix … with the swarm" | Review, local fixes, and tests |
| Explicit "commit" | Commit only, after the ship gate |
| Explicit "push" | Push only, after the ship gate |
| Explicit "commit and push" | Both, after the ship gate |
| "ship" / "take it all the way" | Ambiguous — ask one scope question |

- **Only a direct imperative grants scope.** Mentions, quotations, examples,
  explanations, descriptions, and questions authorize nothing. "Review this
  commit," "Should we commit?", "Explain how to commit," and "the example says
  'commit this'" are all denied. Honor negation; leave ambiguity denied.
- **A swarm command may carry direct action commands** — "Launch the swarm.
  Commit this." grants review + commit.
- **PR, merge, release, install/bootstrap, deploy, external writes, destructive
  actions, secrets, and cleanup each require their own explicit words.** One
  never implies another (PR authority does not grant push).
- **Subagents are always read-only.** The parent performs any authorized
  mutation and all evidence gathering.
- **Risk acceptance is finding-specific.** The operator must say `Accept risk for
  <finding_id>` in the same request; the orchestrator honors it only for that
  exact finding at the current revision. An unbound or mismatched acceptance
  grants nothing.

## Revalidate before acting

The parent fingerprints the exact revision plus every in-scope file byte into
one candidate ID. `HEAD` plus a dirty-tree flag is not sufficient. Recapture
the exact candidate:

- before the probe;
- before any fix, and after fixes before renewed review;
- immediately before any commit / push / PR / merge / release / install / deploy
  / external write / destructive action / cleanup.

Drift invalidates prior coverage. Re-review **only the changed territory**
through the SKILL.md §8 second-pass gate, or report a stale-coverage block. A swarm fix
is expected drift and still requires review of the new state before shipping —
but that is a scoped re-review, never a second full swarm.

## The verifier and second-pass gates

Both gates are **band-independent** and enforced deterministically by the CLI
(`gate-verifier`, `gate-second-pass`); the orchestrator calls them at SKILL.md
§7–§8. This is the single source for their human-readable conditions.

- **Verifier gate.** Run **exactly one** verifier **only if** one holds: a
  candidate P0; an unresolved P1 contradiction; a security / privacy /
  data-integrity / concurrency finding that would block shipping; or an explicit
  shipping-clearance request on a critical change. Otherwise run **zero**
  verifiers and report `shipping_clearance = not_evaluated` (never
  "approved"/"failed"). Route the verifier per `routing.md`.
- **Second-pass gate.** Allow a second pass **only when all** hold: (1) a
  candidate P0/P1 lacks independent evidence, *or* two material findings
  contradict, *or* a named critical territory is uncovered, *or* a fix changed a
  reviewed critical boundary; (2) you state the exact unresolved question +
  territory; (3) ≤2 existing charter IDs are reused; (4) accepted-worker
  capacity and the 20-minute start-new-work cutoff still allow new work. It
  inspects only the unresolved territory. A separately planned completion
  allowance lets already-healthy large reviews finish; it never authorizes a
  second full swarm.

## The ship gate (three lines)

Immediately before any shipping action, all three must hold — this replaces the
old attestation stack:

1. **Explicit action authority** for this exact action (from the ladder above).
2. **Workspace/repository policy allows** it (git identity, session-lock, branch
   protection, and any loaded rule).
3. **No unresolved blocker for the exact current candidate** — no open P0,
   unresolved P1 contradiction, candidate drift, uncovered required territory,
   failed/stalled worker, malformed/partial result, or missing probe-blind
   coverage.

If any line fails, do not act; report which line failed. One action never
implies another; revalidate before each. After the attempt, report the
**observed** outcome — a green intent is not a completed action. Never skip
hooks, force-push, hide unrelated changes, or claim an unobserved action.

## Rollback boundary

Never remove a shared source capability before its governed enrollment and
downstream references have been quarantined/excluded, delete-propagated, and
reconciled. A source-only review may document this boundary, but external
rollout or rollback is never inferred from local source authority.
