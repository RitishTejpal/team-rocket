# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

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

import uuid
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

try:
    from ..models import SciCheckAction, SciCheckObservation, SciCheckState
    from .environment import SciCheckEnvironment
except ImportError:
    from models import SciCheckAction, SciCheckObservation, SciCheckState  # type: ignore[no-redef]
    from SciCheck.server.environment import SciCheckEnvironment  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SciCheck",
    description=(
        "A multi-step investigation environment where an AI agent must "
        "fact-check a science press release against the underlying research."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Session pool  { session_id -> SciCheckEnvironment }
# ---------------------------------------------------------------------------

_sessions: dict[str, SciCheckEnvironment] = {}


def _require_session(session_id: Optional[str]) -> SciCheckEnvironment:
    if not session_id or session_id not in _sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found. POST /reset first (with X-Session-ID header).",
        )
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ResetRequest(BaseModel):
    task_id: Optional[str] = None
    difficulty: Optional[str] = None


class ResetResponse(BaseModel):
    session_id: str
    observation: SciCheckObservation


class StepResponse(BaseModel):
    session_id: str
    observation: SciCheckObservation
    reward: float
    done: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/reset", response_model=ResetResponse, tags=["episode"])
def reset(
    body: ResetRequest = ResetRequest(),
    x_session_id: Optional[str] = Header(None),
) -> ResetResponse:
    """
    Start a new episode.

    - Supply `task_id` to pin a specific scenario.
    - Supply `difficulty` ("easy" | "medium" | "hard") to draw randomly from that tier.
    - Omit both to draw from the full pool.

    Returns a `session_id` - include it as `X-Session-ID` in all subsequent calls.
    """
    sid = x_session_id or str(uuid.uuid4())

    # Reuse existing env instance if session already exists, else create fresh
    if sid not in _sessions:
        try:
            _sessions[sid] = SciCheckEnvironment()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    env = _sessions[sid]
    try:
        obs = env.reset(task_id=body.task_id, difficulty=body.difficulty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ResetResponse(session_id=sid, observation=obs)


@app.post("/step", response_model=StepResponse, tags=["episode"])
def step(
    action: SciCheckAction,
    x_session_id: Optional[str] = Header(None),
) -> StepResponse:
    """
    Execute one agent action.

    Action types:
    - `fetch_abstract` / `fetch_methods` / `fetch_results` / `fetch_limitations` / `fetch_stats`
    - `submit_verdict`  (include a `verdict` payload)
    """
    env = _require_session(x_session_id)
    try:
        obs, reward, done = env.step(action)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StepResponse(
        session_id=x_session_id,
        observation=obs,
        reward=reward,
        done=done,
    )


@app.get("/state", tags=["debug"])
def get_state(x_session_id: Optional[str] = Header(None)) -> dict:
    """
    Return the full internal episode state including planted distortions and ground truth.
    Intended for debugging and grader inspection - never shown to the agent.
    """
    env = _require_session(x_session_id)
    try:
        return env.state.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/grader", tags=["debug"])
def get_grader(x_session_id: Optional[str] = Header(None)) -> dict:
    """
    Return the grader breakdown from the most recently completed episode.
    Only available after `submit_verdict` has been called.
    """
    env = _require_session(x_session_id)
    try:
        state = env.state
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if state.grader_result is None:
        raise HTTPException(
            status_code=400,
            detail="No grader result yet. Call /step with submit_verdict first.",
        )
    return state.grader_result


@app.get("/tasks", tags=["meta"])
def get_tasks() -> list[dict]:
    """
    List all available scenarios with metadata.
    Ground-truth distortions and paper sections are NOT included.
    """
    try:
        env = SciCheckEnvironment()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return env.scenarios_metadata()


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


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
