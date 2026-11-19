# App-server stdio routing source evidence

Disposition: **source implementation; native routing UNQUALIFIED**. No native
model action or stdio app-server session was started. No profile/model/error/ack
mapping is adopted, and `app-server-bindings.json` intentionally has no profiles.
The qualified desktop/legacy Cursor routing files remain byte-identical.

The [caller contract](../../../global/rules/subagent-orchestration/APP-SERVER-DISPATCH.md)
defines closed v2 input, profile, evidence, planning and lifecycle records.
The [separate canary runbook](../../runbooks/app-server-stdio-routing-canary.md)
binds the future operation and lists the actual missing native proof. The accepted
integration/Skills authorities are unchanged; ordinary source delivery adds no
new human approval gate. Broader support/parity, preference changes or weakened
qualification would be separate semantic changes.

`host-inventory.json` records read-only embedded-binary/schema inspection on
2026-10-31. Its protocol hash is SHA-256 of compact sorted UTF-8 JSON mapping every
relative generated JSON filename to its byte SHA-256 (no trailing newline).
The package entrypoint is a shell launcher; inventory records its hash separately
from the resolved Mach-O server executable. Repeating schema generation directly
with that executable produced all 320 byte-identical JSON files. Generating schemas
completed with a PATH-alias permission warning, which did not
prevent schema output. This is field-shape evidence only, not actual runtime
provider, native offer, non-persistence, model identity or cleanup qualification.
No host trust/configuration change was requested or made by this work.

MOD-01/02 verification is reproducible:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s global/rules/subagent-orchestration/tests -p 'test_*.py'
bash .github/scripts/verify-skills.sh
python3 global/rules/subagent-orchestration/native_dispatch.py source-digest
python3 global/rules/subagent-orchestration/app_server_dispatch.py source-digest
```

The fixtures cover exact surface/source/build/profile/instance/freshness/pagination,
policy/tier/force/provider/fixed-mode behavior, closed parser/no-echo limits,
bounded fallback and repair, pending/started/terminal correlation, ambiguous
acceptance, reroutes, acknowledgement limits and cleanup. Native model/error/ack
provenance remains absent even when fixture tests pass. Final source review and
exact delivered revision/checks are reported in the delivery PR.

V1 continuity anchor: source digest
`2e355af2666b52a56d7dd8d19c3c925dcede36b666b9c0a15426b8f9bb546ed2`
at qualified revision `4c22951ec6c5bc5421accf3c7f1d5b5a78aa36da`.
The separate v2 digest includes its contract and source registry and expires on
any relevant file or profile change. Existing active pins are not updated.
