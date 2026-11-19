# local-jobs handler ABI (`abi/v1`)

Every job type is a self-contained executable handler. The core discovers types
from `config/registry.yml` plus operator overlays in `~/.local-jobs/registry.d`
and drives each handler through the verbs below.

## Operator CLI Verbs

| Verb | Purpose |
|---|---|
| `view` | Regenerate + open the read-only Cursor dashboard canvas (live `dashboard/v1`) |
| `view-jobs` | Managed instances plus discovered launchd agents |
| `dashboard [--json|--brief]` | Rich `dashboard/v1` payload or plain summary |
| `explain-job --id <id>` | Narrative troubleshooting and suggested commands |
| `resolve-instance --query <text>` | Fuzzy job discovery |
| `list-types [--plain|--json]` | Human catalog or add schema |
| `describe-types` | Type schema superset with update-field matrix |
| `add-job [--dry-run]` | Create or preview an instance |
| `update-job`, `delete-job`, `run-job`, `logs-job` | Instance lifecycle |
| `enable-job`, `disable-job` | Toggle scheduling |
| `enable-canvas-runs`, `disable-canvas-runs` | Install/uninstall the optional canvas Run now bridge |
| `repair-job`, `doctor [--plain]` | Convergence and health |
| `adopt-job` | Import an unmanaged LaunchAgent |
| `add-job-type`, `update-job-type` | Agent-mediated overlay type authoring |

Command handlers expose two mutually-exclusive members of the required
`schedule` input group: `--schedule HH:MM` and `--interval-seconds N`.
`interval_seconds` is a typed add-schema kind that normalizes to
`{"kind":"interval","seconds":N}`; managed intervals must be
60–2,147,483,647 seconds. Handlers may use `required_one_of` on schema fields to
declare another named group with the same exactly-one contract.

### Optional identity + run mode (additive; no version bump)

