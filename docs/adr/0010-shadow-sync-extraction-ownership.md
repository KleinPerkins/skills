# ADR 0010: Extract ShadowSync into a standalone governed macOS product
Status: accepted — 2026-11-02
Supersedes: ADR-0004 source-ownership portion only; effective at the gated handoff below.

**Scope:** Skills source ownership and handoff only. The linked accepted plan owns identity, installation, CI and release constraints; destination ADR adoption remains pending.

**Decision owner:** Laurence Duggan (`KleinPerkins`)
**Owners:** ShadowSync architect/release engineer; Skills, dev, AWA and repository-administration owners retain their own authority.
**Authority:** [accepted execution package v1](../plans/shadow-sync-extraction-v1.md), accepted by the explicit 2026-11-02 instruction “PLEASE IMPLEMENT THIS PLAN”.

## Decision

1. Establish public `KleinPerkins/shadow-sync` as a proprietary macOS product, with durable checkout `~/dev/personal/shadow-sync`. Publish only the reviewed allowlisted source snapshot and sanitized provenance. Preserve the original private Skills history; import no unrelated history or machine-local state.
2. Adopt technical identity `shadow-sync` and `com.kleinperkins.shadow-sync` end to end. Preserve product name ShadowSync and ShadowSync.app. Legacy identity is restricted to explicit migration readers, compatibility fixtures and immutable evidence; new active writes use the new identity.
3. Preserve the existing managed-host/manual-router architecture. A signed, source-independent lifecycle coordinator owns installation, identity migration, recovery and Sparkle replacement coordination. Preserve one effective operation lock, user authority/selections and recoverable data throughout migration. Startup remains opt-in through normal macOS Login Items.
4. Authorize free standard GitHub-hosted CI and the Sterling-style reviewer-App process only for the new repository, contingent on the companion dev exception and settings verification. The reviewer App alone approves eligible exact heads and arms native squash auto-merge. Ordinary implementation delivery has no additional operator code-review gate. Protected automation administration and product-release approval remain separate.
5. Begin with arm64/macOS 26, candidates 0.10.0 (15) and 0.10.1 (16), and independent ShadowSync Sparkle keys and protected beta/stable feeds. Signing readiness, immutable release, clean installation, installed update, legacy retirement and explicit UAT acceptance are distinct outcomes.
6. AWA owns generic policy matching; dev owns concrete host literals and deployment compatibility; Skills ultimately owns discovery only. AWA release/pin/runtime, concrete dev policy and the verified ShadowSync consumer are prerequisites for installed activation. Never bypass them by removing policy or using a copied fallback matcher.

## Prospective adoption of retained behavior

Adopt from this date the six behavior rules described in draft ADR 0005: preview is not mutation authority; checked-out targets may use bounded unknown-relation preview but must freshly classify before mutation; target/worktree evidence is operation-scoped; session evidence never substitutes for mutation revalidation; completed historical reports are independent read-only owners; and repository/action outcomes remain stable, bounded and derived from durable evidence. Retain the currently observed implementation of these six rules as the behavior baseline, subject to the verification and open-UAT gates in the extraction plan. No other requirement of the draft v0.6 plan is adopted by this record. This is prospective authority, not a claim that ADR 0005 or the v0.6 plan was historically accepted. Their bytes and DRAFT index status remain unchanged.

All other ADR 0004 repository-identity, explicit canonical-root, Git-safety, bounded-repair, retention, destructive-selection and evidence requirements remain effective. This extraction expands no cleanup permission and introduces no unrelated UI redesign.

## Why

The accepted product needs independent signing, notarization, updates and release traceability without a Skills checkout/compiler at installation time. A reviewed snapshot avoids disclosure of unrelated private Skills history. Explicit versioned external interfaces preserve the AWA/dev authority boundary. A full identity migration avoids retaining two operational applications or permanent legacy state/lock namespaces.

## Consequences

### Handoff and gates

Skills remains the implementation authority until the source snapshot, renamed runtime verification and destination governance/CI are proved. During export/handoff, the architect owns the source freeze; necessary source corrections are coordinated into both the frozen export receipt and destination before handoff, never divergent product development. The cutover receipt names the exact final source/destination revisions and digests. Thereafter only shadow-sync accepts implementation changes; Skills becomes discovery-only with a bounded non-installing compatibility entry.

Installed build 14 is not activated by this decision. Source export, CI and synthetic preparation may proceed while the external safety chain is unfinished. A public export is gated by sanitized-manifest review. Installation/release/promotion require their named evidence and approval gates. Legacy retirement requires at least two verified standalone releases and 90 days plus a separate retirement receipt. No last rollback copy or user data is deleted by extraction.

### Documentation transaction and compatibility

This successor and the accepted plan are introduced through a single explicitly approved legacy documentation exception, validated structurally and delivered by the normal Skills source PR. It does not enroll Skills in doc-warden v2, forge consent/receipts, change frozen historical bytes, or authorize future semantic edits. Only the two new semantic documents and their two indexes are in this transaction. Destination ADRs remain to be adopted through the new repository’s born-v2 workflow.

### Recovery

Before public export, correct the unpublished snapshot. After publication, disclose any export incident and use corrective commits; publication cannot be undone by deleting history. Before installed readiness commit, recover the verified legacy application/state only to a stopped state. After new-version work, repair forward unless state-format downgrade compatibility is proved. Any material scope or authority change requires a successor record.
