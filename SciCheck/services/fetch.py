from bs4 import BeautifulSoup
import re, time, requests
from requests.exceptions import RequestException

DOMAINS = {
    "sleep_nutrition":              '"sleep"[mh] AND "diet"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "exercise_mental_health":       '"exercise"[mh] AND "mental health"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "meditation":                   '"mindfulness"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "caffeine":                     '"caffeine"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "social_media_wellbeing":       '"social media"[mh] AND "well-being" AND "humans"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "yoga_stress":                  '"yoga"[mh] AND "stress"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "omega3_cognition":             '"fatty acids, omega-3"[mh] AND "cognition"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "physical_activity_elderly":    '"exercise"[mh] AND "aged"[mh] AND "cognitive function"[tiab] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "weight_loss_behavior":         '"weight loss"[mh] AND "behavior therapy"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "smoking_cessation":            '"smoking cessation"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "vitamin_d_immunity":           '"vitamin d"[mh] AND "immunity"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "gut_microbiome":               '"probiotics"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "alcohol_cognition":            '"alcohol drinking"[mh] AND "cognition"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "screen_time_sleep":            '"screen time"[tiab] AND "sleep"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "intermittent_fasting":         '"intermittent fasting"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "cold_exposure":                '"cold temperature"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "resistance_training":          '"resistance training"[mh] AND "mental health"[tiab] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "pain_mindfulness":             '"chronic pain"[mh] AND "mindfulness"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "blue_light":                   '"blue light"[tiab] AND "sleep"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "loneliness_intervention":      '"loneliness"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "music_therapy_anxiety":        '"music therapy"[mh] AND "anxiety"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "art_therapy_depression":       '"art therapy"[mh] AND "depression"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "nature_exposure_stress":       '"nature"[tiab] AND "stress"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "heat_therapy_cardiovascular":  '"hyperthermia, induced"[mh] AND "cardiovascular system"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "massage_therapy_pain":         '"massage"[mh] AND "chronic pain"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "acupuncture_pain":             '"acupuncture therapy"[mh] AND "chronic pain"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "sleep_deprivation_cognition":  '"sleep deprivation"[mh] AND "cognition"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "napping_performance":          '"sleep"[mh] AND "nap"[tiab] AND "cognitive performance"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "sugar_behavior_children":      '"dietary sucrose"[mh] AND "child behavior"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "time_restricted_eating":       '"time-restricted eating"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "dietary_fiber_gut":            '"dietary fiber"[mh] AND "gastrointestinal microbiome"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "protein_intake_muscle":        '"dietary proteins"[mh] AND "muscle strength"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "zinc_immunity":                '"zinc"[mh] AND "immunity"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "breathing_exercises_anxiety":  '"breathing exercises"[mh] AND "anxiety"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "gratitude_wellbeing":          '"personal satisfaction"[mh] AND "gratitude"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "standing_desk_health":         '"sedentary behavior"[mh] AND "standing"[tiab] AND "workplace"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "workplace_stress_intervention":'"occupational stress"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "social_connection_health":     '"social isolation"[mh] AND "health"[tiab] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "light_therapy_depression":     '"phototherapy"[mh] AND "depressive disorder, seasonal"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    "alcohol_sleep":                '"alcohol drinking"[mh] AND "sleep wake disorders"[mh] AND "randomized controlled trial"[pt] AND "humans"[mh] NOT "review"[pt]',
    }

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


# -- Fetch Layer ----------

def fetch_pmcids_for_domain(domain_key: str, count=20) -> list[str]:
    """
    Searches for PMCIds, given a domain key (must be in DOMAINS).
    Returns list of PMCIDs.
    """
    query = DOMAINS[domain_key]
    full_query = f"{query} AND open access[filter] AND has abstract[filter]"
    params = {
        "db": "pmc",
        "term": full_query,
        "retmax": count * 3,
        "retmode": "json",
        "sort": "relevance",
    }

    for attempt in range(3):
        try:
            time.sleep(1.0 + attempt)
            r = requests.get(ESEARCH_URL, params=params, timeout=30)
            r.raise_for_status()

            data = r.json()
            if "esearchresult" not in data or "idlist" not in data["esearchresult"]:
                print(f"[{domain_key}] unexpected response: {data}")
                time.sleep(5 * (attempt + 1))
                continue

            pmcids = data["esearchresult"]["idlist"]
            print(f"[{domain_key}] fetched {len(pmcids)} PMCIDs")
            return pmcids

        except RequestException as e:
            print(f"[{domain_key}] attempt {attempt+1} failed: {e}")
            time.sleep(5 * (attempt + 1))

    print(f"[{domain_key}] giving up after 3 attempts - returning empty list")
    return []
    
