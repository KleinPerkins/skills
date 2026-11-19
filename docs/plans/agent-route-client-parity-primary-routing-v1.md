# Agent-route client parity — expose Claude/Codex and prefer primary checkouts

**Version:** v1
**Status:** ACCEPTED — 2026-08-19
**Date:** 2026-08-19
**Owning repository:** `KleinPerkins/skills` (`~/dev/capabilities/skills`)
**Plan-type:** standard
**Review provenance:** Operator-authorized Skills-owned planning step, grounded against live Skills
`main` at `28bcaadeebcee80a891df897928971d0635e8bfd`, accepted Context Efficiency Program v2
at live Dev `main` `9395b3fe1ee6e466ea1474e2eb12c8963224ed7b` (program blob
`d452a49a1f4e0eac579947a9a853637138966706`), the current `agent-route` source/tests, isolated
bootstrap contracts, and read-only live client/ranking probes. Bugbot reported no findings; the
full Skills verifier passed and doc-warden classified this plan/index conformant before acceptance.
No implementation, client reconciliation, E-09 run, private-content access, or scheduled-writer
activation occurred.

**Goal:** Make `agent-route` discoverable and usable from fresh Cursor, Claude, and Codex clients,
while making a repository's primary checkout the default cross-repo routing result instead of one
of its incidental linked worktrees.
**Architecture:** Expand the existing metadata-owned exposure to all three clients, then use generic
Git worktree identity to collapse same-repository checkouts for route ranking and verdicts. Keep the
primary checkout as the default representative, retain linked checkouts as explicit alternatives,
and preserve fail-open behavior when Git identity cannot be read.
**Tech stack:** `kp-capability/v1` metadata, Bash bootstrap fixtures, Python standard library, Git
worktree metadata, the existing `agent-route` registry/index, and runnerless Skills verification.

---

## Global constraints

- This PR is planning-only. Plan acceptance is not implementation GO and authorizes no source,
  metadata-lock, HOME/XDG, client, hook, launchd, CPP, Dev evidence, or scheduled-job mutation.
- Do not run E-09, create an E-09 receipt/manifest, or represent any test below as E-09 evidence.
- Do not re-enable, invoke, or modify any scheduled writer.
- Use only generic Git/worktree behavior in shipped code and fixtures. No real repository name,
  operator path, private content, learned data, transcript, or CPP token may enter `global/` or
  `local/`.
- Keep `meta.yml` as the sole client-exposure source and `.eco-registry.lock` as generated metadata
  parity. Do not add an installer channel, exposure registry, router, daemon, or runtime.
- Keep `agent-route` route-only. It may choose or report a workspace; it must not clone, create,
  delete, clean, rebase, or otherwise manage worktrees.
- Preserve explicit linked-worktree access: a linked checkout that is the only scored/available
  checkout remains routable, and linked alternatives remain visible for an operator request that
  names one.
- Preserve current scoring weights and the existing semantic re-rank escape hatch. This plan does
  not tune global weights or consume operator feedback.
- Use synthetic temporary repositories and isolated HOME/state for implementation tests. No test
  may read or write the operator's real `~/.agent-route`, client projections, or work repos.
- The existing `agent-route` feedback-loop plan/ADR remain separate drafts. Do not merge, revise,
  implement, or depend on them here.
- The reviewer App alone approves and arms native auto-merge. Agents must not approve, merge, arm
  auto-merge, or admin-bypass a failed check/comment.

## 1. Authority and verified current state

| Authority | Exact binding | Relevant fact |
|---|---|---|
| Skills owner source | `KleinPerkins/skills` `main` at `28bcaadeebcee80a891df897928971d0635e8bfd` | Live remote main; implementation base and rollback ref |
| Context Efficiency Program v2 | `KleinPerkins/dev` `main` at `9395b3fe1ee6e466ea1474e2eb12c8963224ed7b`; program blob `d452a49a1f4e0eac579947a9a853637138966706` | E-09 remains last and requires applicable owner/client prerequisites green; the program does not authorize this implementation or E-09 |
| Skills E-01 plan | `docs/plans/context-efficiency-e01-durable-skills-source-v1.md`, accepted on Skills main | Fresh eligible client evidence must use the durable Skills primary; source tests do not substitute for fresh-client evidence |
| Exposure authority | `bootstrap.sh` and `global/skills/agent-route/meta.yml` | `meta.yml` `expose:` is the sole per-client source; bootstrap already supports `cursor`, `claude`, and `codex` |
| Routing authority | `global/skills/agent-route/{lib,scripts,tests}` | Discovery includes linked worktrees; route order is currently raw score then path |

