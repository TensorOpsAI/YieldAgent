"""LLM provider catalog + connectivity checks for the console.

Single source of truth for which models the UI offers, and which providers are
actually reachable. A provider is "connected" only if its API key is set AND it
authenticates — checked by calling the provider's **models-list** endpoint, which
validates the key (401 if bad) WITHOUT running any inference, so health checks
cost nothing. Results are cached per process; pass force=True to re-check.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

# Frontier line-ups (June 2026).
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "google",
        "label": "Gemini",
        "env": "GOOGLE_API_KEY",
        "models": [
            "gemini-3.1-pro-preview",
            "gemini-3.5-pro",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ],
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "env": "OPENAI_API_KEY",
        "models": ["gpt-5.5", "gpt-5.5-pro", "gpt-5.5-mini", "gpt-5.4", "gpt-5.4-mini"],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "env": "ANTHROPIC_API_KEY",
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
    },
]

_cache: dict[str, dict[str, Any]] | None = None


def _models_request(provider_id: str, key: str) -> tuple[str, dict[str, Any]]:
    """The free, auth-only models-list call for a provider — no inference."""
    if provider_id == "google":
        return (
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"params": {"key": key}},
        )
    if provider_id == "openai":
        return (
            "https://api.openai.com/v1/models",
            {"headers": {"Authorization": f"Bearer {key}"}},
        )
    return (
        "https://api.anthropic.com/v1/models",
        {"headers": {"x-api-key": key, "anthropic-version": "2023-06-01"}},
    )


async def _probe(provider: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get(provider["env"])
    if not key:
        return {"connected": False, "reason": f"{provider['env']} not set"}
    url, kwargs = _models_request(provider["id"], key)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, **kwargs)
        if res.status_code == 200:
            return {"connected": True, "reason": None}
        return {"connected": False, "reason": f"key rejected (HTTP {res.status_code})"}
    except Exception as exc:  # noqa: BLE001 — network/anything means "not usable"
        return {"connected": False, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


async def status(force: bool = False) -> list[dict[str, Any]]:
    """Return each provider's connection state and its available models.

    Models are only listed when the provider is connected, so the UI shows just
    what the operator can actually use.
    """
    global _cache
    if _cache is None or force:
        results = await asyncio.gather(*(_probe(p) for p in PROVIDERS))
        _cache = {p["id"]: r for p, r in zip(PROVIDERS, results, strict=True)}
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "connected": _cache[p["id"]]["connected"],
            "reason": _cache[p["id"]]["reason"],
            "models": p["models"] if _cache[p["id"]]["connected"] else [],
        }
        for p in PROVIDERS
    ]
