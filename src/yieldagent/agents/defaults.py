"""Shared model defaults for the agents.

Kept in one platform-neutral place (the console's LLM helpers import from here)
so model selection lives in a single module.
"""

from __future__ import annotations

# Provider is inferred from the model name by init_chat_model:
#   gemini-*  -> google_genai (requires GOOGLE_API_KEY)
#   claude-*  -> anthropic    (requires ANTHROPIC_API_KEY)
#   gpt-*     -> openai       (requires OPENAI_API_KEY)
# Override at the CLI via --model, or pass an explicit "provider:model" string.
DEFAULT_MODEL = "gemini-3.1-pro-preview"


def resolve_model_name(model_name: str) -> str:
    """Disambiguate a bare `gemini-*` name to Google AI Studio.

    LangChain's init_chat_model routes bare `gemini-*` to Vertex AI by default,
    which needs full GCP setup. Users with just a `GOOGLE_API_KEY` want the
    Gemini API (Google AI Studio) — the `google_genai` provider — so we make
    that choice explicit. An explicit `provider:model` string is passed through.
    """
    if ":" in model_name:
        return model_name
    if model_name.startswith("gemini-"):
        return f"google_genai:{model_name}"
    return model_name
