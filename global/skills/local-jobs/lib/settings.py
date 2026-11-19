#!/usr/bin/env python3
"""Central settings for local-jobs runtime.

The global payload ships neutral defaults. Operators may override them in
``$LOCAL_JOBS_STATE/config.yml`` or with explicit environment variables.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LABEL_ROOT = "com.local-jobs"
LEGACY_PREFIX_ROOTS = {
    "com.kleinperkins.": "com.kleinperkins.local-jobs",
}


def state_dir() -> Path:
    return Path(os.environ.get("LOCAL_JOBS_STATE", str(Path.home() / ".local-jobs"))).expanduser()


def state_config_path() -> Path:
    return Path(os.environ.get("LOCAL_JOBS_CONFIG", str(state_dir() / "config.yml"))).expanduser()


def load_state_config() -> dict[str, Any]:
    path = state_config_path()
    if not path.is_file():
        return {}
    with path.open() as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _clean_root(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().rstrip(".") or None


def legacy_root_from_discovery(discovery: dict[str, Any]) -> str | None:
    prefix = discovery.get("label_prefix")
    if not prefix:
        return None
    if prefix in LEGACY_PREFIX_ROOTS:
        return LEGACY_PREFIX_ROOTS[prefix]
    prefix = str(prefix).rstrip(".")
    if prefix.endswith(".local-jobs"):
        return prefix
    return f"{prefix}.local-jobs" if prefix else None


def label_root(registry: dict[str, Any] | None = None) -> str:
    env = _clean_root(os.environ.get("LOCAL_JOBS_LABEL_ROOT"))
    if env:
        return env
    state = _clean_root(load_state_config().get("label_root"))
    if state:
        return state
    discovery = (registry or {}).get("discovery") or {}
    configured = _clean_root(discovery.get("label_root"))
    if configured:
        return configured
    legacy = legacy_root_from_discovery(discovery)
    return legacy or DEFAULT_LABEL_ROOT


def discovery_prefixes(registry: dict[str, Any] | None = None) -> list[str]:
    discovery = (registry or {}).get("discovery") or {}
    roots = [label_root(registry)]
    legacy = legacy_root_from_discovery(discovery)
    if legacy and legacy not in roots:
        roots.append(legacy)
    legacy_prefix = discovery.get("label_prefix")
    prefixes = [f"{root}." for root in roots]
    if legacy_prefix and legacy_prefix not in prefixes:
        prefixes.append(str(legacy_prefix))
    return prefixes


def label_for(token: str, cardinality: str = "multi", iid: str | None = None, registry: dict[str, Any] | None = None) -> str:
    root = label_root(registry)
    if cardinality == "singleton" or not iid:
        return f"{root}.{token}"
    return f"{root}.{token}.{iid}"


def main() -> int:
    ap = argparse.ArgumentParser(prog="settings.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("label-root")
    p_label = sub.add_parser("label")
    p_label.add_argument("--token", required=True)
    p_label.add_argument("--cardinality", default="multi")
    p_label.add_argument("--id", default="")
    sub.add_parser("discovery-prefixes")
    args = ap.parse_args()
    if args.cmd == "label-root":
        print(label_root())
        return 0
    if args.cmd == "label":
        print(label_for(args.token, args.cardinality, args.id or None))
        return 0
    if args.cmd == "discovery-prefixes":
        for prefix in discovery_prefixes():
            print(prefix)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
