-- WanderLab Pipeline Schema
-- Run this in Supabase SQL Editor

-- Pipeline runs: one row per weekly execution, coordinates all agents
CREATE TABLE pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_of DATE NOT NULL UNIQUE,

    scout_status TEXT NOT NULL DEFAULT 'pending',
    scout_started_at TIMESTAMPTZ,
    scout_finished_at TIMESTAMPTZ,
    scout_error TEXT,
    scout_raw_count INTEGER,

    filter_status TEXT NOT NULL DEFAULT 'pending',
    filter_started_at TIMESTAMPTZ,
    filter_finished_at TIMESTAMPTZ,
    filter_error TEXT,
    filter_scored_count INTEGER,

    analyst_status TEXT NOT NULL DEFAULT 'pending',
    analyst_started_at TIMESTAMPTZ,
    analyst_finished_at TIMESTAMPTZ,
    analyst_error TEXT,
    analyst_brief_count INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_scout_status CHECK (scout_status IN ('pending', 'running', 'done', 'failed', 'timeout')),
    CONSTRAINT valid_filter_status CHECK (filter_status IN ('pending', 'running', 'done', 'failed', 'timeout')),
    CONSTRAINT valid_analyst_status CHECK (analyst_status IN ('pending', 'running', 'done', 'failed', 'timeout'))
);

-- Raw complaints scraped by Scout
CREATE TABLE pipeline_raw (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT,
    subreddit TEXT,
    app_name TEXT,
    app_id TEXT,
    title TEXT,
    body TEXT NOT NULL,
    author TEXT,
    score INTEGER,
    posted_at TIMESTAMPTZ,
    is_complaint BOOLEAN NOT NULL DEFAULT true,
    product_mentioned TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_source CHECK (source IN ('reddit', 'appstore')),
    UNIQUE (source, source_id)
);

-- Scored complaints produced by Filter
CREATE TABLE pipeline_filtered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    raw_id UUID NOT NULL UNIQUE REFERENCES pipeline_raw(id),
    intensity_score REAL NOT NULL,
    wtp_score REAL NOT NULL,
    ai_replaceability_score REAL NOT NULL,
    composite_score REAL NOT NULL,
    scoring_rationale TEXT NOT NULL,
    passes_threshold BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_intensity CHECK (intensity_score >= 0.0 AND intensity_score <= 1.0),
    CONSTRAINT valid_wtp CHECK (wtp_score >= 0.0 AND wtp_score <= 1.0),
    CONSTRAINT valid_ai_replaceability CHECK (ai_replaceability_score >= 0.0 AND ai_replaceability_score <= 1.0),
    CONSTRAINT valid_composite CHECK (composite_score >= 0.0 AND composite_score <= 1.0)
);

-- Opportunity briefs produced by Analyst
CREATE TABLE pipeline_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    product_name TEXT NOT NULL,
    problem_summary TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    avg_composite_score REAL NOT NULL,
    opportunity_brief TEXT NOT NULL,
    verdict TEXT NOT NULL,
    verdict_rationale TEXT NOT NULL,
    filtered_ids UUID[] NOT NULL,
    discord_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_verdict CHECK (verdict IN ('build', 'watch', 'skip'))
);