Three optional scalar fields are additive to any chassis type (and mirrored in
git-fetch's bespoke config) — absent, behavior is exactly as before:

* `display_name` — human-friendly name shown first on the dashboard; the
  immutable `id` is shown second when they differ. Falls back to `id`.
* `description` — one-line operator description. Display precedence is
  `description` (user-set) > `overview` (derived) > type description.
* `execution_mode` — `scheduled` (default) | `on_demand` (command jobs).

A schema field may declare two additive attributes the core honors generically:

* `choices: [...]` — `build-entry`/`build-patch` reject a value outside the list.
* `required_unless: {"field": <name>, "equals": <value>}` — the field (or its
  `required_one_of` group) is not required when the referenced field already
  equals that value. The store mirrors this with a required-field spec object
  `{"field": <name>, "unless": {"field": <k>, "equals": <v>}}`.

`command` uses these so a schedule is required for `execution_mode: scheduled`
but waived for `on_demand`.

### `execution_mode: on_demand`

An `on_demand` command job installs **no** launchd scheduling agent and needs no
schedule. It is still runnable via `run-job` / the canvas Run now. Because it
carries no agent, "no loaded agent" is the **correct** state:

* `doctor` / `repair` never report it as drift and preserve `execution_mode`
  across a repair pass (repair boots out any lingering agent for it).
* the dashboard forces `drift=false` and `stale=false`, reports
  `next_run.basis:"on_demand"`, excludes it from the `disabled` count, and adds a
  `summary.on_demand` count.

## Handler Verbs

Handlers are called as `<handler> <verb> [args]` and implement:

| Verb | Contract |
|---|---|
| `describe` | Print one JSON object describing the type. Read-only. |
| `list-instances` | Print a JSON array of normalized instances. Read-only. |
| `view --id <id>` | Print one normalized instance. Read-only. |
| `run --id <id> [--dry-run]` | Execute now and emit one `@@RUNLOG@@ {json}` line. |
| `logs --id <id> [--tail N]` | Print log paths and recent lines. |
| `add`, `update`, `delete` | Mutate instance store through declared schema. |
| `enable`, `disable`, `repair`, `doctor` | Scheduling and health lifecycle. |

## Labels

`describe.label_template` must be derived from the central label root. The default
root is `com.local-jobs`; operators may override it in `~/.local-jobs/config.yml`.
Templates use `<label_root>.<token>[.<id>]`.

## Instance Shape

```json
{
  "id": "reference",
  "type": "incremental-git-fetch",
  "enabled": true,
  "role": "instance",
  "schedule": "inherit",
  "display_name": "Reference mirror",
  "description": "Nightly filtered fetch of the reference clone.",
  "launchd_label": "com.local-jobs.git-fetch",
  "launchd_loaded": true,
  "log_paths": {"stdout": "...", "stderr": "..."}
}
```

`display_name` and `description` are optional (present only when set).
`command` instances additionally carry `execution_mode` (`scheduled` |
`on_demand`).

## Run Log Payload

Handlers print exactly one line:

```text
@@RUNLOG@@ {"status":"success","fields":{}}
```

`status` is `success`, `completed_with_failures`, `failure`, `skipped`, or
`dry-run`. `fields` is handler-specific structured data that `lib/summarize.py`
turns into a headline. The dispatcher adds timestamp, job id, type, duration,
return code, and appends a versioned event record under `~/.local-jobs`.

`completed_with_failures` is **additive — no `runlog` schema or version bump**:
old records and handlers that never emit it are unaffected. It reports a
multi-child run that finished with a *mix* of outcomes — some children failed
while others succeeded. It is **not** a fully-failed run: the handler exits `0`
and it accrues no failure streak of its own; only the genuinely-failed children
do. A run whose attempted children all fail is `failure`; a run whose children
all succeed — or that has no enabled children — is `success`.

The dispatcher also holds an exclusive per-type/per-instance lock for the whole
run. Concurrent triggers serialize instead of overlapping, and launchd keeps a
single active process for each job label.

### Per-child fan-out, counts, and reasons

A handler may add an optional `per_instance` array so a multi-target run records
each child's own last-run rather than only the aggregate:

```text
@@RUNLOG@@ {"status":"completed_with_failures",
  "fields":{"target":"all","counts":{"total":3,"succeeded":2,"failed":1,"skipped":0},"repos":[…]},
  "per_instance":[
    {"job_id":"a","status":"success","fields":{"reason":"up to date","repos":[…]}},
    {"job_id":"b","status":"failure","fields":{"reason":"network/SSH error","repos":[…]}}
  ]}
```

* `fields.counts` (multi-target sweeps only) is `{total, succeeded, failed, skipped}`.
* Each child carries its **own** `status` (`success` | `failure` | `skipped` |
  `dry-run`) plus a short plain-language `reason` (e.g. `up to date`,
  `fast-forwarded`, `remote not found`, `network/SSH error`,
  `merge not fast-forward`).
* The dispatcher reconciles **each record by its own return code** — a non-zero
  *parent* rc can never flip a truthful successful *child*. A child's rc is
  derived from its own status: `0` for success/skipped/dry-run, non-zero for
  failure.

### `incremental-git-fetch` failure_policy

The `git-fetch` global config block accepts `failure_policy: continue | stop`
(default `continue`, validated in `config.py`):

* `continue` — attempt every enabled repo; the parent is
  `completed_with_failures` when some (but not all) fail.
* `stop` — halt the sweep after the first failure. Unattempted repos are counted
  in the **parent** `counts.skipped` and a `skipped` ledger entry only — they
  emit **no** per-child run event, so a repo's real prior failing streak is never
  reset by a skip.

Handler exit code `2` keeps its usage-error meaning and is never overloaded to
signal a partial success.

## Dashboard Canvas Bridge

The dashboard payload includes read-only `run_bridge_enabled`, derived from the
bridge LaunchAgent's loaded state. When enabled, the canvas writes sidecar
requests that the bridge picks up, validates, dedups, and dispatches:

- **Refresh** — `dash.viewRequest = {nonce, at, snapshotGeneratedAt}` → `view`
- **Run now** — `dash.runRequest = {jobId, type, nonce, at, snapshotGeneratedAt}` → `run-job`, then `view`
- **Pause/Resume** — `dash.controlRequest = {jobId, action, nonce, at, snapshotGeneratedAt}` → `disable-job` / `enable-job`, then `view`
- **Full explain-job** — `dash.explainRequest = {jobId, nonce, at, snapshotGeneratedAt}` → explain inspect, then `view`

`bin/canvas-run-bridge.sh` ignores the supplied type on run requests, resolves the exact
registered non-error instance by `jobId`, allows `__global__` only for the known
global scheduler row, dedups by nonce under `~/.local-jobs/canvas-bridge`, and
never writes the sidecar.
