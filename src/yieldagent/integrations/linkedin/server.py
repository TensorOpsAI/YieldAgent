"""MCP server exposing the LinkedIn Marketing API to YieldAgent agents.

Run with: `python -m yieldagent.integrations.linkedin.server`

Required env: LINKEDIN_ACCESS_TOKEN, LINKEDIN_AD_ACCOUNT_ID
Optional env: LINKEDIN_API_VERSION (default 202605),
              LINKEDIN_ALLOWED_AD_ACCOUNTS (comma-separated allowlist),
              YIELDAGENT_ALLOW_LIVE (set to 1 to bypass the allowlist)
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from yieldagent.domain import Campaign
from yieldagent.env import load_dotenv

from .client import LinkedInClient
from .config import LinkedInConfig
from .mapping import (
    DEFAULT_CAMPAIGN_TYPE,
    audience_to_targeting,
    campaign_objective,
    campaign_run_schedule,
    creative_content_reference,
    flight_to_run_schedule,
    line_item_locale,
    money_to_linkedin_amount,
    post_article_content,
    post_commentary,
)

mcp = FastMCP("yieldagent-linkedin")


def _client() -> LinkedInClient:
    return LinkedInClient(LinkedInConfig.from_env())


def _strip_unresolved(targeting: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split the mapping's targeting payload into wire payload + unresolved B2B notes."""
    wire = {k: v for k, v in targeting.items() if not k.startswith("_")}
    unresolved = targeting.get("_unresolved_b2b", {})
    return wire, unresolved


@mcp.tool()
async def get_ad_account() -> dict[str, Any]:
    """Return metadata for the configured LinkedIn ad account."""
    async with _client() as client:
        return await client.get_ad_account()


@mcp.tool()
async def create_campaign_group(
    name: str, total_budget_amount: str, currency: str
) -> dict[str, Any]:
    """Create a DRAFT Campaign Group on the configured account."""
    async with _client() as client:
        client.assert_account_allowed()
        return await client.create_campaign_group(
            name=name,
            total_budget={"amount": total_budget_amount, "currencyCode": currency.upper()},
        )


@mcp.tool()
async def create_campaign(
    campaign_group_urn: str,
    name: str,
    objective_type: str,
    total_budget_amount: str,
    currency: str,
    start_epoch_ms: int,
    end_epoch_ms: int,
    targeting_criteria: dict[str, Any],
    locale_country: str = "US",
    locale_language: str = "en",
    campaign_type: str = DEFAULT_CAMPAIGN_TYPE,
) -> dict[str, Any]:
    """Create a DRAFT Campaign (= YieldAgent LineItem) under a Campaign Group."""
    async with _client() as client:
        client.assert_account_allowed()
        return await client.create_campaign(
            campaign_group_urn=campaign_group_urn,
            name=name,
            objective_type=objective_type,
            campaign_type=campaign_type,
            total_budget={"amount": total_budget_amount, "currencyCode": currency.upper()},
            run_schedule={"start": start_epoch_ms, "end": end_epoch_ms},
            targeting_criteria=targeting_criteria,
            locale={"country": locale_country.upper(), "language": locale_language.lower()},
        )


@mcp.tool()
async def create_creative(campaign_urn: str, content: dict[str, Any]) -> dict[str, Any]:
    """Create a DRAFT Creative (= YieldAgent Ad) under a Campaign."""
    async with _client() as client:
        client.assert_account_allowed()
        return await client.create_creative(campaign_urn=campaign_urn, content=content)


