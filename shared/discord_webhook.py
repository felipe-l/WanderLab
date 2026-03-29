"""Discord webhook posting utilities."""

import logging
from datetime import datetime, timezone

import httpx

from shared.config import settings
from shared.retry import retry

logger = logging.getLogger(__name__)


@retry(max_attempts=3, base_delay=1.0, exceptions=(httpx.HTTPError,))
async def _post_webhook(webhook_url: str, payload: dict) -> dict | None:
    """Post a payload to a Discord webhook. Returns the message data if wait=true."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{webhook_url}?wait=true", json=payload)
        if resp.is_error:
            logger.error(f"Discord webhook error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()


async def post_log(message: str):
    """Post a status message to #agent-logs."""
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    content = f"**[{settings.agent_name}]** {timestamp} — {message}"
    await _post_webhook(settings.discord_webhook_agent_logs, {"content": content})
    logger.info(f"Discord log: {message}")


async def post_alert(message: str):
    """Post an alert to #agent-logs with @here mention."""
    timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    content = f"@here **[{settings.agent_name} ALERT]** {timestamp} — {message}"
    await _post_webhook(settings.discord_webhook_agent_logs, {"content": content})
    logger.warning(f"Discord alert: {message}")


async def post_opportunity(embed: dict) -> str | None:
    """Post a rich embed to all configured #opportunities webhooks. Returns the first message ID."""
    first_id = None
    for url in settings.discord_webhook_opportunities_list:
        try:
            result = await _post_webhook(url, {"embeds": [embed]})
            if result and first_id is None:
                first_id = result.get("id")
        except Exception as e:
            logger.error(f"Failed to post opportunity to webhook: {e}")
    return first_id
