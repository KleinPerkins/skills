"""Read saved base-registry declarations without dispatching handlers or probing job targets."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

import yaml


class Unavailable(ValueError):
    """The configuration cannot be described from the supported files."""


@contextmanager
def directory(path: Path):
    if not path.is_absolute() or ".." in path.parts:
        raise Unavailable("an absolute state directory without parent traversal is required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for name in path.parts[1:]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_yaml(path: Path):
    with directory(path.parent) as parent:
        # O_NONBLOCK permits rejecting a FIFO before it can wait for a writer.
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Unavailable("configuration must be a regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return yaml.safe_load(stream)
        finally:
            os.close(fd)


def read_store(path: Path, forward_compatible: bool) -> dict:
    try:
        value = read_yaml(path)
    except FileNotFoundError:
        return {}
    if value is None:
        return {}
    if not isinstance(value, dict) or value.get("schema") not in (None, "jobs/v1"):
        raise Unavailable("unrecognized job store")
    version = value.get("version")
    if version is not None and (type(version) is not int or version < 1
                                or version > 1 and not forward_compatible):
        raise Unavailable("unqualified job store version")
    return value


def base_registry(home: Path, state: Path) -> dict:
    package = Path(__file__).resolve().parents[1]
    if home not in (Path(os.path.abspath(__file__)).parents[1], package):
        raise Unavailable("alternate package requires its owner's inventory")
    expected = home / "config/registry.yml"
    if Path(os.environ.get("LOCAL_JOBS_REGISTRY") or expected) != expected:
        raise Unavailable("alternate registry requires its owner's inventory")
    overlay = state / "registry.d"
    if Path(os.environ.get("LOCAL_JOBS_OVERLAY_DIR") or overlay) != overlay:
        raise Unavailable("alternate overlay requires its owner's inventory")
    try:
        with directory(overlay) as fd:
            if any(name.endswith(".yml") for name in os.listdir(fd)):
                raise Unavailable("registry overlays require their owners' inventories")
    except FileNotFoundError:
        pass
    # Read the registry shipped with this observer, never a path from a job or overlay.
    reg = read_yaml(package / "config/registry.yml")
    # Some callers stage bin/lib and the registry independently. A different
    # registration can select different handlers even with the same type names.
    active = home.resolve()
    if active != package and read_yaml(active / "config/registry.yml") != reg:
        raise Unavailable("modified base registry requires its owner's inventory")
    if reg.get("schema") != "registry/v1" or reg.get("version") != 1:
        raise Unavailable("unrecognized base registry")
    return reg["job_types"]


def declared_rows(kind: str, spec: dict, state: Path) -> list[dict]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", kind) or not isinstance(spec, dict):
        raise Unavailable("job type lacks a supported configuration declaration")
    path = state / "jobs" / (kind + ".yml")
    configured_path = os.environ.get(spec["override"])
    if configured_path and Path(configured_path) != path:
        raise Unavailable("a job type uses an alternate configuration file")
    data = read_store(path, spec.get("forward_compatible_versions") is True)
    collection = spec["collection"]
    records = data.get(collection)
    if records is None:
        records = []
    if not isinstance(records, list):
        raise Unavailable("job collection must be a list")
    defaults = data.get("defaults")
    options = data.get("global")
    defaults = {} if defaults is None else defaults
    options = {} if options is None else options
    if not isinstance(defaults, dict) or not isinstance(options, dict):
        raise Unavailable("invalid job defaults or global settings")
    rows = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            raise Unavailable("job record lacks an instance id")
        row = {"id": record["id"], "type": kind}
        field = spec.get("checkout_field")
        if field:
            declared = record.get(field, defaults.get(field))
            root = options.get("dev_root") or os.environ.get(spec["checkout_root_override"]) or "."
            if not isinstance(declared, str) or not declared or not isinstance(root, str):
                raise Unavailable("invalid checkout declaration")
            row.update(declared_path=declared, declared_root=root)
        rows.append(row)
    return rows


def snapshot() -> dict:
    home = Path(os.environ["LOCAL_JOBS_HOME"])
    state = Path(os.environ["LOCAL_JOBS_STATE"])
    result = {"schema": "local-jobs/configured-jobs/v1", "scope": "base-configured-instances",
              "complete": False, "instances": []}
    try:
        rows = []
        for kind, meta in base_registry(home, state).items():
            rows.extend(declared_rows(kind, meta.get("configuration"), state))
        if len({row["id"] for row in rows}) != len(rows):
            raise Unavailable("duplicate instance id")
    except Unavailable as exc:
        result["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError):
        # Parse errors can include private command arguments. Keep raw store values out of errors.
        result["reason"] = "configuration unreadable or malformed"
    else:
        result.update(complete=True, instances=rows)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = snapshot()
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["complete"]:
        print(f"Configured instances: {len(result['instances'])}")
        for row in result["instances"]:
            print(f"  {json.dumps(row['id'])} ({row['type']})")
    else:
        print(f"Configuration inventory incomplete: {result['reason']}")
    raise SystemExit(0 if result["complete"] else 1)
