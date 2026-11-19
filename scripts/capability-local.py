#!/usr/bin/env python3
"""Machine-local capability preferences for KleinPerkins/skills bootstrap."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

SCHEMA = "kp-capability-local/v1"
DEFAULT_REGISTRY = Path.home() / ".local" / "share" / "kleinperkins" / "capability-local.yml"


def registry_path() -> Path:
    override = os.environ.get("CAPABILITY_LOCAL_REGISTRY")
    return Path(override).expanduser() if override else DEFAULT_REGISTRY


def _parse_registry(text: str) -> tuple[str | None, list[str], list[str]]:
    """Parse the bounded kp-capability-local/v1 file without external YAML deps."""
    schema: str | None = None
    opt_out: list[str] = []
    errors: list[str] = []
    in_opt_out = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("schema:"):
            schema = line.split(":", 1)[1].strip().strip("\"'")
            in_opt_out = False
            continue
        if line.startswith("opt_out:"):
            in_opt_out = True
            continue
        if in_opt_out and line.lstrip().startswith("- "):
            value = line.lstrip()[2:].strip().strip("\"'")
            if value and value != "[]":
                opt_out.append(value)
            continue
        if in_opt_out and not line.startswith("- "):
            in_opt_out = False
        errors.append(f"unrecognized line: {raw_line!r}")
    return schema, opt_out, errors


def load_registry(path: Path | None = None) -> tuple[str | None, list[str]]:
    target = path or registry_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, []
    except OSError as exc:
        print(f"WARN capability-local registry unreadable: {exc}", file=sys.stderr)
        return None, []
    schema, opt_out, errors = _parse_registry(text)
    if schema not in (None, SCHEMA):
        print(
            f"WARN capability-local registry schema {schema!r} unsupported; ignoring opt-outs",
            file=sys.stderr,
        )
        return schema, []
    for error in errors:
        print(f"WARN capability-local registry: {error}", file=sys.stderr)
    seen: set[str] = set()
    normalized: list[str] = []
    for item in opt_out:
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    return schema, normalized


def render_registry(opt_out: list[str]) -> str:
    lines = [f"schema: {SCHEMA}", "opt_out:"]
    if opt_out:
        lines.extend(f"  - {item}" for item in opt_out)
    else:
        lines.append("  []")
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def is_opted_out(capability_id: str, path: Path | None = None) -> bool:
    _schema, opt_out = load_registry(path)
    return capability_id in opt_out


def record_opt_out(capability_id: str, path: Path | None = None) -> None:
    target = path or registry_path()
    _schema, opt_out = load_registry(target)
    if capability_id not in opt_out:
        opt_out.append(capability_id)
    atomic_write(target, render_registry(opt_out))


def clear_opt_out(capability_id: str, path: Path | None = None) -> None:
    target = path or registry_path()
    _schema, opt_out = load_registry(target)
    filtered = [item for item in opt_out if item != capability_id]
    if not filtered:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        try:
            target.parent.rmdir()
        except OSError:
            pass
        return
    atomic_write(target, render_registry(filtered))


def reset_registry(path: Path | None = None) -> None:
    target = path or registry_path()
    try:
        target.unlink()
    except FileNotFoundError:
        return
    try:
        target.parent.rmdir()
    except OSError:
        pass


def cmd_is_opted_out(args: argparse.Namespace) -> int:
    path = args.registry.expanduser() if args.registry else None
    return 0 if is_opted_out(args.id, path) else 1


def cmd_opt_out(args: argparse.Namespace) -> int:
    path = args.registry.expanduser() if args.registry else None
    record_opt_out(args.id, path)
    return 0


def cmd_clear_opt_out(args: argparse.Namespace) -> int:
    path = args.registry.expanduser() if args.registry else None
    clear_opt_out(args.id, path)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    path = args.registry.expanduser() if args.registry else None
    reset_registry(path)
    return 0


def cmd_path(_args: argparse.Namespace) -> int:
    print(registry_path())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_id_command(name: str, handler) -> None:
        cmd = sub.add_parser(name)
        cmd.add_argument(
            "--registry",
            type=Path,
            default=None,
            help="override registry path",
        )
        cmd.add_argument("id")
        cmd.set_defaults(func=handler)

    add_id_command("is-opted-out", cmd_is_opted_out)
    add_id_command("opt-out", cmd_opt_out)
    add_id_command("clear-opt-out", cmd_clear_opt_out)

    reset = sub.add_parser("reset")
    reset.add_argument("--registry", type=Path, default=None)
    reset.set_defaults(func=cmd_reset)

    path = sub.add_parser("path")
    path.set_defaults(func=cmd_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "registry", None) is not None:
        os.environ["CAPABILITY_LOCAL_REGISTRY"] = str(args.registry.expanduser())
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
