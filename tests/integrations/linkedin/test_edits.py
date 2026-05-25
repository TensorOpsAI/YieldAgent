"""Tests for read + partial-update campaign methods."""

from __future__ import annotations

import httpx
import pytest

from yieldagent.integrations.linkedin.client import LinkedInError

from .conftest import json_response


async def test_list_campaigns_builds_search_query(make_client):
    client, session = make_client(lambda req: json_response({"elements": []}))
    async with client:
        await client.list_campaigns(
            status_values=["ACTIVE", "PAUSED"],
            type_values=["SPONSORED_UPDATES"],
            page_size=50,
        )
    req = session.last
    assert req.path == "/rest/adAccounts/500001/adCampaigns"
    assert req.params["q"] == "search"
    assert req.params["pageSize"] == "50"
    assert req.params["sortOrder"] == "DESCENDING"
    # search expression must contain both filter clauses (order of insertion).
    assert req.params["search"] == (
        "(status:(values:List(ACTIVE,PAUSED)),type:(values:List(SPONSORED_UPDATES)))"
    )


async def test_list_campaigns_passes_page_token(make_client):
    client, session = make_client(lambda req: json_response({"elements": []}))
    async with client:
        await client.list_campaigns(page_token="tok-abc")
    assert session.last.params["pageToken"] == "tok-abc"


async def test_get_campaign_uses_account_scoped_path(make_client):
    client, session = make_client(
        lambda req: json_response({"id": 42, "status": "ACTIVE"})
    )
    async with client:
        result = await client.get_campaign("42")
    assert result["id"] == 42
    assert session.last.path == "/rest/adAccounts/500001/adCampaigns/42"


async def test_patch_campaign_dry_run_returns_preview_no_http(make_client):
    client, session = make_client(
        lambda req: pytest.fail("dry run must not hit LinkedIn")  # type: ignore[misc]
    )
    async with client:
        preview = await client.patch_campaign(
            "777",
            set_fields={"status": "PAUSED"},
        )
    assert preview["dry_run"] is True
    assert preview["method"] == "POST"
    assert preview["endpoint"] == "/adAccounts/500001/adCampaigns/777"
    assert preview["headers"] == {"X-RestLi-Method": "PARTIAL_UPDATE"}
    assert preview["body"] == {"patch": {"$set": {"status": "PAUSED"}}}
    assert session.requests == []


async def test_patch_campaign_confirm_true_issues_partial_update(make_client):
    client, session = make_client(lambda req: httpx.Response(204))
    async with client:
        result = await client.patch_campaign(
            "777",
            set_fields={"status": "PAUSED"},
            confirm=True,
        )
    req = session.last
    assert req.method == "POST"
    assert req.path == "/rest/adAccounts/500001/adCampaigns/777"
    assert req.headers["x-restli-method"] == "PARTIAL_UPDATE"
    import json as _json

    body = _json.loads(req.body)
    assert body == {"patch": {"$set": {"status": "PAUSED"}}}
    assert result["applied"] is True


async def test_patch_campaign_refuses_completed_status(make_client):
    client, _session = make_client(lambda req: json_response({}))
    async with client:
        with pytest.raises(LinkedInError) as exc_info:
            await client.patch_campaign("1", set_fields={"status": "COMPLETED"}, confirm=True)
        assert exc_info.value.status_code == 400
        assert "COMPLETED" in str(exc_info.value)


async def test_update_campaign_budget_serializes_money(make_client):
    client, session = make_client(lambda req: httpx.Response(204))
    async with client:
        await client.update_campaign_budget(
            "11",
            daily_budget={"amount": "30.0", "currencyCode": "USD"},
            total_budget={"amount": "300.0", "currencyCode": "USD"},
            confirm=True,
        )
    import json as _json

    body = _json.loads(session.last.body)
    assert body == {
        "patch": {
            "$set": {
                "dailyBudget": {"amount": "30.0", "currencyCode": "USD"},
                "totalBudget": {"amount": "300.0", "currencyCode": "USD"},
            }
        }
    }


async def test_update_campaign_budget_clear_total_uses_delete(make_client):
    client, session = make_client(lambda req: httpx.Response(204))
    async with client:
        await client.update_campaign_budget(
            "11",
            daily_budget={"amount": "30.0", "currencyCode": "USD"},
            clear_total_budget=True,
            confirm=True,
        )
    import json as _json

    body = _json.loads(session.last.body)
    assert body["patch"]["$delete"] == ["totalBudget"]
    assert body["patch"]["$set"] == {
        "dailyBudget": {"amount": "30.0", "currencyCode": "USD"}
    }


async def test_update_campaign_schedule_only_end(make_client):
    client, session = make_client(lambda req: httpx.Response(204))
    async with client:
        await client.update_campaign_schedule("11", end_epoch_ms=9876543210000, confirm=True)
    import json as _json

    body = _json.loads(session.last.body)
    assert body == {"patch": {"$set": {"runSchedule": {"end": 9876543210000}}}}


async def test_update_campaign_schedule_requires_an_arg(make_client):
    client, _session = make_client(lambda req: json_response({}))
    async with client:
        with pytest.raises(ValueError, match="start_epoch_ms or end_epoch_ms"):
            await client.update_campaign_schedule("11")
