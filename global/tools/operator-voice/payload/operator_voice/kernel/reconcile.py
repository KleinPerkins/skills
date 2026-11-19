"""Deterministic typed reconciliation of multi-machine profile generations — build plan v4 §13 M4
worklist 5 ("Add deterministic typed reconciliation for disjoint multi-machine profile
generations; conflicting corrections or identity changes require review") and decision D18 ("one
active remote writer in M1 ... typed disjoint reconciliation arrives in M4").

PURE and deterministic (no I/O, no crypto, no Git). The application service is responsible for
decrypting the remote profile pack into :class:`FactView`s, calling :func:`reconcile_facts`,
persisting the adopted merges, and turning conflicts into operator review items. This module never
force-merges an operator-authoritative disagreement and never touches shared refs — it only decides
what a machine should adopt locally and what must stop for a human.

Reconciliation rules (per (facet, scope) key):

* **remote-only** key → *adopt* (disjoint typed change; safe to merge).
* both present, byte-equal value AND same state → *unchanged*.
* both present but differing:
    * an **identity** facet (``identity:`` namespace) → **conflict** (never auto-resolved).
    * either side is **operator-authoritative** (CORRECTED/CONFIRMED) → **conflict**
      ("conflicting correction"): operator feedback is P0 and is never silently overwritten by a
      replica, in either direction.
    * otherwise (both inferred) → a deterministic winner is chosen by
      (state precedence desc, confidence desc, value-string asc). If the winner is the remote value
      it is *adopted*; if the local value already wins it is *unchanged*. Fully deterministic:
      the same two inputs always produce the same decision on any machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from operator_voice.domain.models import FACT_STATE_PRECEDENCE, FactState

RECONCILE_VERSION = "reconcile/v1"

# Corrections/confirmations are the operator's own words (P0). A replica must never overwrite them
# without a human decision, so any disagreement touching one is a conflict, not an auto-merge.
OPERATOR_AUTHORITATIVE_STATES = frozenset({FactState.CORRECTED, FactState.CONFIRMED})
# Identity facets (who this subject IS / how sources map to them) are never auto-reconciled.
IDENTITY_FACET_PREFIX = "identity:"


@dataclass(frozen=True, slots=True)
class FactView:
    """The minimal, crypto-free projection of a fact used for reconciliation. The service builds
    these from local facts and from decrypted remote profile-pack objects."""

    facet: str
    scope_key: str
    value: Any
    state: FactState
    confidence: float = 0.0
    fact_id: Optional[str] = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.facet, self.scope_key)


@dataclass(frozen=True, slots=True)
class Conflict:
    facet: str
    scope_key: str
    reason: str  # "identity_change" | "conflicting_correction"
    local_state: str
    remote_state: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "facet": self.facet,
            "scope_key": self.scope_key,
            "reason": self.reason,
            "local_state": self.local_state,
            "remote_state": self.remote_state,
        }


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    adopt: list[FactView] = field(default_factory=list)  # remote facts to merge into local
    conflicts: list[Conflict] = field(default_factory=list)
    unchanged: int = 0

    @property
    def merged_count(self) -> int:
        return len(self.adopt)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)


def _value_string(value: Any) -> str:
    """Deterministic canonical string for value equality + tie-breaking (order-independent)."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _precedence(state: FactState) -> int:
    return FACT_STATE_PRECEDENCE.get(state, 0)


def _remote_wins(local: FactView, remote: FactView) -> bool:
    """Deterministic winner for two INFERRED (non-authoritative) facts that disagree.
    Order: higher state precedence, then higher confidence, then smaller value string. Returns
    True iff the remote value should be adopted."""
    lp, rp = _precedence(local.state), _precedence(remote.state)
    if rp != lp:
        return rp > lp
    if remote.confidence != local.confidence:
        return remote.confidence > local.confidence
    # Fully deterministic final tie-break: lexicographically smaller value string "wins"; adopt
    # remote only when it is the strictly smaller string (equal strings are handled earlier).
    return _value_string(remote.value) < _value_string(local.value)


def reconcile_facts(local: list[FactView], remote: list[FactView]) -> ReconcileResult:
    """Compute the deterministic reconciliation of a remote replica's facts against local facts.
    Never mutates its inputs. Local-only facts are intentionally left alone (they publish on the
    next exact-parent push); this function only decides what to ADOPT from the remote and what to
    stop for REVIEW."""
    local_by_key: dict[tuple[str, str], FactView] = {}
    for fv in local:
        # If the local set somehow has duplicates for a key, keep the higher-precedence one so the
        # decision is stable regardless of input ordering.
        cur = local_by_key.get(fv.key)
        if cur is None or _precedence(fv.state) > _precedence(cur.state):
            local_by_key[fv.key] = fv
    remote_by_key: dict[tuple[str, str], FactView] = {}
    for fv in remote:
        cur = remote_by_key.get(fv.key)
        if cur is None or _precedence(fv.state) > _precedence(cur.state):
            remote_by_key[fv.key] = fv

    adopt: list[FactView] = []
    conflicts: list[Conflict] = []
    unchanged = 0

    for key in sorted(remote_by_key.keys()):
        remote_fv = remote_by_key[key]
        local_fv = local_by_key.get(key)
        if local_fv is None:
            adopt.append(remote_fv)  # disjoint remote-only change
            continue
        same_value = _value_string(local_fv.value) == _value_string(remote_fv.value)
        if same_value and local_fv.state == remote_fv.state:
            unchanged += 1
            continue
        facet = key[0]
        if facet.startswith(IDENTITY_FACET_PREFIX):
            conflicts.append(Conflict(facet, key[1], "identity_change", local_fv.state.value, remote_fv.state.value))
            continue
        if local_fv.state in OPERATOR_AUTHORITATIVE_STATES or remote_fv.state in OPERATOR_AUTHORITATIVE_STATES:
            conflicts.append(Conflict(facet, key[1], "conflicting_correction", local_fv.state.value, remote_fv.state.value))
            continue
        if _remote_wins(local_fv, remote_fv):
            adopt.append(remote_fv)
        else:
            unchanged += 1

    return ReconcileResult(adopt=adopt, conflicts=conflicts, unchanged=unchanged)


__all__ = [
    "RECONCILE_VERSION",
    "OPERATOR_AUTHORITATIVE_STATES",
    "IDENTITY_FACET_PREFIX",
    "FactView",
    "Conflict",
    "ReconcileResult",
    "reconcile_facts",
]
