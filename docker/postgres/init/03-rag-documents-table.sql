-- RAG document corpus table with pgvector embeddings.
-- Each row represents one indexed corpus document (transformation doc,
-- failure case, correction case, or workflow example).
-- source_path is the unique key; indexing is idempotent via ON CONFLICT.
-- The embedding column dimension must match the chosen embedding model:
--   text-embedding-3-small  → 1536
--   text-embedding-ada-002  → 1536

CREATE TABLE IF NOT EXISTS rag_documents (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type    TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    metadata    JSONB,
    source_path TEXT        NOT NULL UNIQUE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding   vector(1536)
);

-- HNSW index for fast cosine-similarity search on the embedding column.
-- Built only when the table has rows; CREATE INDEX IF NOT EXISTS is safe to re-run.
CREATE INDEX IF NOT EXISTS idx_rag_documents_embedding
    ON rag_documents
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_rag_documents_doc_type
    ON rag_documents (doc_type);
