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
    campaign_objective,
    campaign_run_schedule,
    creative_content_reference,
    flight_to_run_schedule,
    line_item_locale,
    money_to_linkedin_amount,
    post_article_content,
    post_commentary,
)
from .targeting import TargetingResolver

mcp = FastMCP("yieldagent-linkedin")


def _client() -> LinkedInClient:
    return LinkedInClient(LinkedInConfig.from_env())


class _Created:
    """Tracks resources created during a publish so they can be rolled back.

    The publish flow is not transactional: a failure midway (e.g. a creative
    that LinkedIn refuses to sponsor) otherwise leaves the already-created
    campaign group / campaigns / posts as orphaned DRAFTs on the account.
    """

    def __init__(self) -> None:
        self.creatives: list[str] = []
        self.posts: list[str] = []
        self.campaigns: list[str] = []
        self.groups: list[str] = []

    def is_empty(self) -> bool:
        return not (self.creatives or self.posts or self.campaigns or self.groups)


async def _rollback(client: LinkedInClient, created: _Created) -> list[str]:
    """Best-effort delete of everything created, in reverse dependency order.

    Never raises: each delete is attempted independently, and any failure is
    collected into the returned warning list so the caller can surface what
    could not be cleaned up (and therefore needs manual attention).
    """
    warnings: list[str] = []

    async def _try(label: str, coro):
        try:
            await coro
        except Exception as exc:  # noqa: BLE001 — cleanup must not mask the real error
            warnings.append(f"{label}: {exc}")

    for creative_urn in reversed(created.creatives):
        await _try(f"creative {creative_urn}", client.delete_creative(creative_urn))
    for campaign_id in reversed(created.campaigns):
        await _try(f"campaign {campaign_id}", client.delete_campaign(campaign_id))
    for group_id in reversed(created.groups):
        await _try(f"campaign_group {group_id}", client.delete_campaign_group(group_id))
    for post_urn in reversed(created.posts):
        await _try(f"post {post_urn}", client.delete_post(post_urn))
    return warnings


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


def _group_budget(parsed: Campaign) -> tuple[Any, str]:
    """Choose the campaign-group total budget.

    An explicit `lifetime_budget` wins; otherwise sum the line-item budgets in
    the first line item's currency.
    """
    if parsed.lifetime_budget is not None:
        return parsed.lifetime_budget.amount, parsed.lifetime_budget.currency
    if parsed.line_items:
        currency = parsed.line_items[0].budget.currency
        amount = sum(
            li.budget.amount for li in parsed.line_items if li.budget.currency == currency
        )
        return amount, currency
    raise ValueError("Campaign has no line_items and no lifetime_budget")


async def _resolve_org_urn(
    client: LinkedInClient, config: LinkedInConfig, parsed: Campaign
) -> str | None:
    """Resolve the Company Page URN that authors Direct Sponsored Content posts.

    Only needed when at least one ad mints a fresh post; ads reusing a
    hand-published post via `existing_post_urn` require no org. Raises if a post
    must be minted but no usable organization URN is available.
    """
    if all(ad.creative.existing_post_urn for ad in parsed.ads):
        return config.organization_urn
    org_urn = config.organization_urn
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
    return org_urn


async def _create_group(
    client: LinkedInClient, parsed: Campaign, created: _Created, amount: Any, currency: str
) -> tuple[str, str]:
    """Create the DRAFT Campaign Group, track it, and return (id, urn)."""
    group = await client.create_campaign_group(
        name=parsed.name,
        total_budget=money_to_linkedin_amount(amount, currency),
        # LinkedIn now requires runSchedule on the group; span all line items.
        run_schedule=campaign_run_schedule([li.flight for li in parsed.line_items]),
    )
    created.groups.append(group["id"])
    return group["id"], f"urn:li:sponsoredCampaignGroup:{group['id']}"


