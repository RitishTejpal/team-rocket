from openai import OpenAI
import requests, json, re
import random, argparse
from core.config import get_settings

settings = get_settings()
if settings.hf_token:
    client = OpenAI(api_key=settings.hf_token, base_url=settings.api_base_url)
else:
    print("CONFIG ERROR: Set the HF Token in the .env file.")
    exit(1)


# ------------------------------------
# Helper Functions
# ------------------------------------

def get_tasks(base_url: str) -> list[dict]:
    response = requests.get(f"{base_url}/tasks")
    response.raise_for_status()
    return response.json()

def reset_episode(task_id: str, base_url: str) -> dict:
    print(f"Resetting episode with task_id={task_id}")
    response = requests.post(f"{base_url}/reset", json={"task_id": task_id})

    if response.status_code != 200:
        print(f"SERVER ERROR ({response.status_code}): {response.text}")

    response.raise_for_status()
    data = response.json()
    return data["session_id"], data["observation"]

def step_episode(session_id: str, action_type: str, base_url: str, verdict: dict = None) -> tuple[dict, float, bool]:
    body = {"action_type": action_type}
    if verdict is not None:
        body["verdict"] = verdict
    response = requests.post(f"{base_url}/step", json=body, headers={"X-Session-ID": session_id})
    
    if response.status_code == 404:
        print(f"DEBUG: Check your URL!")

    response.raise_for_status()
    data = response.json()
    return data["observation"], data["reward"], data["done"]

def get_grader_result(session_id: str, base_url: str) -> dict:
    response = requests.get(f"{base_url}/grader", headers={"X-Session-ID": session_id})
    if response.status_code == 400:
        return None
    response.raise_for_status()
    return response.json()


# ------------------------------------
# Prompts and Parsing
# ------------------------------------

SECTION_LIMITS = {
    "abstract":    4000,
    "methods":     4000,
    "results":     6000,
    "limitations": 3000,
    "stats":       3000,
}

def build_prompt(press_release: str, fetched_sections: dict, available_tools: list) -> str:
    sections_text = ""
    for section in ["abstract", "methods", "results", "limitations", "stats"]:
        if section in fetched_sections and fetched_sections[section]:
            text = fetched_sections[section]
            limit = SECTION_LIMITS.get(section, 4000)
            if len(text) > limit:
                text = text[:limit] + "\n... [truncated]"
            sections_text += f"\n[{section.upper()}]\n{text}\n"

    if not sections_text:
        sections_text = "None yet."

    return f"""You are a scientific fact-checker investigating a press release. The press release may or may not have some disparities with the underlying scientific paper. Given a press release and sections from the underlying paper, you must identify where the press release distorts, exaggerates or misinterprets the research.
You have access to different sections of the paper that you can fetch one at a time, but fetching is costly. You must decide which section to fetch next, or if you have enough information to submit a final verdict on the press release's accuracy.
You have the valid fetch tools available for you listed down below.

PRESS RELEASE:
{press_release}

SECTIONS YOU HAVE READ SO FAR:
{sections_text}

AVAILABLE ACTIONS:
{available_tools}

Decide what to do next.
- Read the press release. Fetch a section of your choice to begin the process of fact checking.
- If you can already identify distortions from what you have read and feel like there is nothing suspicious about the text anymore, choose submit_verdict.
- If you need more evidence, fetch the most relevant section as per you.
- You have a limited step budget. Do NOT fetch sections unnecessarily.

If your action is anything other than submit_verdict, output ONLY this JSON:
{{
    "action": "fetch_abstract | fetch_methods | fetch_results | fetch_limitations | fetch_stats | submit_verdict",
    "reasoning": "why you chose this"
}}

If your action is submit_verdict, output ONLY this JSON:
{{
    "action": "submit_verdict",
    "reasoning": "why you have enough evidence to decide",
    "verdict": {{
        "overall": "accurate" | "overstated" | "misinterpreted" | "misleading_by_omission",
        "divergences": [
        {{
            "type": "scope_inflation" | "certainty_inflation" | "magnitude_distortion" | "hedging_stripped" | "population_generalized" | "causal_overclaim" | "misleading_omission" | "stat_fabrication",
            "pr_quote": "exact sentence from press release that is wrong",
            "explanation": "why this is wrong based on the paper",
            "severity": "low" | "medium" | "high"
        }}
        ]
    }}
}}
"""

