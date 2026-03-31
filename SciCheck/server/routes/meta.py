from fastapi import APIRouter, HTTPException
from SciCheck.server.environment import SciCheckEnvironment

router = APIRouter(tags=["meta"])

@router.get("/tasks")
def get_tasks() -> list[dict]:
    """
    List all available scenarios with metadata.
    Ground-truth distortions and paper sections are NOT included.
    """
    try:
        return SciCheckEnvironment.scenarios_metadata()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}
