"""Complaint classifier for Scout — concurrent batch processing."""

import asyncio
import logging

from shared.openrouter_client import FLASH_LITE, call_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a complaint classifier for a product research pipeline.

For each piece of user-generated content, determine:
1. Is this a complaint about a PAID software product? (not free tools, not hardware, not services)
2. If yes, what specific product is being complained about?

Respond with a JSON object containing a "results" array. Each result has:
- "index": the index of the item in the input
- "is_complaint": true/false
- "product_mentioned": the product name or null

Only mark is_complaint=true if the user is genuinely frustrated or reporting a problem with a paid software product. Feature requests, neutral reviews, and general discussion should be false."""

BATCH_SIZE = 15
MAX_CONCURRENT = 8  # number of LLM calls in flight at once


async def _classify_single_batch(batch: list[dict], batch_index: int) -> list[dict]:
    """Classify one batch and return results list."""
    user_prompt = "Classify the following items:\n\n"
    for idx, item in enumerate(batch):
        user_prompt += f"--- Item {idx} ---\n"
        user_prompt += f"Source: {item.get('source', 'unknown')}\n"
        if item.get("subreddit"):
            user_prompt += f"Subreddit: r/{item['subreddit']}\n"
        if item.get("app_name"):
            user_prompt += f"App: {item['app_name']}\n"
        user_prompt += f"Text: {item.get('body', '')[:1000]}\n\n"

    try:
        response = await call_llm_json(FLASH_LITE, SYSTEM_PROMPT, user_prompt)
        return response.get("results", [])
    except Exception as e:
        logger.error(f"Classification batch {batch_index} failed: {e}")
        return []


async def classify_batch(items: list[dict]) -> list[dict]:
    """Classify all scraped items concurrently.

    Splits into batches and fires up to MAX_CONCURRENT LLM calls at once.
    Mutates each item dict in place with 'is_complaint' and 'product_mentioned'.
    """
    if not items:
        return items

    batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_with_semaphore(batch, batch_index):
        async with semaphore:
            return await _classify_single_batch(batch, batch_index)

    # Fire all batches concurrently (bounded by semaphore)
    tasks = [run_with_semaphore(batch, i) for i, batch in enumerate(batches)]
    all_results = await asyncio.gather(*tasks)

    # Map results back to items
    for batch_idx, (batch, results) in enumerate(zip(batches, all_results)):
        result_map = {r["index"]: r for r in results}
        for idx, item in enumerate(batch):
            if idx in result_map:
                item["is_complaint"] = result_map[idx].get("is_complaint", False)
                item["product_mentioned"] = result_map[idx].get("product_mentioned")
            else:
                # Batch failed — default to False so we don't inflate complaint count
                item["is_complaint"] = False
                item["product_mentioned"] = None

    complaint_count = sum(1 for item in items if item.get("is_complaint"))
    logger.info(f"Classified {len(items)} items: {complaint_count} complaints")
    return items
