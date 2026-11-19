# operator-voice — Global Capability Binding (snapshot shape)

**Global Capability Binding (GCB) to a Standalone System Package (SSP), Flavor-2, `shape:
snapshot`.** Operator Voice Toolkit (OVT) is one self-contained product that lives in its own
private repo, `KleinPerkins/operator-voice`. Unlike [`global/tools/awa`](../awa) (`shape:
release-descriptor`, which clones its SSP repo at install time), this shelf carries the ACTUAL
runtime bytes in [`payload/`](payload/) — a deterministic, personal-data-free snapshot of
`operator_voice`'s source tree at `meta.yml`'s `provenance_ref`. That is what lets a machine with
**no access to the private SSP repo** install a working OVT runtime from this shelf alone — the
whole point of an embedded-bytes snapshot rather than a clone pointer.

## Two contracts, one product

- **SSP** — `KleinPerkins/operator-voice` is complete on its own: `git clone … && ./install.sh`
  builds the same payload from the checkout and installs it.
- **GCB (this shelf)** — `install.sh` here skips the clone entirely and installs directly from the
  embedded `payload/` directory. Both paths converge on the identical `version`+`digest` receipt
  for the same release content (build plan §13 M1 acceptance: "two independent distributors
  converge to the same receipt") — proved by this repo's own hermetic distributor-fixture tests
  plus a real run of each install path in `KleinPerkins/operator-voice`'s test suite.

## Scope and current status

- **`scope: global` from M1**: OVT carries `scope: global` in this shelf's `meta.yml` (build plan
  §8.1, decision D22). As of M5-B this shelf's release/receipt contract is GA and the WF1 registry
  record (`personal/ecosystem-orchestrator/config/registry.yml`) is `enrolled` — see that repo's
  own registry entry for the live enrollment reason/digest, never mirrored here to avoid a second,
  driftable copy of the same fact.
- **This shelf performs no downstream governed-repo write of any kind.** This shelf existing, and
  this `install.sh` working on a home machine, is NOT enrollment. The *only* route from here to an
  installed OVT in any other governed repository is, at every milestone with no exception: this
  binding → WF1 registry/reconcile/lockkit → WF2 orchestrator sync → that repository's own
  data-plane manifest → that repository's own generic `kind: tool` install/repair reconciler
  already invoked by its own sync/bootstrap path. There is no bespoke OVT vendoring, no direct
  write into any downstream repository's control plane, and no parallel installer channel — see
  `operator-voice-toolkit-build-plan.md` in `KleinPerkins/dev` for the full ecosystem-integration
  decision record.

## What `install.sh` does

```bash
install.sh              # install from the embedded payload (idempotent; default)
install.sh --repair      # verify/replace the runtime payload only (never config/state/keys)
install.sh --doctor      # read-only health check
install.sh --check       # CI-safe static preflight: verifies payload/payload-manifest.json's
                          # digest matches meta.yml's payload_digest AND the on-disk payload
                          # (no network, no writes)
install.sh --uninstall   # remove the venv/runtime/wrapper/skill; profile data+keys untouched
```

All paths are `HOME` / `XDG_*`-relative:

```
${XDG_DATA_HOME:-$HOME/.local/share}/operator-voice/venv                  runtime deps (cryptography, mcp)
${XDG_DATA_HOME:-$HOME/.local/share}/operator-voice/runtime/current       the active installed slot
${XDG_STATE_HOME:-$HOME/.local/state}/operator-voice/install-receipt.json version+digest receipt
~/.local/bin/operator-voice                                               CLI wrapper
```

## Keeping the embedded payload current

`payload/` is a point-in-time snapshot, not a live pointer. When `KleinPerkins/operator-voice`
ships a new release intended for this binding, regenerate it from that checkout:

```python
from pathlib import Path
from operator_voice.runtime.payload import build_portable_payload
build_portable_payload(Path("src/operator_voice"), Path("<this-shelf>/payload"), version="<new-version>")
```

then update `meta.yml`'s `provenance_ref`/`payload_digest`/`payload_version` to match, and run
`.github/scripts/eco-lock.sh write` in this repo.
