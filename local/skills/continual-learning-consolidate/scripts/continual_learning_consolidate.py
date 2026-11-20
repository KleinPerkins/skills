#!/usr/bin/env python3
"""Build the machine-local global continual-learning projection.

Candidate roots come only from ``agent-route map --json``. The home seed is
``~/agent-learnings.md``. ``~/AGENTS.md`` is an output projection and is never
used as memory input.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

import memory  # noqa: E402
import classifications  # noqa: E402

MANAGED_HEADER = "<!-- generated; edit agent-learnings.md sources, not this file -->\n"
_LOADED_MODULE_CODE = sys._getframe().f_code


class ConsolidationError(RuntimeError):
    """A fail-closed condition that must leave the output unchanged."""


@dataclass(frozen=True)
class Source:
    path: Path
    identity: str
    is_work: bool
    bullets: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Occurrence:
    source: Source
    section: str
    text: str
    index: int


_open_directory = classifications.open_directory


def _pointer_at(directory: int, name: str) -> str:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
            raise ValueError("Git pointer must be a small regular file")
        data = handle.read(8193)
        if len(data) > 8192:
            raise ValueError("Git pointer exceeds bound")
        return data.decode("utf-8", errors="strict").strip()


def _same_directory(left: int, right: int) -> bool:
    a, b = os.fstat(left), os.fstat(right)
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _git_directory_at(directory: int, pointer: str) -> int:
    """Resolve Git's relative pointers from the directory that supplied them.

    Unlike policy aliases, Git pointers legitimately contain '..'. Traverse
    those components through descriptors too; never rebase them on a pathname
    that may now name a replacement directory. Symlinks remain inadmissible.
    """
    path = Path(pointer)
    if not pointer:
        raise ValueError("empty Git directory pointer")
    descriptor = (os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                  if path.is_absolute() else os.dup(directory))
    components = path.parts[1:] if path.is_absolute() else path.parts
    try:
        for component in components:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _primary_owns_common(primary: Path, primary_fd: int, common_fd: int) -> bool:
    info = os.stat(".git", dir_fd=primary_fd, follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode):
        git_fd = os.open(".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=primary_fd)
    else:
        pointer = _pointer_at(primary_fd, ".git")
        if not pointer.startswith("gitdir: "):
            return False
        git_fd = _git_directory_at(primary_fd, pointer[len("gitdir: "):])
    try:
        return _same_directory(git_fd, common_fd)
    finally:
        os.close(git_fd)


def _root_matches_binding(root: Path, metadata: dict[str, Any], root_fd: int) -> bool:
    """Corroborate route identity using local Git pointers, never a Git process."""
    primary, common = Path(metadata["primary_abs_path"]), Path(metadata["git_common_dir"])
    try:
        info = os.stat(".git", dir_fd=root_fd, follow_symlinks=False)
        common_fd = _open_directory(common)
        try:
            primary_fd = root_fd if root == primary else _open_directory(primary)
            try:
                if not _primary_owns_common(primary, primary_fd, common_fd):
                    return False
            finally:
                if primary_fd != root_fd:
                    os.close(primary_fd)
            if root == primary:
                return True
            if stat.S_ISDIR(info.st_mode):
                return False
            pointer = _pointer_at(root_fd, ".git")
            if not pointer.startswith("gitdir: "):
                return False
            admin_fd = _git_directory_at(root_fd, pointer[len("gitdir: "):])
            try:
                # The pointer must name a direct registration in this opened
                # common store, not a same-spelled replacement on disk.
                parent_fd = _git_directory_at(admin_fd, "..")
                try:
                    worktrees_fd = os.open("worktrees", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                           dir_fd=common_fd)
                    try:
                        if not _same_directory(parent_fd, worktrees_fd):
                            return False
                    finally:
                        os.close(worktrees_fd)
                finally:
                    os.close(parent_fd)
                declared_fd = _git_directory_at(admin_fd, _pointer_at(admin_fd, "commondir"))
                try:
                    if not _same_directory(declared_fd, common_fd):
                        return False
                finally:
                    os.close(declared_fd)
                backpointer = Path(_pointer_at(admin_fd, "gitdir"))
                if backpointer.name != ".git":
                    return False
                observed_fd = _git_directory_at(admin_fd, str(backpointer.parent))
                try:
                    return _same_directory(observed_fd, root_fd)
                finally:
                    os.close(observed_fd)
            finally:
                os.close(admin_fd)
        finally:
            os.close(common_fd)
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return False


def _read_bullets(path: Path, *, no_follow: bool = False, root_fd: int | None = None) -> tuple[tuple[str, str], ...]:
    try:
        if no_follow:
            # The descriptor, not a prior path check, binds the admitted file.
            # NONBLOCK also avoids hanging if a workspace swaps in a FIFO.
            if root_fd is None:
                raise ConsolidationError("workspace directory descriptor is missing")
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=root_fd)
            with os.fdopen(descriptor, "r", encoding="utf-8", errors="strict") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ConsolidationError(f"workspace memory is not a regular file: {path}")
                text = handle.read()
        else:
            text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ConsolidationError(f"cannot parse {path}: {exc}") from exc
    # A valid-UTF8 file with no machine headings (e.g. a fresh clone's
    # human-readable placeholder) carries no memory yet, so it is skipped like an
    # empty file rather than failing the whole run. Undecodable bytes still fail
    # closed above, the home seed is still gated by its own explicit check, and
    # the final secret scanner still gates the projection.
    return tuple(memory.learned_bullets(text))


def _route_payload(
    agent_route: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if not agent_route.is_file():
        raise ConsolidationError(f"agent-route is unavailable at {agent_route}")
    command = ["/bin/bash", str(agent_route), "map", "--json"]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConsolidationError(f"agent-route failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        raise ConsolidationError(
            f"agent-route failed with exit {completed.returncode}"
            + (f": {detail}" if detail else "")
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConsolidationError(f"agent-route returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("roots"), list):
        raise ConsolidationError("agent-route JSON is missing roots[]")
    return payload


def _workspace_sources(
    payload: dict[str, Any],
    policy: classifications.Policy,
    seed_path: Path,
) -> tuple[list[Source], int, int]:
    unknown_roots = 0
    sources: list[Source] = []
    seen_paths: set[Path] = set()
    observed_origins: dict[str, str] = {}
    roots = payload["roots"]

    admitted_roots = []
    with ExitStack() as handles:
        # Corroborate every identity and detect global origin conflicts before
        # opening any workspace memory; keep those same admitted directories.
        for position, raw_root in enumerate(roots):
            if not isinstance(raw_root, dict):
                raise ConsolidationError(
                    f"agent-route roots[{position}] is not an object"
                )
            if raw_root.get("exists") is False:
                continue
            raw_path = raw_root.get("abs_path")
            if not isinstance(raw_path, str) or not raw_path:
                raise ConsolidationError(
                    f"agent-route roots[{position}] is missing abs_path"
                )
            root_path = Path(raw_path)
            if not root_path.is_absolute():
                raise ConsolidationError(
                    f"agent-route roots[{position}] abs_path is not absolute"
                )
            try:
                # Preserve lexical exclusions: resolving a recovery alias first
                # would erase its excluded location and borrow the active target.
                classifications.canonical_path(str(root_path))
            except classifications.PolicyError:
                unknown_roots += 1
                continue
            assigned = policy.resolve(raw_root, root_path)
            if assigned is None:
                unknown_roots += 1
                continue
            identity, kind = assigned
            try:
                root_fd = _open_directory(root_path)
            except OSError:
                unknown_roots += 1
                continue
            handles.callback(os.close, root_fd)
            if not _root_matches_binding(root_path, raw_root, root_fd):
                unknown_roots += 1
                continue
            for field in ("origin", "live_origin"):
                if raw_root.get(field):
                    origin = classifications.normalize_origin(raw_root[field])
                    previous_id = observed_origins.setdefault(origin, identity)
                    if previous_id != identity:
                        raise ConsolidationError("discovered origin conflicts across accepted repository IDs")
            admitted_roots.append((root_path, root_fd, identity, kind))
        for root_path, root_fd, identity, kind in admitted_roots:
            candidate = root_path / "agent-learnings.md"
            if candidate == seed_path or candidate in seen_paths:
                continue
            seen_paths.add(candidate)
            try:
                info = os.stat(candidate.name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                unknown_roots += 1
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            bullets = _read_bullets(candidate, no_follow=True, root_fd=root_fd)
            if not bullets:
                continue
            sources.append(Source(path=candidate, identity=identity,
                                  is_work=kind == "work", bullets=bullets))

    sources.sort(key=lambda item: (item.is_work, str(item.path)))
    return sources, len(roots), unknown_roots


def _admit(
    seed: Source,
    workspaces: list[Source],
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    seed_texts = {text for _, text in seed.bullets}
    occurrences = [
        Occurrence(source, section, text, index)
        for source in workspaces
        for index, (section, text) in enumerate(source.bullets)
    ]

    recurring: list[Occurrence] = []
    matched_seed = 0
    rejected_work = 0
    rejected_unconfirmed = 0
    for occurrence in occurrences:
        if occurrence.text in seed_texts:
            matched_seed += 1
            continue
        corroborating = [
            other
            for other in occurrences
            if other.source.identity != occurrence.source.identity
            and memory.near_duplicate(occurrence.text, other.text)
        ]
        has_non_work = not occurrence.source.is_work or any(
            not other.source.is_work for other in corroborating
        )
        if corroborating and has_non_work:
            recurring.append(occurrence)
        elif occurrence.source.is_work:
            rejected_work += 1
        else:
            rejected_unconfirmed += 1

    # Non-work phrasing wins before the equivalent work phrasing. The same
    # conservative near-duplicate predicate used for recurrence then removes the
    # work variant, preventing work-only detail from becoming canonical.
    recurring.sort(
        key=lambda item: (
            item.source.is_work,
            str(item.source.path),
            item.index,
        )
    )
    admitted = list(seed.bullets)
    admitted.extend((item.section, item.text) for item in recurring)
    return admitted, {
        "matched_home_seed": matched_seed,
        "recurring_admitted": len(recurring),
        "work_only_rejected": rejected_work,
        "unconfirmed_rejected": rejected_unconfirmed,
    }


def _projection(
    home: Path,
    payload: dict[str, Any],
    policy: classifications.Policy,
) -> tuple[bytes, dict[str, Any]]:
    seed_path = (home / "agent-learnings.md").resolve(strict=False)
    if not seed_path.is_file():
        raise ConsolidationError(f"home seed is missing: {seed_path}")
    seed_bullets = _read_bullets(seed_path)
    if not seed_bullets:
        raise ConsolidationError(f"home seed has no Learned bullets: {seed_path}")

    seed = Source(
        path=seed_path,
        identity="home-seed",
        is_work=False,
        bullets=seed_bullets,
    )
    workspaces, discovered_roots, unknown_roots = _workspace_sources(payload, policy, seed_path)
    sources = [seed, *workspaces]
    if not sources:
        raise ConsolidationError("no readable learning sources")

    admitted, admission = _admit(seed, workspaces)
    canonical = memory.consolidate(admitted)
    if not canonical:
        raise ConsolidationError("consolidation produced no bullets")
    rendered = MANAGED_HEADER + memory.render_learned(canonical)

    try:
        findings, blocked = memory.scan(rendered)
    except Exception as exc:
        raise ConsolidationError(f"final scanner failed: {exc}") from exc
    if blocked:
        rules = sorted(
            {item["rule"] for item in findings if item.get("severity") == "BLOCK"}
        )
        raise ConsolidationError(
            "final scanner blocked projection: " + ", ".join(rules)
        )

    report: dict[str, Any] = {
        "discovered_roots": discovered_roots,
        "unknown_or_excluded_roots": unknown_roots,
        "classification_schema": classifications.SCHEMA,
        "classification_sha256": policy.digest,
        "sources": len(sources),
        "workspace_sources": len(workspaces),
        "source_paths": [str(item.path) for item in sources],
        "input_bullets": sum(len(item.bullets) for item in sources),
        "home_seed_bullets": len(seed.bullets),
        "canonical_bullets": len(canonical),
        "deduplicated": len(admitted) - len(canonical),
        "scanner_warnings": sum(
            item.get("severity") == "WARN" for item in findings
        ),
        **admission,
    }
    return rendered.encode("utf-8"), report


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        pass

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _installed_runtime_root() -> Path | None:
    release = SCRIPT_DIR.parent
    if release.parent.name == "releases" and len(release.name) == 64:
        return release.parent.parent
    return None


@contextmanager
def _runtime_snapshot():
    release = SCRIPT_DIR.parent
    runtime = _installed_runtime_root()
    if runtime is None:
        yield  # Source-tree tests/runs are outside installed pointer activation.
        return
    with classifications.open_install_lock(runtime / ".install.lock") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        lock.seek(0)
        if lock.read(1):
            raise ConsolidationError("installation recovery is incomplete; keep consolidation paused")
        # A process can load the old script before blocking on the installer.
        # Refuse that snapshot after the exclusive publisher changes current.
        # The bin/current symlinks can change after Python reads the script but
        # before SCRIPT_DIR is resolved. Compare the executing module too.
        try:
            script_fd = _open_directory(SCRIPT_DIR)
            try:
                code, _ = classifications.read_regular_file(
                    Path("continual_learning_consolidate.py"), directory_fd=script_fd)
            finally:
                os.close(script_fd)
            current_code = compile(code, _LOADED_MODULE_CODE.co_filename, "exec",
                                   dont_inherit=True, optimize=sys.flags.optimize)
        except (OSError, ValueError, SyntaxError) as exc:
            raise ConsolidationError("cannot verify installed runtime code") from exc
        if ((runtime / "current").resolve(strict=False) != release
                or current_code != _LOADED_MODULE_CODE):
            raise ConsolidationError("installed runtime changed before startup; retry")
        yield


def consolidate_home(
    home: Path,
    agent_route: Path,
    *,
    dry_run: bool = False,
    policy_path: Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Consolidate once. All validation and scanning precede the atomic write."""
    with _runtime_snapshot():
        home = home.expanduser().resolve(strict=False)
        target = home / "AGENTS.md"
        if policy_path is None:
            runtime_root = _installed_runtime_root() or home / ".local/share/continual-learning-consolidate"
            policy_path = runtime_root / "classifications.json"
        try:
            policy = classifications.load_policy(policy_path)
        except classifications.PolicyError as exc:
            raise ConsolidationError(str(exc)) from exc
        payload = _route_payload(agent_route.expanduser(), runner=runner)
        content, report = _projection(home, payload, policy)

        previous = target.read_bytes() if target.is_file() else None
        changed = previous != content
        if changed and not dry_run:
            _atomic_write(target, content)
        return {
            **report,
            "target": str(target),
            "changed": changed,
            "dry_run": dry_run,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="continual-learning-consolidate")
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--agent-route",
        type=Path,
        default=Path.home()
        / ".cursor"
        / "skills"
        / "agent-route"
        / "scripts"
        / "agent-route.sh",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--classifications", type=Path, help="private active-source classification projection")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = consolidate_home(
            args.home,
            args.agent_route,
            dry_run=args.dry_run,
            policy_path=args.classifications,
        )
    except ConsolidationError as exc:
        print(f"continual-learning-consolidate: BLOCKED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"continual-learning-consolidate: BLOCKED: unexpected failure: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        state = "would update" if args.dry_run and report["changed"] else (
            "updated" if report["changed"] else "unchanged"
        )
        print(
            f"continual-learning-consolidate: {state} {report['target']} "
            f"({report['canonical_bullets']} bullets from "
            f"{report['sources']} sources)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