Fresh read-only probes at authoring time established:

- `global/skills/agent-route/meta.yml` declares `expose: cursor`.
- The durable source is linked at `~/.cursor/skills/agent-route`; the corresponding Claude and
  Codex paths are absent.
- `bootstrap.sh` already interprets `expose: cursor claude codex`; no bootstrap behavior change is
  needed to add these links.
- `SKILL.md` still hard-codes the Cursor projection path and Cursor app-control move mechanism, so
  exposure alone would leave Claude/Codex instructions incomplete.
- `lib/discover.py` intentionally discovers Git worktrees as routable roots.
- `lib/context_mine.py` derives path keywords/aliases but records no primary-vs-linked checkout
  identity.
- `scripts/agent_route.py::route_task()` sorts all scored roots by `(-score, path)` and computes the
  verdict from that undeduplicated list.
- A read-only route against the current fresh index returned three linked checkouts at score `167`
  ahead of the primary checkout at score `159`; the same-repository duplicates also forced a weak
  verdict. Git reported the primary and linked paths under one common directory.
- The existing unit/regression suite has no primary-preference case, and the repository verifier
  does not directly make `agent-route`'s own `make verify` a required job.
- The existing `agent-route-feedback-loop-v1.md` is unrelated and remains DRAFT. Current doc-warden
  overall status is already non-zero only because that pre-existing draft lacks the current
  `Plan-type` marker; this new plan must be independently `CONFORMANT`.

Implementation must refresh both live authority refs before editing. A material change to exposure
semantics, route result shape, worktree discovery, owner verification, or program sequencing requires
plan re-adjudication; do not silently widen this plan.

## 2. Scope and non-goals

### In scope

1. Change `agent-route` exposure from Cursor-only to Cursor/Claude/Codex through its existing
   `meta.yml`, then regenerate only the canonical metadata-lock row.
2. Make `SKILL.md` and `README.md` client-neutral: invoke the current client's installed projection,
   use the client's supported root/cwd transition, and never claim a move without observing the new
   root.
3. Mine generic Git checkout identity (`primary`, `linked`, or `unknown`) plus one same-repository
   grouping key without persisting a new authority.
4. Rank and calculate verdicts from one representative per Git repository: an existing scored
   primary is the default representative; otherwise the best existing linked checkout remains the
   representative. Surface same-repository linked checkouts as alternatives rather than independent
   competitors.
5. Add biting exposure, checkout-classification, ranking, fallback, fail-open, and verifier coverage.
6. After a separately authorized implementation merge and machine reconcile, run only the affected
   fresh-client canaries and hand content-safe results to the Dev program owner.

### Non-goals

- Implementing adaptive feedback, changing the feedback draft/ADR, or tuning any score constant.
- Hard-coding one repository, organization, home path, worktree directory, or client installation.
- Removing worktree discovery, hiding a specifically requested linked checkout, or managing Git
  branches/worktrees.
- Changing `bootstrap.sh` exposure semantics, adding client-specific copies, or adding another
  registry/installer.
- Changing CPP source/control-plane files, Dev program/evidence files, AWA, generated memory, or
  private operator state.
- Changing the Context Efficiency Program, assigning a new E-number, freezing a denominator, or
  running any E-09 command.
- Re-enabling or exercising a scheduled writer.
- Bundling a live HOME reconcile or fresh-client process into the implementation PR.

## 3. Design contract

### 3.1 Client exposure and instructions

Set `global/skills/agent-route/meta.yml` to:

```yaml
expose: cursor claude codex
```

Regenerate `.eco-registry.lock` only through `.github/scripts/eco-lock.sh write`; do not hand-edit
its agent-route digest. `bootstrap.sh` remains byte-identical because it already owns metadata-driven
client links.

Update `SKILL.md`/`README.md` so:

- examples resolve through the current client's `~/.cursor`, `~/.claude`, or `~/.codex` projection;
- Cursor retains the current app-control move and next-turn workspace-signal verification;
- Claude/Codex use their native supported root/cwd transition when available;
- any client without a supported transition reports the selected path and required operator action
  instead of claiming success;
- transport errors remain inconclusive and the route engine remains fail-open.

### 3.2 Generic checkout identity

