# Ecosystem Index

A local observation cache for finding capabilities and preparing source context. It reads only an explicit, externally authorized inventory. Scores explain retrieval signals; they confer no permission, enrollment, approval or installation status.

## Source and prerequisites

This flavor-1 snapshot tool ships its Python source here. Its lifecycle script performs read-only source/prerequisite checks, including on `--install` and `--uninstall`; it creates no links or runtime state. The generic package installer validates `tool.yml` and supplies no command link. No installer provisions Python packages, virtualenvs, services or PATH entries.

Use Python 3.10 or later. JSON reads require only the standard library. YAML refresh adapters require the separately provisioned `PyYAML==6.0.3` declared in `requirements.txt`. A missing parser produces partial refresh coverage, a bounded `parser_unavailable` reason and stale prior observations. It never triggers installation.

The source-backed consumer dependency is explicit: resolve the physical installed skill directory, verify its declared Skills source root and Git identity, then resolve `global/tools/ecosystem-index/ecosystem_index.py` within **that same source tree**. A copied skill, missing tool or mismatched source is unavailable. Do not search for another checkout, copy a runtime or use a PATH fallback. Recipient packaging and retained installation need their own qualification. Source tests do not qualify installed clients.

## CLI and library

```text
python3 -B <verified-skills-root>/global/tools/ecosystem-index/ecosystem_index.py refresh --config PATH --cache PATH
python3 -B <verified-skills-root>/global/tools/ecosystem-index/ecosystem_index.py search --cache PATH [--limit 1..20]
python3 -B <verified-skills-root>/global/tools/ecosystem-index/ecosystem_index.py describe --cache PATH --id ID
python3 -B <verified-skills-root>/global/tools/ecosystem-index/ecosystem_index.py context --cache PATH --id ID
```

Search reads at most 4096 UTF-8 bytes from stdin; default limit is five. There are no compatibility commands or abbreviated options. Queries read one validated JSON snapshot, perform no source reads, writes or subprocess execution, and never refresh implicitly. Query text is neither echoed nor stored. `lib` exports `refresh`, `search`, `describe`, `context` and `Refusal`; library records and CLI records use the same validators. The CLI sets the bytecode flag before loading its library. Library callers must start Python with `-B` or set `PYTHONDONTWRITEBYTECODE=1` **before import** for write-free loading; a flag set inside a package cannot prevent that package import from creating its own bytecode cache.

CLI exit codes: 0 for valid results, including `none` and `partial`; 2 for invalid input; 3 for unavailable/refused state, including `busy`. Errors contain bounded reason codes rather than input values, paths or backend exceptions. All machine records use deterministic UTF-8 JSON and closed versioned schemas under `schemas/`. Semantic validation also enforces duplicate IDs, field eligibility, safe relative pointers, type/ID consistency and configured lower bounds; JSON Schema is not the entire policy.

Search returns `matches`, `ambiguous` (equal highest scores) or `none`, with candidates containing the entity, integer score and contributions by `exact_id`, `title`, `aliases`, `description` and `identity`. It uses conservative token normalization and additive overlap; exact typed IDs win. Identical titles in different repositories remain ambiguous. This is deterministic retrieval, with no probability or authority claim. Corpus results are synthetic only.

`describe` returns the exact entity or null and preserves separate clone/worktree locations beneath an identified repository. `context` returns at most 20 owner/instruction/decision/check pointers plus at most 100 declared relationships, supporting provenance, source owner, coverage and truncation. Clone/worktree context follows at most two parent hops to the logical repository, using visited IDs to terminate cycles. Missing parents, cycles, overlong chains or conflicts at any hop produce `ambiguous` with a null `source_owner`; supporting pointers and relationships are interleaved across the known owners within the same bounds, with explicit truncation. It never fetches or executes a pointer. Callers must read permitted authority sources live before relying on them.

Every query reports snapshot coverage and freshness: observation timestamp, exact age in seconds, a 24-hour advisory threshold and a stale advisory boolean. Observation states and timestamps remain visible on each fact. A snapshot or observation timestamp later than the query clock refuses the query as `unavailable` (exit 3), rather than reporting a false zero age. Freshness is unrelated to approval validity.

## Explicit inventory and eligibility

Config is `ecosystem-index/config/v1` JSON. No roots or exclusions are built in. The caller must supply complete policy, including identity exclusions established outside this miner. `scope: unknown` or null identity keeps a root unopened. Normalized provider, remote and local identity representations are all checked against identity exclusions **before** root or metadata access, so a provider declaration cannot hide an excluded remote alias. Lexical exclusions also cover explicit Git scopes and source paths. These configured identities provide pre-access exclusions. If the separately permitted fixed Git metadata probe reveals a contradictory excluded remote, no source mining occurs and all current/prior inputs for that root are dropped with partial/excluded coverage. A nonexcluded identity contradiction is retained explicitly as a conflict with partial coverage and no new source mining. A failed probe or unknown observed identity retains only authorization-bound eligible prior facts as stale. A scope declaration is input authority, not independent proof of its truth.

