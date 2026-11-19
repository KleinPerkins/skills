# Native dispatch interface

`native_dispatch.py` is the opt-in INT-009 source interface. The existing
`verify_model_tiers.py`, `model-tiers.json`, installed rule, installer, metadata,
and swarm interface remain unchanged. Dev's INT-007B owns instruction activation.
This module does not install, register, launch, sleep, authenticate, or write files.
It is an implementation of the accepted interoperability design's model contract;
it does not replace the existing Cursor ADR 0006/0008 behavior.

## Source and selection

The existing v2 catalog remains the ordered preference policy.
`native-model-bindings.json` gives each candidate an explicit provider, family,
effort or fixed behavior, and opaque per-host model identifier. A missing binding
is unavailable; no family or provider is inferred from a token's spelling.
The three additional Codex bindings are available only for an explicit override
under the approved bootstrap mapping. They are not adopted tier preferences.

The request separates work kind (`find`, `run`, `build`, `review`, `design`,
`sign-off`) from difficulty (`normal`, or `raised` with a stronger `tier` and
`raise_reason`). Normal difficulty preserves the existing tier. Effort has no
implicit maximum: it comes from the selected policy choice or exact override,
and must be supported by current native evidence.

`mode: auto` follows policy; `mode: force` requires an exact semantic `selection`;
`mode: off` returns unavailable with no dispatch. Force is a scoped caller input,
not persistent catalog adoption or evidence of operator authorization. The caller
must have an actual user override/approved mapping. An unavailable forced choice
never falls back to another choice. Known host support and freshness remain
required. These are new-interface modes, not historical Cursor CLI options.

## Caller contract

Run `python3 native_dispatch.py source-digest` from the source directory. Observe
the current native tool's offered models and supported efforts immediately before
planning. Account/API catalogs do not qualify. Build a `native-offers/v1` object:

```json
{
  "schema": "native-offers/v1",
  "host": "codex",
  "surface": "local-macos-desktop",
  "session_id": "the-current-session",
  "contract_sha256": "sha256-of-canonical-models-array",
  "host_build": null,
  "tool": "collaboration.spawn_agent",
  "origin": "native-tool",
  "observed_at": "2026-10-27T20:00:00+00:00",
  "source_sha256": "source-digest-output",
  "models": [
    {"model": "gpt-6-luna", "efforts": ["low", "medium", "high", "xhigh", "max"], "fixed_behavior": null}
  ]
}
```

The example is a shape, not current dispatch evidence. Use the complete live
offered list. `digest()` uses sorted-key compact UTF-8 JSON, without a newline.
`source_digest()` binds the policy, mappings and adapter bytes. Freshness is at
most 900 seconds, within the same session, host/surface, build and observed tool
contract. This expires a native observation, not the catalog's informational date.
Unknown builds remain null with an explicit limitation; no build is invented.

The `plan --input PATH` envelope has exactly `request`, `evidence`, `continuation`
(initially null). A request has these exact fields:

```json
{
  "context": {"host": "codex", "surface": "local-macos-desktop", "session_id": "the-current-session", "contract_sha256": "current-native-models-digest", "host_build": null},
  "work_kind": "run", "difficulty": "normal", "tier": null, "raise_reason": null,
  "mode": "force",
  "selection": {"provider": "openai", "family": "gpt-6-luna", "effort": "low", "fixed_behavior": null},
  "author_provider": null, "require_different_provider": false
}
```

For `auto`, set `selection` to null. For review/sign-off, use an explicitly known
canonical author provider (`openai`, `anthropic`, `cursor`), `none` for human work,
or `unknown`. Legacy slug prefixes are not provider identities. A same-provider
request is reported; a required different-provider review refuses unknown or
same-provider choices. Requested provider difference alone is not execution proof.

Only `status: ready` supplies `dispatch`. Pass its model arguments verbatim to the
named native tool, adding the task name and bounded task text. Codex dispatch
explicitly sets `fork_turns: none` so model/effort overrides are valid. Use the
ordinary native agent type: custom/pinned role qualification belongs to INT-010.
Cursor dispatch contains only its offered opaque model name and no effort field.
Future hosts/surfaces return unavailable until their adapter is explicitly added.

## Feedback and bounded fallback

`observe --input PATH` accepts exactly `plan`, `event`, `worker_id` and
`acknowledged`. Use the immediately preceding plan/observation. Events:

- `prelaunch-rejected`: native availability/transport rejection before a worker
  starts. Replan using the returned continuation and current native evidence.
- `not-offered`: re-read the native contract before replan. Changed offers do not
  reset the consumed launch budget.
- `invalid-request`: repair the caller request; no model fallback is authorized.
- `started`: requires the native worker handle. Do not classify a later task or
  server failure as a pre-launch rejection.
- `succeeded`, `failed`, `terminated`: valid only after started. No model retry
  continuation is returned. The caller joins the worker and verifies cleanup.

The limit remains primary, other-provider secondary if offered, a 60-second wait,
then the bounded repeat and unavailable. With one provider, the limit is two
attempts. A wait result contains no dispatch; the caller waits and replans with
fresh evidence. The planner never controls worker lifecycle or creates hooks.

`acknowledged` stays null when the tool reports only a handle. If the host actually
supplies execution identity, use the closed fields `provider`, `family`, `model`,
`effort`, `fixed_behavior`, `origin: native-tool`; absent attributes stay null.
Never populate acknowledgement from the requested values or worker self-report.
Mismatch remains visible. Do not infer different-provider review, quality, cost,
or performance from an accepted request with unknown execution identity.

`refresh --input PATH` takes `context` and `evidence` and prints a proposal only.
It never changes preferences. Adoption requires a separate reviewed source change;
an outage is not evidence for changing a preference.

## Validation and handoff

Run the existing owner gate, `bash .github/scripts/verify-skills.sh`; it discovers
the new `tests/test_native_dispatch.py` alongside the unchanged legacy suite.
The new tests exercise MOD-01 refusals and MOD-02 lifecycle/replan behavior,
including opaque tokens and comparisons across Cursor offered-list subsets.
Native dispatch qualification additionally requires an observed native canary.
Fixtures alone are not a native support claim.

For INT-007B, pin the merged revision and invoke this source path explicitly with
fresh evidence. Do not edit installed policy, automatically adopt proposals, or
add enforcement hooks. Source rollback uses the normal reviewed revert process.
The existing routing instructions remain active until that owning activation gate.
