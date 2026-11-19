# Model and rigor routing

Every routing decision carries a **runtime-supported concrete catalog slug**,
tier, and rigor. There is no lazy parent-model inheritance anywhere.

## Rigor is a charter obligation, not a runtime knob

Cursor's Task API accepts a concrete model slug but exposes **no runtime effort
parameter**: each offered slug is fixed at the level last chosen for that model
in the picker. Compute therefore scales two ways only:

1. **The slug.** The tier picks the model; its level comes with it.
2. **A stated review-rigor obligation** written into the charter instructions —
   the evidence bar and reasoning depth the reviewer must meet. The rigor per
   tier is the table below, not catalog data.

Never claim a runtime compute knob the API does not expose, and never place an
"effort" value in a `methods` field. Rigor is prose in the charter, enforced by
the evidence lineage the reviewer returns.

## Shared catalog

The only tier → slug mapping is the sibling global rule capability
`rules/subagent-orchestration/model-tiers.json`. `swarm_helper.py` loads it
directly in both source and installed capability layouts. Do not copy the
mapping into this file. When the live list drifts, the fix is a one-file edit
to that catalog.

Candidate order is preference order; later candidates from another provider
are bounded failover.

The executing Cursor Subagent tool's concrete model enum is authoritative for
that session. Pass it as `--runtime-models '<JSON array>'` to every `route-*`,
`route`, and `plan` call. The resolver filters candidates before dispatch,
selects the first configured match, and reports stale candidates under
`filtered_models`. It never emits one. If a tier has no configured runtime
match, preflight fails precisely with zero launches for that role.

## Host bindings

- **Cursor:** pass the returned concrete `slug` to the native subagent. On a
  rejected-before-worker transport failure, try at most the next returned
  `fallbacks` slug. Every returned fallback was already runtime-filtered.
- **Claude:** pass this explicit host-native alias on every invocation while
  preserving the returned `rigor`:

  | model_class | Primary alias | Fallback alias |
  |---|---|---|
  | `economy` | `haiku` | `sonnet` |
  | `standard` | `sonnet` | `opus` |
  | `deep` | `sonnet` | `opus` |
  | `critical` | `opus` | `sonnet` |

- **Codex:** native swarm roles are unavailable, so use the parent-led fallback
  in `fallback.md` while preserving the returned `model_class` and `rigor`;
  never silently downgrade.

Shared role payloads intentionally have no `model:` default. Every native
dispatch must pass its routed Cursor slug or Claude alias explicitly; omission
and `inherit` are invalid.

## Role routing

| Role / obligation | Tier | Rigor obligation |
|---|---|---|
| Probe — default | `standard` | standard |
| Probe — pre-probe trivial (1 root, ≤5 files, ≤100 lines, no protected paths) | `economy` | light |
| Probe — pre-probe heavy (multi-root + protected/security/release surface) | `deep` | deep |
| Reviewer — basic (score <40, bundled) | `economy` | light |
| Reviewer — targeted (40–59) | `standard` | standard |
| Reviewer — specialist/strong (60–89) | `deep` | deep |
| Reviewer — critical (≥90) | `critical` | max |
| Verifier — P1 / critical shipping gate | `deep` | deep |
| Verifier — P0 / unsafe-to-ship | `critical` | max |

## Rules

- **No parent-model inheritance.** Cursor dispatches pass an explicit catalog
  slug; Claude dispatches pass the explicit host-native alias above — never
  omit the model, use `inherit`, or use "same as parent."
- **The probe is never routed off its own scores** (no circular routing). Probe
  model is chosen from **pre-probe facts only**: declared-root count, changed
  file/line counts, and presence of protected paths (security, privacy, data
  migration, release). Reviewer/verifier slugs *are* chosen from probe scores.
- **Resolution precedes launch.** A catalog preference absent from the runtime
  enum is filtered in one preflight decision; it is not a rejected launch and
  consumes no worker/coverage capacity.
- **Transport fallback is separately bounded.** After resolution, a genuine
  rejected-before-worker transport/model refusal may use only the next returned
  fallback, once for that assignment. It consumes no accepted-worker capacity.
  If none remains, name the assignment as uncovered. Never inherit or silently
  downgrade.
- **Bad output is a charter failure, not a model failure.** For `INERT`, non-JSON,
  or contract-invalid output, inspect and correct the instantiated charter once,
  then retry the same assigned model only if accepted-worker capacity remains.
  Each accepted worker counts exactly once. A malformed, partial, stalled, or
  errored completion remains failed coverage even if a later retry succeeds; it
  never triggers model fallback and is never counted as "no findings."
- **Rigor tracks the slug.** The rigor obligation in the charter matches the
  routing row so the review depth and the model choice cannot drift apart.

The band → cohort mapping that decides *how many* reviewers of each class to
route lives in `dimensions.md`; this file decides *which slug* each dispatched
role carries.
