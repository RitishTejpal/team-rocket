import random
from SciCheck.services.distortions import (
    apply_scope_inflation, apply_certainty_inflation,
    apply_magnitude_distortion, apply_hedging_stripped,
    apply_population_generalized, apply_causal_overclaim,
    apply_misleading_omission, apply_stat_fabrication
)

# stat_fabrication is handled separately in run_distortion_engine (Step 2)
# because it reads from sections["stats"], not from working_text
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
        "count":    2,
        "severity": "medium",
        "requires_misleading_omission": False,
    },
    "hard": {
        "section":  "results",
        "allowed":  ["hedging_stripped", "population_generalized",
                     "causal_overclaim", "certainty_inflation", "magnitude_distortion"],
        "count":    (3, 5),
        "severity": "high",
        "requires_misleading_omission": True,
    },
}

def run_distortion_engine(sections: dict, press_release: str, difficulty: str) -> tuple[str, list]:
    """
    Takes the press_release + difficulty level.
    Returns (distorted_text, planted_distortions).
    """
    config = DIFFICULTY_CONFIG[difficulty]
    planted = []

    working_text = press_release

    # Step 1: misleading_omission for hard
    if config["requires_misleading_omission"]:
        record = apply_misleading_omission(sections)
        if not record:
            return working_text, []
        record["found_in_section"] = "results"
        if record.get("limitations_corroboration"):
            record["also_in_section"] = "limitations"
        record["severity"] = "high"
        planted.append(record)

    # Step 2: stat_fabrication
    if "stat_fabrication" in config["allowed"]:
        stats_text = sections.get("stats") or ""
        result = apply_stat_fabrication(stats_text)
        if result is not None:
            fabricated_number, record = result
            real_number = record["original_text"]
            if real_number in working_text:
                working_text = working_text.replace(real_number, f"{fabricated_number}%", 1)
                record["found_in_section"] = "stats"
                record["severity"] = config["severity"]
                planted.append(record)

    # Step 3: regular distortions on working_text 
    regular = [d for d in config["allowed"] if d != "stat_fabrication"]
    random.shuffle(regular)
    
    count = config["count"] if isinstance(config["count"], int) else random.randint(*config["count"])
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