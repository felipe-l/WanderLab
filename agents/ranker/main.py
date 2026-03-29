"""Ranker agent — groups, themes, and scores complaints from Scout."""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

# Add shared library to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os

from shared.discord_webhook import post_log
from shared.logging_setup import setup_logging
from shared.pipeline_run import PipelineRunContext
from shared.supabase_client import get_latest_run_id, get_raw_complaints, insert_ranked_clusters

from canonicalizer import canonicalize_product_names
from themer import identify_themes, synthesize_unmet_needs

logger = setup_logging("ranker")

MIN_COMPLAINTS = int(os.environ.get("RANKER_MIN_COMPLAINTS", "3"))
PREVIEW_N = int(os.environ.get("RANKER_PREVIEW_N", "10"))  # how many clusters to show in Discord summary
UNMET_NEEDS_THEMES = int(os.environ.get("RANKER_UNMET_NEEDS_THEMES", "5"))
MAX_CONCURRENT = 5  # parallel Sonnet calls for theme identification


async def run():
    # Ranker reads from Scout's run — use latest run or override via env
    run_id = os.environ.get("RUN_ID") or get_latest_run_id()
    if not run_id:
        raise RuntimeError("No pipeline run found — run Scout first")

    async with PipelineRunContext("ranker", run_id=run_id) as ctx:

        # Step 1 — Load complaints
        logger.info("Loading complaints from pipeline_raw")
        all_complaints = get_raw_complaints(ctx.run_id, only_complaints=True)
        logger.info(f"Loaded {len(all_complaints)} complaints")
        await post_log(f"Loaded {len(all_complaints)} complaints from Scout")

        if not all_complaints:
            await post_log("No complaints found — nothing to rank")
            ctx.set_count(0)
            return

        # Step 2 — Split named vs unmet needs
        named = [c for c in all_complaints if c.get("product_mentioned")]
        unmet = [c for c in all_complaints if not c.get("product_mentioned")]
        logger.info(f"Named product complaints: {len(named)}, Unmet needs: {len(unmet)}")

        # Step 3 — Canonicalize product names
        raw_names = [c["product_mentioned"] for c in named]
        name_mapping = await canonicalize_product_names(raw_names)

        # Apply canonical names
        for complaint in named:
            raw_name = complaint["product_mentioned"]
            complaint["canonical_product"] = name_mapping.get(raw_name, raw_name)

        # Step 4 — Group by canonical product
        product_groups = defaultdict(list)
        for complaint in named:
            product_groups[complaint["canonical_product"]].append(complaint)

        # Separate weak signals
        strong_products = {p: complaints for p, complaints in product_groups.items() if len(complaints) >= MIN_COMPLAINTS}
        weak_products = {p: complaints for p, complaints in product_groups.items() if len(complaints) < MIN_COMPLAINTS}

        logger.info(f"Strong product clusters: {len(strong_products)}, Weak signals: {len(weak_products)}")
        await post_log(f"Product clusters: {len(strong_products)} strong, {len(weak_products)} weak signals")

        all_clusters = []

        # Step 5 — Theme + score strong clusters (concurrent Sonnet calls)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def theme_with_semaphore(product, complaints):
            async with semaphore:
                return await identify_themes(product, complaints)

        tasks = [theme_with_semaphore(product, complaints) for product, complaints in strong_products.items()]
        theme_results = await asyncio.gather(*tasks)

        for themes in theme_results:
            all_clusters.extend(themes)

        logger.info(f"Generated {len(all_clusters)} product theme clusters")

        # Step 6 — Weak signals (no LLM — just store as-is)
        for product, complaints in weak_products.items():
            all_clusters.append({
                "cluster_type": "weak_signal",
                "product_name": product,
                "problem_theme": f"General complaints about {product}",
                "complaint_count": len(complaints),
                "raw_ids": [str(c["id"]) for c in complaints if c.get("id")],
                "sample_complaints": [c.get("body", "")[:200] for c in complaints[:3]],
                "intensity_score": 0.0,
                "wtp_score": 0.0,
                "ai_replaceability_score": 0.0,
                "composite_score": 0.0,
                "is_weak_signal": True,
            })

        # Step 7 — Unmet needs synthesis
        await post_log(f"Synthesizing {len(unmet)} unmet need complaints...")
        unmet_clusters = await synthesize_unmet_needs(unmet, top_n=UNMET_NEEDS_THEMES)
        all_clusters.extend(unmet_clusters)

        # Step 8 — Rank and write
        strong_clusters = [c for c in all_clusters if not c.get("is_weak_signal")]
        strong_clusters.sort(key=lambda x: x["composite_score"], reverse=True)

        top_clusters = strong_clusters[:PREVIEW_N]
        top_summary = ", ".join(
            f"{c.get('product_name') or 'Unmet need'}: {c['problem_theme'][:40]} ({c['composite_score']:.2f})"
            for c in top_clusters
        )
        logger.info(f"Top {TOP_N} clusters: {top_summary}")
        await post_log(f"Top clusters identified:\n{top_summary}")

        count = insert_ranked_clusters(ctx.run_id, all_clusters)
        ctx.set_count(count)
        await post_log(f"Done — wrote {count} clusters to pipeline_ranked")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
