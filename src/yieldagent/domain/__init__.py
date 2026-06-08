"""Platform-neutral adtech domain model.

The first pillar of YieldAgent: a shared ontology so agents on either side of the
market interoperate without translation loss.

Vocabulary follows IAB / industry-common usage. Each platform integration is
responsible for mapping these types onto its own surface (Meta calls a LineItem
an "Ad Set", Google calls it an "Ad Group", etc.).
"""

from .campaign import (
    Ad,
    BiddingStrategy,
    Campaign,
    CampaignPlan,
    CampaignStatus,
    LineItem,
    PlatformPlan,
    Targeting,
)
from .primitives import KPI, Audience, CreativeAsset, Flight, Money, Objective

__all__ = [
    "Ad",
    "Audience",
    "BiddingStrategy",
    "Campaign",
    "CampaignPlan",
    "CampaignStatus",
    "CreativeAsset",
    "Flight",
    "KPI",
    "LineItem",
    "Money",
    "Objective",
    "PlatformPlan",
    "Targeting",
]
