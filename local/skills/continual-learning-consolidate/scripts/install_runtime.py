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
from classifications import load_policy  # noqa: E402


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_files(source: Path) -> dict[str, bytes]:
    return {str(path.relative_to(source)): path.read_bytes()
            for path in sorted((source / "scripts").rglob("*.py"))}


def required_mode(name: str) -> int:
    return 0o755 if Path(name).parent.name == "scripts" else 0o644


def manifest(files: dict[str, bytes]) -> bytes:
    return (json.dumps({name: {"sha256": file_hash(data), "mode": required_mode(name)} for name, data in files.items()},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify_release(path: Path, release_id: str) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("release contains symlinks")
    recorded = (path / "manifest.json").read_bytes()
    if file_hash(recorded) != release_id or manifest(release_files(path)) != recorded:
        raise ValueError("release content failed address verification")
    for name, entry in json.loads(recorded).items():
        if stat.S_IMODE((path / name).stat().st_mode) != entry["mode"]:
            raise ValueError("release file mode failed verification")
    expected = set(json.loads(recorded)) | {"manifest.json"}
    actual = {str(p.relative_to(path)) for p in path.rglob("*") if not p.is_dir()}
    if expected != actual or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("release contains unexpected files or symlinks")


def atomic_bytes(path: Path, content: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".policy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
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
        return
    fd, name = tempfile.mkstemp(prefix=".link-", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink()
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    bin_dir.mkdir(parents=True, exist_ok=True)
    with (root / ".install.lock").open("a") as lock:
        os.chmod(root / ".install.lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        current, binary = root / "current", bin_dir / "continual-learning-consolidate"
        previous_current, previous_binary = link_preimage(current), link_preimage(binary)
        if args.expected_current is not None:
            observed = Path(previous_current).name if previous_current else "absent"
            if args.expected_current != observed or (previous_current is not None and previous_current != str(root / "releases" / observed)):
                raise ValueError("current runtime preimage changed")
        policy = root / "classifications.json"
        if policy.is_symlink() or (policy.exists() and not policy.is_file()):
            raise ValueError("private policy must be a regular file")
        previous_policy = policy.read_bytes() if policy.exists() else None
        previous_policy_mode = policy.stat().st_mode & 0o777 if policy.exists() else None
        observed_policy = file_hash(previous_policy) if previous_policy is not None else "absent"
        if args.policy is not None:
            if args.expected_policy_sha256 is None:
                raise ValueError("policy installation requires --expected-policy-sha256 HASH|absent")
            if args.expected_policy_sha256 != observed_policy:
                raise ValueError("private policy preimage changed")
            candidate_policy = args.policy.read_bytes()
            # Validate exactly the bytes later installed, avoiding input rereads.
            from classifications import Policy, _unique_object
            Policy(json.loads(candidate_policy.decode("utf-8"), object_pairs_hook=_unique_object), file_hash(candidate_policy))
        else:
            if args.expected_policy_sha256 is not None and args.expected_policy_sha256 != observed_policy:
                raise ValueError("private policy preimage changed")
            load_policy(policy)
            candidate_policy = previous_policy
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
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
                try:
                    for name, content in files.items():
                        target = stage / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
                        target.chmod(required_mode(name))
                    (stage / "manifest.json").write_bytes(record)
                    stage.rename(release)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
            verify_release(release, release_id)
        validate_target_policy(release, candidate_policy)
        # All policy/source/path validation precedes changing live pointers.
        # Keep the old release and restore exact preimages on any local failure.
        try:
            if candidate_policy != previous_policy or previous_policy_mode != 0o600:
                atomic_bytes(policy, candidate_policy)
            atomic_link(current, str(release))
            atomic_link(binary, str(current / "scripts/continual_learning_consolidate.py"))
        except Exception:
            atomic_link(current, previous_current)
            atomic_link(binary, previous_binary)
            if previous_policy is None:
                policy.unlink(missing_ok=True)
            else:
                atomic_bytes(policy, previous_policy)
                os.chmod(policy, previous_policy_mode)
            raise
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
