"""Minimal streaming chat for the web console (M0.5: real LLM, no tools yet).

Proves a real model streaming into the chat, replacing the M0 echo. The full
tool-using agent (recipe-book lookups, propose, create draft) lands in M1.

Model is provider-agnostic: defaults to `DEFAULT_MODEL`, override with the
`YIELDAGENT_CONSOLE_MODEL` env var (e.g. `gpt-4o`, `claude-...`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, SystemMessage

from yieldagent.agents.defaults import DEFAULT_MODEL, resolve_model_name

SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a LinkedIn media-buying copilot helping an operator plan an ad "
        "campaign through conversation. Be concise and ask focused clarifying "
        "questions (budget, audience, objective, geos). Tool use and draft "
        "creation are coming soon; for now, help the operator think it through."
    )
)


def console_model_name() -> str:
    return os.environ.get("YIELDAGENT_CONSOLE_MODEL", DEFAULT_MODEL)


def _delta_text(content: Any) -> str:
    """Extract plain text from a streamed chunk's content.

    Providers differ: OpenAI/Anthropic stream `content` as a string, while
    Gemini streams a list of typed blocks (e.g. `[{"type": "text", "text": ...}]`).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


async def stream_reply(history: list[BaseMessage]) -> AsyncIterator[str]:
    """Stream the assistant's reply for the given chat history."""
    model = init_chat_model(resolve_model_name(console_model_name()))
    async for chunk in model.astream([SYSTEM_PROMPT, *history]):
        text = _delta_text(chunk.content)
        if text:
            yield text
