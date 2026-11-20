#!/bin/bash
# Fast, fail-open Cursor heartbeat for a finite Amphetamine session.
set -u
umask 077
export LC_ALL=C

EVENT="${1:-}"
case "$EVENT" in
  beforeSubmitPrompt) RESPONSE='{}' ;;
  preToolUse) RESPONSE='{"permission":"allow"}' ;;
  maintenance) RESPONSE='{}' ;;
  *) printf '{}\n'; exit 0 ;;
esac

RESPONDED=0
# Tracked so every exit path (normal or signal-interrupted) can release a held throttle lock and
# reap a still-running osascript child instead of leaking either past this process's lifetime.
LOCK_HELD=0
LOCK_DIR=""
LOCK_OWNER=""
OSA_PID=""

release_lock() {
  if [ "$LOCK_HELD" -eq 1 ] && [ -n "$LOCK_DIR" ]; then
    current_owner=""
    IFS= read -r current_owner <"$LOCK_DIR/owner" 2>/dev/null || current_owner=""
    # A stale-lock recovery may have replaced the directory after this process acquired it.
    # Remove only the exact generation we own; never erase a successor's live lock.
    if [ -n "$LOCK_OWNER" ] && [ "$current_owner" = "$LOCK_OWNER" ]; then
      "$RM" -rf "$LOCK_DIR" >/dev/null 2>&1 || true
    fi
    LOCK_HELD=0
  fi
}

kill_osa() {
  if [ -n "$OSA_PID" ]; then
    kill -TERM "$OSA_PID" >/dev/null 2>&1 || true
    OSA_PID=""
  fi
}

respond() {
  RESPONDED=1
  kill_osa
  release_lock
  printf '%s\n' "$RESPONSE"
  trap - EXIT HUP INT TERM
  exit 0
}
# shellcheck disable=SC2329 # Invoked indirectly by the traps below.
respond_on_exit() {
  kill_osa
  release_lock
  if [ "$RESPONDED" -eq 0 ]; then
    printf '%s\n' "$RESPONSE"
  fi
  trap - EXIT HUP INT TERM
  exit 0
}
trap respond_on_exit EXIT HUP INT TERM

# Cursor sends one JSON object on stdin. Runtime decisions use only the event arg.
/bin/cat >/dev/null 2>&1 || true

UNAME="${KEEP_AWAKE_UNAME:-/usr/bin/uname}"
PLUTIL="${KEEP_AWAKE_PLUTIL:-/usr/bin/plutil}"
DATE="${KEEP_AWAKE_DATE:-/bin/date}"
SED="${KEEP_AWAKE_SED:-/usr/bin/sed}"
TR="${KEEP_AWAKE_TR:-/usr/bin/tr}"
CUT="${KEEP_AWAKE_CUT:-/usr/bin/cut}"
MKDIR="${KEEP_AWAKE_MKDIR:-/bin/mkdir}"
CHMOD="${KEEP_AWAKE_CHMOD:-/bin/chmod}"
MV="${KEEP_AWAKE_MV:-/bin/mv}"
RM="${KEEP_AWAKE_RM:-/bin/rm}"
SLEEP="${KEEP_AWAKE_SLEEP:-/bin/sleep}"
PGREP="${KEEP_AWAKE_PGREP:-/usr/bin/pgrep}"
OSASCRIPT="${KEEP_AWAKE_OSASCRIPT:-/usr/bin/osascript}"
CAFFEINATE="${KEEP_AWAKE_CAFFEINATE:-/usr/bin/caffeinate}"
PS="${KEEP_AWAKE_PS:-/bin/ps}"

PLATFORM="${KEEP_AWAKE_PLATFORM:-$("$UNAME" -s 2>/dev/null || true)}"
[ "$PLATFORM" = "Darwin" ] || respond

SCRIPT_DIR="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || respond
CAP_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)" || respond
DESCRIPTOR="${KEEP_AWAKE_DESCRIPTOR:-$CAP_DIR/plugin.json}"

descriptor_value() {
  "$PLUTIL" -extract "$1" raw -o - "$DESCRIPTOR" 2>/dev/null
}

