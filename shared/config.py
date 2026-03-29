"""Environment configuration with validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _load_env():
    """Load .env from the agent directory (one level up from shared)."""
    # Try agent-level .env first, then project-level
    for candidate in [Path.cwd() / ".env", Path(__file__).parent.parent / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return
    load_dotenv()


_load_env()


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    # Core — required by all agents
    supabase_url: str = field(default_factory=lambda: _require("SUPABASE_URL"))
    supabase_service_key: str = field(default_factory=lambda: _require("SUPABASE_SERVICE_KEY"))
    discord_webhook_agent_logs: str = field(default_factory=lambda: _require("DISCORD_WEBHOOK_AGENT_LOGS"))
    agent_name: str = field(default_factory=lambda: _require("AGENT_NAME"))

    # OpenRouter — required by Scout, Filter, Analyst
    openrouter_api_key: str = field(default_factory=lambda: _optional("OPENROUTER_API_KEY"))

    # Discord — Analyst only (comma-separated for multiple webhooks)
    discord_webhook_opportunities: str = field(default_factory=lambda: _optional("DISCORD_WEBHOOK_OPPORTUNITIES"))

    @property
    def discord_webhook_opportunities_list(self) -> list[str]:
        return [u.strip() for u in self.discord_webhook_opportunities.split(",") if u.strip()]

    # Scout config
    reddit_subreddits: str = field(default_factory=lambda: _optional("REDDIT_SUBREDDITS", "SaaS,startups,Entrepreneur,SmallBusiness,productivity,Notion,Adobe,Shopify,Slack,Jira,Figma,Lightroom,Asana,HubSpot,webdev,Freelance,SEO,marketing"))
    reddit_user_agent: str = field(default_factory=lambda: _optional("REDDIT_USER_AGENT", "WanderLab-Scout/1.0"))
    appstore_app_ids: str = field(default_factory=lambda: _optional("APPSTORE_APP_IDS", ""))

    # Filter config
    composite_threshold: float = field(default_factory=lambda: float(_optional("COMPOSITE_THRESHOLD", "0.55")))

    # Supervisor config
    pipeline_timezone: str = field(default_factory=lambda: _optional("PIPELINE_TIMEZONE", "America/New_York"))
    poll_interval_seconds: int = field(default_factory=lambda: int(_optional("POLL_INTERVAL_SECONDS", "600")))

    @property
    def subreddit_list(self) -> list[str]:
        return [s.strip() for s in self.reddit_subreddits.split(",") if s.strip()]

    @property
    def appstore_id_list(self) -> list[str]:
        return [s.strip() for s in self.appstore_app_ids.split(",") if s.strip()]


# Singleton — fail fast on import if config is invalid
settings = Settings()