async def _create_line_items(
    client: LinkedInClient,
    parsed: Campaign,
    created: _Created,
    group_urn: str,
    objective_type: str,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Create one DRAFT Campaign per LineItem, resolving its B2B targeting.

    Returns the per-line-item campaign URNs, any unresolved targeting facets
    keyed by line-item name, and the result rows for the publish response.
    """
    resolver = TargetingResolver(client)
    line_item_urns: dict[str, str] = {}
    unresolved_by_li: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for li in parsed.line_items:
        resolved = await resolver.resolve(li.targeting.audience)
        if resolved.unresolved:
            unresolved_by_li[li.name] = resolved.unresolved
        created_li = await client.create_campaign(
            campaign_group_urn=group_urn,
            name=li.name,
            objective_type=objective_type,
            campaign_type=DEFAULT_CAMPAIGN_TYPE,
            total_budget=money_to_linkedin_amount(li.budget.amount, li.budget.currency),
            run_schedule=flight_to_run_schedule(li.flight),
            targeting_criteria=resolved.criteria,
            locale=line_item_locale(li.targeting.audience),
        )
        created.campaigns.append(created_li["id"])
        urn = f"urn:li:sponsoredCampaign:{created_li['id']}"
        line_item_urns[li.name] = urn
        results.append({"name": li.name, "id": created_li["id"], "urn": urn})
    return line_item_urns, unresolved_by_li, results


async def _create_ads(
    client: LinkedInClient,
    config: LinkedInConfig,
    parsed: Campaign,
    created: _Created,
    line_item_urns: dict[str, str],
    org_urn: str | None,
) -> list[dict[str, Any]]:
    """Create a DRAFT Creative per Ad, minting a dark post where needed.

    Each ad either references a hand-published post (`existing_post_urn`) or
    mints a new Direct Sponsored Content post authored by `org_urn`.
    """
    results: list[dict[str, Any]] = []
    for ad in parsed.ads:
        campaign_urn = line_item_urns.get(ad.line_item_name)
        if not campaign_urn:
            raise ValueError(
                f"Ad {ad.name!r} references unknown line_item_name {ad.line_item_name!r}"
            )
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
            if post_urn:
                created.posts.append(post_urn)
        created_ad = await client.create_creative(
            campaign_urn=campaign_urn,
            content=creative_content_reference(post_urn),
        )
        if created_ad.get("id"):
            created.creatives.append(created_ad["id"])
        results.append(
            {
                "name": ad.name,
                "id": created_ad.get("id"),
                "campaign_urn": campaign_urn,
                "post_urn": post_urn,
            }
        )
    return results


async def _rollback_and_raise(
    client: LinkedInClient, created: _Created, exc: Exception
) -> None:
    """Tear down partial work and re-raise with a human-readable summary."""
    rolled_back = not created.is_empty()
    cleanup_warnings = await _rollback(client, created)
    summary = {
        "campaign_groups": list(created.groups),
        "campaigns": list(created.campaigns),
        "creatives": list(created.creatives),
        "posts": list(created.posts),
    }
    detail = f"publish failed: {exc}. " + (
        f"Rolled back created resources {summary}."
        if rolled_back
        else "No resources were created."
    )
    if cleanup_warnings:
        detail += (
            " WARNING: some resources could not be deleted and need manual "
            f"cleanup in Campaign Manager: {cleanup_warnings}"
        )
    raise RuntimeError(detail) from exc


@mcp.tool()
async def publish_draft_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create a paused draft Campaign on LinkedIn in one call.

    Accepts a serialized `yieldagent.domain.Campaign` and chains
    create_campaign_group → create_campaign (per LineItem) → create_creative
    (per Ad). Everything is created as `DRAFT` — nothing can spend without a
    manual activation step in LinkedIn Campaign Manager.

    Returns the URNs created so the agent can present them for approval, plus a
    `notes` block flagging any B2B targeting facet values from the Brief that
    matched no LinkedIn entity (so they were not pushed — we never guess a URN).
    """
    parsed = Campaign.model_validate(campaign)
    config = LinkedInConfig.from_env()

    result: dict[str, Any] = {"line_items": [], "ads": [], "notes": {}}
    unresolved_by_li: dict[str, dict[str, Any]] = {}

    async with LinkedInClient(config) as client:
        client.assert_account_allowed()
        amount, currency = _group_budget(parsed)

        # Track every resource we create so we can tear it down if a later step
        # fails — LinkedIn has no transaction, so a mid-flow error otherwise
        # strands orphaned DRAFTs on the account.
        created = _Created()
        try:
            group_id, group_urn = await _create_group(client, parsed, created, amount, currency)
            result["campaign_id"] = group_id
            result["campaign_group_urn"] = group_urn

            org_urn = await _resolve_org_urn(client, config, parsed)
            line_item_urns, unresolved_by_li, result["line_items"] = await _create_line_items(
                client, parsed, created, group_urn, campaign_objective(parsed)
            )
            result["ads"] = await _create_ads(
                client, config, parsed, created, line_item_urns, org_urn
            )
        except Exception as exc:
            await _rollback_and_raise(client, created, exc)

        if unresolved_by_li:
            result["notes"]["unresolved_b2b_targeting"] = unresolved_by_li
            result["notes"]["unresolved_b2b_hint"] = (
                "These facet values came from the Brief but matched no LinkedIn targeting "
                "entity (typeahead/standardized lookup returned nothing), so they were not "
                "pushed — we never guess a URN. Add them manually in Campaign Manager before "
                "activation, or refine the wording to match LinkedIn's taxonomy."
            )

    return result


def main() -> None:
    load_dotenv()
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
