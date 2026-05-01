"""Pydantic models for the chat (full pipeline) endpoint."""
from pydantic import BaseModel

from app.models.rag import RAGContext
from app.models.workflow import ExecutionResult, StepResult


class ChatRequest(BaseModel):
    dataset_id: str
    query: str
    rag_top_k: int = 3
    # When True (default) and no warnings/errors are detected, the backend
    # automatically runs execute() + explain() and returns the full result.
    # When False, always returns preview-only so the UI can show the Confirm button.
    auto_confirm: bool = True


class ChatResponse(BaseModel):
    query: str
    # Raw step dicts as produced by the planner — inspectable before validation
    planned_steps: list[dict]
    # Per-step execution metrics and risk-rule issues from the preview pass
    step_results: list[StepResult]
    has_warnings: bool
    has_errors: bool
    rag_context: RAGContext
    # Populated only when auto_confirm triggered a full execute + explain pass.
    # None means the client should show a Confirm button and call /workflows/confirm.
    explanation: str | None = None
    execution_result: ExecutionResult | None = None
