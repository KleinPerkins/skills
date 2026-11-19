# INT-010 native role contract assessment

Status: preparation evidence only, observed 2026-10-31. INT-010 remains unsupported
under the observed native restriction contract; INT-012 is not dependency-ready.
This is an evidence assessment, not an accepted renderer design, permanent
exception, implementation completion, or permission to expose the roles.

## Authority and exact subject

The accepted dev ADR 0012, PRD REQ-INT-007, SPEC section 5 / DEC-05, and PLAN
INT-010/012 / AGT-01/02 remain authoritative at
`14fa5f95fe86178f32e966cb747ab9c884f4b92b`. Their bytes and the plan governance
sidecar were compared with the current coordinator checkout and are unchanged.
Standing execution authorization was verified from the direct human turn in the
coordinator chat; it does not change these acceptance conditions.

The source observation is Skills `8fdb02b48ea5c21691b53cb35915a3f4fe75c8ee`.
[assessment.json](assessment.json) binds the exact three role payloads and metadata
plus the existing fallback/routing references by file digest. These are assessment
inputs, not generated native role bytes. No renderer exists in this delivery.
[observations.json](observations.json) uses the accepted closed qualification
schema and deliberately contains no passing native role observation.

## What was observed

The supported host-version tool reported desktop version `26.1027.30824`, build
`22943`; no update was applied. The current native spawn schema offers built-in
and GSD roles, but none of `swarm-probe`, `swarm-reviewer`, or `swarm-verifier`.
It has no per-launch tool allowlist or independent permission argument. The
twelve exact project/user `.md` and `.toml` paths for these roles are absent.
No custom role was installed or launched and no denial probe was attempted.

The current [official subagent contract](https://learn.chatgpt.com/docs/agent-configuration/subagents)
documents standalone TOML with identity and instruction fields, model overrides,
and selected feature/skill disables. Permissions and MCP configuration remain
inherited from the parent. A role's instructions to avoid writes do not establish
a separate read-only sandbox. These documented controls do not establish the
complete read/search-only tool policy required here.

| Required property | Current evidence | Disposition |
|---|---|---|
| Shared charter, inert invalid-input response, exact JSON protocol | Existing source payloads and contract tests | Preserve unchanged; native behavior unobserved |
| Read/search only; no commands, network, mutation, or delegation | Source allows `Read, Glob, Grep`; the observed host contract lacks an equivalent complete per-role restriction | AGT-01 unsupported; feature disables alone are insufficient proof |
| Explicit routed model/effort without a role-level fixed default | Existing role source has no model default; native declarations can override launch selection | Future projection must preserve resolver authority; no new override adopted |
| Native discovery and invocation | Required role names absent from the live spawn enum | Unobserved; file parsing/presence cannot pass AGT-01 |
| Success, failure, timeout, parent interruption, joined workers, cleanup | Existing fixture supervision tests; no qualified custom-role launch | AGT-02 remains unobserved for these roles |

## Narrow owner proposal and re-entry conditions

Preserve the existing charters and native exclusions. Prepare a renderer only
after a supported host mechanism can enforce their complete tool restriction.
That mechanism must permit the necessary read/search operations while excluding
shell/test execution, direct edits, network/service mutations, and delegation,
including access through a general tool-execution wrapper. An advisory prompt,
file-format conversion, or broader parent permission setting is insufficient by
itself. This proposal does not create a new enforcement framework or weaken
AGT-01.

Once that prerequisite exists, the owner decision can be bounded to:

1. A deterministic projection from the existing charter/protocol source into
   native TOML, with explicit field mapping and no fixed model/effort override.
2. Separate validation for native projections, leaving the current Markdown
   validator and Cursor/Claude behavior intact. Unknown or unenforceable
   restrictions must refuse projection/exposure.
3. Fixture tests for parsing, exact charter/protocol preservation, malformed
   inputs, deterministic generation, opt-outs, conflicts, idempotence, and rollback.
4. A bounded native canary after the owner contract is accepted: observe actual
   role loading, allowed read/search positive controls and prohibited-operation
   negative controls, model-setting precedence, and the declared output protocol.
5. AGT-02 lifecycle cases on that qualified role path, including failure,
   timeout, interrupted parent, multiple answer-critical workers, and verified
   cleanup. Only then revisit exposure and dependent INT-012 integration.

Until then, use the existing documented `parent-led-fallback` with
`isolation = degraded`. Preserve its candidate binding, probe-blind coverage,
evidence lineage, budgets, and shipping-clearance rules. This is not native role
isolation and does not satisfy the open qualification requirement.

The practical next dependency is a supported native restriction contract, owned
by the host provider, followed by the Skills-owned renderer decision and proof.
A permanent relaxation of the required role behavior would instead require a
governed acceptance amendment; none is proposed or inferred here. Other
dependency-ready retrofit work can continue in its owning chat.

## Validation and boundaries

The 122 existing swarm unit/contract/authority/fault tests and the full repository
owner gate passed. A separate technical review found no blocking findings. Exact
outcomes and limitations are recorded in `assessment.json`; those checks validate
the unchanged source and this evidence delivery, not native role execution. No
new tests were added solely to restate this assessment.

No role metadata, installer, routing preference, installed configuration, frozen
workload, accepted semantic record, or protected automation was changed. No
secrets, installed configuration copies, raw prompts/transcripts, or work-data
bodies are retained. No native role installation, INT-008 migration, INT-012
completion, or broader rollout follows from merging this evidence.
