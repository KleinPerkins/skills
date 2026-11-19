#!/usr/bin/env python3
"""Strict parser for this repository's intentionally flat capability metadata."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, NamedTuple, Optional


ALLOWED_KEYS = frozenset(
    {
        "assets",
        "descriptor_ref",
        "expose",
        "flavor",
        "id",
        "install",
        "kind",
        "owner",
        "payload_digest",
        "payload_version",
        "post_mgmt",
        "provenance_ref",
        "provenance_source",
        "provenance_trust",
        "runtime_contract",
        "schema",
        "scope",
        "shape",
        "sync_policy",
    }
)
ALLOWED_SHELVES = frozenset({"plugins", "rules", "skills", "sub-agents", "tools"})
REQUIRED_KEYS = frozenset({"flavor", "id", "install", "kind", "owner", "schema", "scope"})
QUOTABLE_KEYS = frozenset(
    {
        "descriptor_ref",
        "payload_digest",
        "payload_version",
        "provenance_ref",
        "provenance_source",
        "provenance_trust",
        "runtime_contract",
    }
)
RUNTIME_CONTRACT = "installer-doctor/v1"
KEY_PATTERN = re.compile(rb"[a-z][a-z0-9_]*")
QUOTES = (b'"', b"'")
PLAN_MAGIC = "kp-capability-plan/v1"
KIND_SHELVES = {
    "plugin": "plugins",
    "rule": "rules",
    "skill": "skills",
    "sub-agent": "sub-agents",
    "tool": "tools",
}
EXPOSE_TOOLS = ("cursor", "claude", "codex")


class ActionManifest(NamedTuple):
    directory: str
    capability_id: str
    kind: str
    flavor: str
    post_mgmt: str
    runtime_contract: str
    install: str
    expose_cursor: str
    expose_claude: str
    expose_codex: str
    local_off: str
    assets: tuple[str, ...]


class MetadataError(ValueError):
    def __init__(self, path: Path, line: Optional[int], message: str) -> None:
        self.path = path
        self.line = line
        self.message = message
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


def _has_control(value: bytes) -> bool:
    return any(byte < 0x20 or byte == 0x7F for byte in value)


def _decode_utf8(path: Path, line: int, value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MetadataError(path, line, f"{label} is not valid UTF-8") from exc


def _parse_scalar(path: Path, line: int, key: str, raw: bytes) -> str:
    scalar = raw.strip(b" \t")
    if not scalar:
        raise MetadataError(path, line, "scalar must not be empty")
    if b":" in scalar:
        raise MetadataError(path, line, "extra ':' is not allowed in a scalar")
    if b"#" in scalar:
        raise MetadataError(path, line, "inline comments are not allowed")

    quote = scalar[:1]
    if quote in QUOTES:
        if key not in QUOTABLE_KEYS:
            raise MetadataError(path, line, f"key {key!r} requires an unquoted scalar")
        if len(scalar) < 2 or scalar[-1:] != quote:
            raise MetadataError(path, line, "quoted scalar must use one matching quote pair")
        payload = scalar[1:-1]
        if any(mark in payload for mark in QUOTES):
            raise MetadataError(path, line, "embedded quotes are not allowed")
    else:
        if any(mark in scalar for mark in QUOTES):
            raise MetadataError(path, line, "unquoted scalar must not contain quotes")
        payload = scalar

    if _has_control(payload):
        raise MetadataError(path, line, "scalar contains an ASCII control byte")
    return _decode_utf8(path, line, payload, "scalar")


def parse_metadata(path: Path) -> Dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise MetadataError(path, None, "metadata path must be a regular file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise MetadataError(path, None, f"metadata is unreadable: {exc}") from exc

    values: Dict[str, str] = {}
    key_lines: Dict[str, int] = {}
    for line_number, line in enumerate(data.split(b"\n"), 1):
        if not line or not line.strip(b" \t"):
            continue
        if line.startswith(b"#"):
            if _has_control(line):
                raise MetadataError(path, line_number, "comment contains an ASCII control byte")
            _decode_utf8(path, line_number, line, "comment")
            continue
        if b":" not in line:
            raise MetadataError(path, line_number, "metadata entry must contain exactly one key separator")

        raw_key, raw_value = line.split(b":", 1)
        if KEY_PATTERN.fullmatch(raw_key) is None:
            raise MetadataError(
                path,
                line_number,
                "key must be an exact lowercase ASCII identifier",
            )
        key = raw_key.decode("ascii")
        if key not in ALLOWED_KEYS:
            raise MetadataError(path, line_number, f"unknown metadata key {key!r}")
        if key in values:
            raise MetadataError(
                path,
                line_number,
                f"duplicate metadata key {key!r} (first declared on line {key_lines[key]})",
            )
        values[key] = _parse_scalar(path, line_number, key, raw_value)
        key_lines[key] = line_number

    runtime_contract = values.get("runtime_contract")
    if runtime_contract is not None and runtime_contract != RUNTIME_CONTRACT:
        raise MetadataError(
            path,
            key_lines["runtime_contract"],
            f"runtime_contract must equal {RUNTIME_CONTRACT!r}",
        )
    missing = sorted(REQUIRED_KEYS - values.keys())
    if missing:
        raise MetadataError(path, None, f"missing required metadata keys: {', '.join(missing)}")
    return values


def discover_metadata(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise MetadataError(root, None, "repository root must be a regular directory")
    manifests = []
    for scope in ("global", "local"):
        scope_root = root / scope
        if not scope_root.exists():
            continue
        if scope_root.is_symlink() or not scope_root.is_dir():
            raise MetadataError(scope_root, None, "scope path must be a regular directory")
        candidates = []
        scope_meta = scope_root / "meta.yml"
        if scope_meta.exists():
            candidates.append(scope_meta)
        candidates.extend(scope_root.glob("*/meta.yml"))
        candidates.extend(scope_root.glob("*/*/meta.yml"))
        for path in candidates:
            if path.parent.is_symlink() or path.parent.parent.is_symlink():
                raise MetadataError(path, None, "metadata path must not traverse a symlink")
            relative = path.relative_to(root)
            parts = relative.parts
            if (
                len(parts) != 4
                or parts[0] != scope
                or parts[1] not in ALLOWED_SHELVES
                or not parts[2]
                or parts[3] != "meta.yml"
            ):
                raise MetadataError(path, None, "metadata path is outside the flat shelf layout")
            manifests.append(path)
    manifests.sort(key=lambda path: path.relative_to(root).as_posix())
    if not manifests:
        raise MetadataError(root, None, "no capability metadata discovered")
    return manifests


def _tokens(path: Path, key: str, value: str) -> list[str]:
    bounded = value.strip()
    if bounded.startswith("[") or bounded.endswith("]"):
        if not (bounded.startswith("[") and bounded.endswith("]")):
            raise MetadataError(path, None, f"{key} must use one matching bracket pair")
        bounded = bounded[1:-1]
    return bounded.replace(",", " ").split()


def _require_payload(path: Path, payload: Path, label: str, *, executable: bool = False) -> None:
    if payload.is_symlink() or not payload.is_file():
        raise MetadataError(path, None, f"{label} is missing or not a regular file: {payload}")
    if executable and not os.access(payload, os.X_OK):
        raise MetadataError(path, None, f"{label} is not executable: {payload}")


def build_action_plan(root: Path) -> list[ActionManifest]:
    manifests: list[ActionManifest] = []
    seen_ids: dict[str, Path] = {}
    for path in discover_metadata(root):
        values = parse_metadata(path)
        relative = path.relative_to(root)
        scope, shelf, directory_id, _name = relative.parts
        capability_id = values["id"]
        kind = values["kind"]

        if values["schema"] != "kp-capability/v1":
            raise MetadataError(path, None, "schema must equal 'kp-capability/v1'")
        if values["scope"] != scope:
            raise MetadataError(path, None, f"scope must equal containing scope {scope!r}")
        if capability_id != directory_id:
            raise MetadataError(path, None, f"id must equal directory name {directory_id!r}")
        previous = seen_ids.get(capability_id)
        if previous is not None:
            raise MetadataError(path, None, f"duplicate capability id {capability_id!r} (first declared by {previous})")
        seen_ids[capability_id] = path

        expected_shelf = KIND_SHELVES.get(kind)
        if expected_shelf is None:
            raise MetadataError(path, None, f"kind {kind!r} is not installable by bootstrap")
        if shelf != expected_shelf:
            raise MetadataError(path, None, f"kind {kind!r} belongs on shelf {expected_shelf!r}")

        install = values["install"]
        if not install or "/" in install or "\\" in install or ".." in install:
            raise MetadataError(path, None, "install must be a bare filename")
        _require_payload(path, path.parent / install, "installer", executable=True)

        expose = _tokens(path, "expose", values.get("expose", ""))
        if not expose:
            expose = list(EXPOSE_TOOLS)
        unknown = sorted(set(expose) - {*EXPOSE_TOOLS, "none"})
        if unknown:
            raise MetadataError(path, None, f"expose contains unsupported tool(s): {', '.join(unknown)}")
        if "none" in expose and expose != ["none"]:
            raise MetadataError(path, None, "expose 'none' must stand alone")
        if len(expose) != len(set(expose)):
            raise MetadataError(path, None, "expose must not contain duplicate tools")

        assets = _tokens(path, "assets", values.get("assets", ""))
        if len(assets) != len(set(assets)):
            raise MetadataError(path, None, "assets must not contain duplicates")
        for asset in assets:
            if not asset or "/" in asset or "\\" in asset or ".." in asset:
                raise MetadataError(path, None, f"asset must be a bare filename: {asset!r}")
            _require_payload(path, path.parent / asset, f"declared asset {asset!r}")

        if kind == "skill":
            _require_payload(path, path.parent / "SKILL.md", "skill payload")
        elif kind == "rule":
            _require_payload(path, path.parent / f"{capability_id}.mdc", "rule payload")
        elif kind == "sub-agent":
            _require_payload(path, path.parent / f"{capability_id}.md", "sub-agent payload")
        elif kind == "tool":
            _require_payload(path, path.parent / "tool.yml", "tool descriptor")
        elif kind == "plugin":
            _require_payload(path, path.parent / "SKILL.md", "plugin skill payload")
            _require_payload(path, path.parent / "plugin.json", "plugin descriptor")

        directory = str(path.parent)
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in directory):
            raise MetadataError(path, None, "capability path contains a control character")
        exposed = set(expose)
        manifests.append(
            ActionManifest(
                directory=directory,
                capability_id=capability_id,
                kind=kind,
                flavor=values["flavor"],
                post_mgmt=values.get("post_mgmt", ""),
                runtime_contract=values.get("runtime_contract", ""),
                install=install,
                expose_cursor="1" if "cursor" in exposed else "0",
                expose_claude="1" if "claude" in exposed else "0",
                expose_codex="1" if "codex" in exposed else "0",
                local_off="1" if expose == ["none"] else "0",
                assets=tuple(assets),
            )
        )
    return manifests


def render_action_plan(root: Path) -> bytes:
    fields: list[str] = [PLAN_MAGIC]
    manifests = build_action_plan(root)
    fields.append(str(len(manifests)))
    for manifest in manifests:
        fields.extend(manifest[:-1])
        fields.append(str(len(manifest.assets)))
        fields.extend(manifest.assets)
    return b"".join(field.encode("utf-8") + b"\0" for field in fields)


def _validate(paths: Iterable[Path]) -> int:
    failed = False
    for path in paths:
        try:
            parse_metadata(path)
        except MetadataError as exc:
            print(exc, file=sys.stderr)
            failed = True
    return 1 if failed else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate one or more meta.yml files")
    validate.add_argument("paths", nargs="+", type=Path)
    tree = commands.add_parser(
        "validate-tree",
        help="discover and validate every manifest in a repository tree",
    )
    tree.add_argument("root", type=Path)
    plan = commands.add_parser(
        "action-plan",
        help="emit one validated deterministic NUL-delimited bootstrap action plan",
    )
    plan.add_argument("root", type=Path)
    args = parser.parse_args(argv)

    if args.command == "validate":
        return _validate(args.paths)
    if args.command == "validate-tree":
        try:
            paths = discover_metadata(args.root)
        except MetadataError as exc:
            print(exc, file=sys.stderr)
            return 1
        return _validate(paths)
    if args.command == "action-plan":
        try:
            payload = render_action_plan(args.root)
        except MetadataError as exc:
            print(exc, file=sys.stderr)
            return 1
        sys.stdout.buffer.write(payload)
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
