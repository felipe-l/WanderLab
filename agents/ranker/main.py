"""Ranker agent — embeds, clusters, and scores complaints from Scout."""

import asyncio
import os
import sys
from pathlib import Path

# Add shared library to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.discord_webhook import post_log
from shared.logging_setup import setup_logging
from shared.pipeline_run import PipelineRunContext
from shared.supabase_client import get_latest_run_id, get_raw_complaints, insert_ranked_clusters

from themer import cluster_and_label

logger = setup_logging("ranker")

TOP_N = int(os.environ.get("RANKER_TOP_N", "10"))


async def run():
    run_id = os.environ.get("RUN_ID") or get_latest_run_id()
    if not run_id:
        raise RuntimeError("No pipeline run found — run Scout first")

    async with PipelineRunContext("ranker", run_id=run_id) as ctx:

        # Step 1 — Load all complaints
        logger.info("Loading complaints from pipeline_raw")
        all_complaints = get_raw_complaints(ctx.run_id, only_complaints=True)
        logger.info(f"Loaded {len(all_complaints)} complaints")
        await post_log(f"Loaded {len(all_complaints)} complaints from Scout")

        if not all_complaints:
            await post_log("No complaints found — nothing to rank")
            ctx.set_count(0)
            return

        named = sum(1 for c in all_complaints if c.get("product_mentioned"))
        unmet = len(all_complaints) - named
        await post_log(f"{named} named-product complaints, {unmet} unmet needs — embedding all together")

        # Step 2 — Embed, cluster, label (no product boundaries)
        clusters = await cluster_and_label(all_complaints, top_n=TOP_N)

        if not clusters:
            await post_log("No clusters found after embedding — nothing to write")
            ctx.set_count(0)
            return

        top_summary = ", ".join(
            f"{c.get('product_name') or 'Unmet need'}: {c['problem_theme'][:40]} ({c['composite_score']:.2f})"
            for c in clusters
        )
        logger.info(f"Top {TOP_N} clusters: {top_summary}")
        await post_log(f"Top clusters identified:\n{top_summary}")

        # Step 3 — Write (strip intermediate scoring fields not in DB schema)
        for c in clusters:
            c.pop("unique_products", None)
            c.pop("avg_engagement", None)
        count = insert_ranked_clusters(ctx.run_id, clusters)
        ctx.set_count(count)
        await post_log(f"Done — wrote {count} clusters to pipeline_ranked")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
