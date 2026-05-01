-- Dataset metadata table.
-- Raw CSV files are NOT stored here; Postgres holds only metadata and a storage_uri pointer.
-- storage_backend + storage_uri support future migration from 'local' to 's3' or 'minio'
-- without changing the table schema.
-- user_id is nullable and has no foreign key in MVP3; reserved for future multi-user support.

CREATE TABLE IF NOT EXISTS datasets (
    id              UUID        PRIMARY KEY,
    user_id         UUID,
    filename        TEXT        NOT NULL,
    storage_backend TEXT        NOT NULL DEFAULT 'local',
    storage_uri     TEXT        NOT NULL,
    content_type    TEXT        NOT NULL DEFAULT 'text/csv',
    size_bytes      BIGINT,
    row_count       INTEGER,
    column_count    INTEGER,
    profile_json    JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partial index for future user-scoped queries; no-op while user_id is always NULL.
CREATE INDEX IF NOT EXISTS idx_datasets_user_id
    ON datasets (user_id)
    WHERE user_id IS NOT NULL;
