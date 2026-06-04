"""FastAPI backend for the YieldAgent web console.

A thin HTTP/SSE layer over the `yieldagent` package — the business logic stays in
the tested package; this service only exposes it to the Next.js frontend.
"""
