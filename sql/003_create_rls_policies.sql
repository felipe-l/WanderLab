-- Row Level Security policies
-- Currently using service role key, so RLS is permissive.
-- Enable stricter policies when the Vercel dashboard is added.

ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_filtered ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_ranked ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_opportunities ENABLE ROW LEVEL SECURITY;

-- Allow full access for service role (agents use this)
CREATE POLICY "Service role full access" ON pipeline_runs
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON pipeline_raw
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON pipeline_filtered
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON pipeline_ranked
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON pipeline_opportunities
    FOR ALL USING (true) WITH CHECK (true);

-- TODO: Add anon/authenticated read-only policies for the Vercel dashboard
-- CREATE POLICY "Dashboard read access" ON pipeline_opportunities
--     FOR SELECT USING (auth.role() = 'authenticated');
