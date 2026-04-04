"""Embedding-based clustering and LLM labeling for all complaints.

Pipeline: embed → UMAP reduce → HDBSCAN cluster → split oversized → LLM label.
"""

import asyncio
import logging
import os
from collections import Counter

from shared.openrouter_client import SONNET, call_llm_json

logger = logging.getLogger(__name__)

# --- Config from env ---
MIN_CLUSTER_SIZE = int(os.environ.get("RANKER_MIN_CLUSTER_SIZE", "5"))
MIN_SAMPLES = int(os.environ.get("RANKER_MIN_SAMPLES", "2"))
CLUSTER_EPSILON = float(os.environ.get("RANKER_CLUSTER_EPSILON", "0.0"))
CLUSTER_METHOD = os.environ.get("RANKER_CLUSTER_SELECTION_METHOD", "eom")
UMAP_DIMS = int(os.environ.get("RANKER_UMAP_DIMS", "15"))
UMAP_NEIGHBORS = int(os.environ.get("RANKER_UMAP_NEIGHBORS", "15"))
MAX_CLUSTER_SIZE = int(os.environ.get("RANKER_MAX_CLUSTER_SIZE", "50"))

# --- Scoring weights (all 0.0-1.0, sub-weights should sum to 1.0 within group) ---
W_DATA = float(os.environ.get("RANKER_W_DATA", "0.5"))           # weight for hard data signals
W_LLM = float(os.environ.get("RANKER_W_LLM", "0.5"))            # weight for LLM-judged signals
W_VOLUME = float(os.environ.get("RANKER_W_VOLUME", "0.30"))      # complaint count (log-scaled)
W_DIVERSITY = float(os.environ.get("RANKER_W_DIVERSITY", "0.45"))  # unique products in cluster
W_ENGAGEMENT = float(os.environ.get("RANKER_W_ENGAGEMENT", "0.25"))  # avg reddit score
W_INTENSITY = float(os.environ.get("RANKER_W_INTENSITY", "0.30"))    # user frustration
W_WTP = float(os.environ.get("RANKER_W_WTP", "0.45"))               # willingness to pay
W_AI_FIT = float(os.environ.get("RANKER_W_AI_FIT", "0.25"))         # AI replaceability

LABEL_PROMPT = """You are a product opportunity analyst for a startup research pipeline.

Given a cluster of similar user complaints (pre-grouped by semantic similarity),
your job is to summarize the theme and score the opportunity.

Scoring dimensions (0.0 to 1.0):
- intensity: How frustrated are users? (0.3=mild annoyance, 0.6=clear frustration, 0.9=rage-quitting/cancelling)
- wtp: Willingness to pay for a better solution (0.3=no signal, 0.6=mentions alternatives, 0.9=explicitly switching/paying)
- ai_replaceability: Could an AI-native tool realistically solve this? (0.3=no, 0.6=partially, 0.9=perfect fit)

Respond with JSON:
{
  "theme": "concise problem description (max 10 words)",
  "intensity_score": <float 0-1>,
  "wtp_score": <float 0-1>,
  "ai_replaceability_score": <float 0-1>,
  "sample_quotes": ["verbatim quote 1", "verbatim quote 2", "verbatim quote 3"]
}

Guidelines:
- theme must be specific, not generic (bad: "tool issues", good: "no offline mode for mobile editing")
- sample_quotes must be verbatim excerpts — pick the most specific and emotionally vivid ones
- Score honestly — not every cluster is a strong opportunity"""


# --- Embedding ---

