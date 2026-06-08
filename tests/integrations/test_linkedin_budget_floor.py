"""Tests for `quote_budget_floor` — the live LinkedIn per-plan budget floor.

The hardcoded `_MIN_DAILY_BUDGET` table is a fallback only; the real floor comes
from LinkedIn's `adBudgetPricing` finder, which varies by (account, objective,
audience, bidding). adBudgetPricing requires resolved targeting and returns a
normalized (USD) figure even for a EUR account, so a successful quote is buffered
~10% and relabeled in the plan currency. These tests cover the live path (real
response shape), the buffer, and every fallback.
"""

from __future__ import annotations

from typing import Any

from yieldagent.integrations.linkedin.diagnostics import (
    fallback_floor,
    quote_budget_floor,
)

# Any non-empty criteria dict satisfies the "targeting present" requirement; the
# fake client ignores its contents.
CRITERIA: dict[str, Any] = {"include": {"and": [{"or": {"facet": ["urn:x"]}}]}}


class _LiveClient:
    """Returns a canned adBudgetPricing payload and records the call kwargs."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    async def ad_budget_pricing(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self._payload


class _BrokenClient:
    """Every call raises — exercises the fallback path."""

    async def ad_budget_pricing(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated API error")


# The shape LinkedIn actually returns: an `elements` entry with `dailyBudgetLimits`
# (min/default/max), in USD, and no lifetime limits.
REAL_PAYLOAD: dict[str, Any] = {
    "paging": {"start": 0, "count": 10},
    "elements": [
        {
            "bidLimits": {"min": {"currencyCode": "USD", "amount": "12.0"}},
            "dailyBudgetLimits": {
                "min": {"currencyCode": "USD", "amount": "10.0"},
                "default": {"currencyCode": "USD", "amount": "100.0"},
                "max": {"currencyCode": "USD", "amount": "100000.0"},
            },
        }
    ],
}


async def test_quote_uses_live_floor_and_sends_required_params() -> None:
    client = _LiveClient(REAL_PAYLOAD)
    result = await quote_budget_floor(
        client, objective="awareness", currency="EUR", targeting_criteria=CRITERIA
    )
    assert result["source"] == "live"
    # Raw 10.0 USD -> buffered ceil(10.0 * 1.10) = 11.00, relabeled in the plan currency.
    assert result["min_daily"] == {"amount": "11.00", "currency": "EUR"}
    # The untouched platform quote (real currency) is preserved for transparency.
    assert result["quoted_daily"] == {"amount": "10.0", "currency": "USD"}
    # adBudgetPricing 400s without these, so the call must always send them.
    sent = client.calls[0]
    assert sent["targeting_criteria"] == CRITERIA
    assert sent["objective_type"] == "BRAND_AWARENESS"
    assert sent["optimization_target"] == "MAX_IMPRESSION"
    assert sent["bid_type"] == "CPM"


async def test_quote_buffers_a_eur_quote_above_the_raw_minimum() -> None:
    payload = {"dailyBudgetLimits": {"min": {"amount": "10.40", "currencyCode": "EUR"}}}
    result = await quote_budget_floor(
        _LiveClient(payload), objective="awareness", currency="EUR", targeting_criteria=CRITERIA
    )
    # 10.40 * 1.10 = 11.44; the buffered gate clears the raw 10.40 enforcement.
    assert result["min_daily"] == {"amount": "11.44", "currency": "EUR"}
    assert result["quoted_daily"]["amount"] == "10.40"


async def test_quote_without_targeting_falls_back() -> None:
    # The endpoint requires targetingCriteria; without it we never call (no
    # guaranteed-400 round trip) and return the conservative floor.
    client = _LiveClient(REAL_PAYLOAD)
    result = await quote_budget_floor(client, objective="awareness", currency="EUR")
    assert result["source"] == "fallback"
    assert client.calls == []  # we did not waste an API call


async def test_quote_falls_back_when_objective_is_unknown() -> None:
    result = await quote_budget_floor(
        _LiveClient(REAL_PAYLOAD), objective=None, currency="EUR", targeting_criteria=CRITERIA
    )
    assert result["source"] == "fallback"
    assert result["min_daily"] == {"amount": "11", "currency": "EUR"}


async def test_quote_falls_back_when_api_raises() -> None:
    result = await quote_budget_floor(
        _BrokenClient(), objective="awareness", currency="EUR", targeting_criteria=CRITERIA
    )
    assert result["source"] == "fallback"
    assert result["min_daily"]["amount"] == "11"


async def test_quote_falls_back_when_response_shape_is_unparseable() -> None:
    result = await quote_budget_floor(
        _LiveClient({"elements": [{}]}),
        objective="awareness",
        currency="EUR",
        targeting_criteria=CRITERIA,
    )
    assert result["source"] == "fallback"


def test_fallback_floor_is_conservative_for_known_currencies() -> None:
    for currency in ("EUR", "USD", "GBP"):
        floor = fallback_floor(currency)
        assert floor["source"] == "fallback"
        assert floor["min_daily"]["currency"] == currency
        # The fallback must clear the legacy "10 EUR" rejection comfortably.
        assert int(float(floor["min_daily"]["amount"])) >= 11


def test_fallback_floor_handles_unknown_currency() -> None:
    floor = fallback_floor("CHF")
    assert floor["source"] == "fallback"
    assert floor["min_daily"]["amount"] == "11"
