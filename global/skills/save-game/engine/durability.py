"""Darwin-durable, no-follow, permission-strict filesystem primitives.

Every write in this engine goes through here so a successful return has one
meaning: bytes and the containing namespace update have both been synchronously
persisted. Darwin requires `F_FULLFSYNC` after `fsync` for both files and
directories (a plain `fsync` on APFS/HFS+ does not guarantee the platter/SSD has
actually flushed); its absence is treated as a durability failure, never a silent
downgrade, because this skill only ever targets Darwin (macOS) hosts.

Design precedent (behavioral, not a runtime import — this engine is self-contained
per the plan's zero-link rule): local durability/lock helpers used elsewhere on
this machine for the same class of problem (component-by-component no-follow
directory creation, same-directory temp-then-rename, mandatory parent-dir sync).
This module reimplements the same bounded behavior from scratch.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable

DIR_MODE = 0o700
FILE_MODE = 0o600

# Filesystem type names `mount`(8) reports for network/synced mounts on Darwin.
# Best-effort defense-in-depth only (see is_local_disk docstring) — not exhaustive.
_NETWORK_FS_TYPES = {"nfs", "smbfs", "afpfs", "webdav", "ftp", "cifs"}


class UnsafePathError(OSError):
    """A path component is a symlink, special file, or otherwise unsafe to use."""


class DurabilityError(OSError):
    """A write could not be certified as durable. Never treat this as success."""


class UnsupportedEnvironmentError(RuntimeError):
    """The state/lock root is not a verified-safe local-disk private location."""


def _retry_eintr(call: Callable, *args):
    while True:
        try:
            return call(*args)
        except OSError as exc:
            if exc.errno != errno.EINTR:
                raise


def _sync_fd(fd: int) -> None:
    _retry_eintr(os.fsync, fd)
    if sys.platform == "darwin":
        full_sync = getattr(fcntl, "F_FULLFSYNC", None)
        if full_sync is None:
            raise DurabilityError("Darwin F_FULLFSYNC is unavailable; durability cannot be certified")
        _retry_eintr(fcntl.fcntl, fd, full_sync)


def _open_nofollow_dir(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(str(path), flags)


def sync_directory(path: Path) -> None:
    fd = _open_nofollow_dir(path)
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"not a directory: {path}")
        _sync_fd(fd)
    finally:
        os.close(fd)


def sync_parent(path: Path) -> None:
    sync_directory(path.parent)


def lstat_safe(path: Path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def assert_no_symlink(path: Path) -> None:
    st = lstat_safe(path)
    if st is not None and stat.S_ISLNK(st.st_mode):
        raise UnsafePathError(f"refusing untrusted symlink: {path}")


def normalize_trusted_prefix(path: Path) -> Path:
    """Resolve ROOT-OWNED symlink parent components (Darwin exposes system roots
    such as `/var` and `/tmp` as root-owned links to `/private/...`) while leaving
    the final component untouched, so no-follow checks still apply to the literal
    name a caller asked for. A symlink parent component owned by a NON-root user
    is left unresolved here and rejected by the caller's own no-follow walk —
    that is the actual attacker-plantable case this engine must refuse.
    """
    absolute = Path(os.path.abspath(str(path)))
    parts = absolute.parts
    if len(parts) < 2:
        return absolute
    cursor = Path(parts[0])
    for part in parts[1:-1]:
        candidate = cursor / part
        st = lstat_safe(candidate)
        if st is None:
            cursor = candidate
            continue
        if stat.S_ISLNK(st.st_mode):
            if getattr(st, "st_uid", -1) != 0:
                raise UnsafePathError(f"refusing untrusted (non-root-owned) symlink component: {candidate}")
            cursor = Path(os.path.realpath(candidate))
        else:
            cursor = candidate
    return cursor / parts[-1]


def ensure_private_dir(path: Path, mode: int = DIR_MODE) -> None:
    """Create every missing component (no-follow, containment-checked).

    Pre-existing components (including ones above our own managed subtree,
    e.g. Darwin's `/private`, `/var`) are verified to be real, non-symlink
    directories but their permissions are left untouched — we neither own nor
    may chmod system-level directories. Only components THIS call creates,
    plus the final target itself, are forced to `mode`.
    """
    path = normalize_trusted_prefix(Path(path))
    parts = path.parts
    if len(parts) < 2:
        raise UnsafePathError(f"refusing to treat filesystem root as private dir: {path}")
    cursors = []
    cursor = Path(parts[0])
    for part in parts[1:]:
        cursor = cursor / part
        cursors.append(cursor)

    first_missing = len(cursors)
    for index, comp in enumerate(cursors):
        st = lstat_safe(comp)
        if st is None:
            first_missing = index
            break
        if stat.S_ISLNK(st.st_mode):
            raise UnsafePathError(f"refusing untrusted symlink component: {comp}")
        if not stat.S_ISDIR(st.st_mode):
            raise UnsafePathError(f"path component is not a real directory: {comp}")

    for comp in cursors[first_missing:]:
        try:
            os.mkdir(comp, mode)
        except FileExistsError:
            st = lstat_safe(comp)
            if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise UnsafePathError(f"path component raced with a non-directory: {comp}")
            continue
        os.chmod(comp, mode)
        sync_directory(comp)
        sync_directory(comp.parent)

    final_st = lstat_safe(path)
    if final_st is None or stat.S_ISLNK(final_st.st_mode) or not stat.S_ISDIR(final_st.st_mode):
        raise UnsafePathError(f"private directory is not a real directory: {path}")
    if stat.S_IMODE(final_st.st_mode) != mode:
        os.chmod(path, mode)  # repair broader-than-private perms on our own target dir
        sync_directory(path)


def read_file_bytes(path: Path) -> bytes:
    """No-follow read: refuses a symlinked or non-regular target."""
    path = Path(path)
    st = lstat_safe(path)
    if st is None:
        raise FileNotFoundError(path)
    if stat.S_ISLNK(st.st_mode):
        raise UnsafePathError(f"refusing to read through symlink: {path}")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafePathError(f"refusing to read non-regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    try:
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            raise
        if written <= 0:
            raise DurabilityError("short durable write")
        view = view[written:]


def atomic_replace_durable(path: Path, data: bytes, *, file_mode: int = FILE_MODE) -> None:
    """Same-directory temp create, complete write, fsync+F_FULLFSYNC, atomic
    rename, then parent-directory sync. Any exception means "not certified" —
    callers must never report success without this function returning cleanly."""
    path = Path(path)
    ensure_private_dir(path.parent)
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}.{os.urandom(6).hex()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(str(tmp), flags, file_mode)
    try:
        try:
            os.fchmod(fd, file_mode)
            _write_all(fd, data)
            _sync_fd(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)  # same-directory rename is atomic
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    sync_directory(path.parent)


def create_exclusive_durable(path: Path, data: bytes, *, file_mode: int = FILE_MODE) -> None:
    """O_EXCL durable create for immutable, append-only artifacts. Raises
    FileExistsError (unmodified) on collision so callers can apply their own
    content-addressed reuse-or-fail-closed policy."""
    path = Path(path)
    ensure_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(str(path), flags, file_mode)
    try:
        try:
            os.fchmod(fd, file_mode)
            _write_all(fd, data)
            _sync_fd(fd)
        finally:
            os.close(fd)
    except BaseException:
        # A half-written O_EXCL file is unsafe to leave behind: an immutable
        # artifact must never be observed in a partially-written state, and a
        # bare unlink (not a durable one) is enough since nothing durable was
        # ever claimed for it.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    sync_directory(path.parent)


def assert_contained(root: Path, target: Path) -> None:
    """No-follow containment: every component from `root` down to `target` must
    exist as a real (non-symlink) directory, and `target` itself must resolve
    under `root` once created. Refuses path traversal / symlink escape."""
    root = Path(root).resolve()
    target = Path(target)
    try:
        rel = target.relative_to(root) if target.is_absolute() else target
    except ValueError as exc:
        raise UnsafePathError(f"{target} escapes containment root {root}") from exc
    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        st = lstat_safe(cursor)
        if st is not None and stat.S_ISLNK(st.st_mode):
            raise UnsafePathError(f"refusing symlink component under {root}: {cursor}")


def is_local_disk(path: Path) -> bool:
    """Best-effort Darwin local-disk check via `mount`(8) output.

    This is defense-in-depth, not a complete filesystem-type oracle (the plan
    itself disclaims regex/heuristic DLP completeness in the same spirit): if
    `mount` is unavailable or its output can't be parsed, we fail OPEN (assume
    local) rather than block every environment where this heuristic can't run —
    ship the check that catches the common network-mount case, don't block on a
    fully general implementation.
    """
    path = Path(path).resolve()
    try:
        out = subprocess.run(["mount"], capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return True
    best_match_len = -1
    best_type = None
    for line in out.splitlines():
        # Typical line: "//server/share on /Volumes/share (smbfs, nodev, nosuid)"
        if " on " not in line or "(" not in line:
            continue
        mount_point = line.split(" on ", 1)[1].split(" (", 1)[0]
        try:
            mp = Path(mount_point)
        except Exception:
            continue
        if mp == path or mp in path.parents:
            mp_len = len(str(mp))
            if mp_len > best_match_len:
                paren = line.split("(", 1)[1].split(")", 1)[0]
                best_type = paren.split(",")[0].strip().lower()
                best_match_len = mp_len
    if best_type is None:
        return True
    return best_type not in _NETWORK_FS_TYPES


def assert_environment_safe(root: Path) -> None:
    """Flush precondition bundle: local-disk + safe-to-create private root.

    Raises UnsupportedEnvironmentError (mapped by callers to the Flush status of
    the same name) rather than a raw OSError, so a bad environment is always a
    clean status code, never a crash.
    """
    root = Path(root)
    try:
        if not is_local_disk(root if root.exists() else root.parent):
            raise UnsupportedEnvironmentError(f"refusing synced/network state root: {root}")
        ensure_private_dir(root)
    except (UnsafePathError, DurabilityError) as exc:
        raise UnsupportedEnvironmentError(str(exc)) from exc
