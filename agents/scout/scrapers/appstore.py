"""iTunes App Store RSS review scraper."""

import asyncio
import logging
from datetime import datetime

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

APPSTORE_RSS_BASE = "https://itunes.apple.com/us/rss/customerreviews"
REQUEST_DELAY = 1.5  # seconds between requests


async def scrape_app_reviews(app_id: str, max_pages: int = 10) -> list[dict]:
    """Scrape recent reviews for an App Store app via RSS JSON feed.

    Focuses on 1-2 star reviews (complaints).
    """
    results = []

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, max_pages + 1):
            url = f"{APPSTORE_RSS_BASE}/page={page}/sortBy=mostRecent/id={app_id}/json"

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.error(f"Failed to scrape App Store app {app_id} (page {page}): {e}")
                break

            entries = data.get("feed", {}).get("entry", [])
            if not entries:
                break

            # First entry is the app metadata, skip it
            reviews = entries[1:] if page == 1 else entries

            for review in reviews:
                rating = int(review.get("im:rating", {}).get("label", "5"))

                # Only keep 1-2 star reviews (complaints)
                if rating > 2:
                    continue

                # Extract app name from feed metadata
                app_name = data.get("feed", {}).get("title", {}).get("label", "").replace("Customer Reviews: ", "")

                review_id = review.get("id", {}).get("label", "")
                results.append({
                    "source": "appstore",
                    "source_id": f"appstore_{review_id}",
                    "source_url": review.get("author", {}).get("uri", {}).get("label"),
                    "app_name": app_name,
                    "app_id": app_id,
                    "title": review.get("title", {}).get("label", ""),
                    "body": f"{review.get('title', {}).get('label', '')}\n\n{review.get('content', {}).get('label', '')}",
                    "author": review.get("author", {}).get("name", {}).get("label"),
                    "score": rating,
                    "posted_at": review.get("updated", {}).get("label"),
                })

            if len(reviews) < 49:  # Less than a full page means no more
                break

            await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Scraped {len(results)} negative reviews for app {app_id}")
    return results


async def scrape_all_apps() -> list[dict]:
    """Scrape reviews for all configured App Store apps."""
    all_results = []
    for app_id in settings.appstore_id_list:
        try:
            reviews = await scrape_app_reviews(app_id)
            all_results.extend(reviews)
        except Exception as e:
            logger.error(f"Failed to scrape app {app_id}, continuing: {e}")
        await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Total App Store reviews scraped: {len(all_results)}")
    return all_results
