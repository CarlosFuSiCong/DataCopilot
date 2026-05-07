-- Extend workflow_runs with history and rerun support columns.
-- Uses ADD COLUMN IF NOT EXISTS so this is safe to apply on existing databases.

ALTER TABLE workflow_runs
    ADD COLUMN IF NOT EXISTS query          TEXT,
    ADD COLUMN IF NOT EXISTS status         TEXT NOT NULL DEFAULT 'success',
    ADD COLUMN IF NOT EXISTS explanation    TEXT,
    ADD COLUMN IF NOT EXISTS planned_steps  JSONB,
    ADD COLUMN IF NOT EXISTS step_count     INTEGER,
    ADD COLUMN IF NOT EXISTS parent_run_id  UUID REFERENCES workflow_runs(id);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at
    ON workflow_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_parent
    ON workflow_runs (parent_run_id);
