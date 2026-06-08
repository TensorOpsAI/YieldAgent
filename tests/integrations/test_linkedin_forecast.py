"""Tests for the ad-supply forecast response parser.

The query building hits the live API (covered by the probe scripts); the parsing
of LinkedIn's verbose elements[] into flight-total ranges is the bug-prone part,
so it is pinned here against a realistic sample.
"""

from __future__ import annotations

from yieldagent.integrations.linkedin.client import _parse_forecast


def _range(metric: str, granularity: str, low: float, high: float) -> dict:
    return {
        "metricType": metric,
        "granularity": granularity,
        "timeSeries": [{"adForecastRange": {"lowEnd": low, "highEnd": high}, "value": high}],
    }


def test_parse_forecast_reduces_to_custom_window_and_derives_cpm_ctr() -> None:
    data = {
        "elements": [
            # A non-CUSTOM window must be ignored in favour of the CUSTOM total.
            _range("IMPRESSION", "DAILY", 1, 2),
            _range("IMPRESSION", "CUSTOM", 8700, 35000),
            _range("CLICK", "CUSTOM", 69, 280),
            _range("SPENDING", "CUSTOM", 82, 199),
            _range("COST_PER_MILLION_IMPRESSIONS", "CUSTOM", 8010, 9410),
            _range("CLICK_PER_MILLION_IMPRESSIONS", "CUSTOM", 5500, 8400),
        ]
    }
    out = _parse_forecast(data, {"amount": "200", "currencyCode": "EUR"})

    assert out["impressions"] == {"low": 8700, "high": 35000}
    assert out["clicks"] == {"low": 69, "high": 280}
    assert out["spend"] == {"low": 82.0, "high": 199.0, "currency": "EUR"}
    # cost-per-million / 1000 = cost per 1,000 impressions (CPM)
    assert out["cpm"] == {"low": 8.01, "high": 9.41, "currency": "EUR"}
    # clicks-per-million / 1e6 * 100 = CTR percent
    assert out["ctr"] == {"low": 0.55, "high": 0.84}


def test_parse_forecast_empty_is_empty() -> None:
    assert _parse_forecast({"elements": []}, {}) == {}
    assert _parse_forecast({}, {"currencyCode": "USD"}) == {}


def test_parse_forecast_includes_only_present_metrics() -> None:
    data = {"elements": [_range("SPENDING", "CUSTOM", 10, 50)]}
    out = _parse_forecast(data, {"currencyCode": "GBP"})
    assert set(out) == {"spend"}
    assert out["spend"]["currency"] == "GBP"
