-- Update pipeline_opportunities for new Ranker→Analyst flow
ALTER TABLE pipeline_opportunities
  ADD COLUMN ranked_id UUID REFERENCES pipeline_ranked(id),
  ADD COLUMN buyer_profile TEXT,
  ADD COLUMN wedge TEXT,
  ADD COLUMN build_complexity TEXT,
  ADD COLUMN product_concept TEXT;
