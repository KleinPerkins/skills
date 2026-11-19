# Plans

This directory contains multi-session plans for `skills` (`KleinPerkins/skills`).

**Governance:** `~/dev/_ops/doc-warden/POLICY.md` §2 (taxonomy), §9 (archival).
Plans are **byte-identical-forever** once their Status line reads `ACCEPTED` — no in-place edits
after approval. A revision is a new `{{slug}}-v2.md` with a `Supersedes:` pointer; the prior
version is never modified.

## Index

| Plan | Status | Date | Notes |
|---|---|---|---|
| [agent-route-client-parity-primary-routing-v1.md](agent-route-client-parity-primary-routing-v1.md) | SUPERSEDED (conflicting router requirements only) | 2026-08-19 | Immutable historical plan; supersession scope and canonical authority are linked from [v2](agent-route-client-parity-primary-routing-v2.md). |
| [agent-route-client-parity-primary-routing-v2.md](agent-route-client-parity-primary-routing-v2.md) | CANONICAL SUCCESSOR APPROVED | 2026-11-03 | Mutable pointer to the canonical plan and its approval; planning merge remains the source-execution gate. |
| [agent-route-feedback-loop-v1.md](agent-route-feedback-loop-v1.md) | WITHDRAWN (unaccepted draft) | 2026-08-06 | Removed from active work by the [canonical revision](agent-route-client-parity-primary-routing-v2.md); original draft bytes retained, with no learned-feedback scope. |
| [context-efficiency-d02-skills-description-reduction-v1.md](context-efficiency-d02-skills-description-reduction-v1.md) | ACCEPTED | 2026-08-21 | Release 1.1 D-02 plan: retain scope, shorten 15 over-budget Skills descriptions, enforce deterministic 300/600/1,024 thresholds, and prove eligible-client discovery. |
| [context-efficiency-e01-durable-skills-source-v1.md](context-efficiency-e01-durable-skills-source-v1.md) | ACCEPTED | 2026-08-15 | E-01 child plan: reject standalone Skills sources nested below disposable Cursor worktrees, reconcile owned links/pointers from the durable primary, and prove root-class/idempotence/client closure. |
| [context-efficiency-e03-description-eligibility-v1.md](context-efficiency-e03-description-eligibility-v1.md) | ACCEPTED | 2026-08-15 | E-03 child plan: require strict YAML 1.2 Core frontmatter and `skill-description-normalization/v1`, fix the `update-skills` syntax blocker, and prohibit fallback totals. |
| [context-efficiency-e05-awa-v1-5-2-gcb-pin-v1.md](context-efficiency-e05-awa-v1-5-2-gcb-pin-v1.md) | ACCEPTED | 2026-08-17 | E-05 child plan: advance the global AWA standalone-release binding to qualified v1.5.2 through an exact pin, lockkit, isolated install, clean-room, and rollback proof without vendoring runtime bytes. |
| [context-efficiency-s02-skills-reduction-v1.md](context-efficiency-s02-skills-reduction-v1.md) | ACCEPTED | 2026-08-20 | Release 1 S-02 plan for reducing Skills-owned generated/global projections after protected E-09 (implemented; PR #152, Release-1 evidence PASS). |
| [dev-main-sync-global-capability-v1.md](dev-main-sync-global-capability-v1.md) | SUPERSEDED | 2026-09-09 | Superseded by accepted [v2](dev-main-sync-global-capability-v2.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v2.md](dev-main-sync-global-capability-v2.md) | SUPERSEDED | 2026-09-09 | Superseded by accepted [v3](dev-main-sync-global-capability-v3.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v3.md](dev-main-sync-global-capability-v3.md) | SUPERSEDED | 2026-09-12 | Superseded by accepted [v4](dev-main-sync-global-capability-v4.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v4.md](dev-main-sync-global-capability-v4.md) | SUPERSEDED | 2026-09-17 | Superseded by accepted [v5](dev-main-sync-global-capability-v5.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v5.md](dev-main-sync-global-capability-v5.md) | SUPERSEDED | 2026-09-17 | Superseded by accepted [v6](dev-main-sync-global-capability-v6.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v6.md](dev-main-sync-global-capability-v6.md) | SUPERSEDED | 2026-09-18 | Superseded by accepted [v7](dev-main-sync-global-capability-v7.md); retained byte-identically as historical evidence. |
| [dev-main-sync-global-capability-v7.md](dev-main-sync-global-capability-v7.md) | ACCEPTED | 2026-09-18 | Current authority: replace only the Phase Tiles foreground mark with the exact source-pinned Lucide draft-pull-request geometry, then close unchanged valid-host and governed-delivery gates. |
| [eco-lock-digest-exit-status-v1.md](eco-lock-digest-exit-status-v1.md) | ACCEPTED | 2026-08-09 | Fix `eco-lock.sh digest` returning non-zero for valid metas that omit optional `descriptor_ref`, with a focused shell regression and unchanged digest bytes. |
| [plan-refine-doctrine-hardening-v1.md](plan-refine-doctrine-hardening-v1.md) | ACCEPTED | 2026-08-09 | Harden `plan-refine` lifecycle, authorization, deterministic swarm routing, and evidence-based approval-report doctrine. |
| [shadow-sync-awa-release-exception-v1.md](shadow-sync-awa-release-exception-v1.md) | ACCEPTED | 2026-11-02 | Replace only the initial AWA v1.8.2 controller-deployment dependency with its owner-governed one-time audited release route; preserve fleet pins and all downstream safety gates. |
| [shadow-sync-extraction-v1.md](shadow-sync-extraction-v1.md) | ACCEPTED | 2026-11-02 | Standalone public proprietary product, complete technical rename, governed signed delivery, and gated migration/update; external safety and UAT gates remain open.  Controller-deployment dependency only is replaced by [the release exception](shadow-sync-awa-release-exception-v1.md); all other gates remain. |
| [shadowsync-beta-v0-6-v1.md](shadowsync-beta-v0-6-v1.md) | DRAFT | 2026-10-04 | Beta v0.6 corrective execution authority: operation-scoped admission, session/history ownership, stable results, exact-merged-main delivery, and explicitly open UAT. |
| [shadowsync-beta-v0-7-v1.md](shadowsync-beta-v0-7-v1.md) | ACCEPTED | 2026-10-05 | Beta v0.7 bounded corrective authority: linear/coalesced Live Log, truthful neutral Repair unavailability, stable repository/action hierarchy, governed ready-PR delivery, and explicitly open UAT. |
| [shadowsync-beta-v0-8-v1.md](shadowsync-beta-v0-8-v1.md) | ACCEPTED | 2026-10-05 | Beta v0.8 bounded corrective authority: complete bounded execution evidence, truthful command/relation diagnostics, dynamic AppKit appearance, local completed-report metadata, governed ready-PR delivery, and explicitly open UAT. |
| [shadowsync-beta-v0-9-v1.md](shadowsync-beta-v0-9-v1.md) | ACCEPTED | 2026-10-06 | Beta v0.9 bounded inspection authority: bulk local relation evidence, four-child read-only PR admission, retained inspection progress, coherent RLCC candidate hierarchy, governed ready-PR delivery, and explicitly open UAT. |
| [subagent-orchestration-sibling-assets-v1.md](subagent-orchestration-sibling-assets-v1.md) | DRAFT | 2026-09-01 | Declare/co-install/verify required runtime sibling assets (e.g. `model-tiers.json`) via an optional `kp-capability/v1` `assets:` field; fixes silent local-missing + cpp-stale catalog. See `docs/adr/0002-subagent-orchestration-sibling-assets.md`. |
| [codex-work-assessment-v1.md](codex-work-assessment-v1.md) | ACCEPTED | 2026-11-02 | Codex-first assessment, native qualification and governed activation. |

## Conventions

- Filename: `<slug>-vN.md` where `N` starts at `1`
- Status values: `DRAFT` → `ACCEPTED` → `SUPERSEDED` (tracked in the index row, NOT in the plan file itself after acceptance)
- A new version (`-v2`, `-v3`, …) is created when a material revision is needed post-acceptance; the prior version is immutable
- Draft plans may be edited in place before acceptance; accepted plans may not

## Archive

Superseded and retired plans that are no longer active but preserved for history live in
`docs/archive/plans/` (moved via `git mv`, not deleted).

## Scoped Codex installer addendum

The approved [scoped installer execution addendum](../../.planning/artifacts/PLAN-f7571d74-f495-5461-ae37-ed0e227347d5-fc42143e-439b-5956-95de-5682598a686b-v1.md) and its [governance sidecar](../../.planning/artifacts/PLAN-f7571d74-f495-5461-ae37-ed0e227347d5-fc42143e-439b-5956-95de-5682598a686b-v1.governance.json) partially amend only the prior prohibition on new generic bootstrap behavior. [ADR0013](../adr/0013-scoped-codex-skill-installation-through-the-existing-bootstrap.md) defines that bounded change. The existing canonical plan, requirements and all other installation/retirement/downstream gates remain authoritative. This is a navigation projection; no live installation is authorized.
