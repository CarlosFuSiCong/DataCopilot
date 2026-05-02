"""Retriever interface and implementations for DataCopilot RAG.

Exposes a single async Retriever protocol:
    retrieved_docs, debug = await retriever.retrieve(query, top_k)

Two implementations are provided:
  - KeywordRetriever   baseline; token-overlap scoring against in-memory docs.
  - PgvectorRetriever  semantic search via OpenAI embeddings + pgvector.

Use get_retriever(method) to obtain the configured implementation.
The active method is controlled by settings.retrieval_method.
"""
import json
import logging
import re
from typing import Protocol, runtime_checkable

import openai

from app.core import database
from app.core.config import settings
from app.models.rag import RetrievalDebug, RetrievedDoc
from app.services.rag_service import load_docs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
        self, query: str, top_k: int = 3
    ) -> tuple[list[RetrievedDoc], RetrievalDebug]:
        """Return top-k retrieved docs and debug metadata for a query."""
        ...


# ---------------------------------------------------------------------------
# Keyword retriever
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> list[str]:
    tokens = re.split(r"[\s\W]+", text.lower())
    return [t for t in tokens if t]


def _doc_key(doc: dict) -> str:
    return doc.get("source_path") or doc.get("type", "unknown")


def _score_doc(doc: dict, query_tokens: set[str]) -> float:
    doc_tokens: set[str] = set()
    for kw in doc.get("keywords", []):
        doc_tokens.update(_tokenise(kw))
    doc_tokens.update(_tokenise(doc.get("description", "")))
    return float(len(query_tokens & doc_tokens))


class KeywordRetriever:
    """Token-overlap retriever operating on in-memory corpus docs.

    Pass ``docs`` explicitly to avoid filesystem reads (useful in tests).
    When ``docs`` is None the corpus is loaded from disk on each call.
    """

    def __init__(self, docs: list[dict] | None = None) -> None:
        self._docs = docs

    async def retrieve(
        self, query: str, top_k: int = 3
    ) -> tuple[list[RetrievedDoc], RetrievalDebug]:
        docs = self._docs if self._docs is not None else load_docs()
        query_tokens = set(_tokenise(query))
        scores: dict[str, float] = {
            _doc_key(doc): _score_doc(doc, query_tokens) for doc in docs
        }

        ranked = sorted(docs, key=lambda d: scores[_doc_key(d)], reverse=True)
        selected = ranked[:top_k]

        retrieved = [
            RetrievedDoc(
                doc_type=doc.get("doc_type", "transformation"),
                source_path=doc.get("source_path", ""),
                title=doc.get("title", doc.get("type", "")),
                type=doc.get("type", ""),
                description=doc["description"],
                keywords=doc.get("keywords", []),
                parameters=doc.get("parameters", []),
                example=doc.get("example", {}),
                score=scores[_doc_key(doc)],
            )
            for doc in selected
        ]

        debug = RetrievalDebug(
            method="keyword_matching",
            query_tokens=sorted(query_tokens),
            all_scores=scores,
        )

        logger.info(
            "KeywordRetriever: retrieved %d docs for query %r",
            len(retrieved),
            query,
        )
        return retrieved, debug


# ---------------------------------------------------------------------------
# pgvector retriever
# ---------------------------------------------------------------------------

class PgvectorRetriever:
    """Semantic retriever using OpenAI embeddings + pgvector cosine similarity.

    Requires:
    - rag_documents table populated by scripts/index_rag_corpus.py.
    - database.pool initialised (app startup lifespan).
    - settings.llm_api_key set for OpenAI embedding calls.
    """

    def __init__(self, openai_client: openai.AsyncOpenAI | None = None) -> None:
        self._client = openai_client or openai.AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    async def _embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=settings.embedding_model,
            input=[text],
        )
        return response.data[0].embedding

    async def retrieve(
        self, query: str, top_k: int = 3
    ) -> tuple[list[RetrievedDoc], RetrievalDebug]:
        if database.pool is None:
            raise RuntimeError(
                "PgvectorRetriever requires an active database pool. "
                "Ensure the app lifespan has run database.connect()."
            )

        query_embedding = await self._embed(query)
        # Format as pgvector literal: '[0.1,0.2,...]'
        vec_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"

        sql = """
            SELECT
                doc_type,
                title,
                content,
                metadata,
                source_path,
                1 - (embedding <=> $1::vector) AS similarity
            FROM rag_documents
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """

        async with database.pool.acquire() as conn:
            rows = await conn.fetch(sql, vec_literal, top_k)

        retrieved: list[RetrievedDoc] = []
        all_scores: dict[str, float] = {}

        for row in rows:
            source_path = row["source_path"]
            similarity = float(row["similarity"])
            all_scores[source_path] = similarity

            meta: dict = json.loads(row["metadata"]) if row["metadata"] else {}

            retrieved.append(
                RetrievedDoc(
                    doc_type=row["doc_type"],
                    source_path=source_path,
                    title=row["title"],
                    type=meta.get("type", ""),
                    description=meta.get("description", row["content"]),
                    keywords=meta.get("keywords", []),
                    parameters=meta.get("parameters", []),
                    example=meta.get("example", {}),
                    score=similarity,
                )
            )

        debug = RetrievalDebug(
            method="pgvector",
            query_tokens=[],
            all_scores=all_scores,
            embedding_model=settings.embedding_model,
        )

        logger.info(
            "PgvectorRetriever: retrieved %d docs for query %r (top similarity=%.4f)",
            len(retrieved),
            query,
            max(all_scores.values(), default=0.0),
        )
        return retrieved, debug


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_retriever(
    method: str | None = None,
    docs: list[dict] | None = None,
) -> Retriever:
    """Return the retriever matching *method* (defaults to settings.retrieval_method).

    Pass ``docs`` to force KeywordRetriever with a fixed corpus — used in tests
    to avoid filesystem reads and database/OpenAI calls.
    """
    resolved = method or settings.retrieval_method

    if docs is not None:
        # Explicit docs always resolve to keyword retriever (test / override mode)
        return KeywordRetriever(docs=docs)

    if resolved == "pgvector":
        return PgvectorRetriever()

    return KeywordRetriever()
