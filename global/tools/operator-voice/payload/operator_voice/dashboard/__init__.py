"""Render-only OVT status dashboard (build plan v4 §13 M4 worklist "render-only Cursor dashboard").

The dashboard is a single ``.canvas.tsx`` React app that DISPLAYS OVT state and cannot change it.
Its only data comes from a redacted, content-free snapshot (``service.dashboard_data`` /
``ovt://status/dashboard``) embedded inline at generation time — the canvas makes no network call,
imports only from ``cursor/canvas``, and dispatches no host/OVT action, so it is structurally
render-only. The builder lives in :mod:`operator_voice.dashboard.generate`.
"""
