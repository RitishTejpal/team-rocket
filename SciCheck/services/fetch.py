from bs4 import BeautifulSoup
import re, time, requests

DOMAINS = {
    "sleep_nutrition":        '"sleep"[mh] AND "diet"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "exercise_mental_health": '"exercise"[mh] AND "mental health"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "meditation":             '"mindfulness"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "caffeine":               '"caffeine"[mh] AND "randomized controlled trial"[pt] NOT "review"[pt]',
    "social_media_wellbeing": '"social media"[mh] AND "well-being" AND "humans"[mh] NOT "review"[pt]',
}

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# -- Fetch Layer ----------

def fetch_pmcids_for_domain(domain_key: str, count=20) -> list[str]:
    """Searches for PMIds"""
    query = DOMAINS[domain_key]
    full_query = f"{query} AND open access[filter] AND has abstract[filter]"
    params = {
        "db": "pmc",
        "term": full_query,
        "retmax": count * 3,
        "retmode": "json",
        "sort": "relevance",
    }
    time.sleep(0.4)    # NCBI rate limit without API key - 3 requests per second
    r = requests.get(ESEARCH_URL, params=params)
    r.raise_for_status()

    data = r.json()
    pmcids = data["esearchresult"]["idlist"]
    print(f"[{domain_key}] fetched {len(pmcids)} PMIDs")
    return pmcids
    
def fetch_full_text(pmcid: str) -> str:
    """Given a PMCID, fetch the full text XML from PMC."""
    params = {
        "db": "pmc",
        "id": pmcid,
        "rettype": "xml",
        "retmode": "xml"
    }
    time.sleep(0.4)

    r = requests.get(EFETCH_URL, params=params)
    r.raise_for_status()

    if "<article" not in r.text:
        print(f"[{pmcid}] no full text available")
        return None
    
    if "<restricted-by>pmc</restricted-by>" in r.text:
        print(f"[{pmcid}] restricted - skipping")
        return None
    
    return r.text
 
def parse_sections(xml_text: str) -> dict:
    soup = BeautifulSoup(xml_text, "xml")
    sections = {}

    # abstract
    abstract_tag = soup.find("abstract")
    sections["abstract"] = abstract_tag.get_text(" ", strip=True) if abstract_tag else None

    sec_type_map = {
        "methods": ["methods", "materials|methods"],
        "results": ["results"],
        "limitations": ["limitations", "discussion"],
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
    
    if not sections.get("results"):
        return False, "no results section"
    
    results = sections["results"].lower()
    future_signals = [
        "will be carried out",
        "will be collected",
        "will be analyzed",
        "once the project",
        "will be performed",
        "is ongoing",
        "are ongoing",
    ]
    for signal in future_signals:
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