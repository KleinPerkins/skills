#!/usr/bin/env python3
"""Load and query the incremental-git-fetch YAML configuration (jobs/v1)."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LABEL = "com.local-jobs.git-fetch"
DEFAULT_LOG_DIR = "~/Library/Logs/local-jobs"
LOG_BASENAME = "git-fetch.out.log"

# Multi-repo sweep behavior on a per-repo failure (additive; no schema bump).
#   continue → attempt every enabled repo (default).
#   stop     → halt after the first failure; unattempted repos are summarized in
#              the parent run only (no per-child run events, so a real streak is
#              never reset by a skip).
FAILURE_POLICIES = ("continue", "stop")
DEFAULT_FAILURE_POLICY = "continue"


def parse_bool(value: str) -> bool:
    """Parse an operator-facing boolean without silently accepting typos."""
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("use true or false")


def normalize_failure_policy(global_cfg: dict[str, Any]) -> str:
    """Validated ``global.failure_policy`` (defaults to ``continue``)."""
    policy = global_cfg.get("failure_policy", DEFAULT_FAILURE_POLICY)
    if policy not in FAILURE_POLICIES:
        raise ValueError(
            f"invalid failure_policy: {policy!r} (use one of {', '.join(FAILURE_POLICIES)})"
        )
    return policy


def config_path(path: str | None = None) -> Path:
    return Path(path or os.environ.get("LOCAL_JOBS_IGF_CONFIG", "")).expanduser()


def default_raw_config() -> dict[str, Any]:
    return {
        "schema": "jobs/v1",
        "version": 1,
        "defaults": {
            "remote": "origin",
            "branch": "main",
            "enabled": True,
            "filter_blobs": True,
            "ff_only_merge": True,
            "fetch_tags": False,
            "schedule": "inherit",
        },
        "global": {
            "launchd": {"window_start_hour": 18, "window_end_hour": 24, "use_jitter": True},
            "logging": {"dir": DEFAULT_LOG_DIR},
        },
        "repos": [],
    }


def _check_version(data: dict[str, Any]) -> None:
    # Forward-migration policy (P1-3): never brick existing instances on a
    # version bump. v1/missing load as-is; a higher version still loads (the
    # schema is forward-compatible via defaults-merge) with a one-line note.
    version = data.get("version", 1)
    if version in (None, 1):
        return
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"unsupported config version: {version!r}")
    print(
        f"incremental-git-fetch: config version {version} > 1; loading forward-compatibly",
        file=sys.stderr,
    )


def load_raw_config(path: str | None = None) -> dict[str, Any]:
    """Read and validate the schema before any view or mutation uses this store."""
    config_file = config_path(path)
    if config_file.is_file():
        with config_file.open() as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = default_raw_config()
    _check_version(data)
    return data


def save_raw_config(data: dict[str, Any], path: str | None = None) -> Path:
    config_file = config_path(path).resolve()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=config_file.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            if config_file.exists():
                os.fchmod(output.fileno(), stat.S_IMODE(config_file.stat().st_mode))
            yaml.safe_dump(data, output, default_flow_style=False, sort_keys=False)
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, config_file)
        finally:
            temporary.unlink(missing_ok=True)
    return config_file


def find_repo_index(data: dict[str, Any], repo_id: str) -> int:
    repos = data.get("repos") or []
    for index, entry in enumerate(repos):
        if isinstance(entry, dict) and entry.get("id") == repo_id:
            return index
    raise SystemExit(f"repo not found: {repo_id}")


def load_config(path: str | None = None) -> dict[str, Any]:
    return normalized_config(load_raw_config(path))


def normalized_config(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    defaults = data.get("defaults") or {}
    repos = data.get("repos") or []
    global_cfg = dict(data.get("global") or {})

    dev_root = os.path.expanduser(
        global_cfg.get("dev_root") or os.environ.get("LOCAL_JOBS_IGF_DEV_ROOT") or "."
    )

    # Validate + normalize the additive sweep policy so `validate` (and every
    # read path) fails closed on an unknown value. Written back in-memory only —
    # save_raw_config never sees it, so the on-disk YAML is untouched.
    global_cfg["failure_policy"] = normalize_failure_policy(global_cfg)

    normalized: list[dict[str, Any]] = []
    for entry in repos:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ValueError("each repo entry requires an id")
        merged = {**defaults, **entry}
        fetch_tags = merged.get("fetch_tags", False)
        if not isinstance(fetch_tags, bool):
            raise ValueError(f"invalid fetch_tags for {entry['id']!r}: use true or false")
        merged["fetch_tags"] = fetch_tags
        raw_path = merged["path"]
        path_obj = Path(os.path.expanduser(raw_path))
        if not path_obj.is_absolute():
            path_obj = Path(dev_root) / raw_path
        merged["path"] = str(path_obj.resolve())
        normalized.append(merged)

    data["repos"] = normalized
    data["global"] = global_cfg
    data["_dev_root"] = dev_root
    return data


def cmd_list() -> int:
    cfg = load_config()
    for repo in cfg["repos"]:
        print(
            f"{repo['id']}\t"
            f"{'enabled' if repo.get('enabled', True) else 'disabled'}\t"
            f"{repo['path']}\t"
            f"{repo.get('remote', 'origin')}/{repo.get('branch', 'main')}\t"
            f"fetch_tags={str(repo.get('fetch_tags', False)).lower()}"
        )
    return 0


def cmd_get_global() -> int:
    print(json.dumps(load_config()["global"], indent=2, sort_keys=True))
    return 0


def cmd_get_repo(repo_id: str) -> int:
    cfg = load_config()
    for repo in cfg["repos"]:
        if repo["id"] == repo_id:
            print(json.dumps(repo, indent=2, sort_keys=True))
            return 0
    raise SystemExit(f"repo not found: {repo_id}")


def cmd_enabled_ids() -> int:
    for repo in load_config()["repos"]:
        if repo.get("enabled", True):
            print(repo["id"])
    return 0


def cmd_inherit_ids() -> int:
    """Enabled repos that follow the global window (no per-repo agent).

    The global scheduled run fetches only these so a repo with its own
    per-repo agent is never also fetched in the global window (no double-run).
    """
    for repo in load_config()["repos"]:
        schedule = repo.get("schedule", "inherit")
        if repo.get("enabled", True) and (schedule == "inherit" or schedule is None):
            print(repo["id"])
    return 0


def cmd_validate() -> int:
    load_config()
    print("ok")
    return 0


def _repo_git_hint(path: str) -> dict[str, str]:
    repo_path = Path(path)
    if not repo_path.is_dir():
        return {"git": "missing"}
    import subprocess

    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return {"git": "not-a-repo"}

    branch = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"git": "ok", "branch": branch, "head": head}


def _last_log_hint(repo_id: str, log_dir: str) -> str | None:
    log_path = Path(os.path.expanduser(log_dir)) / LOG_BASENAME
    if not log_path.is_file():
        return None
    marker = f"[{repo_id}]"
    try:
        lines = deque_tail(log_path, 200)
    except OSError:
        return None
    for line in reversed(lines):
        if marker in line:
            return line.strip()
    return None


def deque_tail(path: Path, max_lines: int) -> list[str]:
    from collections import deque

    with path.open(errors="replace") as handle:
        return list(deque(handle, maxlen=max_lines))


def removal_revision(repo: dict[str, Any]) -> str:
    record = {"store": str(config_path().resolve()), "repo": repo}
    encoded = yaml.safe_dump(record, sort_keys=True, allow_unicode=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cmd_view() -> int:
    cfg = load_config()
    global_cfg = cfg.get("global") or {}
    launchd = global_cfg.get("launchd") or {}
    logging_cfg = global_cfg.get("logging") or {}
    log_dir = os.path.expanduser(logging_cfg.get("dir", DEFAULT_LOG_DIR))

    repos_out: list[dict[str, Any]] = []
    for repo in cfg["repos"]:
        hints = _repo_git_hint(repo["path"])
        entry: dict[str, Any] = {
            "id": repo["id"],
            "enabled": repo.get("enabled", True),
            "path": repo["path"],
            "remote": repo.get("remote", "origin"),
            "branch": repo.get("branch", "main"),
            "schedule": repo.get("schedule", "inherit"),
            "filter_blobs": repo.get("filter_blobs", True),
            "full_fetch_other_refs": repo.get("full_fetch_other_refs", False),
            "ff_only_merge": repo.get("ff_only_merge", True),
            "fetch_tags": repo.get("fetch_tags", False),
            "git": hints,
            "last_run_hint": _last_log_hint(repo["id"], log_dir),
        }
        # Optional operator identity (M2): only surfaced when set, so absence
        # falls back to the id at display time.
        if repo.get("display_name"):
            entry["display_name"] = repo["display_name"]
        if repo.get("description"):
            entry["description"] = repo["description"]
        if repo.get("schedule", "inherit") == "inherit":
            entry["removal_revision"] = removal_revision(repo)
        repos_out.append(entry)

    payload = {
        "global": {
            "dev_root": cfg.get("_dev_root"),
            "launchd": launchd,
            "logging": {"dir": log_dir},
            "failure_policy": global_cfg.get("failure_policy", DEFAULT_FAILURE_POLICY),
            **({"display_name": global_cfg["display_name"]} if global_cfg.get("display_name") else {}),
            **({"description": global_cfg["description"]} if global_cfg.get("description") else {}),
            "schedule_summary": (
                f"daily {launchd.get('window_start_hour', 18):02d}:00 "
                f"with jitter to {launchd.get('window_end_hour', 24):02d}:00"
                if launchd.get("use_jitter", True)
                else f"daily {launchd.get('window_start_hour', 18):02d}:00 fixed"
            ),
        },
        "repos": repos_out,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.type != "incremental":
        raise SystemExit(f"unsupported repo type: {args.type!r} (only 'incremental')")

    data = load_raw_config()
    repos = data.setdefault("repos", [])
    if any(isinstance(entry, dict) and entry.get("id") == args.id for entry in repos):
        raise SystemExit(f"repo already exists: {args.id}")

    dev_root = os.path.expanduser(
        (data.get("global") or {}).get("dev_root")
        or os.environ.get("LOCAL_JOBS_IGF_DEV_ROOT") or "."
    )
    raw_path = args.path
    resolved = Path(os.path.expanduser(raw_path))
    if not resolved.is_absolute():
        resolved = Path(dev_root) / raw_path

    if not args.dry_run and not resolved.is_dir():
        raise SystemExit(f"path does not exist: {resolved}")

    entry: dict[str, Any] = {
        "id": args.id,
        "path": raw_path,
        "branch": args.branch,
        "enabled": args.enabled,
        "fetch_tags": args.fetch_tags,
        "schedule": args.schedule,
    }
    if args.remote:
        entry["remote"] = args.remote
    if getattr(args, "display_name", None):
        entry["display_name"] = args.display_name
    if getattr(args, "description", None):
        entry["description"] = args.description

    repos.append(entry)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "would_add": entry}, indent=2, sort_keys=True))
        return 0

    saved = save_raw_config(data)
    print(f"added {args.id} to {saved}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    data = load_raw_config()
    index = find_repo_index(data, args.id)
    if args.if_revision is not None:
        matches = [row for row in data["repos"] if row.get("id") == args.id]
        if len(matches) != 1:
            raise SystemExit("conditional removal needs one unique fetch id")
        selected = normalized_config({**data, "repos": matches})["repos"][0]
        if selected.get("schedule", "inherit") != "inherit":
            raise SystemExit("retire the dedicated launch agent through its owner first")
        if removal_revision(selected) != args.if_revision:
            raise SystemExit("fetch record changed since the preview; nothing removed")
    removed = data["repos"].pop(index)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "would_remove": removed,
                    "purge_launchd": args.purge_launchd,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    saved = save_raw_config(data)
    print(f"removed {args.id} from {saved}")
    if args.purge_launchd:
        print(f"PURGE_LAUNCHD:{args.id}")
    return 0


def cmd_set_enabled(repo_id: str, enabled: bool, dry_run: bool) -> int:
    data = load_raw_config()
    index = find_repo_index(data, repo_id)
    data["repos"][index]["enabled"] = enabled

    if dry_run:
        print(json.dumps({"dry_run": True, "id": repo_id, "enabled": enabled}, indent=2))
        return 0

    saved = save_raw_config(data)
    state = "enabled" if enabled else "disabled"
    print(f"{state} {repo_id} in {saved}")
    return 0


def cmd_set_fetch_tags(repo_id: str, fetch_tags: bool, dry_run: bool) -> int:
    data = load_raw_config()
    index = find_repo_index(data, repo_id)
    data["repos"][index]["fetch_tags"] = fetch_tags

    if dry_run:
        print(json.dumps({"dry_run": True, "id": repo_id, "fetch_tags": fetch_tags}, indent=2))
        return 0

    saved = save_raw_config(data)
    print(f"set fetch_tags={str(fetch_tags).lower()} for {repo_id} in {saved}")
    return 0


def cmd_set_schedule(args: argparse.Namespace) -> int:
    data = load_raw_config()
    global_cfg = data.setdefault("global", {})
    launchd = global_cfg.setdefault("launchd", {})

    if args.global_schedule:
        launchd["window_start_hour"] = args.hour
        if args.minute is not None:
            launchd["window_start_minute"] = args.minute
        target = "global"
        schedule_value: Any = {
            "window_start_hour": args.hour,
            **({"window_start_minute": args.minute} if args.minute is not None else {}),
        }
    else:
        if not args.id:
            raise SystemExit("set-schedule requires --id or --global")
        index = find_repo_index(data, args.id)
        if args.inherit:
            data["repos"][index]["schedule"] = "inherit"
            schedule_value = "inherit"
        else:
            minute = 0 if args.minute is None else args.minute
            data["repos"][index]["schedule"] = {"hour": args.hour, "minute": minute}
            schedule_value = {"hour": args.hour, "minute": minute}
        target = args.id

    if args.dry_run:
        print(
            json.dumps(
                {"dry_run": True, "target": target, "schedule": schedule_value},
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    saved = save_raw_config(data)
    print(f"updated schedule for {target} in {saved}")
    return 0


def cmd_set_fields(args: argparse.Namespace) -> int:
    """Set display_name/description (any target) or failure_policy (global) on
    a repo entry or the global block.

    Only the flags explicitly provided are written; a stored value is never
    cleared or overwritten unless the operator passes that flag (parity with the
    chassis update-job path — migrate never touches these).
    """
    updates: dict[str, str] = {}
    if args.display_name is not None:
        updates["display_name"] = args.display_name
    if args.description is not None:
        updates["description"] = args.description
    failure_policy = getattr(args, "failure_policy", None)
    if failure_policy is not None:
        if not args.global_target:
            raise SystemExit("set-fields --failure-policy applies to --global only")
        if failure_policy not in FAILURE_POLICIES:
            raise SystemExit(
                f"invalid failure_policy: {failure_policy!r} (use one of {', '.join(FAILURE_POLICIES)})"
            )
        updates["failure_policy"] = failure_policy
    if not updates:
        raise SystemExit("set-fields requires --display-name, --description, and/or --failure-policy")

    data = load_raw_config()
    if args.global_target:
        target_obj = data.setdefault("global", {})
        target = "global"
    else:
        if not args.id:
            raise SystemExit("set-fields requires --id or --global")
        index = find_repo_index(data, args.id)
        target_obj = data["repos"][index]
        target = args.id
    target_obj.update(updates)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "target": target, "set": updates}, indent=2, sort_keys=True))
        return 0

    saved = save_raw_config(data)
    print(f"updated fields for {target} in {saved}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="config.py")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    sub.add_parser("validate")
    sub.add_parser("global")
    sub.add_parser("enabled-ids")
    sub.add_parser("inherit-ids")
    sub.add_parser("view")

    repo_p = sub.add_parser("repo")
    repo_p.add_argument("repo_id")

    add_p = sub.add_parser("add")
    add_p.add_argument("--id", required=True)
    add_p.add_argument("--path", required=True)
    add_p.add_argument("--branch", required=True)
    add_p.add_argument("--type", default="incremental")
    add_p.add_argument("--remote", default="")
    add_p.add_argument("--enabled", type=lambda v: v.lower() == "true", default=True)
    add_p.add_argument("--fetch-tags", dest="fetch_tags", type=parse_bool, default=False)
    add_p.add_argument("--schedule", default="inherit")
    add_p.add_argument("--display-name", dest="display_name", default=None)
    add_p.add_argument("--description", dest="description", default=None)
    add_p.add_argument("--dry-run", action="store_true")

    remove_p = sub.add_parser("remove")
    remove_p.add_argument("--id", required=True)
    remove_p.add_argument("--if-revision")
    remove_p.add_argument("--purge-launchd", action="store_true")
    remove_p.add_argument("--dry-run", action="store_true")

    enable_p = sub.add_parser("enable")
    enable_p.add_argument("--id", required=True)
    enable_p.add_argument("--dry-run", action="store_true")

    disable_p = sub.add_parser("disable")
    disable_p.add_argument("--id", required=True)
    disable_p.add_argument("--dry-run", action="store_true")

    tags_p = sub.add_parser("set-fetch-tags")
    tags_p.add_argument("--id", required=True)
    tags_p.add_argument("--fetch-tags", dest="fetch_tags", required=True, type=parse_bool)
    tags_p.add_argument("--dry-run", action="store_true")

    sched_p = sub.add_parser("set-schedule")
    sched_p.add_argument("--id", default="")
    sched_p.add_argument("--global", dest="global_schedule", action="store_true")
    sched_p.add_argument("--hour", type=int)
    sched_p.add_argument("--minute", type=int)
    sched_p.add_argument("--inherit", action="store_true")
    sched_p.add_argument("--dry-run", action="store_true")

    fields_p = sub.add_parser("set-fields")
    fields_p.add_argument("--id", default="")
    fields_p.add_argument("--global", dest="global_target", action="store_true")
    fields_p.add_argument("--display-name", dest="display_name", default=None)
    fields_p.add_argument("--description", dest="description", default=None)
    fields_p.add_argument("--failure-policy", dest="failure_policy", default=None)
    fields_p.add_argument("--dry-run", action="store_true")

    return parser


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] in {
        "list",
        "validate",
        "global",
        "enabled-ids",
        "inherit-ids",
        "repo",
    }:
        command = sys.argv[1]
        if command == "list":
            return cmd_list()
        if command == "validate":
            return cmd_validate()
        if command == "global":
            return cmd_get_global()
        if command == "enabled-ids":
            return cmd_enabled_ids()
        if command == "inherit-ids":
            return cmd_inherit_ids()
        if command == "repo":
            if len(sys.argv) != 3:
                raise SystemExit("usage: config.py repo <id>")
            return cmd_get_repo(sys.argv[2])

    parser = build_parser()
    args = parser.parse_args()

    mutating = {"add", "remove", "enable", "disable", "set-fetch-tags", "set-schedule", "set-fields"}
    if args.command in mutating and not args.dry_run:
        # Keep comparison, read-modify-write and replacement in one owner transaction.
        # A sibling lock survives replacement of the YAML file itself.
        target = config_path().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(target.with_name(target.name + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(lock_fd, "r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            return dispatch(args)
    return dispatch(args)


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "list":
        return cmd_list()
    if args.command == "validate":
        return cmd_validate()
    if args.command == "global":
        return cmd_get_global()
    if args.command == "enabled-ids":
        return cmd_enabled_ids()
    if args.command == "inherit-ids":
        return cmd_inherit_ids()
    if args.command == "view":
        return cmd_view()
    if args.command == "repo":
        return cmd_get_repo(args.repo_id)
    if args.command == "add":
        if args.schedule not in ("inherit",) and not isinstance(args.schedule, dict):
            if args.schedule.startswith("{"):
                args.schedule = json.loads(args.schedule.replace("'", '"'))
            elif ":" in args.schedule:
                hour_s, minute_s = args.schedule.split(":", 1)
                args.schedule = {"hour": int(hour_s), "minute": int(minute_s)}
        return cmd_add(args)
    if args.command == "remove":
        return cmd_remove(args)
    if args.command == "enable":
        return cmd_set_enabled(args.id, True, args.dry_run)
    if args.command == "disable":
        return cmd_set_enabled(args.id, False, args.dry_run)
    if args.command == "set-fetch-tags":
        return cmd_set_fetch_tags(args.id, args.fetch_tags, args.dry_run)
    if args.command == "set-schedule":
        if args.global_schedule and args.inherit:
            raise SystemExit("--inherit is only valid with per-repo --id")
        if args.global_schedule:
            if args.hour is None:
                raise SystemExit("set-schedule --global requires --hour")
        elif args.inherit:
            if not args.id:
                raise SystemExit("set-schedule --inherit requires --id")
        else:
            if not args.id or args.hour is None:
                raise SystemExit("set-schedule requires --id and --hour (or --inherit)")
            if args.minute is None:
                args.minute = 0
        return cmd_set_schedule(args)
    if args.command == "set-fields":
        return cmd_set_fields(args)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
