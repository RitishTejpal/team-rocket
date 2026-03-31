from openai import OpenAI
import requests, json
import random, argparse
from SciCheck.core.config import get_settings

settings = get_settings()
client = OpenAI(api_key=settings.groq_api_key, 
                base_url="https://api.groq.com/openai/v1")

# Helper Functions

def get_tasks(base_url: str) -> list[dict]:
    response = requests.get(f"{base_url}/tasks")
    response.raise_for_status()
    return response.json()

def reset_episode(task_id: str, difficulty: str, base_url: str) -> dict:
    print(f"Resetting episode with task_id={task_id} difficulty={difficulty}")
    response = requests.post(f"{base_url}/reset", json={"task_id": task_id, "difficulty": difficulty})

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
    response.raise_for_status()
    return response.json()

SECTION_LIMITS = {
    "abstract":    4000,
    "methods":     4000,
    "results":     6000,
    "limitations": 3000,
    "stats":       3000,
}

def build_prompt(press_release: str, fetched_sections: dict) -> str:
    sections_text = ""
    for section in ["abstract", "methods", "results", "limitations", "stats"]:
        if section in fetched_sections and fetched_sections[section]:
            text = fetched_sections[section]
            limit = SECTION_LIMITS.get(section, 4000)
            if len(text) > limit:
                text = text[:limit] + "\n... [truncated]"
            sections_text += f"\n[{section.upper()}]\n{text}\n"
    return f"""
You are a scientific fact-checker. Given a press release and sections from the underlying paper, you must identify where the press release distorts, exaggerates or misinterprets the research.

Press Release: {press_release}
Sections from the paper: {sections_text}

Output ONLY valid JSON with the following format:
{{
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
"""

def call_llm(prompt: str) -> dict:
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    return response.choices[0].message.content

def parse_verdict(raw_text: str) -> dict | None:
    valid_overalls = {"accurate", "overstated", "misinterpreted", "misleading_by_omission"}
    valid_types = {"scope_inflation", "certainty_inflation", "magnitude_distortion", "hedging_stripped", "population_generalized", "causal_overclaim", "misleading_omission", "stat_fabrication"}
    valid_severities = {"low", "medium", "high"}

    try:
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text.split("```")[1]
            text = text.removeprefix("json").strip()
        data = json.loads(text)

        if data["overall"] not in valid_overalls:
            return None
        
        for divergence in data["divergences"]:
            if divergence["type"] not in valid_types or divergence["severity"] not in valid_severities:
                return None
            if not divergence.get("pr_quote") or not divergence.get("explanation"):
                return None
            
        return data

    except Exception:
        return None

# Baseline Main

FETCH_STRATEGY = {
    "easy":   ["abstract"],
    "medium": ["abstract", "methods", "stats"],
    "hard":   ["abstract", "results", "limitations"],
}
FALLBACK_VERDICT = {
    "easy":   "overstated",
    "medium": "misinterpreted",
    "hard":   "misleading_by_omission",
}

def run_episode(task_id: str, difficulty: str, base_url: str) -> dict:
    # 1. Reset
    # print(task_id, difficulty)
    session_id, obs = reset_episode(task_id, difficulty, base_url)
    press_release = obs["press_release"]
    fetched_sections = {}

    # 2. Fetch sections
    for section in FETCH_STRATEGY[difficulty]:
        obs, reward, done = step_episode(session_id, f"fetch_{section}", base_url)
        fetched_sections = obs["fetched_sections"]
        print(f"  [{task_id}] Fetched {section} (reward={reward:.3f}); done={done})")
        if done:
            print("  Episode ended early - stopping fetch loop")
            break

    # 3. Build prompt and call LLM
    prompt = build_prompt(press_release, fetched_sections)
    raw = call_llm(prompt)
    print(raw)

    # 4. Parse verdict and step
    verdict = parse_verdict(raw)
    if verdict is None:
        print(f"  [{task_id}] parse_verdict failed - using fallback")
        verdict = {"overall": FALLBACK_VERDICT[difficulty], "divergences": []}
    obs, final_reward, done = step_episode(session_id, "submit_verdict", base_url, verdict)
    print(f"  [{task_id}] Submitted verdict (reward={final_reward:.3f}); done={done}")

    # 5. Get grader result
    grader = get_grader_result(session_id, base_url)

    return {
        "task_id": task_id,
        "difficulty": difficulty,
        "final_reward": final_reward,
        "grader": grader,
    }


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
            print(f"  {task['id']}: {result['grader']['final_score']}")
            print("---"*25, "\n")

    print("\n=== BASELINE SUMMARY ===")
    for difficulty in ["easy", "medium", "hard"]:
        subset = [r for r in results if r["difficulty"] == difficulty]
        avg = sum(r["final_reward"] for r in subset) / len(subset)
        print(f"  {difficulty:<8} avg score: {avg:.3f}  ({len(subset)} episodes)")

    with open("baseline_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to baseline_results.json")


if __name__ == "__main__":
    main()