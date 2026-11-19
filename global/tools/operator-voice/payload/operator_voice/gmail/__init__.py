"""OVT Gmail Adapter (M2) — agent-delegated, Sent-only Gmail voice capture.

This package materializes an agent-submitted envelope of the operator's own **Sent** messages into
immutable, timestamp-prefixed Markdown under the operator's fixed ``gmail_export_dir``, after
**server-side** author verification (:mod:`operator_voice.gmail.materialize`). It never calls Google
— no OAuth, no token, no SDK (§ ``docs/gmail-adapter.md``; ADR 0001/0002). The ``gmail_export``
adapter (:mod:`operator_voice.adapters.gmail_export`) then scans that tree like any other file-tree
source. Not under ``kernel/`` by construction — this is I/O + policy, not the pure kernel (build
plan §5.4).
"""
