#!/usr/bin/env python3
"""Install/restore addressed runtime and private policy under a local lock."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from classifications import open_directory, read_policy_file, read_regular_file  # noqa: E402


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_files(source: Path, *, directory_fd: int | None = None,
                  modes: dict[str, int] | None = None) -> dict[str, bytes]:
    owned = directory_fd is None
    if owned:
        source = source.resolve(strict=True)
        directory_fd = open_directory(source)
    try:
        result = {}
        for path in sorted((source / "scripts").rglob("*.py")):
            name = str(path.relative_to(source))
            content, mode = read_regular_file(Path(name), directory_fd=directory_fd)
            result[name] = content
            if modes is not None:
                modes[name] = mode
        return result
    finally:
        if owned:
            os.close(directory_fd)


def required_mode(name: str) -> int:
    return 0o755 if Path(name).parent.name == "scripts" else 0o644


def manifest(files: dict[str, bytes]) -> bytes:
    return (json.dumps({name: {"sha256": file_hash(data), "mode": required_mode(name)} for name, data in files.items()},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify_release(path: Path, release_id: str) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("release contains symlinks")
    descriptor = open_directory(path)
    try:
        recorded, _ = read_regular_file(Path("manifest.json"), directory_fd=descriptor)
        modes = {}
        files = release_files(path, directory_fd=descriptor, modes=modes)
        if file_hash(recorded) != release_id or manifest(files) != recorded:
            raise ValueError("release content failed address verification")
        if any(mode != required_mode(name) for name, mode in modes.items()):
            raise ValueError("release file mode failed verification")
    finally:
        os.close(descriptor)
    expected = set(json.loads(recorded)) | {"manifest.json"}
    actual = {str(p.relative_to(path)) for p in path.rglob("*") if not p.is_dir()}
    if expected != actual or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("release contains unexpected files or symlinks")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_directory(path: Path, mode: int = 0o755) -> None:
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(mode=mode if directory == path else 0o755, exist_ok=True)
        fsync_directory(directory.parent)


def write_release_file(path: Path, content: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fchmod(handle.fileno(), mode)
        os.fsync(handle.fileno())
    fsync_directory(path.parent)


def atomic_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    fd, name = tempfile.mkstemp(prefix=".policy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(name, path)
        fsync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def link_preimage(path: Path) -> str | None:
    if path.is_symlink():
        return os.readlink(path)
    if path.exists():
        raise ValueError(f"refusing to replace real path: {path}")
    return None


def atomic_link(path: Path, target: str | None) -> None:
    if target is None:
        path.unlink(missing_ok=True)
        fsync_directory(path.parent)
        return
    fd, name = tempfile.mkstemp(prefix=".link-", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink()
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def read_policy_preimage(path: Path) -> tuple[bytes | None, int | None]:
    try:
        return read_policy_file(path)
    except FileNotFoundError:
        return None, None


def recovery_marker(lock, pending: bool) -> None:
    lock.seek(0)
    if pending:
        if not lock.read(1):
            lock.write("pending recovery\n")
    else:
        lock.truncate(0)
    lock.flush()
    os.fsync(lock.fileno())


def restore_policy(path: Path, content: bytes | None, mode: int | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        fsync_directory(path.parent)
    else:
        atomic_bytes(path, content, mode)


def validate_target_policy(release: Path, policy: bytes) -> None:
    # Run only the verified target's validator in an isolated Python process.
    # Current-source validation alone cannot establish rollback compatibility.
    program = (
        "import hashlib,json,sys;sys.path.insert(0,sys.argv[1]);"
        "import classifications as c;data=sys.stdin.buffer.read();"
        "c.Policy(json.loads(data.decode('utf-8'),object_pairs_hook=c._unique_object),"
        "hashlib.sha256(data).hexdigest())"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", program, str(release / "scripts/lib")],
            input=policy, capture_output=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("target runtime policy validation timed out") from exc
    if result.returncode != 0:
        raise ValueError("target runtime rejects classification policy")


def install(args: argparse.Namespace) -> dict:
    root, bin_dir = args.runtime.resolve(), args.bin_dir.resolve()
    ensure_directory(root, mode=0o700)
    ensure_directory(bin_dir)
    with (root / ".install.lock").open("a+") as lock:
        os.chmod(root / ".install.lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        lock.seek(0)
        was_pending = bool(lock.read(1))
        current, binary = root / "current", bin_dir / "continual-learning-consolidate"
        previous_current, previous_binary = link_preimage(current), link_preimage(binary)
        managed_binary = str(current / "scripts/continual_learning_consolidate.py")
        if previous_binary is not None and previous_binary != managed_binary:
            raise ValueError("refusing to replace nonmanaged binary symlink")
        if args.expected_current is not None:
            observed = Path(previous_current).name if previous_current else "absent"
            if args.expected_current != observed or (previous_current is not None and previous_current != str(root / "releases" / observed)):
                raise ValueError("current runtime preimage changed")
        policy = root / "classifications.json"
        previous_policy, previous_policy_mode = read_policy_preimage(policy)
        observed_policy = file_hash(previous_policy) if previous_policy is not None else "absent"
        if args.policy is not None:
            if args.expected_policy_sha256 is None:
                raise ValueError("policy installation requires --expected-policy-sha256 HASH|absent")
            if args.expected_policy_sha256 != observed_policy:
                raise ValueError("private policy preimage changed")
            candidate_policy, _ = read_policy_file(args.policy)
        else:
            if args.expected_policy_sha256 is not None and args.expected_policy_sha256 != observed_policy:
                raise ValueError("private policy preimage changed")
            candidate_policy = previous_policy
        if candidate_policy is None:
            raise ValueError("private classification policy is missing")
        from classifications import Policy, _unique_object
        Policy(json.loads(candidate_policy.decode("utf-8"), object_pairs_hook=_unique_object), file_hash(candidate_policy))
        releases = root / "releases"
        ensure_directory(releases)
        if args.rollback_to:
            if args.expected_current is None:
                raise ValueError("rollback requires --expected-current")
            release_id = args.rollback_to
            if len(release_id) != 64 or any(c not in "0123456789abcdef" for c in release_id):
                raise ValueError("rollback target must be a release digest")
            release = releases / release_id
            verify_release(release, release_id)
        else:
            files = release_files(args.source)
            required = {"scripts/continual_learning_consolidate.py", "scripts/lib/memory.py", "scripts/lib/classifications.py", "scripts/install_runtime.py"}
            if not required <= files.keys():
                raise ValueError("runtime source dependency missing")
            record = manifest(files)
            release_id = file_hash(record)
            release = releases / release_id
            if not release.exists():
                stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
                fsync_directory(root)
                try:
                    for name, content in files.items():
                        target = stage / name
                        ensure_directory(target.parent)
                        write_release_file(target, content, required_mode(name))
                    write_release_file(stage / "manifest.json", record, 0o644)
                    stage.rename(release)
                    fsync_directory(releases)
                    fsync_directory(root)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
            verify_release(release, release_id)
        validate_target_policy(release, candidate_policy)
        # The existing coordination lock also carries a one-bit incomplete
        # status. Readers refuse a mixed state until a successful repair.
        recovery_marker(lock, True)
        try:
            if candidate_policy != previous_policy or previous_policy_mode != 0o600:
                atomic_bytes(policy, candidate_policy)
            atomic_link(current, str(release))
            atomic_link(binary, str(current / "scripts/continual_learning_consolidate.py"))
            if (link_preimage(current) != str(release)
                    or link_preimage(binary) != managed_binary
                    or read_policy_preimage(policy) != (candidate_policy, 0o600)):
                raise ValueError("published runtime/policy verification failed")
        except Exception as failure:
            inverses = {
                "current": lambda: atomic_link(current, previous_current),
                "binary": lambda: atomic_link(binary, previous_binary),
                "policy": lambda: restore_policy(policy, previous_policy, previous_policy_mode),
            }
            checks = {
                "current": lambda: link_preimage(current) == previous_current,
                "binary": lambda: link_preimage(binary) == previous_binary,
                "policy": lambda: read_policy_preimage(policy) == (previous_policy, previous_policy_mode),
            }
            recovery = {}
            for name, inverse in inverses.items():
                entry = {}
                try:
                    inverse()
                except Exception as error:
                    entry["inverse_error"] = str(error)
                try:
                    entry["restored"] = checks[name]()
                except Exception as error:
                    entry.update(restored=False, verification_error=str(error))
                recovery[name] = entry
            restored = all(entry["restored"] and "inverse_error" not in entry
                           and "verification_error" not in entry
                           for entry in recovery.values())
            if restored and not was_pending:
                try:
                    recovery_marker(lock, False)
                except Exception as error:
                    recovery["marker_error"] = str(error)
            lock.seek(0)
            recovery["runtime_blocked"] = bool(lock.read(1))
            raise ValueError("installation failed; recovery=" + json.dumps(recovery, sort_keys=True)) from failure
        # A verified successful retry can repair a previously incomplete state.
        recovery_marker(lock, False)
        return {"release_id": release_id, "classification_sha256": file_hash(candidate_policy),
                "previous_release": previous_current, "runtime": str(root)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--expected-policy-sha256")
    parser.add_argument("--expected-current")
    parser.add_argument("--rollback-to")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"continual-learning-consolidate install: BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
