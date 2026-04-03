from pydantic import BaseModel
from typing import Optional
from models import SciCheckObservation


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