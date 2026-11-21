# Client adapters

Save-game uses one generic engine and a small, factual client registry in
`engine/adapters.py`. Client adapters describe discovery, invocation, manual compaction,
and optional hook capability. They never invoke compaction or claim that a client loaded
the skill.

## Cursor

- Configured discovery link: `~/.cursor/skills/save-game`
- Explicit invocation: `/save-game`
- Manual native compaction: `/summarize`
- Pre-compaction hook class: `observational_only`; it can observe but cannot block.
- Acceptance: **PASSED (2026-08-02)** — live discovery (slash-command autocomplete) and
  invocation (a real `flush → index → status` round trip) both confirmed. See `EVIDENCE.md`
  for the full canary record. The post-compaction resume/reconcile step (step 4 below) was not
  separately re-exercised.

## Claude Code

- Configured discovery link: `~/.claude/skills/save-game`
- Explicit invocation: `/save-game`
- Manual native compaction: `/compact`
- Pre-compaction hook class: `can_block`; a future optional hook can block through the
  client's explicit block decision.
- Acceptance: **discovery PASSED (2026-08-02)** — a live client probe confirmed `save-game` is
  loaded in the skill catalog. Invocation was not separately re-tested (the engine is
  client-agnostic and already proven via the Cursor canary). See `EVIDENCE.md`. Note: a probe
  that disables all tool access produces a false negative on skill enumeration — do not use
  that as a discovery test.

## Codex

- Configured compatibility link: `~/.codex/skills/save-game`
- Current documented user-skill location: `~/.agents/skills/save-game`
- Explicit invocation: `$save-game`
- Manual native compaction: `/compact`
- Pre-compaction hook class: `halt_only_no_block`; a future optional hook can halt through
  non-continuation but cannot use the other clients' block decision.
- Status: **exposed via legacy path, acceptance unverified — pending live discovery
  canary**. Do not claim Codex parity from the compatibility link alone, and do not create
  a save-game-only canonical-path workaround.

## Disk and engine doctors

From the skill directory:

```sh
./install.sh --doctor
python3 -m engine.doctor
python3 -m engine.doctor --json
```

`install.sh --doctor` is intentionally limited to the configured client links and their
resolution to this skill. It does not validate schema shape or run the engine.

The engine doctor reports `pass`, `fail`, or `unknown` for:

- all twelve expected schema files parsing as JSON and retaining the closed-object shape;
- clean imports of `engine/schemas_validate.py` and every top-level `engine/*.py` module;
- both `scripts/save-game.sh` and `python3 -m engine.cli` completing throwaway
  `flush`, `index`, `compact-check`, and `reconcile` runs;
- each configured discovery path being a current-user-owned symlink that resolves to this
  skill directory.

The doctor uses temporary state for runtime checks and does not write to the inspected
repository. A passing disk report proves prerequisites only. A client canary verifies
whether the running client discovers and invokes the skill.

## Observational resume integration

For an integration that needs strictly observational resume evidence, use
`save-game.sh --root <repository> reconcile --task-id <scope> --observe`.
This checks enabled adoption and takes a nonblocking shared lock on an existing
workstream. It returns `save-game-reconcile-observation/v1` with a bounded status
and opaque scope keys. Exit zero and `MATCH` include the current checkpoint ID,
canonical SHA-256 digest and generation. Other statuses exit one and carry no
checkpoint. A busy workstream, changed Git state, ambiguous evidence or an
unfinished write requires attention through the corresponding owner route.
The observation performs no recovery. Ordinary `reconcile` retains its existing
recovery behavior.

## Live-discovery canary

Run this manually for every client after installation. Use a fresh client session so its
skill catalog is not stale.

### Cursor canary

1. Start a new Cursor Agent chat and confirm `save-game` is offered as a slash skill.
2. Enter `/save-game save current progress without compacting`.
3. Confirm the response follows the save-game flow and gives a truthful save receipt.
4. When compaction is desired, type `/summarize` yourself. On the next turn, invoke
   `/save-game resume` and confirm Reconcile runs before mutation.

### Claude Code canary

1. Start a new Claude Code session and confirm `save-game` is available as a slash skill.
2. Enter `/save-game save current progress without compacting`.
3. Confirm the response follows the save-game flow and gives a truthful save receipt.
4. When compaction is desired, type `/compact` yourself. On the next turn, invoke
   `/save-game resume` and confirm Reconcile runs before mutation.

### Codex canary

1. Start a new Codex CLI session and run `/skills`.
2. Confirm `save-game` appears exactly once. If it is absent, Codex acceptance remains
   pending; the compatibility link is not proof of discovery.
3. Enter `$save-game save current progress without compacting`.
4. Confirm the response follows the save-game flow and gives a truthful save receipt.
5. When compaction is desired, type `/compact` yourself. On the next turn, enter
   `$save-game resume` and confirm Reconcile runs before mutation.

Record the client/version, discovery result, invocation result, and manual compaction
result. Printing a command, seeing a hook event, or passing either disk doctor is never
evidence that native compaction actually ran.
