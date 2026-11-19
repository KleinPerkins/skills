"""Pure aggregation for ``google.status`` — combines existing Drive + Gmail local snapshots.

No network, no Google credentials, no new reads beyond what ``drive.status`` and
``gmail.status`` already surface. Every field is derived from the two channel status dicts.
"""

from __future__ import annotations

from typing import Any


def _channel_stale_part(channel: str, status: dict[str, Any]) -> str:
    brief = str(status.get("brief", ""))
    if "not configured" in brief:
        return f"{channel} not configured"
    if status.get("stale"):
        return f"{channel} stale"
    if channel == "drive":
        fc = int(status.get("file_count") or 0)
        rc = int(status.get("record_count") or 0)
        return f"{channel} fresh ({fc} files, {rc} revisions)"
    mc = int(status.get("message_count") or 0)
    return f"{channel} fresh ({mc} messages)"


def build_google_brief(*, drive: dict[str, Any], gmail: dict[str, Any]) -> str:
    """One plain-language dashboard line for PM session-start hooks."""
    drive_brief = str(drive.get("brief", ""))
    gmail_brief = str(gmail.get("brief", ""))
    if "not configured" in drive_brief and "not configured" in gmail_brief:
        return "google-voice: not configured (no runtime paths)"

    stale = bool(drive.get("stale")) or bool(gmail.get("stale"))
    if stale:
        parts = (_channel_stale_part("drive", drive), _channel_stale_part("gmail", gmail))
        return f"google-voice: stale — ask agent to refresh Google voice ({'; '.join(parts)})"

    d_fc = int(drive.get("file_count") or 0)
    d_rc = int(drive.get("record_count") or 0)
    g_mc = int(gmail.get("message_count") or 0)
    return f"google-voice: fresh (drive: {d_fc} files/{d_rc} revisions, gmail: {g_mc} messages)"


def aggregate_google_status(
    *, drive: dict[str, Any], gmail: dict[str, Any], stale_after_hours: float,
) -> dict[str, Any]:
    """Merge two channel status snapshots into one combined result."""
    stale = bool(drive.get("stale")) or bool(gmail.get("stale"))
    return {
        "drive": drive,
        "gmail": gmail,
        "stale": stale,
        "stale_after_hours": stale_after_hours,
        "brief": build_google_brief(drive=drive, gmail=gmail),
    }


__all__ = ["aggregate_google_status", "build_google_brief"]