async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts using Gemini gemini-embedding-001, batching 100 at a time."""
    from google import genai
    from shared.config import settings

    client = genai.Client(api_key=settings.gemini_api_key)
    chunk_size = 100
    chunks = [texts[i:i + chunk_size] for i in range(0, len(texts), chunk_size)]

    semaphore = asyncio.Semaphore(10)

    async def embed_chunk(i, chunk):
        async with semaphore:
            for attempt in range(5):
                try:
                    result = await client.aio.models.embed_content(
                        model="gemini-embedding-001",
                        contents=chunk,
                        config={"task_type": "CLUSTERING"},
                    )
                    return [e.values for e in result.embeddings]
                except Exception as e:
                    if "429" in str(e) and attempt < 4:
                        wait = 60 * (attempt + 1)
                        logger.warning(f"Embedding chunk {i} rate limited, retrying in {wait}s (attempt {attempt + 1}/5)")
                        await asyncio.sleep(wait)
                    else:
                        raise

    results = await asyncio.gather(*[embed_chunk(i, c) for i, c in enumerate(chunks)])
    return [vec for chunk_result in results for vec in chunk_result]


# --- Dimensionality reduction + clustering ---

def _reduce_and_cluster(embeddings: list[list[float]]) -> list[int]:
    """UMAP reduce → HDBSCAN cluster. Returns label per embedding (-1 = noise)."""
    import hdbscan
    import numpy as np
    import umap

    matrix = np.array(embeddings)
    n_samples = len(matrix)

    # UMAP reduction — compress high-dim embeddings to a space where
    # density-based clustering can actually find structure
    n_neighbors = min(UMAP_NEIGHBORS, n_samples - 1)
    reducer = umap.UMAP(
        n_components=UMAP_DIMS,
        n_neighbors=n_neighbors,
        metric="cosine",
        min_dist=0.0,      # pack clusters tight for HDBSCAN
        random_state=42,
    )
    reduced = reducer.fit_transform(matrix)

    logger.info(f"UMAP: {matrix.shape[1]}d → {UMAP_DIMS}d ({n_samples} points, n_neighbors={n_neighbors})")

    # HDBSCAN on the reduced space
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        cluster_selection_epsilon=CLUSTER_EPSILON,
        cluster_selection_method=CLUSTER_METHOD,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(reduced).tolist()

    return labels


def _split_oversized_clusters(clusters: dict[int, list[dict]], embeddings_by_cluster: dict[int, list[list[float]]]) -> dict[int, list[dict]]:
    """Recursively split clusters larger than MAX_CLUSTER_SIZE.

    Uses HDBSCAN on the sub-cluster's embeddings to find finer structure.
    If splitting fails (everything becomes noise), keeps the original cluster.
    """
    import hdbscan
    import numpy as np

    result = {}
    next_label = max(clusters.keys()) + 1

    for label, complaints in clusters.items():
        if len(complaints) <= MAX_CLUSTER_SIZE:
            result[label] = complaints
            continue

        logger.info(f"Splitting oversized cluster {label} ({len(complaints)} complaints, max={MAX_CLUSTER_SIZE})")

        sub_embeddings = np.array(embeddings_by_cluster[label])
        sub_clusterer = hdbscan.HDBSCAN(
            min_cluster_size=max(3, MIN_CLUSTER_SIZE // 2),
            min_samples=1,
            cluster_selection_method="leaf",
            metric="euclidean",
        )
        sub_labels = sub_clusterer.fit_predict(sub_embeddings).tolist()

        sub_clusters: dict[int, list[dict]] = {}
        for complaint, sl in zip(complaints, sub_labels):
            if sl == -1:
                continue
            sub_clusters.setdefault(sl, []).append(complaint)

        if not sub_clusters:
            # Splitting failed — keep original
            logger.warning(f"Sub-clustering failed for cluster {label}, keeping as-is")
            result[label] = complaints
        else:
            logger.info(f"Split cluster {label} into {len(sub_clusters)} sub-clusters")
            for sub_complaints in sub_clusters.values():
                result[next_label] = sub_complaints
                next_label += 1

    return result


# --- LLM labeling ---

async def _label_cluster(cluster_complaints: list[dict]) -> dict | None:
    """Label a single cluster with one focused Sonnet call.

    Returns cluster dict with raw scores — composite is computed later
    in cluster_and_label() after all clusters are available for normalization.
    """
    # For large clusters, sample to keep prompt manageable
    sample = cluster_complaints[:30] if len(cluster_complaints) > 30 else cluster_complaints

    user_prompt = f"Cluster complaints ({len(cluster_complaints)} total, showing {len(sample)}):\n\n"
    for complaint in sample:
        user_prompt += f"- {complaint.get('body', '')[:600]}\n\n"

    try:
        response = await call_llm_json(SONNET, LABEL_PROMPT, user_prompt)

        intensity = max(0.0, min(1.0, float(response.get("intensity_score", 0.5))))
        wtp = max(0.0, min(1.0, float(response.get("wtp_score", 0.5))))
        ai_rep = max(0.0, min(1.0, float(response.get("ai_replaceability_score", 0.5))))

        raw_ids = [str(c["id"]) for c in cluster_complaints if c.get("id")]

        products = Counter(
            c["product_mentioned"] for c in cluster_complaints if c.get("product_mentioned")
        )
        cluster_type = "product" if products else "unmet_need"
        product_name = products.most_common(1)[0][0] if products else None

        # Compute data signals (raw, not yet normalized)
        unique_products = len(products)
        avg_engagement = sum(c.get("score", 0) for c in cluster_complaints) / len(cluster_complaints)

        return {
            "cluster_type": cluster_type,
            "product_name": product_name,
            "products_mentioned": dict(products),
            "problem_theme": response.get("theme", "Unnamed theme"),
            "complaint_count": len(cluster_complaints),
            "raw_ids": raw_ids,
            "sample_complaints": response.get("sample_quotes", [])[:5],
            "intensity_score": round(intensity, 3),
            "wtp_score": round(wtp, 3),
            "ai_replaceability_score": round(ai_rep, 3),
            "unique_products": unique_products,
            "avg_engagement": round(avg_engagement, 2),
            "composite_score": 0.0,  # computed after normalization
            "is_weak_signal": False,
        }
    except Exception as e:
        logger.error(f"Cluster labeling failed: {e}")
        return None


def _compute_composite_scores(clusters: list[dict]) -> None:
    """Compute normalized composite scores across all clusters.

    Uses max-normalization so each signal is scaled 0-1 relative to the
    best cluster in this run. This makes scores comparable across signals
    with different natural ranges (complaint count vs product diversity).
    """
    import math

    if not clusters:
        return

    # Find max values for normalization
    max_volume = max(math.log(c["complaint_count"] + 1) for c in clusters)
    max_diversity = max(c["unique_products"] for c in clusters) or 1
    max_engagement = max(math.log(1 + c["avg_engagement"]) for c in clusters) or 1

    for c in clusters:
        # Data signals (normalized 0-1)
        volume_norm = math.log(c["complaint_count"] + 1) / max_volume if max_volume else 0
        diversity_norm = c["unique_products"] / max_diversity
        engagement_norm = math.log(1 + c["avg_engagement"]) / max_engagement if max_engagement else 0

        data_score = (
            W_VOLUME * volume_norm
            + W_DIVERSITY * diversity_norm
            + W_ENGAGEMENT * engagement_norm
        )

        # LLM signals (already 0-1)
        llm_score = (
            W_INTENSITY * c["intensity_score"]
            + W_WTP * c["wtp_score"]
            + W_AI_FIT * c["ai_replaceability_score"]
        )

        c["composite_score"] = round(W_DATA * data_score + W_LLM * llm_score, 3)

        logger.info(
            f"Score for '{c['problem_theme'][:40]}': "
            f"data={data_score:.3f} (vol={volume_norm:.2f} div={diversity_norm:.2f} eng={engagement_norm:.2f}) "
            f"llm={llm_score:.3f} (int={c['intensity_score']:.2f} wtp={c['wtp_score']:.2f} ai={c['ai_replaceability_score']:.2f}) "
            f"→ composite={c['composite_score']:.3f}"
        )


# --- Main entry point ---

async def cluster_and_label(complaints: list[dict], top_n: int = 10) -> list[dict]:
    """Embed all complaints, reduce dimensions, cluster, split oversized, label with Sonnet.

    Pipeline:
    1. Gemini embeddings (3072d)
    2. UMAP dimensionality reduction (3072d → 15d)
    3. HDBSCAN clustering on reduced space
    4. Split any cluster > MAX_CLUSTER_SIZE via recursive sub-clustering
    5. LLM labels and scores each cluster
    """
    if not complaints:
        return []

    # Step 1 — Embed
    logger.info(f"Embedding {len(complaints)} complaints...")
    try:
        texts = [c.get("body", "")[:600] for c in complaints]
        embeddings = await _embed_texts(texts)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []

    # Step 2 — UMAP + HDBSCAN
    labels = _reduce_and_cluster(embeddings)

    clusters: dict[int, list[dict]] = {}
    embeddings_by_cluster: dict[int, list[list[float]]] = {}
    for complaint, embedding, label in zip(complaints, embeddings, labels):
        if label == -1:
            continue
        clusters.setdefault(label, []).append(complaint)
        embeddings_by_cluster.setdefault(label, []).append(embedding)

    noise_count = labels.count(-1)
    logger.info(f"HDBSCAN: {len(clusters)} clusters, {noise_count} noise from {len(complaints)} complaints")

    if not clusters:
        logger.warning("No clusters found — all complaints were noise")
        return []

    # Step 3 — Split oversized clusters
    clusters = _split_oversized_clusters(clusters, embeddings_by_cluster)
    logger.info(f"After splitting: {len(clusters)} clusters")

    # Step 4 — Label each cluster concurrently
    semaphore = asyncio.Semaphore(3)

    async def label_with_semaphore(cluster_complaints):
        async with semaphore:
            return await _label_cluster(cluster_complaints)

    tasks = [label_with_semaphore(c) for c in clusters.values()]
    results = await asyncio.gather(*tasks)

    labeled = [r for r in results if r is not None]

    # Step 5 — Compute composite scores (needs all clusters for normalization)
    _compute_composite_scores(labeled)
    labeled.sort(key=lambda x: x["composite_score"], reverse=True)

    logger.info(f"Labeled {len(labeled)} clusters (returning top {top_n})")
    return labeled[:top_n]
