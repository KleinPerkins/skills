#!/usr/bin/env python3
"""Generic chassis runtime for store-backed handlers.

Given a type's uniform knobs (token, cardinality, store file, schema_version,
defaults) this projects normalized instances and installs/uninstalls launchd
agents through the single chassis writers (:mod:`store`, :mod:`launchd`,
:mod:`schedule`). Handlers stay thin: they declare their schema, contribute
launchd env + working dir, and implement ``run``.

Every scheduled instance dispatches through ``bin/run-scheduled.sh`` so each run
is uniformly run-logged regardless of type.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import launchd
import schedule as schedule_mod
import settings
import store as store_mod

def label_for(token: str, cardinality: str, iid: str) -> str:
    return settings.label_for(token, cardinality, iid)


def log_paths(log_dir: str, job_type: str, cardinality: str, iid: str) -> dict[str, str]:
    base = job_type if cardinality == "singleton" else f"{job_type}-{iid}"
    root = os.path.expanduser(log_dir)
    return {"stdout": f"{root}/{base}.out.log", "stderr": f"{root}/{base}.err.log"}


def _store(args: argparse.Namespace) -> store_mod.Store:
    defaults = json.loads(args.defaults) if args.defaults else {}
    required = json.loads(args.required) if args.required else []
    return store_mod.Store(
        Path(args.file), schema_version=args.schema_version, field_defaults=defaults, required=required
    )


def _normalize(entry: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    iid = entry["id"]
    label = label_for(args.token, args.cardinality, iid)
    inst: dict[str, Any] = {
        "id": iid,
        "type": args.type,
        "role": "instance",
        "enabled": bool(entry.get("enabled", True)),
        "schedule": entry.get("schedule"),
        "launchd_label": label,
        "launchd_loaded": launchd.is_loaded(label),
        "log_paths": log_paths(args.log_dir, args.type, args.cardinality, iid),
    }
    for key, value in entry.items():
        if key.startswith("_") or key in ("id", "enabled", "schedule"):
            continue
        inst[key] = value
    return inst


def _build_spec(args: argparse.Namespace, entry: dict[str, Any]) -> dict[str, Any]:
    iid = entry["id"]
    label = label_for(args.token, args.cardinality, iid)
    sched = schedule_mod.Schedule.parse(entry.get("schedule"))
    schedule_errors = sched.validate()
    if schedule_errors:
        raise ValueError(f"invalid schedule for {iid}: {'; '.join(schedule_errors)}")
    extra_env = json.loads(args.extra_env) if args.extra_env else {}
    env = {**extra_env, "LOCAL_JOBS_HOME": args.home}
    program = [str(Path(args.home) / "bin" / "run-scheduled.sh"), "--type", args.type, "--id", iid]
    logs = log_paths(args.log_dir, args.type, args.cardinality, iid)
    spec = {
        "label": label,
        "program_args": program,
        "env": env,
        "schedule": sched.launchd_schedule(),
        "stdout": logs["stdout"],
        "stderr": logs["stderr"],
    }
    if args.working_dir:
        spec["working_directory"] = args.working_dir
    return spec


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--type", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--cardinality", default="multi")
    p.add_argument("--file", required=True)
    p.add_argument("--schema-version", type=int, default=1)
    p.add_argument("--defaults", default=None)
    p.add_argument("--required", default=None)
    p.add_argument("--log-dir", default="~/Library/Logs/local-jobs")
    p.add_argument("--home", default=os.environ.get("LOCAL_JOBS_HOME", ""))


def main() -> int:
    ap = argparse.ArgumentParser(prog="handler_runtime.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-instances")
    _add_common(p_list)

    p_view = sub.add_parser("view")
    _add_common(p_view)
    p_view.add_argument("--id", required=True)

    p_install = sub.add_parser("install")
    _add_common(p_install)
    p_install.add_argument("--id", required=True)
    p_install.add_argument("--extra-env", default=None)
    p_install.add_argument("--working-dir", default=None)

    p_un = sub.add_parser("uninstall")
    _add_common(p_un)
    p_un.add_argument("--id", required=True)
    p_un.add_argument("--keep-plist", action="store_true")

    args = ap.parse_args()
    store = _store(args)

    if args.cmd == "list-instances":
        out = [_normalize(e, args) for e in store.list()]
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "view":
        entry = store.find(args.id)
        if entry is None:
            print(f"unknown instance: {args.id}", file=sys.stderr)
            return 2
        print(json.dumps(_normalize(entry, args), indent=2))
        return 0
    if args.cmd == "install":
        entry = store.get(args.id)
        result = launchd.install(_build_spec(args, entry))
        print(json.dumps(result))
        return 0 if result.get("ok") else 1
    if args.cmd == "uninstall":
        label = label_for(args.token, args.cardinality, args.id)
        launchd.uninstall(label, remove_plist=not args.keep_plist)
        print(json.dumps({"uninstalled": label}))
        return 0
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
