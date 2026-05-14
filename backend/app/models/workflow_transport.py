"""Workflow HTTP request and preview response contracts."""
from pydantic import BaseModel

from app.models.workflow_execution import StepResult
from app.models.workflow_steps import WorkflowStep


class WorkflowRequest(BaseModel):
    dataset_id: str
    steps: list[WorkflowStep]


class PreviewResponse(BaseModel):
    """Response for the preview-only execution endpoint.

    The workflow runs through the validator and executor (with risk checks)
    but the result explainer is never called. Errors are captured instead of
    raised so the client can inspect the full partial result.
    """

    planned_steps: list[dict]
    step_results: list[StepResult]
    has_warnings: bool
    has_errors: bool
    # Index of the step that caused a blocking error and stopped execution.
    blocked_at_step: int | None = None


class ConfirmRequest(BaseModel):
    """Request to execute a pre-reviewed workflow and generate an explanation."""

    dataset_id: str
    steps: list[WorkflowStep]
    # Original user query, used by the result explainer for language detection
    # and grounding the explanation in the user's intent.
    query: str
    # When confirming after a rerun, carry the original run's ID so the new
    # run record can reference it via parent_run_id.
    parent_run_id: str | None = None