def call_llm(prompt: str) -> dict:
    response = client.chat.completions.create(
        model=settings.model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    return response.choices[0].message.content

def parse_response(raw_text: str, available_tools: list) -> tuple[str, dict | None]:
    valid_overalls = {"accurate", "overstated", "misinterpreted", "misleading_by_omission"}
    valid_types = {"scope_inflation", "certainty_inflation", "magnitude_distortion", "hedging_stripped", "population_generalized", "causal_overclaim", "misleading_omission", "stat_fabrication"}
    valid_severities = {"low", "medium", "high"}

    try:
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        data = json.loads(text)

        action = data.get("action", "").strip()
        if action not in available_tools:
            return None, None

        if action != "submit_verdict":
            return action, None
        
        # Validate the embedded verdict
        v = data.get("verdict")
        if not v or v.get("overall") not in valid_overalls:
            return None, None

        for d in v.get("divergences", []):
            if d.get("type") not in valid_types:
                return None, None
            if d.get("severity") not in valid_severities:
                return None, None
            if not d.get("pr_quote") or not d.get("explanation"):
                return None, None

        return action, v

    except Exception:
        return None, None


# ------------------------------------
# Episode Runner
# ------------------------------------

FALLBACK_VERDICT = {
    "easy":   "overstated",
    "medium": "misinterpreted",
    "hard":   "misleading_by_omission",
}
MAX_STEPS = {
    "easy": 3,
    "medium": 7,
    "hard": 10,
}

def run_episode(task_id: str, difficulty: str, base_url: str) -> dict:
    # [START]
    print(json.dumps({"log": "[START]", "task_id": task_id, "difficulty": difficulty}))

    # 1. Reset
    # print(task_id, difficulty)
    session_id, obs = reset_episode(task_id, base_url)
    press_release = obs["press_release"]
    fetched_sections = {}
    available_tools = obs["available_tools"]
    final_reward = 0.0
    max_steps = MAX_STEPS[difficulty]
    verdict_submitted = False

    # 2. Agentic loop
    for step in range(max_steps):
        # 2.1 Ask llm what to do next
        raw = call_llm(build_prompt(press_release, fetched_sections, available_tools))
        action, verdict = parse_response(raw, available_tools)

        if action is None:
            if fetched_sections:
                action = "submit_verdict"
                verdict = {"overall": FALLBACK_VERDICT[difficulty], "divergences": []}
            else:
                action = "fetch_abstract"
                
        # 2.2 if submit, ask for verdict
        if action == "submit_verdict":
            if verdict is None:
                verdict = {
                    "overall": FALLBACK_VERDICT[difficulty], 
                    "divergences": []
                }

            obs, final_reward, done = step_episode(session_id, "submit_verdict", base_url, verdict)
            verdict_submitted = True
            # [STEP]
            print(json.dumps({
                "log":      "[STEP]",
                "task_id":  task_id,
                "step":     step + 1,
                "action":   "submit_verdict",
                "reward":   round(final_reward, 4),
                "done":     done,
            }))
            break

        # 2.3 fetch action  
        obs, reward, done = step_episode(session_id, action, base_url)
        fetched_sections = obs["fetched_sections"]
        available_tools = obs["available_tools"]
        # [STEP]
        print(json.dumps({
                "log":      "[STEP]",
                "task_id":  task_id,
                "step":     step + 1,
                "action":   "submit_verdict",
                "reward":   round(final_reward, 4),
                "done":     done,
            }))

        if done:    # Max steps exceeded
            break

    # 3. Get grader result
    grader = get_grader_result(session_id, base_url) if verdict_submitted else None
    score = grader["final_score"] if grader else 0.0
    # [END]
    print(json.dumps({
        "log":      "[END]",
        "task_id":  task_id,
        "score":    round(score, 4),
        "reward":   round(final_reward, 4),
        "difficulty": difficulty,
    }))

    return {
        "task_id": task_id,
        "difficulty": difficulty,
        "final_score": score,
        "final_reward": final_reward,
        "grader": grader,
    }


# ------------------------------------
# Main
# ------------------------------------

RANDOM_SEED = 42
EPISODES_PER_DIFFICULTY = 5

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base_url = args.base_url

    random.seed(RANDOM_SEED)
    all_tasks = get_tasks(base_url)
    results = []

    for difficulty in ["easy", "medium", "hard"]:
        pool = [t for t in all_tasks if t["difficulty"] == difficulty]
        sample = random.sample(pool, min(EPISODES_PER_DIFFICULTY, len(pool)))
        print(f"\n--- {difficulty.upper()} ({len(sample)} episodes) ---")

        for task in sample:
            result = run_episode(task["id"], difficulty, base_url)
            results.append(result)
            print(f"  {task['id']}: {result['final_reward']:.3f}")
            print("---"*25, "\n")

    print("\n=== BASELINE SUMMARY ===")
    for difficulty in ["easy", "medium", "hard"]:
        subset = [r for r in results if r["difficulty"] == difficulty]
        if subset:
            avg = sum(r["final_reward"] for r in subset) / len(subset)
            print(f"  {difficulty:<8} avg score: {avg:.3f}  ({len(subset)} episodes)")

    with open("baseline_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to baseline_results.json")


if __name__ == "__main__":
    main()