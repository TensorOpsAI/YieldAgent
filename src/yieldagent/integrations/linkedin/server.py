"""MCP server exposing the LinkedIn Marketing API to YieldAgent agents.

Run with: `python -m yieldagent.integrations.linkedin.server`

Required env: LINKEDIN_ACCESS_TOKEN, LINKEDIN_AD_ACCOUNT_ID
Optional env: LINKEDIN_API_VERSION (default 202405),
              LINKEDIN_ALLOWED_AD_ACCOUNTS (comma-separated allowlist),
              YIELDAGENT_ALLOW_LIVE (set to 1 to bypass the allowlist)
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from yieldagent.domain import Campaign

from .client import AnalyticsPivot, LinkedInClient, TimeGranularity
from .config import LinkedInConfig
from .mapping import (
    DEFAULT_CAMPAIGN_TYPE,
    audience_to_targeting,
    campaign_objective,
    creative_content,
    flight_to_run_schedule,
    hash_email_for_dmp,
    line_item_locale,
    money_to_linkedin_amount,
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
        )
        group_urn = f"urn:li:sponsoredCampaignGroup:{group['id']}"
        result["campaign_id"] = group["id"]
        result["campaign_group_urn"] = group_urn

        objective_type = campaign_objective(parsed)

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
            created = await client.create_creative(
                campaign_urn=campaign_urn,
                content=creative_content(ad.creative),
            )
            result["ads"].append(
                {"name": ad.name, "id": created.get("id"), "campaign_urn": campaign_urn}
            )

        if unresolved_by_li:
            result["notes"]["unresolved_b2b_targeting"] = unresolved_by_li
            result["notes"]["unresolved_b2b_hint"] = (
                "These B2B facets are present on the Brief audience but were not pushed to "
                "LinkedIn — they require URN resolution via the typeahead endpoint, which is "
                "not wired in this slice. Add them manually in Campaign Manager before activation."
            )

    return result


# -- Campaign reads (read-only) ---------------------------------------------


@mcp.tool()
async def list_campaigns(
    status_values: list[str] | None = None,
    type_values: list[str] | None = None,
    campaign_group_urns: list[str] | None = None,
    page_size: int = 100,
    page_token: str | None = None,
) -> dict[str, Any]:
    """Read-only: list campaigns under the configured ad account.

    Filters are optional. `status_values` accepts LinkedIn statuses
    (ACTIVE, PAUSED, ARCHIVED, COMPLETED, CANCELED, DRAFT, REMOVED).
    Returns the raw search payload, including `metadata.nextPageToken` if
    paginated.
    """
    async with _client() as client:
        return await client.list_campaigns(
            status_values=status_values,
            type_values=type_values,
            campaign_group_urns=campaign_group_urns,
            page_size=page_size,
            page_token=page_token,
        )


@mcp.tool()
async def get_campaign(campaign_id: str) -> dict[str, Any]:
    """Read-only: fetch a single campaign by numeric id."""
    async with _client() as client:
        return await client.get_campaign(campaign_id)


# -- Campaign edits (spend_or_publish, gated by confirm) -------------------


@mcp.tool()
async def pause_campaign(campaign_id: str, confirm: bool = False) -> dict[str, Any]:
    """Spend gate: pause an existing campaign.

    Returns a dry-run preview when `confirm` is False. Re-call with
    `confirm=True` to apply.
    """
    async with _client() as client:
        return await client.set_campaign_status(campaign_id, "PAUSED", confirm=confirm)


@mcp.tool()
async def resume_campaign(campaign_id: str, confirm: bool = False) -> dict[str, Any]:
    """Spend gate: resume a paused campaign back to ACTIVE.

    Returns a dry-run preview when `confirm` is False.
    """
    async with _client() as client:
        return await client.set_campaign_status(campaign_id, "ACTIVE", confirm=confirm)


@mcp.tool()
async def archive_campaign(campaign_id: str, confirm: bool = False) -> dict[str, Any]:
    """Spend gate: archive a campaign (hidden but not deleted)."""
    async with _client() as client:
        return await client.set_campaign_status(campaign_id, "ARCHIVED", confirm=confirm)


@mcp.tool()
async def activate_draft_campaign(campaign_id: str, confirm: bool = False) -> dict[str, Any]:
    """Spend gate: flip a DRAFT campaign to ACTIVE.

    This is the gated path around the create-campaign refusal to set ACTIVE
    directly. The agent must explicitly ask the operator before delivering
    impressions / spending budget.
    """
    async with _client() as client:
        return await client.set_campaign_status(campaign_id, "ACTIVE", confirm=confirm)


@mcp.tool()
async def update_campaign_budget(
    campaign_id: str,
    daily_budget_amount: str | None = None,
    total_budget_amount: str | None = None,
    currency: str = "USD",
    clear_total_budget: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Spend gate: change a campaign's daily and/or total budget.

    Pass either or both of `daily_budget_amount` / `total_budget_amount`.
    Set `clear_total_budget=True` to remove the lifetime cap (rare; only
    valid when a daily cap exists). Returns a dry-run preview by default.
    """
    daily = (
        {"amount": daily_budget_amount, "currencyCode": currency.upper()}
        if daily_budget_amount is not None
        else None
    )
    total = (
        {"amount": total_budget_amount, "currencyCode": currency.upper()}
        if total_budget_amount is not None
        else None
    )
    async with _client() as client:
        return await client.update_campaign_budget(
            campaign_id,
            daily_budget=daily,
            total_budget=total,
            clear_total_budget=clear_total_budget,
            confirm=confirm,
        )


