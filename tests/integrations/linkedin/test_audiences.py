"""Tests for DMP-segment / matched-audience client methods."""

from __future__ import annotations

import json

import httpx
import pytest

from yieldagent.integrations.linkedin.client import LinkedInError
from yieldagent.integrations.linkedin.mapping import hash_email_for_dmp

from .conftest import json_response


def test_hash_email_for_dmp_lowercases_and_trims():
    expected = (
        "fa922cb41ff930664d4c9ced3c472ce7ecf29a0f8248b7018456e990177fff75"
    )
    assert hash_email_for_dmp("abc@test.com") == expected
    assert hash_email_for_dmp(" ABC@Test.com ") == expected


async def test_create_dmp_segment_posts_account_scoped_payload(make_client):
    client, session = make_client(lambda req: json_response({}, status=201, headers={"x-restli-id": "987"}))
    async with client:
        result = await client.create_dmp_segment(name="ABM tier 1")
    assert result["id"] == "987"
    req = session.last
    assert req.method == "POST"
    assert req.path == "/rest/dmpSegments"
    body = json.loads(req.body)
    assert body == {
        "account": "urn:li:sponsoredAccount:500001",
        "destinations": [{"destination": "LINKEDIN"}],
        "name": "ABM tier 1",
        "sourcePlatform": "LIST_UPLOAD",
        "type": "COMPANY_LIST_UPLOAD",
    }


async def test_generate_dmp_upload_url_returns_value(make_client):
    client, session = make_client(
        lambda req: json_response({"value": "https://www.linkedin.com/ambry/?x-li-ambry-ep=AQ..."})
    )
    async with client:
        url = await client.generate_dmp_upload_url()
    # The action= goes in the path, not the query — verify it survived.
    assert "action=generateUploadUrl" in session.last.full_url
    assert url["value"].startswith("https://www.linkedin.com/ambry/")


async def test_upload_dmp_csv_returns_media_urn_from_location(make_client):
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(
            201,
            headers={"location": "/AAYAAwEvAAQAAQAAAAAAAAv-R5Tyj8t6.csv"},
        )

    client, _session = make_client(handler)
    async with client:
        urn = await client.upload_dmp_csv(
            "https://www.linkedin.com/ambry/?x-li-ambry-ep=XYZ",
            b"companyname\nMicrosoft\n",
        )
    assert urn == "urn:li:media:/AAYAAwEvAAQAAQAAAAAAAAv-R5Tyj8t6.csv"
    request = captured["req"]
    assert request.method == "POST"
    assert "linkedin.com/ambry" in str(request.url)
    assert request.content == b"companyname\nMicrosoft\n"
    assert request.headers["content-type"] == "text/csv"
    assert request.headers["authorization"] == "Bearer tok-test"


async def test_upload_dmp_csv_raises_without_location(make_client):
    client, _session = make_client(lambda req: httpx.Response(201))
    async with client:
        with pytest.raises(LinkedInError) as exc:
            await client.upload_dmp_csv("https://www.linkedin.com/ambry/", b"x")
    assert exc.value.status_code == 502


async def test_attach_dmp_list_posts_inputFile(make_client):
    client, session = make_client(lambda req: json_response({}, status=201, headers={"x-restli-id": "52105"}))
    async with client:
        result = await client.attach_dmp_list("22685", "urn:li:media:/AAYA.csv")
    assert result["id"] == "52105"
    body = json.loads(session.last.body)
    assert body == {"inputFile": "urn:li:media:/AAYA.csv"}
    assert session.last.path == "/rest/dmpSegments/22685/listUploads"


async def test_add_dmp_users_builds_streaming_payload(make_client):
    client, session = make_client(lambda req: httpx.Response(204))
    async with client:
        await client.add_dmp_users(
            "1001",
            hashed_emails=[
                "fa922cb41ff930664d4c9ced3c472ce7ecf29a0f8248b7018456e990177fff75"
            ],
            google_aids=["GA-1"],
            action="ADD",
        )
    body = json.loads(session.last.body)
    assert body == {
        "elements": [
            {
                "action": "ADD",
                "userIds": [
                    {
                        "idType": "SHA256_EMAIL",
                        "idValue": "fa922cb41ff930664d4c9ced3c472ce7ecf29a0f8248b7018456e990177fff75",
                    },
                    {"idType": "GOOGLE_AID", "idValue": "GA-1"},
                ],
            }
        ]
    }


async def test_add_dmp_users_rejects_empty_input(make_client):
    client, _session = make_client(lambda req: httpx.Response(204))
    async with client:
        with pytest.raises(ValueError):
            await client.add_dmp_users("1001")


async def test_get_dmp_segment_returns_status(make_client):
    client, session = make_client(
        lambda req: json_response(
            {
                "id": 22685,
                "destinations": [
                    {
                        "destinationSegmentId": "urn:li:adSegment:164005",
                        "status": "READY",
                        "audienceSize": 5900,
                    }
                ],
            }
        )
    )
    async with client:
        seg = await client.get_dmp_segment("22685")
    assert seg["destinations"][0]["status"] == "READY"
    assert session.last.path == "/rest/dmpSegments/22685"
