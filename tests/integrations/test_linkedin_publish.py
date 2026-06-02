"""Tests for the publish_draft_campaign orchestration.

The focus here is the creative-backing-post branch: an ad may reference a
hand-published post via `existing_post_urn` (no posting permission needed), or
let the server mint a Direct Sponsored Content "dark" post. These pin which
path each ad takes without standing up a real MCP server or hitting LinkedIn.
"""

from __future__ import annotations

from datetime import date

import pytest

from yieldagent.domain import (
    Audience,
    Campaign,
    CreativeAsset,
    Flight,
    LineItem,
    Money,
    Objective,
    Targeting,
)
from yieldagent.domain.campaign import Ad
from yieldagent.integrations.linkedin import server as srv
from yieldagent.integrations.linkedin.config import LinkedInConfig

_AD_ACCOUNT_ID = "537690018"
_ORG_URN = "urn:li:organization:80050982"


def _config() -> LinkedInConfig:
    return LinkedInConfig(
        access_token="t",
        ad_account_id=_AD_ACCOUNT_ID,
        api_version="202605",
        allow_live=True,
        organization_urn=_ORG_URN,
    )


class _FakeClient:
    """Records create_post / create_creative calls; returns plausible ids."""

    def __init__(self, config: LinkedInConfig):
        self.config = config
        self.create_post_calls: list[dict] = []
        self.create_creative_calls: list[dict] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    def assert_account_allowed(self) -> None:
        pass

    async def get_ad_account(self) -> dict:
        return {"reference": _ORG_URN}

    async def create_campaign_group(self, **_kw) -> dict:
        return {"id": "111"}

    async def create_campaign(self, **_kw) -> dict:
        return {"id": "222"}

    async def create_post(self, **kw) -> dict:
        self.create_post_calls.append(kw)
        return {"id": "urn:li:share:MINTED"}

    async def create_creative(self, **kw) -> dict:
        self.create_creative_calls.append(kw)
        return {"id": "333"}


@pytest.fixture
def patched(monkeypatch):
    captured: dict[str, _FakeClient] = {}

    def _factory(config: LinkedInConfig) -> _FakeClient:
        client = _FakeClient(config)
        captured["client"] = client
        return client

    monkeypatch.setattr(srv, "LinkedInClient", _factory)
    monkeypatch.setattr(srv.LinkedInConfig, "from_env", classmethod(lambda cls: _config()))
    return captured


def _campaign(*creatives: CreativeAsset) -> dict:
    line_item = LineItem(
        name="LI-1",
        budget=Money(amount=100, currency="EUR"),
        flight=Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)),
        targeting=Targeting(audience=Audience(description="engineers", geos=["US"])),
    )
    ads = [
        Ad(name=c.name, line_item_name="LI-1", creative=c) for c in creatives
    ]
    return Campaign(
        name="C",
        objective=Objective.traffic,
        line_items=[line_item],
        ads=ads,
    ).model_dump(mode="json")


async def test_existing_post_urn_skips_create_post(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="reuse", existing_post_urn="urn:li:share:HANDMADE")
    )
    result = await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert client.create_post_calls == []
    assert len(client.create_creative_calls) == 1
    assert client.create_creative_calls[0]["content"] == {"reference": "urn:li:share:HANDMADE"}
    assert result["ads"][0]["post_urn"] == "urn:li:share:HANDMADE"


async def test_missing_post_urn_mints_dark_post(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="fresh", landing_url="https://example.com")
    )
    await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert len(client.create_post_calls) == 1
    assert client.create_creative_calls[0]["content"] == {"reference": "urn:li:share:MINTED"}


async def test_mixed_ads_only_mint_for_missing_urn(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="reuse", existing_post_urn="urn:li:share:HANDMADE"),
        CreativeAsset(name="fresh", landing_url="https://example.com"),
    )
    await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert len(client.create_post_calls) == 1
    refs = {c["content"]["reference"] for c in client.create_creative_calls}
    assert refs == {"urn:li:share:HANDMADE", "urn:li:share:MINTED"}
