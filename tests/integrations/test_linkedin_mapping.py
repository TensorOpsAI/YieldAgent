"""Tests for the LinkedIn payload mapper."""

from __future__ import annotations

from datetime import date

from yieldagent.domain import (
    Audience,
    BiddingStrategy,
    CreativeAsset,
    Flight,
    LineItem,
    Money,
    Targeting,
)
from yieldagent.integrations.linkedin.mapping import (
    campaign_bidding,
    campaign_run_schedule,
    creative_content_reference,
    flight_to_run_schedule,
    line_item_locale,
    post_article_content,
)


def _line_item(**overrides) -> LineItem:
    base = {
        "name": "li",
        "budget": Money(amount="100", currency="EUR"),
        "flight": Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 15)),
        "targeting": Targeting(audience=Audience(description="x", geos=["PT"])),
    }
    base.update(overrides)
    return LineItem(**base)


def test_campaign_bidding_maximum_delivery_is_auto_cpm() -> None:
    out = campaign_bidding(_line_item(), "BRAND_AWARENESS")
    assert out["cost_type"] == "CPM"
    assert out["optimization_target_type"] == "MAX_IMPRESSION"
    assert out["unit_cost"] is None


def test_campaign_bidding_manual_sets_unit_cost_and_no_target() -> None:
    li = _line_item(
        bidding_strategy=BiddingStrategy.manual,
        bid_amount=Money(amount="12", currency="EUR"),
    )
    out = campaign_bidding(li, "BRAND_AWARENESS")
    assert out["cost_type"] == "CPC"
    assert out["optimization_target_type"] is None
    assert out["unit_cost"] == {"amount": "12", "currencyCode": "EUR"}


def test_campaign_bidding_cost_cap_keeps_target_and_carries_cap() -> None:
    li = _line_item(
        bidding_strategy=BiddingStrategy.cost_cap,
        bid_amount=Money(amount="8", currency="EUR"),
    )
    out = campaign_bidding(li, "WEBSITE_VISITS")
    assert out["cost_type"] == "CPM"
    assert out["optimization_target_type"] == "MAX_CLICK"
    assert out["unit_cost"] == {"amount": "8", "currencyCode": "EUR"}


def test_campaign_bidding_respects_optimization_goal_override() -> None:
    li = _line_item(optimization_goal="MAX_REACH")
    out = campaign_bidding(li, "BRAND_AWARENESS")
    assert out["optimization_target_type"] == "MAX_REACH"


def test_flight_to_run_schedule_emits_epoch_millis() -> None:
    flight = Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
    out = flight_to_run_schedule(flight)
    # Values are epoch milliseconds; start should be 13-digit, end strictly later.
    assert out["start"] > 1_000_000_000_000
    assert out["end"] > out["start"]
    # 31-day flight: end - start is roughly 31 days in ms, within 1 day tolerance.
    span_days = (out["end"] - out["start"]) / 1000 / 86400
    assert 30 < span_days < 32


def test_campaign_run_schedule_spans_earliest_start_to_latest_end() -> None:
    """LinkedIn Campaign Group's runSchedule must cover all child Campaigns."""
    flights = [
        Flight(start_date=date(2026, 7, 6), end_date=date(2026, 8, 31)),
        Flight(start_date=date(2026, 6, 15), end_date=date(2026, 7, 15)),
        Flight(start_date=date(2026, 8, 1), end_date=date(2026, 9, 30)),
    ]
    out = campaign_run_schedule(flights)
    # earliest start = 2026-06-15
    earliest = flight_to_run_schedule(
        Flight(start_date=date(2026, 6, 15), end_date=date(2026, 6, 15))
    )
    assert out["start"] == earliest["start"]
    # latest end = 2026-09-30
    latest = flight_to_run_schedule(
        Flight(start_date=date(2026, 9, 30), end_date=date(2026, 9, 30))
    )
    assert out["end"] == latest["end"]


def test_campaign_run_schedule_single_flight_is_passthrough() -> None:
    flight = Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
    out = campaign_run_schedule([flight])
    assert out == flight_to_run_schedule(flight)


def test_post_article_content_maps_landing_headline_description() -> None:
    creative = CreativeAsset(
        name="Engineering-leader story",
        headline="We replaced our warehouse in 30 days.",
        primary_text="How Northwind migrated to Lattice Cloud.",
        description="A migration story.",
        landing_url="https://lattice.example/cloud",
    )
    article = post_article_content(creative)
    assert article["source"] == "https://lattice.example/cloud"
    assert article["title"] == "We replaced our warehouse in 30 days."
    assert article["description"] == "A migration story."
    # image_url is a plain URL, not an urn:li:image — thumbnail needs the Images
    # API, so it must NOT be set here.
    assert "thumbnail" not in article


def test_post_article_content_defaults_source_when_no_landing_url() -> None:
    article = post_article_content(CreativeAsset(name="x"))
    assert article["source"].startswith("http")


def test_creative_content_reference_wraps_post_urn() -> None:
    assert creative_content_reference("urn:li:share:123") == {"reference": "urn:li:share:123"}


def test_line_item_locale_strips_and_uppercases_geo() -> None:
    # A padded/lowercase code for a supported country must still resolve to its
    # locale (e.g. Germany -> de_DE), not fall back to US.
    locale = line_item_locale(Audience(description="x", geos=["de "]))
    assert locale == {"country": "DE", "language": "de"}


def test_line_item_locale_defaults_to_us_for_unknown_code() -> None:
    assert line_item_locale(Audience(description="x", geos=["ZZ"]))["country"] == "US"


def test_line_item_locale_falls_back_when_country_has_no_supported_locale() -> None:
    # Portugal has no LinkedIn-supported interface locale (en_PT is rejected and
    # Portuguese only exists as pt_BR), so it must fall back to en_US.
    assert line_item_locale(Audience(description="x", geos=["PT"])) == {
        "country": "US",
        "language": "en",
    }
