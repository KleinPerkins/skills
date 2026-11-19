# awa — Agent Worktree Automation (standalone-release binding)

**Global Capability Binding (GCB) to a Standalone System Package (SSP).** AWA is one self-contained
product that lives in its own repo, `KleinPerkins/awa`, and installs itself from a fresh clone. This
shelf entry is the *binding*: it pins a release and, on `install.sh`, clones `KleinPerkins/awa` at
that exact commit and hands off to the checkout's own installer. The shelf carries a pinned release
pointer — never the runtime bytes.

## Two contracts, one product

- **SSP (Standalone System Package)** — the `KleinPerkins/awa` repo is complete on its own:
  `git clone … && ./install.sh` installs a generic kernel + engine + dashboard + frozen contract
  into your XDG dirs, wires the Cursor hooks, and registers an add-only MCP server. No sibling-repo
  dependency; idempotent; backup-before-write.
- **GCB (Global Capability Binding)** — this `global/tools/awa/` shelf is a Flavor-2
  `standalone-release` entry. Its `install.sh` reads the pin from [`meta.yml`](meta.yml)
  (`provenance_source` @ `provenance_ref`), clones/updates the repo at that commit into a per-user
  checkout, then runs the checkout's own `install.sh`. Enrollment/exposure is managed by the
  ecosystem workflow (WF1); the host supplies only a machine-local policy overlay.

## What AWA is

AWA keeps agent work off your main checkout: mutations are steered into an isolated `git` worktree
(a "Safe Workspace"), native edits to the primary are detected, unsafe cleanups are refused, and
uncommitted work can be recovered. It is **kernel-first** — the safety guarantee holds with the
engine/daemon **off**. Every org/host-specific fact lives only in a machine-local policy overlay
(`AWA_POLICY`); the product itself names no organization.

## Where the software lives

| | |
|---|---|
| Repo | `github.com/KleinPerkins/awa` (private) |
| Pinned release | `v1.8.2` |
| Pinned ref | `v1.8.2` (immutable annotated release tag) |
| Pinned commit | `cfe9437739d2928014c2156532d1986a8511fd30` |

This [maintenance release](https://github.com/KleinPerkins/awa/releases/tag/v1.8.2)
backports the generic hard-no-touch policy contract from AWA PR #184 onto exact
v1.8.1 through [PR #200](https://github.com/KleinPerkins/awa/pull/200). It excludes
later mainline registration work. Updating this binding does not install the
runtime, deploy concrete host policy, or activate a consumer; those require their
own verified rollout steps.

The pin is recorded in [`meta.yml`](meta.yml). To move to a newer release, bump `provenance_ref`
(and the `tool.yml` `release:` block), regenerate the repo lock, and open a PR.

## What `install.sh` does

`install.sh` (shape `release-descriptor`, `sync_policy: standalone-release`) **binds** the pinned
SSP release: it clones/updates `KleinPerkins/awa` at the pin and delegates the actual install to the
checkout's own `install.sh`. It carries no runtime bytes and no `bin/`.

```bash
install.sh              # clone-at-pin + run the standalone install (default; idempotent)
install.sh --repair     # force-update the checkout to the pin + standalone --repair
install.sh --doctor     # read-only health check of the binding + standalone doctor
install.sh --check      # CI-safe static preflight (no writes, no network)
install.sh --print      # print the resolved (source, ref, checkout)
install.sh --uninstall [--keep-state]   # delegate the standalone uninstall + drop the gcb pointer
```

All paths are `HOME` / `XDG_*`-relative (CI-safe; honors overrides):

```
${XDG_DATA_HOME:-$HOME/.local/share}/awa/checkout               pinned KleinPerkins/awa clone
${XDG_DATA_HOME:-$HOME/.local/share}/awa/gcb-pointer.json        awa-gcb-pointer/v1 binding record
${XDG_DATA_HOME:-$HOME/.local/share}/awa/current                 runtime  (written by the SSP installer)
${XDG_DATA_HOME:-$HOME/.local/share}/awa/release-pointer.json    release  (written by the SSP installer)
```

`install.sh` clones over SSH by default (derived from `provenance_source`); set `AWA_CLONE_URL` to
override the remote, or `AWA_CHECKOUT` to relocate the checkout. If `git` or the network is
unavailable it degrades with an honest message instead of leaving a half-install.

## Installing AWA directly (without the shelf)

The SSP is always installable straight from its repo — the shelf is a convenience/pin, not a
gatekeeper:

```bash
git clone git@github.com:KleinPerkins/awa.git
cd awa
./install.sh            # idempotent; installs into your XDG dirs
./install.sh --doctor   # read-only health check
```
