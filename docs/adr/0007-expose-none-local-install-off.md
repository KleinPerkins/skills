# ADR 0007: `expose: none` keeps a capability in the repo but never installs it locally
Status: accepted — 2026-10-20

**Owners:** Laurence Duggan (`KleinPerkins`); `KleinPerkins/skills` maintainers
**Scope:** `meta.yml` `expose:`, `bootstrap.sh` (install, reconcile, prune, repair, doctor), each
capability's own `install.sh`, `.github/scripts/verify-skills.sh`
**Decision owner:** Laurence Duggan (approved 2026-10-20)

## Decision

1. **One tracked setting decides local install.** `expose:` already lists which agent tools get a
   capability. It now also accepts the single value `none`, meaning "keep this capability in the
   repo, but never install it on any local machine". It applies the same way to every machine:
   a fresh bootstrap and an existing machine end up identical.
2. **What `none` does.** Bootstrap creates no links for it in any tool folder and never runs its
   installer, in install, reconcile, and repair alike. Reconcile and prune remove links an earlier
   install left behind. Doctor reports the capability as `OFF`, skips its runtime health check,
   and warns about any leftover link until reconcile removes it. Each capability's own
   `install.sh` also installs nothing when run directly; keep-awake's `--uninstall` still works so
   an earlier runtime can be removed.
3. **`none` stands alone.** `verify-skills.sh` rejects `none` combined with tool names. An absent
   `expose:` still means all three tools.
4. **cpp distribution stays separate.** Whether a capability is copied into cpp is decided only by
   the ecosystem orchestrator's `config/registry.yml` (`enrolled`/`excluded`/`demoted`), with
   `sync_policy: none` in `meta.yml` as the in-repo declaration for excluded global capabilities.
   `expose: none` is still validated and locked like any other value.
5. **The machine-local opt-out list is no longer the switch.** keep-awake's uninstall still records
   it in `capability-local.yml`, and bootstrap still honours that list for plugin installers, but
   a capability with `expose: none` is skipped before the list is consulted, so the two never
   disagree.

First users: `algorithmic-art` (also excluded from cpp), `session-close` (local scope, never
distributed), and `keep-awake` (already excluded from cpp).

## Why

The operator wanted some capabilities kept in the repo but not installed, everywhere. The only
existing switch was the machine-local opt-out list, which lives outside the repo, covers only a
plugin's installer, and still leaves its skill link in place: keep-awake looked uninstalled but
was still offered to Cursor, and bootstrap doctor reported it as needing repair. Reusing
`expose:` adds one value to a field operators already read for "where does this show up", instead
of a new field.

## Consequences

- Turning a capability off or back on is a one-line `meta.yml` edit followed by
  `bootstrap.sh --reconcile`.
- If an `expose: none` capability is ever enrolled for cpp, its cpp manifest entry would carry
  `expose: [none]`; confirm the cpp-side reconciler treats that as "no links" before enrolling one.
- `~/dev/capabilities/verify-capabilities.sh` (home repo) accepts `none` and checks that no links
  remain.
