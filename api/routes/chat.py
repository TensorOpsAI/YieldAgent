"""Chat endpoint.

M0: echoes the user's message back as streamed `token` events. The SSE event
contract (thread / token / tool_call / tool_result / proposal / created / error /
done) is fixed here so the frontend and the real M1 agent speak one protocol —
only the producer behind `_stream` changes.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yieldagent.agents.console.chat import stream_reply

router = APIRouter()

# In-memory chat history per thread (M0.5). A real store / checkpointer lands
# with the M1 agent; this is enough to hold a single demo conversation.
_HISTORY: dict[str, list[BaseMessage]] = {}


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    reason: str | None = None


def _event(name: str, payload: dict) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload)}


async def _agent_stream(req: ChatRequest) -> AsyncIterator[dict[str, str]]:
    thread_id = req.thread_id or "thread-demo"
    yield _event("thread", {"thread_id": thread_id})

    history = _HISTORY.setdefault(thread_id, [])
    history.append(HumanMessage(content=req.message))

    reply = ""
    try:
        async for delta in stream_reply(history):
            reply += delta
            yield _event("token", {"text": delta})
    except Exception as exc:  # noqa: BLE001 — surface model/config errors to the UI
        yield _event("error", {"message": str(exc)})
    finally:
        history.append(AIMessage(content=reply))
        yield _event("done", {})


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_agent_stream(req))


@router.post("/chat/resume")
async def chat_resume(req: ResumeRequest) -> EventSourceResponse:
    # M0 placeholder; M1 resumes the agent's approval interrupt here.
    async def _stream() -> AsyncIterator[dict[str, str]]:
        yield _event("token", {"text": f"(resume) approved={req.approved}"})
        yield _event("done", {})

    return EventSourceResponse(_stream())
