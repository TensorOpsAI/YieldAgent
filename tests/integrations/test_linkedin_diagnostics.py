"""Tests for the two-layer campaign validation: pre-flight + error translation."""

from __future__ import annotations

from datetime import date

from yieldagent.domain import Campaign
from yieldagent.integrations.linkedin.client import LinkedInError
from yieldagent.integrations.linkedin.diagnostics import (
    AUDIENCE_MIN_SIZE,
    CampaignValidationError,
    describe_constraints,
    explain_linkedin_error,
    preflight_problems,
)

TODAY = date(2026, 6, 8)


class _FakeClient:
    """Stands in for LinkedInClient.get_ad_account — no network."""

    def __init__(self, currency: str = "EUR") -> None:
        self._currency = currency

    async def get_ad_account(self) -> dict:
        return {"currency": self._currency}


def _campaign(amount: str = "100", currency: str = "EUR", start: str = "2026-06-09") -> Campaign:
    return Campaign.model_validate(
        {
            "name": "c",
            "objective": "awareness",
            "line_items": [
                {
                    "name": "li",
                    "budget": {"amount": amount, "currency": currency},
                    "flight": {"start_date": start, "end_date": "2026-06-23"},
                    "targeting": {"audience": {"description": "x", "geos": ["PT"]}},
                }
            ],
            "ads": [],
        }
    )


async def _problems(campaign: Campaign, currency: str = "EUR") -> list[dict]:
    return await preflight_problems(_FakeClient(currency), campaign, today=TODAY)


async def test_preflight_passes_a_valid_campaign() -> None:
    assert await _problems(_campaign()) == []


async def test_preflight_flags_budget_below_minimum() -> None:
    problems = await _problems(_campaign(amount="50"))
    assert any(p["field"] == "campaign.budget" for p in problems)


async def test_preflight_flags_currency_mismatch_with_account() -> None:
    problems = await _problems(_campaign(currency="USD"), currency="EUR")
    assert any("does not match" in p["message"] for p in problems)


async def test_preflight_flags_past_flight_dates() -> None:
    problems = await _problems(_campaign(start="2020-01-01"))
    assert any("in the past" in p["message"] for p in problems)


def _campaign_with(**li_extra) -> Campaign:
    return Campaign.model_validate(
        {
            "name": "c",
            "objective": "awareness",
            "line_items": [
                {
                    "name": "li",
                    "budget": {"amount": "100", "currency": "EUR"},
                    "flight": {"start_date": "2026-06-09", "end_date": "2026-06-23"},
                    "targeting": {"audience": {"description": "x", "geos": ["PT"]}},
                    **li_extra,
                }
            ],
            "ads": [],
        }
    )


async def test_preflight_requires_bid_amount_for_manual_bidding() -> None:
    problems = await _problems(_campaign_with(bidding_strategy="manual"))
    assert any(p["field"].endswith("bid_amount") for p in problems)


async def test_preflight_accepts_manual_bidding_with_bid_amount() -> None:
    c = _campaign_with(
        bidding_strategy="manual", bid_amount={"amount": "12", "currency": "EUR"}
    )
    assert await _problems(c) == []


async def test_preflight_flags_daily_budget_below_minimum() -> None:
    problems = await _problems(_campaign_with(daily_budget={"amount": "5", "currency": "EUR"}))
    assert any(p["field"].endswith("daily_budget") for p in problems)


def test_explain_translates_input_errors() -> None:
    err = LinkedInError(
        400,
        {
            "errorDetails": {
                "inputErrors": [
                    {
                        "description": "value 50 cannot be lower than 100.00",
                        "inputPath": {"fieldPath": "/CampaignGroup/totalBudget/amount"},
                        "code": "FIELD_VALUE_TOO_LOW",
                    }
                ]
            }
        },
    )
    problems = explain_linkedin_error(err)
    assert len(problems) == 1
    assert problems[0]["field"] == "CampaignGroup/totalBudget/amount"
    assert "minimum" in problems[0]["fix"]


def test_explain_locale_error_gets_locale_hint() -> None:
    # A locale rejection's fieldPath is /Campaign/targetingCriteria, but the fix
    # hint must still be the locale-specific one, not the generic targeting one.
    err = LinkedInError(
        400,
        {
            "errorDetails": {
                "inputErrors": [
                    {
                        "description": "Interface locale urn:li:locale:en_PT is not supported.",
                        "inputPath": {"fieldPath": "/Campaign/targetingCriteria"},
                        "code": "INVALID_INTERFACE_LOCALE_CODE",
                    }
                ]
            }
        },
    )
    assert "locale" in explain_linkedin_error(err)[0]["fix"].lower()


def test_explain_falls_back_to_top_level_message() -> None:
    problems = explain_linkedin_error(LinkedInError(500, {"message": "Internal Server Error"}))
    assert len(problems) == 1
    assert "500" in problems[0]["message"]


async def test_describe_constraints_reports_account_currency_and_rules() -> None:
    c = await describe_constraints(_FakeClient("EUR"))
    assert c["platform"] == "linkedin"
    assert c["currency"] == "EUR"
    assert c["budget"]["currency_must_match_account"] is True
    assert c["audience"]["min_size"] == AUDIENCE_MIN_SIZE
    assert c["creative"]["reshares_sponsorable"] is False
    assert c["locale"]["auto_selected"] is True
    # Budget reports both a total and a per-day minimum.
    assert c["budget"]["min_daily"] == "10"
    # The field spec lists required and optional fields so the agent can offer them.
    assert "objective" in c["fields"]["required"]
    optional_keys = {f["key"] for f in c["fields"]["optional"]}
    assert {"daily_budget", "bidding_strategy", "audience_network"} <= optional_keys
    # Wired fields are marked settable so the agent knows it can apply them.
    daily = next(f for f in c["fields"]["optional"] if f["key"] == "daily_budget")
    assert daily["status"] == "settable"


def test_campaign_validation_error_summary() -> None:
    exc = CampaignValidationError(
        [{"field": "campaign.budget", "message": "too low", "fix": "raise it"}],
        rolled_back=True,
    )
    assert exc.rolled_back is True
    assert "too low" in str(exc)
