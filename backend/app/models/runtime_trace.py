"""Stable workflow runtime trace contracts."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.observation.models import ObservationSummary


WorkflowRunState = Literal[
    "draft",
    "needs_clarification",
    "planned",
    "validation_failed",
    "repair_attempted",
    "preview_ready",
    "warning_review",
    "confirmed",
    "executed",
    "failed",
]


class WorkflowContext(BaseModel):
    dataset_id: str
    dataset_hash: str
    query: str
    clarification_answer: str | None = None
    dataset_profile: dict[str, Any]
    current_schema: list[str]
    previous_steps: list[dict[str, Any]] = Field(default_factory=list)
    current_steps: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_method: str | None = None
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_debug: dict[str, Any] | None = None
    execution_boundary: Literal["preview", "warning", "confirm", "executed", "failed"] = "preview"


class WorkflowContextSummary(BaseModel):
    query: str
    dataset_hash: str
    schema_columns: list[str]
    row_count: int
    retrieved_docs: list[str] = Field(default_factory=list)
    planned_step_types: list[str] = Field(default_factory=list)
    status: WorkflowRunState
    boundary: str
    validation_status: str | None = None
    warning_count: int = 0
    error_count: int = 0
    last_observation: ObservationSummary | None = None
    # Tool suggestions derived from observation signals (Task 8).
    # Each entry has tool_type, signal, and reason fields.
    tool_suggestions: list[dict[str, str]] = Field(default_factory=list)
    # Analyst flow suggestions produced when suggest_analysis_steps runs (Task 9).
    # Each entry is a serialised AnalystStepSuggestion dict.
    analyst_flow_suggestions: list[dict[str, Any]] = Field(default_factory=list)


class AttemptSummary(BaseModel):
    attempt_index: int
    query: str
    retrieval_method: str | None = None
    retrieved_docs: list[str] = Field(default_factory=list)
    planner_raw_output: str | None = None
    parsed_step_types: list[str] = Field(default_factory=list)
    validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    preview_status: Literal["not_run", "passed", "warning", "error"] = "not_run"
    warning_count: int = 0
    error_count: int = 0
    repair_reason: str | None = None
    final_status: WorkflowRunState


class WorkflowAttempt(BaseModel):
    attempt_index: int
    query: str
    retrieval_method: str | None = None
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    planner_raw_output: str | None = None
    parsed_steps: list[dict[str, Any]] = Field(default_factory=list)
    validation_result: dict[str, Any] | None = None
    repair_reason: str | None = None
    final_status: WorkflowRunState
    summary: AttemptSummary


class WorkflowTrace(BaseModel):
    state: WorkflowRunState
    context: WorkflowContext
    context_summary: WorkflowContextSummary
    attempts: list[WorkflowAttempt] = Field(default_factory=list)
