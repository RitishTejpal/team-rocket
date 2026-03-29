# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the SciCheck environment.

All Pydantic shapes live here. No logic. Every other file imports from this.
"""

from enum import Enum
from typing import Dict, List, Literal, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DivergenceType(str, Enum):
    SCOPE_INFLATION = "scope_inflation"
    CERTAINTY_INFLATION = "certainty_inflation"
    MAGNITUDE_DISTORTION = "magnitude_distortion"
    HEDGING_STRIPPED = "hedging_stripped"
    POPULATION_GENERALIZED = "population_generalized"
    CAUSAL_OVERCLAIM = "causal_overclaim"
    MISLEADING_OMISSION = "misleading_omission"


class TaskDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ActionType(str, Enum):
    FETCH_ABSTRACT = "fetch_abstract"
    FETCH_METHODS = "fetch_methods"
    FETCH_RESULTS = "fetch_results"
    FETCH_LIMITATIONS = "fetch_limitations"
    FETCH_STATS = "fetch_stats"
    SUBMIT_VERDICT = "submit_verdict"


# ---------------------------------------------------------------------------
# Verdict (agent's final answer)
# ---------------------------------------------------------------------------


class Divergence(BaseModel):
    """A single divergence the agent identified in the press release."""

    type: DivergenceType
    pr_quote: str = Field(..., description="Offending sentence from the press release")
    explanation: str = Field(..., description="Agent's reasoning")
    severity: Literal["low", "medium", "high"]


class Verdict(BaseModel):
    """The agent's final verdict on the press release."""

    overall: Literal["accurate", "overstated", "misleading_by_omission"]
    divergences: List[Divergence] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Action / Observation (the openenv interface contract)
# ---------------------------------------------------------------------------


class SciCheckAction(Action):
    """Action sent by the agent each step."""

    action_type: ActionType
    verdict: Optional[Verdict] = Field(
        None, description="Required only when action_type is submit_verdict"
    )


class SciCheckObservation(Observation):
    """What the agent sees at each step."""

    press_release: str = Field(..., description="The press release (always visible)")
    available_tools: List[str] = Field(..., description="Actions the agent may call")
    fetched_sections: Dict[str, str] = Field(
        default_factory=dict, description="Paper sections revealed so far"
    )
    step_count: int = Field(0)
    done: bool = Field(False)


# ---------------------------------------------------------------------------
# Ground truth / internal state (agent never sees these)
# ---------------------------------------------------------------------------


class PlantedDistortion(BaseModel):
    """A single ground-truth distortion planted in the press release."""

    type: DivergenceType
    original_text: str
    distorted_to: str
    found_in_section: str  # "abstract" | "methods" | "results" | "limitations" | "stats"


class SciCheckState(BaseModel):
    """Full internal episode state. Never sent to the agent."""

    task_id: str
    difficulty: TaskDifficulty
    press_release: str
    paper_sections: Dict[str, str]
    planted_distortions: List[PlantedDistortion]
    verdict_ground_truth: Literal["accurate", "overstated", "misleading_by_omission"]
    required_sections_for_full_score: List[str]

    fetched_so_far: List[str] = Field(default_factory=list)
    step_count: int = 0
    max_steps: int = 6
    done: bool = False
    trajectory_score: float = 0.0
    verdict_submitted: Optional[Verdict] = None
    grader_result: Optional[dict] = None
