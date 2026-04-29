"""Pydantic models for the chat (full pipeline) endpoint."""
from pydantic import BaseModel

from app.models.rag import RAGContext
from app.models.workflow import ExecutionResult


class ChatRequest(BaseModel):
    dataset_id: str
    query: str
    rag_top_k: int = 3


class ChatResponse(BaseModel):
    query: str
    # Raw step dicts as produced by the planner — inspectable before validation
    planned_steps: list[dict]
    execution_result: ExecutionResult
    rag_context: RAGContext
    # Natural-language explanation grounded in the execution result
    explanation: str
