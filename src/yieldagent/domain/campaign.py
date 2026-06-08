"""Platform-neutral campaign structure.

Three levels — Campaign, LineItem, Ad — map cleanly onto every major ad platform:

| YieldAgent | Meta    | Google Ads | DV360       |
|------------|---------|------------|-------------|
| Campaign   | Campaign| Campaign   | Campaign    |
| LineItem   | Ad Set  | Ad Group   | Line Item   |
| Ad         | Ad      | Ad         | Creative    |

Budget and schedule live at the LineItem level (matching Meta and DV360); a
Campaign-level lifetime budget is optional and only used by platforms that
support it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .brief import Audience, CreativeAsset, Flight, Money, Objective


class CampaignStatus(StrEnum):
    draft = "draft"
    paused = "paused"
    active = "active"


class Targeting(BaseModel):
    audience: Audience


class BiddingStrategy(StrEnum):
    """How the platform bids in the auction.

    maximum_delivery — let the platform spend the full budget for the most results
    (auto bid, no price needed). cost_cap — chase results while keeping average cost
    under a target. manual — set the bid yourself. cost_cap and manual need bid_amount.
    """

    maximum_delivery = "maximum_delivery"
    cost_cap = "cost_cap"
    manual = "manual"


class LineItem(BaseModel):
    name: str
    budget: Money
    flight: Flight
    targeting: Targeting

    # Optional delivery controls. Absent means the agent/platform picks a sensible
    # default (maximum delivery, no daily cap, no expansion, LinkedIn-only). The
    # operator can set any of these to take control; each connector maps what it
    # supports and ignores the rest.
    daily_budget: Money | None = None
    bidding_strategy: BiddingStrategy | None = None
    bid_amount: Money | None = Field(
        default=None, description="Bid or cost cap; required for cost_cap and manual bidding."
    )
    optimization_goal: str | None = Field(
        default=None,
        description="Override the auto optimization goal; omit to derive it from the objective.",
    )
    audience_expansion: bool | None = None
    audience_network: bool | None = Field(
        default=None, description="Deliver off-platform via the Audience Network."
    )


class Ad(BaseModel):
    name: str
    line_item_name: str = Field(
        description="References LineItem.name; resolved to a platform id at publish time."
    )
    creative: CreativeAsset


class Campaign(BaseModel):
    name: str
    objective: Objective
    status: CampaignStatus = Field(
        default=CampaignStatus.draft,
        description="Drafts never auto-activate; flipping to active is a human gate.",
    )
    lifetime_budget: Money | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    ads: list[Ad] = Field(default_factory=list)


class PlatformPlan(BaseModel):
    """One platform's slice of a campaign: its connector key + native Campaign.

    Budgets live inside `campaign` (per platform), so platforms never share a
    budget — a core requirement. The agent fills each PlatformPlan by ELICITING
    per-platform inputs and reusing only genuinely-identical shared inputs (geo,
    dates, creative); it never auto-converts one platform's targeting to another.
    """

    platform: str
    campaign: Campaign


class CampaignPlan(BaseModel):
    """A single campaign intent spanning one or more platforms.

    The shared core (name) plus a `PlatformPlan` per platform. Targeting stays in
    the union `Audience` (LinkedIn B2B facets and Meta age/gender/interests coexist
    on one model; each connector reads what it understands) — a deliberate choice
    over splitting into platform-native targeting types, so shared inputs reuse
    cleanly and the agent has one audience shape to fill.
    """

    name: str
    platforms: list[PlatformPlan] = Field(default_factory=list)

    @classmethod
    def single(cls, platform: str, campaign: Campaign | dict) -> CampaignPlan:
        """Build a one-platform plan from a platform key and a Campaign (or dict)."""
        camp = campaign if isinstance(campaign, Campaign) else Campaign.model_validate(campaign)
        return cls(name=camp.name, platforms=[PlatformPlan(platform=platform, campaign=camp)])
