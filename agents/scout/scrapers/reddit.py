"""Reddit public JSON endpoint scraper."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"
REQUEST_DELAY = 2.0  # seconds between requests (Reddit rate limit)
TOP_COMMENTS_PER_POST = 5  # how many top-level comments to fetch per post
MIN_POST_SCORE = 10  # only fetch comments for posts with this score or higher


async def scrape_subreddit(subreddit: str, limit: int = 100) -> list[dict]:
    """Scrape recent posts from a subreddit using the public JSON API."""
    url = f"{REDDIT_BASE}/r/{subreddit}/new.json"
    params = {"limit": min(limit, 100), "t": "week"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    results = []
    after = None

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for page in range(2):
            if after:
                params["after"] = after

            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.error(f"Failed to scrape r/{subreddit} (page {page}): {e}")
                break

            posts = data.get("data", {}).get("children", [])
            if not posts:
                break

            for post in posts:
                p = post.get("data", {})
                if not p.get("selftext"):
                    continue

                results.append({
                    "source": "reddit",
                    "source_id": f"reddit_{p.get('id', '')}",
                    "source_url": f"{REDDIT_BASE}{p.get('permalink', '')}",
                    "subreddit": subreddit,
                    "title": p.get("title", ""),
                    "body": f"{p.get('title', '')}\n\n{p.get('selftext', '')}",
                    "author": p.get("author"),
                    "score": p.get("score", 0),
                    "posted_at": datetime.fromtimestamp(
                        p.get("created_utc", 0), tz=timezone.utc
                    ).isoformat() if p.get("created_utc") else None,
                    "_post_id": p.get("id", ""),  # used for comment fetching, stripped before insert
                    "_post_score": p.get("score", 0),
                })

            after = data.get("data", {}).get("after")
            if not after:
                break

            await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Scraped {len(results)} posts from r/{subreddit}")
    return results


async def fetch_comments_for_post(post_id: str, subreddit: str, client: httpx.AsyncClient) -> list[dict]:
    """Fetch top comments for a single Reddit post."""
    url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": TOP_COMMENTS_PER_POST, "sort": "top", "depth": 1}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"Failed to fetch comments for post {post_id}: {e}")
        return []

    # data[1] contains the comments listing
    if len(data) < 2:
        return []

    comments = []
    for child in data[1].get("data", {}).get("children", []):
        c = child.get("data", {})
        body = c.get("body", "").strip()

        # Skip deleted/removed comments and very short ones
        if not body or body in ("[deleted]", "[removed]") or len(body) < 30:
            continue

        comment_id = c.get("id", "")
        if not comment_id:
            continue

        comments.append({
            "source": "reddit",
            "source_id": f"reddit_comment_{comment_id}",
            "source_url": f"{REDDIT_BASE}{c.get('permalink', '')}",
            "subreddit": subreddit,
            "title": None,
            "body": body,
            "author": c.get("author"),
            "score": c.get("score", 0),
            "posted_at": datetime.fromtimestamp(
                c.get("created_utc", 0), tz=timezone.utc
            ).isoformat() if c.get("created_utc") else None,
        })

    return comments[:TOP_COMMENTS_PER_POST]


async def scrape_subreddit_with_comments(subreddit: str) -> list[dict]:
    """Scrape posts and fetch comments for high-score posts."""
    posts = await scrape_subreddit(subreddit)

    # Only fetch comments for posts that meet the score threshold
    high_score_posts = [p for p in posts if p.get("_post_score", 0) >= MIN_POST_SCORE]
    logger.info(f"r/{subreddit}: {len(posts)} posts, fetching comments for {len(high_score_posts)} high-score posts")

    all_items = []
    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch comments first (before stripping internal fields)
        for post_data in high_score_posts:
            post_id = post_data.get("_post_id", "")
            if not post_id:
                continue
            comments = await fetch_comments_for_post(post_id, subreddit, client)
            all_items.extend(comments)
            await asyncio.sleep(REQUEST_DELAY)

        # Now strip internal fields and add posts
        for post in posts:
            post.pop("_post_id", None)
            post.pop("_post_score", None)
            all_items.append(post)

    return all_items


async def scrape_all_subreddits() -> list[dict]:
    """Scrape all configured subreddits sequentially (respecting rate limits)."""
    all_results = []
    for subreddit in settings.subreddit_list:
        try:
            items = await scrape_subreddit_with_comments(subreddit)
            all_results.extend(items)
        except Exception as e:
            logger.error(f"Failed to scrape r/{subreddit}, continuing: {e}")
        await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Total Reddit items scraped: {len(all_results)} (posts + comments)")
    return all_results
