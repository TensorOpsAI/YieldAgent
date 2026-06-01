"""Tests for the LinkedIn payload mapper."""

from __future__ import annotations

from datetime import date

from yieldagent.domain import Flight
from yieldagent.integrations.linkedin.mapping import (
    campaign_run_schedule,
    flight_to_run_schedule,
)


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
