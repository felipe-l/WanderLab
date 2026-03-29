"""Haiku-based complaint scorer for Filter."""

import logging

from shared.openrouter_client import HAIKU, call_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a complaint scoring agent for a product research pipeline.

For each complaint about a paid software product, score it on three dimensions (0.0 to 1.0):

1. **intensity** — How frustrated is the user?
   - 0.0-0.3: Mild annoyance, casual mention
   - 0.4-0.6: Clear frustration, specific pain points
   - 0.7-1.0: Rage-quitting, threatening to cancel, emotional language

2. **wtp** (willingness to pay) — Does the user signal they'd pay for a better alternative?
   - 0.0-0.3: No mention of money, switching, or alternatives
   - 0.4-0.6: Mentions looking for alternatives, compares products
   - 0.7-1.0: Explicitly says they'd pay, mentions pricing, switching costs

3. **ai_replaceability** — Could an AI-powered tool realistically solve this complaint?
   - 0.0-0.3: The complaint is about something AI can't help with (hardware, network, etc.)
   - 0.4-0.6: AI could partially address this (automation, smart defaults)
   - 0.7-1.0: AI is a natural fit (content generation, data analysis, personalization)

Respond with a JSON object containing a "results" array. Each result has:
- "index": the index of the item
- "intensity": float 0.0-1.0
- "wtp": float 0.0-1.0
- "ai_replaceability": float 0.0-1.0
- "rationale": one sentence explaining the scores"""

BATCH_SIZE = 5


async def score_complaints(complaints: list[dict]) -> list[dict]:
    """Score a list of raw complaints. Returns scored records ready for insertion."""
    scored = []

    for i in range(0, len(complaints), BATCH_SIZE):
        batch = complaints[i:i + BATCH_SIZE]

        user_prompt = "Score the following complaints:\n\n"
        for idx, complaint in enumerate(batch):
            user_prompt += f"--- Complaint {idx} ---\n"
            if complaint.get("product_mentioned"):
                user_prompt += f"Product: {complaint['product_mentioned']}\n"
            user_prompt += f"Text: {complaint.get('body', '')[:1500]}\n\n"

        try:
            response = await call_llm_json(HAIKU, SYSTEM_PROMPT, user_prompt)
            results = response.get("results", [])

            result_map = {r["index"]: r for r in results}
            for idx, complaint in enumerate(batch):
                if idx in result_map:
                    r = result_map[idx]
                    intensity = max(0.0, min(1.0, float(r.get("intensity", 0.5))))
                    wtp = max(0.0, min(1.0, float(r.get("wtp", 0.5))))
                    ai_rep = max(0.0, min(1.0, float(r.get("ai_replaceability", 0.5))))
                    composite = 0.35 * intensity + 0.35 * wtp + 0.30 * ai_rep

                    scored.append({
                        "raw_id": complaint["id"],
                        "intensity_score": round(intensity, 3),
                        "wtp_score": round(wtp, 3),
                        "ai_replaceability_score": round(ai_rep, 3),
                        "composite_score": round(composite, 3),
                        "scoring_rationale": r.get("rationale", "No rationale provided"),
                        "passes_threshold": composite >= 0.55,
                    })
                else:
                    logger.warning(f"No score returned for complaint {complaint.get('id')}")
        except Exception as e:
            logger.error(f"Scoring batch failed: {e}")
            # Skip this batch rather than inserting garbage scores
            continue

    logger.info(f"Scored {len(scored)} complaints, {sum(1 for s in scored if s['passes_threshold'])} pass threshold")
    return scored
