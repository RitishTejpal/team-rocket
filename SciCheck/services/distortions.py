import re, random

def apply_scope_inflation(text: str) -> str:
    patterns = [
        (r'\bin mice\b', lambda: random.choice(["in humans", ""])),
        (r'\bin vitro\b', lambda: random.choice(["in humans", ""])),
        (r'\banimal model\b', lambda: random.choice(["in humans", ""])),
        (r'\bin (?:elderly|older) (?:adults|women|men|patients)\b', 'in all adults'),
        (r'\bin (?:women|men) only\b', 'in adults'),
        (r'\bpilot study\b', 'study'),
        (r'\bsingle.?(?:center|site|institution)\b', 'multi-center'),
    ]

    for pattern, replacement in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            replacement = replacement() if callable(replacement) else replacement
            original_snippet = text[max(0, match.start()-30):match.end()+30]
            distorted_text = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)

            record = {
                "type": "scope_inflation",
                "original_text": original_snippet,
                "distorted_to": replacement,
            }
            return distorted_text, record
    return None

def apply_certainty_inflation(text: str) -> str:
    patterns = [
        (r'\bmay\b', 'demonstrably'),
        (r'\bsuggests\b', 'confirms'),
        (r'\bappears to\b', 'is proven to'),
        (r'\bcould\b', 'will'),
        (r'\bmight\b', 'does'),
        (r'\bassess(?:ed|ing)?\s+the\s+effectiveness\b', 'confirm the effectiveness'),
        (r'\baim(?:ed)?\s+to\s+(?:assess|evaluate|examine)\b', 'demonstrated'),
        (r'\bobserved\b', 'proved'),
        (r'\bshowed\b', 'confirmed'),
        (r'\bindicated?\b', 'proved'),
    ]

    for pattern, replacement in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            original_snippet = text[max(0, match.start()-30):match.end()+30]
            distorted_text = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)

            record = {
                "type": "certainty_inflation",
                "original_text": original_snippet,
                "distorted_to": replacement,
            }
            return distorted_text, record
    return None

def apply_stat_fabrication(text: str) -> str:
    pattern = r'(\d+(?:\.\d+)?)\s*%'
    effect_keywords = r'(?:improved?|reduced?|increased?|decreased?|change[d]?|difference|effect|gain|loss)'
    priority_pattern = rf'{effect_keywords}.{{0,40}}?(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%.{{0,40}}?{effect_keywords}'
    
    priority_match = re.search(priority_pattern, text, re.IGNORECASE)
    if priority_match:
        raw = priority_match.group(1) or priority_match.group(2)
        match = re.search(rf'\b{re.escape(raw)}\s*%', text)
    else:
        match = re.search(pattern, text)

    if match:
        real_number = float(re.search(r'\d+(?:\.\d+)?', match.group(0)).group())
        for _ in range(10):
            fabricated_number = round(real_number * random.uniform(3.0, 5.0))
            if fabricated_number > 100:
                fabricated_number = round(real_number / random.uniform(3.0, 5.0))
            if fabricated_number != round(real_number):
                break

        record = {
            "type": "stat_fabrication",
            "original_text": f"{real_number}%",
            "distorted_to": f"{fabricated_number}%",
        }
        return f"{fabricated_number}%", record
    return None

def apply_magnitude_distortion(text: str) -> str:
    patterns = [
        (r'\bsmall\b', lambda: random.choice(["dramatic", "significant", "major"])),
        (r'\bmodest\b', lambda: random.choice(["dramatic", "significant", "major"])),
        (r'\b\d+(?:\.\d+)?\s*%\b', lambda: random.choice(["dramatic", "a wide range", "a significant spread"])),
    ]

    for pattern, replacement in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            replacement = replacement() if callable(replacement) else replacement
            original_snippet = text[max(0, match.start()-30):match.end()+30]
            distorted_text = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)

            record = {
                "type": "magnitude_distortion",
                "original_text": original_snippet,
                "distorted_to": replacement,
            }
            return distorted_text, record
    return None

