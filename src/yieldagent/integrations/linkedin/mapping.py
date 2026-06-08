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

from yieldagent.domain import (
    Audience,
    BiddingStrategy,
    Campaign,
    CreativeAsset,
    Flight,
    LineItem,
    Objective,
)

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

# Auto-bidding ("Maximum delivery") optimizationTargetType per objective. With one
# of these set, LinkedIn bids automatically — costType is CPM and unitCost stays 0,
# so we never set a manual bid (no guessed price). Without it, a campaign defaults
# to manual CPC bidding and shows a "fix your bid" error until a price is entered.
OBJECTIVE_TO_OPTIMIZATION_TARGET: dict[str, str] = {
    "BRAND_AWARENESS": "MAX_IMPRESSION",
    "WEBSITE_VISITS": "MAX_CLICK",
    "ENGAGEMENT": "MAX_CLICK",
    "LEAD_GENERATION": "MAX_LEAD",
    "WEBSITE_CONVERSIONS": "MAX_CONVERSION",
}

# costType for auto-bidding is always CPM (LinkedIn charges per impression and
# optimizes toward the objective's target event).
AUTO_BID_COST_TYPE = "CPM"


def campaign_objective(campaign: Campaign) -> str:
    return OBJECTIVE_TO_LINKEDIN[campaign.objective]


def campaign_optimization_target(objective_type: str) -> str | None:
    """The auto-bidding optimizationTargetType for a LinkedIn objectiveType.

    None for an unmapped objective — the caller then omits the field (manual
    bidding), rather than sending an invalid combination LinkedIn would reject.
    """
    return OBJECTIVE_TO_OPTIMIZATION_TARGET.get(objective_type)


def campaign_bidding(line_item: LineItem, objective_type: str) -> dict[str, Any]:
    """Translate a line item's bidding choice into create_campaign kwargs.

    Returns `cost_type`, `optimization_target_type`, and `unit_cost`:
      * maximum_delivery (default) — CPM + the objective's optimization target,
        no manual price (LinkedIn bids automatically).
      * cost_cap — same auto target, but `unit_cost` carries the target cost cap.
      * manual — CPC with `unit_cost` as the bid, and no optimization target.

    An operator-supplied `optimization_goal` overrides the objective-derived one.
    `bid_amount` is required for cost_cap/manual (enforced in pre-flight); if it is
    somehow absent, `unit_cost` is None and LinkedIn's API is the backstop.
    """
    strategy = line_item.bidding_strategy or BiddingStrategy.maximum_delivery
    target = line_item.optimization_goal or campaign_optimization_target(objective_type)
    bid = line_item.bid_amount
    unit_cost = money_to_linkedin_amount(bid.amount, bid.currency) if bid else None

    if strategy is BiddingStrategy.manual:
        return {"cost_type": "CPC", "optimization_target_type": None, "unit_cost": unit_cost}
    if strategy is BiddingStrategy.cost_cap:
        return {
            "cost_type": AUTO_BID_COST_TYPE,
            "optimization_target_type": target,
            "unit_cost": unit_cost,
        }
    # maximum_delivery: auto-bid when we have a target, else fall back to manual CPC.
    if target:
        return {
            "cost_type": AUTO_BID_COST_TYPE,
            "optimization_target_type": target,
            "unit_cost": None,
        }
    return {"cost_type": "CPC", "optimization_target_type": None, "unit_cost": unit_cost}


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


# LinkedIn campaign `locale` must be a SUPPORTED member-UI interface locale, not
# any country+language combo. e.g. `en_PT` is rejected (INVALID_INTERFACE_LOCALE_CODE)
# and Portuguese only exists as `pt_BR`. This maps each country with a known-good
# locale to its (country, language); everything else falls back to en_US.
# Source: LinkedIn reference-tables/language-codes (interface locales).
SUPPORTED_LOCALE_BY_COUNTRY: dict[str, tuple[str, str]] = {
    "AE": ("AE", "ar"),
    "BR": ("BR", "pt"),
    "CN": ("CN", "zh"),
    "CZ": ("CZ", "cs"),
    "DE": ("DE", "de"),
    "DK": ("DK", "da"),
    "ES": ("ES", "es"),
    "FR": ("FR", "fr"),
    "GB": ("GB", "en"),
    "ID": ("ID", "in"),
    "IT": ("IT", "it"),
    "JP": ("JP", "ja"),
    "KR": ("KR", "ko"),
    "MY": ("MY", "ms"),
    "NL": ("NL", "nl"),
    "NO": ("NO", "no"),
    "PH": ("PH", "tl"),
    "PL": ("PL", "pl"),
    "RO": ("RO", "ro"),
    "RU": ("RU", "ru"),
    "SE": ("SE", "sv"),
    "TH": ("TH", "th"),
    "TR": ("TR", "tr"),
    "TW": ("TW", "zh"),
    "UA": ("UA", "uk"),
    "US": ("US", "en"),
}


def line_item_locale(audience: Audience) -> dict[str, str]:
    """LinkedIn campaigns require a `locale` that is a SUPPORTED interface locale.

    Not every country+language combination is valid (e.g. `en_PT` is rejected),
    so we look the first audience geo up in the supported-locale table and fall
    back to en_US for anything LinkedIn does not support as a UI locale.
    """
    country = audience.geos[0].strip().upper() if audience.geos else "US"
    locale = SUPPORTED_LOCALE_BY_COUNTRY.get(country, ("US", "en"))
    return {"country": locale[0], "language": locale[1]}


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
    "AUTO_BID_COST_TYPE",
    "DEFAULT_CAMPAIGN_TYPE",
    "OBJECTIVE_TO_LINKEDIN",
    "OBJECTIVE_TO_OPTIMIZATION_TARGET",
    "campaign_bidding",
    "campaign_objective",
    "campaign_optimization_target",
    "campaign_run_schedule",
    "creative_content_reference",
    "flight_to_run_schedule",
    "line_item_locale",
    "money_to_linkedin_amount",
    "post_article_content",
    "post_commentary",
]
