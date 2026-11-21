"""Per-workstream advisory lock (plan: "Workstream locks use bounded flock").

CAS generation/digest checks and all phase writes must occur inside this same
lock. Different workstreams never contend (each gets its own lockfile keyed by
`workstream_key`); same-workstream callers serialize, and a caller that cannot
acquire the lock within the bound gets `LockTimeoutError` (mapped by contracts to
the Flush `LOCK_BUSY` status) rather than blocking forever.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import time
from contextlib import contextmanager

from . import durability, paths


class LockTimeoutError(RuntimeError):
    """A bounded, non-blocking-retry acquire could not get the lock in time."""


@contextmanager
def observe_workstream_lock(workstream_key: str):
    """Share the owner's existing lock without creating or changing its record."""
    path = paths.lock_path(workstream_key)
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != durability.FILE_MODE):
            raise ValueError("unsafe observation lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockTimeoutError("workstream writer active") from exc
        def check_lock_path():
            visible = path.lstat()
            if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
                raise ValueError("observation lock changed")
        check_lock_path()
        yield
        check_lock_path()
    finally:
        os.close(fd)


@contextmanager
def workstream_lock(workstream_key: str, *, timeout: float = 10.0, poll_interval: float = 0.05):
    lf = paths.lock_path(workstream_key)
    durability.ensure_private_dir(lf.parent)
    fd = os.open(str(lf), os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), durability.FILE_MODE)
    acquired = False
    try:
        os.chmod(lf, durability.FILE_MODE)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(f"workstream lock busy after {timeout:g}s: {lf}")
                time.sleep(poll_interval)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            os.fsync(fd)
        except OSError:
            pass  # diagnostics only — never the identity/authority boundary
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
