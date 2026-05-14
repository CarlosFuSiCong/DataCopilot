"""Workflow execution result contracts."""
from typing import Literal

from pydantic import BaseModel, Field


class StepIssue(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class StepResult(BaseModel):
    step_index: int
    step_type: str
    status: Literal["success", "warning", "error"] = "success"
    issues: list[StepIssue] = Field(default_factory=list)
    input_row_count: int
    output_row_count: int
    input_column_count: int
    output_column_count: int
    # Absolute number of rows removed or added by this step.
    affected_rows: int = 0
    match_rate: float | None = None
    affected_rate: float | None = None
    preview: list[dict] = Field(default_factory=list)
    message: str


class StepLog(BaseModel):
    step_index: int
    step_type: str
    rows_before: int
    rows_after: int
    message: str


class ExecutionResult(BaseModel):
    row_count: int
    column_count: int
    columns: list[str]
    preview: list[dict]
    step_results: list[StepResult]
    # Backward-compatible log shape for MVP1 frontend/tests.
    logs: list[StepLog]
    # True when the workflow includes a generate_summary step.
    has_summary: bool