DURATION_SECONDS="${KEEP_AWAKE_DURATION_SECONDS:-$(descriptor_value durationSeconds)}"
THROTTLE_SECONDS="${KEEP_AWAKE_THROTTLE_SECONDS:-$(descriptor_value throttleSeconds)}"
TIMEOUT_SECONDS="${KEEP_AWAKE_TIMEOUT_SECONDS:-$(descriptor_value timeoutSeconds)}"
DISPLAY_SLEEP_ALLOWED="${KEEP_AWAKE_DISPLAY_SLEEP_ALLOWED:-$(descriptor_value displaySleepAllowed)}"
PREVENT_SCREEN_SAVER="${KEEP_AWAKE_PREVENT_SCREEN_SAVER:-$(descriptor_value preventScreenSaver)}"
# Deliberately NOT validated below alongside DISPLAY_SLEEP_ALLOWED/PREVENT_SCREEN_SAVER: those two
# fields are required by the core Amphetamine AppleScript call, so a malformed value there must
# abort the whole hook (respond()). This is the on/off switch for an isolated supplemental
# subsystem (see plugin.json/SKILL.md) -- a malformed or missing value here must never take down
# the core keep-awake mechanism, so handle_caffeinate (below) treats anything other than the
# literal "true" as disabled rather than failing the entire hook open or closed.
CAFFEINATE_SUPPLEMENT_ENABLED="${KEEP_AWAKE_CAFFEINATE_SUPPLEMENT_ENABLED:-$(descriptor_value caffeinateSupplementEnabled)}"
MAINTENANCE_ENABLED="${KEEP_AWAKE_MAINTENANCE_ENABLED:-$(descriptor_value maintenanceEnabled)}"
ACTIVITY_WINDOW_SECONDS="${KEEP_AWAKE_ACTIVITY_WINDOW_SECONDS:-$(descriptor_value activityWindowSeconds)}"
# Optional v1 extension defaults: an old descriptor remains hook-only and never acquires a
# background timer lease merely because a newer runtime happens to read it.
[ -n "$MAINTENANCE_ENABLED" ] || MAINTENANCE_ENABLED="false"
[ -n "$ACTIVITY_WINDOW_SECONDS" ] || ACTIVITY_WINDOW_SECONDS="14400"
STATE_ROOT_RAW="${KEEP_AWAKE_STATE_ROOT:-$(descriptor_value stateRoot)}"
APP_NAME="${KEEP_AWAKE_APP_NAME:-$(descriptor_value backend.app)}"
PROCESS_NAME="${KEEP_AWAKE_PROCESS:-$(descriptor_value backend.process)}"
BUNDLE_ID="${KEEP_AWAKE_BUNDLE_ID:-$(descriptor_value backend.bundleId)}"

is_uint() {
  case "$1" in
    ""|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

is_uint "$DURATION_SECONDS" || respond
is_uint "$THROTTLE_SECONDS" || respond
is_uint "$TIMEOUT_SECONDS" || respond
[ "$DURATION_SECONDS" -gt 0 ] || respond
[ "$THROTTLE_SECONDS" -gt 0 ] || respond
[ "$TIMEOUT_SECONDS" -gt 0 ] || respond
[ $((DURATION_SECONDS % 60)) -eq 0 ] || respond
case "$DISPLAY_SLEEP_ALLOWED" in true|false) ;; *) respond ;; esac
case "$PREVENT_SCREEN_SAVER" in true|false) ;; *) respond ;; esac
[ -n "$APP_NAME" ] || respond
[ -n "$PROCESS_NAME" ] || respond
[ -n "$BUNDLE_ID" ] || respond

# Hoisted here from its original point of use (immediately before the AppleScript invocation
# gates further down) so the caffeinate supplement block below -- placed right after acquire_lock,
# before the throttle check -- can check Amphetamine's installed state too, without duplicating
# this computation. The actual install/running gate against APP_PATH still lives at its original
# call site further down and still exits via respond() there; only the assignment moved.
APP_PATH="${KEEP_AWAKE_APP_PATH:-/Applications/${APP_NAME}.app}"

