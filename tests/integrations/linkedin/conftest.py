"""Shared fixtures for LinkedIn client tests.

We mock the LinkedIn API via `httpx.MockTransport`, which lets us assert on
the exact request line + headers the client emits without adding `respx` as
a dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from yieldagent.integrations.linkedin.client import LinkedInClient
from yieldagent.integrations.linkedin.config import LinkedInConfig

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class RecordedRequest:
    method: str
    path: str
    full_url: str
    headers: dict[str, str]
    body: bytes
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class MockSession:
    requests: list[RecordedRequest] = field(default_factory=list)

    @property
    def last(self) -> RecordedRequest:
        if not self.requests:
            raise AssertionError("no LinkedIn requests were recorded")
        return self.requests[-1]


def _record(session: MockSession, request: httpx.Request) -> None:
    session.requests.append(
        RecordedRequest(
            method=request.method,
            path=request.url.path,
            full_url=str(request.url),
            headers=dict(request.headers),
            body=request.content,
            params={k: v for k, v in request.url.params.multi_items()},
        )
    )


@pytest.fixture
def linkedin_config() -> LinkedInConfig:
    return LinkedInConfig(
        access_token="tok-test",
        ad_account_id="500001",
        api_version="202605",
        allow_live=False,
        allowed_accounts=frozenset({"500001"}),
    )


@pytest.fixture
def make_client(linkedin_config: LinkedInConfig):
    """Return a builder that wires a LinkedInClient to a mock transport.

    Usage::

        client, session = make_client(handler)

    where `handler(request) -> httpx.Response` lets the test decide what
    LinkedIn would reply.
    """

    def _build(handler: Handler) -> tuple[LinkedInClient, MockSession]:
        session = MockSession()

        def transport_handler(request: httpx.Request) -> httpx.Response:
            _record(session, request)
            return handler(request)

        transport = httpx.MockTransport(transport_handler)
        http = httpx.AsyncClient(transport=transport)
        client = LinkedInClient(linkedin_config, http=http)
        return client, session

    return _build


def json_response(body: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers or {})
