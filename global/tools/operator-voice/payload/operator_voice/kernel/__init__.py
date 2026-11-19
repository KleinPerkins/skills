"""Deterministic kernel — build plan v3 §4: "owns authorship policy, normalization, quarantine,
feature extraction, confidence math, synthesis, retrieval, validation rules, lifecycle
consequences, and schema/version compatibility. It has no network or model imports."

Hard invariant (quality gate applies from M1): no module under ``operator_voice.kernel`` may
import ``operator_voice.application`` (network/model gateway lives there), any HTTP/socket
library, or the ``mcp``/``cryptography`` packages. ``tests/unit/test_kernel_purity.py`` enforces
this by static import-graph inspection.
"""
