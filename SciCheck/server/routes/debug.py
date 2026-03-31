from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from SciCheck.server.session_store import get_session
router = APIRouter(tags=["debug"])

@router.get("/state")
def get_state(x_session_id: Optional[str] = Header(None)) -> dict:
    """
    Return the full internal episode state including planted distortions and ground truth.
    Intended for debugging and grader inspection - never shown to the agent.
    """
    env = get_session(x_session_id)
    try:
        return env.state.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/grader")
def get_grader(x_session_id: Optional[str] = Header(None)) -> dict:
    """
    Return the grader breakdown from the most recently completed episode.
    Only available after `submit_verdict` has been called.
    """
    env = get_session(x_session_id)
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

