"""RAG corpus indexing script.

Reads all corpus JSON docs from the four corpus directories, generates
embeddings via the OpenAI embedding API, and upserts each document into the
rag_documents Postgres table.

Upsert key: source_path (UNIQUE constraint in 03-rag-documents-table.sql).
Re-running this script refreshes existing rows and inserts new ones — it will
never create duplicates.

Usage (inside the container or locally with DATABASE_URL pointing to Postgres):

    # Run from the backend/ directory so .env is loaded automatically
    python scripts/index_rag_corpus.py

    # Dry-run: print docs without writing to database
    python scripts/index_rag_corpus.py --dry-run

Environment variables (read from .env or shell):
    DATABASE_URL        asyncpg-compatible Postgres connection string
    LLM_API_KEY         OpenAI API key used for embeddings
    LLM_BASE_URL        OpenAI-compatible base URL (default: https://api.openai.com/v1)
    EMBEDDING_MODEL     model name (default: text-embedding-3-small)
    EMBEDDING_DIMENSIONS vector size — must match rag_documents.embedding (default: 1536)
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import openai

# ---------------------------------------------------------------------------
# Bootstrap: add backend root to sys.path so app.core.config is importable
# when the script is run from any working directory.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402  (after sys.path fix)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("index_rag_corpus")

# ---------------------------------------------------------------------------
# Corpus directories — must match the order in rag_service.py
# ---------------------------------------------------------------------------
_APP_DIR = _BACKEND_DIR / "app"
_CORPUS_DIRS = [
    _APP_DIR / "transformations",
    _APP_DIR / "rag_docs" / "failure_cases",
    _APP_DIR / "rag_docs" / "correction_cases",
    _APP_DIR / "rag_docs" / "workflow_examples",
]


def load_corpus_docs() -> list[dict]:
    """Load all JSON docs from every corpus directory."""
    docs: list[dict] = []
    for directory in _CORPUS_DIRS:
        for path in sorted(directory.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                docs.append(doc)
                logger.debug("Loaded %s", path.relative_to(_BACKEND_DIR))
            except Exception as exc:
                logger.warning("Skipping %s — %s", path.name, exc)
    logger.info("Loaded %d corpus docs from %d directories", len(docs), len(_CORPUS_DIRS))
    return docs


def build_embed_text(doc: dict) -> str:
    """Concatenate the fields that best represent the doc's meaning for embedding.

    Title + description capture the primary intent.
    Keywords add retrieval-friendly tokens (including Chinese variants).

    Raises ValueError if the resulting text is empty — sending an empty string
    to the embeddings API either causes an API error or produces a meaningless
    zero-like vector.
    """
    parts: list[str] = []
    if doc.get("title"):
        parts.append(doc["title"])
    if doc.get("description"):
        parts.append(doc["description"])
    keywords = doc.get("keywords", [])
    if keywords:
        parts.append(", ".join(keywords))
    text = "\n".join(parts)
    if not text:
        raise ValueError(
            f"Doc '{doc.get('source_path', '?')}' has no title, description, or keywords — "
            "cannot build embed text."
        )
    return text


def build_metadata(doc: dict) -> dict:
    """Return a JSON-serialisable metadata dict for storage in the JSONB column.

    Stores the full original doc so the pgvector retriever can reconstruct a
    RetrievedDoc without re-reading the filesystem.
    """
    return {k: v for k, v in doc.items()}


async def embed_texts(texts: list[str], client: openai.AsyncOpenAI) -> list[list[float]]:
    """Call the OpenAI embeddings endpoint and return a list of float vectors."""
    # OpenAI accepts up to 2048 inputs per request; our corpus is small enough
    # to send in a single batch.
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    # response.data is ordered to match the input list
    return [item.embedding for item in response.data]


async def upsert_documents(
    conn: asyncpg.Connection,
    rows: list[dict],
) -> None:
    """Upsert a batch of prepared row dicts into rag_documents."""
    sql = """
        INSERT INTO rag_documents
            (doc_type, title, content, metadata, source_path, updated_at, embedding)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (source_path)
        DO UPDATE SET
            doc_type   = EXCLUDED.doc_type,
            title      = EXCLUDED.title,
            content    = EXCLUDED.content,
            metadata   = EXCLUDED.metadata,
            updated_at = EXCLUDED.updated_at,
            embedding  = EXCLUDED.embedding
    """
    now = datetime.now(tz=timezone.utc)
    records = [
        (
            row["doc_type"],
            row["title"],
            row["content"],
            json.dumps(row["metadata"]),
            row["source_path"],
            now,
            row["embedding"],
        )
        for row in rows
    ]
    await conn.executemany(sql, records)


async def run(dry_run: bool = False) -> None:
    docs = load_corpus_docs()
    if not docs:
        logger.error("No corpus docs found — check that _CORPUS_DIRS paths are correct.")
        sys.exit(1)

    # Validate that every doc has the mandatory source_path field
    missing_source = [d.get("title", "?") for d in docs if not d.get("source_path")]
    if missing_source:
        logger.error(
            "The following docs are missing 'source_path' and cannot be upserted: %s",
            missing_source,
        )
        sys.exit(1)

    # Build embed texts and catch any docs that lack embeddable content before
    # making any API calls — fail fast with a clear per-doc error message.
    texts: list[str] = []
    bad_docs: list[str] = []
    for doc in docs:
        try:
            texts.append(build_embed_text(doc))
        except ValueError as exc:
            bad_docs.append(str(exc))
    if bad_docs:
        for msg in bad_docs:
            logger.error(msg)
        logger.error("%d doc(s) cannot be indexed — fix the corpus files and re-run.", len(bad_docs))
        sys.exit(1)

    if dry_run:
        logger.info("--- DRY RUN: showing embed texts ---")
        for doc, text in zip(docs, texts):
            logger.info("[%s] %s\n%s\n", doc.get("source_path"), doc.get("title"), text[:200])
        return

    openai_client = openai.AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    logger.info(
        "Generating embeddings with model=%s for %d docs...",
        settings.embedding_model,
        len(texts),
    )
    embeddings = await embed_texts(texts, openai_client)
    logger.info("Embeddings generated (dim=%d)", len(embeddings[0]))

    rows = [
        {
            "doc_type": doc.get("doc_type", "transformation"),
            "title": doc.get("title", doc.get("type", "")),
            "content": text,
            "metadata": build_metadata(doc),
            "source_path": doc["source_path"],
            "embedding": embedding,
        }
        for doc, text, embedding in zip(docs, texts, embeddings)
    ]

    logger.info("Connecting to Postgres at %s...", settings.database_url)
    conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    try:
        # Register pgvector codec so asyncpg can serialise Python lists as vectors
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.set_type_codec(
            "vector",
            encoder=lambda v: "[" + ",".join(str(x) for x in v) + "]",
            decoder=lambda v: [float(x) for x in v.strip("[]").split(",")],
            schema="pg_catalog",
            format="text",
        )
        await upsert_documents(conn, rows)
        logger.info("Upserted %d documents into rag_documents.", len(rows))
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Index RAG corpus into rag_documents table.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print embed texts without writing to the database.",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
