import json
from collections import Counter
with open("data/scenarios.json", "r", encoding="utf-8") as f:
    scenarios = json.load(f)

by_diff = {"easy": [], "medium": [], "hard": []}
for s in scenarios:
    by_diff[s["difficulty"]].append(s)

for diff, pool in by_diff.items():
    distortion_sections = Counter()
    has_limitations = sum(1 for s in pool if s["paper_sections"].get("limitations"))
    required = Counter()
    for s in pool:
        for d in s["planted_distortions"]:
            distortion_sections[d["found_in_section"]] += 1
        for r in s.get("required_sections_for_full_score", []):
            required[r] += 1
    print(f"\n{diff.upper()} ({len(pool)} scenarios)")
    print(f"  has limitations section: {has_limitations}/{len(pool)}")
    print(f"  distortion locations: {dict(distortion_sections)}")
    print(f"  required_sections: {dict(required)}")