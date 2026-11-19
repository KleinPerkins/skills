"""Deterministic, personal-data-free portable runtime payload — build plan v4 §6.1/§8.1: "a
deterministic, personal-data-free portable runtime payload generated from that same release so
the orchestrator can vendor working bytes into a governed downstream product repo without
exposing the private SSP repo or any operator data."

A payload is just a content-addressed snapshot of the INSTALLED package tree (exactly what a
wheel build would ship — see ``pyproject.toml``'s ``[tool.hatch.build.targets.wheel] packages``):
every ``.py``/``.md``/``.json`` file under ``src/operator_voice/``, nothing else. The digest is a
pure function of (relative path, content) pairs, sorted, so it is identical no matter which
distributor (a Laurence home checkout vs. a hermetic future vendor-fixture clone) produced the
tree, as long as the underlying release content is byte-identical — this is the "home and
vendor-fixture-first installs converge to the same receipt" acceptance property (§13 M1).
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

PAYLOAD_MANIFEST_VERSION = "payload-manifest/v1"
TOOL_RUNTIME_CONTRACT_VERSION = "tool-runtime-contract/v1"

# Deliberately narrow: only file types that can plausibly be *source*, never operator data. A
# stray `.sqlite3`/`.keychain-db`/`.env` accidentally copied into the package tree would be
# excluded by this allowlist rather than silently included in a "personal-data-free" claim.
_ALLOWED_SUFFIXES = frozenset({".py", ".md", ".json", ".toml"})

# Hard denylist double-check (belt + suspenders over the allowlist above): if the SOURCE tree ever
# contains one of these, refuse to build a payload at all rather than silently omitting it, since
# their presence usually means something ran in-place inside the package directory it shouldn't have.
_FORBIDDEN_SUFFIXES = frozenset({".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".keychain-db", ".env", ".pem", ".key"})


class PayloadIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class PayloadManifest:
    schema: str
    version: str
    digest: str
    file_count: int
    files: tuple[str, ...]  # sorted relative posix paths, for audit/diffing


def _iter_source_files(package_root: Path) -> list[Path]:
    return sorted(p for p in package_root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def _relative_posix(package_root: Path, path: Path) -> str:
    return path.relative_to(package_root.parent).as_posix()


def compute_digest(package_root: Path) -> tuple[str, tuple[str, ...]]:
    files = _iter_source_files(package_root)
    forbidden = [f for f in files if f.suffix in _FORBIDDEN_SUFFIXES]
    if forbidden:
        raise PayloadIntegrityError(
            f"refusing to build a payload: forbidden file type(s) present in source tree: "
            f"{[str(f) for f in forbidden]}"
        )
    included = [f for f in files if f.suffix in _ALLOWED_SUFFIXES]
    hasher = hashlib.sha256()
    rel_paths: list[str] = []
    for f in included:
        rel = _relative_posix(package_root, f)
        rel_paths.append(rel)
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(f.read_bytes())
        hasher.update(b"\x00")
    return hasher.hexdigest(), tuple(sorted(rel_paths))


def build_portable_payload(package_root: Path, output_dir: Path, version: str) -> PayloadManifest:
    """Copies every allowlisted file from ``package_root`` (an ``operator_voice`` package
    directory) into ``output_dir`` preserving relative structure, and writes
    ``payload-manifest.json`` alongside it. Refuses (raises :class:`PayloadIntegrityError`) if a
    forbidden file type is present anywhere in the source tree, even one this payload would not
    have copied — the presence itself is the signal something is wrong."""
    digest, rel_paths = compute_digest(package_root)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    for rel in rel_paths:
        src = package_root.parent / rel
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    manifest = PayloadManifest(
        schema=PAYLOAD_MANIFEST_VERSION, version=version, digest=digest, file_count=len(rel_paths), files=rel_paths
    )
    _write_manifest(output_dir, manifest)
    _write_tool_runtime_contract(output_dir, package_root.name)
    return manifest


def _write_manifest(output_dir: Path, manifest: PayloadManifest) -> None:
    import json

    payload = {
        "schema": manifest.schema,
        "version": manifest.version,
        "digest": manifest.digest,
        "file_count": manifest.file_count,
        "files": list(manifest.files),
    }
    (output_dir / "payload-manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_tool_runtime_contract(output_dir: Path, package_name: str) -> None:
    """Writes ``tool-runtime.json`` at the payload ROOT — a sibling of ``payload-manifest.json``,
    OUTSIDE the ``<package_name>/`` tree ``compute_digest`` hashes (so it never affects the digest;
    only the package tree's own content does). This is the generic, cross-repo contract that any
    downstream ``kind: tool`` installer/reconciler — authored under that downstream repository's OWN
    governance, never by this project or an intermediating orchestrator — reads to provision a
    runnable Python CLI from these vendored bytes without importing this package's code or guessing
    its shape. Deliberately NOT operator-voice-specific in schema: any future ``shape: snapshot``
    Python tool payload with a ``<package>/runtime/requirements.json`` (schema
    ``runtime-requirements/v1``) and a ``python -m <entrypoint_module>``-runnable module satisfies
    it identically. ``requirements_file``/``entrypoint_module`` are payload-root-relative paths /
    dotted module names respectively — never a filesystem path outside the payload."""
    import json

    contract = {
        "schema": TOOL_RUNTIME_CONTRACT_VERSION,
        "runtime": "python",
        "python_min": "3.12",
        "package": package_name,
        "requirements_file": f"{package_name}/runtime/requirements.json",
        "entrypoint_module": f"{package_name}.interfaces.cli",
    }
    (output_dir / "tool-runtime.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(payload_dir: Path) -> PayloadManifest:
    import json

    data = json.loads((payload_dir / "payload-manifest.json").read_text(encoding="utf-8"))
    return PayloadManifest(
        schema=data["schema"], version=data["version"], digest=data["digest"],
        file_count=data["file_count"], files=tuple(data["files"]),
    )


def verify_payload(payload_dir: Path) -> bool:
    """Re-derives the digest of the files ON DISK under ``payload_dir`` (excluding the manifest
    itself) and compares it to the recorded manifest digest. Used by ``repair`` to detect a
    corrupted/tampered installed runtime."""
    manifest = load_manifest(payload_dir)
    package_root = payload_dir / "operator_voice"
    if not package_root.exists():
        return False
    digest, _ = compute_digest(package_root)
    return digest == manifest.digest


__all__ = [
    "PayloadManifest",
    "PayloadIntegrityError",
    "TOOL_RUNTIME_CONTRACT_VERSION",
    "build_portable_payload",
    "compute_digest",
    "load_manifest",
    "verify_payload",
]
