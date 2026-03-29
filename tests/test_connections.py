"""Test all external connections before a pipeline run.

Usage:
    cd tests
    python test_connections.py

Checks:
- Supabase connection and table access
- OpenRouter API key validity
- Discord webhook (agent-logs)
- Discord webhook (opportunities)
- Reddit public JSON endpoint
- App Store RSS endpoint
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from shared.config import settings
from shared.supabase_client import supabase


async def test_supabase():
    try:
        result = supabase.table("pipeline_runs").select("id").limit(1).execute()
        print("  ✓ Supabase connection OK")
        return True
    except Exception as e:
        print(f"  ✗ Supabase connection FAILED: {e}")
        return False


async def test_openrouter():
    if not settings.openrouter_api_key:
        print("  ✗ OpenRouter: OPENROUTER_API_KEY not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
            if resp.status_code == 200:
                print("  ✓ OpenRouter API key valid")
                return True
            else:
                print(f"  ✗ OpenRouter returned {resp.status_code}: {resp.text[:100]}")
                return False
    except Exception as e:
        print(f"  ✗ OpenRouter FAILED: {e}")
        return False


async def test_discord_webhook(url: str, label: str):
    if not url:
        print(f"  ✗ Discord {label}: webhook URL not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # GET on a webhook URL returns its metadata without posting
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ✓ Discord {label}: webhook '{data.get('name', 'unknown')}' is valid")
                return True
            else:
                print(f"  ✗ Discord {label}: returned {resp.status_code}: {resp.text[:100]}")
                return False
    except Exception as e:
        print(f"  ✗ Discord {label} FAILED: {e}")
        return False


async def test_reddit():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.reddit.com/r/SaaS/new.json?limit=1",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", {}).get("children", []))
                print(f"  ✓ Reddit public JSON OK (got {count} post)")
                return True
            else:
                print(f"  ✗ Reddit returned {resp.status_code}: {resp.text[:100]}")
                return False
    except Exception as e:
        print(f"  ✗ Reddit FAILED: {e}")
        return False


async def test_reddit_comments():
    """Test that comment fetching works with browser headers."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.reddit.com/r/SaaS/comments/.json?limit=1&sort=top&depth=1",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/javascript, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if resp.status_code == 200:
                print("  ✓ Reddit comment endpoint accessible with browser headers")
                return True
            else:
                print(f"  ✗ Reddit comments returned {resp.status_code} — browser headers may need updating")
                return False
    except Exception as e:
        print(f"  ✗ Reddit comments FAILED: {e}")
        return False


async def test_appstore():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://itunes.apple.com/us/rss/customerreviews/page=1/sortBy=mostRecent/id=310633997/json"
            )
            if resp.status_code == 200:
                print("  ✓ App Store RSS endpoint OK")
                return True
            else:
                print(f"  ✗ App Store returned {resp.status_code}")
                return False
    except Exception as e:
        print(f"  ✗ App Store FAILED: {e}")
        return False


async def main():
    print("Testing all external connections...\n")

    results = await asyncio.gather(
        test_supabase(),
        test_openrouter(),
        test_discord_webhook(settings.discord_webhook_agent_logs, "agent-logs"),
        test_discord_webhook(settings.discord_webhook_opportunities, "opportunities"),
        test_reddit(),
        test_reddit_comments(),
        test_appstore(),
    )

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} connections OK.")

    if passed < total:
        print("Fix failing connections before running the pipeline.")
        sys.exit(1)
    else:
        print("All connections healthy — safe to run the pipeline.")


if __name__ == "__main__":
    asyncio.run(main())