There is no recursive discovery, IDE database access, remote fetch, execution of Git, repository import, hook/helper invocation or indexed command execution. `inventory` records whether a permitted root was supplied by `configured`, `native` or explicit `workspace` observations. Native tools/workspace exports are supplied by the caller; this tool does not query native applications. The `json`/`yaml` normalized observation adapters accept caller-supplied metadata documents. Two source-backed adapters consume actual owner files:

- `capability-yaml`: closed `kp-capability/v1` `meta.yml`, using the approved SafeLoader family and current flat owner field/type contract. It retains the declared ID as title when title storage is allowed. The capability ID is scoped by logical repository, capability kind and global/project scope; same names in other owners remain distinct.
- `skill-frontmatter`: only `name` and `description` from explicitly selected `SKILL.md` YAML frontmatter. Requires an explicit `capability_scope` (`global` or `project`). It derives the matching repository/kind/scope capability ID. Markdown body content is never retained. Other frontmatter shapes refuse rather than guessing.

All YAML paths use SafeLoader with composition-time depth/node limits, duplicate-key rejection and refusal of aliases, explicit tags and multiple documents. No custom YAML parser or repository code is loaded. Actual metadata and frontmatter formats outside these closed subsets report partial coverage; no claim of ecosystem-wide format coverage is made.

The example below authorizes only one exact synthetic source file. Root identities are previously resolved inventory facts, not an instruction to probe unknown roots. Add source-backed adapters by replacing `adapter`/`path` and supplying the eligible field list; a frontmatter source additionally supplies `capability_scope`.

```json
{
  "schema": "ecosystem-index/config/v1",
  "exclude_paths": [],
  "exclude_identities": [],
  "bounds": {"roots": 500, "entities": 5000, "input_bytes": 262144, "snapshot_bytes": 20971520, "refresh_seconds": 60},
  "roots": [{
    "key": "example",
    "path": "/absolute/permitted/project",
    "identity": {"provider": null, "remote": "https://code.example/team/project.git"},
    "scope": "permitted",
    "inventory": "configured",
    "title": "Example Project",
    "aliases": ["example-owner"],
    "storage_fields": ["title", "description", "aliases", "pointers", "edges"],
    "sources": [{"path": "eligible.json", "adapter": "json", "kind": "capability", "revision": null,
                 "fields": ["title", "description", "aliases", "pointers", "edges"]}],
    "git": null
  }]
}
```

A normalized metadata document has this closed shape:

```json
{
  "schema": "ecosystem-index/metadata/v1",
  "entities": [{
    "id": "capability:example",
    "kind": "capability",
    "title": "Example",
    "description": "An explicitly storage-eligible description.",
    "aliases": ["demo"],
    "pointers": [{"kind": "instruction", "path": "AGENTS.md"}],
    "edges": []
  }]
}
```

Normalized documents accept `capability` and `repository` entities. A repository entity must name the exact logical repository ID for its current root; it has no parent or `belongs_to` edge. Its eligible pointers merge with the inventory facts and remain available to repository, clone and worktree context. Other repository IDs refuse the source. Only `id` and `kind` are required per normalized entity. Identity fields are schema-eligible; other fields require both root and source storage allowlists. The optional fields above are the whole persistable field vocabulary. A root's title/aliases also require root eligibility. Generic README, AGENTS, policy, decision and work-content bodies have no adapter. Their pointers can be declared; their prose cannot be copied into observations. Secret-shaped or malicious eligible values refuse the source with a bounded reason; keyword refusal is an additional filter, never evidence of storage eligibility. Recognized noneligible fields are omitted, and unknown fields refuse. No raw source bytes, query history, logs, environment dumps or interaction feedback enter the cache.

Explicit normalized IDs may intentionally refer to the same entity across sources. Distinct facts and parent relationships survive, with supporting observations and conflict labels; no source-priority guess resolves them. Real capability adapter IDs incorporate their source repository to avoid accidentally merging unrelated owners.

## Git identity and scope

Logical repository IDs hash an already-authorized provider ID when supplied; otherwise a normalized credential-free remote identity; otherwise a local root/common-directory identity. Userinfo, query and fragments are discarded without following a URL. Local/remote-helper forms refuse. Missing remotes never group roots by project name.

An optional `git` object must explicitly supply `common_dir` and `git_dir`, both absolute permitted physical directories. The adapter verifies only the fixed `.git` marker, optional `commondir` marker and common `config`. It never follows discovered destinations: marker-derived paths must match the supplied scopes. Symlinks refuse. It reads no ref bodies, Git commands or config includes; unsupported layout/includes return partial/unverified facts. Provider identity remains declared by the external inventory, never qualified by this small parser.

