# Charter provenance

The swarm must **never dispatch an orchestrator-authored charter that was not
produced in conjunction with the `/prompt-architect` skill**
(SKILL.md §10). This file makes that coupling **checkable, not aspirational**: it
records the `/prompt-architect` framework and version behind every committed
template. The provenance lint asserts that every dispatched charter traces to one
of the template ids below **or** to a recorded runtime `/prompt-architect`
invocation (Deep/Critical only). A hand-authored charter with neither fails.

- **`/prompt-architect` source version:** `3.2.2` (pin `v3.2.2`;
  `source_provenance: ckelsoe/prompt-architect`).
- **Frameworks used:**
  - **RISEN** — Role, Instructions, Steps, End-goal, Narrowing —
    `.cursor/skills/prompt-architect/references/frameworks/risen.md`. The default
    for reviewer charters (review is a stepwise methodology with boundaries).
  - **TIDD-EC** — Task, Instructions, Do, Don't, Examples, Context —
    `.cursor/skills/prompt-architect/references/frameworks/tidd-ec.md`. Layered as
    an explicit Do/Don't block where crisp positive/negative constraints
    materially reduce review error (protected-axis and compliance focus areas,
    plus the probe and verifier).

## Template registry

| Template id | Role | focus_area | Framework(s) | PA version |
|---|---|---|---|---|
| `probe` | swarm-probe | — (recon) | RISEN + TIDD-EC | 3.2.2 |
| `verifier` | swarm-verifier | (adjudication) | RISEN + TIDD-EC | 3.2.2 |
| `security-authz` | swarm-reviewer | security | RISEN + TIDD-EC | 3.2.2 |
| `privacy-secrets` | swarm-reviewer | privacy | RISEN + TIDD-EC | 3.2.2 |
| `data-integrity-migration` | swarm-reviewer | data-integrity | RISEN + TIDD-EC | 3.2.2 |
| `concurrency-ordering` | swarm-reviewer | concurrency | RISEN + TIDD-EC | 3.2.2 |
| `api-contract-compat` | swarm-reviewer | api-contract | RISEN + TIDD-EC | 3.2.2 |
| `policy-governance` | swarm-reviewer | policy | RISEN + TIDD-EC | 3.2.2 |
| `reliability-failure` | swarm-reviewer | reliability | RISEN | 3.2.2 |
| `performance` | swarm-reviewer | performance | RISEN | 3.2.2 |
| `architecture-maintainability` | swarm-reviewer | architecture | RISEN | 3.2.2 |
| `testing-evidence` | swarm-reviewer | testing | RISEN | 3.2.2 |
| `generic-surface` | swarm-reviewer | generic | RISEN | 3.2.2 |

Thirteen committed templates: `probe`, `verifier`, and eleven per-focus-area
reviewer templates. Each template file carries its attribution in its header
comment. The shared shapes are **single-sourced in `../protocol.md`** and pulled
in by substitution, never re-copied: every reviewer template and `verifier` carry
`{{finding_contract}}` (§Conformed finding + §Risk and priority) and `probe`
carries `{{probe_schema}}` (§Probe output).

Two non-template support files live alongside the thirteen templates and are
**not** registry entries:

- `SKELETON.md` — the shared reviewer RISEN scaffold. Each of the eleven reviewer
  templates is this skeleton composed with that file's per-focus delta (its
  unique ROLE / INSTRUCTIONS / STEPS / DO-DON'T / NARROWING), so no reviewer
  re-copies the scaffold, the finding contract, or the caps. `probe` and
  `verifier` are standalone (not skeleton-composed).
- `INDEX.md` — the compact `focus_area → charter file` map, so only the probe's
  surfaced charters load (1–4 of 13), never all of them.

## Why the split

- **RISEN everywhere** because a charter is a *methodology with boundaries*: a
  Role, guiding Instructions, ordered Steps, an End-goal (the exact return
  shape), and Narrowing (what is out of scope). This is precisely RISEN's stated
  best fit — complex, multi-step tasks where defining what NOT to do matters.
- **+ TIDD-EC** on the six error-prone charters (`security-authz`,
  `privacy-secrets`, `data-integrity-migration`, `concurrency-ordering`,
  `api-contract-compat`, `policy-governance`) and on `probe`/`verifier`, because
  those are exactly the domains where explicit, separated **Do / Don't** lists
  prevent the classic false-positive / false-negative and scope-bleed errors —
  TIDD-EC's documented strength.

## Runtime provenance (Deep/Critical only)

When SKILL.md §10 authorizes a runtime `/prompt-architect` invocation to tailor a
critical or novel charter, the orchestrator records, alongside the run: the base
template id, the `/prompt-architect` framework used, version `3.2.2`, and a
one-line note on what was tailored. That record satisfies the provenance lint the
same way a committed template id does.
