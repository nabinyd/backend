import os, json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _build_prompt(report_json: dict, lang: str):
    # Keep input small: include only stats + top previews
    small = {
        "stats": report_json.get("stats", {}),
        "top_hotspots": report_json.get("hotspots", [])[:30],
        "frames_preview": report_json.get("frames_preview", [])[:10],
    }

    system = (
        "You are an agricultural field inspection assistant.\n"
        "You MUST use ONLY the provided JSON data.\n"
        "Do NOT guess diseases that are not in 'top_issues'.\n"
        "If data is insufficient, say so.\n"
        "Return STRICT JSON only (no markdown)."
    )

    user = {
        "language": lang,
        "task": "Generate farmer-friendly report based on provided inspection stats.",
        "data": small,
        "output_schema": {
            "lang": "ne|en",
            "summary": "string (2-4 lines)",
            "risk_level": "low|medium|high",
            "key_findings": ["string"],
            "priority_actions": ["string"],
            "notes": ["string"]
        }
    }

    return system, json.dumps(user, ensure_ascii=False)

def generate_farmer_report(report_json: dict, lang: str = "ne") -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    system, user_msg = _build_prompt(report_json, lang)

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
    )

    text = resp.choices[0].message.content.strip()
    # Must be JSON:
    return json.loads(text)
