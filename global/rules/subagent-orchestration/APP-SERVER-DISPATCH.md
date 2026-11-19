# App-server stdio routing — v2 caller contract

Status: source implementation; native surface **UNQUALIFIED**. This opt-in pure
planner does not start processes, install, authenticate, change configuration,
submit model turns or provide AWA registration/protection. The source-owned
profile registry is empty. No production ready plan is possible until a separate
reviewed host/provider discovery profile is added and its evidence is qualified.
Source merge is neither native dispatch qualification nor activation.

## Ownership and continuity

This is the plan-conforming INT-009 adapter under accepted Skills ADRs 0006/0008
and Dev DEC-05. It preserves classification, catalog order, review-provider
preference, explicit overrides and bounded fallback. Routine source delivery
adds no operator code-review gate. Actual security, permission and consequence
requirements still govern effects; this contract supplies none of that consent.

The only surface is `codex / local-macos-app-server-stdio`. Never substitute
`local-macos-desktop`, `cli`, `fixture`, cloud or remote to satisfy another
consumer's schema. A shared consumer needs its own versioned extension before
consuming this new tag. There is no parity claim.

The v1 `native_dispatch.py`, `native-model-bindings.json`, `model-tiers.json`,
`NATIVE-DISPATCH.md`, legacy checker, rule and installer remain unchanged. V2
imports only pure policy/choice helpers, never a v1 ready plan, evidence record,
encoder or observer. Its digest namespace is `app-server-dispatch-source/v2`;
it binds all seven files named in `SOURCE_FILES` plus the semantic policy,
bindings and host registry. Changes expire affected v2 evidence. V1's qualified
source digest/pins are unchanged. No installation or host projection is added.

## Entrypoints

Run from this exact reviewed source directory:

```sh
python3 app_server_dispatch.py source-digest
python3 app_server_dispatch.py plan --input REQUEST.json
python3 app_server_dispatch.py observe --input OBSERVATION.json
```

The CLI loads only source-owned policy, semantic bindings and
`app-server-bindings.json`; it accepts no arbitrary profile/config path.
Library injection exists for synthetic fixtures and is not native qualification.
Exit 2 means unavailable; success status still must be inspected (wait is not
ready). Only `status=ready` permits the exact model fragments to be composed by
the caller. Other states retain fragments only as provenance; never execute them.
A plan is neither entitlement proof nor an execution acknowledgement.

All records are closed: duplicate/unknown keys, wrong types/enums, nonfinite or
floating-point JSON, malformed UTF-8 and excessive input refuse. Errors contain
only bounded reason codes, never supplied input or raw exceptions. Maximum JSON
input is 1 MiB, model rows 1,024, reroutes 64. No prompts, credentials, config
copies, account contents or arbitrary server errors belong in these records.

`Label` is a nonempty string of at most 200 Unicode characters, without controls
or surrogate code points; no case/space/Unicode normalization. `Digest` is 64
lowercase hex characters. UTC times use RFC3339 with `Z` or `+00:00`. Integer
fields reject booleans. Effort names are exactly
`none|minimal|low|medium|high|xhigh|max|ultra`, still subject to the observed row.
Canonical hashes use UTF-8 JSON, sorted keys, compact separators, no ASCII
escaping and no final newline. Evidence rows sort by exact model identifier and
efforts lexicographically; duplicate models/efforts refuse. This never reorders
policy candidates. Observation arrays retain their sequence.

## Profile and discovery boundary

Registry: `{schema:"app-server-bindings/v1", profiles:[]}`. Each future profile
must have exactly these fields (validators in `app_server_contract.profile`):

- `schema="app-server-host-profile/v1"`, `profile_id`, `host_build`;
- `server_binary_sha256`, `protocol_schema_sha256`, `initialize_profile_sha256`;
- `launch_descriptor`, `model_bindings`, `override_bindings`;
- `acknowledgement_methods`, `prelaunch_codes`.

The launch descriptor is closed:
`schema="app-server-provider-profile/v1", profile_id, provider_id,
transport="stdio", source_revision, offer_semantics`.
Only `qualified-native-offers` can plan; `catalog-only` and `unknown` refuse.
It describes a source-reviewed non-secret launch/provider contract, not installed
config, environment values or credentials. Its hash binds the actual permitted
launch and provider behavior. Unknown inheritance or uncontrolled overrides
invalidate it. `model_bindings` must explicitly map every current semantic choice
to a native model string or null. Do not copy desktop mappings on name similarity.
Override bindings have the existing closed provider/family/model/mode/fixed-behavior
shape, with separate app-server provenance. A force authority reference is only a
reference; the caller must possess actual scope-specific authority.

`initialize_profile_sha256` hashes the exact non-secret native initialize params.
Initialize once, then send `initialized`, on the same owned channel/process used
for discovery and submission. Suppressing `turn/started`, `turn/completed` or
`model/rerouted` invalidates qualification. No experimental opt-in is supplied by
this adapter. A process restart, changed handshake, binary, schema or provider
requires new evidence; never reconstruct continuity from a PID or session name.

