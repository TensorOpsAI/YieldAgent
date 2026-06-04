# YieldAgent — Web Console (`web/`)

Next.js (App Router) + Tailwind frontend for the conversational campaign console.
Talks to the FastAPI backend in `api/` over REST + SSE.

## Requirements

- **Node ≥ 20.9** (use `nvm use` — this folder pins **22** via `.nvmrc`).
  The repo's other tooling tolerates Node 18, but Next.js 16 does not.

## Run (two terminals)

```bash
# 1) backend (from repo root)
pip install -e ".[web,linkedin,agent]"
uvicorn api.main:app --reload --port 8000

# 2) frontend (from web/)
nvm use                 # -> Node 22 (.nvmrc)
npm install             # first time only
npm run dev             # http://localhost:3000
```

The frontend calls the backend at `http://localhost:8000` by default; override
with `NEXT_PUBLIC_API_BASE`.

## Status (M0)

Skeleton + the SSE pipe: shell (sidebar, Dashboard, Agent Console, Connections)
and a chat that streams an **echo** from `POST /api/chat`. The real
conversational agent lands in M1 (see `docs/claude_docs/web_console_plan.md`).
