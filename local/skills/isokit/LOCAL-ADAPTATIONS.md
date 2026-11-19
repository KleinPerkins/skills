# Local adaptations

This is a reviewed Flavor-2 snapshot of
`github.com/aadilghani1/isokit@e25dfc82681628dfb5240cddc9f07081042fe348`.

## Copied upstream source

- `skills/isokit/` was copied into this capability root.
- `examples/demo/src/figures/` was retained as the compact example-figure source
  library used by the skill's “nearest example” instruction.
- `LICENSE` and `NOTICE.md` were retained verbatim.

Except for the routing and launch-diagnostic changes below, copied upstream
files remain byte-identical to the pinned commit.

## Local changes

- `SKILL.md` has a shorter, differentiated routing description below the
  repository's 300-character warning threshold. It remains specific to
  pressable React isometric objects whose controls produce state, output, or
  optional sound.
- `scripts/shoot.mjs` preserves the error from each failed browser launch and
  replaces upstream's automatic-download suggestion with the explicit boundary
  that a Playwright browser bundle requires operator approval.
- `package.json` and `package-lock.json` pin only
  `playwright-core@1.64.1`, matching the reviewed upstream lock.
- `install.sh` idempotently exposes the skill to Cursor, Claude, and Codex and
  runs `npm ci` with lifecycle scripts and browser downloads disabled when the
  exact, importable Playwright runtime is absent or incomplete. Exposure is
  preflighted so a real-path collision fails before runtime provisioning or any
  new tool link. When the repository bootstrap sets
  `KP_BOOTSTRAP_MANAGES_EXPOSURE=1`, the installer provisions only the runtime;
  bootstrap owns the single journaled publication transaction.
- `meta.yml`, this file, and the bounded package files are local governance
  additions.

`react-isokit` is intentionally not installed here. A consuming React project
must declare that application dependency in its own package manifest.

## Verification environments

The runnerless `stdlib-shell.v1` image has no Node.js. The portable installer
suite uses explicit npm and runtime doubles to exercise failure propagation,
link publication, collision handling, and missing-Node behavior.
`TestNodeIntegration` repeats these checks with actual JavaScript module imports
and tests browser-launch diagnostics on Node-equipped hosts; it reports explicit
skips when Node is absent. Run the full suite locally before delivery so the
real module/API checks are covered without changing the governed sandbox image.