case "$STATE_ROOT_RAW" in
  \~/*) STATE_ROOT="${HOME}/${STATE_ROOT_RAW#\~/}" ;;
  /*) STATE_ROOT="$STATE_ROOT_RAW" ;;
  *) respond ;;
esac
STATE_FILE="$STATE_ROOT/state.json"
LOCK_DIR="$STATE_ROOT/.lock"
CAFFEINATE_STATE_FILE="$STATE_ROOT/caffeinate.json"
ACTIVITY_STATE_FILE="$STATE_ROOT/activity.json"
STOP_FENCE_FILE="$STATE_ROOT/stop.fence"

NOW="${KEEP_AWAKE_NOW:-$("$DATE" +%s 2>/dev/null || true)}"
is_uint "$NOW" || respond
LOCK_OWNER="runtime-$$-$NOW-${RANDOM:-0}"

# A lifecycle uninstall writes this fence before removing the local-jobs timer or Cursor hooks.
# Check it both before and after a hook activity write so an invocation already entering while
# uninstall begins cannot start or refresh assertions afterward.
[ -e "$STOP_FENCE_FILE" ] && respond

read_activity_time() {
  [ -f "$ACTIVITY_STATE_FILE" ] || { printf '0\n'; return; }
  value="$("$SED" -n 's/.*"last_hook_activity":[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
    "$ACTIVITY_STATE_FILE" 2>/dev/null)"
  is_uint "$value" || value=0
  printf '%s\n' "$value"
}

write_activity_state() {
  timestamp="$1"
  is_uint "$timestamp" || return 1
  tmp="$ACTIVITY_STATE_FILE.tmp.$$"
  if ! "$MKDIR" -p "$STATE_ROOT" 2>/dev/null ||
     ! "$CHMOD" 700 "$STATE_ROOT" 2>/dev/null ||
     ! printf '{"last_hook_activity":%s}\n' "$timestamp" >"$tmp" 2>/dev/null ||
     ! "$CHMOD" 600 "$tmp" 2>/dev/null ||
     ! "$MV" -f "$tmp" "$ACTIVITY_STATE_FILE" 2>/dev/null; then
    "$RM" -f "$tmp" >/dev/null 2>&1 || true
    return 1
  fi
  return 0
}

remove_current_activity_if_fenced() {
  [ -e "$STOP_FENCE_FILE" ] || return 1
  recorded="$(read_activity_time)"
  if [ "$recorded" = "$NOW" ]; then
    "$RM" -f "$ACTIVITY_STATE_FILE" >/dev/null 2>&1 || true
  fi
  return 0
}

case "$EVENT" in
  beforeSubmitPrompt|preToolUse)
    # This lease records real Cursor activity, including throttled/no-backend/error paths. It is
    # intentionally best-effort: inability to persist the timer lease must not suppress the
    # existing direct hook attempt.
    write_activity_state "$NOW" || true
    remove_current_activity_if_fenced && respond
    ;;
  maintenance)
    [ "$MAINTENANCE_ENABLED" = "true" ] || respond
    is_uint "$ACTIVITY_WINDOW_SECONDS" || respond
    [ "$ACTIVITY_WINDOW_SECONDS" -gt 0 ] || respond
    LAST_HOOK_ACTIVITY="$(read_activity_time)"
    [ "$LAST_HOOK_ACTIVITY" -gt 0 ] || respond
    [ "$NOW" -ge "$LAST_HOOK_ACTIVITY" ] || respond
    [ $((NOW - LAST_HOOK_ACTIVITY)) -le "$ACTIVITY_WINDOW_SECONDS" ] || respond
    ;;
esac
[ -e "$STOP_FENCE_FILE" ] && respond

read_state_number() {
  key="$1"
  [ -f "$STATE_FILE" ] || { printf '0\n'; return; }
  value="$("$SED" -n "s/.*\"${key}\":[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p" "$STATE_FILE" 2>/dev/null)"
  is_uint "$value" || value=0
  printf '%s\n' "$value"
}

# ---- Caffeinate supplement -------------------------------------------------------------------
# An independent, always-on `caffeinate` process that overlaps (create-then-destroy) instead of
# Amphetamine's gap-prone rebuild -- see the comment on REFRESH_THRESHOLD_SECONDS below for the
# confirmed gap this closes. Everything handle_caffeinate (the single call site, right after
# acquire_lock below) needs must be defined above that call site: bash resolves a function call by
# looking up whatever is registered at that point in a top-to-bottom pass, so helpers cannot be
# defined further down the file the way they can be in languages with forward declarations.

# Only pid/expiry are ever read back on this hot path; status is write-only here (doctor, repair,
# and uninstall read it back through manage.py's own JSON-based validator instead of this
# dependency-free sed extraction, which -- like read_state_number above -- only ever handles bare
# unsigned-integer fields).
read_caffeinate_state() {
  key="$1"
  [ -f "$CAFFEINATE_STATE_FILE" ] || { printf '0\n'; return; }
  value="$("$SED" -n "s/.*\"${key}\":[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p" "$CAFFEINATE_STATE_FILE" 2>/dev/null)"
  is_uint "$value" || value=0
  printf '%s\n' "$value"
}

# Moved up from its original position (immediately before the state.json write_state() helper
# further down) because write_caffeinate_state() below needs it too, and this block's call site
# (right after acquire_lock) runs before write_state()'s own original position in a top-to-bottom
# pass.
sanitize_json_string() {
  printf '%s' "$1" |
    "$TR" '\r\n\t' '   ' |
    "$CUT" -c 1-240 |
    "$SED" 's/[^ -~]/?/g; s/\\/\\\\/g; s/"/\\"/g'
}

write_caffeinate_state() {
  pid="$1"
  expiry="$2"
  status="$(sanitize_json_string "$3")"
  # Belt-and-suspenders alongside manage.py's validate_caffeinate_state: this hot-path writer must
  # be structurally incapable of producing a sidecar with pid <= 0, regardless of what a future
  # caller might accidentally pass -- kill -0/-TERM on pid 0 targets this whole process group, not
  # one process.
  is_uint "$pid" && [ "$pid" -gt 0 ] || return 1
  is_uint "$expiry" || return 1
  tmp="$CAFFEINATE_STATE_FILE.tmp.$$"
  if ! "$MKDIR" -p "$STATE_ROOT" 2>/dev/null ||
     ! "$CHMOD" 700 "$STATE_ROOT" 2>/dev/null ||
     ! printf '{"pid":%s,"expiry":%s,"status":"%s"}\n' "$pid" "$expiry" "$status" >"$tmp" 2>/dev/null ||
     ! "$CHMOD" 600 "$tmp" 2>/dev/null ||
     ! "$MV" -f "$tmp" "$CAFFEINATE_STATE_FILE" 2>/dev/null; then
    "$RM" -f "$tmp" >/dev/null 2>&1 || true
    return 1
  fi
  return 0
}

# kill -0/kill -TERM on a tracked pid must never fire without first re-confirming BOTH liveness
# and identity here: liveness alone would trust a since-recycled pid (a different, unrelated
# process the OS happened to reassign that same number to after a crash), and pid 0 (empty/corrupt
# tracking) is refused outright per the note on write_caffeinate_state above.
caffeinate_alive_and_owned() {
  pid="$1"
  is_uint "$pid" && [ "$pid" -gt 0 ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  [ -x "$PS" ] || return 1
  # `ps -p PID -o comm=` reports the full executable path on macOS (e.g. /usr/bin/caffeinate), not
  # a bare command name -- confirmed empirically while building this, not assumed -- so this
  # strips any directory prefix before comparing rather than requiring an exact "caffeinate"
  # string.
  comm="$("$PS" -p "$pid" -o comm= 2>/dev/null)"
  [ "${comm##*/}" = "caffeinate" ]
}

