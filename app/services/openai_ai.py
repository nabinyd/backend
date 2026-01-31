import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

FINDINGS_SCHEMA = {
  "name": "plant_inspection_findings",
  "schema": {
    "type": "object",
    "additionalProperties": False,
    "required": ["plant_health", "issues", "recommendation_tags"],
    "properties": {
      "plant_health": {"type": "string", "enum": ["healthy", "stressed", "diseased", "unknown"]},
      "issues": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": False,
          "required": ["type", "severity", "confidence"],
          "properties": {
            "type": {"type": "string", "enum": ["leaf_spot","yellowing","wilting","pest_damage","mildew","unknown"]},
            "severity": {"type": "string", "enum": ["low","medium","high"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
          }
        }
      },
      "recommendation_tags": {"type": "array", "items": {"type": "string"}}
    }
  }
}

REPORT_SCHEMA = {
  "name": "farm_mission_report",
  "schema": {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "risk_areas", "actions", "confidence_note"],
    "properties": {
      "summary": {"type": "string"},
      "risk_areas": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": False,
          "required": ["row", "issues", "severity"],
          "properties": {
            "row": {"type": "integer"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "severity": {"type": "string", "enum": ["low","medium","high"]}
          }
        }
      },
      "actions": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": False,
          "required": ["priority", "action"],
          "properties": {
            "priority": {"type": "string", "enum": ["now","today","this_week"]},
            "action": {"type": "string"}
          }
        }
      },
      "confidence_note": {"type": "string"}
    }
  }
}

def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        # fallback: sometimes model returns whitespace/newlines; still try
        return json.loads(text.strip())

def extract_findings_from_image_url(image_url: str, crop: str) -> dict:
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": (
                    f"Analyze this {crop} plant image. "
                    "Return ONLY JSON that matches the schema. "
                    "If unsure, use 'unknown' and lower confidence."
                )},
                {"type": "input_image", "image_url": image_url}
            ]
        }],
        response_format={"type": "json_schema", "json_schema": FINDINGS_SCHEMA},
    )
    return _parse_json(resp.output_text)

def generate_report_from_findings(mission_context: dict) -> dict:
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": (
                    "You are an agriculture assistant. "
                    "Use ONLY the provided JSON findings. "
                    "Do not invent diseases not present in the data. "
                    "Write short, actionable advice for farmers.\n\n"
                    f"DATA:\n{json.dumps(mission_context, ensure_ascii=False)}"
                )}
            ]
        }],
        response_format={"type": "json_schema", "json_schema": REPORT_SCHEMA},
    )
    return _parse_json(resp.output_text)
