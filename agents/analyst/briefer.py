"""Sonnet-based opportunity brief generation."""

import json
import logging
from pathlib import Path

from shared.openrouter_client import SONNET, call_llm_json

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text()


async def generate_product_brief(cluster: dict) -> dict | None:
    """Generate an opportunity brief for a named product cluster."""
    system_prompt = _load_prompt("product_brief.txt")

    sample_complaints = "\n".join(
        f'- "{q}"' for q in cluster.get("sample_complaints", [])
    )

    user_prompt = (system_prompt
        .replace("{product_name}", str(cluster.get("product_name", "Unknown")))
        .replace("{problem_theme}", str(cluster.get("problem_theme", "")))
        .replace("{complaint_count}", str(cluster.get("complaint_count", 0)))
        .replace("{composite_score}", str(cluster.get("composite_score", 0)))
        .replace("{intensity_score}", str(cluster.get("intensity_score", 0)))
        .replace("{wtp_score}", str(cluster.get("wtp_score", 0)))
        .replace("{ai_replaceability_score}", str(cluster.get("ai_replaceability_score", 0)))
        .replace("{sample_complaints}", sample_complaints)
    )

    try:
        result = await call_llm_json(SONNET, "You are a product opportunity analyst. Respond only with valid JSON.", user_prompt)
        result["ranked_id"] = str(cluster.get("id", ""))
        result["product_name"] = cluster.get("product_name")
        result["problem_theme"] = cluster.get("problem_theme")
        result["evidence_count"] = cluster.get("complaint_count", 0)
        result["avg_composite_score"] = cluster.get("composite_score", 0)
        result["cluster_type"] = "product"
        logger.info(f"Brief generated for {cluster.get('product_name')} — verdict: {result.get('verdict')}")
        return result
    except Exception as e:
        logger.error(f"Brief generation failed for {cluster.get('product_name')}: {e}")
        return None


async def generate_unmet_need_brief(cluster: dict) -> dict | None:
    """Generate an opportunity brief for an unmet need cluster."""
    system_prompt = _load_prompt("unmet_need_brief.txt")

    sample_complaints = "\n".join(
        f'- "{q}"' for q in cluster.get("sample_complaints", [])
    )

    user_prompt = (system_prompt
        .replace("{problem_theme}", str(cluster.get("problem_theme", "")))
        .replace("{complaint_count}", str(cluster.get("complaint_count", 0)))
        .replace("{ai_replaceability_score}", str(cluster.get("ai_replaceability_score", 0)))
        .replace("{sample_complaints}", sample_complaints)
    )

    try:
        result = await call_llm_json(SONNET, "You are a product opportunity analyst. Respond only with valid JSON.", user_prompt)
        result["ranked_id"] = str(cluster.get("id", ""))
        result["product_name"] = None
        result["problem_theme"] = cluster.get("problem_theme")
        result["evidence_count"] = cluster.get("complaint_count", 0)
        result["avg_composite_score"] = cluster.get("composite_score", 0)
        result["cluster_type"] = "unmet_need"
        logger.info(f"Unmet need brief generated — verdict: {result.get('verdict')}")
        return result
    except Exception as e:
        logger.error(f"Unmet need brief generation failed: {e}")
        return None
