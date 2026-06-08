"""Which ad platforms the operator can create campaigns on.

Single source of truth for the agent's `list_ad_platforms` tool AND the
Connections page — so platform availability is data-driven, not hardcoded in the
prompt or the UI. A platform is `connected` when its config is present; the
console can currently *create* only on LinkedIn (`can_create`).
"""

from __future__ import annotations

from typing import Any

from yieldagent.connectors.registry import manifests
from yieldagent.integrations.meta.config import MetaConfig


def _configured(load: Any) -> bool:
    try:
        load()
        return True
    except Exception:  # noqa: BLE001 — missing/invalid config means "not connected"
        return False


def ad_platform_status() -> list[dict[str, Any]]:
    """Platform availability, sourced from the connector registry.

    Registered connectors (currently LinkedIn) report via their manifest; Meta and
    Google are still "declared" (config-detected, not yet wrapped as connectors —
    C3/C6), so they are appended until their connectors land.
    """
    rows = [m.as_status() for m in manifests()]
    registered = {row["platform"] for row in rows}
    if "Meta" not in registered:
        meta = _configured(MetaConfig.from_env)
        rows.append({"platform": "Meta", "connected": meta, "can_create": False})
    if "Google" not in registered:
        rows.append({"platform": "Google", "connected": False, "can_create": False})
    return rows
