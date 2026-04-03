from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from models import (
    ActionType, DivergenceType, Divergence,
    SciCheckAction, SciCheckObservation,
    Verdict
)

class SciCheckEnv(EnvClient[SciCheckAction, SciCheckObservation, State]):
    """
    Client for the My Env Environment.

    This client maintains a persistent WebSocket connection to the environment server,
    enabling efficient multi-step interactions with lower latency.
    Each client instance has its own dedicated environment session on the server.

    Usage:
        # From Docker image (production)
        client = SciCheckClient.from_docker_image("scicheck-env:latest")

        # From local server (development)
        with SciCheckClient(base_url="http://localhost:8000") as client:
            result = client.reset()
            obs = result.observation
            print(obs.press_release)
            print(obs.available_tools)
    """
    

    def _step_payload(self, action: SciCheckAction) -> Dict:
        """
        Convert SciCheckAction to JSON payload for step message.
        The server expects action_type always, and verdict only on submit_verdict.
        """
        payload = {"action": action.action_type.value}

        if action.verdict is not None:
            payload["verdict"] = {
                "overall": action.verdict.overall,
                "divergences": [
                    {
                        "type": d.type.value,
                        "pr_quote": d.pr_quote,
                        "explanation": d.explanation,
                        "severity": d.severity,
                    }
                    for d in action.verdict.divergences
                ],
            }

        return payload

    def _parse_result(self, payload: Dict) -> StepResult[SciCheckObservation]:
        """
        Parse server response into StepResult[SciCheckObservation].
        Server returns StepResult(observation, reward, done) with SciCheckObservation.  
        """
        obs_data = payload.get("observation", {})
        observation = SciCheckObservation(
            press_release=obs_data.get("press_release", ""),
            available_tools=obs_data.get("available_tools", []),
            fetched_sections=obs_data.get("fetched_sections", {}),
            step_count=obs_data.get("step_count", 0),
            done=obs_data.get("done", False)
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse the /state debug endpoint response.
        Returns the raw State object — this is never sent to the agent.
        """
        return State(
            episode_id=payload.get("task_id"),
            step_count=payload.get("step_count", 0),
        )
