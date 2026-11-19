"""One JSON rendering rule for CLI and MCP results (ADR 0005)."""
from __future__ import annotations

import json
from typing import Any

from operator_voice.kernel.retrieval import EMITTED_JSON_SEPARATORS

COMPACT_OPERATIONS = frozenset({"context.get"})


def render_json(op_name: str, result: Any) -> str:
    if op_name in COMPACT_OPERATIONS:
        return json.dumps(result, separators=EMITTED_JSON_SEPARATORS, default=str)
    return json.dumps(result, indent=2, default=str)
