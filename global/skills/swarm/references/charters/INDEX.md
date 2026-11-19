# Charter index

Load **only** the charter(s) the probe's territories surface (1–4 of the 13),
never the whole set. Each key is a probe territory `focus_area` (the routing key
the probe emits, e.g. `security-authz`); it maps 1:1 to a charter file.

| focus_area (probe territory / routing key) | charter file | role |
|---|---|---|
| generic-surface | generic-surface.md | swarm-reviewer |
| api-contract-compat | api-contract-compat.md | swarm-reviewer |
| data-integrity-migration | data-integrity-migration.md | swarm-reviewer |
| security-authz | security-authz.md | swarm-reviewer |
| privacy-secrets | privacy-secrets.md | swarm-reviewer |
| reliability-failure | reliability-failure.md | swarm-reviewer |
| concurrency-ordering | concurrency-ordering.md | swarm-reviewer |
| performance | performance.md | swarm-reviewer |
| testing-evidence | testing-evidence.md | swarm-reviewer |
| architecture-maintainability | architecture-maintainability.md | swarm-reviewer |
| policy-governance | policy-governance.md | swarm-reviewer |
| probe | probe.md | swarm-probe |
| verifier | verifier.md | swarm-verifier |

Each **reviewer** charter is `SKELETON.md` (shared RISEN scaffold +
`{{finding_contract}}`) composed with that file's per-focus delta. `probe.md`
(carries `{{probe_schema}}` + the D01–D16 map) and `verifier.md` (carries
`{{finding_contract}}`) are standalone. Provenance for all thirteen templates is
in `PROVENANCE.md`; the shared shapes are single-sourced in
`../protocol.md`.

Note: the routing key above is the charter-name form the probe emits in
`territories[].focus_area`; each reviewer charter header's own `focus_area:`
field is the shorter finding-classification label (e.g. `security`), which is a
finer, pre-existing distinction — not a routing key.
