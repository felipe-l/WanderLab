"""Analyst agent — generates product opportunity briefs from ranked clusters."""

import asyncio
import os
import sys
from pathlib import Path

# Add shared library to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import settings
from shared.discord_webhook import _post_webhook, post_log, post_opportunity
from shared.logging_setup import setup_logging
from shared.pipeline_run import PipelineRunContext
from shared.supabase_client import (
    get_latest_run_id,
    get_ranked_clusters,
    get_weak_signal_clusters,
    insert_opportunities,
)

from briefer import generate_product_brief, generate_unmet_need_brief
from formatter import format_product_brief, format_unmet_need_brief, format_weak_signals

logger = setup_logging("analyst")

TOP_N = int(os.environ.get("ANALYST_TOP_N", "10"))
MAX_CONCURRENT = 3  # parallel Sonnet calls — keep low to avoid rate limits


async def run():
    run_id = os.environ.get("RUN_ID") or get_latest_run_id()
    if not run_id:
        raise RuntimeError("No pipeline run found — run Scout and Ranker first")

    async with PipelineRunContext("analyst", run_id=run_id) as ctx:

        # Load clusters
        clusters = get_ranked_clusters(run_id, top_n=TOP_N)
        weak_signals = get_weak_signal_clusters(run_id)

        logger.info(f"Loaded {len(clusters)} clusters, {len(weak_signals)} weak signals")
        await post_log(f"Generating briefs for {len(clusters)} clusters (top {TOP_N} by composite score)")

        if not clusters:
            await post_log("No clusters found — nothing to analyze")
            ctx.set_count(0)
            return

        # Generate briefs concurrently
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def generate_with_semaphore(cluster):
            async with semaphore:
                if cluster.get("cluster_type") == "unmet_need":
                    return await generate_unmet_need_brief(cluster)
                else:
                    return await generate_product_brief(cluster)

        tasks = [generate_with_semaphore(c) for c in clusters]
        briefs = await asyncio.gather(*tasks)

        # Filter failed briefs
        valid_briefs = [b for b in briefs if b is not None]
        logger.info(f"Generated {len(valid_briefs)}/{len(clusters)} briefs successfully")

        # Attach sample complaints from cluster for Discord formatting
        cluster_map = {str(c.get("id")): c for c in clusters}
        for brief in valid_briefs:
            cluster = cluster_map.get(brief.get("ranked_id"), {})
            brief["sample_complaints"] = cluster.get("sample_complaints", [])

        # --- Write to Supabase FIRST before any Discord posts ---
        records = []
        for brief in valid_briefs:
            records.append({
                "ranked_id": brief.get("ranked_id"),
                "product_name": brief.get("product_name") or "Market Gap",
                "problem_summary": brief.get("core_problem", ""),
                "evidence_count": brief.get("evidence_count", 0),
                "avg_composite_score": brief.get("avg_composite_score", 0),
                "opportunity_brief": brief.get("product_concept", ""),
                "verdict": brief.get("verdict", "skip"),
                "verdict_rationale": brief.get("verdict_rationale", ""),
                "filtered_ids": [],
                "buyer_profile": brief.get("buyer_profile"),
                "wedge": brief.get("wedge"),
                "build_complexity": brief.get("build_complexity"),
                "product_concept": brief.get("product_concept"),
            })

        count = insert_opportunities(run_id, records)
        ctx.set_count(count)
        logger.info(f"Wrote {count} briefs to Supabase")

        # --- Post to Discord — failures are logged but don't crash the run ---
        build_count = sum(1 for b in valid_briefs if b.get("verdict") == "build")
        watch_count = sum(1 for b in valid_briefs if b.get("verdict") == "watch")
        skip_count = sum(1 for b in valid_briefs if b.get("verdict") == "skip")

        await post_log(f"Posting {len(valid_briefs)} briefs — 🟢 {build_count} build · 🟡 {watch_count} watch · 🔴 {skip_count} skip")

        for brief in valid_briefs:
            try:
                if brief.get("cluster_type") == "unmet_need":
                    embed = format_unmet_need_brief(brief)
                else:
                    embed = format_product_brief(brief)
                await post_opportunity(embed)
            except Exception as e:
                logger.error(f"Failed to post brief for {brief.get('product_name')}: {e}")

        # Post weak signals as plain text
        if weak_signals:
            try:
                weak_summary = format_weak_signals(weak_signals)
                await _post_webhook(settings.discord_webhook_opportunities, {"content": weak_summary[:2000]})
            except Exception as e:
                logger.error(f"Failed to post weak signals: {e}")

        await post_log(f"Done — {count} briefs written to Supabase")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
