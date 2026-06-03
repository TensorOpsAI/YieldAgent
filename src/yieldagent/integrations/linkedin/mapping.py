"""Translate platform-neutral domain objects into LinkedIn Marketing API payloads.

Kept in one place so the MCP server stays a thin HTTP layer and so contributors
adding new platforms have a clear reference for what this mapping involves.

Hierarchy mapping:

| YieldAgent | LinkedIn       |
|------------|----------------|
| Campaign   | Campaign Group |
| LineItem   | Campaign       |
| Ad         | Creative       |

LinkedIn's three-level hierarchy lines up cleanly with our domain model — the
naming is the only thing that shifts.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

import pycountry

from yieldagent.domain import Audience, Campaign, CreativeAsset, Flight, Objective

# LinkedIn objectiveType values for Sponsored Content campaigns.
OBJECTIVE_TO_LINKEDIN: dict[Objective, str] = {
    Objective.awareness: "BRAND_AWARENESS",
    Objective.traffic: "WEBSITE_VISITS",
    Objective.engagement: "ENGAGEMENT",
    Objective.leads: "LEAD_GENERATION",
    Objective.app_promotion: "WEBSITE_VISITS",  # no dedicated app-install on LinkedIn
    Objective.sales: "WEBSITE_CONVERSIONS",
}

# LinkedIn campaign type for standard image / single-share Sponsored Content.
DEFAULT_CAMPAIGN_TYPE = "SPONSORED_UPDATES"


def campaign_objective(campaign: Campaign) -> str:
    return OBJECTIVE_TO_LINKEDIN[campaign.objective]


def money_to_linkedin_amount(amount: Any, currency: str) -> dict[str, str]:
    """LinkedIn expects amounts as decimal strings, not minor units."""
    return {"amount": str(amount), "currencyCode": currency.upper()}


def flight_to_run_schedule(flight: Flight) -> dict[str, int]:
    """LinkedIn `runSchedule` uses epoch milliseconds. End-date is inclusive."""
    start = datetime.combine(flight.start_date, time.min, tzinfo=UTC)
    end = datetime.combine(flight.end_date, time.max, tzinfo=UTC)
    return {"start": int(start.timestamp() * 1000), "end": int(end.timestamp() * 1000)}


def campaign_run_schedule(flights: list[Flight]) -> dict[str, int]:
    """Build a Campaign Group runSchedule that spans all its child Campaigns.

    LinkedIn now requires `runSchedule` on `POST /adAccounts/{id}/adCampaignGroups`.
    The group must cover the earliest start and latest end across its line items.
    """
    if not flights:
        raise ValueError("Cannot compute runSchedule from empty list of flights")
    earliest = min(f.start_date for f in flights)
    latest = max(f.end_date for f in flights)
    return flight_to_run_schedule(Flight(start_date=earliest, end_date=latest))


def line_item_locale(audience: Audience) -> dict[str, str]:
    """LinkedIn campaigns require a `locale` (country + language).

    Derived from the first audience geo if it is a valid ISO 3166-1 alpha-2
    code; defaults to en/US otherwise.
    """
    country = audience.geos[0].strip().upper() if audience.geos else "US"
    if pycountry.countries.get(alpha_2=country) is None:
        country = "US"
    return {"country": country, "language": "en"}


def post_article_content(creative: CreativeAsset) -> dict[str, Any]:
    """Build the `article` block for a Posts API dark post.

    A Creative can't hold inline copy — it references a Post. We model each ad as
    an article post pointing at the landing URL. The Posts API does *not* scrape
    the URL, so we set title/description explicitly.

    Thumbnail is intentionally omitted: it must be an `urn:li:image:{id}` from the
    Images API, not a plain URL. Uploading creative imagery is a follow-up; until
    then posts render with LinkedIn's default link preview.
    """
    article: dict[str, Any] = {
        "source": creative.landing_url or "https://example.com",
    }
    if creative.headline:
        article["title"] = creative.headline
    if creative.description:
        article["description"] = creative.description
    return article


def post_commentary(creative: CreativeAsset) -> str:
    """The text shown above the post. Falls back through primary_text → headline → name."""
    return creative.primary_text or creative.headline or creative.name


def creative_content_reference(post_urn: str) -> dict[str, Any]:
    """Wrap a Post URN as a Creative `content` reference."""
    return {"reference": post_urn}


__all__ = [
    "DEFAULT_CAMPAIGN_TYPE",
    "OBJECTIVE_TO_LINKEDIN",
    "campaign_objective",
    "campaign_run_schedule",
    "creative_content_reference",
    "flight_to_run_schedule",
    "line_item_locale",
    "money_to_linkedin_amount",
    "post_article_content",
    "post_commentary",
]
