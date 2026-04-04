-- Add products_mentioned to pipeline_ranked for cross-product cluster metadata
ALTER TABLE pipeline_ranked
  ADD COLUMN products_mentioned JSONB NOT NULL DEFAULT '{}';

-- Drop weak_signal cluster type — HDBSCAN noise replaces this concept
ALTER TABLE pipeline_ranked
  DROP CONSTRAINT valid_cluster_type;

ALTER TABLE pipeline_ranked
  ADD CONSTRAINT valid_cluster_type CHECK (cluster_type IN ('product', 'unmet_need', 'weak_signal'));
