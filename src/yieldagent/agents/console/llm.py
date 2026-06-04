"""LLM helpers for the console agent: model selection + streamed-content parsing."""

from __future__ import annotations

import os
from typing import Any

from yieldagent.agents.defaults import DEFAULT_MODEL


def console_model_name() -> str:
    """The model to use when a request doesn't specify one (env-overridable)."""
    return os.environ.get("YIELDAGENT_CONSOLE_MODEL", DEFAULT_MODEL)


def delta_text(content: Any) -> str:
    """Extract plain text from a streamed chunk's content.

    Providers differ: OpenAI/Anthropic stream `content` as a string, while Gemini
    streams a list of typed blocks (e.g. `[{"type": "text", "text": ...}]`).
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
