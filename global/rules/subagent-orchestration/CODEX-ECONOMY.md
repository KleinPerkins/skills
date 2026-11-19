# Codex-native economy policy

Status: accepted source policy; not installed, activated or native-qualified.
This document and its sibling data files do not authorize a launch. Source
delivery, bounded native qualification and instruction activation remain separate
events. The owner accepted ADR0009 and authorized source implementation on
2026-10-31 after independent review of the decision package.

## Policy and workload

The accepted choice is `gpt-6-luna` with `reasoning_effort: low` for normal
`find`/`run` work
whose hardest requirement is mechanical: bounded file/metadata lookup, extraction
from supplied synthetic or approved inputs, status/log summarization, and running
already-specified checks without diagnosing failures or making repair decisions.
Initial qualification excludes source edits, security decisions, ambiguous
investigation, design, review, sign-off and authority-sensitive execution. Keep
the existing classification when a task needs more judgment; unavailable economy
is never a reason to raise its difficulty or perform rejected-tier work directly.

The pair adds a real OpenAI semantic choice after the two existing economy
candidates. Their Codex bindings stay null. With today's native offers, Luna/low
is the sole eligible Codex economy choice and the existing `fallback` warning is
reported. There is no alternate-model or alternate-effort fallback. A proven
prelaunch rejection allows one same-pair retry after the existing 60-second wait;
then routing is unavailable. Invalid requests, uncertain acceptance and started
task failures must not be relabeled as model-availability rejection.

## Existing interface, explicit data selection

Use the unchanged `native_dispatch.py` interface. Outside a separately authorized
bounded native qualification operation, only an accepted and activated Codex
economy caller selects both of these source-owned files. A pre-activation
qualification may select the pair only within its exact reviewed operation scope:

```text
python3 native_dispatch.py source-digest --policy codex-model-tiers.json --bindings codex-native-model-bindings.json
python3 native_dispatch.py plan --policy codex-model-tiers.json --bindings codex-native-model-bindings.json --input REQUEST.json
python3 native_dispatch.py observe --policy codex-model-tiers.json --bindings codex-native-model-bindings.json --input OBSERVATION.json
python3 native_dispatch.py refresh --policy codex-model-tiers.json --bindings codex-native-model-bindings.json --input EVIDENCE.json
```

Run in the verified owner source directory; these are interface templates, not
current execution authorization. Select the pair only for `host:codex`,
`surface:local-macos-desktop`, `mode:auto`, normal `find` or `run`, after the
workload check above. Other work, explicit force/off modes, Cursor and Claude
continue on their existing paths. Never use only one of the two new files.
Retain the selected pair for the complete plan/observe/replan lineage.

No request, evidence, observation or native dispatch field changes. The result
still targets `collaboration.spawn_agent` with `fork_turns:none`. The existing
digest binds resolver bytes and the selected data values; this pair produces a
different digest. Base-policy evidence cannot authorize this pair. After source
delivery pin the resulting pair digest and record fresh complete native tool
offers before any separately permitted operation. The inherited schema's
`verified_against` field is informational, not current offers or qualification.

Tool-specific offer evidence is not a successful-launch or execution-identity
claim. Preserve `acknowledged:null` when the tool returns only a worker handle.
Join workers, observe health/interruption, and verify task-owned resource cleanup
under the existing orchestration contract. This data change adds no permission,
role restriction, cancellation mechanism or security isolation.

## Source views and regression boundary

`model-tiers.json` and `native-model-bindings.json` remain the original canonical
shared inputs. The two Codex files are deterministic constrained views: copy
those inputs; change only the informational marker, append one economy identity,
and add its explicit semantic binding. All existing choices, all other tier lists,
all override mappings and all existing native bindings must stay identical.
The added choice has `cursor:null`; no unrelated provider family is relabeled.
The parity tests deliberately fail if the shared inputs later change without
reconciling these views. ADR0009 also permits one content-specific acceptance
test pinning this decision's exact identity and semantic tuple; a different choice
needs a successor decision. Legacy catalog tests remain content-agnostic. Future edits require source review, not live refresh.

Keep the legacy checker, schemas, resolver, base caller contract, rule, installer,
`meta.yml` assets and app-server files unchanged. The new pair is not an installer
asset and is not read by default. No downstream synchronization is triggered.

## Qualification and rollback

Offline validation proves data validity, selected-request behavior, refusal,
retry/observation transitions and regression equivalence. It cannot establish
model output quality, latency, task cost, native acceptance, true execution
identity, cancellation or isolation. Bounded native operations require their own
preview and authorization; no launch follows solely from this source policy.

Rollback of a later instruction activation selects the previous qualified
base-policy invocation and pin for future work. Finish or safely interrupt and
join already-started workers before changing their lineage; retain their evidence.
Do not rewrite a running request or imply an interrupted worker was reaped without
observation. Restore only matching owned instruction postimages, preserving later
user changes. Source withdrawal uses a normal successor/revert; accepted ADR
bytes and frozen evidence stay intact.
