#!/usr/bin/env python3
"""Strict, deterministic Skills-owned description inventory."""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


INVENTORY_SCHEMA = "skill-description-inventory/v1"
NORMALIZATION_CONTRACT = "skill-description-normalization/v1"
PARSER_PROFILE = "skills-yaml12-core-profile/v1"
WHITESPACE_SET = "unicode-15.0-white-space"
FIXTURE_SCHEMA = "skill-description-normalization-fixtures/v1"
DESCRIPTION_BUDGET_WARNING_LIMIT = 300
DESCRIPTION_BUDGET_FAILURE_LIMIT = 600
DESCRIPTION_MIGRATION_FAILURE_LIMIT = 1024
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "tests"
    / "fixtures"
    / "skill-description-normalization-v1"
    / "cases.json"
)

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_INTEGER = re.compile(
    r"[-+]?(?:0|[1-9][0-9_]*|0o[0-7_]+|0x[0-9a-fA-F_]+)\Z"
)
_FLOAT = re.compile(
    r"[-+]?(?:(?:[0-9][0-9_]*)?\.[0-9_]+"
    r"|[0-9][0-9_]*(?:\.[0-9_]*)?[eE][-+]?[0-9]+"
    r"|\.inf|\.nan)\Z",
    re.IGNORECASE,
)
_BLOCK_HEADER = re.compile(r"([>|])([+-]?)\Z")


class BlockedPrerequisite(Exception):
    """A closed prerequisite failure with path-safe diagnostics."""

    def __init__(self, failures):
        if isinstance(failures, tuple) and len(failures) == 2:
            failures = [failures]
        self.failures = tuple((str(path), str(reason)) for path, reason in failures)
        super().__init__("; ".join(f"{path}: {reason}" for path, reason in self.failures))


def _block(path: str, reason: str):
    raise BlockedPrerequisite((path, reason))


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_comment(value: str) -> str:
    stripped = value.lstrip()
    if not stripped:
        return ""
    if stripped[0] not in "'\"[":
        match = re.search(r"\s#", value)
        return value[: match.start()].rstrip() if match else value.rstrip()
    single = False
    double = False
    escaped = False
    for index, character in enumerate(value):
        if double and escaped:
            escaped = False
            continue
        if double and character == "\\":
            escaped = True
            continue
        if not double and character == "'":
            single = not single
            continue
        if not single and character == '"':
            double = not double
            continue
        if (
            character == "#"
            and not single
            and not double
            and (index == 0 or value[index - 1].isspace())
        ):
            return value[:index].rstrip()
    return value.rstrip()


def _decode_double_quoted(value: str, source_path: str):
    output = []
    index = 1
    escapes = {
        "0": "\0",
        "a": "\a",
        "b": "\b",
        "t": "\t",
        "n": "\n",
        "v": "\v",
        "f": "\f",
        "r": "\r",
        "e": "\x1b",
        " ": " ",
        '"': '"',
        "/": "/",
        "\\": "\\",
        "N": "\u0085",
        "_": "\u00a0",
        "L": "\u2028",
        "P": "\u2029",
    }
    while index < len(value):
        character = value[index]
        if character == '"':
            if value[index + 1 :].strip():
                _block(source_path, "content follows a quoted scalar")
            return "".join(output)
        if character != "\\":
            if ord(character) < 0x20:
                _block(source_path, "control character in quoted scalar")
            output.append(character)
            index += 1
            continue
        index += 1
        if index >= len(value):
            _block(source_path, "unterminated escape")
        marker = value[index]
        if marker in escapes:
            output.append(escapes[marker])
            index += 1
            continue
        widths = {"x": 2, "u": 4, "U": 8}
        if marker not in widths:
            _block(source_path, "unsupported quoted escape")
        width = widths[marker]
        digits = value[index + 1 : index + 1 + width]
        if len(digits) != width or re.fullmatch(
            r"[0-9a-fA-F]+", digits
        ) is None:
            _block(source_path, "malformed Unicode escape")
        scalar = int(digits, 16)
        if scalar > 0x10FFFF or 0xD800 <= scalar <= 0xDFFF:
            _block(source_path, "invalid Unicode scalar")
        output.append(chr(scalar))
        index += width + 1
    _block(source_path, "unterminated double-quoted scalar")


def _decode_single_quoted(value: str, source_path: str):
    output = []
    index = 1
    while index < len(value):
        character = value[index]
        if character != "'":
            if ord(character) < 0x20:
                _block(source_path, "control character in quoted scalar")
            output.append(character)
            index += 1
            continue
        if index + 1 < len(value) and value[index + 1] == "'":
            output.append("'")
            index += 2
            continue
        if value[index + 1 :].strip():
            _block(source_path, "content follows a quoted scalar")
        return "".join(output)
    _block(source_path, "unterminated single-quoted scalar")