Clone IDs hash the physical common-directory path; worktree IDs hash the per-worktree Git directory plus root. Multiple clones can share one logical repository while retaining distinct locations. Linked worktrees share a clone but retain their own IDs. No root is preferred as primary and no writable/contributable/approved inference is made.

## Storage and refresh

Paths remain explicit on every CLI invocation. Select private config/cache directories outside indexed roots and source repositories. Conventional choices are `${XDG_CONFIG_HOME:-$HOME/.config}/ecosystem-index/config.json` and `${XDG_CACHE_HOME:-$HOME/.cache}/ecosystem-index/snapshot.json`; this tool does not scan or create those directories. Provision the selected directories as 0700 and config/cache files as 0600. Config is read-only input and is never overwritten.

Writable path components are opened without following symlinks. Private directories/files must belong to the current user; nonregular files, unsupported ownership and wrong private modes refuse. Refresh is supported on POSIX in the main thread with an available real-time deadline timer; an unsupported thread/host or pre-existing application timer refuses. Queries have no timer/platform requirement beyond the safe local filesystem primitives.

Linux directory traversal requires `O_PATH`: each single component is pinned with `O_NOFOLLOW`, checked for directory type and ownership, and reopened through literal `.` relative to that pin. The reopened descriptor retains directory `fsync` support. Missing primitives or failed checks refuse without a path-based fallback. Other POSIX hosts retain the native `O_DIRECTORY|O_NOFOLLOW` path. This avoids the named-component flag interaction reported in [gVisor issue 14786](https://github.com/google/gvisor/issues/14786); it still requires correct host descriptor and no-follow semantics. Offline fixtures are not deployed-runtime qualification.

Refresh rechecks scope, identity, exclusions and field eligibility, then hashes bounded inputs/config bindings. Every inventory/Git/source input has a required `authorization_digest`, separate from its content `digest`. Authorization binds root identity/path/Git scopes, source path/adapter/kind/scope and exclusions. Reusing an inventory key after a path, identity or adapter change cannot retain facts from its prior scope; exclusion changes conservatively invalidate prior authorization bindings. Field-list changes are checked independently so reduced eligible fields can safely retain the remaining stale facts. Unchanged authorized metadata/Git inputs reuse validated parser records; observation time does not enter the input content binding. Missing or failed sources retain only matching-authorization facts as stale/unverified and make coverage partial. A successful complete metadata enumeration marks omitted entities `missing`; it does not treat a failed scan as deletion, and later failure never turns an existing `missing` tombstone into a search candidate. Eligibility removal drops no-longer-permitted facts. Snapshot generation and configured choices remain separate.

One cooperative `CACHE.lock` is created exclusively; contention returns `busy` and never steals or guesses stale ownership. Publication stages in the same directory, validates, flushes/fsyncs, reads back and atomically replaces the snapshot, then fsyncs the directory and verifies readback. Readers observe an old or new complete generation. Before atomic replacement, interruption preserves the old snapshot. After replacement, an interruption/error can leave the new validated generation committed, including when directory fsync or final readback is interrupted. The caller must read back the snapshot to establish the outcome and must not retry implicitly. No post-replacement rollback is promised. Cleanup removes only the temporary file/lock whose inode this operation owns. This is cooperative local consistency, not protection against malicious same-user writers.

Missing cache can start a refresh. Corrupt cache is unavailable to both queries and refresh, preserving evidence rather than discarding prior facts implicitly. A separate explicitly authorized disposal can permit a rebuild. No reader repairs corruption.

Hard maxima: 500 roots, 5000 distinct entities, 256 KiB per input, 20 MiB snapshot, 60 seconds per refresh, 512 description characters, 32 aliases, 20 context pointers and 4096 query bytes. Config may lower the operational limits. Extra parser node/depth and record-count bounds also refuse excessive complexity. Partial coverage and refusal are explicit; limits do not silently truncate a result into completeness.

## Verification and lifecycle boundary

```text
python3 -B -m unittest discover -s global/tools/ecosystem-index/tests -p 'test_*.py'
bash global/tools/ecosystem-index/install.sh --check
```

Tests create synthetic roots only. Release-blocking probes cover forbidden/unknown/renamed identities, provider-plus-remote exclusions, symlink escape, query writes/processes, malicious metadata, bounds, duplicate records, YAML complexity, private state, authorization-bound failed-source retention, missing tombstones, changed/unchanged bindings, future-clock refusal, repository context inheritance, pre/post-replacement interruption, write-free `-B` library loading, reader/publication overlap and lock contention. The immutable 27-case corpus is `tests/fixtures/relevance-v1.json`, SHA-256 `22307e06c568b4e20d2a5d7fe422209713d18ace1e22a44040691ac4e64feb72`; `relevance-results-v1.json` records the absent preimplementation baseline and the synthetic candidate result.

Source implementation, owner enrollment, installation, native qualification, retirement and downstream distribution are separate outcomes. Nothing here automatically enrolls, distributes, syncs, installs or activates this capability.
