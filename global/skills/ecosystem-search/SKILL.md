---
name: ecosystem-search
description: Find an eligible local capability or prepare bounded task-context pointers from an existing ecosystem index. Return candidates with provenance, conflicts and freshness; refresh only with explicit source-read and metadata-storage authority.
---

# Ecosystem search

Use for capability lookup or source-owner, instruction, decision and check pointers.
The index is an observation cache. It cannot grant access, enrollment or execution.

## Locate the declared tool

Resolve this installed skill's physical directory and the same Skills source root.
Verify that root's Git identity, then resolve
`global/tools/ecosystem-index/ecosystem_index.py` within that tree. The read-only
source check in [README](README.md) demonstrates this contract.

If the skill was copied or the tool/root identity is missing or mismatched, report
the dependency unavailable. Do not search a home directory, use a PATH fallback,
copy a runtime, download dependencies or run bootstrap. A known permitted source
can still be read directly under its owner's rules.

## Query an existing snapshot

Use Python 3 with the verified absolute tool path and an explicit cache path:

```text
python3 -B <tool> search --cache <cache> [--limit 1..20]
python3 -B <tool> describe --cache <cache> --id <entity-id>
python3 -B <tool> context --cache <cache> --id <entity-id>
```

Supply search text on stdin (at most 4096 UTF-8 bytes), not in command arguments,
files, logs or persistent shell history. Default search limit is five. Do not echo
the query in diagnostics. Context returns at most twenty pointers and its coverage.

Return the bounded candidates with contribution reasons, identity, provenance,
conflicts and exact freshness. Keep logical repository, clone and worktree locations
distinct. Do not turn inferred relevance into a declared dependency or permission.
Report ambiguity, no result, stale/partial coverage and unavailable cache explicitly.
Inspect `status`, `coverage`, `reasons` and `freshness` separately. Search returns
`candidates[].entity` (observations/conflicts) and `contributions`; describe returns
`entity` and distinct `locations`. Context returns `source_owner`, `pointers` with
provenance, `relationships` and `truncated`. Exit zero includes valid `none` and
`partial` results; it does not establish complete coverage.
Invalid input is exit two; unavailable/refused source or cache is exit three.

Queries do not refresh, execute a source command, fetch a pointer or write state.
Before an action, independently verify the current permitted owner sources,
workspace, permissions and writer rules. A fresh snapshot is not current authority.

## Explicit refresh

Refresh only after explicit authority covers the configured roots, source adapters,
storage-eligible fields, exclusions and cache target:

```text
python3 -B <tool> refresh --config <config> --cache <cache>
```

There is no default home scan, implicit source discovery or background maintenance.
Unknown provenance and excluded roots remain unopened. A failed source can leave
prior observations stale/unverified; never interpret incomplete coverage as deletion.
Missing YAML support is explicit partial/unavailable coverage and never triggers pip.
Preserve curated configuration separately from generated cache.

Source existence, installation and native qualification are separate facts. This
skill does not install or activate capabilities, sync downstream copies, execute
indexed checks, change permissions, or migrate old private routing state.
