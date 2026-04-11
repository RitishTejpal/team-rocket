from openai import OpenAI
import requests, json, subprocess, time
import random, argparse, sys, os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("HF_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"

if not API_KEY:
    print("CONFIG ERROR: Set the HF Token in the .env file.")
    exit(1)
client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)

# ------------------------------------
# Stdout Logging  -  SPEC-REQUIRED FORMAT
# ------------------------------------
 
def log_start(task_id, model):
    print(f"[START] task={task_id} env=scicheck model={model}", flush=True)

def log_step(step, action, reward, done, error=None):
    error_val = error if error else "null"
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={error_val}", flush=True)

def log_end(success, steps, score, rewards):
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)


# ------------------------------------
# Helper Functions
# ------------------------------------

def get_tasks(base_url: str) -> list[dict]:
    response = requests.get(f"{base_url}/tasks")
    response.raise_for_status()
    return response.json()

def reset_episode(task_id: str, base_url: str) -> dict:
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
        print(f"DEBUG /step - response body: {response.text}") 

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

DIFFICULTY_GUIDANCE = """ 
    "easy": "The distortion is visible in the abstract. Compare carefully and submit directly.",
    "medium": "The distortion is subtle and likely NOT visible in the abstract alone. Fetch methods or stats before submitting.", 
    "hard": "The distortion involves omission or results manipulation. Fetch results AND limitations before submitting.", 
"""

def build_prompt(press_release: str, fetched_sections: dict, available_tools: list, steps_remaining: int) -> str:
    sections_text = ""
    for section in ["abstract", "methods", "results", "limitations", "stats"]:
        if section in fetched_sections and fetched_sections[section]:
            text = fetched_sections[section]
            limit = SECTION_LIMITS.get(section, 4000)
            if len(text) > limit:
                text = text[:limit] + "\n... [truncated]"
            sections_text += f"\n[{section.upper()}]\n{text}\n"
    steps_remaining = steps_remaining

    if not sections_text:
        sections_text = "None yet."
    
    guidance = DIFFICULTY_GUIDANCE

    return f"""You are a scientific fact-checker. You have been given a press release and the paper's ABSTRACT is already in your sections below.
The scenarios have a difficulty of easy, medium and hard. You could be presented with any at a time. 
STRATEGY: {guidance} 
BUDGET: {steps_remaining} steps remaining (including final submit). Wrong fetches cost -0.1. Your goal is to maximize your score.

STEP 1 - COMPARE CAREFULLY:
Read the press release and the abstract side by side. Look for:
- Numbers, percentages, or effect sizes that differ
- Certainty words added (e.g. "proves", "shows", "confirms") that the abstract doesn't use  
- Scope expanded (e.g. "all people" when abstract says "elderly patients")
- Causal language added (e.g. "causes" when abstract says "associated with")
- Qualifications or hedging removed (e.g. abstract says "may reduce" but PR says "reduces")
- Key limitations the abstract mentions but the PR omits entirely

STEP 2 - CLASSIFY:
Pick the SINGLE best verdict:
- "overstated": findings are real but PR inflates certainty, magnitude, or scope beyond what abstract supports
- "misinterpreted": PR changes the nature of the finding - adds causation, wrong population, strips hedging, alters statistics
- "misleading_by_omission": PR is accurate but silently drops key limitations or caveats the abstract mentions
- "accurate": no distortion found

Divergence type mapping - use this exactly:
- Certainty words added / probability presented as fact -> "certainty_inflation"
- Effect size or numbers exaggerated -> "magnitude_distortion"  
- Scope of finding broadened beyond the data -> "scope_inflation"
- Causal language where abstract shows only correlation -> "causal_overclaim"
- Specific population generalized to everyone -> "population_generalized"
- Hedging or qualifying language stripped out -> "hedging_stripped"
- Key limitation silently omitted -> "misleading_omission"
- Statistics changed or fabricated -> "stat_fabrication"

STEP 3 - DECIDE ACTION:
- If the abstract comparison already reveals the distortion clearly -> submit_verdict immediately. Do NOT fetch more sections.
- Only fetch one more section if the abstract is genuinely inconclusive AND you know exactly which section to check.


PRESS RELEASE:
{press_release}

SECTIONS READ SO FAR (abstract is always here):
{sections_text}

AVAILABLE ACTIONS:
{available_tools}

If fetching, output ONLY:
{{
    "action": "fetch_methods | fetch_results | fetch_limitations | fetch_stats",
    "reasoning": "specific claim in PR that contradicts abstract, and why this section will clarify it"
}}

If submitting, output ONLY:
{{
    "action": "submit_verdict",
    "reasoning": "exact comparison between PR claim and what abstract actually says",
    "verdict": {{
        "overall": "overstated | misinterpreted | misleading_by_omission | accurate",
        "divergences": [
        {{
            "type": "certainty_inflation | magnitude_distortion | scope_inflation | causal_overclaim | population_generalized | hedging_stripped | misleading_omission | stat_fabrication",
            "pr_quote": "exact sentence from press release that is wrong",
            "explanation": "what the abstract actually says vs what the PR claims",
            "severity": "low | medium | high"
        }}
        ]
    }}
}}
"""

