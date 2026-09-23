"""Result contracts for workflow planning decomposition layers."""
from typing import Any

from pydantic import BaseModel, Field

from app.models.workflow_steps import WorkflowStep
from app.workflow.intake.intent import ParsedTaskIntent


class IntentParseResult(BaseModel):
    raw_query: str
    parsed: ParsedTaskIntent
    candidate_column_match_ratio: float = 0.0


class ParameterResolutionResult(BaseModel):
    raw_step: dict[str, Any]
    resolved_step: dict[str, Any]
    missing_required_fields: list[str] = Field(default_factory=list)
    defaulted_fields: list[str] = Field(default_factory=list)
    column_errors: list[str] = Field(default_factory=list)


class WorkflowBuildResult(BaseModel):
    raw_steps: list[dict[str, Any]]
    steps: list[WorkflowStep]
    step_count: int