@mcp.tool()
async def update_campaign_schedule(
    campaign_id: str,
    start_epoch_ms: int | None = None,
    end_epoch_ms: int | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Spend gate: change a campaign's start and/or end time (epoch ms)."""
    async with _client() as client:
        return await client.update_campaign_schedule(
            campaign_id,
            start_epoch_ms=start_epoch_ms,
            end_epoch_ms=end_epoch_ms,
            confirm=confirm,
        )


# -- Ad Analytics (read-only) ----------------------------------------------

_DEFAULT_ANALYTICS_FIELDS = [
    "impressions",
    "clicks",
    "costInLocalCurrency",
    "externalWebsiteConversions",
    "oneClickLeads",
    "landingPageClicks",
    "likes",
    "shares",
    "dateRange",
    "pivotValues",
]


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"date must be ISO YYYY-MM-DD, got {value!r}") from exc


@mcp.tool()
async def get_campaign_analytics(
    campaign_urns: list[str],
    date_start: str,
    date_end: str | None = None,
    pivot: AnalyticsPivot = "CAMPAIGN",
    time_granularity: TimeGranularity = "ALL",
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only: pull Ad Analytics for one or more campaigns.

    `date_start` / `date_end` accept ISO `YYYY-MM-DD` strings; `date_end` is
    optional (open range). `pivot` controls how rows are grouped (CAMPAIGN,
    CREATIVE, MEMBER_*, etc.).
    """
    start = _parse_iso_date(date_start)
    end = _parse_iso_date(date_end) if date_end else None
    async with _client() as client:
        return await client.get_ad_analytics(
            pivot=pivot,
            date_start=start,
            date_end=end,
            time_granularity=time_granularity,
            campaign_urns=campaign_urns,
            fields=fields or _DEFAULT_ANALYTICS_FIELDS,
        )


@mcp.tool()
async def get_creative_analytics(
    creative_urns: list[str],
    date_start: str,
    date_end: str | None = None,
    time_granularity: TimeGranularity = "DAILY",
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only: pull Ad Analytics broken down by creative.

    Same shape as `get_campaign_analytics` but scoped to creative URNs and
    pivoted by `CREATIVE`. Defaults to DAILY granularity so the caller can
    plot a curve / detect drift.
    """
    start = _parse_iso_date(date_start)
    end = _parse_iso_date(date_end) if date_end else None
    async with _client() as client:
        return await client.get_ad_analytics(
            pivot="CREATIVE",
            date_start=start,
            date_end=end,
            time_granularity=time_granularity,
            creative_urns=creative_urns,
            fields=fields or _DEFAULT_ANALYTICS_FIELDS,
        )


@mcp.tool()
async def get_account_analytics(
    date_start: str,
    date_end: str | None = None,
    pivot: AnalyticsPivot = "ACCOUNT",
    time_granularity: TimeGranularity = "ALL",
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only: pull Ad Analytics scoped to the configured ad account.

    Useful for "what did we spend overall last week" without enumerating
    campaign URNs. Pivot defaults to ACCOUNT but can be set to any pivot
    LinkedIn supports for an account-scoped query.
    """
    start = _parse_iso_date(date_start)
    end = _parse_iso_date(date_end) if date_end else None
    async with _client() as client:
        return await client.get_ad_analytics(
            pivot=pivot,
            date_start=start,
            date_end=end,
            time_granularity=time_granularity,
            account_urns=[client.config.account_urn],
            fields=fields or _DEFAULT_ANALYTICS_FIELDS,
        )


@mcp.tool()
async def compare_campaign_periods(
    campaign_urns: list[str],
    current_start: str,
    current_end: str,
    baseline_start: str,
    baseline_end: str,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only: pull aggregate metrics for the same campaigns over two windows.

    Returns `{current: <analytics>, baseline: <analytics>}`. The agent can
    diff CTR / CPL / spend to spot week-over-week drift. Both windows use
    `timeGranularity=ALL` so each campaign collapses to a single row.
    """
    metrics = fields or _DEFAULT_ANALYTICS_FIELDS
    async with _client() as client:
        current = await client.get_ad_analytics(
            pivot="CAMPAIGN",
            date_start=_parse_iso_date(current_start),
            date_end=_parse_iso_date(current_end),
            time_granularity="ALL",
            campaign_urns=campaign_urns,
            fields=metrics,
        )
        baseline = await client.get_ad_analytics(
            pivot="CAMPAIGN",
            date_start=_parse_iso_date(baseline_start),
            date_end=_parse_iso_date(baseline_end),
            time_granularity="ALL",
            campaign_urns=campaign_urns,
            fields=metrics,
        )
    return {"current": current, "baseline": baseline}


# -- Lead Sync (read + subscribe) ------------------------------------------


@mcp.tool()
async def list_lead_forms(
    owner_organization_urn: str | None = None,
    owner_sponsored_account_urn: str | None = None,
    count: int = 10,
    start: int = 0,
) -> dict[str, Any]:
    """Read-only: list Lead Gen Forms owned by an organization or ad account."""
    async with _client() as client:
        return await client.list_lead_forms(
            owner_organization_urn=owner_organization_urn,
            owner_sponsored_account_urn=owner_sponsored_account_urn,
            count=count,
            start=start,
        )


@mcp.tool()
async def get_lead_form(form_id: str) -> dict[str, Any]:
    """Read-only: fetch one Lead Gen Form by id."""
    async with _client() as client:
        return await client.get_lead_form(form_id)


@mcp.tool()
async def pull_lead_responses(
    versioned_form_urn: str | None = None,
    lead_type: str = "SPONSORED",
    limited_to_test_leads: bool = False,
) -> dict[str, Any]:
    """Read-only: pull lead-form submissions for the configured ad account.

    `versioned_form_urn` looks like
    `urn:li:versionedLeadGenForm:(urn:li:leadGenForm:3162,1)`. If omitted,
    responses across all forms owned by the account are returned. Requires
    the `r_marketing_leadgen_automation` scope.
    """
    if lead_type.upper() not in {"SPONSORED", "ORGANIC"}:
        raise ValueError("lead_type must be SPONSORED or ORGANIC")
    async with _client() as client:
        return await client.list_lead_responses(
            sponsored_account_urn=client.config.account_urn,
            versioned_form_urn=versioned_form_urn,
            lead_type=lead_type.upper(),  # type: ignore[arg-type]
            limited_to_test_leads=limited_to_test_leads,
        )


@mcp.tool()
async def subscribe_lead_webhook(
    webhook_url: str,
    versioned_form_urn: str | None = None,
    lead_type: str = "SPONSORED",
    confirm: bool = False,
) -> dict[str, Any]:
    """Credential-sensitive: register a webhook to receive lead notifications.

    LinkedIn validates the webhook before accepting it: it issues a GET to
    `webhook_url` with a `challengeCode` query parameter, expecting
    `{challengeCode, challengeResponse}` where `challengeResponse` is the
    hex HMAC-SHA256 of the code keyed by the LinkedIn app's client secret.
    YieldAgent's web app ships a receiver at
    `/api/webhooks/linkedin/leadsync` that performs this handshake using
    the stored provider config. Confirm=False returns the payload preview.
    """
    if not webhook_url.startswith("https://"):
        raise ValueError("LinkedIn only accepts HTTPS webhook URLs.")
    if lead_type.upper() not in {"SPONSORED", "ORGANIC"}:
        raise ValueError("lead_type must be SPONSORED or ORGANIC")
    async with _client() as client:
        if not confirm:
            return {
                "dry_run": True,
                "endpoint": "/leadNotifications",
                "body": {
                    "webhook": webhook_url,
                    "owner": {"sponsoredAccount": client.config.account_urn},
                    "leadType": lead_type.upper(),
                    **({"versionedForm": versioned_form_urn} if versioned_form_urn else {}),
                },
                "hint": "Re-call with confirm=True to register.",
            }
        client.assert_account_allowed()
        return await client.subscribe_lead_notifications(
            webhook_url=webhook_url,
            owner_sponsored_account_urn=client.config.account_urn,
            versioned_form_urn=versioned_form_urn,
            lead_type=lead_type.upper(),  # type: ignore[arg-type]
        )


# -- Matched Audiences (credential_sensitive, gated by confirm for upload) --


@mcp.tool()
async def create_dmp_segment(
    name: str,
    segment_type: str = "COMPANY_LIST_UPLOAD",
    source_platform: str = "LIST_UPLOAD",
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a DMP Segment under the configured ad account.

    Requires the `rw_dmp_segments` OAuth scope. Returns a dry-run preview
    when `confirm` is False so the operator can verify name + type before a
    write. Types: COMPANY_LIST_UPLOAD / USER_LIST_UPLOAD for CSV uploads,
    COMPANY / USER for streaming dynamic add/remove.
    """
    if not confirm:
        return {
            "dry_run": True,
            "method": "POST",
            "endpoint": "/dmpSegments",
            "body": {
                "account": LinkedInConfig.from_env().account_urn,
                "destinations": [{"destination": "LINKEDIN"}],
                "name": name,
                "sourcePlatform": source_platform,
                "type": segment_type,
            },
            "hint": "Re-call with confirm=True to create the segment.",
        }
    async with _client() as client:
        client.assert_account_allowed()
        return await client.create_dmp_segment(
            name=name,
            segment_type=segment_type,  # type: ignore[arg-type]
            source_platform=source_platform,  # type: ignore[arg-type]
        )


@mcp.tool()
async def get_dmp_segment(segment_id: str) -> dict[str, Any]:
    """Read-only: fetch a DMP segment's status. READY means the adSegment URN is targetable."""
    async with _client() as client:
        return await client.get_dmp_segment(segment_id)


@mcp.tool()
async def upload_audience_csv(
    segment_id: str,
    csv_bytes_b64: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Spend-or-publish: upload a CSV to an existing DMP segment.

    `csv_bytes_b64` must be a base64-encoded CSV body (so the MCP tool
    surface stays text-safe). The full LinkedIn handshake is:
    `generateUploadUrl` → POST CSV bytes → `attach_dmp_list`. Confirm=False
    returns the URLs + media URN it would attach without actually attaching.
    """
    import base64

    csv_bytes = base64.b64decode(csv_bytes_b64)
    async with _client() as client:
        client.assert_account_allowed()
        url_resp = await client.generate_dmp_upload_url()
        upload_url = url_resp.get("value")
        if not upload_url:
            raise RuntimeError(
                "generateUploadUrl returned no value; check rw_dmp_segments scope"
            )
        media_urn = await client.upload_dmp_csv(upload_url, csv_bytes)
        if not confirm:
            return {
                "dry_run": True,
                "upload_url": upload_url,
                "media_urn": media_urn,
                "next": f"POST /dmpSegments/{segment_id}/listUploads",
                "hint": "Re-call with confirm=True to attach this upload.",
            }
        attach = await client.attach_dmp_list(segment_id, media_urn)
        return {"applied": True, "media_urn": media_urn, "attach": attach}


@mcp.tool()
async def hash_emails_for_audience(emails: list[str]) -> list[str]:
    """Read-only utility: SHA256-hex-hash a list of emails (lowercased, trimmed).

    Returned strings match LinkedIn's expected format for contact-list
    matched-audience uploads. Does not touch the network.
    """
    return [hash_email_for_dmp(email) for email in emails]


@mcp.tool()
async def add_dmp_users(
    segment_id: str,
    hashed_emails: list[str] | None = None,
    google_aids: list[str] | None = None,
    action: str = "ADD",
    confirm: bool = False,
) -> dict[str, Any]:
    """Spend-or-publish: streaming add/remove for `sourcePlatform=API`, `type=USER` segments.

    Provide pre-hashed emails (use `hash_emails_for_audience` first).
    Confirm=False returns the payload preview without hitting LinkedIn.
    """
    if action.upper() not in {"ADD", "REMOVE"}:
        raise ValueError("action must be 'ADD' or 'REMOVE'")
    if not (hashed_emails or google_aids):
        raise ValueError("add_dmp_users requires hashed_emails or google_aids")
    if not confirm:
        ids: list[dict[str, str]] = []
        for email in hashed_emails or []:
            ids.append({"idType": "SHA256_EMAIL", "idValue": email})
        for gaid in google_aids or []:
            ids.append({"idType": "GOOGLE_AID", "idValue": gaid})
        return {
            "dry_run": True,
            "endpoint": f"/dmpSegments/{segment_id}/users",
            "body": {"elements": [{"action": action.upper(), "userIds": ids}]},
            "hint": "Re-call with confirm=True to send.",
        }
    async with _client() as client:
        client.assert_account_allowed()
        return await client.add_dmp_users(
            segment_id,
            hashed_emails=hashed_emails,
            google_aids=google_aids,
            action=action.upper(),  # type: ignore[arg-type]
        )


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
