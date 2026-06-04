"""Tests for the conversational campaign completeness checker."""

from __future__ import annotations

from typing import Any

from yieldagent.agents.console.validation import campaign_issues


def _complete() -> dict[str, Any]:
    return {
        "name": "Q3 Demand Gen",
        "objective": "leads",
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


def test_complete_campaign_has_no_issues() -> None:
    assert campaign_issues(_complete()) == []


def test_missing_objective_is_flagged() -> None:
    data = _complete()
    del data["objective"]
    issues = campaign_issues(data)
    assert any("objective" in i for i in issues)


def test_no_line_items_is_flagged() -> None:
    data = _complete()
    data["line_items"] = []
    assert any("line item" in i for i in campaign_issues(data))


def test_ad_referencing_unknown_line_item_is_flagged() -> None:
    data = _complete()
    data["ads"][0]["line_item_name"] = "Nope"
    assert any("unknown line item" in i for i in campaign_issues(data))


def test_creative_without_source_is_flagged() -> None:
    data = _complete()
    data["ads"][0]["creative"] = {"name": "c1"}  # no post urn, no landing url
    assert any("creative source" in i for i in campaign_issues(data))


def test_invalid_budget_is_flagged() -> None:
    data = _complete()
    data["line_items"][0]["budget"]["amount"] = 0  # must be > 0
    assert campaign_issues(data)  # pydantic catches it


def test_budget_over_cap_is_flagged() -> None:
    data = _complete()
    data["line_items"][0]["budget"]["amount"] = 999_999
    assert any("safety cap" in i for i in campaign_issues(data))


def test_budget_cap_is_env_configurable(monkeypatch) -> None:
    monkeypatch.setenv("YIELDAGENT_MAX_BUDGET", "10000")
    data = _complete()
    data["line_items"][0]["budget"]["amount"] = 8000  # under the raised cap
    assert campaign_issues(data) == []
