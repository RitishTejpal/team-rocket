from SciCheck.core.config import get_settings
from groq import Groq

def build_press_release(sections: dict) -> str | None:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)
    abstract    = sections.get("abstract") or ""
    results     = sections.get("results") or ""
    limitations = sections.get("limitations") or ""

    prompt = f"""You are a university press office writer.
Write a single press release of exactly 200-250 words, based on the reasearch below.
Rules:
- Write in third person, present tense.
- Do not exaggerate, editorialize, or add claims. Stay factual.
- Do NOT use a headline, date, boilerplate or bullet points. Simply one paragraph.
- Mention the study population specifically (who was studied, how many, where).
- Mention the key finding with its actual magnitude if reported.
- Mention at least one limitation or caveat from the paper.

Abstract: {abstract}
Results: {results}
Limitations: {limitations}

Write only the press release text. Nothing else.
"""
    try:
        response = client.chat.completions.create(
                model=settings.groq_model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"[groq] call failed: {e}")