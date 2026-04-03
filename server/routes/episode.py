from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import uuid
from server.session_store import _sessions, get_session
from models import SciCheckAction
from core.schema import ResetRequest, ResetResponse, StepResponse
from server.environment import SciCheckEnvironment

router = APIRouter(tags=["episode"])


@router.post("/reset", response_model=ResetResponse)
def reset(
    body: ResetRequest,
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


@router.post("/step", response_model=StepResponse)
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
    env = get_session(x_session_id)
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
