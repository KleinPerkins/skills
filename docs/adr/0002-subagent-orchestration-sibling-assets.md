# ADR 0002: Capability payloads declare required sibling assets; the generic installer co-installs and verifies them
Status: accepted — 2026-09-01

## Decision

Fix the recurring "missing / stale `model-tiers.json`" failure at its earliest layer — the
capability **package contract** — with ONE generic correction rather than a `model-tiers.json`
special case:

1. **Declare.** Extend the shared `kp-capability/v1` meta contract with an OPTIONAL `assets:` list
   naming the runtime sibling files a capability's payload needs installed alongside its primary
   payload. `subagent-orchestration` declares `assets: [model-tiers.json]`.
2. **Co-install.** Teach the ONE generic installer
   ([`bootstrap.sh`](../../bootstrap.sh) `install_unit()` at `bootstrap.sh:344-375`) to link each
   declared asset next to the primary payload in the client rules dir — i.e. create
   `~/.cursor/rules/model-tiers.json → <repo>/global/rules/subagent-orchestration/model-tiers.json`.
   The capability's own [`install.sh`](../../global/rules/subagent-orchestration/install.sh) is
   updated to do the same for a standalone run.
3. **Verify + repair.** Teach `doctor`/`reconcile`/`repair` (`bootstrap.sh:378-400`) and the
   capability `install.sh --doctor` to fail when a declared asset is not installed, and teach the
   CI gate ([`verify-skills.sh`](../../.github/scripts/verify-skills.sh) around `verify-skills.sh:150`)
   to assert every declared asset exists in source. A missing sibling then surfaces as a loud,
   named failure instead of silent absence.

This aligns the installer with the resolution contract consumers **already** implement — the swarm
helper's second catalog candidate is literally `~/.cursor/rules/model-tiers.json`
([`swarm_helper.py:676-683`](../../global/skills/swarm/scripts/swarm_helper.py)) and the always-applied
rule instructs agents to read the installed sibling ([`subagent-orchestration.mdc:12-13`](../../global/rules/subagent-orchestration/subagent-orchestration.mdc)) — so the fix makes the installer produce the exact artifact the design assumed but never created.

For the **stale** half of the failure, the source-side freshness guard
(`MAX_CATALOG_AGE_DAYS = 30` in
[`verify_model_tiers.py`](../../global/rules/subagent-orchestration/verify_model_tiers.py)) is kept
as-is — it is working as designed. Two bounded, no-new-infra changes remove the recurring manual
cost and the cpp drift it causes:

