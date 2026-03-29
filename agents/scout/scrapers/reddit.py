"""Reddit public JSON endpoint scraper."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"
REQUEST_DELAY = 5.0  # seconds between requests (Reddit rate limit)
TOP_COMMENTS_PER_POST = 5  # how many top-level comments to fetch per post
MIN_POST_SCORE = 10  # only fetch comments for posts with this score or higher

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


async def _scrape_subreddit_posts(subreddit: str, client: httpx.AsyncClient, limit: int = 100) -> list[dict]:
    """Scrape recent posts from a subreddit. Uses the provided client (with its cookies)."""
    url = f"{REDDIT_BASE}/r/{subreddit}/new.json"
    params = {"limit": min(limit, 100), "t": "week"}

    results = []
    after = None

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


async def _fetch_comments_for_post(post_id: str, subreddit: str, client: httpx.AsyncClient, failures: list) -> list[dict]:
    """Fetch top comments for a single Reddit post. Uses the provided client (with its cookies)."""
    url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": TOP_COMMENTS_PER_POST, "sort": "top", "depth": 1}

    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        status = getattr(getattr(e, "response", None), "status_code", "network")
        failures.append({"post_id": post_id, "subreddit": subreddit, "error": str(status)})
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
    """Scrape posts and fetch comments using a single shared client session.

    A single client carries cookies from the first request through all subsequent
    requests, which prevents Reddit from flagging the session as a bot.
    """
    all_items = []
    failures = []

    # One shared client for the entire subreddit — cookies from page 1 carry through
    # to page 2 and all comment fetches, making the session look like a real browser
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        posts = await _scrape_subreddit_posts(subreddit, client)

        high_score_posts = [p for p in posts if p.get("_post_score", 0) >= MIN_POST_SCORE]
        logger.info(f"r/{subreddit}: {len(posts)} posts, fetching comments for {len(high_score_posts)} high-score posts")

        # Fetch comments first (before stripping internal fields)
        for post_data in high_score_posts:
            post_id = post_data.get("_post_id", "")
            if not post_id:
                continue
            await asyncio.sleep(REQUEST_DELAY)
            comments = await _fetch_comments_for_post(post_id, subreddit, client, failures)
            all_items.extend(comments)

        # Strip internal fields and add posts
        for post in posts:
            post.pop("_post_id", None)
            post.pop("_post_score", None)
            all_items.append(post)

    # Summary log so you can see at a glance if failures are worth investigating
    if failures:
        by_error = {}
        for f in failures:
            by_error.setdefault(f["error"], 0)
            by_error[f["error"]] += 1
        summary = ", ".join(f"{count}×{code}" for code, count in by_error.items())
        logger.warning(f"r/{subreddit}: {len(failures)}/{len(high_score_posts)} comment fetches failed ({summary})")
    else:
        logger.info(f"r/{subreddit}: all {len(high_score_posts)} comment fetches succeeded")

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
