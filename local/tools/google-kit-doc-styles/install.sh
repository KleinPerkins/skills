#!/usr/bin/env bash
# install.sh - local bootstrap installer for google-kit document style seeds.
set -euo pipefail

ARTIFACT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

python3 - "$ARTIFACT_DIR" "$@" <<'PY'
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed google-kit document style profiles.")
    parser.add_argument("--config-dir", help="google-kit config directory override")
    parser.add_argument("--dry-run", action="store_true", help="show actions without writing")
    parser.add_argument("--force", action="store_true", help="replace valid destination seed files")
    parser.add_argument("--no-repair", action="store_true", help="do not quarantine corrupt destination seed files")
    parser.add_argument("--template-only", action="store_true", help="install only the generic blank-slate template")
    return parser.parse_args(sys.argv[2:])


def config_dir(args: argparse.Namespace) -> Path:
    if args.config_dir:
        return Path(args.config_dir).expanduser()
    if os.environ.get("GOOGLE_KIT_CONFIG_DIR"):
        return Path(os.environ["GOOGLE_KIT_CONFIG_DIR"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "google-kit"
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg / "google-kit"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("profile must be a JSON object")
    return data


def validate_profile(data: dict, expected_name: str) -> None:
    if not NAME_RE.match(expected_name) or "/" in expected_name or ".." in expected_name:
        raise ValueError(f"unsafe profile name: {expected_name!r}")
    if data.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"schema must be {SCHEMA_VERSION}")
    if data.get("name") != expected_name:
        raise ValueError(f"profile name must match filename stem {expected_name!r}")
    if not isinstance(data.get("named_styles"), dict):
        raise ValueError("named_styles must be an object")
    if not isinstance(data.get("document_style"), dict):
        raise ValueError("document_style must be an object")


def atomic_write_json(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def quarantine(path: Path, dry_run: bool) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.name}.quarantine-{stamp}")
    if not dry_run:
        os.replace(path, target)
        os.chmod(target, 0o600)
    return target


def seed_one(src: Path, dest: Path, args: argparse.Namespace) -> str:
    name = dest.stem
    data = load_json(src)
    validate_profile(data, name)

    if dest.exists() and not args.force:
        try:
            existing = load_json(dest)
            validate_profile(existing, name)
            return f"present: {dest}"
        except Exception as exc:
            if args.no_repair:
                return f"warn: {dest} is invalid ({exc}); left unchanged"
            q = quarantine(dest, args.dry_run)
            atomic_write_json(dest, data, args.dry_run)
            prefix = "would repair" if args.dry_run else "repaired"
            return f"{prefix}: {dest} (quarantined {q.name})"

    if dest.exists():
        action = "would replace" if args.dry_run else "replaced"
    else:
        action = "would seed" if args.dry_run else "seeded"
    atomic_write_json(dest, data, args.dry_run)
    return f"{action}: {dest}"


def main() -> int:
    args = parse_args()
    root = Path(sys.argv[1])
    dest_dir = config_dir(args) / "doc-styles"
    if not args.dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(dest_dir, 0o700)

    seeds: list[tuple[Path, Path]] = [
        (root / "templates" / "blank-style-profile.json", dest_dir / "blank-style-profile.json"),
    ]
    if not args.template_only:
        for src in sorted((root / "profiles" / "laurence").glob("*.json")):
            seeds.append((src, dest_dir / src.name))

    print(f"doc-styles dir: {dest_dir}")
    if args.dry_run:
        print("mode: dry-run")
    for src, dest in seeds:
        print(seed_one(src, dest, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
