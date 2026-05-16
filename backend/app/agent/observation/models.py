"""Pydantic contracts for agent observation intelligence."""
from typing import Literal

from pydantic import BaseModel, Field


ObservationSignal = Literal[
    "empty_result",
    "large_row_removal",
    "high_warning_rate",
    "validation_failed",
    "execution_error",
    "schema_changed",
    # Task 6 – deeper observation signals
    "suspected_wrong_column",
    "suspected_wrong_value",
    "data_quality_issue",
    "needs_inspection",
]


ObservationRecommendedAction = Literal[
    "clarify",
    "plan_workflow",
    "preview_workflow",
    "confirm_required",
    "stop_with_result",
    "stop_with_error",
]


class CandidateFix(BaseModel):
    """A suggested corrective action derived from observation evidence."""

    action: str
    rationale: str
    evidence: str | None = None


class ObservationSummary(BaseModel):
    status: Literal["not_observed", "ok", "warning", "error"] = "not_observed"
    signals: list[ObservationSignal] = Field(default_factory=list)
    message: str | None = None
    possible_causes: list[str] = Field(default_factory=list)
    recommended_next_action: ObservationRecommendedAction | None = None
    workflow_state: str | None = None
    # Task 6 – deeper diagnostics
    diagnostic_explanation: str | None = None
    candidate_fixes: list[CandidateFix] = Field(default_factory=list)
