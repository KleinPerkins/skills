# Native Codex named roles for GSD authoring

This lane covers observation of a named role in an owned, read-only Codex
app-server stdio process for Doc-Warden's GSD 1.11.0 authoring. The ordinary
worker dispatcher and generic app-server registry are independent. This module
does not start Codex, install roles, or grant operation consent. A deployment
must bind and qualify its exact SDK file, destination, Codex build, process
configuration, package and execution scope.

## Caller responsibilities

- Verify the resolved Codex binary and the sealed package and role inventory.
  Pass the actual version, digests, role configuration bytes and the absolute
  bundle directory to `verify_role_input`. The emitter inserts the destination
  in the TOML. Normalize only that exact delimited bundle prefix for the
  content pin. Preserve the raw role digest as evidence of the loaded file.
- Measure the native `collaboration.spawn_agent` selector with the same binary
  and process configuration. Pass the observed `spawn_agent` function from
  that namespace to `verify_spawn_offer`. Missing selector, wrong namespace,
  renamed role or changed schema stop the caller. No ordinary-role fallback.
- Start a fresh ephemeral parent at the approved isolated root with read-only
  and network-denied permissions. Bind the measured configuration directly to
  the process using absolute package-owned entries. The host is accountable
  for isolation, pinned runtime resolution, fresh context and child cleanup.
  Use only the measured model and effort. An offered selector is discovery
  evidence. A completed child must establish the actual named role.
- Call `observe_role` using live events and the actual thread responses from
  the single owned process. Supply the parent start response, parent turn ID,
  completed item and turn notifications, and the direct child read response.
  The decoder requires a completed child turn, a child result for the same
  role, checked model and effort, and a terminal parent. Permission callbacks,
  a foreign child, an incomplete turn, or a parent echo without a child
  message cause refusal. Do not accept files or caller-supplied event JSON as
  native evidence. Cancel and reap the process on either success or refusal.
- Keep the actual report in the caller's private state. `Observation.evidence`
  contains only the pinned source identities, role, actual selection,
  terminal checker verdict and report digest. The result carries no apply
  authority. Doc-Warden separately checks the exact draft, report, current
  plan and operation consent under its own contract.

The observed read-only profile covers the nine package-owned roles reached by
the four authoring skills: advisor researcher, Nyquist auditor, pattern mapper,
phase researcher, plan checker, planner, project researcher, research
synthesizer and roadmapper. The native checker also produced a real report used
in a disposable draft import. Identity canaries for the other roles establish
selection and completion only. A write-enabled profile, production activation,
additional Codex builds, and the four end-to-end skill journeys each require
their own evidence.
