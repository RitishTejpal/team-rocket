import random
from SciCheck.services.distortions import (
    apply_scope_inflation, apply_certainty_inflation,
    apply_magnitude_distortion, apply_hedging_stripped,
    apply_population_generalized, apply_causal_overclaim,
    apply_misleading_omission, apply_stat_fabrication
)

DISTORTION_FN_MAP = {
    "scope_inflation": apply_scope_inflation,
    "certainty_inflation": apply_certainty_inflation,
    "magnitude_distortion": apply_magnitude_distortion,
    "hedging_stripped": apply_hedging_stripped,
    "population_generalized": apply_population_generalized,
    "causal_overclaim": apply_causal_overclaim,
}

DIFFICULTY_CONFIG = {
    "easy": {
        "section":  "abstract",
        "allowed":  ["scope_inflation", "certainty_inflation", "magnitude_distortion"],
        "count":    1,
        "severity": "low",
        "requires_misleading_omission": False,
    },
    "medium": {
        "section":  "methods",
        "allowed":  ["hedging_stripped", "population_generalized",
                     "causal_overclaim", "stat_fabrication"],
        "count":    (1, 2),
        "severity": "medium",
        "requires_misleading_omission": False,
    },
    "hard": {
        "section":  "results",
        "allowed":  ["hedging_stripped", "population_generalized",
                     "causal_overclaim", "certainty_inflation", "magnitude_distortion"],
        "count":    3,               # + misleading_omission = 3 total
        "severity": "high",
        "requires_misleading_omission": True,
    },
}

def run_distortion_engine(sections: dict, press_release: str, difficulty: str) -> tuple[str, list]:
    """
    Takes the real paper sections + difficulty level.
    Returns (distorted_text, planted_distortions).
    
    distorted_text -> gets passed to Groq to write as PR prose.
    planted_distortions -> ground truth stored in scenario JSON.
    """
    config = DIFFICULTY_CONFIG[difficulty]
    planted = []

    working_text = press_release

    # Step 1: misleading_omission for hard
    if config["requires_misleading_omission"]:
        record = apply_misleading_omission(sections)
        if record:
            record["found_in_section"] = "results"
            record["severity"] = "high"
            planted.append(record)

    # Step 2: stat_fabrication (special — reads stats, injects into working_text)
    if "stat_fabrication" in config["allowed"]:
        stats_text = sections.get("stats") or ""
        result = apply_stat_fabrication(stats_text)   # pass stats text specifically
        if result is not None:
            fabricated_claim, record = result
            record["found_in_section"] = "stats"
            record["severity"] = config["severity"]
            planted.append(record)
            # inject the fabricated number into working_text so Groq sees it
            working_text = working_text + f" The study reported {fabricated_claim}."

    # Step 3: regular distortions on working_text 
    regular = [d for d in config["allowed"] if d != "stat_fabrication"]
    random.shuffle(regular)
    
    count = config["count"] if isinstance(config["count"], int) else random.randint(*config["count"])

    # track how many stat_fabrication already consumed from count
    already_planted = len([p for p in planted 
                       if p["type"] in ("stat_fabrication", "misleading_omission")])
    remaining = count - already_planted

    applied = 0
    for name in regular:
        if applied >= remaining:
            break
        fn = DISTORTION_FN_MAP[name]
        result = fn(working_text)
        if result is None:
            continue
        distorted_text, record = result
        record["found_in_section"] = config["section"]
        record["severity"] = config["severity"]
        planted.append(record)
        working_text = distorted_text
        applied += 1

    return working_text, planted