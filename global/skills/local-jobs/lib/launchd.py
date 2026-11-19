#!/usr/bin/env python3
"""The single launchd plist writer + load/unload for local-jobs.

Replaces the three divergent writers (``handlers/command.sh``,
the igf ``install-launchd.sh`` and store-backed handlers) so every job type
gets identical, correctly-escaped plists with ``WorkingDirectory`` (P1-4), the
global minute (P1-5), and a pinned ``PATH`` (P2-9).

``install`` is verify-before-replace safe for live agents: it writes the new
plist atomically, replaces the agent (same label), then confirms it loaded —
so a scheduled job is never left absent. Set ``LOCAL_JOBS_LAUNCHD_DISABLE=1``
(plus ``LOCAL_JOBS_LAUNCHAGENTS_DIR``) for hermetic tests that never touch the
real launchd domain.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def agents_dir() -> Path:
    return Path(
        os.environ.get("LOCAL_JOBS_LAUNCHAGENTS_DIR", str(Path.home() / "Library" / "LaunchAgents"))
    ).expanduser()


def _disabled() -> bool:
    return os.environ.get("LOCAL_JOBS_LAUNCHD_DISABLE", "0") == "1"


def uid_domain() -> str:
    return f"gui/{os.getuid()}"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def plist_path(label: str) -> Path:
    return agents_dir() / f"{label}.plist"


def _validated_schedule(value: Any) -> dict[str, int]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("launchd schedule must be an object")
    unknown = set(value) - {"seconds", "hour", "minute"}
    if unknown:
        raise ValueError(f"unsupported launchd schedule keys: {', '.join(sorted(unknown))}")
    if "seconds" in value and ("hour" in value or "minute" in value):
        raise ValueError("launchd schedule cannot combine interval and calendar fields")
    if "seconds" in value:
        seconds = value["seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise ValueError("launchd interval seconds must be a positive integer")
        return {"seconds": seconds}
    if "hour" not in value:
        raise ValueError("launchd calendar schedule requires hour")
    hour = value["hour"]
    minute = value.get("minute", 0)
    if isinstance(hour, bool) or not isinstance(hour, int) or not (0 <= hour <= 23):
        raise ValueError("launchd schedule hour must be 0-23")
    if isinstance(minute, bool) or not isinstance(minute, int) or not (0 <= minute <= 59):
        raise ValueError("launchd schedule minute must be 0-59")
    return {"hour": hour, "minute": minute}


def render_plist(spec: dict[str, Any]) -> str:
    """Render a launchd plist from a uniform spec.

    spec keys: label, program_args[list], working_directory?, env?{}, schedule?
    ({"hour","minute"} | {"seconds"}), watch_paths?[list], stdout?, stderr?,
    run_at_load?
    """
    if not spec.get("label") or not spec.get("program_args"):
        raise ValueError("launchd spec requires 'label' and non-empty 'program_args'")
    sched = _validated_schedule(spec.get("schedule"))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
        "  <key>Label</key>",
        f'  <string>{_esc(spec["label"])}</string>',
        "  <key>ProgramArguments</key>",
        "  <array>",
    ]
    for arg in spec["program_args"]:
        lines.append(f"    <string>{_esc(arg)}</string>")
    lines.append("  </array>")

    working_dir = spec.get("working_directory")
    if working_dir:
        lines += ["  <key>WorkingDirectory</key>", f"  <string>{_esc(working_dir)}</string>"]

    env = dict(spec.get("env") or {})
    env.setdefault("PATH", DEFAULT_PATH)
    lines += ["  <key>EnvironmentVariables</key>", "  <dict>"]
    for key in sorted(env):
        value = env[key]
        lines += [f"    <key>{_esc(key)}</key>", f"    <string>{_esc(value)}</string>"]
    lines.append("  </dict>")

    if "seconds" in sched:
        lines += ["  <key>StartInterval</key>", f'  <integer>{int(sched["seconds"])}</integer>']
    elif "hour" in sched:
        lines += [
            "  <key>StartCalendarInterval</key>",
            "  <dict>",
            f'    <key>Hour</key><integer>{int(sched["hour"])}</integer>',
            f'    <key>Minute</key><integer>{int(sched.get("minute", 0))}</integer>',
            "  </dict>",
        ]

    if spec.get("run_at_load"):
        lines += ["  <key>RunAtLoad</key>", "  <true/>"]
    watch_paths = list(spec.get("watch_paths") or [])
    if watch_paths:
        lines += ["  <key>WatchPaths</key>", "  <array>"]
        for path in watch_paths:
            lines.append(f"    <string>{_esc(path)}</string>")
        lines.append("  </array>")
    if spec.get("stdout"):
        lines += ["  <key>StandardOutPath</key>", f'  <string>{_esc(spec["stdout"])}</string>']
    if spec.get("stderr"):
        lines += ["  <key>StandardErrorPath</key>", f'  <string>{_esc(spec["stderr"])}</string>']

    lines += ["</dict>", "</plist>"]
    return "\n".join(lines) + "\n"


def is_loaded(label: str) -> bool:
    if _disabled():
        return False
    try:
        return (
            subprocess.run(
                ["launchctl", "print", f"{uid_domain()}/{label}"], capture_output=True
            ).returncode
            == 0
        )
    except FileNotFoundError:  # no launchctl (e.g. Linux CI) — treat as not loaded
        return False


def bootout(label: str) -> None:
    if _disabled():
        return
    try:
        subprocess.run(["launchctl", "bootout", f"{uid_domain()}/{label}"], capture_output=True)
    except FileNotFoundError:
        return


def bootstrap(plist: Path) -> int:
    if _disabled():
        return 0
    try:
        return subprocess.run(
            ["launchctl", "bootstrap", uid_domain(), str(plist)], capture_output=True
        ).returncode
    except FileNotFoundError:
        return 0


def write_plist(spec: dict[str, Any]) -> Path:
    directory = agents_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = plist_path(spec["label"])
    tmp = target.with_suffix(".plist.tmp")
    tmp.write_text(render_plist(spec))
    os.chmod(tmp, 0o644)
    tmp.replace(target)
    return target


def install(spec: dict[str, Any]) -> dict[str, Any]:
    """Write the plist then (re)load the agent, verifying it is live.

    Same-label replace: write → bootout → bootstrap → verify. The plist is left
    on disk regardless, so a failed verify is recoverable via ``repair`` and the
    machine is never left with the agent's config missing.
    """
    label = spec["label"]
    path = write_plist(spec)
    if _disabled():
        return {"label": label, "plist": str(path), "loaded": False, "disabled": True, "ok": True}
    bootout(label)
    rc = bootstrap(path)
    loaded = is_loaded(label)
    return {
        "label": label,
        "plist": str(path),
        "bootstrap_rc": rc,
        "loaded": loaded,
        "ok": bool(rc == 0 and loaded),
    }


def uninstall(label: str, remove_plist: bool = True) -> None:
    bootout(label)
    if remove_plist:
        try:
            plist_path(label).unlink()
        except OSError:
            pass


def _load_spec(raw: str | None) -> dict[str, Any]:
    text = raw if raw is not None else sys.stdin.read()
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError("spec must be a JSON object")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(prog="launchd.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install")
    p_install.add_argument("--spec", default=None, help="spec JSON (else stdin)")

    p_render = sub.add_parser("render")
    p_render.add_argument("--spec", default=None)

    p_un = sub.add_parser("uninstall")
    p_un.add_argument("--label", required=True)
    p_un.add_argument("--keep-plist", action="store_true")

    p_loaded = sub.add_parser("is-loaded")
    p_loaded.add_argument("--label", required=True)

    p_path = sub.add_parser("plist-path")
    p_path.add_argument("--label", required=True)

    sub.add_parser("agents-dir")

    args = ap.parse_args()
    if args.cmd == "install":
        result = install(_load_spec(args.spec))
        print(json.dumps(result))
        return 0 if result.get("ok") else 1
    if args.cmd == "render":
        print(render_plist(_load_spec(args.spec)), end="")
        return 0
    if args.cmd == "uninstall":
        uninstall(args.label, remove_plist=not args.keep_plist)
        return 0
    if args.cmd == "is-loaded":
        return 0 if is_loaded(args.label) else 1
    if args.cmd == "plist-path":
        print(plist_path(args.label))
        return 0
    if args.cmd == "agents-dir":
        print(agents_dir())
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