- **Agent-driven re-verification.** The ≤30-day re-check against the live Cursor subagent model
  enum (a runtime schema no CI runner can see) is delegated to an agent task on the operator's
  existing automation surface (a Cursor Automation or a `local-jobs` entry). When the catalog is
  within a warn window of expiry, the agent re-verifies against its own live `Task`-tool enum and
  opens the small refresh PR — the same shape as the 2026-09-01 tactical fix
  ([PR #172](https://github.com/KleinPerkins/skills/pull/172)). No human edits the catalog by hand.
- **Post-refresh sync.** After a catalog-refresh PR lands on `skills` `main`, the existing
  ecosystem-orchestrator sync (WF2) is triggered so cpp's vendored copy is re-vendored promptly
  instead of drifting until some unrelated sync happens to run.

## Why

### Problem

`subagent-orchestration` ships an always-applied rule (`subagent-orchestration.mdc`) plus a
machine-readable model catalog (`model-tiers.json`) and its validator (`verify_model_tiers.py`).
The rule and every consumer (the swarm, and any agent choosing a subagent tier) depend on the
catalog being present and current. In practice the catalog is repeatedly **missing** from local
installs and **stale** in cpp, so tier routing silently degrades or points at models the runtime no
longer accepts.

### Evidence and reproducible failure

Reproduced live on 2026-09-01 from clean state (sandbox `HOME`, no side effects on the real client):

- **Local install omits the sibling.** `bootstrap.sh --install --dry-run` emits exactly one link
  for this capability — `~/.cursor/rules/subagent-orchestration.mdc` — and no line for
  `model-tiers.json`. Running the capability `install.sh` into a sandbox `HOME` creates only the
  `.mdc` symlink; `~/.cursor/rules/model-tiers.json` is **absent**. This is why the operator had to
  hand-create that symlink on 2026-09-01.
- **Doctor does not detect it.** `install.sh --doctor` and `bootstrap.sh` doctor both return
  success with the catalog sibling absent — the rule branch checks only `$id.mdc`
  (`bootstrap.sh:388`, `verify-skills.sh:150`).
- **Consumers survive only by side-channel.** The swarm resolves the catalog from source
  co-location (`Path(__file__).resolve().parents[3]/rules/subagent-orchestration/model-tiers.json`,
  `swarm_helper.py:668-672`) and only falls back to the installed sibling
  (`swarm_helper.py:676-683`). Co-location works only because the source repo is co-present on this
  machine; a consumer reading the literal installed path finds nothing.
- **cpp is stale, not missing.** cpp's vendored `quiver/rules/subagent-orchestration/model-tiers.json`
  is pinned at `verified_against: cursor-subagent-model-enum/2026-07-28` and routes slugs the enum
  no longer offers (`claude-sonnet-5-thinking-max`, `gpt-5.6-terra-medium`). Running the current
  (2026-09-01) checker against cpp's catalog fails. cpp's directory last synced at orchestrator run
  #731 (2026-08-23) carried only the `.mdc`; the source catalog then refreshed on 2026-08-28 and
  again 2026-09-01, and no sync has run since — so cpp is now older than its own
  `MAX_CATALOG_AGE_DAYS = 30` guard.
- **The orchestrator already carries the catalog.** The orchestrator's payload lister
  (`payload_shared_list()` in `ecosystem-orchestrator/lib/payload.sh`) vendors every git-tracked
  file except a fixed exclusion set (`meta.yml`, `install.sh`, `VENDORED.md`, `tests/*`,
  `EVIDENCE.md`, caches). For this capability it returns exactly `model-tiers.json`,
  `subagent-orchestration.mdc`, `verify_model_tiers.py`. So cpp staleness is a **sync-cadence**
  problem, not an orchestrator omission.

### Root cause

Two distinct recurrences, each with a different earliest layer:

- **Missing (distribution) — earliest layer is the package contract.** The capability
  [`meta.yml`](../../global/rules/subagent-orchestration/meta.yml) declares `kind: rule` and
  `install: install.sh` but has no way to declare that `model-tiers.json` is a required part of the
  payload. Because the contract is silent, the generic installer, doctor, reconcile, repair, and CI
  all faithfully process only the `.mdc`. Nothing downstream is "buggy" — they honor a contract that
  under-specifies the payload. Correctness is first lost where the payload is declared.
- **Stale (freshness) — earliest layer is the hand-verified-snapshot design.** `VERIFIED_CURSOR_SLUGS`
  is a hand-maintained mirror of a runtime enum that CI cannot query, guarded by a 30-day clock. By
  construction it must be re-verified by a human on a recurring cadence; the cpp copy then drifts
  further because the orchestrator→cpp edge re-vendors episodically (per sync run), not when the
  catalog's freshness clock advances.

The dangling `~/.cursor/rules/subagent-orchestration.mdc.bak.<timestamp>` symlink observed on this
machine is a **separate** mechanism, not part of this defect: it is created by the `~/dev` rule
mirror installer (`~/dev/_ops/bin/install-agent-rules.sh:84,120`, backup-before-relink capturing an
ephemeral worktree source path), which the skills installers never do. It is called out here only to
scope it OUT.

### Alternatives considered

1. **Declare required sibling assets in the contract + co-install + doctor/CI validate (CHOSEN).**
   One optional, additive `assets:` field consumed by the single generic installer and the CI gate.
   Generic across all capabilities and kinds, not a `model-tiers.json` special case.
2. **Project a bounded per-capability package directory** (e.g. install
   `~/.cursor/rules/subagent-orchestration/{.mdc,model-tiers.json}`). Rejected: it changes the
   installed rule path every consumer already hard-codes (`~/.cursor/rules/subagent-orchestration.mdc`,
   `swarm_helper.py:678`) and fights Cursor's flat `*.mdc` rules-dir convention. More blast radius
   for no additional correctness.
3. **Co-install every non-payload file in the capability dir** (no declaration). Rejected: it would
   also drop `verify_model_tiers.py` (CI-only) and any future dev file into the client rules dir.
   Implicit and noisy; the explicit `assets:` list keeps the installed surface minimal and intentional.
4. **Embed the tier data into the `.mdc` and delete the sibling.** Rejected: the `.mdc` is loaded
   into every agent's context, so inlining a machine-readable catalog bloats always-applied context
   (against the repo's active context-efficiency work), and it reverses the existing decision to
   point at `model-tiers.json` for catalog data. It also does nothing for the freshness recurrence.
5. **Doctor/integrity validation only** (detect the missing sibling, do not install it). Rejected as
   insufficient alone — it converts silent breakage into a loud failure but still leaves the operator
   to fix it by hand. Adopted as the *verification half* of option 1, not as a standalone fix.

### Why the chosen design is both simpler and more complete

- **Simpler:** one optional meta field + a few lines in the single generic installer, its doctor,
  and the CI gate. No new registry, daemon, service, cache, installer channel, or schema version.
  It reuses `link_path()` (so co-installed assets automatically join `DESIRED_LINKS` and are neither
  pruned nor duplicated, `bootstrap.sh:283-296,447`) and the existing per-kind payload checks.
- **More complete:** it fixes the defect for *every* capability that has runtime siblings, not just
  this one; it closes install, doctor, reconcile, repair, AND CI in lockstep; and it makes the
  installed artifact match the contract that consumers already assume, so the fragile source
  co-location path stops being load-bearing.

## Consequences

### Failure behavior after the change

A capability that declares an asset it does not ship, or an install that fails to place a declared
asset, fails loudly and by name: CI (`verify-skills.sh`) goes red if the source file is absent, and
`doctor` reports the specific missing installed sibling instead of returning OK. Absence becomes
detectable and repairable rather than silent.

### Local-install implications

`bootstrap.sh --install/--reconcile/--repair` create and maintain
`~/.cursor/rules/model-tiers.json` alongside the `.mdc`. The operator's manual 2026-09-01 symlink
becomes a managed desired link (kept if already correct, relinked to the canonical source if not).
`link_path()`'s existing "refuse to overwrite a real (non-symlink) path" guard (`bootstrap.sh:290-291`)
still applies, so a real file at that path is never clobbered. No consumer code must change; the
swarm's source-co-location path remains as a still-valid fallback.

### Ecosystem-orchestrator implications

None are required for correctness: the orchestrator already vendors `model-tiers.json` and
`verify_model_tiers.py` via `payload_shared_list()`. The optional `assets:` field is not part of the
`eco-lock` digest field set and is regenerated away by the orchestrator's cpp-meta translation, so it
adds no lock churn and does not propagate into cpp's meta. The plan records an OPTIONAL,
defense-in-depth orchestrator-side completeness check (assert every source-declared asset is present
in the generated payload) as a non-blocking follow-up.

### cpp distribution and bootstrap implications

cpp receives assets through the existing governed edge (orchestrator sync → cpp PR); this ADR adds no
hand-vendoring and no cpp-side schema change. The concrete cpp defect (an expired 2026-07-28 catalog)
is resolved by the "post-refresh sync" decision above: once a catalog refresh lands on `skills` `main`,
an orchestrator sync re-vendors the current catalog into cpp under its normal governed PR. cpp's own
`verify_model_tiers.py` freshness guard then passes again.

### Compatibility and migration

- `assets:` is **optional and additive**. The CI required-keys loop asserts a fixed key set is
  present and does not reject unknown keys (`verify-skills.sh:80`), and `eco-lock`'s digest hashes a
  fixed field list that excludes `assets:`, so `.eco-registry.lock` stays in parity with no regen.
- The shared contract is validated by sibling repos (`~/dev/_ops/eco/manifest.sh`, kp-mcp's
  verifier). The plan includes an explicit task to confirm those validators also tolerate the extra
  optional key before the field is relied upon; if any enforces a closed key set, that validator is
  widened first.
- No data migration. Existing installs converge on the next `bootstrap.sh --reconcile`.

### Rollback

Low-risk and staged. Remove the `assets:` line from `meta.yml` to stop co-installing (installer and
CI simply revert to `.mdc`-only, the pre-ADR behavior); revert the installer/verifier commits to
fully restore prior logic. No lockfile repair or data migration is needed because the change adds no
tracked-identity field and no canonical digest bytes. The freshness-automation piece is independently
revertible (delete the automation entry); the catalog and its guard are untouched by rollback.

### Explicit non-goals

- No new registry, daemon, service, cache, or installer channel; no paid or self-hosted CI runners
  for the freshness re-check (it is agent-driven on existing automation).
- No `kp-capability/v1` schema-version bump (the field is optional/additive).
- No embedding of catalog data into the always-applied rule.
- No change to the installed rule path or to Cursor's rules-dir convention.
- No fix here for the unrelated `~/dev/_ops` `.bak` dangling-symlink lifecycle; if pursued it is a
  separate ADR under `~/dev`.
- The long-term design is NOT implemented by this ADR or its companion plan; implementation proceeds
  only after this ADR is accepted.