def fetch_full_text(pmcid: str) -> str:
    """
    Given a PMCID, fetch the full text XML from PMC.
    Returns XML text if successful, None if not available or restricted.
    """
    params = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml"
    }

    for attempt in range(3):
        try:
            time.sleep(0.4 + attempt) # 0.4s, 1.4s, 2.4s -> back off on retry
            r = requests.get(EFETCH_URL, params=params, timeout=30)
            r.raise_for_status()

            if "<article" not in r.text:
                print(f"[{pmcid}] no full text available")
                return None
            if "<restricted-by>pmc</restricted-by>" in r.text:
                print(f"[{pmcid}] restricted - skipping")
                return None
            return r.text

        except RequestException as e:
            print(f"[{pmcid}] attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print(f"[{pmcid}] giving up after 3 attempts")
                return None
            time.sleep(2 ** attempt)
 
def parse_sections(xml_text: str) -> dict:
    """
    Extract required sections from the XML. 
    Returns dict with keys: abstract, methods, results, limitations, stats.
    """
    soup = BeautifulSoup(xml_text, "xml")
    sections = {}

    # abstract
    abstract_tag = soup.find("abstract")
    sections["abstract"] = abstract_tag.get_text(" ", strip=True) if abstract_tag else None

    sec_type_map = {
        "methods": ["methods", "materials|methods"],
        "results": ["results"],
        "limitations": ["limitations", "discussion"],
        "conclusion": ["conclusion"],
        }
    
    for key, sec_types in sec_type_map.items():
        found = None
        for sec_type in sec_types:
            found = soup.find("sec", {"sec-type": sec_type})
            if found: break

        if not found:
            for sec in soup.find_all("sec"):
                title = sec.find("title")
                if title and key.lower() in title.get_text().lower():
                    found = sec
                    break

        sections[key] = found.get_text(" ", strip=True) if found else None

    if sections["results"]:
        stat_pattern = r'[^.]*\b\d+(?:\.\d+)?(?:\s*%|[\s,]p\s*[<=]\s*0\.\d+|[\s,]CI)[^.]*\.'
        stats_sentences = re.findall(stat_pattern, sections["results"], re.IGNORECASE)
        sections["stats"] = " ".join(stats_sentences) if stats_sentences else None
    else:
        sections["stats"] = None
    return sections

def is_usable_paper(sections: dict) -> tuple[bool, str]:
    """
    Returns (True, "") if paper is usable.
    Returns (False, reason) if paper should be skipped.
    """
    if not sections.get("abstract"):
        return False, "no abstract"

    protocol_signals = [
        "currently conducting",
        "aims to assess",
        "will be carried out",
        "will be collected",
        "will be analyzed",
        "once the project",
        "will be performed",
        "is ongoing",
        "are ongoing",
    ]
    abstract = (sections.get("abstract") or "").lower()
    if any(sig in abstract for sig in protocol_signals):
        return False, "protocol paper (future tense abstract)"

    if not sections.get("results"):
        return False, "no results section"
    
    results = sections["results"].lower()
    for signal in protocol_signals:
        if signal in results:
            return False, f"protocol paper detected: '{signal}'"
    
    has_numbers = bool(re.search(r'\d+(?:\.\d+)?\s*%|p\s*[<=]\s*0\.\d+', 
                                  (sections.get("results") or "") + 
                                  (sections.get("abstract") or "")))
    if not has_numbers:
        return False, "no statistical content found"
    
    rct_signals = [
        r'\brandomized\b', r'\brandomised\b',
        r'\bcontrol(?:led)?\s+group\b', r'\bintervention\s+group\b',
        r'\btreatment\s+group\b', r'\bplacebo\b',
        r'\bbaseline\b',
        r'\bparticipants\s+(?:were|completed|showed)\b',
    ]
    rct_text = (sections.get("abstract") or "") + " " + (sections.get("results") or "")
    if not any(re.search(p, rct_text, re.IGNORECASE) for p in rct_signals):
        return False, "not an intervention study"
    
    return True, ""