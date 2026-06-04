"""Dashboard data — the campaigns created via the console."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from yieldagent.store import campaigns

router = APIRouter()


@router.get("/campaigns")
async def list_campaigns() -> list[dict[str, Any]]:
    return campaigns.list_all()


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str) -> dict[str, Any]:
    record = campaigns.get(campaign_id)
    if record is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return record


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str) -> dict[str, bool]:
    """Forget a campaign locally (dashboard view). Does not touch LinkedIn."""
    if not campaigns.delete(campaign_id):
        raise HTTPException(status_code=404, detail="campaign not found")
    return {"deleted": True}


@router.get("/summary")
async def summary() -> dict[str, Any]:
    counts = campaigns.summary()
    return {"campaigns": counts["total"], "drafts": counts["drafts"]}
