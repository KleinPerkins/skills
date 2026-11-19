# Codex work assessment and dispatch

This source-owned interface implements ADR0011. It does not launch, authorize,
install, intercept tools, or persist records. Dev owns instruction activation.
Existing interfaces remain historical. No compatibility guarantee is added.

## Assessment contract

`assess --input PATH` consumes `codex-work-assessment/v1`: objective, deliverable,
scope, work_class (`inspect`, `operate`, `build`, `design`, `assure`), ratings,
effects, reversibility, verification, unknowns, review. Each rating has an integer
level 0..3 (or null) and concise factual evidence; dimensions are `ambiguity`,
`reasoning`, `coupling`. No private chain of thought is requested.

| Level | Ambiguity | Reasoning | Coupling |
|---|---|---|---|
| 0 | Exact procedure and supplied inputs | Mechanical extraction/execution | Independent supplied inputs |
| 1 | Clear goal and established choices | Local judgment using established patterns | One component or explicit local dependency |
| 2 | Diagnosis among known hypotheses | Multi-step logic and edge cases | Multiple interacting known contracts |
| 3 | Conflicting evidence or unresolved architectural alternatives | Novel synthesis and consequential tradeoffs | Uncertain interfaces across systems |

Use the maximum dimension, with D1 floor for source edits/build and D2 floor for
security judgments, independent review, assurance and sign-off. Length, urgency,
and consequences alone do not increase difficulty. A required unknown rating or
unknown that could change the route returns needs-assessment; gather evidence.
Split mixed work into bounded tasks where useful; never hide its hardest part.

Effects are booleans: source_edits, security_judgment, sign_off, consequential,
independent_review. Reversibility is read-only, reversible, or irreversible.
Verification has method automated/inspection/mixed and nonempty checks, each with
unique id and criterion. Unknowns is a list of unresolved routing questions.
Review has nullable author_model and requirement none/separate-context/
different-model/different-provider. Respect stricter external review gates.
Consequential/irreversible work requires applicable authorization and independent
review; computed settings never supply that authority.

## Model first, effort second

D0 uses Luna/low, D1 Sol 6.1/medium, D2 Sol 6.1/high, D3 Astra/high. The policy file
contains exact tokens, separately from effort. It is an initial policy, not a
measured cost optimum. Max/ultra are not automatic defaults. Explicit overrides
must name an approved pair no weaker than the assessment and a user-authorized
reason. They never silently fall back or auto-escalate.

## Native caller

Run `python3 codex_dispatch.py source-digest` from a byte-verified pinned source.
`plan --input PATH` takes exactly assessment, target (worker/parent), context,
evidence, override (null or model/effort/reason), continuation (initially null).

Context: host codex, surface local-macos-desktop, session_id, host_build (nullable).
Evidence: schema codex-native-offers/v1, matching context, tool, origin native-tool,
observed_at UTC ISO timestamp, source_sha256, contract, models. The adapter accepts
only the two exact native profiles below; it never aliases tool names or translates
one profile's arguments into another. Each contract is a closed JSON object:

| Tool | Exact contract fields and values | Decision schema | Fixed dispatch arguments |
|---|---|---|---|
| `multi_agent_v1.spawn_agent` | `model:"string"`, `reasoning_effort:"string"`, `fork_context:"boolean"`, `ordinary_agent:true` | `codex-work-decision/v1` | `fork_context:false`, `agent_type:"default"` |
| `collaboration.spawn_agent` | `model:"string"`, `reasoning_effort:"string"`, `fork_turns:"string"`, `fork_turns_fresh_value:"none"`, `task_name:"string"`, `message:"string"`, `ordinary_agent:true` | `codex-work-decision/v2` with `native_tool:"collaboration.spawn_agent"` | `fork_turns:"none"` |

`fork_turns_fresh_value` records the caller's observation of the supported fresh
context value; it is evidence metadata, never a native tool argument. Models is
the complete live tool list of model/efforts objects. Bind evidence to the current
native schema and ordinary unpinned role; do not copy an old observation. Unknown
build is a visible limitation; activation additionally needs a known host build.
An evidence observation expires after 900 seconds. API lists are not native proof.

Only ready has dispatch. Pass its arguments unchanged to its named tool. They
always contain explicit model and reasoning_effort plus the fixed arguments above.
For the legacy profile, add the bounded task message as before. For the current
profile, `dispatch.caller_fields` is exactly `["task_name", "message"]`: add a
valid bounded task name and message, without replacing the planned arguments.
Never pass caller_fields or other record metadata as native arguments. The current
profile emits no agent_type or fork_context; fork_turns:none supplies the fresh
context required for explicit model/effort overrides. Custom/pinned roles are
unqualified. Native permissions still govern delegation; a ready plan grants no
permission to spawn. Parent target returns advice, no dispatch; never claim to
switch the current model. Reassess on material scope changes. Generic assessment
and unavailable CLI results retain v1; only a validated current-profile plan,
lifecycle record or refresh proposal uses v2. A consumer must support the exact
decision schema and profile before consuming it.

Review uses a fresh worker and criteria; prefer another equally or more capable
family if offered. Same-provider independence means separate context only.
A required different-provider review is unavailable on this OpenAI-only route.

## Lifecycle

`observe --input PATH` takes record, event, worker_id, acknowledged, checks,
cleanup_verified, diagnosis. Unused optional values are null (cleanup false).
started requires a worker handle; acknowledged remains null unless the native
host supplies model/effort/origin:native-tool. Never copy requested settings into
acknowledgement or trust worker self-report. Partial or absent identity is unknown.

Prelaunch rejection permits one same-pair retry after 60 seconds. not-offered also
requires refreshed evidence. Pass the sealed retryable record as continuation;
waiting has no dispatch. Changed offers cannot reset the budget. Invalid requests
are repaired, not relabeled as outages. Started failures never use this path.
Continuations are bound to the original native profile as well as context and
source. A new observation cannot switch profiles to retry or escalate. Legacy v1
records retain their original shape; v2 lifecycle records retain native_tool.
Records from another source digest remain invalid, including earlier source pins.

completed supplies booleans for exactly the predefined check ids. quality-failed
can follow completed only with failed checks, a substantive diagnosis and verified
cleanup. Infrastructure, permissions and ambiguous acceptance are not quality
failures. One escalation is permitted: D0 -> Sol/medium, D1 -> Sol/high,
D2 -> Astra/high, D3 -> Astra/xhigh, or the stronger reassessed requirement.
Keep objective, deliverable, scope and acceptance unchanged. A second failure
exhausts quality escalation. An explicit override requires a new operator decision.

Join each worker and verify its task-owned resources are cleaned up before using
its output or escalating. Runtime failures/termination remain distinct records.
Record hashes prevent accidental mixing, not same-user tampering. These are
caller-observed records, never security attestations or execution authorization.

`refresh` takes context/evidence and prints a proposal without adopting new models.
Keep task evidence private and local; commit only approved synthetic qualification
summaries. No raw work prompts, secrets, customer data or transcripts in the repo.

## Delivery

Run `python3 -m unittest discover -s global/rules/subagent-orchestration/tests`
and `bash .github/scripts/verify-skills.sh`. Offline tests are not native proof.
Qualify two approved fixtures per band against preferred/escalation routes (at
most 16 started workers), then activate the merged pin through dev's governed
preview/apply/verify/rollback interface. Each exact native profile needs its own
qualification; a matching desktop build does not qualify a different tool ABI.
Legacy accepted evidence is not current-profile proof. This source change supplies
neither native qualification nor Dev activation. Preserve all prior accepted
evidence, ADR0011, the frozen qualification plan and the accepted model policy.
