"""Tests for `quote_budget_floor` — the live LinkedIn per-plan budget floor.

The hardcoded `_MIN_DAILY_BUDGET` table is a fallback only; the real floor
comes from LinkedIn's `adBudgetPricing` finder, which varies by
(account, objective, audience, bidding). These tests cover the live path, the
parse, and the fallback when the API misbehaves.
"""

from __future__ import annotations

from typing import Any

from yieldagent.integrations.linkedin.diagnostics import (
    fallback_floor,
    quote_budget_floor,
)


class _LiveClient:
    """Returns a canned adBudgetPricing payload — the common response shape."""

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


async def test_quote_parses_live_floor_from_elements() -> None:
    payload = {
        "elements": [
            {
                "dailyBudgetLimits": {
                    "min": {"amount": "10.40", "currencyCode": "EUR"},
                },
                "lifetimeBudgetLimits": {
                    "min": {"amount": "150.00", "currencyCode": "EUR"},
                },
            }
        ]
    }
    client = _LiveClient(payload)
    result = await quote_budget_floor(
        client,
        objective="awareness",
        currency="EUR",
    )
    assert result["source"] == "live"
    assert result["min_daily"] == {"amount": "10.40", "currency": "EUR"}
    assert result["min_total"] == {"amount": "150.00", "currency": "EUR"}


async def test_quote_trusts_live_quote_even_when_below_table() -> None:
    # The live quote is authoritative — that is the whole point of asking. If
    # LinkedIn returns a smaller floor than our conservative table, we trust it.
    payload = {
        "dailyBudgetLimits": {"min": {"amount": "8.00", "currencyCode": "EUR"}},
    }
    result = await quote_budget_floor(_LiveClient(payload), objective="awareness", currency="EUR")
    assert result["source"] == "live"
    assert result["min_daily"] == {"amount": "8.00", "currency": "EUR"}


async def test_quote_falls_back_when_objective_is_unknown() -> None:
    # No objective → cannot ask LinkedIn for a per-plan quote; return fallback.
    result = await quote_budget_floor(_LiveClient({}), objective=None, currency="EUR")
    assert result["source"] == "fallback"
    assert result["min_daily"] == {"amount": "11", "currency": "EUR"}


async def test_quote_falls_back_when_api_raises() -> None:
    result = await quote_budget_floor(_BrokenClient(), objective="awareness", currency="EUR")
    assert result["source"] == "fallback"
    assert result["min_daily"]["amount"] == "11"


async def test_quote_falls_back_when_response_shape_is_unparseable() -> None:
    # Empty payload — no recognized fields. Caller should still get a usable answer.
    result = await quote_budget_floor(_LiveClient({}), objective="awareness", currency="EUR")
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
