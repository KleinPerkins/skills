"""Adapter dispatch — maps :class:`~operator_voice.domain.models.AdapterType` to its ``scan``
entrypoint. The only lookup table an application service needs; adding an adapter type means
adding one line here plus the module itself, never touching the service's ingest logic."""

from __future__ import annotations

from typing import Callable

from operator_voice.adapters import (
    drive_export,
    gmail_export,
    slack_export,
)
from operator_voice.adapters.base import AdapterScanResult
from operator_voice.domain.models import AdapterType, SourceRegistration

# Every adapter's ``scan`` accepts an optional bounded-continuation ``limit`` (§13 M3 worklist 3);
# the third positional is that limit. Kept as ``...`` in the alias so both 2-arg (unbounded) and
# 3-arg (bounded) call sites type-check.
ScanFn = Callable[..., AdapterScanResult]

_REGISTRY: dict[AdapterType, ScanFn] = {
    AdapterType.SLACK_EXPORT: slack_export.scan,
    AdapterType.DRIVE_EXPORT: drive_export.scan,
    AdapterType.GMAIL_EXPORT: gmail_export.scan,
}


def get_scanner(adapter_type: AdapterType) -> ScanFn:
    try:
        return _REGISTRY[adapter_type]
    except KeyError:
        raise KeyError(f"no adapter registered for {adapter_type!r}") from None


__all__ = ["get_scanner"]
