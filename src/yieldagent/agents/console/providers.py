"""LLM provider catalog + connectivity checks for the console.

Single source of truth for which models the UI offers, and which providers are
actually reachable. A provider is "connected" only if its API key is set AND a
tiny live call authenticates — so the model selector can show only usable
models. Results are cached per process; pass force=True to re-test.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain.chat_models import init_chat_model

from yieldagent.agents.defaults import resolve_model_name

# Frontier line-ups (June 2026). `test_model` is a known-cheap model used only to
# verify the key authenticates.
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "google",
        "label": "Gemini",
        "env": "GOOGLE_API_KEY",
        "test_model": "gemini-3.1-pro-preview",
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
        "test_model": "gpt-5.4-mini",
        "models": ["gpt-5.5", "gpt-5.5-pro", "gpt-5.5-mini", "gpt-5.4", "gpt-5.4-mini"],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "env": "ANTHROPIC_API_KEY",
        "test_model": "claude-haiku-4-5",
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
    },
]

_cache: dict[str, dict[str, Any]] | None = None


async def _probe(provider: dict[str, Any]) -> dict[str, Any]:
    if not os.environ.get(provider["env"]):
        return {"connected": False, "reason": f"{provider['env']} not set"}
    try:
        model = init_chat_model(resolve_model_name(provider["test_model"]))
        await model.ainvoke("ok")
        return {"connected": True, "reason": None}
    except Exception as exc:  # noqa: BLE001 — any failure means "not usable"
        return {"connected": False, "reason": f"{type(exc).__name__}: {str(exc)[:140]}"}


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
