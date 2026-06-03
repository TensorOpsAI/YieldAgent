"""Shared async HTTP-client plumbing for platform integrations.

The LinkedIn and Meta clients differ in their request shape (versioned headers
vs. an access-token query param, JSON body vs. form data, response unwrapping),
so each keeps its own `_request`. What they genuinely share — the error type,
the optionally-injected `httpx.AsyncClient`, and the async-context-manager
lifecycle — lives here so it is written once.
"""

from __future__ import annotations

from typing import Any, Self

import httpx


class ApiError(RuntimeError):
    """Base for a non-2xx response from a platform's Marketing API.

    Subclasses set `platform` so the message reads e.g. "LinkedIn API error 400".
    """

    platform = "API"

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"{self.platform} API error {status_code}: {payload}")


class BaseHttpClient:
    """Owns an `httpx.AsyncClient` and the async-context-manager lifecycle.

    Pass an existing `http` client to reuse it (the caller then owns its
    lifecycle); otherwise one is created with a 30s timeout and closed on exit.
    """

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_http:
            await self._http.aclose()
