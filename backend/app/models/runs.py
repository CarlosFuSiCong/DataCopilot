"""Pydantic models for workflow run history and rerun."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.runtime import WorkflowAttempt, WorkflowContextSummary, WorkflowRunState
from app.models.workflow import WorkflowStep


class RunRecord(BaseModel):
    """Metadata for a single workflow run (used in list and detail views)."""

    run_id: str
    dataset_id: str
    query: str | None
    status: str
    step_count: int | None
    row_count: int | None
    created_at: datetime
    parent_run_id: str | None = None
    # Full fields only in detail response:
    explanation: str | None = None
    planned_steps: list[dict[str, Any]] | None = None
    state: WorkflowRunState | None = None
    attempts: list[WorkflowAttempt] | None = None
    context_summary: WorkflowContextSummary | None = None


class RunListResponse(BaseModel):
    runs: list[RunRecord]
    total: int


class RerunRequest(BaseModel):
    """Request to rerun a previous run, optionally with edited workflow steps."""

    dataset_id: str
    steps: list[WorkflowStep]
    query: str | None = None  # original query, kept for context
