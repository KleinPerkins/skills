#!/usr/bin/env python3
"""Lifecycle manager for the Cursor keep-awake capability."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


CAP_DIR = Path(__file__).resolve().parents[1]
DESCRIPTOR_PATH = CAP_DIR / "plugin.json"
META_PATH = CAP_DIR / "meta.yml"
INSTALLER_PATH = CAP_DIR / "install.sh"
RUNTIME_PATH = CAP_DIR / "scripts" / "hooks" / "keep-awake-refill.sh"
MAINTENANCE_WRAPPER_PATH = CAP_DIR / "scripts" / "maintenance" / "keep-awake-maintenance.sh"
BACKUP_SUFFIX = ".keep-awake.bak"
MAX_CAS_RETRIES = 5
MAX_STATE_BYTES = 4096
MAINTENANCE_JOB_ID = "keep-awake-maintenance"
DEFAULT_MAINTENANCE_INTERVAL_SECONDS = 300
DEFAULT_ACTIVITY_WINDOW_SECONDS = 14400
STATE_FIELDS = {
    "last_attempt",
    "last_success",
    "lease_expiry",
    "last_status",
    "last_error",
}
# The caffeinate supplement's sidecar (see caffeinate_state_path()) is a deliberately separate
# file with its own small bounded schema -- state.json's STATE_FIELDS is exact-match validated
# and CAS-guarded, too risky to extend for an unrelated concern (see the plan's Design section).
CAFFEINATE_STATE_FIELDS = {"pid", "expiry", "status"}
CAFFEINATE_STATUS_MAX_CHARS = 64
ACTIVITY_STATE_FIELDS = {"last_hook_activity"}


class LifecycleError(RuntimeError):
    """A safe lifecycle refusal."""


@dataclass(frozen=True)
class HookSnapshot:
    exists: bool
    raw: bytes
    data: dict[str, Any]
    fingerprint: tuple[Any, ...]
    mode: int


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def canonical_json_hash(path: Path = DESCRIPTOR_PATH) -> str:
    data = load_json(path)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def meta_field(key: str, path: Path = META_PATH) -> str:
    prefix = f"{key}:"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def cursor_home() -> Path:
    override = os.environ.get("KEEP_AWAKE_CURSOR_HOME") or os.environ.get("CURSOR_HOME")
    return Path(override).expanduser() if override else Path.home() / ".cursor"


def hooks_json_path() -> Path:
    override = os.environ.get("KEEP_AWAKE_HOOKS_JSON")
    return Path(override).expanduser() if override else cursor_home() / "hooks.json"


def state_root(descriptor: dict[str, Any]) -> Path:
    override = os.environ.get("KEEP_AWAKE_STATE_ROOT")
    raw = override or descriptor["stateRoot"]
    return Path(raw).expanduser()


def state_path(descriptor: dict[str, Any]) -> Path:
    return state_root(descriptor) / "state.json"


def now_seconds() -> int:
    override = os.environ.get("KEEP_AWAKE_NOW")
    if override is not None:
        try:
            return int(override)
        except ValueError:
            pass
    return int(time.time())


def platform_is_darwin() -> bool:
    value = os.environ.get("KEEP_AWAKE_PLATFORM", sys.platform)
    return value.lower() == "darwin"


def maintenance_config(descriptor: dict[str, Any]) -> tuple[bool, int, int]:
    """Return rollback-safe defaults for the optional v1 maintenance extension.

    A descriptor from before this feature remains hook-only: only an explicit boolean true
    installs the timer. Timing defaults let newer lifecycle code inspect an older descriptor
    without making the old install invalid.
    """

    enabled = descriptor.get("maintenanceEnabled") is True
    interval = descriptor.get("maintenanceIntervalSeconds", DEFAULT_MAINTENANCE_INTERVAL_SECONDS)
    activity_window = descriptor.get("activityWindowSeconds", DEFAULT_ACTIVITY_WINDOW_SECONDS)
    return enabled, interval, activity_window


def validate_descriptor(descriptor: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(descriptor, dict):
        return ["plugin.json must contain an object"]
    if descriptor.get("schema") != "kp-keep-awake/v1":
        errors.append("plugin.json schema must be kp-keep-awake/v1")
    if descriptor.get("platform") != "darwin":
        errors.append("plugin.json platform must be darwin")
    backend = descriptor.get("backend")
    if not isinstance(backend, dict):
        errors.append("plugin.json backend must be an object")
    else:
        for key in ("app", "bundleId", "process"):
            if not isinstance(backend.get(key), str) or not backend[key]:
                errors.append(f"plugin.json backend.{key} must be a non-empty string")
        if backend.get("autoLaunch") is not False:
            errors.append("plugin.json backend.autoLaunch must be false")
    if not isinstance(descriptor.get("marker"), str) or not descriptor["marker"]:
        errors.append("plugin.json marker must be a non-empty string")
    for key in ("durationSeconds", "throttleSeconds", "timeoutSeconds"):
        value = descriptor.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"plugin.json {key} must be a positive integer")
    duration = descriptor.get("durationSeconds")
    if isinstance(duration, int) and not isinstance(duration, bool) and duration % 60:
        errors.append("plugin.json durationSeconds must be whole minutes")
    for key in ("displaySleepAllowed", "preventScreenSaver", "caffeinateSupplementEnabled"):
        if not isinstance(descriptor.get(key), bool):
            errors.append(f"plugin.json {key} must be boolean")
    if "maintenanceEnabled" in descriptor and not isinstance(descriptor["maintenanceEnabled"], bool):
        errors.append("plugin.json maintenanceEnabled must be boolean")
    interval = descriptor.get("maintenanceIntervalSeconds", DEFAULT_MAINTENANCE_INTERVAL_SECONDS)
    if (
        not isinstance(interval, int)
        or isinstance(interval, bool)
        or not (60 <= interval <= 2_147_483_647)
    ):
        errors.append(
            "plugin.json maintenanceIntervalSeconds must be an integer from 60 to 2147483647"
        )
    activity_window = descriptor.get("activityWindowSeconds", DEFAULT_ACTIVITY_WINDOW_SECONDS)
    if not isinstance(activity_window, int) or isinstance(activity_window, bool) or activity_window <= 0:
        errors.append("plugin.json activityWindowSeconds must be a positive integer")
    elif isinstance(interval, int) and not isinstance(interval, bool) and activity_window < interval:
        errors.append(
            "plugin.json activityWindowSeconds must be at least maintenanceIntervalSeconds"
        )
    state_root_raw = descriptor.get("stateRoot")
    if not isinstance(state_root_raw, str) or not state_root_raw:
        errors.append("plugin.json stateRoot must be a non-empty string")
    elif not (state_root_raw.startswith("~/") or state_root_raw.startswith("/")):
        # Mirrors the runtime hook's own case statement (keep-awake-refill.sh), which silently
        # fail-opens (no-ops) on any stateRoot lacking a leading ~/ or /. Catch that shape here so
        # it surfaces as a descriptor error at doctor/apply time instead of a silent runtime no-op.
        errors.append("plugin.json stateRoot must start with '~/' or '/'")
    events = descriptor.get("events")
    expected_events = [
        {"event": "beforeSubmitPrompt", "matcher": "UserPromptSubmit"},
        {"event": "preToolUse"},
    ]
    if events != expected_events:
        errors.append("plugin.json events must declare beforeSubmitPrompt/UserPromptSubmit and preToolUse")
    return errors


def desired_hook_rows(descriptor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for event_spec in descriptor["events"]:
        event = event_spec["event"]
        row: dict[str, Any] = {
            "command": f"./skills/keep-awake/scripts/hooks/keep-awake-refill.sh {event}",
            "type": "command",
            "timeout": descriptor["timeoutSeconds"],
            "failClosed": False,
            "description": descriptor["marker"],
        }
        if "matcher" in event_spec:
            row["matcher"] = event_spec["matcher"]
        rows[event] = row
    return rows


def maintenance_program_path() -> Path:
    # launchd must never retain a Cursor worktree path that may be cleaned up after this session.
    # The bootstrap-managed stable link survives source updates and points at the durable primary.
    return cursor_home() / "skills" / "keep-awake" / "scripts" / "maintenance" / "keep-awake-maintenance.sh"


def local_jobs_cli_path() -> Path | None:
    override = os.environ.get("KEEP_AWAKE_LOCAL_JOBS")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() and os.access(path, os.X_OK) else None
    candidates = (
        CAP_DIR.parents[1] / "skills" / "local-jobs" / "scripts" / "local-jobs.sh",
        Path.home() / ".claude" / "skills" / "local-jobs" / "scripts" / "local-jobs.sh",
        Path.home() / ".cursor" / "skills" / "local-jobs" / "scripts" / "local-jobs.sh",
        Path.home() / ".codex" / "skills" / "local-jobs" / "scripts" / "local-jobs.sh",
    )
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def local_jobs_integration_disabled() -> bool:
    return os.environ.get("KEEP_AWAKE_LOCAL_JOBS_DISABLE") == "1"


def _run_local_jobs(*args: str) -> subprocess.CompletedProcess[str]:
    cli = local_jobs_cli_path()
    if cli is None:
        raise LifecycleError("local-jobs CLI is unavailable; maintenance timer was not changed")
    try:
        proc = subprocess.run(
            [str(cli), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LifecycleError(f"local-jobs {' '.join(args)} failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise LifecycleError(
            f"local-jobs {' '.join(args)} failed with rc={proc.returncode}: "
            f"{detail or '<no output>'}"
        )
    return proc


def local_jobs_view() -> dict[str, Any]:
    proc = _run_local_jobs("view-jobs", "--json")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LifecycleError(f"local-jobs view-jobs emitted malformed JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("instances"), list):
        raise LifecycleError("local-jobs view-jobs payload must contain an instances array")
    if any(not isinstance(row, dict) for row in payload["instances"]):
        raise LifecycleError("local-jobs view-jobs instances must be objects")
    return payload


def _maintenance_instance(payload: dict[str, Any]) -> dict[str, Any] | None:
    instances = payload["instances"]
    quarantined = [
        row
        for row in instances
        if row.get("type") == "command" and row.get("role") == "error"
    ]
    if quarantined:
        reason = (quarantined[0].get("error") or {}).get("reason", "unknown command-type error")
        raise LifecycleError(f"local-jobs command type is quarantined: {reason}")
    matches = [row for row in instances if row.get("id") == MAINTENANCE_JOB_ID]
    if len(matches) > 1:
        raise LifecycleError(
            f"local-jobs contains {len(matches)} rows for globally unique id {MAINTENANCE_JOB_ID}"
        )
    if not matches:
        return None
    row = matches[0]
    if row.get("role") == "error":
        reason = (row.get("error") or {}).get("reason", "unknown error")
        raise LifecycleError(f"maintenance timer is quarantined: {reason}")
    if row.get("type") != "command":
        raise LifecycleError(
            f"local-jobs id {MAINTENANCE_JOB_ID} is owned by type {row.get('type')!r}; "
            "refusing to replace it"
        )
    return row


def _interval_seconds(value: Any) -> int | None:
    if isinstance(value, str) and value.startswith("{"):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    seconds = value.get("seconds")
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        return None
    if value.get("kind") not in (None, "interval"):
        return None
    return seconds


def maintenance_instance_errors(
    descriptor: dict[str, Any],
    row: dict[str, Any],
    *,
    require_loaded: bool,
) -> list[str]:
    _enabled, interval, _activity_window = maintenance_config(descriptor)
    errors: list[str] = []
    expected_program = str(maintenance_program_path())
    if row.get("program") != expected_program:
        errors.append(
            f"maintenance timer program mismatch ({row.get('program')!r} != {expected_program!r})"
        )
    if row.get("args") != []:
        errors.append("maintenance timer args must be empty")
    if _interval_seconds(row.get("schedule")) != interval:
        errors.append(f"maintenance timer interval must be {interval}s")
    if row.get("execution_mode") != "scheduled":
        errors.append("maintenance timer execution_mode must be scheduled")
    if row.get("enabled") is not True:
        errors.append("maintenance timer must be enabled")
    if (
        require_loaded
        and platform_is_darwin()
        and os.environ.get("LOCAL_JOBS_LAUNCHD_DISABLE") != "1"
        and row.get("launchd_loaded") is not True
    ):
        errors.append("maintenance timer launchd agent is not loaded")
    label = row.get("launchd_label")
    if not isinstance(label, str) or not label:
        errors.append("maintenance timer launchd label is missing")
    return errors


def _add_maintenance_job(descriptor: dict[str, Any]) -> None:
    _enabled, interval, _activity_window = maintenance_config(descriptor)
    program = maintenance_program_path()
    if not program.is_file() or not os.access(program, os.X_OK):
        raise LifecycleError(f"maintenance wrapper is missing or not executable: {program}")
    _run_local_jobs(
        "add-job",
        "--type",
        "command",
        "--id",
        MAINTENANCE_JOB_ID,
        "--program",
        str(program),
        "--interval-seconds",
        str(interval),
        "--execution-mode",
        "scheduled",
        "--display-name",
        "Keep Awake maintenance",
        "--description",
        "Refreshes bounded keep-awake assertions only after recent Cursor hook activity.",
        "--enabled",
        "true",
    )


def _delete_maintenance_job() -> None:
    _run_local_jobs(
        "delete-job",
        "--type",
        "command",
        "--id",
        MAINTENANCE_JOB_ID,
        "--confirm",
    )


def reconcile_maintenance_job(descriptor: dict[str, Any]) -> str:
    if local_jobs_integration_disabled():
        return "maintenance timer integration disabled by environment"
    enabled, _interval, _activity_window = maintenance_config(descriptor)
    if not enabled:
        return remove_maintenance_job(descriptor)

    row = _maintenance_instance(local_jobs_view())
    action = "already reconciled"
    if row is None:
        _add_maintenance_job(descriptor)
        action = "installed"
    else:
        config_errors = maintenance_instance_errors(descriptor, row, require_loaded=False)
        if config_errors:
            # The command handler cannot clear an existing args list through update-job. This ID
            # is exclusively owned by keep-awake, so replace the one job atomically enough for a
            # finite assertion system: hooks remain live throughout and verification follows.
            _delete_maintenance_job()
            _add_maintenance_job(descriptor)
            action = "replaced drifted"
        elif (
            platform_is_darwin()
            and os.environ.get("LOCAL_JOBS_LAUNCHD_DISABLE") != "1"
            and row.get("launchd_loaded") is not True
        ):
            _run_local_jobs(
                "repair-job", "--type", "command", "--id", MAINTENANCE_JOB_ID
            )
            action = "repaired"

    verified = _maintenance_instance(local_jobs_view())
    if verified is None:
        raise LifecycleError("maintenance timer vanished after local-jobs reconciliation")
    errors = maintenance_instance_errors(descriptor, verified, require_loaded=True)
    if errors:
        raise LifecycleError("; ".join(errors))
    return f"{action} maintenance timer {verified.get('launchd_label')}"


def remove_maintenance_job(_descriptor: dict[str, Any]) -> str:
    if local_jobs_integration_disabled():
        return "maintenance timer integration disabled by environment"
    row = _maintenance_instance(local_jobs_view())
    if row is None:
        return "no maintenance timer present"
    _delete_maintenance_job()
    if _maintenance_instance(local_jobs_view()) is not None:
        raise LifecycleError("maintenance timer still present after local-jobs delete")
    return f"removed maintenance timer {row.get('launchd_label')}"


def maintenance_job_status(descriptor: dict[str, Any]) -> tuple[str, list[str]]:
    if local_jobs_integration_disabled():
        return "maintenance timer: integration disabled by environment", []
    enabled, interval, activity_window = maintenance_config(descriptor)
    if not enabled:
        return "maintenance timer: disabled via plugin.json", []
    try:
        row = _maintenance_instance(local_jobs_view())
    except LifecycleError as exc:
        return "maintenance timer: unavailable", [str(exc)]
    if row is None:
        return "maintenance timer: missing", ["maintenance timer is not installed"]
    errors = maintenance_instance_errors(descriptor, row, require_loaded=True)
    return (
        f"maintenance timer: {row.get('launchd_label')} every {interval}s "
        f"(activity window {activity_window}s, loaded={row.get('launchd_loaded')})",
        errors,
    )


def legacy_hook_rows(home: Path | None = None) -> dict[str, dict[str, Any]]:
    root = home or cursor_home()
    return {
        "beforeSubmitPrompt": {
            "command": str(root / "hooks" / "caffeine-on.sh"),
            "type": "command",
            "matcher": "UserPromptSubmit",
            "timeout": 10,
            "failClosed": False,
            "description": "amphetamine-keep-awake-on",
        },
        "stop": {
            "command": str(root / "hooks" / "caffeine-off.sh"),
            "type": "command",
            "timeout": 10,
            "failClosed": False,
            "description": "amphetamine-keep-awake-off",
        },
    }


def validate_hooks_shape(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LifecycleError(f"{path} must contain a JSON object")
    version = data.get("version")
    if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
        raise LifecycleError(f"{path} version must be an integer")
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise LifecycleError(f"{path} hooks must be an object")
    for event, rows in hooks.items():
        if not isinstance(event, str) or not isinstance(rows, list):
            raise LifecycleError(f"{path} hook event values must be arrays")
        if any(not isinstance(row, dict) for row in rows):
            raise LifecycleError(f"{path} hook rows must be objects")
    return data


def file_fingerprint(path: Path) -> tuple[Any, ...]:
    try:
        raw = path.read_bytes()
        st = path.stat()
    except FileNotFoundError:
        return ("absent",)
    return (
        "present",
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        hashlib.sha256(raw).hexdigest(),
    )


def read_hook_snapshot(path: Path) -> HookSnapshot:
    try:
        raw = path.read_bytes()
        st = path.stat()
    except FileNotFoundError:
        data: dict[str, Any] = {"version": 1, "hooks": {}}
        return HookSnapshot(False, b"", data, ("absent",), 0o600)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"refusing malformed {path}: {exc}") from exc
    validated = validate_hooks_shape(data, path)
    fingerprint = (
        "present",
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        hashlib.sha256(raw).hexdigest(),
    )
    return HookSnapshot(True, raw, validated, fingerprint, stat.S_IMODE(st.st_mode))


def is_owned_row(row: dict[str, Any], descriptor: dict[str, Any]) -> bool:
    return row.get("description") == descriptor["marker"]


def transform_hooks(
    data: dict[str, Any],
    descriptor: dict[str, Any],
    *,
    install: bool,
    remove_legacy: bool,
) -> dict[str, Any]:
    out = copy.deepcopy(data)
    hooks = out.get("hooks")
    if hooks is None:
        if not install:
            return out
        hooks = {}
        out["hooks"] = hooks

    legacy = legacy_hook_rows()
    for event in list(hooks):
        rows = hooks[event]
        filtered = [
            row
            for row in rows
            if not is_owned_row(row, descriptor)
            and not (remove_legacy and event in legacy and row == legacy[event])
        ]
        if filtered:
            hooks[event] = filtered
        elif filtered != rows:
            del hooks[event]

    if install:
        if "version" not in out:
            out = {"version": 1, **out}
            hooks = out["hooks"]
        for event, row in desired_hook_rows(descriptor).items():
            hooks.setdefault(event, []).append(row)
    return out


def json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def stage_bytes(path: Path, payload: bytes, mode: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        return tmp
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path, payload: bytes, mode: int = 0o600) -> None:
    tmp = stage_bytes(path, payload, mode)
    try:
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def reconcile_hooks(
    descriptor: dict[str, Any],
    *,
    install: bool,
    remove_legacy: bool,
    path: Path | None = None,
    pre_commit: Callable[[Path, int], None] | None = None,
) -> tuple[bool, str]:
    target = path or hooks_json_path()
    for attempt in range(MAX_CAS_RETRIES):
        snapshot = read_hook_snapshot(target)
        updated = transform_hooks(
            snapshot.data,
            descriptor,
            install=install,
            remove_legacy=remove_legacy,
        )
        if updated == snapshot.data:
            return False, f"already reconciled: {target}"

        payload = json_bytes(updated)
        if pre_commit is not None:
            pre_commit(target, attempt)
        if file_fingerprint(target) != snapshot.fingerprint:
            continue

        staged = stage_bytes(target, payload, snapshot.mode)
        try:
            if file_fingerprint(target) != snapshot.fingerprint:
                continue
            os.replace(staged, target)
        finally:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass

        if target.read_bytes() != payload:
            continue
        if snapshot.exists:
            backup = target.with_name(target.name + BACKUP_SUFFIX)
            atomic_write_bytes(backup, snapshot.raw, snapshot.mode)
        return True, f"updated: {target}"
    raise LifecycleError(f"{target} changed concurrently {MAX_CAS_RETRIES} times; no update was forced")


def validate_owned_state(path: Path, descriptor: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, []
    errors: list[str] = []
    try:
        st = path.lstat()
    except OSError as exc:
        return None, [f"owned state unreadable: {exc}"]
    if not stat.S_ISREG(st.st_mode):
        return None, ["owned state must be a regular file"]
    if st.st_size > MAX_STATE_BYTES:
        return None, [f"owned state exceeds {MAX_STATE_BYTES} bytes"]
    if stat.S_IMODE(st.st_mode) & 0o077:
        errors.append("owned state permissions must not allow group/other access")
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, errors + [f"owned state is malformed: {exc}"]
    if not isinstance(data, dict):
        return None, errors + ["owned state must contain a JSON object"]
    if set(data) != STATE_FIELDS:
        errors.append("owned state fields do not match the bounded schema")
    for key in ("last_attempt", "last_success", "lease_expiry"):
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"owned state {key} must be a non-negative integer")
    for key, limit in (("last_status", 64), ("last_error", 512)):
        value = data.get(key)
        if not isinstance(value, str) or len(value) > limit:
            errors.append(f"owned state {key} must be a string of at most {limit} characters")
    lease = data.get("lease_expiry")
    success = data.get("last_success")
    if (
        isinstance(lease, int)
        and not isinstance(lease, bool)
        and lease > 0
        and (not isinstance(success, int) or isinstance(success, bool) or success <= 0 or lease <= success)
    ):
        errors.append("owned state lease_expiry must follow last_success")
    return data, errors


def atomic_write_state(path: Path, data: dict[str, Any]) -> None:
    root = path.parent
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    atomic_write_bytes(path, json_bytes(data), 0o600)


def clear_expired_ownership(
    descriptor: dict[str, Any],
    *,
    pre_commit: Callable[[Path, int], None] | None = None,
) -> tuple[bool, str]:
    # CAS-guarded like reconcile_hooks(): --repair runs alongside a live runtime hook that can
    # write state.json at any moment, so a blind read-then-write here could silently clobber a
    # concurrent runtime write with our stale read (TOCTOU). Fingerprint-check before AND
    # immediately before the atomic replace, and retry on drift instead of forcing the write.
    path = state_path(descriptor)
    for attempt in range(MAX_CAS_RETRIES):
        fingerprint = file_fingerprint(path)
        state_data, errors = validate_owned_state(path, descriptor)
        if errors:
            raise LifecycleError("; ".join(errors))
        if state_data is None:
            return False, "no owned state present"
        lease = state_data["lease_expiry"]
        if not lease or lease > now_seconds():
            return False, "owned state is current"
        updated = dict(state_data)
        updated["lease_expiry"] = 0
        updated["last_status"] = "ownership-expired"
        updated["last_error"] = ""
        payload = json_bytes(updated)

        if pre_commit is not None:
            pre_commit(path, attempt)
        if file_fingerprint(path) != fingerprint:
            continue
        staged = stage_bytes(path, payload, 0o600)
        try:
            if file_fingerprint(path) != fingerprint:
                continue
            os.replace(staged, path)
        finally:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass
        if path.read_bytes() != payload:
            continue
        return True, "cleared expired ownership lease"
    raise LifecycleError(f"{path} changed concurrently {MAX_CAS_RETRIES} times; ownership lease was not cleared")


def remove_owned_state(descriptor: dict[str, Any]) -> bool:
    path = state_path(descriptor)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return True


def activity_state_path(descriptor: dict[str, Any]) -> Path:
    return state_root(descriptor) / "activity.json"


def validate_activity_state(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, []
    errors: list[str] = []
    try:
        st = path.lstat()
    except OSError as exc:
        return None, [f"owned activity state unreadable: {exc}"]
    if not stat.S_ISREG(st.st_mode):
        return None, ["owned activity state must be a regular file"]
    if st.st_size > MAX_STATE_BYTES:
        return None, [f"owned activity state exceeds {MAX_STATE_BYTES} bytes"]
    if stat.S_IMODE(st.st_mode) & 0o077:
        errors.append("owned activity state permissions must not allow group/other access")
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, errors + [f"owned activity state is malformed: {exc}"]
    if not isinstance(data, dict):
        return None, errors + ["owned activity state must contain a JSON object"]
    if set(data) != ACTIVITY_STATE_FIELDS:
        errors.append("owned activity state fields do not match the bounded schema")
    value = data.get("last_hook_activity")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append("owned activity state last_hook_activity must be a non-negative integer")
    return data, errors


def remove_activity_state(descriptor: dict[str, Any]) -> bool:
    try:
        activity_state_path(descriptor).unlink()
    except FileNotFoundError:
        return False
    return True


def repair_activity_state(descriptor: dict[str, Any]) -> str:
    path = activity_state_path(descriptor)
    data, errors = validate_activity_state(path)
    if data is None and not errors:
        return "no owned activity state present"
    if errors:
        remove_activity_state(descriptor)
        return "removed malformed owned activity state"
    return "owned activity state is valid"


def describe_activity_status(
    descriptor: dict[str, Any], state_data: dict[str, Any] | None
) -> tuple[str, list[str]]:
    enabled, _interval, activity_window = maintenance_config(descriptor)
    if not enabled:
        return "Cursor activity lease: maintenance disabled", []
    if state_data is None:
        return "Cursor activity lease: not yet observed (cold start)", []
    timestamp = state_data["last_hook_activity"]
    age = now_seconds() - timestamp
    if age < 0:
        return (
            f"Cursor activity lease: future timestamp {timestamp}",
            ["Cursor activity lease timestamp is in the future"],
        )
    status = "active" if age <= activity_window else "expired"
    return f"Cursor activity lease: {status} (last hook {age}s ago)", []


def stop_fence_path(descriptor: dict[str, Any]) -> Path:
    return state_root(descriptor) / "stop.fence"


def write_stop_fence(descriptor: dict[str, Any]) -> None:
    root = state_root(descriptor)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    atomic_write_bytes(stop_fence_path(descriptor), b"uninstalling\n", 0o600)


def remove_stop_fence(descriptor: dict[str, Any]) -> bool:
    path = stop_fence_path(descriptor)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _read_lock_field(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def acquire_runtime_lock(descriptor: dict[str, Any]) -> str:
    root = state_root(descriptor)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock = root / ".lock"
    owner = f"manager-{os.getpid()}-{time.time_ns()}"
    deadline = time.monotonic() + max(1, descriptor["timeoutSeconds"])
    stale_after = descriptor["throttleSeconds"] * 2
    while True:
        try:
            lock.mkdir()
        except FileExistsError:
            stamp_raw = _read_lock_field(lock / "acquired")
            prior_owner = _read_lock_field(lock / "owner")
            try:
                stamp = int(stamp_raw)
            except ValueError:
                stamp = None
            observed = now_seconds()
            if stamp is not None and observed >= stamp and observed - stamp > stale_after:
                if (
                    _read_lock_field(lock / "acquired") == stamp_raw
                    and _read_lock_field(lock / "owner") == prior_owner
                ):
                    try:
                        shutil.rmtree(lock)
                    except OSError:
                        pass
                    if not lock.exists():
                        continue
        else:
            try:
                (lock / "owner").write_text(owner + "\n", encoding="utf-8")
                (lock / "acquired").write_text(str(now_seconds()) + "\n", encoding="utf-8")
                os.chmod(lock / "owner", 0o600)
                os.chmod(lock / "acquired", 0o600)
                return owner
            except OSError:
                shutil.rmtree(lock, ignore_errors=True)
                raise
        if time.monotonic() >= deadline:
            raise LifecycleError("runtime lock remained busy during lifecycle cleanup")
        time.sleep(0.05)


def release_runtime_lock(descriptor: dict[str, Any], owner: str) -> None:
    lock = state_root(descriptor) / ".lock"
    if _read_lock_field(lock / "owner") == owner:
        shutil.rmtree(lock, ignore_errors=True)


def caffeinate_state_path(descriptor: dict[str, Any]) -> Path:
    return state_root(descriptor) / "caffeinate.json"


def validate_caffeinate_state(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate the caffeinate.json sidecar written by keep-awake-refill.sh's own bash-native
    write_caffeinate_state(). Deliberately mirrors validate_owned_state()'s structure (same
    file-shape/permission/size checks) so the two validators enforce one schema by construction,
    not by convention -- but pid must be > 0, not the >= 0 bound validate_owned_state uses for
    state.json's counters: kill -0 / kill -TERM on pid 0 targets the entire calling process
    group, not one process, so a corrupted or mistyped sidecar must never be allowed to reach
    that value.
    """
    if not path.exists():
        return None, []
    errors: list[str] = []
    try:
        st = path.lstat()
    except OSError as exc:
        return None, [f"owned caffeinate state unreadable: {exc}"]
    if not stat.S_ISREG(st.st_mode):
        return None, ["owned caffeinate state must be a regular file"]
    if st.st_size > MAX_STATE_BYTES:
        return None, [f"owned caffeinate state exceeds {MAX_STATE_BYTES} bytes"]
    if stat.S_IMODE(st.st_mode) & 0o077:
        errors.append("owned caffeinate state permissions must not allow group/other access")
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, errors + [f"owned caffeinate state is malformed: {exc}"]
    if not isinstance(data, dict):
        return None, errors + ["owned caffeinate state must contain a JSON object"]
    if set(data) != CAFFEINATE_STATE_FIELDS:
        errors.append("owned caffeinate state fields do not match the bounded schema")
    pid = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        errors.append("owned caffeinate state pid must be a positive integer")
    expiry = data.get("expiry")
    if not isinstance(expiry, int) or isinstance(expiry, bool) or expiry < 0:
        errors.append("owned caffeinate state expiry must be a non-negative integer")
    status = data.get("status")
    if not isinstance(status, str) or not status or len(status) > CAFFEINATE_STATUS_MAX_CHARS:
        errors.append(
            f"owned caffeinate state status must be a non-empty string of at most "
            f"{CAFFEINATE_STATUS_MAX_CHARS} characters"
        )
    return data, errors


