-- Workflow runs table.
-- Each confirmed execution creates one run record.  The full result CSV is
-- stored on local disk (same scheme as raw datasets); only metadata lives here.
-- run_id is a UUID so download URLs are not guessable by enumeration.

CREATE TABLE IF NOT EXISTS workflow_runs (
    id              UUID        PRIMARY KEY,
    dataset_id      UUID        NOT NULL REFERENCES datasets(id),
    steps_hash      TEXT        NOT NULL,
    filename        TEXT        NOT NULL,
    storage_uri     TEXT        NOT NULL,
    row_count       INTEGER,
    size_bytes      BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_dataset_id
    ON workflow_runs (dataset_id);
