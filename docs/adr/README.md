# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for `skills` (`KleinPerkins/skills`).

**Governance:** `~/dev/_ops/doc-warden/POLICY.md` §2 (taxonomy), §9 (archival).
ADRs are **byte-identical-forever** once their Status line reads `accepted` — no in-place edits
after acceptance, not even a status-bullet edit. Supersession is recorded only via a new ADR's
`Supersedes:` pointer and this index file's row update.

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001-agent-route-feedback-loop.md](0001-agent-route-feedback-loop.md) | Per-entry learned multiplier for `agent-route`, not global weight tuning | WITHDRAWN (unaccepted draft; see [0012](0012-separate-ecosystem-discovery-from-codex-project-entry.md)) | 2026-08-06 |
| [0002-subagent-orchestration-sibling-assets.md](0002-subagent-orchestration-sibling-assets.md) | Capability payloads declare required sibling assets; the generic installer co-installs and verifies them | ACCEPTED (catalog-freshness clauses superseded by 0006 — 2026-10-19) | 2026-09-01 |
| [0003-dev-main-sync-global-capability.md](0003-dev-main-sync-global-capability.md) | Own Dev Main Sync as a source-owning global tool capability | SUPERSEDED | 2026-09-09 |
| [0004-dev-main-sync-repository-lifecycle-control-center.md](0004-dev-main-sync-repository-lifecycle-control-center.md) | Make Dev Main Sync a repository lifecycle control center | ACCEPTED (source-ownership portion superseded at gated handoff by 0010) | 2026-09-09 |
| [0005-shadowsync-preview-admission-and-result-ownership.md](0005-shadowsync-preview-admission-and-result-ownership.md) | Separate ShadowSync preview admission from mutation evidence and result ownership | DRAFT | 2026-10-04 |
| [0006-subagent-task-tier-routing.md](0006-subagent-task-tier-routing.md) | Route subagents by task tier to fixed-level models; reported fallbacks trigger catalog maintenance | ACCEPTED (transport-failure-only retry, structure-only checking, and fallback-only reporting clauses superseded by 0008 — 2026-10-21; decision 4 narrowed for Codex economy by 0009 — 2026-10-31) | 2026-10-19 |
| [0007-expose-none-local-install-off.md](0007-expose-none-local-install-off.md) | `expose: none` keeps a capability in the repo but never installs it locally | ACCEPTED | 2026-10-20 |
| [0008-subagent-launch-planner.md](0008-subagent-launch-planner.md) | Plan each subagent launch with the tier checker and ride out rejected models in a fixed order | ACCEPTED (retained ADR0006 decision 4 narrowed for Codex economy by 0009 — 2026-10-31) | 2026-10-21 |
| [0009-codex-native-economy-policy.md](0009-codex-native-economy-policy.md) | Add an opt-in Codex economy data pair to the native resolver | ACCEPTED | 2026-10-31 |
| [0010-shadow-sync-extraction-ownership.md](0010-shadow-sync-extraction-ownership.md) | Extract ShadowSync into a standalone governed macOS product | ACCEPTED | 2026-11-02 |
| [0011-codex-work-assessment.md](0011-codex-work-assessment.md) | Codex-first assessment, explicit model/effort and bounded escalation | ACCEPTED | 2026-11-02 |

## Conventions

Format (Nygard):
```markdown
# ADR <NNNN>: <title>
Status: <draft|accepted|superseded> — <date>

## Decision
## Why
## Consequences
```

- Numbering: 4-digit zero-padded sequential (`0001`, `0002`, …)
- Filename: `<NNNN>-<slug>.md`
- Status values: `draft` → `accepted` → `superseded`
- `Supersedes: ADR-NNNN` line added to the new ADR; old ADR is never modified
- The index row for a superseded ADR is updated to `superseded — <date>` (this index is mutable;
  the ADR file itself is not)

## Canonical v2 ADR index

The legacy index above preserves prior decisions and dates. Canonical v2 ADRs are listed below; this generated index is a navigation projection, not semantic authority.

| ADR | Status | One-line decision |
|---|---|---|
| [0012](0012-separate-ecosystem-discovery-from-codex-project-entry.md) | Accepted (installer prohibition partially amended by [0013](0013-scoped-codex-skill-installation-through-the-existing-bootstrap.md)) | Separate ecosystem discovery from Codex project entry |
| [0013](0013-scoped-codex-skill-installation-through-the-existing-bootstrap.md) | Accepted | Scoped Codex skill installation through the existing bootstrap |
