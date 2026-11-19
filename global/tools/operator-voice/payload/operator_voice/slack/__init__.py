"""Slack materialization support (OVT Slack Adapter, v1). Pure file-format logic shared by the
``slack.import`` service handler (writes) and the ``slack_export`` adapter (reads) — no network,
no persistence, no Slack SDK. See :mod:`operator_voice.slack.materialize`.
"""
