"""Tests for the LinkedIn A/B creative experiment agent."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from yieldagent.agents.linkedin_experiment.graph import (
    ExperimentConfig,
    recommend,
    run_experiment,
    score_elements,
)


@pytest.fixture
def two_day_creative_analytics() -> list[dict[str, Any]]:
    """Two creatives × two days of synthetic data."""
    return [
        # creative A: 2 days, very high CTR
        {
            "pivotValues": ["urn:li:sponsoredCreative:A"],
            "impressions": 600,
            "clicks": 60,
            "costInLocalCurrency": "12.0",
            "externalWebsiteConversions": 4,
            "oneClickLeads": 2,
        },
        {
            "pivotValues": ["urn:li:sponsoredCreative:A"],
            "impressions": 600,
            "clicks": 60,
            "costInLocalCurrency": "12.0",
            "externalWebsiteConversions": 6,
            "oneClickLeads": 3,
        },
        # creative B: 2 days, lower CTR
        {
            "pivotValues": ["urn:li:sponsoredCreative:B"],
            "impressions": 700,
            "clicks": 10,
            "costInLocalCurrency": "8.5",
            "externalWebsiteConversions": 1,
            "oneClickLeads": 1,
        },
        {
            "pivotValues": ["urn:li:sponsoredCreative:B"],
            "impressions": 800,
            "clicks": 14,
            "costInLocalCurrency": "9.5",
            "externalWebsiteConversions": 1,
            "oneClickLeads": 0,
        },
    ]


def test_score_elements_aggregates_and_ranks_by_ctr(two_day_creative_analytics):
    scores = score_elements(
        two_day_creative_analytics,
        primary_metric="ctr",
        min_impressions=1000,
    )
    assert len(scores) == 2
    # A: 1200 impressions, 120 clicks → CTR 0.1
    # B: 1500 impressions, 24 clicks → CTR 0.016
    assert scores[0].creative_urn == "urn:li:sponsoredCreative:A"
    assert scores[0].impressions == 1200
    assert scores[0].clicks == 120
    assert scores[0].ctr == pytest.approx(0.1)
    assert scores[0].sufficient_data is True
    assert scores[1].creative_urn == "urn:li:sponsoredCreative:B"
    assert scores[1].ctr == pytest.approx(24 / 1500)


def test_score_elements_handles_zero_clicks_for_cpc():
    elements = [
        {"pivotValues": ["urn:li:sponsoredCreative:Z"], "impressions": 500, "clicks": 0}
    ]
    scores = score_elements(elements, primary_metric="cpc", min_impressions=100)
    assert scores[0].cpc is None
    assert scores[0].primary_score is None


def test_score_elements_marks_under_threshold_as_insufficient():
    elements = [
        {
            "pivotValues": ["urn:li:sponsoredCreative:X"],
            "impressions": 50,
            "clicks": 2,
            "costInLocalCurrency": "0.5",
        }
    ]
    scores = score_elements(elements, primary_metric="ctr", min_impressions=1000)
    assert scores[0].sufficient_data is False


def test_recommend_picks_winner_and_pauses_rest(two_day_creative_analytics):
    scores = score_elements(
        two_day_creative_analytics,
        primary_metric="ctr",
        min_impressions=1000,
    )
    result = recommend(scores, primary_metric="ctr")
    assert result.primary_metric == "ctr"
    actions = {rec.creative_urn: rec.action for rec in result.recommendations}
    assert actions["urn:li:sponsoredCreative:A"] == "scale"
    assert actions["urn:li:sponsoredCreative:B"] == "pause"


def test_recommend_holds_low_volume_variants_as_needs_data():
    elements = [
        {
            "pivotValues": ["urn:li:sponsoredCreative:A"],
            "impressions": 2000,
            "clicks": 80,
            "costInLocalCurrency": "20.0",
        },
        {
            "pivotValues": ["urn:li:sponsoredCreative:B"],
            "impressions": 100,
            "clicks": 8,
            "costInLocalCurrency": "1.0",
        },
    ]
    scores = score_elements(elements, primary_metric="ctr", min_impressions=1000)
    result = recommend(scores, primary_metric="ctr")
    by_urn = {rec.creative_urn: rec for rec in result.recommendations}
    assert by_urn["urn:li:sponsoredCreative:A"].action == "scale"
    assert by_urn["urn:li:sponsoredCreative:B"].action == "needs_data"
    assert any("below the impressions floor" in note for note in result.notes)


def test_recommend_handles_empty_input():
    result = recommend([], primary_metric="ctr")
    assert result.recommendations == []
    assert any("No analytics rows" in note for note in result.notes)


async def test_run_experiment_drives_the_graph_with_a_fake_fetcher(two_day_creative_analytics):
    captured: dict[str, ExperimentConfig] = {}

    async def fake_fetcher(config: ExperimentConfig) -> list[dict[str, Any]]:
        captured["config"] = config
        return two_day_creative_analytics

    config = ExperimentConfig(
        creative_urns=[
            "urn:li:sponsoredCreative:A",
            "urn:li:sponsoredCreative:B",
        ],
        date_start=date(2026, 5, 1),
        date_end=date(2026, 5, 21),
        primary_metric="ctr",
        min_impressions=1000,
    )
    result = await run_experiment(config, fetcher=fake_fetcher)
    assert captured["config"] is config
    assert result.primary_metric == "ctr"
    # Winner first.
    assert result.recommendations[0].creative_urn == "urn:li:sponsoredCreative:A"
    assert result.recommendations[0].action == "scale"
    # Serializable.
    payload = result.to_dict()
    assert payload["primary_metric"] == "ctr"
    assert len(payload["rankings"]) == 2
