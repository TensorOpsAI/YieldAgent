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

from enum import Enum

from pydantic import BaseModel, Field

from .brief import Audience, CreativeAsset, Flight, Money, Objective


class CampaignStatus(str, Enum):
    draft = "draft"
    paused = "paused"
    active = "active"


class Targeting(BaseModel):
    audience: Audience


class LineItem(BaseModel):
    name: str
    budget: Money
    flight: Flight
    targeting: Targeting


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