def _split_flow_members(inner: str, source_path: str) -> List[str]:
    members = []
    start = 0
    single = False
    double = False
    escaped = False
    for index, character in enumerate(inner):
        if double and escaped:
            escaped = False
            continue
        if double and character == "\\":
            escaped = True
            continue
        if not double and character == "'":
            single = not single
            continue
        if not single and character == '"':
            double = not double
            continue
        if not single and not double:
            if character in "[]{}":
                _block(source_path, "nested flow collections are unsupported")
            if character == ":":
                _block(source_path, "flow mappings are unsupported")
            if character == ",":
                member = inner[start:index].strip()
                if not member:
                    _block(source_path, "empty flow-sequence member")
                members.append(member)
                start = index + 1
    if single or double or escaped:
        _block(source_path, "unterminated flow-sequence scalar")
    final = inner[start:].strip()
    if final:
        members.append(final)
    elif members:
        _block(source_path, "trailing flow-sequence comma")
    return members


def _parse_plain(value: str, source_path: str):
    if not value:
        return None
    if value[0] in "-?:,[]{}#&*!|>@`":
        _block(source_path, "unsupported plain-scalar indicator")
    if re.search(r":(?:\s|$)", value):
        _block(source_path, "mapping syntax inside plain scalar")
    if any(ord(character) < 0x20 for character in value):
        _block(source_path, "control character in plain scalar")
    lower = value.lower()
    if lower in {"null", "~"}:
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    if _INTEGER.fullmatch(value):
        cleaned = value.replace("_", "")
        sign = -1 if cleaned.startswith("-") else 1
        unsigned = cleaned.lstrip("+-")
        if unsigned.startswith("0o"):
            return sign * int(unsigned[2:], 8)
        if unsigned.startswith("0x"):
            return sign * int(unsigned[2:], 16)
        return int(cleaned, 10)
    if _FLOAT.fullmatch(value):
        cleaned = value.replace("_", "")
        if cleaned.lower().endswith(".inf"):
            return -math.inf if cleaned.startswith("-") else math.inf
        if cleaned.lower().endswith(".nan"):
            return math.nan
        return float(cleaned)
    return value


def _parse_scalar(value: str, source_path: str):
    value = _split_comment(value).strip()
    if value.startswith("'"):
        return _decode_single_quoted(value, source_path)
    if value.startswith('"'):
        return _decode_double_quoted(value, source_path)
    if value.startswith("["):
        if not value.endswith("]"):
            _block(source_path, "unterminated flow sequence")
        inner = value[1:-1].strip()
        return [
            _parse_scalar(member, source_path)
            for member in _split_flow_members(inner, source_path)
        ]
    if value.startswith("{"):
        _block(source_path, "flow mappings are unsupported")
    return _parse_plain(value, source_path)


def _fold_block_lines(lines: Sequence[str]) -> str:
    trailing = 0
    for line in reversed(lines):
        if line != "":
            break
        trailing += 1
    body = list(lines[: len(lines) - trailing] if trailing else lines)
    if not body:
        folded = ""
    else:
        folded = body[0]
        for current, following in zip(body, body[1:]):
            if current and following:
                separator = " "
            elif current:
                separator = ""
            else:
                separator = "\n"
            folded += separator + following
    return folded + ("\n" * (1 + trailing))


def _parse_block_scalar(
    style: str, chomp: str, content: Sequence[str]
) -> str:
    if style == "|":
        value = "\n".join(content) + ("\n" if content else "")
    else:
        value = _fold_block_lines(content)
    if chomp == "-":
        return value.rstrip("\n")
    if chomp == "+":
        return value
    if not value:
        return ""
    return value.rstrip("\n") + "\n"


