"""Campaign brief — the input contract handed to a campaign-setup agent.

A Brief is platform-agnostic. A planner (human or upstream agent) writes one;
a downstream agent reads it and produces a draft Campaign for one or more
platforms.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Objective(StrEnum):
    awareness = "awareness"
    traffic = "traffic"
    engagement = "engagement"
    leads = "leads"
    app_promotion = "app_promotion"
    sales = "sales"


class Flight(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _end_after_start(self) -> Flight:
        if self.end_date < self.start_date:
            raise ValueError("Flight end_date must be on or after start_date")
        return self


class Money(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217 code")


class KPI(BaseModel):
    metric: str = Field(description="e.g. 'ROAS', 'CPA', 'CTR'")
    target: Decimal | None = None


class Audience(BaseModel):
    description: str
    age_min: int | None = Field(default=None, ge=13, le=99)
    age_max: int | None = Field(default=None, ge=13, le=99)
    genders: list[str] = Field(default_factory=list)
    geos: list[str] = Field(
        default_factory=list,
        description="ISO 3166-1 alpha-2 country codes; finer-grained geos handled per-platform",
    )
    interests: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)

    # B2B targeting facets — used by LinkedIn, ignored by consumer platforms.
    industries: list[str] = Field(
        default_factory=list,
        description=(
            "Industry names (e.g. 'Software Development', 'Financial Services'). "
            "LinkedIn resolves these to URNs."
        ),
    )
    job_functions: list[str] = Field(
        default_factory=list,
        description="Job functions (e.g. 'Engineering', 'Marketing', 'Sales').",
    )
    job_titles: list[str] = Field(
        default_factory=list,
        description=(
            "Free-form job titles (e.g. 'VP of Engineering'). "
            "LinkedIn resolves to title URNs."
        ),
    )
    seniorities: list[str] = Field(
        default_factory=list,
        description="Seniority levels (e.g. 'Manager', 'Director', 'VP', 'CXO', 'Owner').",
    )
    company_sizes: list[str] = Field(
        default_factory=list,
        description="LinkedIn staff-count buckets, e.g. '11-50', '51-200', '1001-5000', '10001+'.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description=(
            "Skill keywords (e.g. 'Kubernetes', 'Demand Generation'). "
            "LinkedIn resolves to skill URNs."
        ),
    )


class CreativeAsset(BaseModel):
    name: str
    headline: str | None = None
    primary_text: str | None = None
    description: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    call_to_action: str | None = None
    landing_url: str | None = None
    existing_post_urn: str | None = Field(
        default=None,
        description=(
            "URN of an already-published LinkedIn post/share (e.g. 'urn:li:share:123'). "
            "When set, the ad references this post directly instead of creating a new "
            "Direct Sponsored Content post — use it to advertise content published by hand."
        ),
    )


class Brief(BaseModel):
    advertiser: str
    product: str
    objective: Objective
    kpis: list[KPI]
    budget: Money
    flight: Flight
    audience: Audience
    creatives: list[CreativeAsset]
    platforms: list[str] = Field(description="Lowercase platform keys, e.g. ['meta']")
    notes: str | None = None
