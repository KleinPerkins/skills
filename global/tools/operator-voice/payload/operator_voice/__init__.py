"""Operator Voice Toolkit (OVT) — durable voice memory and application layer.

See ``docs/architecture.md`` for the module map and ``AGENTS.md`` for governance.
This package has one deterministic kernel (no network/model imports — see
``operator_voice.kernel``) and one mutation boundary (``operator_voice.application.service``).
"""

__version__ = "0.1.15"