# Spawns a new caffeinate, confirms it is alive, and leaves its pid in NEW_CAFFEINATE_PID (a
# deliberate global "return value", mirroring OSA_PID/OSA_STATUS further down for the same
# top-to-bottom-script reason). `-d` only when the display itself must not sleep
# (displaySleepAllowed=false, the same descriptor field the AppleScript session below already
# honors); `-i` prevents idle sleep. `-s` adds PreventSystemSleep while on AC power, closing the
# confirmed Maintenance Sleep gap that idle-class assertions do not cover. On battery macOS
# ignores only `-s`; the bounded `-d`/`-i` assertions continue normally. Redirected fds so the
# child never inherits this wrapper's stdin/stdout.
#
# The spawn happens inside `( set -m; cmd & echo $! >file )` -- a throwaway SUBSHELL, not this
# script's own shell. Enabling job control (`set -m`) there puts caffeinate in ITS OWN process
# group rather than this wrapper's: confirmed empirically (its pgid differed from the spawning
# shell's, and its ppid became 1 once the subshell exited), so a hook-runner that enforces
# timeoutSeconds via a process-group-wide signal cannot incidentally reap it too. Confining
# `set -m` to a throwaway subshell, rather than toggling it in this script's own shell, also
# avoids a second problem confirmed empirically while building this: toggling job control on/off
# directly in THIS shell registers the spawned job in THIS shell's own job table, and bash then
# prints a "[pid]  Terminated: 15 ..." notification straight to stderr the moment that job is
# later killed -- exactly the kind of stray output this hook cannot risk on a stream Cursor may be
# parsing. A job started inside a subshell is never registered anywhere once that subshell exits,
# so no such notification is possible; killing it later is just an ordinary signal to an ordinary
# pid. The new pid crosses the subshell boundary through a tmp file (scoped by this process's own
# pid, mirroring OSA_OUT's naming further down) because the subshell's own $! is not visible
# outside it.
fork_caffeinate() {
  # Guard mirrors write_state's own "mkdir -p then use" ordering further down: never attempt the
  # spawn unless the tracking directory is confirmed creatable first. Spawning before confirming
  # that would risk an orphaned, untracked caffeinate process if the pidfile write below then
  # failed (e.g. STATE_ROOT unwritable) -- there would be no way to recover its pid to kill it.
  "$MKDIR" -p "$STATE_ROOT" 2>/dev/null && "$CHMOD" 700 "$STATE_ROOT" 2>/dev/null || return 1
  pidfile="$STATE_ROOT/.caffeinate-new-pid.$$"
  "$RM" -f "$pidfile" >/dev/null 2>&1 || true
  if [ "$DISPLAY_SLEEP_ALLOWED" = "false" ]; then
    caffeinate_flags=(-d -i -s)
  else
    caffeinate_flags=(-i -s)
  fi
  (
    set -m
    "$CAFFEINATE" "${caffeinate_flags[@]}" -t "$DURATION_SECONDS" </dev/null >/dev/null 2>&1 &
    candidate_pid=$!
    # Keep the parent alive long enough to reap an immediate startup failure.
    # An orphan can still answer kill -0 while exiting (or as a zombie), which
    # would otherwise let a failed replacement retire the working old process.
    "$SLEEP" 0.05
    if ! kill -0 "$candidate_pid" >/dev/null 2>&1; then
      wait "$candidate_pid" 2>/dev/null || true
      exit 1
    fi
    echo "$candidate_pid" >"$pidfile"
  ) >/dev/null 2>&1 || return 1
  NEW_CAFFEINATE_PID=""
  IFS= read -r NEW_CAFFEINATE_PID <"$pidfile" 2>/dev/null || NEW_CAFFEINATE_PID=""
  "$RM" -f "$pidfile" >/dev/null 2>&1 || true
  is_uint "$NEW_CAFFEINATE_PID" && [ "$NEW_CAFFEINATE_PID" -gt 0 ] || return 1
  # Confirm alive immediately -- create-then-destroy only closes the Amphetamine gap (see
  # REFRESH_THRESHOLD_SECONDS below) if the new process is confirmed up before the old one is ever
  # touched.
  kill -0 "$NEW_CAFFEINATE_PID" >/dev/null 2>&1 || return 1
  return 0
}

