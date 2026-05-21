"""MCP server exposing the Meta Marketing API to YieldAgent agents.

Run with: `python -m yieldagent.integrations.meta.server`

Required env: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, META_PAGE_ID
Optional env: META_API_VERSION (default v22.0), YIELDAGENT_ALLOW_LIVE
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from yieldagent.domain import Campaign

from .client import MetaClient
from .config import MetaConfig
from .mapping import (
    campaign_objective,
    creative_payload,
    flight_to_meta_times,
    audience_to_targeting,
    to_minor_units,
)

mcp = FastMCP("yieldagent-meta")


def _client() -> MetaClient:
    return MetaClient(MetaConfig.from_env())


@mcp.tool()
async def get_ad_account() -> dict[str, Any]:
    """Return metadata for the configured Meta ad account."""
    async with _client() as client:
        return await client.get_ad_account()


@mcp.tool()
async def create_campaign(name: str, objective: str) -> dict[str, Any]:
    """Create a PAUSED campaign on the configured ad account.

    `objective` must be a Meta OUTCOME_* value (e.g. OUTCOME_SALES).
    """
    async with _client() as client:
        await client.assert_test_account()
        return await client.create_campaign(name=name, objective=objective)


@mcp.tool()
async def create_ad_set(
    campaign_id: str,
    name: str,
    lifetime_budget_minor: int,
    start_time: str,
    end_time: str,
    targeting: dict[str, Any],
) -> dict[str, Any]:
    """Create a PAUSED ad set under a campaign.

    `lifetime_budget_minor` is in the account's minor currency units (e.g. cents
    for USD). `start_time`/`end_time` are ISO-8601 strings. `targeting` is a Meta
    targeting spec — at minimum `geo_locations`.
    """
    async with _client() as client:
        await client.assert_test_account()
        return await client.create_ad_set(
            campaign_id=campaign_id,
            name=name,
            lifetime_budget_minor=lifetime_budget_minor,
            start_time=start_time,
            end_time=end_time,
            targeting=targeting,
        )


@mcp.tool()
async def create_ad(ad_set_id: str, name: str, creative: dict[str, Any]) -> dict[str, Any]:
    """Create a PAUSED ad under an ad set with the given creative spec."""
    async with _client() as client:
        await client.assert_test_account()
        return await client.create_ad(ad_set_id=ad_set_id, name=name, creative=creative)


@mcp.tool()
async def publish_draft_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create a paused draft Campaign on Meta in one call.

    Accepts a serialized `yieldagent.domain.Campaign` and chains
    create_campaign → create_ad_set (per LineItem) → create_ad (per Ad).
    Returns the IDs created so the agent can present them for approval.
    """
    parsed = Campaign.model_validate(campaign)
    config = MetaConfig.from_env()
    if not config.page_id:
        raise RuntimeError("META_PAGE_ID is required to publish ads")

    result: dict[str, Any] = {"line_items": [], "ads": []}
    async with MetaClient(config) as client:
        await client.assert_test_account()

        camp = await client.create_campaign(
            name=parsed.name, objective=campaign_objective(parsed)
        )
        result["campaign_id"] = camp["id"]

        line_item_ids: dict[str, str] = {}
        for li in parsed.line_items:
            start, end = flight_to_meta_times(li.flight)
            ad_set = await client.create_ad_set(
                campaign_id=camp["id"],
                name=li.name,
                lifetime_budget_minor=to_minor_units(li.budget.amount, li.budget.currency),
                start_time=start,
                end_time=end,
                targeting=audience_to_targeting(li.targeting.audience),
            )
            line_item_ids[li.name] = ad_set["id"]
            result["line_items"].append({"name": li.name, "id": ad_set["id"]})

        for ad in parsed.ads:
            ad_set_id = line_item_ids.get(ad.line_item_name)
            if not ad_set_id:
                raise ValueError(
                    f"Ad {ad.name!r} references unknown line_item_name {ad.line_item_name!r}"
                )
            created = await client.create_ad(
                ad_set_id=ad_set_id,
                name=ad.name,
                creative=creative_payload(ad.creative, page_id=config.page_id),
            )
            result["ads"].append({"name": ad.name, "id": created["id"]})

    return result


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
