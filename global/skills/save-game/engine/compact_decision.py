"""The Compact Decision contract (plan: "3. Compact Decision").

An ORDERED RULE SET over observable pressure signals and continuation count —
deliberately not a scored heuristic. The plan's threshold rules (below) are the
same for every client: pre-compaction hooks are explicitly "optional defense-
in-depth" that "cannot synthesize a trustworthy semantic durable delta," so
`adapters.py`'s per-client capability facts never change WHICH status this
module returns. What they do change (plan verification gates "exact manual
command" and "unsupported client capability"): the operator-facing manual
command and hook-capability class attached to the result, sourced from the one
capability registry rather than duplicated/guessed elsewhere. An unrecognized
`client_id` degrades to unresolved capability fields, never a crash — the
plan's "unknown stays unknown" posture applied to client identity too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import adapters

STATUSES = {"NEW_CHAT_RECOMMENDED", "SAVE_ONLY", "COMPACTION_REQUIRED", "RECOMMEND_COMPACTION"}
_PRESSURE_SOURCES = {"client_metric", "operator_report", "unknown"}
_OPERATOR_REQUESTS = {"compact", "no_compact", "unspecified"}


@dataclass
class CompactDecisionInputs:
    # Hard gates (plan: "Hard gates"). Flush/Index are asserted finalized by the
    # caller sequencing Compact Decision strictly after both succeed.
    flush_and_index_finalized: bool = True
    active_tool_or_action: bool = False
    privacy_failure: bool = False
    incomplete_transaction: bool = False
    authority_conflict: bool = False
    same_logical_task: bool = True
    task_completed_or_topic_change: bool = False
    # Observable inputs (plan: "Observable inputs").
    operator_request: str = "unspecified"  # compact | no_compact | unspecified
    pressure_source: str = "unknown"  # client_metric | operator_report | unknown
    pressure_percent: Optional[int] = None
    continuation_count: int = 0
    explicit_cross_session_continuation: bool = False
    # Client-capability lookup key (plan: "Cross-client discovery and
    # invocation" + "Client version and capability facts are recorded in
    # receipts"). Never changes a status outcome; see module docstring.
    client_id: Optional[str] = None


@dataclass
class CompactDecisionResult:
    status: str
    pressure_source: str
    pressure_percent: Optional[int]
    reason: str
    # Enrichment only — resolved from `adapters.py`, never persisted verbatim
    # into the closed `checkpoint.v1` schema (see `as_checkpoint_compaction`).
    # `None` means "no client_id supplied" or "unrecognized client_id"; the
    # two are distinguished by `client_capability_known`, never conflated.
    client_id: Optional[str] = None
    manual_compaction_command: Optional[str] = None
    pre_compaction_capability: Optional[str] = None
    client_capability_known: bool = False

    def as_checkpoint_compaction(self) -> dict:
        doc = {"status": self.status.lower(), "pressure_source": self.pressure_source}
        if self.pressure_percent is not None:
            doc["pressure_percent"] = self.pressure_percent
        return doc


def _hard_gates_pass(inputs: CompactDecisionInputs) -> bool:
    return (
        inputs.flush_and_index_finalized
        and not inputs.active_tool_or_action
        and not inputs.privacy_failure
        and not inputs.incomplete_transaction
        and not inputs.authority_conflict
        and inputs.same_logical_task
    )


def _resolve_capability(client_id: Optional[str]) -> Optional[adapters.ClientCapability]:
    """`None` for "no client_id given" AND for "unrecognized client_id" alike
    — an unsupported client capability must degrade, never raise, so a caller
    that cannot yet identify its own client still gets a safe SAVE_ONLY-class
    result rather than a crash (plan verification gate "unsupported client
    capability")."""
    if not client_id:
        return None
    try:
        return adapters.get_client(client_id)
    except KeyError:
        return None


def evaluate(inputs: CompactDecisionInputs) -> CompactDecisionResult:
    pressure_source = inputs.pressure_source if inputs.pressure_source in _PRESSURE_SOURCES else "unknown"
    operator_request = inputs.operator_request if inputs.operator_request in _OPERATOR_REQUESTS else "unspecified"
    pressure_percent = inputs.pressure_percent if pressure_source != "unknown" else None

    capability = _resolve_capability(inputs.client_id)
    enrichment = dict(
        client_id=inputs.client_id,
        manual_compaction_command=capability.manual_compaction_command if capability else None,
        pre_compaction_capability=capability.pre_compaction_capability if capability else None,
        client_capability_known=capability is not None,
    )

    def result(status: str, reason: str) -> CompactDecisionResult:
        return CompactDecisionResult(status, pressure_source, pressure_percent, reason, **enrichment)

    # Rule 1: completed task or topic change short-circuits everything else.
    if inputs.task_completed_or_topic_change:
        return result("NEW_CHAT_RECOMMENDED", "task completed or topic changed")

    # Rule 2: explicit no-compact always wins next.
    if operator_request == "no_compact":
        return result("SAVE_ONLY", "operator explicitly requested no compaction")

    if not _hard_gates_pass(inputs):
        # A failed hard gate (active tool/action, privacy failure, incomplete
        # transaction, authority conflict, or a task boundary break) can never
        # safely force compaction: fail to the safest status.
        return result("SAVE_ONLY", "a hard gate did not pass")

    # Rule 3: explicit compact, hard gates already confirmed above.
    if operator_request == "compact":
        return result("COMPACTION_REQUIRED", "operator explicitly requested compaction")

    # Rules 4-5 require a VERIFIED (non-unknown) pressure percentage — never invent one.
    if pressure_source != "unknown" and pressure_percent is not None:
        if pressure_percent >= 80 and inputs.continuation_count >= 2:
            return result("COMPACTION_REQUIRED", "verified pressure >= 80% with >= 2 remaining actions")
        if 60 <= pressure_percent <= 79 and (inputs.continuation_count >= 4 or inputs.explicit_cross_session_continuation):
            return result("RECOMMEND_COMPACTION", "verified pressure 60-79% with a long continuation")

    # Rule 6: unknown pressure, or pressure/continuation below every threshold above.
    return result("SAVE_ONLY", "unknown pressure or continuation below thresholds")
