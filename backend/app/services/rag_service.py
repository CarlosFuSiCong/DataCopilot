"""RAG service for DataCopilot.

Retrieval strategy (MVP): keyword matching.
- Load all transformation docs from app/transformations/*.json.
- Tokenise the user query (lowercase, split on whitespace and punctuation).
- Score each doc by counting how many query tokens appear in the doc's
  keywords list or description text.
- Return the top-k docs with the highest score; include all docs when
  fewer than top_k have a non-zero score.

This can be upgraded to embedding-based retrieval in a later task without
changing the public interface.
"""
import json
import logging
import re
from pathlib import Path

from app.models.dataset import DatasetProfile
from app.models.rag import (
    DatasetSummary,
    RAGContext,
    RetrievalDebug,
    RetrievedDoc,
)

logger = logging.getLogger(__name__)

_DOCS_DIR = Path(__file__).parent.parent / "transformations"


def load_docs() -> list[dict]:
    """Load all transformation JSON docs from the transformations directory."""
    docs = []
    for path in sorted(_DOCS_DIR.glob("*.json")):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Could not load transformation doc '%s': %s", path.name, exc)
    logger.info("Loaded %d transformation docs", len(docs))
    return docs


def _tokenise(text: str) -> list[str]:
    """Lowercase and split on non-alphanumeric characters (handles CJK too)."""
    tokens = re.split(r"[\s\W]+", text.lower())
    return [t for t in tokens if t]


def _score_doc(doc: dict, query_tokens: set[str]) -> int:
    """Return the number of query tokens that match any keyword or description word."""
    doc_tokens: set[str] = set()
    for kw in doc.get("keywords", []):
        doc_tokens.update(_tokenise(kw))
    doc_tokens.update(_tokenise(doc.get("description", "")))
    return len(query_tokens & doc_tokens)


def retrieve(query: str, docs: list[dict], top_k: int = 3) -> tuple[list[RetrievedDoc], RetrievalDebug]:
    """Score and rank docs against the query; return top-k with debug info."""
    query_tokens = set(_tokenise(query))
    scores: dict[str, int] = {doc["type"]: _score_doc(doc, query_tokens) for doc in docs}

    ranked = sorted(docs, key=lambda d: scores[d["type"]], reverse=True)
    selected = ranked[:top_k]

    retrieved = [
        RetrievedDoc(
            type=doc["type"],
            description=doc["description"],
            keywords=doc["keywords"],
            parameters=doc.get("parameters", []),
            example=doc["example"],
            score=scores[doc["type"]],
        )
        for doc in selected
    ]

    debug = RetrievalDebug(
        method="keyword_matching",
        query_tokens=sorted(query_tokens),
        all_scores=scores,
    )

    logger.info(
        "Retrieved %d docs for query %r: scores=%s",
        len(retrieved),
        query,
        scores,
    )
    return retrieved, debug


def build_context(
    query: str,
    dataset_profile: DatasetProfile,
    top_k: int = 3,
    docs: list[dict] | None = None,
) -> RAGContext:
    """Assemble a full RAGContext from transformation retrieval + dataset profile.

    Pass `docs` explicitly in tests to avoid filesystem reads.
    """
    if docs is None:
        docs = load_docs()

    retrieved, debug = retrieve(query, docs, top_k=top_k)

    dataset_summary = DatasetSummary(
        filename=dataset_profile.filename,
        row_count=dataset_profile.row_count,
        column_count=dataset_profile.column_count,
        columns=[col.model_dump() for col in dataset_profile.columns],
    )

    return RAGContext(
        query=query,
        retrieved_docs=retrieved,
        dataset_summary=dataset_summary,
        debug=debug,
    )
