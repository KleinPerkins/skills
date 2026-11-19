#!/usr/bin/env python3
"""Authoring engine for local-jobs job types (add-job-type / update-job-type).

The CLI scaffolders are thin shells over these primitives so the safety logic
lives in one tested place:

  - ``verify_type``   — a type conforms iff describe + every instance validate
    against the contract (no quarantine row) and its ``doctor`` returns PASS.
  - ``regression``    — every *other* registered type still verifies, so adding
    or evolving one type can never silently break discovery for the rest.
  - ``register_type`` / ``unregister_type`` — atomic registry.yml edits (write a
    sibling temp + ``os.replace``) with a backup the caller restores on rollback.

This is the executable engine only; the operator-facing authoring flow doc lives
with the skill (owned separately).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402
import registry  # noqa: E402
import settings  # noqa: E402

import yaml  # noqa: E402


def verify_type(job_type: str, reg: dict[str, Any] | None = None, run_doctor: bool = True) -> dict[str, Any]:
    """A type conforms iff it discovers cleanly (no quarantine) and doctors PASS."""
    reg = reg or registry.load_registry()
    errors: list[str] = []
    rows = registry.collect_for_type(job_type, reg)
    quarantine = [r for r in rows if r.get("role") == "error"]
    for q in quarantine:
        err = q.get("error") or {}
        errors.append(f"{err.get('verb', 'discover')}: {err.get('reason')}")
    instances = [r for r in rows if r.get("role") != "error"]

    if run_doctor and not errors:
        try:
            proc = subprocess.run(
                [str(registry.handler_path(job_type, reg)), "doctor"],
                capture_output=True, text=True, timeout=registry.HANDLER_TIMEOUT,
            )
            if proc.returncode != 0:
                errors.append(f"doctor failed (rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[-300:]}")
        except subprocess.TimeoutExpired:
            errors.append("doctor timed out")
        except SystemExit as exc:
            errors.append(str(exc))

    return {"type": job_type, "ok": not errors, "errors": errors, "instances": len(instances)}


def regression(exclude: str | None = None, reg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify every registered type (optionally excluding one) still conforms."""
    reg = reg or registry.load_registry()
    results = []
    for jtype in registry.job_types(reg):
        if jtype == exclude:
            continue
        results.append(verify_type(jtype, reg))
    return {"ok": all(r["ok"] for r in results), "results": results}


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def overlay_fragment(job_type: str) -> Path:
    return registry.overlay_dir() / f"{job_type}.yml"


def backup_registry() -> Path:
    src = overlay_fragment(".registry-overlay-backup")
    src.parent.mkdir(parents=True, exist_ok=True)
    fd, dst = tempfile.mkstemp(dir=str(src.parent), suffix=".overlay.bak")
    os.close(fd)
    Path(dst).write_text(json.dumps({"overlay_dir": str(src.parent)}))
    return Path(dst)


def restore_registry(backup: Path) -> None:
    # Overlay registration is file-per-type; rollback removes the registered
    # fragment recorded in the backup marker.
    if backup.is_file():
        try:
            data = json.loads(backup.read_text() or "{}")
            frag = data.get("fragment")
            if frag:
                Path(frag).unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            pass
        backup.unlink()


def register_type(job_type: str, handler_rel: str, description: str = "") -> dict[str, Any]:
    """Register operator-private types in the overlay, never in the managed base."""
    data = registry.load_registry()
    if job_type in registry.job_types(data):
        raise SystemExit(f"job type already registered: {job_type}")
    handler_path = Path(handler_rel).expanduser()
    if not handler_path.is_absolute():
        handler_path = settings.state_dir() / "handlers" / Path(handler_rel).name
    if not handler_path.is_file() or not os.access(handler_path, os.X_OK):
        raise SystemExit(f"overlay handler is not executable: {handler_path}")
    frag = overlay_fragment(job_type)
    entry: dict[str, Any] = {"id": job_type, "handler": str(handler_path)}
    if description:
        entry["description"] = description
    _atomic_write(frag, entry)
    backup = frag.with_suffix(frag.suffix + ".rollback")
    backup.write_text(json.dumps({"fragment": str(frag)}))
    return {"registered": job_type, "backup": str(backup)}


def unregister_type(job_type: str) -> dict[str, Any]:
    frag = overlay_fragment(job_type)
    if frag.is_file():
        frag.unlink()
    return {"unregistered": job_type}


def main() -> int:
    ap = argparse.ArgumentParser(prog="authoring.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_v = sub.add_parser("verify"); p_v.add_argument("--type", required=True); p_v.add_argument("--no-doctor", action="store_true")
    p_r = sub.add_parser("regression"); p_r.add_argument("--exclude", default=None)
    p_reg = sub.add_parser("register"); p_reg.add_argument("--type", required=True); p_reg.add_argument("--handler", required=True); p_reg.add_argument("--description", default="")
    p_un = sub.add_parser("unregister"); p_un.add_argument("--type", required=True)
    p_bak = sub.add_parser("restore-registry"); p_bak.add_argument("--backup", required=True)
    args = ap.parse_args()

    if args.cmd == "verify":
        result = verify_type(args.type, run_doctor=not args.no_doctor)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    if args.cmd == "regression":
        result = regression(exclude=args.exclude)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    if args.cmd == "register":
        print(json.dumps(register_type(args.type, args.handler, args.description)))
        return 0
    if args.cmd == "unregister":
        print(json.dumps(unregister_type(args.type)))
        return 0
    if args.cmd == "restore-registry":
        restore_registry(Path(args.backup))
        print(json.dumps({"restored": str(registry.registry_path())}))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
