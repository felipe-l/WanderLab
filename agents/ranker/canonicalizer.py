"""Product name canonicalization using Flash Lite."""

import logging

from shared.openrouter_client import FLASH_LITE, call_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product name normalizer.

Given a list of product name strings extracted from user complaints, group duplicates
and return the canonical name for each input string.

Rules:
- "JIRA", "Jira", "Atlassian Jira", "jira" → "Jira"
- "MS Teams", "Microsoft Teams", "Teams" → "Microsoft Teams"
- "HubSpot CRM", "Hubspot", "HubSpot" → "HubSpot"
- Prefer the most commonly known brand name
- Keep proper capitalization

Respond with a JSON object: {"mapping": {"original_name": "canonical_name", ...}}"""


async def canonicalize_product_names(product_names: list[str]) -> dict[str, str]:
    """Return a mapping from raw product name → canonical name.

    Falls back to identity mapping if LLM call fails.
    """
    if not product_names:
        return {}

    unique_names = list(set(product_names))
    logger.info(f"Canonicalizing {len(unique_names)} unique product names")

    user_prompt = "Normalize these product names:\n" + "\n".join(f"- {n}" for n in unique_names)

    try:
        response = await call_llm_json(FLASH_LITE, SYSTEM_PROMPT, user_prompt)
        mapping = response.get("mapping", {})
        # Fill in any missing names with identity
        for name in unique_names:
            if name not in mapping:
                mapping[name] = name
        logger.info(f"Canonicalized {len(mapping)} product names")
        return mapping
    except Exception as e:
        logger.error(f"Canonicalization failed, using identity mapping: {e}")
        return {name: name for name in unique_names}
