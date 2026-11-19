"""Thin argparse CLI over ``runtime.payload``/``runtime.install`` — the one thing the repo-root
``install.sh`` (the SSP's own installer) shells out to. Kept separate from ``interfaces.cli``
(the operator-facing operation-registry CLI) because this runs BEFORE the package is necessarily
importable from its final installed location — it is invoked with ``PYTHONPATH`` pointed at the
git checkout's ``src/`` during bootstrap, never at an already-installed runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from operator_voice.runtime.install import install_runtime, repair_runtime
from operator_voice.runtime.payload import PayloadIntegrityError, build_portable_payload, compute_digest
from operator_voice.runtime.receipt import read_receipt


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source-root", required=True, help="path to a checkout's src/operator_voice")
    p.add_argument("--runtime-root", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--version", default=None, help="defaults to operator_voice.__version__")


def _resolve_version(explicit: str | None, source_root: Path) -> str:
    if explicit:
        return explicit
    sys.path.insert(0, str(source_root.parent))
    import operator_voice  # noqa: E402  (deliberately deferred; source_root varies at runtime)

    return operator_voice.__version__


def cmd_install(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    version = _resolve_version(args.version, source_root)
    with tempfile.TemporaryDirectory(prefix="ovt-payload-") as tmp:
        payload_dir = Path(tmp) / "payload"
        build_portable_payload(source_root, payload_dir, version=version)
        result = install_runtime(payload_dir, Path(args.runtime_root), Path(args.receipt), source=args.source, force=args.force)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("installed", "up_to_date") else 1


def cmd_repair(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    version = _resolve_version(args.version, source_root)
    with tempfile.TemporaryDirectory(prefix="ovt-payload-") as tmp:
        payload_dir = Path(tmp) / "payload"
        build_portable_payload(source_root, payload_dir, version=version)
        result = repair_runtime(payload_dir, Path(args.runtime_root), Path(args.receipt))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("installed", "ok") else 1


def cmd_check(args: argparse.Namespace) -> int:
    """CI-safe static preflight: no writes, no network. Verifies the source tree can produce a
    valid payload (no forbidden file types) and that Python is new enough."""
    problems: list[str] = []
    if sys.version_info < (3, 12):
        problems.append(f"python {sys.version_info.major}.{sys.version_info.minor} < required 3.12")
    try:
        compute_digest(Path(args.source_root))
    except PayloadIntegrityError as exc:
        problems.append(str(exc))
    except OSError as exc:
        problems.append(f"cannot read source root: {exc}")
    result = {"status": "ok" if not problems else "failed", "problems": problems}
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    receipt = read_receipt(Path(args.receipt))
    runtime_root = Path(args.runtime_root)
    current = runtime_root / "current"
    result = {
        "receipt_present": receipt is not None,
        "receipt_version": receipt.version if receipt else None,
        "current_link_present": current.exists(),
        "current_link_target_exists": current.exists() and current.resolve().exists(),
    }
    healthy = result["receipt_present"] and result["current_link_present"] and result["current_link_target_exists"]
    result["status"] = "ok" if healthy else "needs_attention"
    print(json.dumps(result, indent=2))
    return 0 if healthy else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="operator-voice-install-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install")
    _common_args(p_install)
    p_install.add_argument("--source", default="home")
    p_install.add_argument("--force", action="store_true")
    p_install.set_defaults(_fn=cmd_install)

    p_repair = sub.add_parser("repair")
    _common_args(p_repair)
    p_repair.set_defaults(_fn=cmd_repair)

    p_check = sub.add_parser("check")
    p_check.add_argument("--source-root", required=True)
    p_check.set_defaults(_fn=cmd_check)

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--runtime-root", required=True)
    p_doctor.add_argument("--receipt", required=True)
    p_doctor.set_defaults(_fn=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    return ns._fn(ns)


if __name__ == "__main__":
    sys.exit(main())