def remove_caffeinate_state(descriptor: dict[str, Any]) -> bool:
    path = caffeinate_state_path(descriptor)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _remove_caffeinate_state_if_pid_unchanged(descriptor: dict[str, Any], expected_pid: int) -> bool:
    """Guards a caffeinate-sidecar removal against a concurrent runtime hook tick that retracked a
    different, live pid while this call was validating or signaling `expected_pid` -- e.g.
    _stop_owned_caffeinate's up-to-1s kill-confirmation poll below is a wide enough window for a
    live hook tick to land in the middle of it and refresh the sidecar to a new pid. Re-reads the
    sidecar immediately before deleting it: only refuses to remove when it NOW validates cleanly
    AND names a pid different from the one this call reasoned about -- that pid is a legitimately
    newer, live, owned process, so leave it tracked rather than silently orphaning it.

    Returns True whenever no trace of `expected_pid` is left behind afterward -- that covers both
    an actual removal and a sidecar that was already gone by the time this re-read it (e.g. a
    concurrent bash-side cleanup got there first); callers use False to mean specifically "left in
    place because it now names a different pid", never "unlink() itself reported nothing to do".
    """
    current, errors = validate_caffeinate_state(caffeinate_state_path(descriptor))
    if not errors and current is not None and current["pid"] != expected_pid:
        return False
    remove_caffeinate_state(descriptor)
    return True


