"""Theme identification and scoring for product complaint clusters using Sonnet."""

import logging

from shared.openrouter_client import SONNET, call_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product opportunity analyst for a startup research pipeline.

Given a set of user complaints about a specific software product, your job is to:
1. Identify distinct recurring problem themes
2. Score each theme on three dimensions
3. Select the most vivid representative quotes for each theme

Scoring dimensions (0.0 to 1.0):
- intensity: How frustrated are users? (0.3=mild annoyance, 0.6=clear frustration, 0.9=rage-quitting/cancelling)
- wtp: Willingness to pay for a better solution (0.3=no signal, 0.6=mentions alternatives, 0.9=explicitly switching/paying)
- ai_replaceability: Could an AI-native tool realistically solve this? (0.3=no, 0.6=partially, 0.9=perfect fit)

Respond with JSON:
{
  "themes": [
    {
      "theme": "short descriptive name",
      "complaint_count": <number of complaints in this theme>,
      "intensity_score": <float>,
      "wtp_score": <float>,
      "ai_replaceability_score": <float>,
      "sample_quotes": ["quote1", "quote2", "quote3"],
      "raw_indices": [<indices of complaints that belong to this theme>]
    }
  ]
}

Guidelines:
- Identify 1-5 themes maximum. Merge similar themes, don't over-split.
- sample_quotes must be verbatim excerpts from the complaints. Pick quotes that:
  1. Are specific (mention a real pain, not vague frustration)
  2. Show emotional intensity or switching intent
  3. Would convince a founder this is a real problem worth solving
- A complaint can belong to multiple themes if relevant
- Focus on themes with 2+ complaints — single mentions can be grouped into a misc theme"""


async def identify_themes(product_name: str, complaints: list[dict]) -> list[dict]:
    """Identify themes and scores for a product's complaints.

    Returns list of theme dicts ready for pipeline_ranked insertion.
    Falls back to a single generic theme if LLM call fails.
    """
    user_prompt = f"Product: {product_name}\n\nComplaints ({len(complaints)} total):\n\n"
    for idx, complaint in enumerate(complaints):
        body = complaint.get("body", "")[:800]
        user_prompt += f"[{idx}] {body}\n\n"

    try:
        response = await call_llm_json(SONNET, SYSTEM_PROMPT, user_prompt)
        themes = response.get("themes", [])

        # Map raw_indices back to actual complaint UUIDs
        result = []
        for theme in themes:
            raw_indices = theme.get("raw_indices", [])
            raw_ids = [
                str(complaints[i]["id"])
                for i in raw_indices
                if i < len(complaints) and complaints[i].get("id")
            ]

            intensity = max(0.0, min(1.0, float(theme.get("intensity_score", 0.5))))
            wtp = max(0.0, min(1.0, float(theme.get("wtp_score", 0.5))))
            ai_rep = max(0.0, min(1.0, float(theme.get("ai_replaceability_score", 0.5))))
            composite = round(0.35 * intensity + 0.35 * wtp + 0.30 * ai_rep, 3)

            result.append({
                "cluster_type": "product",
                "product_name": product_name,
                "problem_theme": theme.get("theme", "General complaints"),
                "complaint_count": theme.get("complaint_count", len(raw_indices)),
                "raw_ids": raw_ids,
                "sample_complaints": theme.get("sample_quotes", [])[:5],
                "intensity_score": round(intensity, 3),
                "wtp_score": round(wtp, 3),
                "ai_replaceability_score": round(ai_rep, 3),
                "composite_score": composite,
                "is_weak_signal": False,
            })

        logger.info(f"{product_name}: identified {len(result)} themes")
        return result

    except Exception as e:
        logger.error(f"Theme identification failed for {product_name}: {e}")
        return []


async def synthesize_unmet_needs(complaints: list[dict], top_n: int = 5) -> list[dict]:
    """Synthesize recurring themes from complaints with no product mentioned.

    One Sonnet call for all unmet needs complaints.
    """
    if not complaints:
        return []

    system_prompt = f"""You are a market researcher identifying unmet software needs.

Given complaints where users describe frustrations but don't name a specific product,
identify the top {top_n} recurring themes — problems that appear repeatedly with no good solution.

These are market gaps, not product complaints.

Respond with JSON:
{{
  "themes": [
    {{
      "theme": "concise problem description",
      "complaint_count": <estimated number of complaints about this>,
      "sample_quotes": ["quote1", "quote2", "quote3"],
      "ai_replaceability_score": <float 0-1, could AI solve this?>,
      "raw_indices": [<indices>]
    }}
  ]
}}"""

    user_prompt = f"Unmet need complaints ({len(complaints)} total):\n\n"
    for idx, complaint in enumerate(complaints):
        body = complaint.get("body", "")[:600]
        user_prompt += f"[{idx}] {body}\n\n"

    try:
        response = await call_llm_json(SONNET, system_prompt, user_prompt)
        themes = response.get("themes", [])

        result = []
        for theme in themes:
            raw_indices = theme.get("raw_indices", [])
            raw_ids = [
                str(complaints[i]["id"])
                for i in raw_indices
                if i < len(complaints) and complaints[i].get("id")
            ]

            ai_rep = max(0.0, min(1.0, float(theme.get("ai_replaceability_score", 0.5))))

            result.append({
                "cluster_type": "unmet_need",
                "product_name": None,
                "problem_theme": theme.get("theme", "Unnamed gap"),
                "complaint_count": theme.get("complaint_count", len(raw_indices)),
                "raw_ids": raw_ids,
                "sample_complaints": theme.get("sample_quotes", [])[:5],
                "intensity_score": 0.0,
                "wtp_score": 0.0,
                "ai_replaceability_score": round(ai_rep, 3),
                "composite_score": round(ai_rep * 0.5, 3),  # unmet needs ranked by AI fit only
                "is_weak_signal": False,
            })

        logger.info(f"Identified {len(result)} unmet need themes")
        return result

    except Exception as e:
        logger.error(f"Unmet needs synthesis failed: {e}")
        return []
