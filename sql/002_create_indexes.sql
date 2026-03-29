-- Indexes for pipeline tables

CREATE INDEX idx_pipeline_runs_week_of ON pipeline_runs(week_of);

CREATE INDEX idx_pipeline_raw_run_id ON pipeline_raw(run_id);
-- (source, source_id) unique constraint already creates an index

CREATE INDEX idx_pipeline_filtered_run_id ON pipeline_filtered(run_id);
CREATE INDEX idx_pipeline_filtered_run_passes ON pipeline_filtered(run_id, passes_threshold);

CREATE INDEX idx_pipeline_opportunities_run_id ON pipeline_opportunities(run_id);