def caffeinate_binary_path() -> Path:
    return Path(os.environ.get("KEEP_AWAKE_CAFFEINATE", "/usr/bin/caffeinate"))


def ps_binary_path() -> Path:
    return Path(os.environ.get("KEEP_AWAKE_PS", "/bin/ps"))


def caffeinate_process_alive(pid: int) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists (owned by someone else) -- liveness alone does not imply ownership; the identity
        # check in caffeinate_alive_and_owned() below is what actually gates ownership.
        return True
    return True


def caffeinate_process_identity_matches(pid: int) -> bool:
    """`ps -p PID -o comm=` on macOS reports the full executable path (e.g. /usr/bin/caffeinate),
    not a bare command name -- confirmed empirically, not assumed -- so this matches either shape
    rather than requiring an exact "caffeinate" string.
    """
    ps = ps_binary_path()
    if not os.access(ps, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [str(ps), "-p", str(pid), "-o", "comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    comm = proc.stdout.strip()
    return comm == "caffeinate" or comm.endswith("/caffeinate")


def caffeinate_alive_and_owned(pid: Any) -> bool:
    """Liveness (kill -0) AND identity (ps comm=) together, guarding against PID reuse -- the
    same two-part check the runtime hook's own caffeinate_alive_and_owned() (bash) performs
    before ever spawning, refreshing, or killing a tracked caffeinate process.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    return caffeinate_process_alive(pid) and caffeinate_process_identity_matches(pid)


def _stop_owned_caffeinate(descriptor: dict[str, Any], pid: int) -> str:
    """Shared kill-then-confirm sequence for an alive, identity-matched, owned caffeinate pid,
    used by both uninstall_caffeinate_state() and repair_caffeinate_state() (steps (4)-(5) of the
    plan's run_uninstall sequence). Mirrors remove_owned_state's already-gone-is-success pattern:
    a kill failing because the process is already gone is not an error. Never deletes the sidecar
    for a pid that might still be running -- a PermissionError leaves it in place with a warning
    printed by the caller, so tracking for a possibly-still-alive process is never silently lost.
    The up-to-1s poll below is itself a wide enough window for a live runtime hook tick to refresh
    the sidecar to a new pid while this function is still waiting on the old one to die, so the
    final removal is guarded by _remove_caffeinate_state_if_pid_unchanged rather than an
    unconditional unlink -- see its own docstring.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        return f"owned caffeinate process {pid} could not be signaled (permission denied); state left in place"
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and caffeinate_alive_and_owned(pid):
        time.sleep(0.02)
    if caffeinate_alive_and_owned(pid):
        return f"owned caffeinate process {pid} did not exit after SIGTERM; state left in place"
    if _remove_caffeinate_state_if_pid_unchanged(descriptor, pid):
        return f"stopped owned caffeinate process {pid}"
    return (
        f"stopped owned caffeinate process {pid}, but tracked state now refers to a different "
        "pid (left in place)"
    )


def uninstall_caffeinate_state(descriptor: dict[str, Any]) -> str:
    """Non-fatal caffeinate sidecar cleanup for run_uninstall. Never raises -- the caller's
    hooks-reconcile and state.json removal must run exactly as they do today regardless of this
    outcome (see the plan's exact-sequencing note for run_uninstall).
    """
    try:
        path = caffeinate_state_path(descriptor)
        if not path.exists():
            return "no owned caffeinate state present"
        data, errors = validate_caffeinate_state(path)
        if errors or data is None:
            # No trustworthy pid to check or signal -- nothing safe to kill, but still leave no
            # residue behind (mirrors remove_owned_state's unconditional unlink for state.json).
            remove_caffeinate_state(descriptor)
            return "removed malformed owned caffeinate state (nothing to signal)"
        pid = data["pid"]
        if not caffeinate_alive_and_owned(pid):
            remove_caffeinate_state(descriptor)
            return "removed stale owned caffeinate state (nothing to signal)"
        return _stop_owned_caffeinate(descriptor, pid)
    except Exception as exc:  # pragma: no cover - defense in depth; this function is written to never raise
        return f"caffeinate cleanup failed unexpectedly (non-fatal): {exc}"


def repair_caffeinate_state(descriptor: dict[str, Any]) -> str:
    """Mirrors clear_expired_ownership's Amphetamine-side "stale but still tracked as active"
    repair, for the caffeinate sidecar: a tracked expiry that has already passed means the
    caffeinate process should have self-expired (-t) by now. A still-alive pid found past its own
    timeout is cross-checked for identity before ever being touched -- past its own timeout, a
    still-alive pid is far more likely a reused pid than the real (overdue) caffeinate, so a
    mismatch clears the sidecar without a kill; only a genuine identity match is signaled, via the
    same kill-then-confirm sequence run_uninstall uses.
    """
    try:
        path = caffeinate_state_path(descriptor)
        if not path.exists():
            return "no owned caffeinate state present"
        data, errors = validate_caffeinate_state(path)
        if errors or data is None:
            return "owned caffeinate state present but malformed; run doctor for details"
        if data["expiry"] > now_seconds():
            return "owned caffeinate state is current"
        pid = data["pid"]
        if not caffeinate_alive_and_owned(pid):
            remove_caffeinate_state(descriptor)
            return "removed expired owned caffeinate state"
        return _stop_owned_caffeinate(descriptor, pid)
    except Exception as exc:  # pragma: no cover - defense in depth; this function is written to never raise
        return f"caffeinate repair failed unexpectedly (non-fatal): {exc}"


def describe_caffeinate_status(
    descriptor: dict[str, Any], state_data: dict[str, Any] | None
) -> tuple[str, list[str]]:
    """Doctor's unconditional caffeinate status line plus any liveness/identity mismatch.

    Called regardless of Amphetamine's install/run status (unlike the READY/dormant/inactive
    block above it in run_doctor) so a stale tracked pid is caught even while Amphetamine itself
    is quit. Performs an ACTIVE kill -0 + ps-identity cross-check against the tracked pid -- not
    just an echo of sidecar contents -- so this is what turns the one-time manual pmset check
    under the plan's Verification section into a permanent, repeatable regression detector for the
    display-sleep-during-refresh bug this supplement exists to close. Never flags an error solely
    for "no caffeinate tracked yet" (a legitimate cold-start state) or while the supplement is
    disabled via plugin.json.
    """
    if descriptor.get("caffeinateSupplementEnabled") is not True:
        return "caffeinate supplement: disabled via plugin.json", []
    if state_data is None:
        return "caffeinate supplement: not yet tracked (cold start)", []
    pid = state_data["pid"]
    status = state_data["status"]
    remaining = state_data["expiry"] - now_seconds()
    if caffeinate_alive_and_owned(pid):
        return (
            f"caffeinate supplement: pid {pid} alive and owned (status={status}, "
            f"expires in {remaining}s)",
            [],
        )
    return (
        f"caffeinate supplement: pid {pid} (status={status}) is tracked but NOT alive/owned",
        [f"caffeinate supplement mismatch: tracked pid {pid} is not alive or not identity-matched"],
    )


def backend_app_path(descriptor: dict[str, Any]) -> Path:
    override = os.environ.get("KEEP_AWAKE_APP_PATH")
    if override:
        return Path(override).expanduser()
    return Path("/Applications") / f"{descriptor['backend']['app']}.app"


def backend_running(descriptor: dict[str, Any]) -> bool:
    override = os.environ.get("KEEP_AWAKE_PROCESS_RUNNING")
    if override is not None:
        return override.lower() in {"1", "true", "yes"}
    pgrep = Path("/usr/bin/pgrep")
    if not pgrep.exists():
        return False
    try:
        proc = subprocess.run(
            [str(pgrep), "-x", descriptor["backend"]["process"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


CLOSED_DISPLAY_MODE_SCRIPT = (
    'using terms from application "Amphetamine"\n'
    '\ttell application id "{bundle_id}"\n'
    "\t\treturn closed display mode enabled\n"
    "\tend tell\n"
    "end using terms from\n"
)


def closed_display_mode_status(descriptor: dict[str, Any]) -> str:
    """Read-only probe of Amphetamine's "Allow System to Sleep When Display is Closed" setting.

    Per Amphetamine.sdef, the `closed display mode enabled` AppleScript command is READ-ONLY and
    its boolean is INVERTED from the Preferences checkbox: checkbox CHECKED (the setting that lets
    the Mac sleep the instant the lid/display closes) reads back as false here. Returns "enabled"
    (checkbox unchecked -- healthy), "disabled" (checkbox checked -- the Mac will sleep on
    lid/display close regardless of an active keep-awake session), or "unknown" when the state
    cannot be determined. Callers must treat "unknown" as fail-safe, never as "disabled".

    This deliberately never calls the sdef's *mutating* `enable closed display mode` / `disable
    closed display mode` commands: Amphetamine's own docs warn that toggling this via AppleScript
    can surface a one-time system warning dialog, and instruct flipping it via the UI first
    specifically so a human can dismiss that dialog with "Do Not Show This Message Again" before
    anything automated ever touches it. This capability treats the preference as a human-driven,
    one-time manual setting: doctor only detects and explains it, it never flips it.

    Also refuses to probe unless Amphetamine is already confirmed running via backend_running():
    addressing a not-running app with `tell application id` auto-launches it, which would silently
    violate this capability's backend.autoLaunch:false contract merely by running doctor.
    """
    if not backend_running(descriptor):
        return "unknown"
    osascript = Path(os.environ.get("KEEP_AWAKE_OSASCRIPT", "/usr/bin/osascript"))
    if not osascript.exists():
        return "unknown"
    script = CLOSED_DISPLAY_MODE_SCRIPT.format(bundle_id=descriptor["backend"]["bundleId"])
    try:
        proc = subprocess.run(
            [str(osascript), "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=descriptor["timeoutSeconds"],
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    result = proc.stdout.strip().lower()
    if result == "true":
        return "enabled"
    if result == "false":
        return "disabled"
    return "unknown"


LEGACY_MARKER_PREFIX = "amphetamine-keep-awake-"


def is_legacy_signature_row(row: dict[str, Any]) -> bool:
    """Looser-than-exact-match legacy detection, for doctor only.

    transform_hooks()'s removal path stays conservatively exact-match-only (dict equality) so it
    never deletes a row it cannot prove is the untouched legacy row. This signature match is
    doctor-only: it flags a near-miss legacy row (hand-edited, or from an older predecessor
    version) that therefore survived removal and would otherwise be invisible to doctor too.
    """
    command = row.get("command")
    if isinstance(command, str) and ("caffeine-on.sh" in command or "caffeine-off.sh" in command):
        return True
    description = row.get("description")
    return isinstance(description, str) and description.startswith(LEGACY_MARKER_PREFIX)


def doctor_hook_errors(descriptor: dict[str, Any]) -> list[str]:
    path = hooks_json_path()
    if not path.exists():
        return [f"{path} is missing"]
    try:
        snapshot = read_hook_snapshot(path)
    except LifecycleError as exc:
        return [str(exc)]
    hooks = snapshot.data.get("hooks", {})
    expected = desired_hook_rows(descriptor)
    errors: list[str] = []
    total_owned = 0
    for event, rows in hooks.items():
        owned = [row for row in rows if is_owned_row(row, descriptor)]
        total_owned += len(owned)
        if event in expected:
            if len(owned) != 1:
                errors.append(f"{event} must contain exactly one owned row (found {len(owned)})")
            elif owned[0] != expected[event]:
                errors.append(f"{event} owned row does not match plugin.json")
        elif owned:
            errors.append(f"{event} contains an unexpected owned row")
    for event in expected:
        if event not in hooks:
            errors.append(f"{event} owned row is missing")
    if total_owned != len(expected):
        errors.append(f"expected {len(expected)} owned rows in total (found {total_owned})")
    legacy = legacy_hook_rows()
    exact_legacy_rows = list(legacy.values())
    for event, row in legacy.items():
        if row in hooks.get(event, []):
            errors.append(f"legacy {event} caffeine row is still installed")
    for event, rows in hooks.items():
        for row in rows:
            if (
                isinstance(row, dict)
                and row not in exact_legacy_rows
                and is_legacy_signature_row(row)
            ):
                errors.append(
                    f"{event} contains a legacy-signature row that is not an exact match "
                    "(hand-edited or predecessor version?); verify manually"
                )
    return errors


TCC_ERROR_TOKENS = ("apple event", "appleevent", "not authorized", "not permitted", "tcc", "-1743")


def is_tcc_shaped_error(error: str) -> bool:
    folded = error.lower()
    return any(token in folded for token in TCC_ERROR_TOKENS)


def recent_error(state_data: dict[str, Any] | None, descriptor: dict[str, Any]) -> str | None:
    """Return the runtime hook's last error text if it is recent, regardless of shape.

    This is the only backstop that surfaces a non-TCC osascript/Amphetamine failure (e.g. the
    runtime's catch-all "unexpected osascript response" branch) to doctor. Do not re-narrow this
    to a token allowlist: an unrecognized failure mode is exactly what an allowlist would hide.
    """
    if not state_data or state_data.get("last_status") != "error":
        return None
    attempt = state_data.get("last_attempt", 0)
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        return None
    age = now_seconds() - attempt
    recent_for = max(descriptor["durationSeconds"], descriptor["throttleSeconds"] * 2)
    if age < 0 or age > recent_for:
        return None
    return state_data.get("last_error", "")


def run_doctor() -> int:
    print("== keep-awake doctor ==")
    errors: list[str] = []
    try:
        descriptor = load_json(DESCRIPTOR_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL plugin.json unreadable: {exc}")
        return 1

    descriptor_errors = validate_descriptor(descriptor)
    if descriptor_errors:
        for error in descriptor_errors:
            print(f"FAIL {error}")
        print("NEEDS REPAIR")
        return 1
    actual_hash = canonical_json_hash()
    expected_hash = meta_field("descriptor_ref")
    if actual_hash != expected_hash:
        errors.append(f"descriptor_ref mismatch actual={actual_hash} meta={expected_hash or '<empty>'}")

    link = cursor_home() / "skills" / "keep-awake"
    if not link.is_symlink():
        errors.append(f"stable Cursor link is missing: {link}")
    else:
        try:
            if link.resolve(strict=True) != CAP_DIR.resolve(strict=True):
                errors.append(f"stable Cursor link resolves to the wrong source: {link}")
        except OSError as exc:
            errors.append(f"stable Cursor link is broken: {exc}")

    for executable in (INSTALLER_PATH, RUNTIME_PATH, MAINTENANCE_WRAPPER_PATH):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            errors.append(f"required executable is missing or not executable: {executable}")

    errors.extend(doctor_hook_errors(descriptor))
    owned_state, state_errors = validate_owned_state(state_path(descriptor), descriptor)
    errors.extend(state_errors)
    caffeinate_state, caffeinate_schema_errors = validate_caffeinate_state(caffeinate_state_path(descriptor))
    errors.extend(caffeinate_schema_errors)
    activity_state, activity_schema_errors = validate_activity_state(activity_state_path(descriptor))
    errors.extend(activity_schema_errors)
    if stop_fence_path(descriptor).exists():
        errors.append("uninstall stop fence is still present; run repair to re-enable")
    if platform_is_darwin():
        maintenance_line, maintenance_errors = maintenance_job_status(descriptor)
        errors.extend(maintenance_errors)
    else:
        maintenance_line = "maintenance timer: unavailable off macOS"
    activity_line, activity_errors = describe_activity_status(descriptor, activity_state)
    errors.extend(activity_errors)
    recent = recent_error(owned_state, descriptor)
    if recent is not None:
        if is_tcc_shaped_error(recent):
            errors.append(f"recent Cursor-hook Apple Events (TCC) permission error: {recent}")
        else:
            errors.append(
                "recent Cursor-hook Amphetamine/osascript error (unrecognized shape, not "
                f"TCC-permission-shaped): {recent}"
            )

    print(maintenance_line)
    print(activity_line)
    for error in errors:
        print(f"FAIL {error}")
    if errors:
        print("NEEDS REPAIR")
        return 1

    app = backend_app_path(descriptor)
    if not app.is_dir():
        print("READY but dormant: Amphetamine is not installed")
    elif not backend_running(descriptor):
        print("READY but inactive: Amphetamine is installed but quit")
    else:
        print("READY: Amphetamine is running")
        cdm_status = closed_display_mode_status(descriptor)
        if cdm_status == "enabled":
            print(
                "OK   Mac will not sleep on display/lid close (Amphetamine's 'Allow System to "
                "Sleep When Display is Closed' is unchecked)"
            )
        elif cdm_status == "disabled":
            print(
                "WARN the Mac WILL sleep when the display/lid is closed, even during an active "
                "session (Amphetamine's 'Allow System to Sleep When Display is Closed' is "
                "checked). Fix manually: Amphetamine menu bar -> Settings -> Sessions -> uncheck "
                "'Allow System to Sleep When Display is Closed' (a one-time system warning may "
                "appear -- check 'Do Not Show This Message Again')."
            )
        # "unknown" (Amphetamine unreachable via AppleScript, or an unrecognized osascript
        # response) is intentionally silent here, matching recent_error()'s fail-safe convention
        # above: an inconclusive read is never escalated into a warning or a doctor failure.

    # Unconditional: printed across all three READY/dormant/inactive branches above (not nested
    # inside the "else" branch that requires Amphetamine installed-and-running), so a stale
    # tracked pid is still caught by doctor even while Amphetamine itself is quit.
    caffeinate_line, caffeinate_mismatch_errors = describe_caffeinate_status(descriptor, caffeinate_state)
    print(caffeinate_line)
    if caffeinate_mismatch_errors:
        for error in caffeinate_mismatch_errors:
            print(f"FAIL {error}")
        return 1
    return 0


def run_apply() -> int:
    try:
        descriptor = load_json(DESCRIPTOR_PATH)
        descriptor_errors = validate_descriptor(descriptor)
        if descriptor_errors:
            raise LifecycleError("; ".join(descriptor_errors))
        if platform_is_darwin():
            changed, message = reconcile_hooks(
                descriptor,
                install=True,
                remove_legacy=True,
            )
            maintenance_message = reconcile_maintenance_job(descriptor)
        else:
            changed, message = reconcile_hooks(
                descriptor,
                install=False,
                remove_legacy=False,
            )
            maintenance_message = "maintenance timer unavailable off macOS"
        remove_stop_fence(descriptor)
        try:
            state_root(descriptor).rmdir()
        except OSError:
            pass
        print(("ok   " if changed else "ok   ") + message)
        print("ok   " + maintenance_message)
        return 0
    except (OSError, json.JSONDecodeError, LifecycleError) as exc:
        print(f"FAIL {exc}")
        return 1


def run_repair() -> int:
    if run_apply() != 0:
        return 1
    try:
        descriptor = load_json(DESCRIPTOR_PATH)
        changed, message = clear_expired_ownership(descriptor)
        print(("ok   " if changed else "ok   ") + message)
        # Never raises (see repair_caffeinate_state's own docstring); a problem here must not
        # block the rest of repair, which already ran above and remains unaffected either way.
        print("ok   " + repair_caffeinate_state(descriptor))
        print("ok   " + repair_activity_state(descriptor))
    except (OSError, json.JSONDecodeError, LifecycleError) as exc:
        print(f"FAIL {exc}")
        return 1
    return run_doctor()


def record_plugin_opt_out() -> bool:
    script = CAP_DIR.parents[2] / "scripts" / "capability-local.py"
    capability_id = meta_field("id") or "keep-awake"
    if not script.is_file():
        print(f"FAIL capability-local helper missing: {script}")
        return False
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "opt-out", capability_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"FAIL capability opt-out not recorded: {exc}")
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(f"FAIL capability opt-out not recorded: {detail or 'non-zero exit'}")
        return False
    print("ok   recorded capability opt-out")
    return True


def run_uninstall() -> int:
    try:
        descriptor = load_json(DESCRIPTOR_PATH)
        descriptor_errors = validate_descriptor(descriptor)
        if descriptor_errors:
            raise LifecycleError("; ".join(descriptor_errors))
        # Fence first. If timer removal or hook reconciliation fails, the fence intentionally
        # remains so any still-scheduled/in-flight runtime invocation is a strict no-op.
        write_stop_fence(descriptor)
        maintenance_message = remove_maintenance_job(descriptor)
        changed, message = reconcile_hooks(
            descriptor,
            install=False,
            remove_legacy=True,
        )
        owner = acquire_runtime_lock(descriptor)
        try:
            # Scoped only to the caffeinate sidecar and never raises: timer/hooks removal above
            # and state/activity cleanup below remain independent of this outcome.
            caffeinate_message = uninstall_caffeinate_state(descriptor)
            state_removed = remove_owned_state(descriptor)
            activity_removed = remove_activity_state(descriptor)
        finally:
            release_runtime_lock(descriptor, owner)
        remove_stop_fence(descriptor)
        try:
            state_root(descriptor).rmdir()
        except OSError:
            pass
        print(("ok   " if changed else "ok   ") + message)
        print("ok   " + maintenance_message)
        print("ok   " + caffeinate_message)
        print("ok   removed owned state" if state_removed else "ok   no owned state present")
        print(
            "ok   removed owned activity state"
            if activity_removed
            else "ok   no owned activity state present"
        )
        if not record_plugin_opt_out():
            return 1
        return 0
    except (OSError, json.JSONDecodeError, LifecycleError) as exc:
        print(f"FAIL {exc}")
        return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "doctor", "repair", "uninstall"))
    args = parser.parse_args(argv)
    return {
        "apply": run_apply,
        "doctor": run_doctor,
        "repair": run_repair,
        "uninstall": run_uninstall,
    }[args.action]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
