"""Result contracts for each planner decomposition layer.

Each layer preserves both raw input/output and the parsed structured result
so the pipeline is inspectable at every step.
"""
from typing import Any

from pydantic import BaseModel, Field

from app.agent.task_intake.intent import ParsedTaskIntent
from app.models.workflow_steps import WorkflowStep


class IntentParseResult(BaseModel):
    raw_query: str
    parsed: ParsedTaskIntent
    # Ratio of query terms that matched known dataset columns (0-1).
    candidate_column_match_ratio: float = 0.0


class ToolSelectionResult(BaseModel):
    intent: str
    # Tool type names ordered by relevance, highest first.
    candidate_tools: list[str] = Field(default_factory=list)
    selected_tool: str | None = None
    # Raw score per tool type from retrieved docs + intent + observation bonuses.
    scores: dict[str, float] = Field(default_factory=dict)
    # Tools recommended because of observation signals (may not appear in retrieved docs).
    observation_suggestions: list["ObservationToolSuggestion"] = Field(default_factory=list)


class ObservationToolSuggestion(BaseModel):
    """One tool recommended by an observation signal."""

    tool_type: str
    signal: str
    reason: str


class ParameterResolutionResult(BaseModel):
    raw_step: dict[str, Any]
    resolved_step: dict[str, Any]
    missing_required_fields: list[str] = Field(default_factory=list)
    # Fields that were fixed or defaulted (e.g. case-insensitive column match, default value).
    defaulted_fields: list[str] = Field(default_factory=list)
    column_errors: list[str] = Field(default_factory=list)


class WorkflowBuildResult(BaseModel):
    raw_steps: list[dict[str, Any]]
    steps: list[WorkflowStep]
    step_count: int
