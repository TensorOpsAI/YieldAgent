"""Shared defaults for the campaign-setup agents.

Kept platform-neutral so both the Meta (`campaign_setup`) and LinkedIn
(`linkedin_setup`) entry points import from one place instead of reaching into
each other's modules.
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
