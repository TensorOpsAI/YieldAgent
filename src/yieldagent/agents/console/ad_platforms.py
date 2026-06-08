"""Which ad platforms the operator can create campaigns on.

Single source of truth for the agent's `list_ad_platforms` tool AND the
Connections page — so platform availability is data-driven, not hardcoded in the
prompt or the UI. A platform is `connected` when its connector reports it; the
console can currently *create* only on LinkedIn (`can_create`).
"""

from __future__ import annotations

from typing import Any

from yieldagent.connectors.registry import manifests

# Platforms on the roadmap without a connector yet. They show on the Connections
# page as "coming soon" (not connected, not creatable) until one lands.
_PLANNED_PLATFORMS = ("Meta", "Google")


def ad_platform_status() -> list[dict[str, Any]]:
    """Platform availability, sourced from the connector registry.

    Registered connectors (currently LinkedIn) report via their manifest; planned
    platforms are appended as not-yet-available until their connectors land.
    """
    rows = [m.as_status() for m in manifests()]
    registered = {row["platform"] for row in rows}
    for platform in _PLANNED_PLATFORMS:
        if platform not in registered:
            rows.append({"platform": platform, "connected": False, "can_create": False})
    return rows