Add one read-only helper in `lib/context_mine.py` that returns:

```text
checkout_kind: primary | linked | unknown
git_common_dir: canonical absolute Git common-directory path or ""
primary_abs_path: canonical primary worktree path or ""
```

Derive these fields only from local Git metadata. A primary has its own common directory; a linked
checkout points into that common directory's worktree metadata. The first valid `worktree` row from
`git worktree list --porcelain` supplies the primary path. Any timeout, malformed output, missing
path, or Git error yields `unknown`/empty fields without raising.

`mine_root()` emits these machine-local fields at the existing top level. Existing
`build_registry()`/`build_index()` dictionary propagation should carry them without a schema
migration; if that assumption fails, stop and revise the exact file map rather than adding
parallel state.

### 3.3 Repository representative selection

In `scripts/agent_route.py`, group positive existing candidates by non-empty canonical
`git_common_dir`; candidates without one use their own absolute path as a unique fail-open group.
For each group:

1. choose the scored, existing `checkout_kind: primary` candidate when present;
2. otherwise choose the group's highest-scoring existing candidate;
3. retain non-representative checkouts as bounded alternatives with their existing path, score, and
   rationale;
4. sort repository representatives by the existing score/path order; and
5. compute `strong`/`weak`/`none` from representatives only, so same-repository worktrees cannot
   manufacture a weak margin.

This preference does not add score weight. A task that matches only a linked checkout still routes
there because no positive primary candidate enters that group. The semantic re-rank step may choose
a surfaced linked alternative when the operator explicitly names it.

Old indexes that lack checkout fields must remain valid and retain today's per-path behavior until
the next normal discovery. The post-merge machine step runs `discover --full` before canaries.

## 4. Exact implementation boundary

Expected modified files:

```text
.eco-registry.lock
.github/scripts/verify-skills.sh
global/skills/agent-route/README.md
global/skills/agent-route/SKILL.md
global/skills/agent-route/lib/context_mine.py
global/skills/agent-route/meta.yml
global/skills/agent-route/scripts/agent_route.py
global/skills/agent-route/tests/regression_selftest.sh
global/skills/agent-route/tests/unit_test.py
global/skills/swarm/tests/test_bootstrap.sh
```

Expected unchanged surfaces include `bootstrap.sh`, `lib/discover.py`, `lib/index_build.py`,
`lib/score.py`, the feedback-loop plan/ADR, every other capability metadata row, registry enrollment,
PR-automation recipes/locks, CPP, Dev, AWA, real HOME/XDG state, and every scheduled writer.

If another tracked file is required, stop and revise this plan before adding it. The only exception
is dropping a listed file after a red test proves it is unnecessary.

## 5. Work items

### 5.1 Write the red exposure and routing fixtures

- Extend `global/skills/swarm/tests/test_bootstrap.sh` to require the isolated durable
  `agent-route` source at all three client skill paths and invoke the same harmless route fixture
  through each path.
- Add neutral temporary Git primary/linked-worktree fixtures under the existing temp root; no real
  workspace names or paths.
- Add unit/regression cases for primary/linked/unknown classification, primary representative,
  same-repository verdict deduplication, linked-only fallback, separate clones not being collapsed,
  stale/missing primary, and old-index fail-open behavior.
- Wire `make -C global/skills/agent-route verify` into `.github/scripts/verify-skills.sh` as a
  required failure, not a suppressed installer warning.
- Prove the new focused slices fail on the untouched baseline for the intended reasons: absent
  Claude/Codex links, no checkout fields, linked checkout ranked first, and duplicates weakening
  the verdict.

### 5.2 Implement the minimum exposure and representative logic

- Change only the exposure field and regenerate the metadata lock through the canonical writer.
- Add the read-only checkout helper and top-level mined fields.
- Add repository grouping/representative selection without touching scoring constants.
- Update only the client-specific instructions made stale by exposure.
- Keep output deterministic: alternatives and representatives use stable score/path ordering.
- Re-run the red slices after each logical change and require green.

### 5.3 Prove owner-repository closure

Run:

```bash
python3 global/skills/agent-route/tests/unit_test.py
bash global/skills/agent-route/tests/regression_selftest.sh
make -C global/skills/agent-route verify
bash global/skills/swarm/tests/test_bootstrap.sh
bash .github/scripts/eco-lock.sh check
bash .github/scripts/verify-skills.sh
"${HOME}/dev/_ops/bin/doc-warden.sh" check "$(git rev-parse --show-toplevel)"
git diff --check
```

