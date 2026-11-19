# Ecosystem search

A thin skill for bounded capability lookup and task-context pointers. All parsing,
ranking, identity, provenance and cache behavior belongs to the single
`ecosystem-index` tool. This skill owns no second runtime, index or registry.

## Source-backed dependency

Resolve the installed skill's physical directory, verify its declared
`KleinPerkins/skills` source root, then resolve
`global/tools/ecosystem-index/ecosystem_index.py` within that same tree:

```text
bash <physical-skill-directory>/install.sh --doctor
```

The read-only check verifies physical layout, local Git remote identity and tracked
skill/tool payloads; it returns the absolute tool path when ready. A copied,
missing or mismatched layout returns unavailable (exit 3). It never invokes the
tool, searches recursively, installs a dependency or falls back to PATH/a primary
checkout. Local Git commands used for this source check are separate from the
index's process-free query runtime. This is source identity, not access authority.

Use Python 3 with that verified path and an explicit cache path. `search` reads
the query from stdin (maximum 4096 UTF-8 bytes); `describe` and `context` use a typed
entity ID. The tool README defines the closed JSON records, limits and result
statuses. Display provenance, conflict and freshness information. Do not execute
the returned pointers or persist query text.

Search/describe/context need only the standard library and a valid JSON snapshot.
Explicit refresh may need the tool's declared PyYAML dependency for eligible YAML
metadata; missing support is reported rather than installed. Freshness is advisory;
all authority-sensitive actions still reread the current permitted owner sources.

## Installation and scope

This flavor-1 skill is exposed to Cursor, Claude and Codex with `post_mgmt: none`.
The existing generic capability installer owns managed skill links. `install.sh`
only checks source prerequisites, including when invoked without arguments; it
does not change an installed client. No PATH command, virtualenv or dependency
download is provided. Recipient packaging must qualify a complete runtime layout
under its own governance before downstream activation.

An absent dependency/cache produces an explicit unavailable result. When a source
is already known, direct permitted reading remains possible without the index.
Refresh requires explicit scope and storage authority. Source publication does
not authorize live scanning, automatic maintenance, installation or legacy cleanup.