# Non-exiting mirror of the installed/running gate enforced (with respond()) further down. Needed
# here as its own check because handle_caffeinate's cleanup branch must still run when Amphetamine
# is NOT installed/running, whereas the gate further down exits immediately via respond() and
# would skip anything placed after it -- see the placement note on the call site below.
amphetamine_present_and_running() {
  [ -d "$APP_PATH" ] || return 1
  [ -x "$PGREP" ] || return 1
  "$PGREP" -x "$PROCESS_NAME" >/dev/null 2>&1 || return 1
  return 0
}

# Amphetamine is not installed or not running: the documented Off control (quit Amphetamine) must
# still fully stop everything, including this. Identity-checked like every other kill here, then
# the sidecar itself is removed -- the first post-quit tick performs this one active cleanup step;
# every tick after that (once the sidecar is gone) is a true no-op.
cleanup_owned_caffeinate() {
  tracked_pid="$(read_caffeinate_state pid)"
  if caffeinate_alive_and_owned "$tracked_pid"; then
    kill -TERM "$tracked_pid" >/dev/null 2>&1 || true
  fi
  "$RM" -f "$CAFFEINATE_STATE_FILE" >/dev/null 2>&1 || true
}

# A missing/non-executable caffeinate or ps binary must skip this tick's caffeinate handling
# without affecting the rest of the script (handle_caffeinate returns right after calling this).
# Never invents a pid to satisfy the pid>0 sidecar schema: only refreshes the status text of an
# already-tracked, still-valid entry, and only when one exists. If nothing is yet tracked there is
# nothing safe to say beyond doctor's existing "not yet tracked (cold start)" reading, so this is
# a silent no-op in that case.
write_caffeinate_binary_missing_error() {
  existing_pid="$(read_caffeinate_state pid)"
  is_uint "$existing_pid" && [ "$existing_pid" -gt 0 ] || return 0
  existing_expiry="$(read_caffeinate_state expiry)"
  write_caffeinate_state "$existing_pid" "$existing_expiry" "error-missing-binary" || true
}

