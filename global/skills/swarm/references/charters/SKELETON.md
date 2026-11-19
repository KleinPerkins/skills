<!--
skeleton_id: reviewer-risen
role: swarm-reviewer
framework: RISEN (+ optional TIDD-EC Do/Don't) — prompt-architect 3.2.2
usage: shared reviewer scaffold; NOT a dispatchable template and NOT in the
  PROVENANCE template registry. Every reviewer charter = this skeleton + one
  per-focus delta file.
composition (design-time): load this skeleton + one delta (e.g.
  charters/security-authz.md); fill each [[slot]] from that delta's matching
  section; omit the [[dodont]] block when the delta is RISEN-only.
instantiation (runtime): the orchestrator then substitutes the {{vars}} below,
  filling {{finding_contract}} verbatim from references/protocol.md.
delimiters: [[...]] = design-time delta slot (from the per-focus file);
  {{...}} = runtime instantiation var (from the orchestrator).
substitution_vars: {{run_id}} {{charter_id}} {{candidate_identity}} {{assignment_id}} {{territory_id}} {{model_slug}} {{rigor_obligation}} {{territory}} {{surfaces}} {{dimensions}} {{evidence_pack}} {{neutral_flow_map}} {{evidence_supplied}} {{blind_to_probe}} {{omissions}} {{finding_contract}}
returns: conformed finding shape (references/protocol.md §Conformed finding)
-->

# Reviewer charter skeleton (shared RISEN scaffold)

The eleven reviewer charters share this scaffold; only the `[[slots]]` differ
between focus areas, so the shared structure lives here exactly once. The finding
contract is single-sourced: `{{finding_contract}}` is filled verbatim from
`references/protocol.md` (§Conformed finding + §Risk and priority), so no charter
re-copies the finding shape, caps, enums, or risk formula. **Load only the
surfaced charters (1–4 of the 13), never all of them** (`INDEX.md`).

To instantiate a reviewer: take this scaffold, replace each `[[slot]]` with the
matching section of the chosen per-focus delta (`charters/<focus_area>.md`), drop
the `[[dodont]]` line if that delta is RISEN-only, then substitute the `{{vars}}`.

```text
ROLE:
For run {{run_id}}, charter {{charter_id}}: you are [[role]]. You are read-only.
blind_to_probe = {{blind_to_probe}}.

ASSIGNMENT:
run_id = {{run_id}}
charter_id = {{charter_id}}
candidate_identity = {{candidate_identity}}
assignment_id = {{assignment_id}}
territory_id = {{territory_id}}
model_slug = {{model_slug}}
rigor_obligation = {{rigor_obligation}}
territory = {{territory}}
surfaces = {{surfaces}}
dimensions = {{dimensions}}
evidence_pack = {{evidence_pack}}
neutral_flow_map = {{neutral_flow_map}}
evidence_supplied = {{evidence_supplied}}
blind_to_probe = {{blind_to_probe}}
omissions = {{omissions}}
finding_contract = {{finding_contract}}

INSTRUCTIONS:
[[instructions]]
- Meet your rigor obligation: {{rigor_obligation}}.
- Inspect only the bounded sections in {{evidence_pack}} at
  {{candidate_identity}}. Use {{neutral_flow_map}} only to trace declared flow
  edges and overlap; it carries no probe conclusions.

STEPS:
[[steps]]

[[dodont]]

END GOAL:
Return exactly one JSON object and nothing else — the conformed finding shape
(references/protocol.md §Conformed finding), role = review, supplied in
`finding_contract` above.

NARROWING:
[[narrowing]]
- Use only {{evidence_supplied}}; name any further evidence need, never gather it.
```
