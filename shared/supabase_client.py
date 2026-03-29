"""Supabase client and typed helpers for all pipeline tables."""

import logging
from datetime import date, datetime, timezone
from uuid import UUID

from supabase import create_client

from shared.config import settings

logger = logging.getLogger(__name__)

supabase = create_client(settings.supabase_url, settings.supabase_service_key)


# --- Pipeline Runs ---

def create_run(week_of: date) -> dict:
    """Create a new pipeline run for the given week. Always inserts a fresh row."""
    result = supabase.table("pipeline_runs").insert({"week_of": week_of.isoformat()}).execute()
    return result.data[0]


def update_run_status(run_id: str, agent: str, status: str, **kwargs) -> dict:
    """Update an agent's status columns on pipeline_runs.

    Args:
        run_id: The pipeline run UUID.
        agent: One of 'scout', 'filter', 'analyst'.
        status: One of 'pending', 'running', 'done', 'failed', 'timeout'.
        **kwargs: Additional columns to update (e.g., scout_raw_count=42).
    """
    update = {f"{agent}_status": status}
    if status == "running":
        update[f"{agent}_started_at"] = datetime.now(timezone.utc).isoformat()
    elif status in ("done", "failed", "timeout"):
        update[f"{agent}_finished_at"] = datetime.now(timezone.utc).isoformat()
    if status == "failed" and "error" in kwargs:
        update[f"{agent}_error"] = kwargs.pop("error")

    # Merge any extra columns (e.g., scout_raw_count)
    for k, v in kwargs.items():
        update[f"{agent}_{k}"] = v

    result = supabase.table("pipeline_runs").update(update).eq("id", run_id).execute()
    return result.data[0] if result.data else {}


def get_run_status(week_of: date) -> dict | None:
    """Get the pipeline run for a given week, or None if it doesn't exist."""
    result = supabase.table("pipeline_runs").select("*").eq("week_of", week_of.isoformat()).execute()
    return result.data[0] if result.data else None


# --- Pipeline Raw ---

def insert_raw_complaints(run_id: str, records: list[dict]) -> int:
    """Bulk insert raw complaints. Skips duplicates on (source, source_id). Returns insert count."""
    if not records:
        return 0
    for r in records:
        r["run_id"] = run_id

    # Deduplicate within the batch before inserting — upsert fails if two rows
    # in the same payload share the same (source, source_id)
    seen = set()
    deduped = []
    for r in records:
        key = (r.get("source"), r.get("source_id"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if len(deduped) < len(records):
        logger.warning(f"Deduplicated {len(records) - len(deduped)} duplicate records before insert")

    # Insert in chunks of 100 — if one chunk fails, log and continue
    total = 0
    chunk_size = 100
    for i in range(0, len(deduped), chunk_size):
        chunk = deduped[i:i + chunk_size]
        try:
            result = supabase.table("pipeline_raw").upsert(
                chunk, on_conflict="source,source_id"
            ).execute()
            total += len(result.data) if result.data else 0
        except Exception as e:
            logger.error(f"Failed to insert chunk {i//chunk_size + 1}, skipping: {e}")

    logger.info(f"Inserted {total} raw complaints")
    return total


def get_raw_complaints(run_id: str, only_complaints: bool = True) -> list[dict]:
    """Get raw complaints for a run. If only_complaints, filters to is_complaint=true."""
    query = supabase.table("pipeline_raw").select("*").eq("run_id", run_id)
    if only_complaints:
        query = query.eq("is_complaint", True)
    result = query.execute()
    return result.data or []


# --- Pipeline Filtered ---

def insert_scored_complaints(run_id: str, records: list[dict]) -> int:
    """Bulk insert scored complaints. Returns insert count."""
    if not records:
        return 0
    for r in records:
        r["run_id"] = run_id
    result = supabase.table("pipeline_filtered").upsert(
        records, on_conflict="raw_id"
    ).execute()
    count = len(result.data) if result.data else 0
    logger.info(f"Inserted {count} scored complaints")
    return count


def get_passing_complaints(run_id: str) -> list[dict]:
    """Get scored complaints that pass the threshold, joined with raw data."""
    # Get filtered records that pass
    filtered = (
        supabase.table("pipeline_filtered")
        .select("*, pipeline_raw(*)")
        .eq("run_id", run_id)
        .eq("passes_threshold", True)
        .execute()
    )
    return filtered.data or []


# --- Pipeline Ranked ---

def insert_ranked_clusters(run_id: str, records: list[dict]) -> int:
    """Bulk insert ranked clusters from Ranker. Returns insert count."""
    if not records:
        return 0
    for r in records:
        r["run_id"] = run_id
    result = supabase.table("pipeline_ranked").insert(records).execute()
    count = len(result.data) if result.data else 0
    logger.info(f"Inserted {count} ranked clusters")
    return count


def get_ranked_clusters(run_id: str, top_n: int = 10) -> list[dict]:
    """Get top N non-weak-signal clusters for Analyst, ordered by composite score."""
    result = (
        supabase.table("pipeline_ranked")
        .select("*")
        .eq("run_id", run_id)
        .eq("is_weak_signal", False)
        .order("composite_score", desc=True)
        .limit(top_n)
        .execute()
    )
    return result.data or []


def get_latest_run_id() -> str | None:
    """Get the most recently created pipeline run ID."""
    result = (
        supabase.table("pipeline_runs")
        .select("id")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


# --- Pipeline Opportunities ---

def insert_opportunities(run_id: str, records: list[dict]) -> int:
    """Bulk insert opportunity briefs. Returns insert count."""
    if not records:
        return 0
    for r in records:
        r["run_id"] = run_id
        # Convert UUID lists to strings for Supabase
        if "filtered_ids" in r:
            r["filtered_ids"] = [str(uid) for uid in r["filtered_ids"]]
    result = supabase.table("pipeline_opportunities").insert(records).execute()
    count = len(result.data) if result.data else 0
    logger.info(f"Inserted {count} opportunity briefs")
    return count