def apply_hedging_stripped(text: str) -> str:
    trigger_pattern = r'(?:preliminary|further research|small sample|limitations|replication needed)'
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    for i, sentence in enumerate(sentences):
        if re.search(trigger_pattern, sentence, re.IGNORECASE):
            if i + 1 < len(sentences):
                combined = sentence.strip() + " " + sentences[i + 1].strip()
            else:
                combined = sentence.strip()
            distorted_text = text.replace(combined, "", 1).strip()
            record = {
                "type": "hedging_stripped",
                "original_text": combined,
                "distorted_to": "",
                "found_in_section": None,
                "severity": "hard"
            }
            return distorted_text, record
    return None

def apply_population_generalized(text: str) -> str:
    patterns = [
        (r'\b\d+\s+(?:[A-Z][a-z]+\s+)?(?:adults|women|men|patients|children)\b',
        lambda: random.choice(["people", "adults", "individuals"])),
        (r'\baged\s+\d+[\s\-–]+\d+\b',"adults"),
        (r'\b(?:elderly|older)\s+(?:adults|women|men|patients)\b',"adults"),
    ]

    for pattern, replacement in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            replacement = replacement() if callable(replacement) else replacement
            original_snippet = match.group(0)
            distorted_text = text.replace(original_snippet, replacement, 1)

            record = {
                "type": "population_generalized",
                "original_text": original_snippet,
                "distorted_to": replacement,
            }
            return distorted_text, record
    return None

def apply_causal_overclaim(text: str) -> str:
    patterns = [
        (r'\bassociated with\b', lambda: random.choice(["causes", "leads to", "results in"])),
        (r'\bcorrelated with\b', lambda: random.choice(["causes", "leads to", "results in"])),
        (r'\blinked to\b', lambda: random.choice(["causes", "leads to", "results in"])),
        (r'\brelationship between\b', lambda: random.choice(["causes", "leads to", "results in"])),
    ]

    for pattern, replacement in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            replacement = replacement() if callable(replacement) else replacement
            original_snippet = text[max(0, match.start()-30):match.end()+30]
            distorted_text = re.sub(pattern, replacement, text, count=1, flags=re.IGNORECASE)

            record = {
                "type": "causal_overclaim",
                "original_text": original_snippet,
                "distorted_to": replacement,
            }
            return distorted_text, record
    return None

def apply_misleading_omission(sections: dict) -> dict | None:
        """
        Doesn't transform text.
        Identifies the primary endpoint failure in results + limitations.
        Returns a record of what the PR should silently omit.
        The PR will only mention the secondary/subgroup finding.
        """
        results_text = sections.get("results", "") or ""
        limitations_text = sections.get("limitations", "") or ""

        primary_fail_patterns = [
            r'primary (?:endpoint|outcome).{0,80}(?:not significant|no significant|failed|did not|p\s*[=>]\s*0\.0[1-9])',
            r'(?:did not|did not significantly).{0,60}(?:improve|change|differ|reach)',
            r'no significant (?:difference|effect|change).{0,60}(?:primary|main|overall)',
            r'failed to (?:reach|achieve|demonstrate).{0,60}(?:significance|significant)',
            r'(?:non-significant|not statistically significant|ns\b).{0,60}',
            r'p\s*[=>]\s*0\.[1-9]\d*\b.{0,60}(?:primary|main|overall)',
            r'did not (?:differ|change|improve|show).{0,60}(?:significant|between groups)',
            r'no (?:statistically significant|significant) (?:difference|effect|change)',
        ]

        matched_snippet = None
        for pattern in primary_fail_patterns:
            match = re.search(pattern, results_text, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 20)
                end = min(len(results_text), match.end() + 20)
                matched_snippet = results_text[start:end].strip()
                break

        limitations_snippet = None
        limitations_patterns = [
            r'[^.]*\b(?:underpowered|limited sample|small sample|pilot|exploratory)\b[^.]*\.',
            r'[^.]*\bprimary (?:endpoint|outcome)\b[^.]*\b(?:not|failed|no)\b[^.]*\.',
        ]
        for pattern in limitations_patterns:
            match = re.search(pattern, limitations_text, re.IGNORECASE)
            if match:
                limitations_snippet = match.group(0).strip()
                break

        if not matched_snippet:
            return None

        return {
            "type": "misleading_omission",
            "original_text": matched_snippet,
            "distorted_to": "[omitted from press release]",
            "limitations_corroboration": limitations_snippet,
        }