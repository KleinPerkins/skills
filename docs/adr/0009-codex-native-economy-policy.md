# ADR 0009: Add an opt-in Codex economy data pair to the native resolver
Status: accepted — 2026-10-31
Extends: ADR-0006/0008 with an opt-in Codex economy view.
Supersedes: ADR-0006 decision 4, as retained by ADR-0008, only for this profile's model-specific decision documentation and exact-choice acceptance test. Shared catalog/test behavior and all other ADR-0006/0008 decisions stand.

Owners: Laurence Duggan (`KleinPerkins`), Skills source owner. Dev owns any later
host-instruction activation; AWA and downstream owners retain their boundaries.

Decision owner: Laurence Duggan, accepted 2026-10-31 after independent technical
review of proposal SHA-256
`8efc3314524f22f71d6bae2aac73086179a791e4b2380fb2a074e2088a652ec9`
and patch SHA-256
`4c4c983f5fe46d4ef1a625c4ff07416ed917b4a33d5f5799990b092aaea756ba`.
The same instruction authorized source implementation; later native operations
and instruction activation remain separate.

## Decision

Accept `gpt-6-luna` at explicit `low` effort as a new, real OpenAI semantic choice
for the bounded mechanical `find`/`run` workload in
[`CODEX-ECONOMY.md`](../../global/rules/subagent-orchestration/CODEX-ECONOMY.md). Add it only
to a source-owned opt-in Codex data pair, after the existing ordered economy
candidates. Preserve their null Codex bindings and their original meanings.
Preserve the base catalog, resolver implementation, Cursor/Claude behavior,
classification, role exclusions, force authority and bounded lifecycle policy.

Use the resolver's existing `--policy` and `--bindings` interface. Do not alter
the qualified default source digest or install a new default. The pair has its
own data-bound digest and needs fresh evidence and bounded native qualification
before a separately authorized instruction activation. The only eligible native
choice today is Luna/low; no alternate model or effort is silently substituted.
Report the existing fallback warning. Preserve the one-provider retry sequence:
attempt, 60-second wait after proven prelaunch rejection, one retry, unavailable.

This is a new owner policy decision, not reuse of the expired bootstrap mapping.
The owner has accepted this decision and authorized source-only implementation.
Model launch, instruction activation, installed settings changes, app-server
qualification, AWA capture and broader rollout are not authorized by this decision
or by the source-delivery instruction.

## Why

Current native worker offers include Luna and explicit low effort. Official
guidance supports Luna for narrow repeatable work and low effort for simple
extraction. General subagent guidance starts Luna at high; this narrower workload
supports selecting low, subject to native quality screening rather than assuming
it is equally reliable. Latency, cost, quality and successful access are unmeasured.
Primary evidence retrieved on **2026-10-31**:

- [OpenAI model-selection guide](https://developers.openai.com/api/docs/guides/model-selection):
  Luna/low is a starting point for simple extraction and tightly bounded tasks.
- [GPT-6 Luna specification](https://developers.openai.com/api/docs/models/gpt-6-luna):
  focused-work positioning and explicit effort controls; API prices are not
  measured native-worker task costs.
- [Codex subagent guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents):
  Luna fits narrow repeatable tasks; its general starting recommendation is high,
  while low fits straightforward tasks. That tension motivates the narrow screen.

The direct `collaboration.spawn_agent` contract was observed on 2026-10-31 in
Codex local macOS session `01a18150-3a2b-7ff3-86ab-4bd9ce7bb9a2`. It offered
`gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, each with
low/medium/high/xhigh/max and all except Luna additionally ultra. Canonical models
array SHA-256: `fd36fd09e88455ab3ca0ed2a2cf4060067b212b07a93fb7b1af3c90b6921875a`.
Host build and executed identity are unknown. This dated observation is not
reusable launch evidence, entitlement or proof of successful access. API/account,
existing-chat and app-server catalogs do not replace direct-worker evidence.

Source baseline: Skills main `f2301ce13d50e471ff1e8ae51fb5a41bf47eaf0a`
(PR240's qualified v1 payload retained through PR246), v1 digest
`2e355af2666b52a56d7dd8d19c3c925dcede36b666b9c0a15426b8f9bb546ed2`;
accepted dev ADR0012/SPEC/PLAN at `8cf1d09747d6f19567907ef2be0124e5d1b738d2`.
Fresh native evidence and source qualification remain required at any later launch.

The default economy candidates have null Codex bindings. Falsely binding Composer
or Claude to an OpenAI token would change their semantic identities. Editing the
shared catalog could change Cursor/Claude behavior. The existing file-selection
interface permits a smaller data-only change than a new resolver or transport.

## Consequences and gates

- Add two constrained data views, a caller supplement and focused parity/behavior
  tests. Existing files named in the qualified resolver digest remain untouched.
- Duplicated view data can drift; tests must enforce the exact allowed delta from
  shared sources. No runtime generation or automatic catalog adoption is added.
- Narrow exception to ADR-0006 decision 4 (retained by ADR-0008): this profile's
  documentation and one acceptance test pin `codex-economy-luna-low` and the full
  `openai / gpt-6-luna / low / fixed_behavior:null / cursor:null / codex:gpt-6-luna`
  tuple. This prevents a coordinated data/offer substitution from silently changing
  the accepted owner decision. Changing that identity or tuple needs a successor
  decision and updated acceptance test. Legacy catalog tests, shared refresh
  behavior and the remaining compatibility tests stay content-agnostic.
- Native offers remain tool-, session-, host-, effort- and freshness-bound.
  Handles are not execution acknowledgement. Model choice adds no safety powers.
- Preserve INT-009 MOD-01/02 and INT-012/AGT-02; frozen dev SPEC/PLAN/workloads are
  not edited. Any future weakening of an acceptance requirement needs a named
  dev successor amendment. No such weakening is proposed here.
- Skills uses its existing legacy documentation convention: this accepted source
  document and mutable index record acceptance through the governed source PR;
  `doc-warden.sh legacy-v1 check` validates structure. No v2 enrollment or
  consent-envelope operation is introduced. These accepted ADR bytes are frozen;
  retain ADR-0006/0008 bytes and use a successor for later semantic changes.
- Installation and activation effects remain zero until their separate phases.
  No AWA ADR0026 work, INT008 copy, mcp-builder or chaos-scheduler change; the
  ecosystem-orchestrator remains the sole downstream distribution writer.

## Rollback

Restore the prior qualified caller selection and pin for future tasks through
the owning activation rollback. Preserve active worker custody and user edits.
Withdraw source via a reviewed revert/successor, never rewriting accepted history.