handle_caffeinate() {
  [ "$CAFFEINATE_SUPPLEMENT_ENABLED" = "true" ] || return 0

  if ! amphetamine_present_and_running; then
    cleanup_owned_caffeinate
    return 0
  fi

  if [ ! -x "$CAFFEINATE" ] || [ ! -x "$PS" ]; then
    write_caffeinate_binary_missing_error
    return 0
  fi

  tracked_pid="$(read_caffeinate_state pid)"
  if caffeinate_alive_and_owned "$tracked_pid"; then
    tracked_expiry="$(read_caffeinate_state expiry)"
    remaining=$((tracked_expiry - NOW))
    if [ "$remaining" -le "$REFRESH_THRESHOLD_SECONDS" ]; then
      if fork_caffeinate; then
        # Re-validate liveness+identity on the OLD pid again immediately before killing it -- not
        # only at the read above -- closing the reuse window between that read and this kill.
        if caffeinate_alive_and_owned "$tracked_pid"; then
          kill -TERM "$tracked_pid" >/dev/null 2>&1 || true
        fi
        write_caffeinate_state "$NEW_CAFFEINATE_PID" "$((NOW + DURATION_SECONDS))" "refreshed" || true
      else
        # The new one failed to come up: leave the still-good old one running and just flag the
        # failure -- never end up with zero protection.
        write_caffeinate_state "$tracked_pid" "$tracked_expiry" "refresh-failed" || true
      fi
    fi
    # else: alive/owned with plenty of time left -- no-op.
  else
    if fork_caffeinate; then
      write_caffeinate_state "$NEW_CAFFEINATE_PID" "$((NOW + DURATION_SECONDS))" "started" || true
    fi
    # else: spawn failed and nothing was owned before -- nothing valid to record (see
    # write_caffeinate_state's own pid>0 guard) -- the next tick retries.
  fi
}

# Serializes the throttle-check-through-attempt-stamp-write critical section below -- and, sharing
# the same lock span, handle_caffeinate's decide/spawn/kill block called immediately after
# acquire_lock -- so two concurrent hook invocations (e.g. beforeSubmitPrompt and preToolUse
# firing close together) cannot both pass a stale last_attempt and both fire an Apple Event, nor
# both independently spawn/kill a caffeinate process. mkdir is atomic: it succeeds for exactly one
# racer, so it doubles as a dependency-free lock (no flock on macOS).
LOCK_STALE_SECONDS=$((THROTTLE_SECONDS * 2))
# `start new session` (per Amphetamine.sdef) unconditionally ends the existing session before
# starting the new one. Live testing (pmset -g assertionslog) during this fix confirmed that
# teardown briefly drops the system-wide PreventUserIdleDisplaySleep assertion to 0 before the
# rebuilt session recreates it -- the caffeinate supplement above exists specifically to cover
# that gap independently. Restricting the AppleScript's own full restart to ticks where the owned
# session is actually close to expiry -- rather than every throttle-permitted tick -- cuts
# exposure to that gap further; two throttle windows of headroom guarantees at least one more
# check-in before the real session could lapse even if a tick is skipped. Computed here (rather
# than at its original point of use, immediately before the AppleScript invocation further down)
# so handle_caffeinate above can reuse the identical threshold for its own refresh decision.
REFRESH_THRESHOLD_SECONDS=$((THROTTLE_SECONDS * 2))

lock_now() {
  if [ -n "${KEEP_AWAKE_NOW:-}" ]; then
    printf '%s\n' "$KEEP_AWAKE_NOW"
  else
    "$DATE" +%s 2>/dev/null
  fi
}

try_mkdir_lock() {
  "$MKDIR" "$LOCK_DIR" 2>/dev/null || return 1
  acquired_at="$(lock_now)"
  if ! is_uint "$acquired_at" ||
     ! printf '%s\n' "$LOCK_OWNER" >"$LOCK_DIR/owner" 2>/dev/null ||
     ! printf '%s\n' "$acquired_at" >"$LOCK_DIR/acquired" 2>/dev/null; then
    "$RM" -rf "$LOCK_DIR" >/dev/null 2>&1 || true
    return 1
  fi
  LOCK_HELD=1
  return 0
}

acquire_lock_once() {
  # A maintenance cold start has no activity sidecar and exits before this point; direct Cursor
  # hooks create the state root for activity.json before locking. Keep the absent-root no-op as a
  # defensive fallback.
  [ -d "$STATE_ROOT" ] || return 0
  try_mkdir_lock && return 0
  # Someone else holds it. Steal only a parseable, positively-aged stamp older than 2x the
  # throttle window. Missing/malformed/future stamps are not proof of staleness and stay untouched.
  # A legacy v2 lock has no owner file but does have this stamp, so genuinely stale legacy locks
  # still upgrade automatically.
  stamp=""
  owner=""
  IFS= read -r stamp <"$LOCK_DIR/acquired" 2>/dev/null || stamp=""
  IFS= read -r owner <"$LOCK_DIR/owner" 2>/dev/null || owner=""
  is_uint "$stamp" || return 1
  observed_at="$(lock_now)"
  is_uint "$observed_at" || return 1
  [ "$observed_at" -ge "$stamp" ] || return 1
  [ $((observed_at - stamp)) -gt "$LOCK_STALE_SECONDS" ] || return 1

  # Re-read the generation immediately before removal. This does not turn mkdir into a general
  # compare-and-swap primitive, but it closes the practical stale-read window and, together with
  # owner-aware release_lock(), prevents an old holder from deleting its successor.
  current_stamp=""
  current_owner=""
  IFS= read -r current_stamp <"$LOCK_DIR/acquired" 2>/dev/null || current_stamp=""
  IFS= read -r current_owner <"$LOCK_DIR/owner" 2>/dev/null || current_owner=""
  [ "$current_stamp" = "$stamp" ] && [ "$current_owner" = "$owner" ] || return 1
  "$RM" -rf "$LOCK_DIR" >/dev/null 2>&1 || return 1
  try_mkdir_lock && return 0
  return 1
}

