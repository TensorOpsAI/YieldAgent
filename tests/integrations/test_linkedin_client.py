"""Tests for the LinkedIn Marketing API client.

These pin the endpoint paths the client uses for writes. LinkedIn deprecated
the global write endpoints (`/adCampaignGroups`, `/adCampaigns`, `/creatives`)
in favour of account-scoped ones (`/adAccounts/{id}/...`). The old endpoints
return 400 with an explicit migration message — see
`docs/claude_docs/linkedin_campaign_manager_api_debug_prompt.md`.

The tests intercept HTTP at the transport layer (no network), assert the
exact path each method posts to, and confirm the payload shape stays intact.
"""

from __future__ import annotations

import httpx
import pytest

from yieldagent.integrations.linkedin.client import LinkedInClient
from yieldagent.integrations.linkedin.config import LinkedInConfig

_AD_ACCOUNT_ID = "537690018"


def _make_config() -> LinkedInConfig:
    return LinkedInConfig(
        access_token="test-token",
        ad_account_id=_AD_ACCOUNT_ID,
        api_version="202605",
        allow_live=False,
        allowed_accounts=frozenset({_AD_ACCOUNT_ID}),
    )


class _Recorder:
    """Collects every outbound httpx request so tests can assert on the URL."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # LinkedIn returns 201 with the new id in this header for write endpoints.
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:sponsoredCampaignGroup:123"},
        )


@pytest.fixture
def recorded_client():
    recorder = _Recorder()
    transport = httpx.MockTransport(recorder.handler)
    http = httpx.AsyncClient(transport=transport, timeout=5.0)
    client = LinkedInClient(_make_config(), http=http)
    yield client, recorder


async def test_create_campaign_group_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_campaign_group(
        name="smoke",
        total_budget={"amount": "10", "currencyCode": "EUR"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaignGroups"


async def test_create_campaign_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_campaign(
        campaign_group_urn="urn:li:sponsoredCampaignGroup:1",
        name="smoke",
        objective_type="WEBSITE_VISITS",
        campaign_type="SPONSORED_UPDATES",
        total_budget={"amount": "10", "currencyCode": "EUR"},
        run_schedule={"start": 1, "end": 2},
        targeting_criteria={"include": {"and": []}},
        locale={"country": "US", "language": "en"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaigns"


async def test_create_creative_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_creative(
        campaign_urn="urn:li:sponsoredCampaign:1",
        content={"reference": "urn:li:share:1"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/creatives"


async def test_get_ad_account_path_unchanged(recorded_client) -> None:
    """Reads were already account-scoped — make sure we don't accidentally regress."""
    client, recorder = recorded_client
    await client.get_ad_account()
    assert recorder.requests[0].url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}"


async def test_list_campaigns_uses_account_scoped_path_with_search(recorded_client) -> None:
    """New helper for the read path used in smoke testing."""
    client, recorder = recorded_client
    await client.list_campaigns()
    request = recorder.requests[0]
    assert request.method == "GET"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaigns"
    assert request.url.params.get("q") == "search"


async def test_required_headers_present(recorded_client) -> None:
    """All writes must include the LinkedIn-Version + restli protocol headers."""
    client, recorder = recorded_client
    await client.create_campaign_group(name="smoke")
    request = recorder.requests[0]
    # Headers are case-insensitive in httpx.
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["linkedin-version"] == "202605"
    assert request.headers["x-restli-protocol-version"] == "2.0.0"
