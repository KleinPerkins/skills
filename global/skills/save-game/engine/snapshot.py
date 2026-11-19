"""Content-addressed sanitized snapshots.

A snapshot is an immutable, verbatim copy of a schema-valid active-state document
(the plan: "an immutable content-addressed copy of a schema-valid active state"),
stored under a filename that IS the SHA-256 hex digest of its own canonical bytes
— a DIFFERENT value from the document's own `current_digest` field (that digest
excludes volatile fields; this one is a plain content hash of everything as
persisted). Because the name is the content hash, `O_EXCL` collisions are
expected in the identical-content case: v2-hardened handling re-hashes the
existing bytes and reuses them only on an exact match; any mismatch is corrupt
evidence and fails closed.
"""

from __future__ import annotations

from pathlib import Path

from . import canonical, durability, paths


class CorruptEvidenceError(RuntimeError):
    """A snapshot filename (content hash) exists but its bytes don't match."""


def snapshot_bytes_for(active_state_doc: dict) -> bytes:
    return canonical.canonical_bytes(active_state_doc)


def write_snapshot(repo_key: str, clone_key: str, workstream_key: str, active_state_doc: dict) -> str:
    """Durably create the snapshot file; return its content digest (sha256 hex).

    Idempotent: calling this twice with byte-identical content reuses the first
    write rather than erroring.
    """
    data = snapshot_bytes_for(active_state_doc)
    digest = canonical.sha256_hex(data)
    path: Path = paths.snapshot_path(repo_key, clone_key, workstream_key, digest)
    try:
        durability.create_exclusive_durable(path, data)
    except FileExistsError:
        existing = durability.read_file_bytes(path)
        if existing != data:
            raise CorruptEvidenceError(
                f"snapshot digest collision at {path}: on-disk bytes do not match recomputed bytes"
            )
        # Identical content already durably present under this exact hash: reuse silently.
    return digest


def read_snapshot(repo_key: str, clone_key: str, workstream_key: str, sha256_hex: str) -> dict:
    import json

    path = paths.snapshot_path(repo_key, clone_key, workstream_key, sha256_hex)
    return json.loads(durability.read_file_bytes(path))
