# local-jobs Cursor canvases

Cursor Canvas surfaces for local-jobs. The dashboard is rendered by the operator
`view` verb. The canvas performs **no direct configuration writes** — every
config change (rename, describe, reschedule, switch mode, repair, delete, and
even create) is agent-mediated through the validated `local-jobs.sh` verbs, which
are the single safe config-writer. Only two things are direct operational
toggles: **Run now** and **Pause/Resume**, both routed through the optional
launchd bridge (no config edit, no chat, no focus steal).

## Dashboard (`view` verb)

`scripts/local-jobs.sh view` regenerates the dashboard from live state and prints
the file to open as a canvas. It shows, at a glance: per-job status
(running / success / failure / never-run), recent run history, next scheduled run,
durations (last + typical), and distilled run summaries — so no one reads raw logs.

| File | Role |
|---|---|
| `local-jobs-dashboard.template.tsx` | Stable React shell; embed marker `__DASHBOARD_JSON__` |
| `local-jobs-dashboard.canvas.tsx` | Tracked **seed** — a data-free empty payload (renders the empty state); what downstream vendoring copies |
| `local-jobs-dashboard.generated.canvas.tsx` | **Live** render written by `view`; git-ignored, machine-specific, never committed |
| `*.canvas.data.json` | Cursor sidecar state; git-ignored, machine-specific; may contain `dash.runRequest`, `dash.viewRequest`, etc. |

### Refresh via the canvas bridge

The dashboard **Refresh** button writes `dash.viewRequest` to the sidecar when the
launchd bridge is enabled. The bridge validates request age/snapshot freshness,
deduplicates through its handled-request ledger, runs `local-jobs view`, and
regenerates the live canvas — the same path as after Run now, Pause/Resume, or
Full explain-job. The canvas also bumps `dash.refresh` so relative ages and
staleness recompute immediately against the live clock (no chat, no file reads).

- **Run now button** writes one sidecar request and waits for the optional
  launchd bridge. The bridge validates the request age/snapshot and job, skips
  stale/replayed/already-running requests through its handled-request ledger,
  runs `run-job`, and then runs `view` after the run finishes or fails; it does
  not open a chat or write back to the sidecar.
- **Full explain-job button** writes `dash.explainRequest` to the same sidecar.
  The bridge inspects the job (program/script comments, handler config — not
  dashboard stats), synthesizes a layperson narrative, writes
  `~/.local-jobs/explain/<id>.json`, and runs `view`. Cached explains embed in
  the next snapshot. Optional `~/.local-jobs/hooks/explain-agent.sh` can upgrade
  the cache with an agent-authored narrative (`source: agent`).

### Run now bridge

The bridge is local opt-in:

```bash
scripts/local-jobs.sh enable-canvas-runs
scripts/local-jobs.sh view
```

This installs the `com.local-jobs.canvas-bridge` LaunchAgent with `WatchPaths`
on this `canvases/` directory plus a 15s backstop. The canvas disables Run
buttons while one request is pending, shows that the request is queued for the
bridge, and clears it when the regenerated snapshot advances or the request ages
out. `disable-canvas-runs` uninstalls the bridge.

The same bridge also carries **Refresh** (`dash.viewRequest`) and **Pause/Resume** (`dash.controlRequest`, action
`pause`/`resume`). It is an operational toggle symmetric with Run now — the
canvas queues a request and the bridge runs the validated `disable-job` /
`enable-job` verb (the single safe config-writer), then regenerates. It never
writes config from the canvas. The button is offered only for scheduled
instances (an on-demand job has no timer to pause; the global git-fetch sweep is
paused per-repo).

`Fix in chat`, `View logs`, `Manage in chat`, `Add job in chat`, and `Adopt` use
`newComposerChat` because those actions are agent-mediated. **Refresh**, `Run now`,
**Pause/Resume**, and **Full explain-job** stay in-canvas via the optional
launchd bridge (no chat, no focus steal).

### Local sidecar flush probe

Before relying on Run now on a new Cursor build, verify that a canvas click that
only calls `setCanvasState` flushes the sidecar promptly:

```bash
scripts/local-jobs.sh view
bin/verify-canvas-sidecar.sh --timeout 60
```

Open the printed live canvas, click **Run now** on any job, and leave the probe
running. Success prints the parsed `dash.runRequest` and sidecar path. If it
times out, keep the bridge disabled and use:

```bash
scripts/local-jobs.sh run-job --id <id>
```

### Empty state

With no `~/.local-jobs` data (fresh machine or cloud) the canvas renders a clear
"no local job data on this machine" state — it never errors or fabricates. The
tracked seed embeds exactly this empty payload.

### Maintainer commands

```bash
bin/generate-dashboard-canvas.sh          # (re)write the tracked data-free seed
bin/generate-dashboard-canvas.sh --live   # write the git-ignored live render (what `view` runs)
bin/generate-dashboard-canvas.sh --check  # assert the tracked seed stays data-free + current (CI/regen gate)
bin/generate-dashboard-canvas.sh --json   # emit dashboard/v1 JSON to stdout
```

Regenerate the seed after editing `local-jobs-dashboard.template.tsx`, then run
`--check` to confirm parity.

## Creating a job

There is no separate builder canvas. Job creation is agent-mediated: the
dashboard header's **Add job in chat** button opens a schema-guided creation
request in a new chat. The agent grounds itself with
`local-jobs.sh describe-types` (the machine-readable type+schema superset) and
walks the operator through display name, description, execution mode, and
type-specific settings, then writes the job with the validated `add-job` verb.