acquire_lock() {
  attempt=0
  while [ "$attempt" -lt 5 ]; do
    acquire_lock_once && return 0
    attempt=$((attempt + 1))
    [ "$attempt" -lt 5 ] || break
    "$SLEEP" 0.05 2>/dev/null || break
  done
  return 1
}

# Retry briefly so a timer tick and Cursor hook landing together converge on the same throttle
# cycle instead of losing the real hook immediately. Still fail open well inside the hook timeout
# if the owner remains live or acquisition fails for any other reason.
acquire_lock || respond

# Placed immediately after acquire_lock succeeds, before the throttle check below and before the
# app-installed/running gates further down -- not after them. Those gates call respond(), which
# exits immediately, so anything placed after them never runs when Amphetamine is missing/not
# running -- exactly the state handle_caffeinate's cleanup branch exists to handle. Placing this
# before the throttle check also means it is never skipped on a throttled tick. Sharing
# acquire_lock's critical section (rather than taking a second lock) is what stops two overlapping
# hook invocations from each independently spawning or killing a caffeinate process; kill -0/ps/
# caffeinate calls are fast and local, so folding them in here does not meaningfully lengthen the
# critical section.
handle_caffeinate

LAST_ATTEMPT="$(read_state_number last_attempt)"
if [ "$NOW" -ge "$LAST_ATTEMPT" ] && [ $((NOW - LAST_ATTEMPT)) -lt "$THROTTLE_SECONDS" ]; then
  respond
fi

[ -d "$APP_PATH" ] || respond
[ -x "$PGREP" ] || respond
"$PGREP" -x "$PROCESS_NAME" >/dev/null 2>&1 || respond
[ -x "$OSASCRIPT" ] || respond

LAST_SUCCESS="$(read_state_number last_success)"
LEASE_EXPIRY="$(read_state_number lease_expiry)"

write_state() {
  attempt="$1"
  success="$2"
  lease="$3"
  status="$(sanitize_json_string "$4")"
  error="$(sanitize_json_string "$5")"
  tmp="$STATE_FILE.tmp.$$"
  if ! "$MKDIR" -p "$STATE_ROOT" 2>/dev/null ||
     ! "$CHMOD" 700 "$STATE_ROOT" 2>/dev/null ||
     ! printf '{"last_attempt":%s,"last_success":%s,"lease_expiry":%s,"last_status":"%s","last_error":"%s"}\n' \
       "$attempt" "$success" "$lease" "$status" "$error" >"$tmp" 2>/dev/null ||
     ! "$CHMOD" 600 "$tmp" 2>/dev/null ||
     ! "$MV" -f "$tmp" "$STATE_FILE" 2>/dev/null; then
    "$RM" -f "$tmp" >/dev/null 2>&1 || true
    return 1
  fi
  return 0
}

# Stamp an attempt before AppleScript. If state cannot be written, do not issue an
# unthrottled Apple Event.
write_state "$NOW" "$LAST_SUCCESS" "$LEASE_EXPIRY" "attempting" "" || respond
# The critical section is over: last_attempt is now stamped, so a concurrent invocation's own
# throttle check will correctly see it. Release before the (potentially slower) Apple Event call.
release_lock

DURATION_MINUTES=$((DURATION_SECONDS / 60))
TOLERANCE_SECONDS=$((THROTTLE_SECONDS + 15))
# REFRESH_THRESHOLD_SECONDS (used just below by the AppleScript's own refresh-vs-preserve
# decision) is computed earlier, immediately after acquire_lock, so the caffeinate supplement
# block above can also use it -- see the comment there for why the gap this threshold manages
# exists at all.

