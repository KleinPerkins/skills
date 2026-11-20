# continual-learning-consolidate

Standard-library consolidator for the machine-local global memory projection.
The runtime makes no Git, GitHub or network calls.

## Admission

1. `~/agent-learnings.md` is the explicit home seed; `~/AGENTS.md` is output-only.
2. `agent-route map --json` supplies candidate roots and local identity metadata.
3. A private accepted classification projection binds logical repository IDs to
   exact **active** primary/common-Git directory pairs. Paths and remote owners
   do not assign personal/work classification.
4. Excluded storage, unknown assignments and stale/unmatched bindings are skipped
   **before opening workspace memory**. Exclude all recovery/archive-only stores
   and retired roots explicitly, including aliases of an otherwise active ID.
5. Workspace memory needs two distinct accepted repository IDs and at least one
   personal source. Worktrees and equivalent clones share their accepted ID;
   normalized origins corroborate bindings and never create an assignment.
6. The existing conservative deduplication and final secret scanner gate a
   deterministic atomic replacement of `~/AGENTS.md`.

Invalid/missing/conflicting policy, discovery/parse failure, and scanner failure
leave the output unchanged. Unassigned discovered roots are reported as unknown,
never guessed personal. The explicit home seed retains its existing eligibility.
This repair does not inspect or clean up earlier projections.

## Private classification projection

Default: `~/.local/share/continual-learning-consolidate/classifications.json`.
`--classifications PATH` selects an explicit policy. Keep host paths, accepted
assignments and private continuity evidence out of source repositories and CI.
This is a derived consumer input, not a new classification authority.

The closed `memory-source-classification/v1` format requires all shown fields:

```json
{
  "schema": "memory-source-classification/v1",
  "excluded_paths": ["/opt/example/recovery", "/opt/example/retired-root"],
  "repositories": [{
    "repository_id": "accepted-example",
    "classification": "personal",
    "active_bindings": [{
      "primary_path": "/opt/example/active-repository",
      "git_common_dir": "/opt/example/active-repository/.git"
    }],
    "origin_aliases": ["https://github.com/example/repository.git"]
  }]
}
```

Classification is `personal`, `work` or `unknown`. A known accepted ID without a
validated active alias may have an empty `active_bindings` array; it admits no
memory. List independent active clone pairs under the same ID. Linked worktrees
match `primary_abs_path` plus `git_common_dir` from route metadata. Both values
must match one pair; no cross-product matching is allowed. Missing metadata or
observed origin disagreement makes that root unknown. Origin aliases are optional
corroboration; equivalent SSH/HTTPS/case/`.git` forms normalize consistently.

All local paths must be absolute and canonical, without symlinks, dot segments or
trailing slashes. Exclusions cover the named path and every descendant, including
root, primary and common-store metadata. Conflicting IDs, primary/common/origin
aliases, duplicate keys and unsupported fields/schema refuse the entire policy.
Continuity alone never makes preserved storage active. Refresh bindings after a
move or successor cutover using accepted identity evidence and local metadata;
never infer identity from a reused remote name.

## Install, qualify and schedule

```bash
bash install.sh --no-schedule \
  --policy /private/path/to/reviewed-classifications.json \
  --expected-policy-sha256 absent
```

For an existing policy, replace `absent` with its exact SHA-256 preimage. Preserve
that preimage privately for rollback. Policy replacement requires this guard;
without `--policy`, installation validates and retains the existing policy.
`--expected-current HASH|absent` optionally guards the runtime pointer as well.

The installer publishes under
`~/.local/share/continual-learning-consolidate/releases/`, records a manifest and
addresses **every Python dependency** (including policy validation and installer
support). It verifies reused releases, atomically replaces links and policy,
restores preimages on a local pointer failure, uses a local installation lock and
retains old releases. Policy bytes are separate private data with mode `0600`;
the JSON receipt binds their hash to the release digest. `current` and
`~/.local/bin/continual-learning-consolidate` point at the installed release.

`--no-schedule` performs no scheduler operation and does not run consolidation.
It preserves an existing paused job, its schedule and capture configuration.
Qualify the installed entrypoint using only a disposable synthetic `--home` and
fake `--agent-route`, with an explicit synthetic policy as needed. A dry run
still reads admitted memory; a real-home dry run is not an isolation test.

Only after installed-runtime qualification should the owner job tooling resume
the intended existing instance. The installer without `--no-schedule` retains an
existing command job unchanged or creates a missing daily **09:00** job, then
runs owner doctor. It never intentionally enables an existing paused instance.
Use the runtime-only form when preserving a different existing schedule.

## Rollback

Keep consolidation paused when installation or qualification fails. Retain the
previous runtime release, policy bytes/hash and pointer target; never overwrite
learned output or enable defective earlier code as part of rollback.

For releases produced by this installer, a guarded pointer rollback is:

```bash
bash install.sh --no-schedule --rollback-to PREVIOUS_RELEASE_DIGEST \
  --expected-current CURRENT_RELEASE_DIGEST
```

To restore a policy too, add `--policy PRESERVED_POLICY` and
`--expected-policy-sha256 CURRENT_POLICY_HASH`. Rollback verifies target release
bytes and refuses a changed current/policy preimage. Older releases without the
new manifest remain on disk for explicit recovery; they are not accepted by this
verification command. No rollback changes schedule or capture state.

## Verify

```bash
bash tests/run_tests.sh
```

Tests use generated synthetic data and child-only disposable homes. They cover
explicit assignment across misleading paths/owners, work linked worktrees,
logical clone deduplication, origin forms, unknown/stale identity before reads,
recovery/retired exclusions, malformed/conflicting policy, unchanged-output
failures, scanner warnings/blocks, idempotence, the route-only process boundary,
addressed dependency updates, installed-entrypoint execution, guarded policy
replacement, pointer failure restoration, corruption rejection and rollback.
