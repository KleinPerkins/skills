---
name: local-jobs
description: Manage, inspect, and schedule local launchd jobs through one generic framework. Use for local jobs, launchd schedules, job dashboard/status/history, run now, logs, add/update/delete jobs, enable/disable/pause/resume, repair, doctor, adopt LaunchAgents, preview jobs, or add/update job types.
---

# local-jobs

Use `scripts/local-jobs.sh` from this skill. The runtime is co-located with the
skill; instances and operator-private overlays live in `~/.local-jobs`.

## First Checks (hard rules)

For dashboard, status, health, "what jobs are running?", or "show local jobs"
requests:

1. Run `scripts/local-jobs.sh dashboard --brief` immediately.
2. Run `scripts/local-jobs.sh view-jobs` immediately.
3. **Paste the output** in your reply — do not open or trust a stale
   `.canvas.tsx` snapshot for operational answers.
4. Do **not** read plans, source code, or config when those commands succeed.

For a specific job: `scripts/local-jobs.sh explain-job --id <id>`

**"Pull up the local jobs canvas"** → run `scripts/local-jobs.sh view`. It
regenerates the dashboard from live state, publishes a copy under the current
Cursor workspace's `canvases/` directory (so the IDE renders the dashboard UX,
not raw source), and prints that path. Open it with **Cmd+P → Open Canvas** (or
click the printed path). The skill's `canvases/*.generated.canvas.tsx` is the
machine-local data source; the workspace copy is what Cursor compiles beside chat.

The dashboard is **operable, not an editor**. It performs **no direct
configuration writes**: every config change — rename, describe, reschedule,
switch execution mode, repair, delete, and even create — is **agent-mediated**
through the validated `local-jobs.sh` verbs (the single safe config-writer),
launched from a row's **Manage in chat** action or the header's **Add job in
chat**. The only two **direct operational toggles** are **Run now** and
**Pause/Resume**: both are operational (start a run / flip the launchd timer),
NOT config edits, and both route through the optional launchd bridge (no chat, no
focus steal) — silent only after `scripts/local-jobs.sh enable-canvas-runs`
installs the opt-in sidecar bridge; otherwise use `run-job --id <id>` and
`disable-job`/`enable-job`. Failed rows also expose **Fix in chat**, **Full
explain-job**, and **View logs**. The in-canvas **Refresh** button recomputes
ages and staleness from the snapshot without a chat.

Canvas files:
- `canvases/local-jobs-dashboard.canvas.tsx` — tracked, data-free **seed** (renders
  the "no local job data" empty state on a fresh checkout).
- `canvases/local-jobs-dashboard.generated.canvas.tsx` — git-ignored **live** render
  written by `view` (this machine's data). Never committed.

On a fresh machine or cloud with no `~/.local-jobs` data, the canvas renders a
clear empty state — it never errors or fabricates. Prefer `dashboard --brief` /
`view-jobs` for scripted/text status answers.

## Common Routes

| Intent | Command |
|---|---|
| Visual dashboard (canvas) | `view` |
| Status or health | `dashboard --brief` |
| Full job list | `view-jobs` |
| Fuzzy job lookup | `resolve-instance --query <text>` |
| Type catalog | `list-types --plain` or `list-types --json` |
| Troubleshoot one job | `explain-job --id <id>` |
| Health check (plain) | `doctor --plain` |
| Run now | `run-job --id <id>` (`--dry-run` to preview) |
| Enable canvas Run now | `enable-canvas-runs` (local opt-in launchd bridge) |
| Disable canvas Run now | `disable-canvas-runs` |
| Pause or resume | `disable-job --id <id>` / `enable-job --id <id>` |
| Repair drift | `repair-job --id <id>` |
| Add generic command | Daily: `--schedule HH:MM`; interval: `--interval-seconds N` (minimum 60). Always add `--dry-run` first, then confirm and rerun without it |
| Add on-demand command | `add-job --type command --execution-mode on_demand ...` (no schedule; no timer; run via `run-job`/Run now) |
| Name / describe a job | `--display-name "..."` and `--description "..."` on `add-job`/`update-job` (git-fetch also via `update-job --id <repo>`/`--global`) |
| Add reference fetch | `add-job --type incremental-git-fetch --dry-run ...`, then confirm and rerun without `--dry-run` |
| Fetch remote tags for one reference | Add or update with `--fetch-tags true`; defaults to `false` (`--no-tags`) |
| Add a new type | `add-job-type` writes only to `~/.local-jobs/handlers` and `~/.local-jobs/registry.d` |

## Guardrails

- Confirm before destructive `delete-job --confirm`.
- After any mutation, run `doctor --plain` and summarize the result.
- Do not hand-edit YAML or plists for an operator; use CLI verbs.
- Command jobs require exactly one of `--schedule HH:MM` or
  `--interval-seconds N`; intervals below 60 seconds fail closed. This is waived
  for `--execution-mode on_demand` jobs, which install no launchd timer and run
  only via `run-job` / canvas Run now — `doctor`/`repair` treat their missing
  agent as correct (never drift) and preserve the mode.
- Optional `display_name` / `description` are never overwritten except by an
  explicit `update-job`; `migrate` only backfills missing defaults.
- Runs are serialized by a per-job dispatcher lock and never overlap.
- `label_root` defaults to `com.local-jobs` and may be overridden in `~/.local-jobs/config.yml`.
