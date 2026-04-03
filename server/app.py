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
from fastapi import FastAPI

from server.environment import SciCheckEnvironment
from server.routes.episode import router as episode_router
from server.routes.debug import router as debug_router
from server.routes.meta import router as meta_router

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

scicheck_app = FastAPI(
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

scicheck_app.include_router(episode_router)
scicheck_app.include_router(debug_router)
scicheck_app.include_router(meta_router)

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the uvicorn server. Called directly by OpenEnv."""
    import uvicorn
    uvicorn.run(scicheck_app, host=host, port=port)
 
 
if __name__ == "__main__":
    main()
