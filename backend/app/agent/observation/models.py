"""Pydantic contracts for agent observation intelligence."""
from typing import Literal

from pydantic import BaseModel, Field


ObservationSignal = Literal[
    "empty_result",
    "high_warning_rate",
    "validation_failed",
    "execution_error",
    "schema_changed",
]


ObservationRecommendedAction = Literal[
    "clarify",
    "plan_workflow",
    "preview_workflow",
    "confirm_required",
    "stop_with_result",
    "stop_with_error",
]


class ObservationSummary(BaseModel):
    status: Literal["not_observed", "ok", "warning", "error"] = "not_observed"
    signals: list[ObservationSignal] = Field(default_factory=list)
    message: str | None = None
    possible_causes: list[str] = Field(default_factory=list)
    recommended_next_action: ObservationRecommendedAction | None = None
    workflow_state: str | None = None
