import json
from collections import Counter
from typing import TypedDict
from services.fetch import (
    DOMAINS,
    fetch_pmcids_for_domain,
    fetch_full_text,
    parse_sections, is_usable_paper
)
from services.engine import run_distortion_engine, DIFFICULTY_CONFIG
from services.groq_pr import build_press_release
from pathlib import Path

SCENARIOS_PATH = Path(__file__).parent / "data" / "scenarios.json"
PAPERS_PER_DOMAIN_PER_DIFFICULTY = 4
VERDICT_MAP = {
    "easy":   "overstated",
    "medium": "misinterpreted",
    "hard":   "misleading_by_omission",
}
REQUIRED_DISTORTION_COUNT = {
    # threshold check
    difficulty: (cfg["count"][0] if isinstance(cfg["count"], tuple) else cfg["count"])
    for difficulty, cfg in DIFFICULTY_CONFIG.items()
}


class Scenario(TypedDict):
    id: str
    pmcid: str
    domain: str
    difficulty: str
    paper_sections: dict
    press_release: str
    planted_distortions: list
    required_sections_for_full_score: list
    verdict_ground_truth: str


def build_scenario(scenario_id, pmcid, domain, difficulty, sections, press_release, planted) -> Scenario:
    return {
        "id": scenario_id,
        "difficulty": difficulty,
        "domain": domain,
        "pmcid": pmcid,
        "paper_sections": sections,
        "press_release": press_release,
        "planted_distortions": planted,
        "required_sections_for_full_score": list({d["found_in_section"] for d in planted if d["found_in_section"]}),
        "verdict_ground_truth": VERDICT_MAP[difficulty],
    }


def load_existing_state(path: Path) -> tuple[list[Scenario], int, set[str]]:
    """
    If a partial scenarios.json already exists, resume from it.
    Returns (all_scenarios, next_counter, used_pmcids).
    """
    if not path.exists():
        return [], 1, set()
 
    existing: list[Scenario] = json.loads(path.read_text(encoding="utf-8"))
    used = {s["pmcid"] for s in existing}
    next_id = len(existing) + 1
    print(f"[resume] found {len(existing)} existing scenarios - resuming from scenario_{next_id:03d}")
    return existing, next_id, used
 
 
def save_checkpoint(path: Path, scenarios: list[Scenario]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)
 
 
def collect_domain_pool(domain_key: str, used_pmcids: set[str]) -> list[str]:
    """
    Fetch a fresh pool of PMIDs for a domain, excluding already-used ones.
    Fetched once per domain (outside the difficulty loop) and reused.
    """
    pmcids = fetch_pmcids_for_domain(domain_key, count=80)
    return [p for p in pmcids if p not in used_pmcids]
 
 
def main():
    SCENARIOS_PATH.parent.mkdir(parents=True, exist_ok=True)
 
    # --- Resume-aware init ---
    all_scenarios, scenario_counter, used_pmcids = load_existing_state(SCENARIOS_PATH)
    failed_domains = []
 
    domain_pools = {
    domain_key: collect_domain_pool(domain_key, used_pmcids)
        for domain_key in DOMAINS
    }

    for difficulty in ["easy", "medium", "hard"]:
        for domain_key in DOMAINS:
            pool = domain_pools[domain_key]
            print(f"\n  [{domain_key}]")
            collected = 0
 
            for pmcid in pool:
                if pmcid in used_pmcids:
                    continue
                if collected >= PAPERS_PER_DOMAIN_PER_DIFFICULTY:
                    break
 
                xml = fetch_full_text(pmcid)
                if not xml:
                    continue
 
                sections = parse_sections(xml_text=xml)
                usable, reason = is_usable_paper(sections)
                if not usable:
                    print(f"    [{pmcid}] skipped - {reason}")
                    continue
                print(f"    [{pmcid}] usable")
 
                press_release = build_press_release(sections)
                if not press_release:
                    print(f"    [{pmcid}] Groq failed - skipping")
                    continue
 
                distorted_pr, planted = run_distortion_engine(sections, press_release, difficulty)
                if len(planted) < REQUIRED_DISTORTION_COUNT[difficulty]:
                    print(f"    [{pmcid}] only {len(planted)} distortions planted - skipping")
                    continue
 
                scenario = build_scenario(
                    scenario_id  = f"scenario_{scenario_counter:03d}",
                    pmcid        = pmcid,
                    domain       = domain_key,
                    difficulty   = difficulty,
                    sections     = sections,
                    press_release= distorted_pr,
                    planted      = planted,
                )
 
                all_scenarios.append(scenario)
                used_pmcids.add(pmcid)
                scenario_counter += 1
                collected += 1
 
                print(f"    [{pmcid}] -> scenario_{scenario_counter-1:03d} ({len(planted)} distortions)")
 
                save_checkpoint(SCENARIOS_PATH, all_scenarios)
 
            if collected < PAPERS_PER_DOMAIN_PER_DIFFICULTY:
                failed_domains.append((difficulty, domain_key, collected))
                print(f"    ⚠️  {collected}/{PAPERS_PER_DOMAIN_PER_DIFFICULTY} collected")
 
    print(f"\n✅ {len(all_scenarios)} scenarios -> {SCENARIOS_PATH}")
    if failed_domains:
        print(f"⚠️  shortfalls: {failed_domains}")

    domain_counts = Counter(s["domain"] for s in all_scenarios)
    print("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        print(f"  {domain}: {count}")



if __name__ == "__main__":
    main()