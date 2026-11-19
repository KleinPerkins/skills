# local-jobs

Self-contained, type-agnostic framework for managing local macOS `launchd` jobs.
The skill directory contains the runtime, handler ABI, generic job types,
dashboard data model, and hermetic test harness.

## What Ships Globally

- `bin/` and `lib/`: the generic CLI, scheduler, registry, store, launchd writer,
  event log, dashboard, and type-authoring chassis.
- `handlers/command.sh`: schedule arbitrary local commands.
- `handlers/incremental-git-fetch.sh` plus `backends/incremental-git-fetch/`:
  incremental filtered fetch for configured reference repositories.
- `config/registry.yml`: base registry with generic types only.
- `canvases/`: dashboard template + generated canvas and
  `canvases/README.md` regeneration notes.

Operator-private job instances live under `~/.local-jobs/jobs`. Operator-private
job types are registered through overlay fragments in `~/.local-jobs/registry.d`
with handlers in `~/.local-jobs/handlers` or another absolute executable path.

## Label Root

The shipped default is `com.local-jobs`. Operators can pin a machine-specific
root in `~/.local-jobs/config.yml`:

```yaml
label_root: com.example.local-jobs
```

Labels are always derived as `<label_root>.<token>[.<id>]`.

## Common Commands

```bash
scripts/local-jobs.sh dashboard --brief
scripts/local-jobs.sh list-types --plain
scripts/local-jobs.sh add-job --type command --id backup --program /path/to/script --schedule 02:00
scripts/local-jobs.sh add-job --type command --id poller --program /path/to/tool --arg poll-once --interval-seconds 60 --dry-run
scripts/local-jobs.sh add-job --type incremental-git-fetch --id reference --path /path/to/repo --branch main
scripts/local-jobs.sh update-job --id reference --fetch-tags true  # opt in to remote tags; default remains --no-tags
scripts/local-jobs.sh enable-canvas-runs    # optional: silent Run now buttons in the Cursor canvas
scripts/local-jobs.sh doctor --plain
```

## Command schedules

Generic command jobs accept exactly one schedule form:

- `--schedule HH:MM` runs daily in local time and preserves existing calendar jobs.
- `--interval-seconds N` uses launchd `StartInterval` for `N` from 60 through
  2,147,483,647 seconds. The 60-second floor prevents accidental rapid-fire job
  storms while supporting once-per-minute polling; the upper bound keeps the
  persisted value portable as a signed 32-bit integer.

Add with `--dry-run` first to inspect the normalized entry, label, and next run
without writing config or a plist. `update-job --interval-seconds N` changes an
existing command job, while `repair-job` re-renders the same deterministic plist.
The shared dispatcher holds a per-type/per-instance lock for the entire run, so
manual and scheduled invocations never overlap. launchd also keeps one process
per label; a trigger that arrives while that process is active is not launched
as a concurrent copy.

## Dashboard canvas (Cursor)

After `bash install.sh` symlinks this skill into your agent tool paths, run the
`view` verb to open the at-a-glance monitor:

```bash
scripts/local-jobs.sh view     # regenerate from live state + print the canvas file to open
```

`view` writes the live render to the git-ignored
`canvases/local-jobs-dashboard.generated.canvas.tsx`. The tracked
`canvases/local-jobs-dashboard.canvas.tsx` is a data-free seed that renders the
empty state. See `canvases/README.md` for the file roles, the canvas bridge
(including Refresh → `view`), and maintainer commands (`--live`, `--check`,
`--json`).

Canvas **Run now**, **Refresh**, **Pause/Resume**, and **Full explain-job** are
intentionally opt-in via the same bridge. `enable-canvas-runs` installs a
`com.local-jobs.canvas-bridge` LaunchAgent with `WatchPaths` on the canvas
directory plus a 15s backstop. The canvas writes sidecar requests (`dash.runRequest`,
`dash.viewRequest`, `dash.controlRequest`, `dash.explainRequest`); the bridge
validates request age/snapshot freshness, dedups with a bounded handled-request
ledger, runs the matching verb (`run-job`, `view`, `disable-job`/`enable-job`, or
explain inspect), and regenerates `view` when appropriate. It never uses
`newComposerChat`; chat buttons remain only for explain/fix flows that need an
agent. Disable it with `scripts/local-jobs.sh disable-canvas-runs`.

## Downstream Sync Note

`local-jobs` is a global skill. Registration metadata stays unchanged for this
feature; downstream delivery is the ecosystem orchestrator's normal
git-ignore-aware payload sync into consumers. The tracked bridge scripts,
launchd writer, and canvas template are copied; generated canvases and
`*.canvas.data.json` sidecars are excluded.

## Dependencies

- `python3` with PyYAML
- macOS `launchctl` for live scheduling
- `git` for `incremental-git-fetch`

`doctor --plain` reports missing dependencies clearly instead of requiring users
to inspect stack traces.
