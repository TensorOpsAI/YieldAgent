"""Which ad platforms the operator can create campaigns on.

Single source of truth for the agent's `list_ad_platforms` tool AND the
Connections page — so platform availability is data-driven, not hardcoded in the
prompt or the UI. A platform is `connected` when its config is present; the
console can currently *create* only on LinkedIn (`can_create`).
"""

from __future__ import annotations

from typing import Any

from yieldagent.integrations.linkedin.config import LinkedInConfig
from yieldagent.integrations.meta.config import MetaConfig


def _configured(load: Any) -> bool:
    try:
        load()
        return True
    except Exception:  # noqa: BLE001 — missing/invalid config means "not connected"
        return False


def ad_platform_status() -> list[dict[str, Any]]:
    linkedin = _configured(LinkedInConfig.from_env)
    meta = _configured(MetaConfig.from_env)
    return [
        {"platform": "LinkedIn", "connected": linkedin, "can_create": linkedin},
        # Meta config may exist, but the console has no Meta creation flow yet.
        {"platform": "Meta", "connected": meta, "can_create": False},
        {"platform": "Google", "connected": False, "can_create": False},
    ]
