# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
SciCheck Environment — all game logic lives here.

Implements the investigation episode:
  - reset(): pick a scenario, return initial observation
  - step(): fetch a section or submit verdict, compute reward
  - _run_grader(): deterministic evaluation against ground truth
  - state: full internal state (for /state debug endpoint)
"""

import json
import random
from pathlib import Path
from typing import Optional, Tuple

try:
    from ..models import (
        ActionType,
        DivergenceType,
        PlantedDistortion,
        SciCheckAction,
        SciCheckObservation,
        SciCheckState,
        TaskDifficulty,
        Verdict,
    )
except ImportError:
    from models import (
        ActionType,
        DivergenceType,
        PlantedDistortion,
        SciCheckAction,
        SciCheckObservation,
        SciCheckState,
        TaskDifficulty,
        Verdict,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTIONS = ["abstract", "methods", "results", "limitations", "stats"]

MAX_STEPS: dict[TaskDifficulty, int] = {
    TaskDifficulty.EASY: 3,
    TaskDifficulty.MEDIUM: 7,
    TaskDifficulty.HARD: 10,
}

# Maps ActionType enum value → section name in paper_sections
FETCH_MAP: dict[ActionType, str] = {
    # ActionType.FETCH_ABSTRACT: "abstract",
    ActionType.FETCH_METHODS: "methods",
    ActionType.FETCH_RESULTS: "results",
    ActionType.FETCH_LIMITATIONS: "limitations",
    ActionType.FETCH_STATS: "stats",
}

DATA_PATH = Path(__file__).parent.parent / "data" / "scenarios.json"


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class SciCheckEnvironment:
    """One instance = one episode. Stateful; must call reset() before step()."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True
    _global_scenarios: Optional[list[dict]] = None

    @classmethod
    def preload_scenarios(cls) -> None:
        """Preload scenarios into class memory, usually triggered by FastAPI lifespan."""
        if cls._global_scenarios is None:
            cls._global_scenarios = cls._load_scenarios()

    def __init__(self) -> None:
        if self._global_scenarios is None:
            self.preload_scenarios()
        self._state: Optional[SciCheckState] = None
        # Use a copy or refer directly since we don't mutate the scenarios list itself
        assert self._global_scenarios is not None
        self._scenarios: list[dict] = self._global_scenarios

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(
        self,
        task_id: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> SciCheckObservation:
        """Select a scenario and initialise a fresh episode."""
        pool = self._scenarios
        if task_id:
            pool = [s for s in pool if s["id"] == task_id]
        elif difficulty:
            pool = [s for s in pool if s["difficulty"] == difficulty]

        if not pool:
            raise ValueError(
                f"No scenarios match: task_id={task_id!r}, difficulty={difficulty!r}"
            )

        scenario = random.choice(pool)
        diff = TaskDifficulty(scenario["difficulty"])

        self._state = SciCheckState(
            task_id=scenario["id"],
            difficulty=diff,
            press_release=scenario["press_release"],
            paper_sections=scenario["paper_sections"],
            planted_distortions=[
                PlantedDistortion(**d) for d in scenario["planted_distortions"]
            ],
            verdict_ground_truth=scenario["verdict_ground_truth"],
            required_sections_for_full_score=scenario.get(
                "required_sections_for_full_score", []
            ),
            fetched_so_far=["abstract"],
            step_count=0,
            max_steps=MAX_STEPS[diff],
            done=False,
            trajectory_score=0.0,
            verdict_submitted=None,
            grader_result=None,
        )

        return self._make_observation()

    def step(
        self, action: SciCheckAction
    ) -> Tuple[SciCheckObservation, float, bool]:
        """Execute one agent action. Returns (observation, reward, done)."""
        if self._state is None:
            raise RuntimeError("Call reset() before step().")

        state = self._state

        # Episode already finished
        if state.done:
            return self._make_observation(), 0.0, True

        state.step_count += 1

        # --- Submit verdict ---
        if action.action_type == ActionType.SUBMIT_VERDICT:
            if action.verdict is None:
                raise ValueError("verdict is required for submit_verdict.")
            reward = self._finalize(action.verdict)
            state.done = True
            return self._make_observation(), reward, True

        # --- Fetch section ---
        section = FETCH_MAP.get(action.action_type)
        if section is None:
            raise ValueError(f"Unrecognised action_type: {action.action_type}")

        if section in state.fetched_so_far:
            # Already revealed — no reward, no penalty
            step_reward = 0.0
        else:
            state.fetched_so_far.append(section)
            step_reward = 0.1 if self._is_relevant_section(section) else -0.1
            state.trajectory_score += step_reward

        # Max steps guard
        if state.step_count >= state.max_steps and not state.done:
            state.trajectory_score -= 0.3
            state.done = True

        return self._make_observation(), step_reward, state.done

    @property
    def state(self) -> SciCheckState:
        if self._state is None:
            raise RuntimeError("No active episode. Call reset() first.")
        return self._state

    @classmethod
    def scenarios_metadata(cls) -> list[dict]:
        """Returns scenario metadata without ground-truth distortion details."""
        if cls._global_scenarios is None:
            cls.preload_scenarios()
        assert cls._global_scenarios is not None
        
        return [
            {
                "id": s["id"],
                "difficulty": s["difficulty"],
                "topic": s.get("domain", ""),
                "num_distortions": len(s.get("planted_distortions", [])),
                "required_sections": s.get("required_sections_for_full_score", []),
            }
            for s in cls._global_scenarios
        ]

    # ------------------------------------------------------------------
    # Grader
    # ------------------------------------------------------------------

    def _finalize(self, verdict: Verdict) -> float:
        """Apply limitations penalty, run grader, compute final score."""
        state = self._state

        # Trajectory penalty: submitted without ever fetching limitations
        if state.difficulty == TaskDifficulty.HARD and "limitations" not in state.fetched_so_far:
            state.trajectory_score -= 0.2

        raw_verdict_score, max_verdict_score = self._run_grader(verdict)
        state.verdict_submitted = verdict

        # Max possible trajectory (0.1 per unique relevant section)
        relevant_sections = {p.found_in_section for p in state.planted_distortions}
        max_trajectory = len(relevant_sections) * 0.1

        # Max theoretical raw score
        max_raw = (max_trajectory * 0.3) + (max_verdict_score * 0.7)
        
        # Achieved raw score
        achieved_raw = (state.trajectory_score * 0.3) + (raw_verdict_score * 0.7)

        MIN = 0.0001
        MAX = 0.9999
        # Normalize to 0 - 1
        raw_ratio = achieved_raw / max_raw if max_raw > 0 else MIN
        final_score = max(MIN, min(MAX, raw_ratio))

        # Persist final numbers in grader result
        assert state.grader_result is not None
        state.grader_result["trajectory_score"] = round(state.trajectory_score, 4)
        state.grader_result["verdict_score"] = round(raw_verdict_score, 4)
        state.grader_result["final_score"] = round(final_score, 4)

        return final_score

    def _run_grader(self, verdict: Verdict) -> Tuple[float, float]:
        """
        Deterministic verdict evaluation.
        Returns: (achieved_score, max_possible_score)

        EASY
          +0.3  overall verdict matches ground truth
          +0.3  per planted distortion whose type appears in agent.divergences
          +0.2  per planted distortion whose found_in_section was fetched

        MEDIUM
          +0.3  baseline buffer
          +0.3  overall verdict matches ground truth
          +0.3  per planted distortion whose type appears in agent.divergences
          +0.2  per planted distortion whose found_in_section was fetched

        HARD
          +0.3  agent.overall == "misleading_by_omission"
          +0.1  "results" in fetched_sections
          +0.1  "limitations" in fetched_sections
          +0.3  per non-MISLEADING_OMISSION distortion type matched
          +0.2  per non-MISLEADING_OMISSION distortion whose section was fetched
        """
        state = self._state
        planted = state.planted_distortions
        submitted_types = {d.type for d in verdict.divergences}
        fetched = set(state.fetched_so_far)
        score = 0.0
        max_possible = 0.0
        checks: list[dict] = []

        def record(check: str, passed: bool, points: float) -> None:
            nonlocal score, max_possible
            max_possible += points
            score += points if passed else 0.0
            checks.append({"check": check, "passed": passed, "points": points if passed else 0.0})

        if state.difficulty == TaskDifficulty.HARD:
            record(
                "overall_verdict:misleading_by_omission",
                verdict.overall == "misleading_by_omission",
                0.3,
            )
            record("results_fetched", "results" in fetched, 0.1)
            record("limitations_fetched", "limitations" in fetched, 0.1)

            for p in planted:
                if p.type == DivergenceType.MISLEADING_OMISSION:
                    continue  # captured by overall field only
                record(f"divergence_type:{p.type.value}", p.type in submitted_types, 0.3)
                record(f"section_fetched:{p.found_in_section}", p.found_in_section in fetched, 0.2)

        elif state.difficulty == TaskDifficulty.MEDIUM:
            record("medium_baseline", True, 0.3)
            record(
                f"overall_verdict:{state.verdict_ground_truth}",
                verdict.overall == state.verdict_ground_truth,
                0.3,
            )
            for p in planted:
                record(f"divergence_type:{p.type.value}", p.type in submitted_types, 0.3)
                record(f"section_fetched:{p.found_in_section}", p.found_in_section in fetched, 0.2)

        else:  # easy
            record(
                f"overall_verdict:{state.verdict_ground_truth}",
                verdict.overall == state.verdict_ground_truth,
                0.3,
            )
            for p in planted:
                record(f"divergence_type:{p.type.value}", p.type in submitted_types, 0.3)
                record(f"section_fetched:{p.found_in_section}", p.found_in_section in fetched, 0.2)

        state.grader_result = {
            "task_id": state.task_id,
            "difficulty": state.difficulty.value,
            "raw_verdict_score": score,
            "max_possible_verdict": max_possible,
            "checks": checks,
            # trajectory / verdict / final filled in by _finalize()
        }
        return score, max_possible

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_relevant_section(self, section: str) -> bool:
        return any(p.found_in_section == section for p in self._state.planted_distortions)

    def _make_observation(self) -> SciCheckObservation:
        state = self._state
        fetched = set(state.fetched_so_far)
        available_tools = [
            f"fetch_{s}" for s in SECTIONS if s not in fetched
        ] + ["submit_verdict"]
        return SciCheckObservation(
            press_release=state.press_release,
            available_tools=available_tools,
            fetched_sections={
                s: state.paper_sections[s]
                for s in state.fetched_so_far
                if s in state.paper_sections and state.paper_sections[s] is not None
            },
            step_count=state.step_count,
            done=state.done,
            reward=None,
        )

    @staticmethod
    def _load_scenarios() -> list[dict]:
        if not DATA_PATH.exists():
            raise FileNotFoundError(
                f"scenarios.json not found at {DATA_PATH}. "
                "Generate it with generate_scenarios.py before starting the server."
            )
        with open(DATA_PATH, encoding="utf-8") as fh:
            return json.load(fh)
