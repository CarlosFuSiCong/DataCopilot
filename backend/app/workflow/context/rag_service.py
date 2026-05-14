"""RAG service for DataCopilot.

Public surface:
  load_docs()      — load all corpus JSON docs from disk.
  retrieve()       — synchronous keyword retrieval (used by tests and scripts).
  build_context()  — async; assembles a full RAGContext using the configured
                     retrieval method (keyword or pgvector, set by settings).

Retrieval is delegated to the retriever interface in app.workflow.context.retriever.
The active method is controlled by settings.retrieval_method.
"""
import json
import logging
import re
from pathlib import Path

from app.core.config import settings
from app.models.dataset import DatasetProfile
from app.models.rag import (
    DatasetSummary,
    RAGContext,
    RetrievalDebug,
    RetrievedDoc,
)

logger = logging.getLogger(__name__)

_APP_DIR = Path(__file__).parents[2]

# Ordered list of corpus directories. New doc types can be added here.
_CORPUS_DIRS = [
    _APP_DIR / "transformations",
    _APP_DIR / "rag_docs" / "failure_cases",
    _APP_DIR / "rag_docs" / "correction_cases",
    _APP_DIR / "rag_docs" / "workflow_examples",
]


def load_docs() -> list[dict]:
    """Load all RAG corpus JSON docs from all corpus directories."""
    docs = []
    for directory in _CORPUS_DIRS:
        for path in sorted(directory.glob("*.json")):
            try:
                docs.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("Could not load doc '%s': %s", path.name, exc)
    logger.info("Loaded %d RAG corpus docs from %d directories", len(docs), len(_CORPUS_DIRS))
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


def _doc_key(doc: dict) -> str:
    """Return a stable unique key for a corpus doc.

    Prefer source_path (present in all docs since Task 4). Fall back to
    the legacy 'type' field so old tests that pass docs without source_path
    continue to work.
    """
    return doc.get("source_path") or doc.get("type", "unknown")


def retrieve(query: str, docs: list[dict], top_k: int = 3) -> tuple[list[RetrievedDoc], RetrievalDebug]:
    """Score and rank docs against the query; return top-k with debug info."""
    query_tokens = set(_tokenise(query))
    scores: dict[str, int] = {_doc_key(doc): _score_doc(doc, query_tokens) for doc in docs}

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
            planner_guidance=doc.get("planner_guidance", ""),
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
        "Retrieved %d docs for query %r: scores=%s",
        len(retrieved),
        query,
        scores,
    )
    return retrieved, debug


async def build_context(
    query: str,
    dataset_profile: DatasetProfile,
    top_k: int = 3,
    docs: list[dict] | None = None,
) -> RAGContext:
    """Assemble a full RAGContext from retrieval + dataset profile.

    Pass ``docs`` explicitly to force keyword retrieval with a fixed corpus
    (test mode). In production the retriever is chosen from
    settings.retrieval_method.
    """
    # Import here to avoid circular import at module load time
    from app.workflow.context.retriever import get_retriever

    retriever = get_retriever(docs=docs)
    retrieved, debug = await retriever.retrieve(query, top_k=top_k)

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
