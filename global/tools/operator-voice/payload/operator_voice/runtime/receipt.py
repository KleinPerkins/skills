"""The install receipt — build plan v4 §13 M1 acceptance: "Home-first and vendor-fixture-first
installs converge to the same receipt; same digest is a no-op; same-version/different-digest
refuses for distributor payloads but upgrades from a home checkout or with ``--force``;
interruption preserves the prior runtime; repair changes runtime only; every state renders one
plain next step."

The receipt is the ONLY durable record of "what runtime is installed" — a single small JSON file
at ``RuntimePaths.receipt_path`` (state dir, never the data/profile dir). It never contains a
path, key, or any operator content; ``version``/``digest`` are the release identity, ``source`` is
a coarse distributor label (``"home"`` | ``"vendor-fixture"`` | any caller-supplied string), never
a real filesystem path.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

RECEIPT_SCHEMA = "install-receipt/v1"


@dataclass(frozen=True)
class InstallReceipt:
    schema: str
    version: str
    digest: str
    installed_at: float
    source: str

    def as_dict(self) -> dict:
        return {
            "schema": self.schema, "version": self.version, "digest": self.digest,
            "installed_at": self.installed_at, "source": self.source,
        }


def read_receipt(receipt_path: Path) -> Optional[InstallReceipt]:
    if not receipt_path.exists():
        return None
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    try:
        return InstallReceipt(
            schema=data["schema"], version=data["version"], digest=data["digest"],
            installed_at=data["installed_at"], source=data["source"],
        )
    except KeyError:
        return None


def write_receipt(receipt_path: Path, version: str, digest: str, source: str) -> InstallReceipt:
    receipt = InstallReceipt(schema=RECEIPT_SCHEMA, version=version, digest=digest, installed_at=time.time(), source=source)
    receipt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(dir=str(receipt_path.parent), prefix=".receipt.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(receipt.as_dict(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, receipt_path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return receipt


__all__ = ["InstallReceipt", "RECEIPT_SCHEMA", "read_receipt", "write_receipt"]
