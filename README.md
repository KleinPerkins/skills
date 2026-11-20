# KleinPerkins/skills

**Single source of truth for Tier-1 "global" agent skills** — the skills that are
useful everywhere, across every tool and every org. Cloned locally to
`~/dev/capabilities/skills` and consumed by Cursor, Claude, and Codex via symlinks.

This is the **public clean source successor** at `KleinPerkins/skills`
(GitHub repository ID `1461925043`). Retained original history, installed runtimes
and downstream pins have separate lifecycle controls.

The initial WORK enrollment and bootstrap correction were admitted in
[PR #2](https://github.com/KleinPerkins/skills/pull/2), producing main revision
`ef67b0f433d163e8d872aa47c8a016344177443e`.
[Main CI run 44696726922, attempt 1](https://github.com/KleinPerkins/skills/actions/runs/44696726922)
passed all four jobs. The subsequent
[read-only App qualification](https://github.com/KleinPerkins/skills/actions/runs/44697238310)
verified that same main revision, the repository-scoped reviewer App and its
inability to bypass either contributing ruleset. The App writer remained off
through these checks; WORK is enrolled and PERSONAL remains disabled.

These bootstrap and read-only results do not establish ordinary App delivery.
That requires a fresh ordinary WORK review and creation witness, an unedited
review receipt, current head/base CI and receipt admission, followed by the
separate writer activation gate, an actual App-owned squash merge and passing
merged-revision CI.

---

## Why this exists

Previously each global skill lived as a real directory under `~/.cursor/skills`
(canonical), with Claude/Codex symlinking into the Cursor copy. That kept tools in
sync but left the canonical content trapped in a machine-local config dir — no
version history, no clean way to reproduce it on a new machine.

This repo promotes the **global** tier into a real, versioned git repo. The repo
is now the single source; every tool reference is a symlink **into** it
("Model A"). Edit a skill once here, commit, and every tool picks it up.

---

## Skill tiering model

Skills are classified by how broadly they apply:

| Tier | Where it lives | Examples |
|------|----------------|----------|
| **Global** (all orgs, everywhere; **vendored to cpp** via the orchestrator) | **this repo** (`global/{skills,sub-agents,...}/`) → symlinked into each tool | `agent-route`, `swarm`, its three internal review agents, and the Anthropic flavor-2 set |
| **Local** (installed locally on operator machines; **NOT** vendored to cpp) | **this repo** (`local/{skills,tools,plugins}/`) → symlinked or activated locally | `isokit`, `session-close`, `update-skills`, `continual-learning-consolidate`, `continual-learning` |
| **Work / Affirm-shared** (home-policed) | `~/.cursor/skills` canonical + Claude/Codex symlinks; surfaced via the work code-workspace | `affirm-app-setup`, `affirm-checkout-setup`, `affirm-design`, `latency`, `snowflake-netskope-reset`, `customer-ops` |
| **Work / cpp-surfaced** (NOT home-policed) | `cpp/quiver/skills/<name>` → surfaced into `~/.{cursor,claude,codex}/skills` by cpp's `_ops/bin/cpp-install-skills.sh` (not by this repo's bootstrap) | `affirm-brand` (cpp-surfaced LINK/subscription wrapper; canonical = BOSS Notion), `council` (cpp-owned fork), `quickhost` (cpp-owned fork) |
| **Bespoke** (one project/context) | with its project | `numenor-automation`, `vision-intake` |

This repo holds the **Global** and **Local** tiers. Scope is decided by the containing
directory (`global/` vs `local/`) and kind by the shelf below it (`skills/`, `rules/`,
`sub-agents/`, `tools/`, `plugins/`) — only orchestrator → cpp vendoring eligibility differs;
per-tool symlink exposure is independent of scope. See `~/dev/OPERATING-MANUAL.md`
for the full dev-environment placement rules.

---

## Repo structure

```
skills/
├── README.md
├── bootstrap.sh         # recreate the tool symlinks on a new machine (idempotent)
├── .gitignore
├── global/              # Tier-1 global capabilities (vendored to cpp via the orchestrator)
│   ├── skills/
│   │   ├── agent-route/                  # flavor-1 (homegrown)
│   │   ├── capability/                   # flavor-1 — agent playbook: operate capabilities for a non-technical owner
│   │   ├── swarm/                        # flavor-1 — operator-facing evidence-led review orchestrator
│   │   ├── prompt-architect/             # flavor-2 (snapshot)
│   │   ├── frontend-design/              # flavor-2 (anthropics/skills)
│   │   └── …                             # Anthropic flavor-2 set (12 more, see table)
│   ├── rules/
│   ├── sub-agents/
│   │   ├── swarm-probe/                  # read-only reconnaissance and D01–D16 scoring
│   │   ├── swarm-reviewer/               # read-only dynamic territory review
│   │   └── swarm-verifier/               # read-only contradiction and clearance adjudication
│   └── tools/
└── local/               # local-scope capabilities (installed locally on operator machines only)
    ├── skills/
    │   ├── continual-learning-consolidate/
    │   ├── isokit/                       # flavor-2 — pinned community snapshot + browser checker
    │   ├── session-close/
    │   └── update-skills/
    ├── rules/
    ├── sub-agents/
    ├── tools/
    └── plugins/
        └── continual-learning/      # local Cursor marketplace plugin governor
```

The `global/skills/` Anthropic flavor-2 set is a verbatim, provenance-pinned snapshot of
`anthropics/skills` (each skill carries `meta.yml` with `flavor: 2` + `provenance_ref`,
and a generic `install.sh` whose `--refresh` reports drift against the pinned upstream
commit without mutating the snapshot).

`bootstrap.sh` iterates all kind shelves under `global/` and `local/` for tool exposure and activation.
Scope only determines whether the orchestrator vendors the capability into cpp. Local plugins are
first-class local capabilities: they may activate machine-local runtime behavior, but they are never
registry-enrolled for downstream vendoring.

Capabilities whose installer provisions activation-critical runtime may opt into
`runtime_contract: installer-doctor/v1`. Bootstrap then preflights exposure,
runs the installer before publishing links, rolls back links newly created by a
failed attempt, propagates installer failure, and runs `install.sh --doctor`.

Before any bootstrap action, `scripts/capability_meta.py` validates every
discovered manifest with the same dependency-free parser used by repository
verification, then emits one deterministic NUL-delimited action plan.
Bootstrap fully decodes that plan into Bash 3.2 indexed arrays and freezes it
before installers, doctor calls, registry reset, links, or stale-link pruning.
No metadata or parser reads occur during execution.

The flat grammar permits blank lines, column-zero comments, and `key: scalar`
entries only. Keys are unique lowercase ASCII identifiers from this explicit
allowlist: `assets`, `descriptor_ref`, `expose`, `flavor`, `id`, `install`,
`kind`, `owner`, `payload_digest`, `payload_version`, `post_mgmt`,
`provenance_ref`, `provenance_source`, `provenance_trust`, `runtime_contract`,
`schema`, `scope`, `shape`, and `sync_policy`. Unknown, indented, punctuated,
non-ASCII, control-bearing, or duplicate keys fail closed. `schema`, `id`,
`kind`, `flavor`, `scope`, `owner`, and `install` are required.

Scalars are plain by default. `descriptor_ref`, `payload_digest`,
`payload_version`, the three `provenance_*` keys, and `runtime_contract` may
instead use one matching pair of single or double quotes; surrounding spaces
or tabs are ignored. Inline comments, extra colons, embedded/mismatched quotes,
and control bytes are rejected.
`runtime_contract` remains optional; when present its parsed value must equal
`installer-doctor/v1`. Complete omission retains legacy best-effort behavior.
For opted-in capabilities, the frozen plan also preflights every destination
and ancestor and journals each destination's absent/symlink state and raw
target. Any installer or publication failure restores that exact state.
Bootstrap passes `KP_BOOTSTRAP_MANAGES_EXPOSURE=1` so cooperating installers
provision runtime only while bootstrap owns the single transactional
publication step.

---

## Symlink model (Model A: repo is the source, tools link in)

Each skill's real content lives at `global/skills/<name>/` or `local/skills/<name>/`. Every tool
reference is an **absolute** symlink into the resolved path:

```
~/.cursor/skills/<name>  ->  ~/dev/capabilities/skills/{global,local}/skills/<name>
~/.claude/skills/<name>  ->  ~/dev/capabilities/skills/{global,local}/skills/<name>
~/.codex/skills/<name>   ->  ~/dev/capabilities/skills/{global,local}/skills/<name>
```

Sub-agent capabilities link their single Markdown payload into each exposed
tool's agent directory:

```
~/.cursor/agents/<name>.md  ->  ~/dev/capabilities/skills/{global,local}/sub-agents/<name>/<name>.md
~/.claude/agents/<name>.md  ->  ~/dev/capabilities/skills/{global,local}/sub-agents/<name>/<name>.md
~/.codex/agents/<name>.md   ->  ~/dev/capabilities/skills/{global,local}/sub-agents/<name>/<name>.md
```

Per-tool exposure is declared in each artifact's `meta.yml` via `expose:`. Use
`cursor`, `claude`, and/or `codex`; inline lists like `expose: [cursor, claude]`
and space-separated values are both valid. If `expose:` is absent, bootstrap treats
the artifact as exposed to all three tools.

`expose: none` keeps a capability in this repo but never installs it on any local machine:
bootstrap creates no links and runs no installer, `--reconcile` removes links from an earlier
install, and `--doctor` reports it as `OFF`. Whether it is copied into cpp is decided separately by
the ecosystem orchestrator's registry (ADR 0007).

**To edit a skill:** change `{global,local}/skills/<name>/...`, commit, push. All symlinked
tools see it immediately — there is no copy step.

Local plugin governors live at `local/plugins/<name>/`. A plugin governor carries a descriptor
(`plugin.json`), a `SKILL.md`, and an installer with `--apply`, `--doctor`, and `--repair`. The
`continual-learning` governor pins descriptor drift, projects the marketplace plugin cadence to
`50` turns / `24` hours via bounded cache projection, retargets all behavior-bearing writers to
machine-local `agent-learnings.md`, and fails closed by pausing mining when an upstream cache shape is
incompatible. `continual-learning-consolidate` builds the scanner-gated home projection without git.

---

## Usage

### New machine

```bash
# clone this repo, then recreate every tool symlink
gh repo clone KleinPerkins/skills ~/dev/capabilities/skills
~/dev/capabilities/skills/bootstrap.sh
```

`bootstrap.sh` also clones the repo itself if `~/dev/capabilities/skills` is
missing, so copying just the script and running it works too.

### Re-run anytime

`bootstrap.sh` is idempotent: it relinks existing symlinks, creates missing ones,
and refuses to clobber a real (non-symlink) directory.

---

## The `capability` playbook skill

`global/skills/capability` is the agent **playbook** for operating capabilities on behalf of a
**non-technical owner** — someone whose only interface is their agent. It encodes one
environment-agnostic loop (confirm the intent in plain language → act via the environment's own
capability verbs → verify the real outcome → narrate plainly → self-repair → escalate only genuine
product / irreversible / secret decisions), a PM-vocabulary map, and safe-default inference. It is
deliberately environment-agnostic (names no specific downstream consumer, INV-zero-link); each
consumer binds the loop to its own verbs and health view on its side. Any agent discovers it
automatically via the skill's own description once it is surfaced (locally by `bootstrap.sh`, or
vendored downstream by the orchestrator).

## Personal Codex PDF provider qualification

For personal Codex build 23880, the already-installed official `pdf` plugin is
an owner-supported native alternative for the bounded operations in
[`docs/evidence/pdf/README.md`](docs/evidence/pdf/README.md). The record binds
the unchanged pinned PDF payload, native provider version and skill bytes,
fresh enabled discovery, local functional checks and visual verification.
A destination must independently match those facts before recording its bounded
acceptance. This does not install anything or authorize additional clients,
bootstrap, external requests, model workers or production-document workflows.
Advanced operations outside the recorded checks remain unqualified.

## The `swarm` review capability

`global/skills/swarm` is the single operator-facing entrypoint for an explicit
“launch/run/dispatch the swarm” request. It fingerprints the subject, runs
mandatory reconnaissance, dynamically charters 4–12 independent read-only
reviewers, verifies contradictions and high-risk paths, enforces a default-deny
authority ladder, and produces one deterministic three-section report. Its
standard-library helper owns only objective risk/sizing arithmetic, response
validation, revision fingerprints, bounded private run ledgers, coverage gates,
and rendering.

The three role definitions under `global/sub-agents/` are internal and inert
without a valid orchestrator dispatch. They expose only read tools. The skill
uses the same bounded parent-led protocol on runtimes without proven native
sub-agent support and labels that mode as degraded isolation.

## Cross-workspace sharing — owned by the orchestrator

Teammates in a downstream consumer workspace need the `global/` subset available without
cloning this private repo. That sharing (an ld-agnostic **vendored copy** delivered via a
governed PR) is owned by a **separate private orchestrator repo** — it is the single place the
relationship between this workspace and any downstream consumer is defined (INV-zero-link). This
repo intentionally names no specific consumer. See `~/dev/OPERATING-MANUAL.md`.

Pull requests are protected by runnerless v3 verification.

G4 informational proof: this head restores `.eco-registry.lock` byte-for-byte after the
controlled parity failure and proves `repo.skills.m3-verify` passes.

G4 requiredness proof: the same named job now blocks a failing head and permits this restored
head to merge.

## Personal Codex XLSX provider qualification

For personal Codex build 23880, the already-installed official Spreadsheets
plugin is an owner-supported native alternative for the bounded operations in
[`docs/evidence/xlsx/README.md`](docs/evidence/xlsx/README.md). The observation
binds the unchanged pinned XLSX payload, native provider version and skill bytes,
fresh enabled discovery, recalculation tests, saved-file structure and visual
readback. A destination must independently match those facts before recording
bounded acceptance. This does not install or enable a provider, publish another
home skill link, or authorize other clients, workers or external resources.
Desktop Excel/LibreOffice behavior and the unsupported workflows listed in the
record remain unqualified.
