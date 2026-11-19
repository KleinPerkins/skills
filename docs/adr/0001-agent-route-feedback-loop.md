# ADR 0001: Agent-route feedback loop uses a per-entry learned multiplier, not global weight tuning
Status: draft — 2026-08-06

## Decision

Add a durable operator-feedback loop to `agent-route`: capture confirmed/corrected/rejected
verdicts on routing decisions in an append-only log, and let that evidence adaptively reweight
only the specific registry entries a feedback event names — via a small, bounded, per-entry score
multiplier — never by tuning `agent-route`'s global scoring weights.

## Why

Two alternatives were considered for what "adaptive weights" should mean here:

1. **Tune the global weight constants** (`W_KEYWORD`, `W_ALIAS`, `W_DOMAIN`, etc. in
   [`lib/score.py`](../../global/skills/agent-route/lib/score.py)) directly from accumulated
   feedback. Rejected: `agent-route` is a single-operator tool with sparse feedback (single digits
   to low tens of events/week) spanning roughly 150 unrelated registry roots. Tuning shared,
   global constants from that little data would overfit to whichever handful of repos happen to
   generate feedback in a given week, and cross-contaminate scoring for the ~140 other roots the
   feedback never mentions.
2. **A per-registry-entry learned multiplier**, scoped to exactly the root(s) named in a feedback
   event. Chosen: this is the statistically sound version of "adaptive weights" at this data
   volume, and it is exactly what would have helped in the live case that motivated this ADR —
   routing `"operator-voice"` scored the canonical `capabilities/operator-voice` checkout at 55 and
   the unrelated `personal/operator-voice-profile` repo at 49, a close-enough margin to produce a
   `weak` verdict even after an unrelated staleness bug (154 registry roots including 8 vanished
   AWA worktrees) was fixed by `discover --full`. A global weight change cannot distinguish "these
   two specific repos are a close call" from "the whole scoring formula is miscalibrated"; a
   per-entry multiplier can, because it only ever moves the entries feedback actually named.

This also has a direct precedent already in the codebase:
[`merge_overlay()`](../../global/skills/agent-route/lib/index_build.py) (`lib/index_build.py:139`)
already carries curated/pinned fields forward, per entry, across every `build_registry` rebuild.
The new `learned` block reuses that exact carry-forward shape for a second, engine-derived
(rather than operator-authored) field — it is not a new persistence mechanism, only a new field
riding the existing one.

For *when* feedback is captured, a hybrid trigger was chosen over the two single-mode
alternatives: passive-only (misses cases where the operator never spontaneously comments on a
correct-but-unverified route) and proactive-only (asks after every route, adding friction to the
common, already-confident case). The hybrid — passive capture on any spontaneous operator
confirm/correct regardless of verdict, plus one proactive yes/no ask but *only* after a `weak` or
`none` verdict — captures the actual friction point (the router's own uncertainty) without nagging
on `strong` verdicts, which are already correct today.

## Consequences

- Registry entries gain an engine-managed `learned` block (`confirmations`, `corrections_toward`,
  `corrections_away`, `rejections`, `multiplier`, `last_feedback_at`) that nudges
  `score_root()`'s output for that one root only. The multiplier is clamped (e.g. `0.6`–`1.4`) so
  it can narrow or widen a close margin but can never manufacture a match from zero underlying
  signal or override a result the existing keyword/alias/domain/etc. contributions have already
  strongly differentiated.
- `learned` must be classified as engine-derived history, never an operator-authored overlay field
  — it must not, by itself, make an entry `_is_operator_curated` (`lib/index_build.py:118`). A
  root that disappears from disk must still drop on the next `discover`, taking its stale learned
  history with it, exactly like the ghost-worktree pruning that motivated this session. Violating
  this would let feedback about a long-deleted worktree permanently distort scoring for a path that
  no longer exists.
- This ADR explicitly forecloses, for this decision: tuning `agent-route`'s global weights from
  feedback, auto-writing new keywords/aliases from feedback text, cross-session recall of routing
  decisions outside the current agent's context, and query-shape-scoped learning. These are
  recorded as non-goals in the companion plan (`docs/plans/agent-route-feedback-loop-v1.md` §2) and
  would each need their own future ADR if evidence later justifies revisiting them.
- The companion plan tracks the concrete work items, sequencing, and acceptance tests for
  implementing this decision; that plan may be superseded by a later `-v2` as work proceeds, but
  this ADR's decision remains stable independent of that revision history.