class _YamlSubsetParser:
    def __init__(self, lines: Sequence[str], source_path: str):
        self.lines = list(lines)
        self.source_path = source_path
        self.index = 0

    def _next_content(self, start: int) -> Optional[int]:
        for index in range(start, len(self.lines)):
            stripped = self.lines[index].strip()
            if stripped and not stripped.startswith("#"):
                return index
        return None

    def _parse_block(
        self, parent_indent: int, header: re.Match
    ) -> str:
        style, chomp = header.groups()
        start = self.index
        end = start
        content_indent = None
        while end < len(self.lines):
            line = self.lines[end]
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if stripped and indent <= parent_indent:
                break
            if stripped and content_indent is None:
                content_indent = indent
            if (
                stripped
                and content_indent is not None
                and indent != content_indent
            ):
                _block(self.source_path, "inconsistent block-scalar indentation")
            end += 1
        if content_indent is None:
            content = []
        else:
            content = []
            for line in self.lines[start:end]:
                if not line.strip():
                    content.append("")
                else:
                    indent = len(line) - len(line.lstrip(" "))
                    if indent < content_indent:
                        _block(
                            self.source_path,
                            "inconsistent block-scalar indentation",
                        )
                    content.append(line[content_indent:])
        self.index = end
        return _parse_block_scalar(style, chomp, content)

    def parse_mapping(self, indent: int) -> Dict[str, object]:
        result = {}
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if "\t" in line:
                _block(self.source_path, "tab indentation is unsupported")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                self.index += 1
                continue
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent < indent:
                break
            if current_indent > indent:
                _block(self.source_path, "unexpected mapping indentation")
            content = line[current_indent:]
            if content.startswith("%") or content == "...":
                _block(self.source_path, "directives and document markers are unsupported")
            if ":" not in content:
                _block(self.source_path, "mapping entry lacks a colon")
            key, remainder = content.split(":", 1)
            key = key.strip()
            if _KEY.fullmatch(key) is None or key == "<<":
                _block(self.source_path, "unsupported mapping key")
            if key in result:
                _block(self.source_path, "duplicate mapping key")
            value_text = _split_comment(remainder).strip()
            self.index += 1
            block_header = _BLOCK_HEADER.fullmatch(value_text)
            if block_header is not None:
                result[key] = self._parse_block(current_indent, block_header)
                continue
            if value_text:
                result[key] = _parse_scalar(value_text, self.source_path)
                continue
            child = self._next_content(self.index)
            if child is None:
                result[key] = None
                continue
            child_line = self.lines[child]
            child_indent = len(child_line) - len(child_line.lstrip(" "))
            if child_indent <= current_indent:
                result[key] = None
                continue
            self.index = child
            result[key] = self.parse_mapping(child_indent)
        return result


