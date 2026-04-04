"""Sonnet-based opportunity brief generation."""

import logging
from pathlib import Path

from shared.openrouter_client import SONNET, call_llm_json

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text()


async def generate_brief(cluster: dict) -> dict | None:
    """Generate an opportunity brief for any cluster (product or unmet need)."""
    system_prompt = _load_prompt("product_brief.txt")

    sample_complaints = "\n".join(
        f'- "{q}"' for q in cluster.get("sample_complaints", [])
    )

    products_mentioned = cluster.get("products_mentioned") or {}
    products_str = ", ".join(f"{p} ({n})" for p, n in sorted(products_mentioned.items(), key=lambda x: -x[1])) or "None"

    user_prompt = (system_prompt
        .replace("{problem_theme}", str(cluster.get("problem_theme", "")))
        .replace("{complaint_count}", str(cluster.get("complaint_count", 0)))
        .replace("{composite_score}", str(cluster.get("composite_score", 0)))
        .replace("{intensity_score}", str(cluster.get("intensity_score", 0)))
        .replace("{wtp_score}", str(cluster.get("wtp_score", 0)))
        .replace("{ai_replaceability_score}", str(cluster.get("ai_replaceability_score", 0)))
        .replace("{products_mentioned}", products_str)
        .replace("{sample_complaints}", sample_complaints)
    )

    try:
        result = await call_llm_json(SONNET, "You are a product opportunity analyst. Respond only with valid JSON.", user_prompt)
        result["ranked_id"] = str(cluster.get("id", ""))
        result["product_name"] = cluster.get("product_name")
        result["problem_theme"] = cluster.get("problem_theme")
        result["evidence_count"] = cluster.get("complaint_count", 0)
        result["avg_composite_score"] = cluster.get("composite_score", 0)
        result["cluster_type"] = cluster.get("cluster_type", "product")
        logger.info(f"Brief generated for '{cluster.get('problem_theme', '')[:50]}' — verdict: {result.get('verdict')}")
        return result
    except Exception as e:
        logger.error(f"Brief generation failed for '{cluster.get('problem_theme', '')[:50]}': {e}")
        return None