The new plan/implementation must add no doc-warden finding. Record the pre-existing feedback-plan
drift separately from candidate-owned results. Compare base/head verifier results if any unrelated
baseline failure appears.

Open the implementation PR as draft, run Bugbot, fix applicable in-scope findings, run
verification-before-completion, then mark ready. The reviewer App alone may approve/arm merge.

### 5.4 Reconcile and collect fresh-client canaries only after separate machine GO

After implementation protected-merges, present the exact merged commit and:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile --dry-run
```

Apply only after an explicit machine-local GO. Then require:

1. all three client links resolve to the durable Skills primary;
2. a second reconcile is converged/idempotent;
3. `agent-route discover --full` succeeds without private output being persisted to Git/chat;
4. fresh Cursor, Claude, and Codex sessions started outside the target repository discover
   `agent-route` from the approved source;
5. each client routes the same ordinary cross-repo request to the primary checkout, not a linked
   alternative, and verifies the actual active root/cwd before claiming success; and
6. the content-safe handoff records only client/root class, merged owner ref, source/install
   digests, result, checkout class, rollback ref, and current product-constraint reason for any
   ineligible row.

These are prerequisite canaries, not E-09. Do not run an E-09 validator, measurement, receipt,
manifest, private-data step, or scheduled writer.

## 6. Acceptance criteria

- `agent-route` is metadata-exposed to exactly Cursor, Claude, and Codex; bootstrap remains the
  sole local projection path and its generic implementation is unchanged.
- Isolated bootstrap creates durable-primary links for all three clients and route invocation
  through each link is behaviorally equivalent.
- Generic worktree identity is read-only, portable, deterministic, and fail-open.
- For a synthetic repository with a positive primary plus linked checkouts, the primary is the
  route representative and same-repository alternates do not weaken the verdict.
- When the primary is absent/unscored, an existing scored linked checkout remains routable.
- Distinct clones/common directories remain distinct candidates; no remote-origin-only collapsing.
- No scoring weight, feedback data, enrollment authority, or new persisted store is added.
- The protected Skills verifier directly runs the complete agent-route regression suite.
- The exact implementation file set stays within §4, lock parity is generated, and all
  candidate-owned focused/full/remote gates and comments are green.
- No private content or real operator path appears in tracked fixtures, PR evidence, or chat.
- No E-09 action or scheduled-writer action occurs.
- After this plan is accepted, implementation still waits for a separate explicit GO; after
  implementation merge, real-machine reconciliation still waits for another exact GO.

## 7. Rollback and stop conditions

### Plan rollback

Before merge, close the PR or revert its two documentation files. After acceptance, this plan is
byte-immutable; a material correction requires `agent-route-client-parity-primary-routing-v2.md`
with a `Supersedes:` pointer and index update.

### Implementation rollback

Before implementation merge, close or governed-revert the candidate. After merge, use an ordinary
revert PR, regenerate `.eco-registry.lock` from the restored metadata, run the full owner verifier,
and reconcile from the restored durable Skills commit only after machine authorization. Refreshing
the index removes additive checkout fields; old-index fail-open behavior requires no migration.
A rollback intentionally removes Claude/Codex exposure and re-blocks the affected fresh-client
evidence until a corrected implementation lands.

### Stop conditions

Stop before implementation commit/push/PR, machine write, or client canary if:

- either live authority binding drifts materially;
- a solution requires hard-coded CPP/operator/client paths, global score tuning, or feedback-loop
  implementation;
- primary preference cannot preserve linked-only routing and deterministic fail-open behavior;
- checkout identity requires network access, a new registry/schema authority, or worktree mutation;
- tests require real HOME, real work repositories, private content, or non-temporary state;
- `bootstrap.sh`, `lib/score.py`, `lib/discover.py`, `lib/index_build.py`, PR automation, or another
  file outside §4 would need a semantic change;
- zero-link, metadata-lock parity, description eligibility, Bugbot, or any candidate-owned
  local/remote gate remains red;
- reviewer comments remain unresolved or normal runnerless automation cannot merge without bypass;
- implementation GO or later machine-local GO is absent; or
- any step would run E-09 or re-enable/invoke a scheduled writer.

Protected merge accepts only this Skills-owned design. The exact next step is a separate
implementation GO to create a fresh safe workspace from live Skills main and execute §§3–6 without
touching real client state.
