"""
FastAPI application for SciCheck.

Routing only - zero game logic. All calls delegate to SciCheckEnvironment.

Endpoints:
    POST /reset   - start a new episode
    POST /step    - execute one agent action
    GET  /state   - full hidden state (debug)
    GET  /grader  - last grader breakdown
    GET  /tasks   - scenario catalogue (no ground truth exposed)
    GET  /health  - liveness check

Session management:
    Pass X-Session-ID header to identify your session.
    If omitted on /reset, a new UUID is generated and returned.
    All subsequent calls must include the returned session_id.

Usage:
    uvicorn SciCheck.server.app:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException

from SciCheck.server.environment import SciCheckEnvironment
from SciCheck.server.routes.episode import router as episode_router
from SciCheck.server.routes.debug import router as debug_router
from SciCheck.server.routes.meta import router as meta_router

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load all scenarios into memory once at startup."""
    try:
        SciCheckEnvironment.preload_scenarios()
    except Exception:
        pass 
    yield

app = FastAPI(
    title="SciCheck",
    description=(
        "A multi-step investigation environment where an AI agent must "
        "fact-check a science press release against the underlying research."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(episode_router)
app.include_router(debug_router)
app.include_router(meta_router)

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    main(port=args.port)
