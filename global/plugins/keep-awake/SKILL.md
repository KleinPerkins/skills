---
name: keep-awake
description: Keep this Mac awake while Cursor agents are active by maintaining a short Amphetamine session. Use when the operator asks to turn agent keep-awake on or off, check its status, repair its hooks, or remove it.
---

# keep-awake

This Cursor-only helper prevents the Mac from sleeping during active agent work. Cursor hooks record
a bounded activity lease; a local-jobs timer can refresh one finite Amphetamine session and its
finite `caffeinate` supplement even while the orchestrating chat is idle waiting on background work.
The timer never renews its own activity lease, so prolonged real Cursor inactivity still lets every
assertion expire naturally.

## Operator controls

- **On:** start Amphetamine. The helper never launches it for you.
- **Off:** quit Amphetamine. The next hook or maintenance tick performs one active cleanup step
  (stopping any live owned `caffeinate` process — see "System/display-sleep supplement" below);
  later calls are harmless no-ops.
- **Status:** run `bash install.sh --doctor`.
- **Repair:** run `bash install.sh --repair`.
- **Install or reconcile:** run `bash install.sh --apply`.
- **Remove:** run `bash install.sh --uninstall`.

Doctor does not change this capability's configuration, hooks, timer, state, or assertions; its
local-jobs status query can create/remove that framework's own transient read lock. Repair reconciles
this capability's Cursor hook rows and maintenance timer, clears an expired ownership lease, and
removes malformed activity state. Neither command launches Amphetamine, sends an Apple Event, or
changes the app. Uninstall first fences new runtime work, removes the local-jobs timer and hook rows,
then removes state and stops any live owned `caffeinate` process (see "System/display-sleep
supplement" below). It lets an existing finite Amphetamine session expire on its own rather than
ending a session that cannot be unambiguously identified.

## Timing and behavior

The default session lasts 20 minutes. Direct assertion work is throttled to at most once every 5
minutes, but every real `beforeSubmitPrompt` or `preToolUse` hook updates
`~/.local/state/keep-awake/activity.json`. A `keep-awake-maintenance` command job runs every 5
minutes through the shared local-jobs framework and may perform the same bounded refresh only while
that last real hook activity is at most 4 hours old. Maintenance ticks never write `activity.json`,
so the timer cannot keep itself alive forever. Once that activity window expires, the last finite
Amphetamine and `caffeinate` assertions expire within their normal 20-minute duration.

The helper preserves infinite, Trigger, app/date, and unrelated finite sessions. It also asks
Amphetamine to prevent the screen saver while a session it owns is active, and (via
`displaySleepAllowed: false`) keeps the physical display itself from sleeping for the life of that
session — a stronger effect than screen-saver suppression alone, so expect a laptop to burn more
battery than usual while an agent-owned session is running on battery power.

Screen-saver suppression is reasserted on every owned check-in, not only when the session is
restarted: Amphetamine has no "extend" command, so refreshing a session's duration means fully
ending and recreating it, which briefly drops the system's display-sleep-prevention assertion.
Doing that on every 5-minute check-in — rather than only once a session is genuinely close to
running out — would reopen that gap far more often than necessary, so a full restart only happens
once the owned session has 10 minutes or less left (twice the check-in interval, guaranteeing at
least one more chance to catch it before it could actually lapse). See "System/display-sleep supplement"
below for how the resulting gap is fully closed rather than merely minimized.

If Amphetamine is missing, setup and health checks report **ready but dormant**. If it is installed
but quit, they report **ready but inactive**. Starting or quitting Amphetamine is the only on/off
control.

## System/display-sleep supplement

Amphetamine's own `start new session` command is atomic: it fully ends the old session before the
new one exists, so every restart described above briefly drops the system's display-sleep-prevention
assertion to zero — confirmed with `pmset -g assertionslog` across a real refresh cycle. On the
default schedule that gap is short, but it is real, and there is no way to hold two overlapping
Amphetamine sessions to close it from Amphetamine's side alone.

While `caffeinateSupplementEnabled` is `true` in `plugin.json` (the default) and Amphetamine is
installed and running, every eligible hook or maintenance tick also manages one independent
`caffeinate -d -i -s` process alongside the Amphetamine session, tracked in its own
`caffeinate.json` sidecar (kept separate from `state.json`, which this capability's own
CAS-guarded lease tracking already owns):

- `-d` prevents display idle sleep because `displaySleepAllowed` is false.
- `-i` prevents user-idle system sleep.
- `-s` adds the distinct `PreventSystemSleep` assertion that blocks scheduled Maintenance Sleep.
  macOS honors this assertion only while connected to AC power; on battery, `-d`/`-i` continue but
  `-s` is ignored. The capability does not use unsafe global power-setting overrides to change that
  OS rule.

- **Cold start:** no process tracked yet -> spawn one, confirm it is alive, and record its pid and
  expiry.
- **Refresh due** (10 minutes or less left, the same threshold used for Amphetamine restarts above):
  spawn a **new** `caffeinate` process, confirm it is alive, *then* kill the old one — never the
  reverse — so a display-sleep-prevention assertion is held continuously through the handover. If
  the new process fails to start, the old one is left running rather than ending up with no
  protection at all.
- **Plenty of time left:** no-op.

Every check re-validates both liveness (`kill -0`) and identity (`ps -p PID -o comm=`) immediately
before acting on a tracked pid, so a crash followed by the OS recycling that pid onto an unrelated
process can never cause the wrong process to be trusted or killed. The whole decide/spawn/kill step
runs inside an owner-tagged lock with bounded retry, so a timer tick and Cursor hook landing together
cannot double-spawn or double-kill it, and an old lock holder cannot delete a replacement lock during
stale-lock recovery.

Quitting Amphetamine (the documented Off control above) stops this too: the next hook or maintenance
tick kills any live owned `caffeinate` process and clears its sidecar as one real, active cleanup
step — only the ticks after that are true no-ops. `bash install.sh --doctor` reports a
`caffeinate supplement:` status line unconditionally — cold start, alive and owned, disabled via
`plugin.json`, or a liveness/identity mismatch — with an active cross-check performed on every run.
That turns the one-time manual `pmset` verification above into a permanent, repeatable regression
check for this exact bug.

To disable this independent supplement without any code change, set `caffeinateSupplementEnabled` to
`false` in `plugin.json` and re-run `bash install.sh --apply`; every other behavior described in this
document is unaffected either way.

## Maintenance timer

`bash install.sh --apply` reconciles one generic local-jobs `command` instance with stable id
`keep-awake-maintenance`; local-jobs chooses the actual `com.kleinperkins.*` launchd label from its
configured `label_root`. The job invokes a dedicated wrapper through Cursor's stable keep-awake
symlink, never a disposable worktree path. That wrapper requires the new maintenance descriptor
fields before dispatching the runtime event; rolling code back to a version without the wrapper or
fields therefore fails safe instead of turning an old unknown-event path into an unbounded refresh.

Configuration in `plugin.json`:

- `maintenanceEnabled` — explicitly enables installation; absent/false descriptors stay hook-only.
- `maintenanceIntervalSeconds` — local-jobs interval (default 300; minimum 60).
- `activityWindowSeconds` — maximum age of real Cursor hook activity (default 14400 / 4 hours).

`--doctor` reports the timer's discovered label, configured interval, loaded state, and the current
activity lease. `--repair` recreates or reloads a drifted timer. `--uninstall` removes it before
runtime state; if timer removal cannot be proven, uninstall leaves a stop fence in place and fails
rather than allowing an orphaned timer to recreate assertions.

## Ownership limit

Amphetamine does not expose a session identifier. Ownership is inferred from a short local lease and
the session's remaining time. A manually replaced finite session is normally preserved because its
remaining time no longer matches the lease; a manual session that happens to match that timing
closely could be treated as the helper's session and refreshed. Infinite and Trigger sessions are
always preserved.

## Troubleshooting

**The Mac still sleeps during active agent work.** This is almost always a first-run macOS
Automation permission gap, not a bug: run `bash install.sh --doctor` and look for a TCC/Apple
Events permission error in its output. If present, open System Settings > Privacy & Security >
Automation, find the app that runs Cursor's hooks (e.g. Cursor or your terminal), and enable its
permission to control Amphetamine. Re-run `--doctor` afterward to confirm the error clears.

`--doctor` also surfaces any *other* recent Amphetamine/osascript error, not just TCC-shaped ones —
so a future Amphetamine update that changes its AppleScript responses in an unrecognized way will
still show up here, even though it won't match the specific TCC wording above. Report the exact
error text from `--doctor` output if you hit one that isn't a permissions issue.

If `--doctor` instead reports a missing, unloaded, or quarantined maintenance timer, run
`bash install.sh --repair`, then inspect the shared framework with
`local-jobs.sh explain-job --id keep-awake-maintenance`. A scheduled timer is intentionally not
evidence of an active lease: after 4 hours without a real Cursor hook it performs a strict no-op so
normal sleep resumes.

**The Mac still sleeps when the display/lid is closed, even with an active session (docked /
clamshell setups).** This is a separate Amphetamine preference, not a bug in this capability:
Preferences → Sessions → "Allow System to Sleep When Display is Closed" overrides every session
this capability starts — including `displaySleepAllowed: false` — the instant the display/lid
closes. If your Mac is permanently docked with the lid closed, this defeats keep-awake completely
and silently, with no other symptom. Run `bash install.sh --doctor`: a `WARN` line about the Mac
sleeping on display/lid close means the checkbox is on. Fix it manually — Amphetamine menu bar >
Settings > Sessions > uncheck "Allow System to Sleep When Display is Closed". A one-time system
warning dialog may appear when you do; check "Do Not Show This Message Again" so it never appears
again. This is deliberately a manual, one-time fix, not something `--doctor`/`--repair` flips for
you: Amphetamine's own docs warn that toggling this preference via AppleScript can trigger that
same warning dialog unattended, which is exactly the failure mode an unattended doctor/repair run
or a mid-session hook must never risk — so this capability only detects and explains the setting,
it never calls the AppleScript commands that would change it. Verified: the create/extend runtime
hook (`keep-awake-refill.sh`) never references this preference either — its AppleScript only ever
calls `start new session ... displaySleepAllowed:` and `prevent screen saver`, a wholly separate
per-session Amphetamine feature — so once you've fixed this checkbox manually, no session
creation, refresh, or check-in this capability performs can read it, write it, or silently revert
your fix. Re-run `--doctor` afterward to confirm the warning clears. If Amphetamine is not running,
or its response is unrecognized, `--doctor` stays silent on this check rather than guessing — that
is fail-safe, not a sign it isn't being checked.

**The screen saver still activates during active agent work, even though a session stays alive.**
Fixed by decoupling screen-saver suppression from session-duration refreshes (see "Timing and
behavior" above) — update to the latest version if you still see this. If it recurs: this
capability only ever prevents the screen saver while its *own* session is confirmed active
(`--doctor` reports **READY**); a manually-started or foreign session is always left untouched
(see "Ownership limit" below), so the screen saver can still fire during one of those. It is also
possible for real idle time to already exceed a very short screen-saver timeout in the instant
between one 5-minute check-in and the next — shortening `throttleSeconds` narrows that window
further but never fully closes it.

**Known limitation — portable tests cannot exercise real Darwin/AppleScript or power-management
behavior.** Tests use Darwin-binary overrides and a hermetic local-jobs state, so they verify command
construction, lease gates, lifecycle ordering, and timer execution without driving real
`osascript`, Amphetamine, launchd, or `pmset`. After a macOS/Amphetamine update, run `--doctor` and
spot-check `pmset -g assertions`: an eligible live session on AC should show `caffeinate` holding
`PreventSystemSleep`, `PreventUserIdleSystemSleep`, and (with the default display setting)
`PreventUserIdleDisplaySleep`.
