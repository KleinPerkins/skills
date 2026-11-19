"""Atomic runtime install/repair over a portable payload — build plan v4 §13 M1 acceptance:
"Home-first and vendor-fixture-first installs converge to the same receipt; same digest is a
no-op; same-version/different-digest refuses for distributor payloads (tamper guard) but upgrades
from a home checkout or with ``--force``; interruption preserves the prior runtime; repair changes
runtime only; every state renders one plain next step."

Layout under ``runtime_root`` (``RuntimePaths.data_dir / "runtime"`` in production):

    runtime_root/<version>-<digest12>/   one immutable installed slot (never mutated after install)
    runtime_root/current -> <slot>       the ONLY thing a caller should read; swapped atomically

Every write below either creates a brand-new directory/tempfile and ``os.replace``s it into its
final name, or leaves existing state completely untouched — there is no code path that mutates a
slot or the ``current`` link in place, which is what makes "interruption preserves the prior
runtime" true by construction rather than by care.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from operator_voice.runtime.payload import load_manifest, verify_payload
from operator_voice.runtime.receipt import InstallReceipt, read_receipt, write_receipt


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for p in version.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _slot_dir(runtime_root: Path, version: str, digest: str) -> Path:
    return runtime_root / f"{version}-{digest[:12]}"


def _activate_slot(runtime_root: Path, slot_dir: Path) -> None:
    current_link = runtime_root / "current"
    tmp_link = runtime_root / f".tmp-current-{os.getpid()}"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(slot_dir, target_is_directory=True)
    os.replace(tmp_link, current_link)  # atomic — the single moment a new runtime becomes live


def _materialize_slot(payload_dir: Path, runtime_root: Path, slot_dir: Path) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp_dir = runtime_root / f".tmp-install-{os.getpid()}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    shutil.copytree(payload_dir, tmp_dir)
    if slot_dir.exists():
        shutil.rmtree(slot_dir)
    os.replace(tmp_dir, slot_dir)  # atomic — slot only appears fully-formed, never partial


def _current_slot_healthy(runtime_root: Path, receipt: InstallReceipt) -> bool:
    slot_dir = _slot_dir(runtime_root, receipt.version, receipt.digest)
    current_link = runtime_root / "current"
    if not (slot_dir.exists() and current_link.exists()):
        return False
    try:
        if current_link.resolve() != slot_dir.resolve():
            return False
    except OSError:
        return False
    return verify_payload(slot_dir)


def install_runtime(payload_dir: Path, runtime_root: Path, receipt_path: Path, source: str, *, force: bool = False) -> dict[str, Any]:
    manifest = load_manifest(payload_dir)
    existing = read_receipt(receipt_path)

    if existing is not None and not force:
        if existing.version == manifest.version and existing.digest == manifest.digest:
            return {
                "status": "up_to_date", "version": manifest.version, "digest": manifest.digest,
                "next_step": "nothing to do — this release is already installed",
            }
        if existing.version == manifest.version and existing.digest != manifest.digest:
            if source == "home":
                pass  # dev/operator loop: checkout may advance without a semver bump
            else:
                return {
                    "status": "refused", "version": manifest.version,
                    "reason": "installed version matches but the content digest differs (possible tamper or corruption)",
                    "next_step": "for an intentional same-version payload refresh, rerun with install.sh --force",
                }
        if _version_tuple(manifest.version) < _version_tuple(existing.version) and _current_slot_healthy(runtime_root, existing):
            return {
                "status": "refused", "installed_version": existing.version, "attempted_version": manifest.version,
                "reason": "the installed version is newer and healthy; refusing to downgrade",
                "next_step": "no action needed — the newer runtime is already active",
            }

    slot_dir = _slot_dir(runtime_root, manifest.version, manifest.digest)
    if not (force and slot_dir.exists() and verify_payload(slot_dir)):
        _materialize_slot(payload_dir, runtime_root, slot_dir)
    _activate_slot(runtime_root, slot_dir)
    write_receipt(receipt_path, manifest.version, manifest.digest, source)
    return {
        "status": "installed", "version": manifest.version, "digest": manifest.digest,
        "next_step": "run `operator-voice setup` to create local encrypted state",
    }


def repair_runtime(payload_dir: Path, runtime_root: Path, receipt_path: Path) -> dict[str, Any]:
    """Verifies/replaces the runtime payload ONLY. Never touches config/data/state beyond the
    receipt file and the ``runtime/`` subtree — this is a structural property (the function
    literally has no reference to any other :class:`RuntimePaths` directory), not a convention."""
    receipt = read_receipt(receipt_path)
    if receipt is None:
        return install_runtime(payload_dir, runtime_root, receipt_path, source="repair-fresh-install")

    manifest = load_manifest(payload_dir)
    if manifest.version != receipt.version or manifest.digest != receipt.digest:
        return {
            "status": "refused",
            "reason": "the available payload does not match the current receipt; repair never changes version — use install",
            "installed_version": receipt.version, "available_version": manifest.version,
            "next_step": "run install explicitly if you intend to change the installed version",
        }

    if _current_slot_healthy(runtime_root, receipt):
        return {"status": "ok", "version": receipt.version, "digest": receipt.digest, "next_step": "runtime payload verified — no repair needed"}

    return install_runtime(payload_dir, runtime_root, receipt_path, source=receipt.source, force=True)


__all__ = ["install_runtime", "repair_runtime"]
