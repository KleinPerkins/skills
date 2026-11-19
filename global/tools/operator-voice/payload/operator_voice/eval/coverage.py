"""Registry-derived evidence collectors for the two eval-manifest measures that are computed
directly from the operation registry (not from a test-suite pass rate):
``deterministic_help_coverage_rate`` and the registry-parity component of
``interface_registry_parity_rate``.

Pure, deterministic functions of :data:`operator_voice.domain.operations.OPERATIONS`, the generated
operation cards, and the CLI/MCP surface builders — no filesystem, no network, no model. This
module is imported by BOTH ``tests/eval/test_help_coverage.py`` and
``scripts/collect_m5_evidence.py`` so the coverage number the M5 evidence pack reports is the exact
number the test suite locks (no drift between "what we assert" and "what we score").
"""

from __future__ import annotations

import argparse

from operator_voice.docs.generate import render_operation_card
from operator_voice.domain.help import challenge_description, error_taxonomy, worked_examples
from operator_voice.domain.operations import (
    OPERATIONS,
    Operation,
    Posture,
    mcp_operations,
)
from operator_voice.eval.metrics import rate


def op_help_complete(op: Operation) -> bool:
    """True iff ``op``'s generated card satisfies every clause of the frozen
    ``deterministic_help_coverage_rate`` measure: a generated card, a worked example, a non-empty
    error taxonomy, and — where the operation is consequential — a plain-language challenge/consent
    description."""
    card = render_operation_card(op)
    has_card = card.startswith("<!-- GENERATED") and f"# `{op.name}`" in card
    has_example = ("## Examples" in card) and ("```" in card) and bool(worked_examples(op))
    has_errors = ("## Errors" in card) and bool(error_taxonomy(op))
    if op.posture == Posture.CONSEQUENTIAL:
        has_challenge = ("## Confirmation" in card) and (challenge_description(op) is not None)
    else:
        has_challenge = True  # a challenge description is only required for consequential ops
    return has_card and has_example and has_errors and has_challenge


def deterministic_help_coverage_rate() -> float:
    """[0, 100] fraction of OPERATIONS whose generated help is complete per :func:`op_help_complete`."""
    complete = sum(1 for op in OPERATIONS if op_help_complete(op))
    return rate(complete, len(OPERATIONS))


def _cli_subcommand_names() -> set[str]:
    from operator_voice.interfaces.cli import build_parser

    parser = build_parser()
    for action in parser._actions:  # noqa: SLF001 — argparse's only public path to subparser names
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return set(action.choices.keys())
    return set()


def op_interface_parity(op: Operation, cli_names: set[str], mcp_names: set[str]) -> bool:
    """True iff ``op`` is present on every surface it must be, and absent from those it must not be:
    a CLI subcommand exists; an MCP tool exists **iff** the operation is MCP-exposed (lifecycle
    operations are deliberately CLI-only); and a generated operation card exists. This is the
    structural, per-operation half of ``interface_registry_parity_rate`` (the colloquial-intent and
    direct-service-policy-enforcement halves are proven by tests/integration/test_interfaces.py)."""
    has_cli = op.cli_name in cli_names
    correct_mcp = (op.mcp_name in mcp_names) == op.mcp_exposed
    card = render_operation_card(op)
    has_card = f"# `{op.name}`" in card
    return has_cli and correct_mcp and has_card


def interface_registry_parity_rate() -> float:
    """[0, 100] structural surface-parity fraction across OPERATIONS (CLI + correct MCP exposure +
    generated card)."""
    cli_names = _cli_subcommand_names()
    mcp_names = {op.mcp_name for op in mcp_operations(mutations_enabled=True)}
    ok = sum(1 for op in OPERATIONS if op_interface_parity(op, cli_names, mcp_names))
    return rate(ok, len(OPERATIONS))


__all__ = [
    "op_help_complete",
    "deterministic_help_coverage_rate",
    "op_interface_parity",
    "interface_registry_parity_rate",
]
