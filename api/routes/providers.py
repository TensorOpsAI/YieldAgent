"""Provider health: which LLM providers authenticate, and their usable models."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from yieldagent.agents.console import providers

router = APIRouter()


@router.get("/providers")
async def get_providers(test: bool = False) -> list[dict[str, Any]]:
    """List providers with connection state + available models.

    Cached per process; pass `?test=1` to force a fresh live re-check.
    """
    return await providers.status(force=test)
