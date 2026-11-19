"""OVT Drive Adapter (M1) — agent-delegated, owner-only Google Drive voice capture.

This package materializes an agent-submitted envelope of the operator's OWN, non-Shared-Drive
files into immutable, timestamp-prefixed Markdown under the operator's fixed ``drive_export_dir``,
after **server-side** owner + not-shared-drive verification (:mod:`operator_voice.drive.materialize`).
It never calls Google — no OAuth, no token, no SDK (§ ``docs/drive-adapter.md``; ADR 0002). The
``drive_export`` adapter (:mod:`operator_voice.adapters.drive_export`) then scans that tree like any
other file-tree source. Not under ``kernel/`` by construction — this is I/O + policy, not the pure
kernel (build plan §5.4; ADR 0002).
"""
