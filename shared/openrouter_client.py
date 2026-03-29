"""OpenRouter LLM client using the OpenAI SDK."""

import json
import logging

from openai import AsyncOpenAI

from shared.config import settings
from shared.retry import retry

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
)

FLASH_LITE = "google/gemini-2.5-flash-lite"  # cheap classifier model
HAIKU = "anthropic/claude-haiku-4-5"
SONNET = "anthropic/claude-sonnet-4-6"


@retry(max_attempts=3, base_delay=5.0)
async def call_llm(model: str, system_prompt: str, user_prompt: str) -> str:
    """Make a single completion call. Returns the assistant's response text."""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
    )
    return response.choices[0].message.content


@retry(max_attempts=3, base_delay=5.0)
async def call_llm_json(model: str, system_prompt: str, user_prompt: str) -> dict | list:
    """Make a completion call and parse the response as JSON.

    Extracts JSON from the response text, handling markdown code blocks
    and other wrapper text that models sometimes add.
    """
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nRespond ONLY with valid JSON, no markdown or extra text."},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
    )
    text = response.choices[0].message.content or ""
    # Strip markdown code blocks if present
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    return json.loads(text.strip())