The context has exactly:
`host, surface, session_id, host_build, server_binary_sha256,
protocol_schema_sha256, server_instance_ref, contract_sha256,
launch_or_provider_profile_sha256, initialize_profile_sha256`.
All required provenance must be known. `server_instance_ref` is controller-local
channel/process custody, not native identity, authorization or AWA generation.
`contract_sha256` hashes the complete canonical normalized offered-model array.

Evidence has exactly:
`schema="native-offers/v2", context, source_sha256, observed_at,
discovery_method="model/list", origin, pagination_complete, include_hidden, models`.
Only `origin="qualified-native-interface"`, `pagination_complete=true` and
`include_hidden=false` are eligible. Maximum age is 900 seconds; future timestamps
refuse. Account/API lists, bundled catalogs, prior sessions and other processes
are not native-offer proof. Even qualified native offers do not prove entitlement.

Each normalized model row is exactly `{model, efforts, fixed_behavior}`: either a
nonempty unique supported effort list with null fixed behavior, or null efforts
with a source-qualified fixed behavior. Never parse slug suffixes or use defaults.
The pure `normalize_pages(pages, context)` helper validates bounded projections
of version-schema-validated model/list responses. A projected page has exactly
`context` (stable context without contract hash), `cursor`, `includeHidden`,
`data`, `nextCursor`. A projected row has exactly `model`, `hidden`,
`supportedReasoningEfforts`; each option has only `reasoningEffort`. Start with
null cursor, follow every exact cursor through explicit null nextCursor, retain
same context and false hidden flags, and refuse repeated/missing pages. Use
`model`, never `id`, descriptions or display names. Discard raw pages after
projection. The initial decoder requires explicit effort options: an empty list
does not establish fixed behavior. Any fixed-mode native decoder needs separate
schema qualification; synthetic fixed-mode encoder tests do not supply it.

## Planning records and selection

Input fields are exactly
`schema="native-dispatch-input/v2", request, evidence, continuation`.
Request has exactly:
`context, operation_ref, work_kind, difficulty, tier, raise_reason, mode,
selection, override_authority_ref, author_provider, require_different_provider`.
The operation reference must bind one concrete controller operation; it is not a
permission token. Work kinds and tiers retain v1 semantics. Normal difficulty
requires null tier/reason; raised requires a genuinely stronger tier and reason.
Non-review work requires null author and false different-provider flag.
Review/sign-off requires a canonical provider or `none`/`unknown` sentinel.

Auto/off require null selection and override reference. Force requires both and
never substitutes another choice. Selection is exactly
`provider, family, effort, fixed_behavior`, with exactly one behavior non-null.
No model is selected by this document. Unavailable economy stays unavailable;
prior capture selections and the expired bootstrap supply no override.

Projection contains only:

| Native request | Exact model fragment |
|---|---|
| thread/start | `{model}` |
| turn/start, effort family | `{model, effort}` |
| turn/start, fixed family | `{model}` |

Both model strings must match the qualified binding. No `reasoning_effort`,
`fork_turns`, storage, permission or fixture fields are emitted. Compose other
fields only under the separately reviewed operation; never overwrite the model
fragment. A fresh, nonpersistent thread path needs exact supported-host proof.
Do not fork/resume or borrow AWA's future zero-prior-turn first-prompt thread.
Before the model turn, verify the fresh thread's native effective provider equals
the launch descriptor and no override intervened. The inspected build returns
`modelProvider` at the **top level of ThreadStartResponse**; this is effective
configuration, not executed-model identity. Recheck source, profile, same-instance
custody and fresh offers immediately before submission.

Result fields are exactly those in `RESULT_KEYS`: schema/status/context; request,
source/evidence/pool hashes; tier/requested/dispatch; continuation/pending/worker;
acknowledged/execution_matches_request/reroutes; used/limit/slot;
warnings/limitations/reason/cleanup. Unavailable malformed inputs return null
executable fields. Ready has no pending/worker/acknowledgement or reroute.
Warnings retain all v1 values, including explicit-override and
review-provider-unverified. Reason/limitation enums are closed in the validator.

Continuation fields are exactly
`schema="native-retry/v2", request_sha256, source_sha256,
stable_context_sha256, pool_sha256, previous_evidence_sha256, used, limit,
next_slot, retry_at, refresh_required`.
Only the offered-contract hash may change on refresh; source, operation, instance,
profiles, request and consumed budget stay bound. Follow primary, different-provider
secondary if available, wait 60 seconds, repeat, then unavailable. One provider
has two total attempts; otherwise four. An offer refresh does not grant attempts.

## Observation and custody

