"""Platform-neutral adtech domain model.

The first pillar of YieldAgent: a shared ontology so agents on either side of the
market interoperate without translation loss.

Vocabulary follows IAB / industry-common usage. Each platform integration is
responsible for mapping these types onto its own surface (Meta calls a LineItem
an "Ad Set", Google calls it an "Ad Group", etc.).
"""

from .brief import KPI, Audience, Brief, CreativeAsset, Flight, Money, Objective
from .campaign import (
    Ad,
    BiddingStrategy,
    Campaign,
    CampaignStatus,
    LineItem,
    Targeting,
)

__all__ = [
    "Ad",
    "Audience",
    "BiddingStrategy",
    "Brief",
    "Campaign",
    "CampaignStatus",
    "CreativeAsset",
    "Flight",
    "KPI",
    "LineItem",
    "Money",
    "Objective",
    "Targeting",
]
