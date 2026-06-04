"""Ad-platform availability — same source the agent's list_ad_platforms uses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from yieldagent.agents.console.ad_platforms import ad_platform_status

router = APIRouter()


@router.get("/ad-platforms")
async def get_ad_platforms() -> list[dict[str, Any]]:
    return ad_platform_status()
