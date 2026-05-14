"""Workflow response envelopes that include runtime trace metadata."""
from pydantic import BaseModel, Field

from app.models.runtime_trace import WorkflowAttempt, WorkflowContextSummary, WorkflowRunState
from app.models.workflow_execution import ExecutionResult


class ConfirmResponse(BaseModel):
    """Response from the confirm execution endpoint."""

    query: str
    planned_steps: list[dict]
    execution_result: ExecutionResult
    explanation: str
    # UUID of the persisted result run; used by the frontend to download the
    # full result CSV via GET /api/runs/{run_id}/download.
    run_id: str | None = None
    state: WorkflowRunState = "executed"
    attempts: list[WorkflowAttempt] = Field(default_factory=list)
    context_summary: WorkflowContextSummary | None = None
