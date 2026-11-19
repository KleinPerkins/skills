#!/bin/bash

dms_owned_root_pids() {
  local root="$1" pid uid command
  while read -r pid; do
    [ -n "$pid" ] || continue
    [ "$pid" -ne "$$" ] && [ "$pid" -ne "$PPID" ] || continue
    uid="$(ps -p "$pid" -o uid= 2>/dev/null | tr -d ' ' || true)"
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [ "$uid" = "$(id -u)" ] || continue
    case "$command" in *"$root"*) printf '%s\n' "$pid" ;; esac
  done < <(pgrep -f "$root" || true)
}

dms_signal_owned_root_pid() {
  local signal="$1" root="$2" pid="$3" uid command group
  uid="$(ps -p "$pid" -o uid= 2>/dev/null | tr -d ' ' || true)"
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [ "$uid" = "$(id -u)" ] || return 1
  case "$command" in *"$root"*) ;; *) return 1 ;; esac
  group="$(ps -p "$pid" -o pgid= 2>/dev/null | tr -d ' ' || true)"
  if [ "$group" = "$pid" ]; then
    kill "-$signal" -- "-$pid" 2>/dev/null || true
  else
    kill "-$signal" "$pid" 2>/dev/null || true
  fi
}

dms_reap_known_owned_root_pid() {
  local root="$1" label="$2" pid="$3" deadline state
  kill -0 "$pid" 2>/dev/null || {
    wait "$pid" 2>/dev/null || true
    return 0
  }
  dms_signal_owned_root_pid TERM "$root" "$pid" || return 1
  deadline=$((SECONDS + 3))
  while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do
    state="$(ps -p "$pid" -o state= 2>/dev/null | tr -d ' ' || true)"
    case "$state" in Z*) wait "$pid" 2>/dev/null || true; return 0 ;; esac
    sleep 0.05
  done
  kill -0 "$pid" 2>/dev/null || {
    wait "$pid" 2>/dev/null || true
    return 0
  }
  dms_signal_owned_root_pid KILL "$root" "$pid" || return 1
  deadline=$((SECONDS + 3))
  while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do
    state="$(ps -p "$pid" -o state= 2>/dev/null | tr -d ' ' || true)"
    case "$state" in Z*) wait "$pid" 2>/dev/null || true; return 0 ;; esac
    sleep 0.05
  done
  kill -0 "$pid" 2>/dev/null && {
    printf '%s: known owned helper could not be reaped\n' "$label" >&2
    return 1
  }
  wait "$pid" 2>/dev/null || true
}

dms_reap_owned_root_helpers() {
  local root="$1" label="$2" expected_cleanup="${3:-0}" leaked=0 pid deadline
  while read -r pid; do
    [ -n "$pid" ] || continue
    leaked=1
    dms_signal_owned_root_pid TERM "$root" "$pid" || return 1
  done < <(dms_owned_root_pids "$root")
  deadline=$((SECONDS + 3))
  while [ -n "$(dms_owned_root_pids "$root")" ] && [ "$SECONDS" -lt "$deadline" ]; do
    sleep 0.05
  done
  while read -r pid; do
    [ -n "$pid" ] || continue
    dms_signal_owned_root_pid KILL "$root" "$pid" || return 1
  done < <(dms_owned_root_pids "$root")
  deadline=$((SECONDS + 3))
  while [ -n "$(dms_owned_root_pids "$root")" ] && [ "$SECONDS" -lt "$deadline" ]; do
    while read -r pid; do
      [ -n "$pid" ] || continue
      wait "$pid" 2>/dev/null || true
    done < <(dms_owned_root_pids "$root")
    sleep 0.05
  done
  [ -z "$(dms_owned_root_pids "$root")" ] || {
    printf '%s: verified owned helper could not be reaped\n' "$label" >&2
    return 1
  }
  [ "$expected_cleanup" -eq 1 ] && return 0
  return "$leaked"
}

dms_unregister_owned_test_apps() {
  local root="$1" app info identifier
  local lsregister
  lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  [ -x "$lsregister" ] || return 0
  [ -d "$root" ] && [ ! -L "$root" ] || return 0
  while IFS= read -r -d '' app; do
    info="$app/Contents/Info.plist"
    [ -f "$info" ] && [ ! -L "$info" ] || continue
    identifier="$(plutil -extract CFBundleIdentifier raw "$info" 2>/dev/null || true)"
    [ "$identifier" = "com.kleinperkins.dev-main-sync" ] || continue
    "$lsregister" -u "$app" >/dev/null 2>&1 || true
  done < <(/usr/bin/find -P "$root" -type d -name '*.app' -prune -print0)
}

dms_remove_owned_root() {
  local root="$1" label="$2" pid uid command deadline
  [ -e "$root" ] || return 0
  dms_unregister_owned_test_apps "$root"
  /bin/rm -rf -- "$root" &
  pid=$!
  kill -0 "$pid" 2>/dev/null || {
    wait "$pid"
    return
  }
  uid="$(ps -p "$pid" -o uid= 2>/dev/null | tr -d ' ' || true)"
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [ -n "$command" ] || {
    wait "$pid"
    return
  }
  [ "$uid" = "$(id -u)" ] || return 1
  case "$command" in *"/bin/rm -rf"*"$root"*) ;; *) return 1 ;; esac
  deadline=$((SECONDS + 15))
  while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do
    sleep 0.05
  done
  if kill -0 "$pid" 2>/dev/null; then
    dms_signal_owned_root_pid KILL "$root" "$pid" || return 1
    deadline=$((SECONDS + 2))
    while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do
      sleep 0.05
    done
  fi
  kill -0 "$pid" 2>/dev/null && {
    printf '%s: root removal exceeded its deadline\n' "$label" >&2
    return 1
  }
  wait "$pid"
}