def call_llm(prompt: str) -> str:
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                seed=RANDOM_SEED,
                max_tokens=1000,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "queue" in str(e).lower() or "rate" in str(e).lower():
                wait = 10 * (attempt + 1)
                print(f"[LLM] Rate limited, retrying in {wait}s... (attempt {attempt+1}/5)", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("[LLM] Failed after 5 retries due to rate limiting.")

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
    "easy":   "accurate",
    "medium": "accurate",
    "hard":   "accurate",
}
MAX_STEPS = {
    "easy": 3,
    "medium": 7,
    "hard": 10,
}

def run_episode(task_id: str, difficulty: str, base_url: str) -> dict:
    # [START]
    log_start(task_id, MODEL_NAME)

    # 1. Reset
    # print(task_id, difficulty)
    session_id, obs = reset_episode(task_id, base_url)
    press_release = obs["press_release"]
    fetched_sections = obs["fetched_sections"]
    available_tools = obs["available_tools"]
    final_reward = 0.0
    max_steps = MAX_STEPS[difficulty]
    verdict_submitted = False
    rewards_list = []
    steps_taken = 0

    # 2. Agentic loop
    for step in range(max_steps):
        steps_taken += 1
        # 2.1 Ask llm what to do next
        steps_remaining = max_steps - step
        if steps_remaining == 1 and fetched_sections:
            action, verdict = "submit_verdict", None
        else:
            raw = call_llm(build_prompt(press_release, fetched_sections, available_tools, steps_remaining))
            action, verdict = parse_response(raw, available_tools)

        if action is None:
            if fetched_sections:
                action = "submit_verdict"
                verdict = {"overall": FALLBACK_VERDICT[difficulty], "divergences": []}
            else:
                action = "fetch_stats"
                
        # 2.2 if submit, ask for verdict
        if action == "submit_verdict":
            if verdict is None:
                verdict = {
                    "overall": FALLBACK_VERDICT[difficulty], 
                    "divergences": []
                }

            obs, final_reward, done = step_episode(session_id, "submit_verdict", base_url, verdict)
            verdict_submitted = True
            rewards_list.append(final_reward)
            # [STEP]
            log_step(steps_taken, action, final_reward, done)
            break

        # 2.3 fetch action  
        obs, reward, done = step_episode(session_id, action, base_url)
        fetched_sections = obs["fetched_sections"]
        available_tools = obs["available_tools"]
        rewards_list.append(reward)
        # [STEP]
        log_step(steps_taken, action, reward, done)

        if done:    # Max steps exceeded
            verdict_submitted = True
            break

    # 3. Get grader result
    grader = get_grader_result(session_id, base_url) if verdict_submitted else None
    score = grader["final_score"] if grader else 0.0
    # if grader:
    #     print(f"[GRADER CHECKS] {json.dumps(grader.get('checks', []), indent=2)}", flush=True)
    # [END]
    log_end(success=(score > 0), steps=steps_taken, score=score, rewards=rewards_list)

    return {
        "task_id": task_id,
        "difficulty": difficulty,
        "final_score": score,
        "final_reward": final_reward,
        "grader": grader,
    }


# ------------------------------------
# Server startup helper
# ------------------------------------
 
def start_server(port: int = 7860) -> subprocess.Popen:
    """Launch the uvicorn server as a subprocess and return the process handle."""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "server.app:scicheck_app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"[SERVER] Started uvicorn on port {port} (pid={proc.pid})", flush=True)
    return proc
 
 
def wait_for_server(base_url: str, timeout: int = 60, interval: float = 2.0) -> None:
    """Block until the server responds on /health (or /tasks), or raise on timeout."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=3)
            if r.status_code < 500:
                print(f"[SERVER] Ready at {base_url}", flush=True)
                return
        except requests.exceptions.ConnectionError as e:
            last_err = e
        print(f"[SERVER] Waiting for server at {base_url} ...", flush=True)
        time.sleep(interval)
    raise RuntimeError(
        f"[SERVER] Did not become ready within {timeout}s. Last error: {last_err}"
    )
 

# ------------------------------------
# Main
# ------------------------------------

RANDOM_SEED = 42
EPISODES_PER_DIFFICULTY = 5
 
def main():
    random.seed(RANDOM_SEED)

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:7860")
    args = parser.parse_args()
    base_url = args.base_url
    server_port = 7860
 
    # Check if the server is already up; if not, start it ourselves.
    server_proc = None
    try:
        requests.get(f"{base_url}/health", timeout=2)
        print("[SERVER] Server responded, waiting until ready...", flush=True)
    except requests.exceptions.ConnectionError:
        server_proc = start_server(port=server_port)
    wait_for_server(base_url, timeout=120)
    
    try:
        all_tasks = get_tasks(base_url)
        results = []
 
        for difficulty in ["easy", "medium", "hard"]:
            pool = sorted([t for t in all_tasks if t["difficulty"] == difficulty], key=lambda t: t["id"])
            sample = random.sample(pool, min(EPISODES_PER_DIFFICULTY, len(pool)))
            print(f"\n--- {difficulty.upper()} ({len(sample)} episodes) ---")
 
            for task in sample:
                result = run_episode(task["id"], difficulty, base_url)
                results.append(result)
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
 
    finally:
        # Clean up the server subprocess if we started it
        if server_proc is not None:
            print(f"[SERVER] Shutting down uvicorn (pid={server_proc.pid})", flush=True)
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()

if __name__ == "__main__":
    main()