# osascript's PID is captured (background + wait) rather than read via a plain $(...) command
# substitution, so a forced kill of this wrapper (e.g. a hook-runner enforcing timeoutSeconds)
# can reap the still-running osascript child from the trap instead of orphaning it mid-Apple-Event.
OSA_OUT="$STATE_ROOT/.osa-out.$$"
"$OSASCRIPT" - \
  "$NOW" \
  "$LEASE_EXPIRY" \
  "$DURATION_MINUTES" \
  "$TOLERANCE_SECONDS" \
  "$TIMEOUT_SECONDS" \
  "$DISPLAY_SLEEP_ALLOWED" \
  "$PREVENT_SCREEN_SAVER" \
  "$BUNDLE_ID" \
  "$REFRESH_THRESHOLD_SECONDS" \
  >"$OSA_OUT" 2>&1 <<'APPLESCRIPT' &
on run argv
	set nowEpoch to (item 1 of argv) as integer
	set leaseExpiry to (item 2 of argv) as integer
	set durationMinutes to (item 3 of argv) as integer
	set toleranceSeconds to (item 4 of argv) as integer
	set timeoutSeconds to (item 5 of argv) as integer
	set displaySleep to ((item 6 of argv) is "true")
	set preventSaver to ((item 7 of argv) is "true")
	set backendID to (item 8 of argv)
	set refreshThresholdSeconds to (item 9 of argv) as integer

	with timeout of timeoutSeconds seconds
		-- Addressed by bundle id (not display name) for rename/relocation resistance. A dynamic
		-- `tell application id` target loses static access to Amphetamine's custom AppleScript
		-- vocabulary unless the compiler is told where to find it, hence `using terms from`.
		using terms from application "Amphetamine"
			tell application id backendID
				-- session time remaining sentinels (per Amphetamine.sdef, confirmed live): 0 =
				-- infinite-duration session, -1 = ends at a Trigger, -2 = ends at an app/date-based
				-- time, -3 = no active session. Any positive value is real seconds remaining.
				set remaining to session time remaining
				if remaining is -3 then
					start new session with options {duration:durationMinutes, interval:minutes, displaySleepAllowed:displaySleep}
					if preventSaver then prevent screen saver
					return "started|" & remaining
				else if remaining > 0 then
					set expectedRemaining to leaseExpiry - nowEpoch
					set delta to remaining - expectedRemaining
					if delta < 0 then set delta to -delta
					if leaseExpiry > nowEpoch and expectedRemaining > 0 and delta is less than or equal to toleranceSeconds then
						-- Confirmed our own session. Only pay the teardown/rebuild cost (and its
						-- brief assertion gap, above) once the session is actually close to running
						-- out; otherwise reassert screen-saver suppression on the still-live session
						-- alone. Per Amphetamine.sdef, "prevent screen saver" on an already-active
						-- session only edits that session's properties -- confirmed live to touch no
						-- assertion and leave the session's own remaining time untouched.
						if remaining <= refreshThresholdSeconds then
							start new session with options {duration:durationMinutes, interval:minutes, displaySleepAllowed:displaySleep}
							if preventSaver then prevent screen saver
							return "refreshed|" & remaining
						else
							if preventSaver then prevent screen saver
							return "preserved-owned|" & remaining
						end if
					end if
					return "preserved-finite|" & remaining
				else
					return "preserved-special|" & remaining
				end if
			end tell
		end using terms from
	end timeout
end run
APPLESCRIPT
OSA_PID=$!
wait "$OSA_PID"
OSA_STATUS=$?
OSA_PID=""
if [ -f "$OSA_OUT" ]; then
  RESULT="$(<"$OSA_OUT")"
else
  RESULT=""
fi
"$RM" -f "$OSA_OUT" >/dev/null 2>&1 || true

if [ "$OSA_STATUS" -ne 0 ]; then
  write_state "$NOW" "$LAST_SUCCESS" "$LEASE_EXPIRY" "error" "$RESULT" || true
  respond
fi

case "$RESULT" in
  started\|*|refreshed\|*)
    NEW_LEASE=$((NOW + DURATION_SECONDS))
    STATUS="${RESULT%%|*}"
    write_state "$NOW" "$NOW" "$NEW_LEASE" "$STATUS" "" || true
    ;;
  preserved-owned\|*)
    # Confirmed ours and still comfortably inside its lease -- unlike preserved-finite/
    # preserved-special below, the tracked lease is real and unchanged (no restart happened), so
    # keep it instead of clearing it to 0.
    STATUS="${RESULT%%|*}"
    write_state "$NOW" "$LAST_SUCCESS" "$LEASE_EXPIRY" "$STATUS" "" || true
    ;;
  preserved-finite\|*|preserved-special\|*)
    STATUS="${RESULT%%|*}"
    write_state "$NOW" "$LAST_SUCCESS" 0 "$STATUS" "" || true
    ;;
  *)
    write_state "$NOW" "$LAST_SUCCESS" "$LEASE_EXPIRY" "error" "unexpected osascript response: $RESULT" || true
    ;;
esac

respond
