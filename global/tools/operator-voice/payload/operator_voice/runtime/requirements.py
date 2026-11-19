"""Single source of truth for OVT's runtime (non-dev) dependency pins.

``pyproject.toml``'s ``[project.dependencies]`` is authoritative for anyone building/testing this
checkout. Every *distributor* (this repo's own ``install.sh``, and the Global Capability Binding
shelf's own ``install.sh``) provisions a private venv from a portable payload that
does not carry ``pyproject.toml`` — only the allowlisted ``.py``/``.md``/``.json``/``.toml`` files
under ``src/operator_voice/`` itself (see ``runtime.payload``). Before this file existed, each
distributor hardcoded its own copy of the same version pins, and they silently drifted apart (the
GCB shelf's copy fell behind a ``cryptography`` floor bump made only in ``pyproject.toml``).

This file is the fix: a plain ``.json`` fact — already inside the payload allowlist, so it is
carried by every distributor automatically and is covered by the same content digest as the code
it ships with — that both this repo's own ``install.sh`` and any downstream generic ``kind: tool``
installer/reconciler read instead of hardcoding pins a second time. A dedicated test
(``tests/unit/test_runtime_requirements.py``) asserts this file and ``pyproject.toml`` never
diverge again.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIREMENTS_SCHEMA = "runtime-requirements/v1"
_REQUIREMENTS_FILENAME = "requirements.json"


def requirements_path(package_root: Path) -> Path:
    """``package_root`` is an ``operator_voice`` package directory (source checkout or an
    installed/vendored payload slot) — the same argument shape as ``runtime.payload`` functions."""
    return package_root / "runtime" / _REQUIREMENTS_FILENAME


def load_install_requires(package_root: Path) -> list[str]:
    """Reads the pinned runtime dependency specifiers for the ``operator_voice`` package rooted at
    ``package_root``. Raises if the file is absent/malformed — a distributor with no dependency
    manifest should fail loudly rather than silently install an unpinned/empty dependency set."""
    data = json.loads(requirements_path(package_root).read_text(encoding="utf-8"))
    if data.get("schema") != REQUIREMENTS_SCHEMA:
        raise ValueError(f"unexpected requirements schema: {data.get('schema')!r}")
    specs = data.get("install_requires")
    if not isinstance(specs, list) or not specs or not all(isinstance(s, str) and s for s in specs):
        raise ValueError("install_requires must be a non-empty list of non-empty strings")
    return list(specs)


__all__ = ["REQUIREMENTS_SCHEMA", "requirements_path", "load_install_requires"]
