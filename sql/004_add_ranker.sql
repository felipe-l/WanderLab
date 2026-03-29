-- Add ranker status tracking to pipeline_runs
ALTER TABLE pipeline_runs
  ADD COLUMN ranker_status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN ranker_started_at TIMESTAMPTZ,
  ADD COLUMN ranker_finished_at TIMESTAMPTZ,
  ADD COLUMN ranker_error TEXT,
  ADD COLUMN ranker_cluster_count INTEGER;

ALTER TABLE pipeline_runs
  ADD CONSTRAINT valid_ranker_status CHECK (ranker_status IN ('pending', 'running', 'done', 'failed', 'timeout'));

-- Ranked clusters produced by Ranker
CREATE TABLE pipeline_ranked (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id),
    cluster_type TEXT NOT NULL,
    product_name TEXT,
    problem_theme TEXT NOT NULL,
    complaint_count INTEGER NOT NULL,
    raw_ids UUID[] NOT NULL,
    sample_complaints TEXT[] NOT NULL,
    intensity_score REAL NOT NULL,
    wtp_score REAL NOT NULL,
    ai_replaceability_score REAL NOT NULL,
    composite_score REAL NOT NULL,
    is_weak_signal BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_cluster_type CHECK (cluster_type IN ('product', 'unmet_need', 'weak_signal'))
);

CREATE INDEX idx_pipeline_ranked_run_id ON pipeline_ranked(run_id);
CREATE INDEX idx_pipeline_ranked_composite ON pipeline_ranked(run_id, composite_score DESC);
