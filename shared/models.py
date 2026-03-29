"""Pydantic models for pipeline data."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineRun(BaseModel):
    id: UUID | None = None
    week_of: date
    scout_status: str = "pending"
    scout_started_at: datetime | None = None
    scout_finished_at: datetime | None = None
    scout_error: str | None = None
    scout_raw_count: int | None = None
    filter_status: str = "pending"
    filter_started_at: datetime | None = None
    filter_finished_at: datetime | None = None
    filter_error: str | None = None
    filter_scored_count: int | None = None
    analyst_status: str = "pending"
    analyst_started_at: datetime | None = None
    analyst_finished_at: datetime | None = None
    analyst_error: str | None = None
    analyst_brief_count: int | None = None
    created_at: datetime | None = None


class RawComplaint(BaseModel):
    id: UUID | None = None
    run_id: UUID
    source: str
    source_id: str
    source_url: str | None = None
    subreddit: str | None = None
    app_name: str | None = None
    app_id: str | None = None
    title: str | None = None
    body: str
    author: str | None = None
    score: int | None = None
    posted_at: datetime | None = None
    is_complaint: bool = True
    product_mentioned: str | None = None
    created_at: datetime | None = None


class ScoredComplaint(BaseModel):
    id: UUID | None = None
    run_id: UUID
    raw_id: UUID
    intensity_score: float = Field(ge=0.0, le=1.0)
    wtp_score: float = Field(ge=0.0, le=1.0)
    ai_replaceability_score: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)
    scoring_rationale: str
    passes_threshold: bool
    created_at: datetime | None = None


class OpportunityBrief(BaseModel):
    id: UUID | None = None
    run_id: UUID
    product_name: str
    problem_summary: str
    evidence_count: int
    avg_composite_score: float
    opportunity_brief: str
    verdict: str = Field(pattern=r"^(build|watch|skip)$")
    verdict_rationale: str
    filtered_ids: list[UUID]
    discord_message_id: str | None = None
    created_at: datetime | None = None
