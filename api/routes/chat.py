"""Chat endpoint.

M0: echoes the user's message back as streamed `token` events. The SSE event
contract (thread / token / tool_call / tool_result / proposal / created / error /
done) is fixed here so the frontend and the real M1 agent speak one protocol —
only the producer behind `_stream` changes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

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


async def _echo_stream(req: ChatRequest) -> AsyncIterator[dict[str, str]]:
    thread_id = req.thread_id or "thread-demo"
    yield _event("thread", {"thread_id": thread_id})
    reply = f"(echo) you said: {req.message}"
    for word in reply.split():
        await asyncio.sleep(0.04)
        yield _event("token", {"text": word + " "})
    yield _event("done", {})


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_echo_stream(req))


@router.post("/chat/resume")
async def chat_resume(req: ResumeRequest) -> EventSourceResponse:
    # M0 placeholder; M1 resumes the agent's approval interrupt here.
    async def _stream() -> AsyncIterator[dict[str, str]]:
        yield _event("token", {"text": f"(resume) approved={req.approved}"})
        yield _event("done", {})

    return EventSourceResponse(_stream())
