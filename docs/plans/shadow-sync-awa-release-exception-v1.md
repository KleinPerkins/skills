# ShadowSync AWA release dependency exception

**Version:** v1
**Plan-type:** standard
**Owning repository:** KleinPerkins/skills
**Status:** ACCEPTED — FROZEN; AWA authority merge remains a prerequisite
**Date:** 2026-11-02
**Relates to:** accepted `shadow-sync-extraction-v1.md`, phase P4 and SF-03;
  accepted ADR0010 remains unchanged.
**Supersedes:** only the P4 requirement to deploy controller maintenance-base
  support before the initial AWA v1.8.2 safety release.
**Owner direction:** proceed with the one-time audited AWA maintenance-release
  exception while retaining deployed controller 0.13.0 and all fleet pins.

## Purpose and boundary

Use the AWA-owned one-time release-administration path in
[AWA ADR0031](https://github.com/KleinPerkins/awa/blob/main/docs/adr/0031-one-time-administrator-release-route-for-awa-v1-8-2.md)
after its authority is merged and release gates pass. AWA remains the sole owner
of the exact maintenance base, backport scope, protection/merge procedure,
verification, release approval and provenance. This pointer does not duplicate
or expand its authority.

The controller source change already merged is retained as history. Its
deployment, replacement binary, fleet rebinding and whole-fleet qualification
are removed from this extraction's execution path. Do not resume those steps
because historical plans or candidate receipts still mention them.

## Replacement dependency and owner map

| Order | Owner | Required evidence |
|---|---|---|
| 1 | AWA release administrator and independent reviewer | Accepted successor, exact v1.8.1/PR184 provenance, full candidate verification, independently reviewed patch, protected maintenance PR, audited exact-head squash, identical reviewed/merged tree, sealed branch and separately approved immutable v1.8.2 release |
| 2 | Skills binding owner | Exact released tag/commit and artifact identities; generated lockkit parity; truthful maintenance-release provenance; no unrelated release or descriptor change |
| 3 | Runtime installation owner | Verified exact bound AWA runtime, parser/module identity and synthetic fail-closed/zero-target-access behavior; recoverable prior runtime |
| 4 | dev policy owner | Concrete hard-no-touch literals and compatibility binding deployed under dev governance; no product duplication of host literals |
| 5 | ShadowSync product owner | PRD/plan dependency successor, pinned bounded matcher consumer, pre-access rejection evidence and remaining signed migration/update readiness gates |

The order is not an atomic cross-repository transaction. Scope-independent
source/CI preparation may continue. Installed activation still requires every
runtime, policy and consumer gate; no policy removal, permissive fallback or
legacy host activation accommodates incomplete dependencies.

## Unchanged constraints

- Preserve the accepted extraction plan and historical evidence byte-for-byte.
- Leave all existing Skills/fleet delivery policies, controller digest pins,
  generated controller locks, App permissions and ordinary merge rules unchanged.
- ShadowSync retains its repository-specific native GitHub Actions/App model.
- No real protected repository is a test fixture or discovery target.
- Source extraction, CI operation, release, runtime installation, migration,
  legacy retirement and UAT remain separate milestones.
- AWA's one-use administration receipt is not a controller check or App approval.
- Do not change the Skills AWA pin until the governed release exists and is
  verified; no local candidate or mutable branch substitutes for an immutable tag.

## Execution and verification

Prepare this additive record privately, verify its exact delta independently,
and adopt it through the applicable Skills documentation workflow and ordinary
PR delivery. The semantic change is only the dependency replacement above.
Confirm old accepted plan bytes, controller policy/lock bytes and registry pins
are unchanged in this governance PR. Run documentation and repository verification.

After AWA publication, implement the separately reviewed binding PR using current
Skills main, a writer-owned worktree, lockkit, the exact released commit and
required checks. Read back merged source and installed runtime separately.

## Completion and recovery

Governance completion requires this successor merged and discoverable from the
plan index, plus ShadowSync's corresponding requirement/plan successor. It does
not prove AWA release or downstream deployment. Record each completion against
its exact revision and evidence.

Before adoption, revise the draft; after acceptance, preserve bytes and author a
successor for changed scope. If the AWA release gate fails, retain the current pin
and stopped application. Never alter shared controller protections or ship current
AWA main as a shortcut.
