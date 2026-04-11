---
title: SciCheck
emoji: 🔬
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# SciCheck: A Scientific Claim Verification Environment for LLM Agents

In today's world, where fact-checking has become a rare event, it's important to ponder what their origin is. Talking specifically about science misinformations - they hardly originate in tabloids, rather in a press release. Then journalists copy them verbatim, and public reads only the headlines. Nobody goes back to the paper.

SciCheck is a multi-step investigation environment where an AI agent must run a fact-check: firstly, read the press release, then systematically investigate the underlying research to find where the science was lost in translation, and what is the "real finding" - if at all.

---

## Core Premise

The agent receives only a press release. It cannot see the paper. Through a series of investigative tools - fetching the abstract, methods, results, limitations and statistics - it must reconstruct what the research actually found and identify every point where the PR overstates, misinterprets or silently omits. Press releases in SciCheck are procedurally generated from real PubMed abstracts with programmatically applied distortions, giving the environment infinite unique episodes with perfectly deterministic ground truth.

---

## Environment

**Base URL:** `https://akanksha-ak-th-scicheck.hf.space`

| Endpoint | Method | Description |
|---|---|---|
| `/reset` | POST | Start a new episode |
| `/step` | POST | Execute one agent action |
| `/state` | GET | Full internal episode state (debug) |
| `/grader` | GET | Detailed scoring breakdown |
| `/tasks` | GET | Enumerate all available scenarios |
| `/health` | GET | Liveness check |

---

## Action Space

Each step the agent chooses one of:

| Action | Effect |
|---|---|
| `fetch_abstract` | Reveals the paper abstract |
| `fetch_methods` | Reveals the methods section |
| `fetch_results` | Reveals the results section |
| `fetch_limitations` | Reveals the limitations section |
| `fetch_stats` | Reveals the statistics section |
| `submit_verdict` | Ends the episode, triggers grader |

---

## Scoring

Each fetch action is evaluated immediately:
- `+0.1` if the fetched section contains a planted distortion
- `-0.1` if the fetched section contains no distortion
- `-0.2` penalty if `limitations` was never fetched before submitting
- `-0.3` penalty if max steps exceeded without submitting

Final score is a weighted combination:
- **30%** trajectory score (fetch efficiency)
- **70%** verdict score (accuracy of final diagnosis)

All scores are normalized and clamped to `[0.0, 1.0]`.

---

## Difficulty Levels

| Difficulty | Distortion Section | Distortion Types | Max Steps |
|---|---|---|---|
| Easy | Abstract | scope_inflation, certainty_inflation, magnitude_distortion | 3 |
| Medium | Methods | hedging_stripped, population_generalized, causal_overclaim, stat_fabrication | 7 |
| Hard | Results | Multiple + misleading_omission | 10 |

---

## Distortion Taxonomy

| Type | Description |
|---|---|
| `scope_inflation` | Finding generalized beyond its actual scope |
| `certainty_inflation` | Uncertain result presented as definitive |
| `magnitude_distortion` | Effect size exaggerated or understated |
| `hedging_stripped` | Qualifying language removed from claims |
| `population_generalized` | Specific population generalized to all |
| `causal_overclaim` | Correlation presented as causation |
| `misleading_omission` | Key limitations silently omitted |
| `stat_fabrication` | Statistics altered |

---

## Setup & Usage

### Environment Variables
```bash
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=your-model-identifier
HF_TOKEN=your-huggingface-token
```

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Generate scenarios (first time only)
python generate_scenarios.py

# Start the server
uvicorn server.app:scicheck_app --host 0.0.0.0 --port 7860

# Run baseline inference
python inference.py --base-url http://localhost:7860
```

### Running Against Deployed Space
```bash
python inference.py --base-url https://akanksha-ak-th-scicheck.hf.space
```

---

## Baseline Results

Naive LLM agent (`seed=42`, `temperature=0.0`) across 15 episodes (5 per difficulty):

| Difficulty | Avg Score | Notes |
|---|---|---|
| Easy | ~0.56 | Correctly identifies overstated verdicts, fetches abstract inconsistently |
| Medium | ~0.10 | Sometimes identifies misinterpreted verdicts, misses specific divergence types |
| Hard | ~0.11 | Fetches results section correctly but misses divergence type identification |

Full results in `baseline_results.json`.

---

## Project Structure

SciCheck/  
    │  .env.example  
    │  .gitignore  
    │  .python-version  
    │  baseline_results.json  
    │  Dockerfile  
    │  generate_scenarios.py  
    │  inference.py  
    │  LICENSE  
    │  models.py  
    │  openenv.yaml  
    │  pyproject.toml   
    │  README.md  
    │  requirements.txt  
    │  structure.txt  
    │  SYSTEM_DESIGN.md  
    │  uv.lock  
    │
    ├─core  
    │  │  schema.py  
    │  └─ __init__.py  
    │          
    ├─data  
    │  │  data_lookup.py  
    │  └─ scenarios.json  
    │          
    ├─server  
    │  │  app.py  
    │  │  environment.py  
    │  │  session_store.py  
    │  │  __init__.py  
    │  │  
    │  └─ routes  
    │     │  debug.py  
    │     │  episode.py  
    │     │  meta.py  
    │     └─ __init__.py  
    │  
    └─services  
    │  distortions.py  
    │  engine.py  
    │  fetch.py  
    │  groq_pr.py  
    └─  __init__.py  

---

## License

MIT License - see `LICENSE` for details.