@mcp.tool()
async def publish_draft_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create a paused draft Campaign on LinkedIn in one call.

    Accepts a serialized `yieldagent.domain.Campaign` and chains
    create_campaign_group → create_campaign (per LineItem) → create_creative
    (per Ad). Everything is created as `DRAFT` — nothing can spend without a
    manual activation step in LinkedIn Campaign Manager.

    Returns the URNs created so the agent can present them for approval, plus a
    `notes` block flagging any B2B targeting facets that were not pushed to the
    API (URN resolution for industries/seniorities/etc. is a follow-up).
    """
    parsed = Campaign.model_validate(campaign)
    config = LinkedInConfig.from_env()

    result: dict[str, Any] = {"line_items": [], "ads": [], "notes": {}}
    async with LinkedInClient(config) as client:
        client.assert_account_allowed()

        # Choose a campaign-group total budget: explicit lifetime_budget if set,
        # otherwise the sum of line-item budgets in the first line item's currency.
        if parsed.lifetime_budget is not None:
            group_amount = parsed.lifetime_budget.amount
            group_currency = parsed.lifetime_budget.currency
        elif parsed.line_items:
            group_currency = parsed.line_items[0].budget.currency
            group_amount = sum(
                li.budget.amount for li in parsed.line_items if li.budget.currency == group_currency
            )
        else:
            raise ValueError("Campaign has no line_items and no lifetime_budget")

        group = await client.create_campaign_group(
            name=parsed.name,
            total_budget=money_to_linkedin_amount(group_amount, group_currency),
            # LinkedIn now requires runSchedule on the group; span all line items.
            run_schedule=campaign_run_schedule([li.flight for li in parsed.line_items]),
        )
        group_urn = f"urn:li:sponsoredCampaignGroup:{group['id']}"
        result["campaign_id"] = group["id"]
        result["campaign_group_urn"] = group_urn

        objective_type = campaign_objective(parsed)

        # Creatives reference a real Post. Ads carrying `existing_post_urn` reuse a
        # hand-published post; the rest mint a new Direct Sponsored Content post,
        # which must be authored by a Company Page. Only resolve/require the org URN
        # when at least one ad needs a fresh post.
        org_urn = config.organization_urn
        if any(not ad.creative.existing_post_urn for ad in parsed.ads):
            if org_urn is None:
                account = await client.get_ad_account()
                org_urn = account.get("reference")
            if not org_urn or not str(org_urn).startswith("urn:li:organization:"):
                raise ValueError(
                    "No organization (Company Page) is associated with this ad account, "
                    "so Direct Sponsored Content posts cannot be authored for creatives. "
                    "Set LINKEDIN_ORGANIZATION_URN, or use an ad account linked to a page, "
                    "or set `existing_post_urn` on every ad to reuse hand-published posts."
                )

        line_item_urns: dict[str, str] = {}
        unresolved_by_li: dict[str, dict[str, Any]] = {}
        for li in parsed.line_items:
            targeting, unresolved = _strip_unresolved(
                audience_to_targeting(li.targeting.audience)
            )
            if unresolved:
                unresolved_by_li[li.name] = unresolved
            run_schedule = flight_to_run_schedule(li.flight)
            created = await client.create_campaign(
                campaign_group_urn=group_urn,
                name=li.name,
                objective_type=objective_type,
                campaign_type=DEFAULT_CAMPAIGN_TYPE,
                total_budget=money_to_linkedin_amount(li.budget.amount, li.budget.currency),
                run_schedule=run_schedule,
                targeting_criteria=targeting,
                locale=line_item_locale(li.targeting.audience),
            )
            urn = f"urn:li:sponsoredCampaign:{created['id']}"
            line_item_urns[li.name] = urn
            result["line_items"].append({"name": li.name, "id": created["id"], "urn": urn})

        for ad in parsed.ads:
            campaign_urn = line_item_urns.get(ad.line_item_name)
            if not campaign_urn:
                raise ValueError(
                    f"Ad {ad.name!r} references unknown line_item_name {ad.line_item_name!r}"
                )
            # Either reference a hand-published post, or mint a dark post (DSC).
            if ad.creative.existing_post_urn:
                post_urn = ad.creative.existing_post_urn
            else:
                post = await client.create_post(
                    author_urn=org_urn,
                    commentary=post_commentary(ad.creative),
                    article=post_article_content(ad.creative),
                    dsc_ad_account_urn=config.account_urn,
                )
                post_urn = post.get("id")
            created = await client.create_creative(
                campaign_urn=campaign_urn,
                content=creative_content_reference(post_urn),
            )
            result["ads"].append(
                {
                    "name": ad.name,
                    "id": created.get("id"),
                    "campaign_urn": campaign_urn,
                    "post_urn": post_urn,
                }
            )

        if unresolved_by_li:
            result["notes"]["unresolved_b2b_targeting"] = unresolved_by_li
            result["notes"]["unresolved_b2b_hint"] = (
                "These B2B facets are present on the Brief audience but were not pushed to "
                "LinkedIn — they require URN resolution via the typeahead endpoint, which is "
                "not wired in this slice. Add them manually in Campaign Manager before activation."
            )

    return result


def main() -> None:
    load_dotenv()
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
