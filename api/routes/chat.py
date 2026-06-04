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
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yieldagent.agents.console import runtime

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    reason: str | None = None


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
    thread_id = req.thread_id or "thread-demo"
    return EventSourceResponse(_sse(thread_id, runtime.run(req.message, thread_id)))


@router.post("/chat/resume")
async def chat_resume(req: ResumeRequest) -> EventSourceResponse:
    events = runtime.resume(req.thread_id, req.approved, req.reason)
    return EventSourceResponse(_sse(req.thread_id, events))
