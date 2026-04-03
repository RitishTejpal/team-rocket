from core.config import get_settings
from groq import Groq, RateLimitError
import time

settings = get_settings()
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=get_settings().groq_api_key)
    return _client

def build_press_release(sections: dict) -> str | None:
    abstract = sections.get("abstract") or ""
    methods = (sections.get("methods") or "")[:600]
    results = (sections.get("results") or "")[:1200]
    limitations = (sections.get("limitations") or "")[:600]
    conclusion = (sections.get("conclusion") or "")[:800]

    prompt = f"""You are a university press office writer.
Write a single press release of STRICTLY 200-250 words, based on the research below.
Rules:
- Write about COMPLETED research only. Use third person, past tense. The study has already been conducted and findings are known
- It should follow the format: introduction, methods, results, conclusion.
- Do not exaggerate, editorialize, or add claims. Stay factual.
- Do NOT use a headline, date, boilerplate or bullet points. Simply one paragraph.
- Mention the study population specifically (who was studied, how many, where).
- Mention the key finding with its actual magnitude if reported.
- Mention at least one limitation or caveat from the paper.
- Do NOT end with a result.

Abstract: {abstract}
Methods: {methods}
Results: {results}
Limitations: {limitations}
Conclusions: {conclusion}

Write only the press release text. Nothing else.
"""
    client = _get_client()

    for attempt in range(3):
        try:
            time.sleep(5.5)
            response = client.chat.completions.create(
                    model=settings.groq_model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
            time.sleep(5.5)
            content = response.choices[0].message.content
            word_count = len(content.split())
            if 180 <= word_count <= 280:
                return content
            else:
                print(f"[groq] word count {word_count}")
                return content
            
        except RateLimitError as e:
            err = str(e)
            if "tokens per day" in err or "TPD" in err:
                print(f"[groq] Daily token limit exhausted. Stop and resume tomorrow.")
                raise SystemExit(1)
            else:
                wait = 60 * (attempt + 1)
                print(f"[groq] Rate limited (per-minute). Waiting {wait}s...")
                time.sleep(wait)

        except Exception as e:
            print(f"[groq] call failed: {e}")
            return None