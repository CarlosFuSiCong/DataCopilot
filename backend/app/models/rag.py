"""Pydantic models for the RAG context pipeline."""
from pydantic import BaseModel


class RetrievedDoc(BaseModel):
    type: str
    description: str
    keywords: list[str]
    parameters: list[dict]
    example: dict
    score: int


class DatasetSummary(BaseModel):
    """Lightweight dataset profile passed as planner context."""
    filename: str
    row_count: int
    column_count: int
    columns: list[dict]  # {name, dtype, missing_count, missing_pct}


class RetrievalDebug(BaseModel):
    method: str
    query_tokens: list[str]
    all_scores: dict[str, int]


class RAGContext(BaseModel):
    query: str
    retrieved_docs: list[RetrievedDoc]
    dataset_summary: DatasetSummary
    debug: RetrievalDebug


class RAGContextRequest(BaseModel):
    dataset_id: str
    query: str
    top_k: int = 3
