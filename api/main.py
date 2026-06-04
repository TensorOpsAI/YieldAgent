"""App factory for the YieldAgent console API.

M0 surface: a health check and an echo chat stream that proves the
frontend<->backend SSE pipe. The real conversational agent (M1) and the
dashboard REST endpoints (M3) mount onto the same app.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from yieldagent.env import load_dotenv

from .routes import chat

# The Next.js dev server runs here; widen for deployment later.
ALLOWED_ORIGINS = ["http://localhost:3000"]


def create_app() -> FastAPI:
    load_dotenv()  # pick up GOOGLE_API_KEY / OPENAI_API_KEY / etc.
    app = FastAPI(title="YieldAgent Console API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
