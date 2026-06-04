"""Chat endpoint — drives the conversational console agent over SSE.

The event contract (thread / token / tool_call / tool_result / proposal /
created / error / done) is fixed in `_sse` so the frontend and the agent runtime
speak one protocol. An optional `model` per request overrides the default,
letting the operator A/B providers from the UI.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yieldagent.agents.console import runtime

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str
    model: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    reason: str | None = None
    model: str | None = None


def _event(name: str, payload: dict) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload)}


async def _sse(thread_id: str, events: AsyncIterator) -> AsyncIterator[dict[str, str]]:
    yield _event("thread", {"thread_id": thread_id})
    try:
        async for name, payload in events:
            yield _event(name, payload)
    except Exception as exc:  # noqa: BLE001 — surface agent/model errors to the UI
        yield _event("error", {"message": str(exc)})
    yield _event("done", {})


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    # A fresh conversation gets its own thread so concurrent operators don't
    # share one checkpointed state (and pending approval interrupt).
    thread_id = req.thread_id or f"thread-{uuid4().hex}"
    events = runtime.run(req.message, thread_id, req.model)
    return EventSourceResponse(_sse(thread_id, events))


@router.post("/chat/resume")
async def chat_resume(req: ResumeRequest) -> EventSourceResponse:
    events = runtime.resume(req.thread_id, req.approved, req.reason, req.model)
    return EventSourceResponse(_sse(req.thread_id, events))
