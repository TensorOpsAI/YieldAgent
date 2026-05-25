"""Tests for the read-only Ad Analytics client methods."""

from __future__ import annotations

from datetime import date

import pytest

from .conftest import json_response


async def test_get_ad_analytics_builds_rest_li_url(make_client):
    client, session = make_client(
        lambda req: json_response(
            {
                "elements": [
                    {
                        "clicks": 177,
                        "impressions": 54494,
                        "costInLocalCurrency": "12.34",
                        "pivotValues": ["urn:li:sponsoredCampaign:1234567"],
                    }
                ],
                "paging": {"count": 10, "start": 0, "links": []},
            }
        )
    )

    async with client:
        result = await client.get_ad_analytics(
            pivot="CAMPAIGN",
            date_start=date(2024, 1, 1),
            date_end=date(2024, 1, 31),
            time_granularity="DAILY",
            campaign_urns=["urn:li:sponsoredCampaign:1234567"],
            fields=["impressions", "clicks", "costInLocalCurrency"],
        )

    assert result["elements"][0]["impressions"] == 54494

    req = session.last
    assert req.method == "GET"
    assert req.path == "/rest/adAnalytics"
    assert req.params["q"] == "analytics"
    assert req.params["pivot"] == "CAMPAIGN"
    assert req.params["timeGranularity"] == "DAILY"
    # dateRange uses Rest.li object syntax; the literal must be present verbatim
    # in the (decoded) query value so LinkedIn can parse it.
    assert (
        req.params["dateRange"]
        == "(start:(year:2024,month:1,day:1),end:(year:2024,month:1,day:31))"
    )
    assert (
        req.params["campaigns"] == "List(urn:li:sponsoredCampaign:1234567)"
    )
    assert req.params["fields"] == "impressions,clicks,costInLocalCurrency"
    # Standard LinkedIn headers must travel.
    assert req.headers["authorization"] == "Bearer tok-test"
    assert req.headers["linkedin-version"] == "202605"
    assert req.headers["x-restli-protocol-version"] == "2.0.0"


async def test_get_ad_analytics_open_range_omits_end(make_client):
    client, session = make_client(lambda req: json_response({"elements": []}))
    async with client:
        await client.get_ad_analytics(
            pivot="CREATIVE",
            date_start=date(2025, 6, 1),
            campaign_urns=["urn:li:sponsoredCampaign:1"],
        )
    assert session.last.params["dateRange"] == "(start:(year:2025,month:6,day:1))"


async def test_get_ad_analytics_requires_scope(make_client):
    client, _session = make_client(lambda req: json_response({}))
    async with client:
        with pytest.raises(ValueError, match="at least one of"):
            await client.get_ad_analytics(
                pivot="CAMPAIGN",
                date_start=date(2025, 1, 1),
            )


async def test_get_ad_statistics_supports_multi_pivot(make_client):
    client, session = make_client(lambda req: json_response({"elements": []}))
    async with client:
        await client.get_ad_statistics(
            pivots=["CAMPAIGN", "MEMBER_COMPANY_SIZE"],
            date_start=date(2025, 5, 1),
            date_end=date(2025, 5, 31),
            account_urns=["urn:li:sponsoredAccount:500001"],
            fields=["impressions", "clicks"],
        )

    assert session.last.params["q"] == "statistics"
    assert session.last.params["pivots"] == "List(CAMPAIGN,MEMBER_COMPANY_SIZE)"
    assert (
        session.last.params["accounts"]
        == "List(urn:li:sponsoredAccount:500001)"
    )


async def test_get_ad_statistics_rejects_too_many_pivots(make_client):
    client, _session = make_client(lambda req: json_response({}))
    async with client:
        with pytest.raises(ValueError, match="at most 3"):
            await client.get_ad_statistics(
                pivots=["CAMPAIGN", "CREATIVE", "ACCOUNT", "COMPANY"],
                date_start=date(2025, 1, 1),
                campaign_urns=["urn:li:sponsoredCampaign:1"],
            )


async def test_get_ad_analytics_propagates_400(make_client):
    import httpx

    client, _session = make_client(
        lambda req: httpx.Response(
            400,
            json={
                "serviceErrorCode": 100,
                "message": "MISSING_FIELD",
                "status": 400,
            },
        )
    )
    async with client:
        from yieldagent.integrations.linkedin.client import LinkedInError

        with pytest.raises(LinkedInError) as exc_info:
            await client.get_ad_analytics(
                pivot="CAMPAIGN",
                date_start=date(2025, 1, 1),
                campaign_urns=["urn:li:sponsoredCampaign:1"],
            )
        assert exc_info.value.status_code == 400
