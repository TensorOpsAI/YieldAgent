"""Tests for the CampaignPlan / PlatformPlan model and plan_issues (C2)."""

from __future__ import annotations

from typing import Any

from yieldagent.agents.console.validation import campaign_issues, plan_issues
from yieldagent.domain import CampaignPlan


def _campaign() -> dict[str, Any]:
    return {
        "name": "Q3 Demand Gen",
        "objective": "awareness",
        "line_items": [
            {
                "name": "Main",
                "budget": {"amount": 300, "currency": "EUR"},
                "flight": {"start_date": "2026-06-16", "end_date": "2026-06-30"},
                "targeting": {"audience": {"description": "x", "geos": ["US"]}},
            }
        ],
        "ads": [
            {
                "name": "Ad 1",
                "line_item_name": "Main",
                "creative": {"name": "c1", "existing_post_urn": "urn:li:share:1"},
            }
        ],
    }


def test_single_builds_one_platform_plan() -> None:
    plan = CampaignPlan.single("linkedin", _campaign())
    assert plan.name == "Q3 Demand Gen"
    assert len(plan.platforms) == 1
    assert plan.platforms[0].platform == "linkedin"
    assert plan.platforms[0].campaign.objective == "awareness"


def test_plan_issues_empty_for_complete_single_platform() -> None:
    plan = {"name": "c", "platforms": [{"platform": "linkedin", "campaign": _campaign()}]}
    assert plan_issues(plan) == []


def test_plan_issues_unprefixed_for_single_platform() -> None:
    # A single-platform plan reports the same messages as campaign_issues — no prefix.
    bad = _campaign()
    bad["ads"] = []
    plan = {"name": "c", "platforms": [{"platform": "linkedin", "campaign": bad}]}
    assert plan_issues(plan) == campaign_issues(bad)


def test_plan_issues_prefixes_each_platform_when_multiple() -> None:
    bad = _campaign()
    bad["ads"] = []
    plan = {
        "name": "c",
        "platforms": [
            {"platform": "linkedin", "campaign": bad},
            {"platform": "meta", "campaign": _campaign()},
        ],
    }
    issues = plan_issues(plan)
    assert any(i.startswith("[linkedin]") for i in issues)
    assert not any(i.startswith("[meta]") for i in issues)  # meta campaign is complete


def test_plan_issues_flags_empty_plan() -> None:
    assert plan_issues({"name": "c", "platforms": []})
