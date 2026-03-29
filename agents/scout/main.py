"""Scout agent — scrapes Reddit and App Store for complaints about paid software."""

import asyncio
import sys
from pathlib import Path

# Add shared library to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import settings
from shared.discord_webhook import post_log
from shared.logging_setup import setup_logging
from shared.pipeline_run import PipelineRunContext
from shared.supabase_client import insert_raw_complaints

from scrapers.reddit import scrape_all_subreddits
from scrapers.appstore import scrape_all_apps
from classifier import classify_batch

logger = setup_logging("scout")


async def run():
    async with PipelineRunContext("scout") as ctx:
        # --- Reddit ---
        logger.info("Starting Reddit scraping")
        reddit_posts = await scrape_all_subreddits()
        logger.info(f"Reddit scraped: {len(reddit_posts)} items")
        await post_log(f"Reddit scraped: {len(reddit_posts)} items")

        # --- App Store ---
        logger.info("Starting App Store scraping")
        appstore_reviews = await scrape_all_apps()
        logger.info(f"App Store scraped: {len(appstore_reviews)} items")
        await post_log(f"App Store scraped: {len(appstore_reviews)} items")

        all_items = reddit_posts + appstore_reviews
        logger.info(f"Total scraped: {len(all_items)} items")

        if not all_items:
            logger.warning("No items scraped from any source")
            await post_log("WARNING: No items scraped from any source")
            ctx.set_count(0)
            return

        # --- Classification ---
        logger.info(f"Classifying {len(all_items)} items")
        await post_log(f"Classifying {len(all_items)} items...")
        classified = await classify_batch(all_items)

        complaints = [c for c in classified if c.get("is_complaint")]
        non_complaints = [c for c in classified if not c.get("is_complaint")]
        logger.info(f"Classification result: {len(complaints)} complaints, {len(non_complaints)} non-complaints")
        await post_log(f"Classification result: {len(complaints)} complaints / {len(non_complaints)} non-complaints")

        # Log top products mentioned
        from collections import Counter
        products = [c.get("product_mentioned") for c in complaints if c.get("product_mentioned")]
        top_products = Counter(products).most_common(10)
        if top_products:
            product_summary = ", ".join(f"{p} ({n})" for p, n in top_products)
            logger.info(f"Top products: {product_summary}")
            await post_log(f"Top products mentioned: {product_summary}")

        # --- Insert ---
        count = insert_raw_complaints(ctx.run_id, classified)
        ctx.set_count(count)
        logger.info(f"Wrote {count} records to pipeline_raw")
        await post_log(f"Done — wrote {count} records to Supabase (run_id: {ctx.run_id})")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
