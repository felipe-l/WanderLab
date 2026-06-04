"""Google Play Store review scraper."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from google_play_scraper import Sort, reviews as gp_reviews

from shared.config import settings

logger = logging.getLogger(__name__)

REQUEST_DELAY = 1.0  # seconds between apps
_executor = ThreadPoolExecutor(max_workers=1)  # gp_reviews is sync, run in thread


def _fetch_reviews_sync(app_id: str, star: int, count: int) -> list[dict]:
    """Synchronous fetch for a single star rating — runs in thread executor."""
    result, _ = gp_reviews(
        app_id,
        lang="en",
        country="us",
        sort=Sort.NEWEST,
        count=count,
        filter_score_with=star,
    )
    return result


async def scrape_app_reviews(app_id: str) -> list[dict]:
    """Scrape reviews for a single Google Play app across configured star ratings."""
    min_star = settings.googleplay_min_star_rating
    max_star = settings.googleplay_max_star_rating
    count_per_star = settings.googleplay_max_reviews_per_star

    all_reviews = []
    loop = asyncio.get_event_loop()

    for star in range(min_star, max_star + 1):
        try:
            raw = await loop.run_in_executor(
                _executor, _fetch_reviews_sync, app_id, star, count_per_star
            )
            for r in raw:
                content = (r.get("content") or "").strip()
                if not content:
                    continue
                all_reviews.append({
                    "source": "googleplay",
                    "source_id": f"googleplay_{r.get('reviewId', '')}",
                    "source_url": f"https://play.google.com/store/apps/details?id={app_id}",
                    "app_name": app_id,
                    "title": None,
                    "body": content,
                    "author": r.get("userName"),
                    "score": r.get("score"),
                    "posted_at": r.get("at").isoformat() if r.get("at") else None,
                })
        except Exception as e:
            logger.error(f"Google Play: failed to fetch {app_id} ★{star}: {e}")

        await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Google Play: '{app_id}' — {len(all_reviews)} reviews (★{min_star}–★{max_star})")
    return all_reviews


async def scrape_all_apps() -> list[dict]:
    """Scrape reviews for all configured Google Play app IDs."""
    all_results = []
    for app_id in settings.googleplay_app_id_list:
        try:
            reviews = await scrape_app_reviews(app_id)
            all_results.extend(reviews)
        except Exception as e:
            logger.error(f"Google Play: failed to scrape '{app_id}', continuing: {e}")
        await asyncio.sleep(REQUEST_DELAY)

    logger.info(f"Google Play: total {len(all_results)} reviews scraped")
    return all_results