Observation input is exactly
`schema="native-observation-input/v2", prior, event`. Use the immediately preceding
record byte-for-byte. Continuations and prior results are caller-owned state, not
authenticated tokens: the controller must keep the immediately preceding bytes,
never edit counters/times/status or replay an earlier record. Structural coherence
checks reject contradictory state, but this pure module does not prevent a caller
from forging an entirely self-consistent history. No stateful enforcement, signer
or security capability is introduced. Retain the original custody record if an event refuses; a malformed event
must not discard responsibility for a live/pending worker.

Worker is exactly `{server_instance_ref, thread_id, turn_id}`. Pending is exactly
`{server_instance_ref, thread_id, request_id}`. Native IDs come from the same
channel; never infer missing IDs or attach another thread/turn.

| Event shape | Meaning and disposition |
|---|---|
| `{kind:"submitted", pending, effective_provider}` | Record the exact outgoing turn request and the previously checked native effective provider; match the source profile. A thread alone is preparation. |
| `{kind:"started", worker, request_id, acknowledged}` | Accepted turn/start response or correlated turn/started establishes conservative started state. |
| `{kind:"succeeded"\|"failed"\|"terminated", worker, request_id, acknowledged}` | Terminal outcome; if it arrives first, exact correlation establishes execution, never prelaunch fallback. |
| `{kind:"prelaunch-rejected", signal_code}` | Only a source-qualified machine signal proving no turn started. No production signal mapping is delivered. |
| `{kind:"not-offered", signal_code:null}` | Only before submission; requires fresh discovery and preserves budget. |
| `{kind:"invalid-request"}` | Only pre-submission caller composition repair. Returns non-executable unavailable plus same-budget/same-slot continuation. Replanning cannot change the bound routing request. After submission, classify conservatively as acceptance unknown. |
| `{kind:"acceptance-unknown"}` | Ambiguous submission, disconnect, timeout or unresolved running state. No retry continuation. |
| `{kind:"rerouted", reroute}` | Exact-worker reroute; preserve mismatch, withhold qualification and stop safely under the operation policy. |
| `{kind:"cleanup-confirmed"\|"cleanup-unknown"}` | Caller-observed cleanup after submitted custody only; pre-submission rejections have nothing to clean. Cleanup cannot turn failure/uncertainty into success. |

No auth/rate-limit/transport error automatically means model unavailable. A later
failure after started is task/lifecycle failure. A submitted proven-no-start
rejection withholds continuation until cleanup is confirmed. Unknown cleanup
withholds it. After ambiguous acceptance or started execution, cleanup never
creates a retry. Invalid native parameters after submission do not authorize a
model switch. If an otherwise eligible routing retry could replay an AWA prompt
callback, the stricter AWA stop/count/freshness rules prevail: withhold and clean;
prepare any new capture as a separate operation.

Duplicate identical events are idempotent; contradictory terminal/ID/ack events
refuse. An early reroute must be buffered boundedly by the controller until the
worker is exactly correlated; replay before closing qualification. Missing,
dropped or uncorrelated required notifications prevent qualification.

Acknowledgement is null unless the version-qualified native contract supplies
actual execution identity. A non-null ack has exactly
`provider, family, model, effort, fixed_behavior, origin="native-execution",
evidence_method`, with unknown attributes null. The method must be source-qualified.
Request echoes, configuration, handles and self-reports do not qualify. Partial
acks leave matching unknown. Conflicts refuse; mismatches remain false.
Do not claim different-provider review, cost or performance from an unacknowledged
request. No production acknowledgement method is delivered here.

Reroute has exactly `worker, from_model, to_model, reason_class="unknown",
reason_code:null`. Raw server reason text is discarded; this initial implementation
adopts no machine reason mapping. A switch away stays a mismatch even if it later
switches back. Unknown target bindings add a limitation; no effort is inferred.
A reroute is not a new dispatch permission, and its absence does not prove identity.

Cleanup means the caller has joined the terminal model action, closed owned input
handles and server process, removed or explicitly retained exact owned artifacts,
and preserved shared host trust/settings and unrelated work. The pure observer
records this outcome; it never performs or authenticates cleanup.

## Qualification and canary

Focused MOD-01/02 tests use synthetic profiles/tokens only. The shipped empty
registry deliberately blocks native dispatch. Read-only exact-binary schema
inventory establishes supported field shapes only; no native offer/provider,
execution, failure or cleanup claim follows. See
[the separate canary runbook](../../../docs/runbooks/app-server-stdio-routing-canary.md)
and [source evidence](../../../docs/evidence/app-server-stdio/README.md).

A future profile may be source-adopted after its non-secret launch/handshake,
provider provenance, exact model bindings and schema/build contract are reviewed.
Then a separate ready-plan-bounded routing canary observes actual dispatch,
terminality, identity limits and cleanup. Only its supported paths qualify;
unobserved failures stay fixture-only. Host/source/profile drift expires affected
evidence. Activation is separate. Custom-role and dependent lifecycle gates stay
unchanged; no roles are installed or exposed by this adapter.

Protocol reference: [official app-server documentation](https://learn.chatgpt.com/docs/app-server).
Catalog caveat: [official provider documentation](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
