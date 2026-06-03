"""Graph nodes for the campaign-setup agent."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from yieldagent.domain import Brief, Campaign, CampaignStatus

from .prompts import PARSE_BRIEF_SYSTEM, PLAN_CAMPAIGN_SYSTEM
from .state import AgentState, AuditEntry

# Provider is inferred from the model name by init_chat_model:
#   gemini-*         -> google_genai (requires GOOGLE_API_KEY)
#   claude-*         -> anthropic    (requires ANTHROPIC_API_KEY)
#   gpt-*            -> openai       (requires OPENAI_API_KEY)
# Override at the CLI via --model, or pass an explicit "provider:model" string.
DEFAULT_MODEL = "gemini-3.1-pro-preview"


def _resolve_model_name(model_name: str) -> str:
    """Disambiguate bare `gemini-*` to Google AI Studio.

    LangChain's init_chat_model routes bare `gemini-*` to Vertex AI by default,
    which needs full GCP setup. Users with just a `GOOGLE_API_KEY` want the
    Gemini API (Google AI Studio) — the `google_genai` provider — so we make
    that choice explicit. Callers who want Vertex can still pass
    `google_vertexai:gemini-...`.
    """
    if ":" in model_name:
        return model_name
    if model_name.startswith("gemini-"):
        return f"google_genai:{model_name}"
    return model_name


def _audit(state: AgentState, entry: AuditEntry) -> list[AuditEntry]:
    return [*state.get("audit", []), entry]


def make_parse_brief_node(model_name: str = DEFAULT_MODEL):
    model = init_chat_model(_resolve_model_name(model_name)).with_structured_output(Brief)

    async def parse_brief(state: AgentState) -> dict[str, Any]:
        brief = await model.ainvoke(
            [
                SystemMessage(content=PARSE_BRIEF_SYSTEM),
                HumanMessage(content=state["brief_text"]),
            ]
        )
        return {
            "brief": brief,
            "audit": _audit(
                state,
                AuditEntry(
                    node="parse_brief",
                    summary=f"Parsed brief for {brief.advertiser} / {brief.product}",
                    detail={"platforms": brief.platforms, "objective": brief.objective.value},
                ),
            ),
        }

    return parse_brief


def make_plan_campaign_node(model_name: str = DEFAULT_MODEL):
    model = init_chat_model(_resolve_model_name(model_name)).with_structured_output(Campaign)

    async def plan_campaign(state: AgentState) -> dict[str, Any]:
        brief = state["brief"]
        campaign = await model.ainvoke(
            [
                SystemMessage(content=PLAN_CAMPAIGN_SYSTEM),
                HumanMessage(content=brief.model_dump_json(indent=2)),
            ]
        )
        # Defense in depth: even if the model ignores the prompt, drafts must be paused.
        if campaign.status == CampaignStatus.active:
            campaign = campaign.model_copy(update={"status": CampaignStatus.draft})
        return {
            "campaign": campaign,
            "audit": _audit(
                state,
                AuditEntry(
                    node="plan_campaign",
                    summary=(
                        f"Planned {len(campaign.line_items)} line item(s) "
                        f"and {len(campaign.ads)} ad(s)"
                    ),
                    detail={"campaign_name": campaign.name, "status": campaign.status.value},
                ),
            ),
        }

    return plan_campaign


def human_gate(state: AgentState) -> dict[str, Any]:
    """Pause for human approval. Pillar 6: nothing spend-affecting without a gate."""
    campaign = state["campaign"]
    decision = interrupt(
        {
            "question": "Approve this draft campaign?",
            "campaign": campaign.model_dump(mode="json"),
        }
    )
    approved = bool(decision.get("approved"))
    reason = decision.get("reason", "")
    return {
        "approved": approved,
        "audit": _audit(
            state,
            AuditEntry(
                node="human_gate",
                summary="Approved" if approved else f"Rejected: {reason}",
                detail={"approved": approved, "reason": reason},
            ),
        ),
    }


def route_after_gate(state: AgentState) -> str:
    return "publish_draft" if state.get("approved") else "__end__"


def make_publish_draft_node(get_mcp_tool):
    """Build the publish node, parameterized by how to fetch the MCP tool.

    Indirection lets tests pass a fake tool without standing up a real MCP server.
    """

    async def publish_draft(state: AgentState) -> dict[str, Any]:
        tool = await get_mcp_tool("publish_draft_campaign")
        result = await tool.ainvoke({"campaign": state["campaign"].model_dump(mode="json")})
        return {
            "publish_result": result,
            "audit": _audit(
                state,
                AuditEntry(
                    node="publish_draft",
                    summary=(
                        f"Published draft campaign {result.get('campaign_id')} "
                        f"with {len(result.get('line_items', []))} line item(s) "
                        f"and {len(result.get('ads', []))} ad(s)"
                    ),
                    detail=result,
                ),
            ),
        }

    return publish_draft
