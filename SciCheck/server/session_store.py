from fastapi import HTTPException
from typing import Optional
from SciCheck.server.environment import SciCheckEnvironment

# Session pool  { session_id -> SciCheckEnvironment }
_sessions: dict[str, SciCheckEnvironment] = {}

def get_session(session_id: Optional[str]) -> SciCheckEnvironment:
    if not session_id or session_id not in _sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found. POST /reset first (with X-Session-ID header).",
        )
    return _sessions[session_id]