def parse_frontmatter(raw: bytes, source_path: str) -> Dict[str, object]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _block(source_path, "source is not strict UTF-8")
    text = _normalize_newlines(text)
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        _block(source_path, "first line is not an exact frontmatter delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError:
        _block(source_path, "frontmatter closing delimiter is missing")
    parser = _YamlSubsetParser(lines[1:closing], source_path)
    value = parser.parse_mapping(0)
    if parser._next_content(parser.index) is not None:
        _block(source_path, "frontmatter was not fully parsed")
    if "description" not in value:
        _block(source_path, "description is missing")
    if type(value["description"]) is not str:
        _block(source_path, "description must be a string")
    return value


_PINNED_WHITESPACE = (
    "\u0009-\u000d"
    "\u0020"
    "\u0085"
    "\u00a0"
    "\u1680"
    "\u2000-\u200a"
    "\u2028\u2029\u202f"
    "\u205f"
    "\u3000"
)
_WHITESPACE_RUN = re.compile("[" + _PINNED_WHITESPACE + "]+")


def normalize_description(value: str) -> str:
    if type(value) is not str:
        raise TypeError("description normalization requires a string")
    return _WHITESPACE_RUN.sub(" ", value).strip(" ")


def _git(repo_root: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError:
        _block(".", "Git inventory is unavailable")


def discover_candidates(repo_root: Path) -> List[Path]:
    try:
        root = repo_root.resolve(strict=True)
    except OSError:
        _block(".", "repository root is unavailable")
    top = _git(root, ["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        _block(".", "Git inventory is unavailable")
    try:
        git_root = Path(top.stdout.decode("utf-8", errors="strict").strip()).resolve(
            strict=True
        )
    except (OSError, UnicodeDecodeError):
        _block(".", "Git top level is unavailable")
    if git_root != root:
        _block(".", "repository root does not match Git top level")
    tracked_result = _git(root, ["ls-files", "-z", "--", "global", "local"])
    if tracked_result.returncode != 0:
        _block(".", "Git tracked-file inventory is unavailable")
    try:
        tracked_all = [
            item.decode("utf-8", errors="strict")
            for item in tracked_result.stdout.split(b"\0")
            if item
        ]
    except UnicodeDecodeError:
        _block(".", "tracked path is not strict UTF-8")
    tracked = {
        item
        for item in tracked_all
        if item.endswith("/SKILL.md")
        and (item.startswith("global/") or item.startswith("local/"))
    }
    physical = set()
    for scope in ("global", "local"):
        if not (root / scope).is_dir():
            continue
        for path in (root / scope).glob("**/SKILL.md"):
            relative = path.relative_to(root)
            if path.is_file() and "node_modules" not in relative.parts:
                physical.add(relative.as_posix())
    if not tracked:
        _block(".", "tracked skill descriptor set is empty")
    failures = []
    for path in sorted(tracked - physical, key=lambda item: item.encode("utf-8")):
        failures.append((path, "tracked descriptor is missing"))
    for path in sorted(physical - tracked, key=lambda item: item.encode("utf-8")):
        failures.append((path, "descriptor is untracked"))
    if failures:
        raise BlockedPrerequisite(failures)
    return [
        root / path
        for path in sorted(tracked, key=lambda item: item.encode("utf-8"))
    ]


def _fixture_identity() -> Tuple[str, str]:
    try:
        raw = FIXTURE_PATH.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _block(
            "scripts/tests/fixtures/skill-description-normalization-v1/cases.json",
            "conformance fixture is unavailable",
        )
    if type(value) is not dict or value.get("schema") != FIXTURE_SCHEMA:
        _block(
            "scripts/tests/fixtures/skill-description-normalization-v1/cases.json",
            "conformance fixture schema is unsupported",
        )
    return FIXTURE_SCHEMA, hashlib.sha256(raw).hexdigest()


def build_inventory(repo_root: Path) -> Dict[str, object]:
    candidates = discover_candidates(repo_root)
    root = repo_root.resolve(strict=True)
    failures = []
    rows = []
    for candidate in candidates:
        relative = candidate.relative_to(root).as_posix()
        try:
            raw = candidate.read_bytes()
            parsed = parse_frontmatter(raw, relative)
            name = parsed.get("name")
            if type(name) is not str:
                _block(relative, "name must be a string")
            normalized = normalize_description(parsed["description"])
            rows.append(
                {
                    "character_count": len(normalized),
                    "name": name,
                    "normalized_description": normalized,
                    "normalized_sha256": hashlib.sha256(
                        normalized.encode("utf-8")
                    ).hexdigest(),
                    "path": relative,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        except BlockedPrerequisite as error:
            failures.extend(error.failures)
        except OSError:
            failures.append((relative, "descriptor could not be read"))
    if failures:
        raise BlockedPrerequisite(failures)
    by_description = {}
    for row in rows:
        by_description.setdefault(row["normalized_description"], []).append(
            row["path"]
        )
    duplicate_groups = [
        paths for paths in by_description.values() if len(paths) > 1
    ]
    if duplicate_groups:
        duplicate_failures = []
        for paths in duplicate_groups:
            for path in paths:
                duplicate_failures.append(
                    (path, "normalized description duplicates another candidate")
                )
        raise BlockedPrerequisite(duplicate_failures)
    fixture_schema, fixture_sha256 = _fixture_identity()
    return {
        "candidate_count": len(rows),
        "candidates": rows,
        "conformance_fixture_schema": fixture_schema,
        "conformance_fixture_sha256": fixture_sha256,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "normalized_duplicates": [],
        "parser_profile": PARSER_PROFILE,
        "schema": INVENTORY_SCHEMA,
        "total_normalized_characters": sum(
            row["character_count"] for row in rows
        ),
        "whitespace_set": WHITESPACE_SET,
    }


def classify_description_budget(
    character_count: int,
) -> Optional[Tuple[str, int]]:
    if type(character_count) is not int or character_count < 0:
        raise ValueError("description character count must be a non-negative integer")
    if character_count > DESCRIPTION_MIGRATION_FAILURE_LIMIT:
        return (
            "DESCRIPTION_MIGRATION_FAILURE",
            DESCRIPTION_MIGRATION_FAILURE_LIMIT,
        )
    if character_count > DESCRIPTION_BUDGET_FAILURE_LIMIT:
        return (
            "DESCRIPTION_BUDGET_FAILURE",
            DESCRIPTION_BUDGET_FAILURE_LIMIT,
        )
    if character_count > DESCRIPTION_BUDGET_WARNING_LIMIT:
        return (
            "DESCRIPTION_BUDGET_WARNING",
            DESCRIPTION_BUDGET_WARNING_LIMIT,
        )
    return None


def description_budget_diagnostics(
    candidates: Sequence[Dict[str, object]],
) -> Tuple[List[str], bool]:
    diagnostics = []
    has_failure = False
    ordered = sorted(
        candidates,
        key=lambda row: str(row["path"]).encode("utf-8"),
    )
    for row in ordered:
        classification = classify_description_budget(row["character_count"])
        if classification is None:
            continue
        diagnostic, limit = classification
        diagnostics.append(
            f"{diagnostic} {row['path']}: "
            f"characters={row['character_count']} limit={limit}"
        )
        if diagnostic != "DESCRIPTION_BUDGET_WARNING":
            has_failure = True
    return diagnostics, has_failure


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the strict Skills description inventory."
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        value = build_inventory(args.repo)
    except BlockedPrerequisite as error:
        for path, reason in error.failures:
            print(
                f"BLOCKED_PREREQUISITE {path}: {reason}",
                file=sys.stderr,
            )
        return 3
    diagnostics, has_budget_failure = description_budget_diagnostics(
        value["candidates"]
    )
    for diagnostic in diagnostics:
        print(diagnostic, file=sys.stderr)
    if has_budget_failure:
        return 3
    output = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
